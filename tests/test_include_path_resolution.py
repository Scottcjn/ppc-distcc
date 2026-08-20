"""Include paths have to survive the trip to a worker that compiles elsewhere.

The worker builds in its own temp directory, so anything the build machine
expressed relative to its cwd is meaningless once it arrives.  These tests pin
that down at the payload level, and - when a compiler is present - by running
the real worker over a real socket.
"""

import json
import os
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ppc_compile_wrapper as wrapper
import ppc_compile_worker as worker


def decode_frames(data):
    frames = []
    offset = 0
    while offset < len(data):
        length = struct.unpack("!I", data[offset:offset + 4])[0]
        msg_type = data[offset + 4:offset + 8].decode("utf-8").strip()
        start = offset + 8
        end = start + length
        frames.append((msg_type, data[start:end]))
        offset = end
    return frames


def frame(msg_type, data):
    if isinstance(data, str):
        data = data.encode("utf-8")
    msg_type = msg_type[:4].ljust(4).encode("utf-8")
    return struct.pack("!I", len(data)) + msg_type + data


class RecordingSocket:
    def __init__(self, response=b""):
        self.response = bytearray(response)
        self.sent = bytearray()
        self.closed = False

    def settimeout(self, timeout):
        pass

    def connect(self, address):
        self.address = address

    def sendall(self, data):
        self.sent.extend(data)

    def recv(self, size):
        if not self.response:
            return b""
        chunk = self.response[:size]
        del self.response[:size]
        return bytes(chunk)

    def close(self):
        self.closed = True


class ResolveIncludePathsTests(unittest.TestCase):
    def test_relative_paths_are_resolved_against_our_cwd(self):
        cwd = os.getcwd()
        resolved = wrapper.resolve_include_paths("src/lib.c", ["include", "../shared"])

        self.assertEqual(
            resolved[1:],
            [os.path.join(cwd, "include"), os.path.abspath(os.path.join(cwd, "..", "shared"))],
        )
        for path in resolved:
            self.assertTrue(os.path.isabs(path), "%s is not absolute" % path)

    def test_source_directory_comes_first(self):
        resolved = wrapper.resolve_include_paths("src/lib.c", ["include"])

        self.assertEqual(resolved[0], os.path.dirname(os.path.abspath("src/lib.c")))

    def test_absolute_paths_are_kept(self):
        resolved = wrapper.resolve_include_paths("/build/src/lib.c", ["/opt/sdk/include"])

        self.assertIn("/opt/sdk/include", resolved)

    def test_source_directory_is_not_repeated(self):
        resolved = wrapper.resolve_include_paths("src/lib.c", ["src", "src/"])

        self.assertEqual(resolved.count(os.path.dirname(os.path.abspath("src/lib.c"))), 1)

    def test_empty_entry_is_dropped_not_turned_into_cwd(self):
        resolved = wrapper.resolve_include_paths("/build/src/lib.c", [""])

        self.assertEqual(resolved, ["/build/src"])

    def test_coordinator_resolves_the_same_way(self):
        import ppc_compile_coordinator as coordinator

        self.assertEqual(
            coordinator.resolve_include_paths("src/lib.c", ["include"]),
            wrapper.resolve_include_paths("src/lib.c", ["include"]),
        )


class JobPayloadTests(unittest.TestCase):
    def _send_job(self, args, source, output):
        sock = RecordingSocket(frame("ERR", json.dumps({"returncode": 1, "stderr": ""})))

        with mock.patch.object(wrapper.socket, "socket", lambda *a, **k: sock):
            with mock.patch("sys.stderr", new=open(os.devnull, "w")):
                wrapper.try_remote_compile("g5.local", 5555, "gcc", source, output, args)

        job = json.loads(decode_frames(sock.sent)[0][1].decode("utf-8"))
        return job

    def test_include_paths_leave_absolute(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            source = os.path.join(tmpdir, "hello.c")
            open(source, "w").write("int main(void){return 0;}\n")

            job = self._send_job(
                ["-Iinclude", "-I", "generated/include", "-O2", "-c", source, "-o", "hello.o"],
                source,
                "hello.o",
            )

        for path in job["include_paths"]:
            self.assertTrue(os.path.isabs(path), "%s went out relative" % path)
        self.assertIn(os.path.join(os.getcwd(), "include"), job["include_paths"])

    def test_source_directory_is_advertised_to_the_worker(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            source = os.path.join(tmpdir, "hello.c")
            open(source, "w").write("int main(void){return 0;}\n")

            job = self._send_job(["-c", source, "-o", "hello.o"], source, "hello.o")

        self.assertEqual(job["include_paths"], [tmpdir])

    def test_defines_and_other_args_are_untouched(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            source = os.path.join(tmpdir, "hello.c")
            open(source, "w").write("int main(void){return 0;}\n")

            job = self._send_job(
                ["-DDEBUG", "-D", "VALUE=1", "-O2", "-c", source, "-o", "hello.o"],
                source,
                "hello.o",
            )

        self.assertEqual(job["defines"], ["DEBUG", "VALUE=1"])
        self.assertEqual(job["args"], ["-O2"])


HAVE_CC = shutil.which("gcc") is not None


@unittest.skipUnless(HAVE_CC, "needs a working gcc to run a real worker")
class RealWorkerTests(unittest.TestCase):
    """Drive the actual worker over a socket - no mocked compile."""

    def setUp(self):
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server.bind(("127.0.0.1", 0))
        self.server.listen(5)
        self.port = self.server.getsockname()[1]
        self.stop = False

        def serve():
            while not self.stop:
                try:
                    conn, addr = self.server.accept()
                except OSError:
                    return
                thread = threading.Thread(target=worker.handle_client, args=(conn, addr))
                thread.daemon = True
                thread.start()

        self.thread = threading.Thread(target=serve)
        self.thread.daemon = True
        self.thread.start()

        self.tmpdir = tempfile.mkdtemp(prefix="distcc_test_")
        self.addCleanup(shutil.rmtree, self.tmpdir, True)

    def tearDown(self):
        self.stop = True
        self.server.close()

    def _compile(self, source, output, args):
        devnull = open(os.devnull, "w")
        self.addCleanup(devnull.close)
        with mock.patch("sys.stderr", new=devnull):
            with mock.patch("sys.stdout", new=devnull):
                return wrapper.try_remote_compile(
                    "127.0.0.1", self.port, "gcc", source, output, args
                )

    def test_relative_include_dir_compiles_on_the_worker(self):
        os.makedirs(os.path.join(self.tmpdir, "inc"))
        open(os.path.join(self.tmpdir, "inc", "util.h"), "w").write("#define MAGIC 42\n")
        source = os.path.join(self.tmpdir, "uses_header.c")
        open(source, "w").write('#include "util.h"\nint magic(void){return MAGIC;}\n')
        output = os.path.join(self.tmpdir, "uses_header.o")

        cwd = os.getcwd()
        os.chdir(self.tmpdir)
        try:
            result = self._compile(source, output, ["-Iinc", "-c", source, "-o", output])
        finally:
            os.chdir(cwd)

        self.assertEqual(result, 0)
        self.assertTrue(os.path.exists(output))

    def test_header_next_to_the_source_compiles_on_the_worker(self):
        open(os.path.join(self.tmpdir, "sibling.h"), "w").write("#define SIB 7\n")
        source = os.path.join(self.tmpdir, "sibling_user.c")
        open(source, "w").write('#include "sibling.h"\nint sib(void){return SIB;}\n')
        output = os.path.join(self.tmpdir, "sibling_user.o")

        result = self._compile(source, output, ["-c", source, "-o", output])

        self.assertEqual(result, 0)
        self.assertTrue(os.path.exists(output))

    def test_object_matches_a_local_compile(self):
        open(os.path.join(self.tmpdir, "sibling.h"), "w").write("#define SIB 7\n")
        source = os.path.join(self.tmpdir, "sibling_user.c")
        open(source, "w").write('#include "sibling.h"\nint sib(void){return SIB;}\n')
        remote_out = os.path.join(self.tmpdir, "remote.o")
        local_out = os.path.join(self.tmpdir, "local.o")

        self.assertEqual(self._compile(source, remote_out, ["-c", source, "-o", remote_out]), 0)
        subprocess.check_call(["gcc", "-c", source, "-o", local_out], cwd=self.tmpdir)

        self.assertEqual(open(remote_out, "rb").read(), open(local_out, "rb").read())

    def test_a_genuinely_missing_header_still_fails(self):
        source = os.path.join(self.tmpdir, "bad.c")
        open(source, "w").write('#include "nope.h"\nint x(void){return 1;}\n')
        output = os.path.join(self.tmpdir, "bad.o")

        result = self._compile(source, output, ["-c", source, "-o", output])

        self.assertNotEqual(result, 0)
        self.assertFalse(os.path.exists(output))


if __name__ == "__main__":
    unittest.main()
