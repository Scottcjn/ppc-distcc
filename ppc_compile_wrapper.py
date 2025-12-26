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

from __future__ import print_function

import socket
import subprocess
import tempfile
import os
import sys
import struct
import time

# Python 2/3 compatibility
try:
    import json
except ImportError:
    import simplejson as json

# Configuration
DEFAULT_PORT = 5555
CONNECT_TIMEOUT = 2.0
COMPILE_TIMEOUT = 300.0

# Default worker hosts
DEFAULT_HOSTS = [
    '192.168.0.130',  # G5
    '192.168.0.179',  # G5 selenamac
    '192.168.0.125',  # Dual G4
    '192.168.0.115',  # G4 PowerBook
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


def get_hosts():
    """Get list of worker hosts from environment or default"""
    env_hosts = os.environ.get('PPC_DISTCC_HOSTS', '')
    if env_hosts:
        return [h.strip() for h in env_hosts.split(',') if h.strip()]
    return DEFAULT_HOSTS


def is_compile_job(args):
    """Check if this is a compile job (not link-only)"""
    has_c_flag = '-c' in args
    has_source = any(a.endswith(('.c', '.cpp', '.cc', '.cxx', '.m', '.mm'))
                     for a in args if not a.startswith('-'))
    return has_c_flag and has_source


def get_source_and_output(args):
    """Extract source file and output file from args"""
    source = None
    output = None

    i = 0
    while i < len(args):
        arg = args[i]
        if arg == '-o' and i + 1 < len(args):
            output = args[i + 1]
            i += 2
        elif arg.endswith(('.c', '.cpp', '.cc', '.cxx', '.m', '.mm')) and not arg.startswith('-'):
            source = arg
            i += 1
        else:
            i += 1

    return source, output


def send_message(sock, msg_type, data):
    """Send a message with length prefix"""
    if isinstance(data, str):
        data = data.encode('utf-8')
    header = struct.pack('!I', len(data)) + msg_type.encode('utf-8')[:4].ljust(4, ' ').encode('utf-8')[:4]
    sock.sendall(header + data)


def recv_exactly(sock, n):
    """Receive exactly n bytes"""
    data = b''
    while len(data) < n:
        chunk = sock.recv(min(n - len(data), 65536))
        if not chunk:
            raise Exception("Connection closed")
        data += chunk
    return data


def recv_message(sock):
    """Receive a message with length prefix"""
    header = recv_exactly(sock, 8)
    length = struct.unpack('!I', header[:4])[0]
    msg_type = header[4:8].decode('utf-8').strip()
    data = recv_exactly(sock, length)
    return msg_type, data


def try_remote_compile(host, port, compiler, source_path, output_path, args):
    """Try to compile on a remote worker"""
    verbose = os.environ.get('PPC_DISTCC_VERBOSE')

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(CONNECT_TIMEOUT)
        sock.connect((host, port))
        sock.settimeout(COMPILE_TIMEOUT)

        # Read source file
        with open(source_path, 'rb') as f:
            source_data = f.read()

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
                    i += 2
                else:
                    include_paths.append(arg[2:])
                    i += 1
            elif arg.startswith('-D'):
                if arg == '-D' and i + 1 < len(args):
                    defines.append(args[i + 1])
                    i += 2
                else:
                    defines.append(arg[2:])
                    i += 1
            elif arg in ('-c', '-o') or arg == source_path or arg == output_path:
                i += 1
                if arg == '-o':
                    i += 1  # Skip output filename too
            else:
                other_args.append(arg)
                i += 1

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
            print("[ppc-distcc] Sending to %s: %s" % (host, os.path.basename(source_path)),
                  file=sys.stderr)

        # Send job
        send_message(sock, 'JOB', json.dumps(job))
        send_message(sock, 'SRC', source_data)
        send_message(sock, 'HDR', '{}')

        # Wait for response
        msg_type, data = recv_message(sock)

        if msg_type == 'ERR':
            response = json.loads(data.decode('utf-8'))
            stderr = response.get('stderr', '')
            if stderr:
                sys.stderr.write(stderr)
            return response.get('returncode', 1)

        elif msg_type == 'OK':
            response = json.loads(data.decode('utf-8'))

            # Receive object file
            msg_type2, obj_data = recv_message(sock)
            if msg_type2 != 'OBJ':
                return 1

            # Write output
            with open(output_path, 'wb') as f:
                f.write(obj_data)

            # Print warnings if any
            warnings = response.get('warnings', '')
            if warnings:
                sys.stderr.write(warnings)

            if verbose:
                elapsed = response.get('elapsed', 0)
                print("[ppc-distcc] Compiled on %s in %.2fs" % (host, elapsed),
                      file=sys.stderr)

            return 0

        else:
            return 1

    except Exception as e:
        if verbose:
            print("[ppc-distcc] Failed on %s: %s" % (host, e), file=sys.stderr)
        return None

    finally:
        try:
            sock.close()
        except:
            pass


def compile_local(compiler, args):
    """Fall back to local compilation"""
    verbose = os.environ.get('PPC_DISTCC_VERBOSE')
    if verbose:
        print("[ppc-distcc] Compiling locally", file=sys.stderr)

    cmd = [compiler] + args
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
        output = os.path.splitext(source)[0] + '.o'

    # Try each host in order
    hosts = get_hosts()
    for host in hosts:
        result = try_remote_compile(host, DEFAULT_PORT, compiler,
                                    source, output, args)
        if result is not None:
            return result

    # All hosts failed, fall back to local
    if os.environ.get('PPC_DISTCC_FALLBACK', '1') != '0':
        return compile_local(compiler, args)
    else:
        print("[ppc-distcc] All workers failed and fallback disabled",
              file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
