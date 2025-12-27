#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
PPC Distributed Compile Worker
Runs on each PowerPC Mac to receive and execute compile jobs.

Compatible with Python 2.5+ and Python 3.7+ (Tiger through modern PPC Linux)

Usage: python ppc_compile_worker.py [--port 5555]
"""

from __future__ import print_function, division, with_statement

import socket
import subprocess
import os
import sys
import hashlib
import struct
import threading
import time
import shutil
import tempfile

# Python 2/3 compatibility
PY2 = sys.version_info[0] == 2

try:
    import json
except ImportError:
    import simplejson as json

try:
    import argparse
    HAS_ARGPARSE = True
except ImportError:
    HAS_ARGPARSE = False

# Python 2/3 string handling
if PY2:
    string_types = (str, unicode)
    def to_bytes(s):
        if isinstance(s, unicode):
            return s.encode('utf-8')
        return s
    def to_str(s):
        if isinstance(s, str):
            return s
        return s.encode('utf-8') if isinstance(s, unicode) else str(s)
else:
    string_types = (str,)
    def to_bytes(s):
        if isinstance(s, str):
            return s.encode('utf-8')
        return s
    def to_str(s):
        if isinstance(s, bytes):
            return s.decode('utf-8')
        return s

try:
    import base64
except ImportError:
    base64 = None

# Configuration
DEFAULT_PORT = 5555
COMPILERS = {
    'gcc': '/usr/bin/gcc',
    'g++': '/usr/bin/g++',
    'gcc-7': '/usr/local/bin/gcc-7',
    'g++-7': '/usr/local/bin/g++-7',
    'gcc-10': '/usr/local/bin/gcc-10',
    'g++-10': '/usr/local/bin/g++-10',
    'clang': None,
    'clang++': None,
}

# Detect clang location
for path in ['/Users/sophia/llvm-3.9-build/bin/clang',
             '/Users/sophia/llvm-3.4-build/Release/bin/clang',
             '/usr/local/bin/clang']:
    if os.path.exists(path):
        COMPILERS['clang'] = path
        COMPILERS['clang++'] = path + '++'
        break


def get_system_info():
    """Get system info for load balancing"""
    info = {
        'hostname': socket.gethostname(),
        'arch': 'ppc',
        'cpus': 1,
        'load': 0.0,
    }

    # Try to get CPU count
    try:
        result = subprocess.Popen(['sysctl', '-n', 'hw.ncpu'],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = result.communicate()
        info['cpus'] = int(out.strip())
    except Exception:
        pass

    # Try to get load average
    try:
        result = subprocess.Popen(['sysctl', '-n', 'vm.loadavg'],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = result.communicate()
        # Strip "{ 1.23 0.45 0.67 }" format - compatible with Py2.5+
        load_str = out.strip().replace('{', '').replace('}', '').split()[0]
        info['load'] = float(load_str)
    except Exception:
        pass

    # Detect G4 vs G5
    try:
        result = subprocess.Popen(['sysctl', '-n', 'machdep.cpu.brand_string'],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = result.communicate()
        brand = to_str(out).lower()
        if '970' in brand or 'g5' in brand:
            info['arch'] = 'g5'
        elif '74' in brand or 'g4' in brand:
            info['arch'] = 'g4'
    except Exception:
        try:
            with open('/proc/cpuinfo', 'r') as f:
                cpuinfo = f.read().lower()
                if '970' in cpuinfo:
                    info['arch'] = 'g5'
                elif '74' in cpuinfo:
                    info['arch'] = 'g4'
        except Exception:
            pass

    return info


def recv_exactly(sock, n):
    """Receive exactly n bytes"""
    data = b''
    while len(data) < n:
        chunk = sock.recv(n - len(data))
        if not chunk:
            raise Exception("Connection closed")
        data += chunk
    return data


def send_message(sock, msg_type, data):
    """Send a message with length prefix"""
    if isinstance(data, str):
        data = to_bytes(data)
    msg_type_bytes = to_bytes(msg_type)[:4].ljust(4, b' ')
    header = struct.pack('!I', len(data)) + msg_type_bytes
    sock.sendall(header + data)


def recv_message(sock):
    """Receive a message with length prefix"""
    header = recv_exactly(sock, 8)
    length = struct.unpack('!I', header[:4])[0]
    msg_type = to_str(header[4:8]).strip()
    data = recv_exactly(sock, length)
    return msg_type, data


def handle_compile_job(sock, job_data):
    """Handle a single compile job"""
    job = json.loads(to_str(job_data))

    job_id = job.get('job_id', 'unknown')
    compiler = job.get('compiler', 'gcc')
    args = job.get('args', [])
    source_name = job.get('source_name', 'input.c')
    source_data = job.get('source_data', '')
    include_paths = job.get('include_paths', [])
    defines = job.get('defines', [])

    print("[%s] Compiling %s with %s" % (job_id, source_name, compiler))

    # Create temp directory for this job
    tmpdir = tempfile.mkdtemp(prefix='ppc_compile_')
    try:
        # Write source file
        source_path = os.path.join(tmpdir, source_name)

        # If source_data is empty, receive it as binary
        if not source_data:
            msg_type, source_bytes = recv_message(sock)
            if msg_type != 'SRC':
                send_message(sock, 'ERR', "Expected SRC, got %s" % msg_type)
                return
        else:
            if base64:
                source_bytes = base64.b64decode(source_data)
            else:
                source_bytes = to_bytes(source_data)

        with open(source_path, 'wb') as f:
            f.write(source_bytes)

        # Receive any additional headers/includes
        msg_type, header_data = recv_message(sock)
        if msg_type == 'HDR':
            headers = json.loads(to_str(header_data))
            for hdr_name, hdr_content in headers.items():
                hdr_path = os.path.join(tmpdir, hdr_name)
                hdr_dir = os.path.dirname(hdr_path)
                if not os.path.exists(hdr_dir):
                    os.makedirs(hdr_dir)
                if base64:
                    with open(hdr_path, 'wb') as f:
                        f.write(base64.b64decode(hdr_content))

        # Determine output filename
        output_name = os.path.splitext(source_name)[0] + '.o'
        output_path = os.path.join(tmpdir, output_name)

        # Build compile command
        compiler_path = COMPILERS.get(compiler, compiler)
        if not compiler_path or not os.path.exists(str(compiler_path)):
            compiler_path = compiler

        cmd = [compiler_path]
        cmd.extend(['-I', tmpdir])
        for inc in include_paths:
            cmd.extend(['-I', inc])
        for define in defines:
            cmd.extend(['-D', define])
        cmd.extend(args)
        cmd.extend(['-c', source_path, '-o', output_path])

        print("[%s] Running: %s" % (job_id, ' '.join(cmd)))

        # Run compilation
        start_time = time.time()
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=tmpdir)
        stdout, stderr = proc.communicate()
        elapsed = time.time() - start_time

        if proc.returncode != 0:
            # Compilation failed
            error_msg = to_str(stderr) or to_str(stdout) or "Unknown error"
            print("[%s] FAILED: %s" % (job_id, error_msg[:100]))
            response = {
                'status': 'error',
                'job_id': job_id,
                'returncode': proc.returncode,
                'stderr': to_str(stderr),
                'stdout': to_str(stdout),
                'elapsed': elapsed,
            }
            send_message(sock, 'ERR', json.dumps(response))
        else:
            # Success - send back object file
            print("[%s] SUCCESS in %.2fs" % (job_id, elapsed))
            with open(output_path, 'rb') as f:
                obj_data = f.read()

            response = {
                'status': 'success',
                'job_id': job_id,
                'output_name': output_name,
                'output_size': len(obj_data),
                'elapsed': elapsed,
                'warnings': to_str(stderr) if stderr else None,
            }
            send_message(sock, 'OK', json.dumps(response))
            send_message(sock, 'OBJ', obj_data)

    finally:
        # Clean up temp directory
        try:
            shutil.rmtree(tmpdir)
        except Exception:
            pass


def handle_client(conn, addr):
    """Handle a single client connection"""
    print("Connection from %s" % (addr,))
    try:
        while True:
            msg_type, data = recv_message(conn)

            if msg_type == 'PING':
                info = get_system_info()
                send_message(conn, 'PONG', json.dumps(info))

            elif msg_type == 'JOB':
                handle_compile_job(conn, data)

            elif msg_type == 'QUIT':
                print("Client %s disconnecting" % (addr,))
                break

            else:
                print("Unknown message type: %s" % msg_type)
                send_message(conn, 'ERR', "Unknown message type: %s" % msg_type)

    except Exception as e:
        print("Error handling %s: %s" % (addr, e))
    finally:
        conn.close()


def parse_args_compat():
    """Parse arguments compatible with Python 2.5+ (no argparse)"""
    port = DEFAULT_PORT
    bind = '0.0.0.0'

    i = 1
    while i < len(sys.argv):
        arg = sys.argv[i]
        if arg == '--port' and i + 1 < len(sys.argv):
            port = int(sys.argv[i + 1])
            i += 2
        elif arg.startswith('--port='):
            port = int(arg.split('=')[1])
            i += 1
        elif arg == '--bind' and i + 1 < len(sys.argv):
            bind = sys.argv[i + 1]
            i += 2
        elif arg.startswith('--bind='):
            bind = arg.split('=')[1]
            i += 1
        elif arg in ('-h', '--help'):
            print("PPC Distributed Compile Worker")
            print("Usage: python %s [--port PORT] [--bind ADDR]" % sys.argv[0])
            print("  --port PORT  Port to listen on (default: %d)" % DEFAULT_PORT)
            print("  --bind ADDR  Address to bind to (default: 0.0.0.0)")
            sys.exit(0)
        else:
            i += 1

    class Args:
        pass
    args = Args()
    args.port = port
    args.bind = bind
    return args


def main():
    # Use argparse if available, otherwise use compat parser
    if HAS_ARGPARSE:
        parser = argparse.ArgumentParser(description='PPC Distributed Compile Worker')
        parser.add_argument('--port', type=int, default=DEFAULT_PORT,
                            help='Port to listen on (default: %d)' % DEFAULT_PORT)
        parser.add_argument('--bind', default='0.0.0.0',
                            help='Address to bind to (default: 0.0.0.0)')
        args = parser.parse_args()
    else:
        args = parse_args_compat()

    # Print system info
    info = get_system_info()
    print("PPC Compile Worker starting on %s:%d" % (args.bind, args.port))
    print("  Hostname: %s" % info['hostname'])
    print("  Arch: %s" % info['arch'])
    print("  CPUs: %d" % info['cpus'])
    print("  Available compilers:")
    for name, path in COMPILERS.items():
        if path and os.path.exists(str(path)):
            print("    %s: %s" % (name, path))

    # Create server socket
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((args.bind, args.port))
    server.listen(5)

    print("Listening for connections...")

    try:
        while True:
            conn, addr = server.accept()
            thread = threading.Thread(target=handle_client, args=(conn, addr))
            thread.daemon = True
            thread.start()
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        server.close()


if __name__ == '__main__':
    main()
