#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
PPC Distributed Compile Wrapper
Drop-in replacement for gcc/g++/clang that distributes compilation.

Compatible with Python 2.5+ (Tiger/Leopard/Sorbet)

Usage:
  ln -s ppc_compile_wrapper.py /usr/local/bin/ppc-gcc
  ln -s ppc_compile_wrapper.py /usr/local/bin/ppc-g++
  ln -s ppc_compile_wrapper.py /usr/local/bin/ppc-clang

  # Then use:
  make CC=ppc-gcc CXX=ppc-g++

Environment:
  PPC_DISTCC_HOSTS    - Comma-separated list of worker hosts
  PPC_DISTCC_FALLBACK - If set, fall back to local compile on failure
  PPC_DISTCC_VERBOSE  - Show verbose output
  PPC_DISTCC_DISABLED - If set, always compile locally
"""

import socket
import subprocess
import tempfile
import os
import sys
import struct
import time

# Python 2/3 compatibility
PY2 = sys.version_info[0] == 2

# Try to import json, fall back to minimal implementation for Python 2.5
try:
    import json
except ImportError:
    try:
        import simplejson as json
    except ImportError:
        # Minimal JSON implementation for Python 2.5
        class _MinimalJson:
            def dumps(self, obj):
                """Encode object to JSON string"""
                if obj is None:
                    return 'null'
                elif obj is True:
                    return 'true'
                elif obj is False:
                    return 'false'
                elif isinstance(obj, int) or isinstance(obj, float):
                    return str(obj)
                elif isinstance(obj, str):
                    # Escape special chars
                    s = obj.replace('\\', '\\\\').replace('"', '\\"')
                    s = s.replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t')
                    return '"%s"' % s
                elif isinstance(obj, list):
                    return '[%s]' % ', '.join(self.dumps(x) for x in obj)
                elif isinstance(obj, dict):
                    pairs = ['"%s": %s' % (k, self.dumps(v)) for k, v in obj.items()]
                    return '{%s}' % ', '.join(pairs)
                else:
                    return '"%s"' % str(obj)

            def loads(self, s):
                """Decode JSON string to object (simplified parser)"""
                s = s.strip()
                if s == 'null':
                    return None
                elif s == 'true':
                    return True
                elif s == 'false':
                    return False
                elif s.startswith('"') and s.endswith('"'):
                    # String - unescape
                    val = s[1:-1]
                    val = val.replace('\\n', '\n').replace('\\r', '\r').replace('\\t', '\t')
                    val = val.replace('\\"', '"').replace('\\\\', '\\')
                    return val
                elif s.startswith('{'):
                    # Object - simple parser
                    result = {}
                    s = s[1:-1].strip()
                    if not s:
                        return result
                    # Parse key-value pairs
                    depth = 0
                    start = 0
                    in_string = False
                    for i, c in enumerate(s):
                        if c == '"' and (i == 0 or s[i-1] != '\\'):
                            in_string = not in_string
                        elif not in_string:
                            if c in '{[':
                                depth = depth + 1
                            elif c in '}]':
                                depth = depth - 1
                            elif c == ',' and depth == 0:
                                self._parse_pair(s[start:i], result)
                                start = i + 1
                    if start < len(s):
                        self._parse_pair(s[start:], result)
                    return result
                elif s.startswith('['):
                    # Array - simple parser
                    result = []
                    s = s[1:-1].strip()
                    if not s:
                        return result
                    depth = 0
                    start = 0
                    in_string = False
                    for i, c in enumerate(s):
                        if c == '"' and (i == 0 or s[i-1] != '\\'):
                            in_string = not in_string
                        elif not in_string:
                            if c in '{[':
                                depth = depth + 1
                            elif c in '}]':
                                depth = depth - 1
                            elif c == ',' and depth == 0:
                                result.append(self.loads(s[start:i].strip()))
                                start = i + 1
                    if start < len(s):
                        result.append(self.loads(s[start:].strip()))
                    return result
                else:
                    # Number
                    try:
                        if '.' in s:
                            return float(s)
                        return int(s)
                    except ValueError:
                        return s

            def _parse_pair(self, pair, result):
                """Parse a key:value pair"""
                pair = pair.strip()
                if not pair:
                    return
                colon = pair.find(':')
                if colon > 0:
                    key = pair[:colon].strip()
                    if key.startswith('"') and key.endswith('"'):
                        key = key[1:-1]
                    value = pair[colon+1:].strip()
                    result[key] = self.loads(value)

        json = _MinimalJson()

# Configuration
DEFAULT_PORT = 5555
CONNECT_TIMEOUT = 2.0
COMPILE_TIMEOUT = 300.0

# Default worker hosts (G5 only - G4s lack libiconv 7.0 for gcc-10)
DEFAULT_HOSTS = [
    '192.168.0.130',  # G5
    '192.168.0.179',  # G5 selenamac
]

# Compiler mapping based on script name
COMPILER_MAP = {
    'ppc-gcc': 'gcc',
    'ppc-g++': 'g++',
    'ppc-clang': 'clang',
    'ppc-clang++': 'clang++',
    'ppc-gcc-7': 'gcc-7',
    'ppc-g++-7': 'g++-7',
    'ppc-gcc-10': 'gcc-10',
    'ppc-g++-10': 'g++-10',
}

# Full paths for local fallback (when /usr/local/bin not in PATH)
LOCAL_COMPILER_PATHS = {
    'gcc-10': '/usr/local/bin/gcc-10',
    'g++-10': '/usr/local/bin/g++-10',
    'gcc-7': '/usr/local/bin/gcc-7',
    'g++-7': '/usr/local/bin/g++-7',
    'clang': '/usr/local/bin/clang',
    'clang++': '/usr/local/bin/clang++',
}


def log_msg(msg):
    """Write message to stderr (Python 2.5 compatible)"""
    sys.stderr.write(msg + "\n")
    sys.stderr.flush()


def get_hosts():
    """Get list of worker hosts from environment or default, shuffled for load balancing"""
    import random
    env_hosts = os.environ.get('PPC_DISTCC_HOSTS', '')
    if env_hosts:
        hosts = [h.strip() for h in env_hosts.split(',') if h.strip()]
    else:
        hosts = list(DEFAULT_HOSTS)
    random.shuffle(hosts)  # Randomize order for load balancing
    return hosts


def is_compile_job(args):
    """Check if this is a compile job (not link-only)"""
    has_c_flag = '-c' in args
    has_source = False
    for a in args:
        if not a.startswith('-'):
            if a.endswith('.c') or a.endswith('.cpp') or a.endswith('.cc') or \
               a.endswith('.cxx') or a.endswith('.m') or a.endswith('.mm'):
                has_source = True
                break
    return has_c_flag and has_source


def get_source_and_output(args):
    """Extract source file and output file from args"""
    source = None
    output = None
    extensions = ('.c', '.cpp', '.cc', '.cxx', '.m', '.mm')

    i = 0
    while i < len(args):
        arg = args[i]
        if arg == '-o' and i + 1 < len(args):
            output = args[i + 1]
            i = i + 2
        elif not arg.startswith('-'):
            for ext in extensions:
                if arg.endswith(ext):
                    source = arg
                    break
            i = i + 1
        else:
            i = i + 1

    return source, output


def send_message(sock, msg_type, data):
    """Send a message with length prefix"""
    if isinstance(data, str):
        data = data.encode('utf-8')
    # Pad message type string to 4 chars before encoding
    msg_type_str = msg_type[:4]
    while len(msg_type_str) < 4:
        msg_type_str = msg_type_str + ' '
    header = struct.pack('!I', len(data)) + msg_type_str.encode('utf-8')
    sock.sendall(header + data)


def recv_exactly(sock, n):
    """Receive exactly n bytes"""
    # Python 2/3 compatible empty bytes
    if PY2:
        data = ''
    else:
        data = ''.encode('utf-8')
    while len(data) < n:
        remaining = n - len(data)
        if remaining > 65536:
            remaining = 65536
        chunk = sock.recv(remaining)
        if not chunk:
            raise Exception("Connection closed")
        data = data + chunk
    return data


def recv_message(sock):
    """Receive a message with length prefix"""
    header = recv_exactly(sock, 8)
    length = struct.unpack('!I', header[:4])[0]
    msg_type = header[4:8]
    if not PY2:
        msg_type = msg_type.decode('utf-8')
    msg_type = msg_type.strip()
    data = recv_exactly(sock, length)
    return msg_type, data


def try_remote_compile(host, port, compiler, source_path, output_path, args):
    """Try to compile on a remote worker"""
    verbose = os.environ.get('PPC_DISTCC_VERBOSE')
    sock = None

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(CONNECT_TIMEOUT)
        sock.connect((host, port))
        sock.settimeout(COMPILE_TIMEOUT)

        # Read source file (Python 2.5 compatible - no with statement)
        f = open(source_path, 'rb')
        try:
            source_data = f.read()
        finally:
            f.close()

        # Extract include paths and defines from args
        include_paths = []
        defines = []
        other_args = []

        i = 0
        while i < len(args):
            arg = args[i]
            if arg.startswith('-I'):
                if arg == '-I' and i + 1 < len(args):
                    include_paths.append(args[i + 1])
                    i = i + 2
                else:
                    include_paths.append(arg[2:])
                    i = i + 1
            elif arg.startswith('-D'):
                if arg == '-D' and i + 1 < len(args):
                    defines.append(args[i + 1])
                    i = i + 2
                else:
                    defines.append(arg[2:])
                    i = i + 1
            elif arg == '-c' or arg == '-o' or arg == source_path or arg == output_path:
                i = i + 1
                if arg == '-o':
                    i = i + 1  # Skip output filename too
            else:
                other_args.append(arg)
                i = i + 1

        # Prepare job
        job = {
            'job_id': 'cli-%d' % os.getpid(),
            'compiler': compiler,
            'args': other_args,
            'source_name': os.path.basename(source_path),
            'include_paths': include_paths,
            'defines': defines,
        }

        if verbose:
            log_msg("[ppc-distcc] Sending to %s: %s" % (host, os.path.basename(source_path)))

        # Send job
        send_message(sock, 'JOB', json.dumps(job))
        send_message(sock, 'SRC', source_data)
        send_message(sock, 'HDR', '{}')

        # Wait for response
        msg_type, data = recv_message(sock)

        if msg_type == 'ERR':
            if not PY2:
                data = data.decode('utf-8')
            response = json.loads(data)
            stderr = response.get('stderr', '')
            if stderr:
                sys.stderr.write(stderr)
            return response.get('returncode', 1)

        elif msg_type == 'OK':
            if not PY2:
                data = data.decode('utf-8')
            response = json.loads(data)

            # Receive object file
            msg_type2, obj_data = recv_message(sock)
            if msg_type2 != 'OBJ':
                return 1

            # Write output (Python 2.5 compatible - no with statement)
            f = open(output_path, 'wb')
            try:
                f.write(obj_data)
            finally:
                f.close()

            # Print warnings if any
            warnings = response.get('warnings', '')
            if warnings:
                sys.stderr.write(warnings)

            if verbose:
                elapsed = response.get('elapsed', 0)
                log_msg("[ppc-distcc] Compiled on %s in %.2fs" % (host, elapsed))

            return 0

        else:
            return 1

    except Exception:
        e = sys.exc_info()[1]
        if verbose:
            log_msg("[ppc-distcc] Failed on %s: %s" % (host, str(e)))
        return None

    finally:
        if sock:
            try:
                sock.close()
            except Exception:
                pass


def compile_local(compiler, args):
    """Fall back to local compilation"""
    verbose = os.environ.get('PPC_DISTCC_VERBOSE')
    if verbose:
        log_msg("[ppc-distcc] Compiling locally")

    # Use full path if available (for when /usr/local/bin not in PATH)
    compiler_path = LOCAL_COMPILER_PATHS.get(compiler, compiler)
    cmd = [compiler_path] + args
    return subprocess.call(cmd)


def main():
    # Determine which compiler to use based on how we were called
    script_name = os.path.basename(sys.argv[0])
    compiler = COMPILER_MAP.get(script_name, 'gcc')

    # Check for explicit compiler override
    if 'PPC_DISTCC_COMPILER' in os.environ:
        compiler = os.environ['PPC_DISTCC_COMPILER']

    args = sys.argv[1:]

    # If disabled or not a compile job, just run locally
    if os.environ.get('PPC_DISTCC_DISABLED'):
        return compile_local(compiler, args)

    if not is_compile_job(args):
        # Linking or other non-compile job - run locally
        return compile_local(compiler, args)

    # Extract source and output
    source, output = get_source_and_output(args)
    if not source:
        return compile_local(compiler, args)

    if not output:
        # Generate output name from source
        base = source
        for ext in ('.c', '.cpp', '.cc', '.cxx', '.m', '.mm'):
            if source.endswith(ext):
                base = source[:-len(ext)]
                break
        output = base + '.o'

    # Try each host in order
    hosts = get_hosts()
    for host in hosts:
        result = try_remote_compile(host, DEFAULT_PORT, compiler,
                                    source, output, args)
        if result is not None:
            return result

    # All hosts failed, fall back to local
    fallback = os.environ.get('PPC_DISTCC_FALLBACK', '1')
    if fallback != '0':
        return compile_local(compiler, args)
    else:
        log_msg("[ppc-distcc] All workers failed and fallback disabled")
        return 1


if __name__ == '__main__':
    sys.exit(main())
