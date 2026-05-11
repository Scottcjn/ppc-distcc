import io
import json
import os
import struct
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import ppc_compile_wrapper as wrapper


def frame(msg_type, data):
    if isinstance(data, str):
        data = data.encode("utf-8")
    msg_type = msg_type[:4].ljust(4).encode("utf-8")
    return struct.pack("!I", len(data)) + msg_type + data


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


class RecordingSocket:
    def __init__(self, response=b""):
        self.response = bytearray(response)
        self.sent = bytearray()
        self.connected_to = None
        self.timeouts = []
        self.closed = False

    def settimeout(self, timeout):
        self.timeouts.append(timeout)

    def connect(self, address):
        self.connected_to = address

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


class SocketFactory:
    def __init__(self, response):
        self.response = response
        self.instance = None

    def __call__(self, *args, **kwargs):
        self.instance = RecordingSocket(self.response)
        return self.instance


class WrapperHelperTests(unittest.TestCase):
    def test_is_compile_job_requires_compile_flag_and_source_file(self):
        self.assertTrue(wrapper.is_compile_job(["-O2", "-c", "src/main.c"]))
        self.assertTrue(wrapper.is_compile_job(["-c", "src/view.mm", "-o", "view.o"]))

        self.assertFalse(wrapper.is_compile_job(["src/main.c", "-o", "app"]))
        self.assertFalse(wrapper.is_compile_job(["-c", "README.md"]))

    def test_get_source_and_output_extracts_explicit_output(self):
        args = [
            "-Wall",
            "-Iinclude",
            "-DNAME=value",
            "-c",
            "src/lib.cpp",
            "-o",
            "build/lib.o",
        ]

        self.assertEqual(
            wrapper.get_source_and_output(args),
            ("src/lib.cpp", "build/lib.o"),
        )

    def test_get_hosts_reads_environment_without_empty_entries(self):
        with mock.patch.dict(os.environ, {"PPC_DISTCC_HOSTS": "g5.local, ,g4.local"}, clear=False):
            with mock.patch("random.shuffle", lambda hosts: None):
                self.assertEqual(wrapper.get_hosts(), ["g5.local", "g4.local"])

    def test_get_hosts_returns_copy_of_defaults(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with mock.patch("random.shuffle", lambda hosts: None):
                hosts = wrapper.get_hosts()

        self.assertEqual(hosts, wrapper.DEFAULT_HOSTS)
        self.assertIsNot(hosts, wrapper.DEFAULT_HOSTS)

    def test_send_and_receive_message_frame_payloads(self):
        out = RecordingSocket()
        wrapper.send_message(out, "LONGTYPE", "payload")
        self.assertEqual(decode_frames(out.sent), [("LONG", b"payload")])

        incoming = RecordingSocket(frame("OK", b"object-bytes"))
        self.assertEqual(wrapper.recv_message(incoming), ("OK", b"object-bytes"))

    def test_try_remote_compile_sends_parsed_job_metadata(self):
        error_response = {
            "returncode": 7,
            "stderr": "compile failed\n",
        }
        socket_factory = SocketFactory(frame("ERR", json.dumps(error_response)))

        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "hello.c"
            output = Path(tmpdir) / "hello.o"
            source.write_text("int main(void) { return 0; }\n")

            args = [
                "-Iinclude",
                "-I",
                "generated/include",
                "-DDEBUG",
                "-D",
                "VALUE=1",
                "-O2",
                "-c",
                str(source),
                "-o",
                str(output),
            ]

            with mock.patch.object(wrapper.socket, "socket", socket_factory):
                with mock.patch.object(wrapper.os, "getpid", return_value=1234):
                    with mock.patch("sys.stderr", new=io.StringIO()) as stderr:
                        result = wrapper.try_remote_compile(
                            "g5.local",
                            5555,
                            "gcc-10",
                            str(source),
                            str(output),
                            args,
                        )

        self.assertEqual(result, 7)
        self.assertEqual(stderr.getvalue(), "compile failed\n")
        self.assertEqual(socket_factory.instance.connected_to, ("g5.local", 5555))
        self.assertTrue(socket_factory.instance.closed)

        sent_frames = decode_frames(socket_factory.instance.sent)
        self.assertEqual([item[0] for item in sent_frames], ["JOB", "SRC", "HDR"])

        job = json.loads(sent_frames[0][1].decode("utf-8"))
        self.assertEqual(job["job_id"], "cli-1234")
        self.assertEqual(job["compiler"], "gcc-10")
        self.assertEqual(job["source_name"], "hello.c")
        self.assertEqual(job["include_paths"], ["include", "generated/include"])
        self.assertEqual(job["defines"], ["DEBUG", "VALUE=1"])
        self.assertEqual(job["args"], ["-O2"])


if __name__ == "__main__":
    unittest.main()
