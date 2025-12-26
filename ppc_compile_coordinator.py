#!/usr/bin/env python3
"""
PPC Distributed Compile Coordinator
Distributes compile jobs across PowerPC Mac workers.

Usage:
  As library: from ppc_compile_coordinator import DistributedCompiler
  As daemon:  python ppc_compile_coordinator.py --daemon
"""

import socket
import subprocess
import tempfile
import os
import json
import struct
import argparse
import threading
import queue
import time
import hashlib
import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple

# Default worker nodes (PowerPC Macs on network)
DEFAULT_WORKERS = [
    # G5 machines (faster - 2 CPUs each)
    {'host': '192.168.0.130', 'port': 5555, 'name': 'g5-130', 'weight': 2.0},
    {'host': '192.168.0.179', 'port': 5555, 'name': 'g5-179', 'weight': 2.0},
    # Add more G5s here as discovered

    # G4 machines (slower - 1-2 CPUs)
    {'host': '192.168.0.125', 'port': 5555, 'name': 'dual-g4-125', 'weight': 1.5},
    {'host': '192.168.0.115', 'port': 5555, 'name': 'g4-powerbook-115', 'weight': 1.0},
    # Add more G4s here
]

# Credentials for SSH-based fallback
SSH_USER = 'sophia'
SSH_PASS = 'Elyanlabs12@'


@dataclass
class WorkerState:
    host: str
    port: int
    name: str
    weight: float
    available: bool = False
    cpus: int = 1
    load: float = 0.0
    arch: str = 'ppc'
    active_jobs: int = 0
    total_jobs: int = 0
    total_time: float = 0.0
    last_check: float = 0.0


@dataclass
class CompileJob:
    job_id: str
    source_path: str
    output_path: str
    compiler: str
    args: List[str]
    include_paths: List[str]
    defines: List[str]
    dependencies: List[str]  # Header files to send


def send_message(sock, msg_type, data):
    """Send a message with length prefix"""
    if isinstance(data, str):
        data = data.encode('utf-8')
    header = struct.pack('!I', len(data)) + msg_type.encode('utf-8')[:4].ljust(4)
    sock.sendall(header + data)


def recv_exactly(sock, n):
    """Receive exactly n bytes"""
    data = b''
    while len(data) < n:
        chunk = sock.recv(min(n - len(data), 65536))
        if not chunk:
            raise ConnectionError("Connection closed")
        data += chunk
    return data


def recv_message(sock):
    """Receive a message with length prefix"""
    header = recv_exactly(sock, 8)
    length = struct.unpack('!I', header[:4])[0]
    msg_type = header[4:8].decode('utf-8').strip()
    data = recv_exactly(sock, length)
    return msg_type, data


class DistributedCompiler:
    def __init__(self, workers=None, local_fallback=True):
        self.workers = []
        self.local_fallback = local_fallback
        self.job_counter = 0
        self.lock = threading.Lock()

        # Initialize workers
        worker_configs = workers or DEFAULT_WORKERS
        for w in worker_configs:
            self.workers.append(WorkerState(
                host=w['host'],
                port=w.get('port', 5555),
                name=w.get('name', w['host']),
                weight=w.get('weight', 1.0),
            ))

        # Check which workers are available
        self.refresh_workers()

    def refresh_workers(self):
        """Check availability of all workers"""
        print("Checking worker availability...")

        def check_worker(worker):
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(2.0)
                sock.connect((worker.host, worker.port))
                send_message(sock, 'PING', '')
                msg_type, data = recv_message(sock)
                sock.close()

                if msg_type == 'PONG':
                    info = json.loads(data.decode('utf-8'))
                    worker.available = True
                    worker.cpus = info.get('cpus', 1)
                    worker.load = info.get('load', 0.0)
                    worker.arch = info.get('arch', 'ppc')
                    worker.last_check = time.time()
                    print(f"  {worker.name} ({worker.host}): OK - {worker.arch}, {worker.cpus} CPUs, load {worker.load:.2f}")
                    return True
            except Exception as e:
                worker.available = False
                print(f"  {worker.name} ({worker.host}): OFFLINE - {e}")
            return False

        with ThreadPoolExecutor(max_workers=10) as executor:
            list(executor.map(check_worker, self.workers))

        available = sum(1 for w in self.workers if w.available)
        print(f"Available workers: {available}/{len(self.workers)}")

    def get_best_worker(self) -> Optional[WorkerState]:
        """Get the best available worker based on load and capacity"""
        with self.lock:
            available = [w for w in self.workers if w.available]
            if not available:
                return None

            # Score = weight * cpus / (1 + load + active_jobs)
            def score(w):
                return w.weight * w.cpus / (1 + w.load + w.active_jobs)

            return max(available, key=score)

    def compile_file(self, source_path: str, output_path: str,
                     compiler: str = 'gcc', args: List[str] = None,
                     include_paths: List[str] = None,
                     defines: List[str] = None) -> Tuple[bool, str]:
        """Compile a single file on a remote worker"""

        args = args or []
        include_paths = include_paths or []
        defines = defines or []

        with self.lock:
            self.job_counter += 1
            job_id = f"job-{self.job_counter:06d}"

        worker = self.get_best_worker()
        if not worker:
            if self.local_fallback:
                print(f"[{job_id}] No workers available, compiling locally")
                return self._compile_local(source_path, output_path, compiler, args,
                                          include_paths, defines)
            else:
                return False, "No workers available"

        with self.lock:
            worker.active_jobs += 1

        try:
            return self._compile_remote(worker, job_id, source_path, output_path,
                                        compiler, args, include_paths, defines)
        finally:
            with self.lock:
                worker.active_jobs -= 1

    def _compile_remote(self, worker: WorkerState, job_id: str,
                        source_path: str, output_path: str,
                        compiler: str, args: List[str],
                        include_paths: List[str], defines: List[str]) -> Tuple[bool, str]:
        """Compile file on remote worker"""

        print(f"[{job_id}] Sending {os.path.basename(source_path)} to {worker.name}")
        start_time = time.time()

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(300.0)  # 5 minute timeout for compilation
            sock.connect((worker.host, worker.port))

            # Read source file
            with open(source_path, 'rb') as f:
                source_data = f.read()

            # Prepare job request
            job = {
                'job_id': job_id,
                'compiler': compiler,
                'args': args,
                'source_name': os.path.basename(source_path),
                'include_paths': include_paths,
                'defines': defines,
            }

            # Send job
            send_message(sock, 'JOB', json.dumps(job))

            # Send source file
            send_message(sock, 'SRC', source_data)

            # Send empty headers (TODO: implement header dependency tracking)
            send_message(sock, 'HDR', '{}')

            # Wait for response
            msg_type, data = recv_message(sock)

            if msg_type == 'ERR':
                response = json.loads(data.decode('utf-8'))
                error_msg = response.get('stderr', 'Unknown error')
                print(f"[{job_id}] FAILED on {worker.name}: {error_msg[:100]}")
                return False, error_msg

            elif msg_type == 'OK':
                response = json.loads(data.decode('utf-8'))

                # Receive object file
                msg_type2, obj_data = recv_message(sock)
                if msg_type2 != 'OBJ':
                    return False, f"Expected OBJ, got {msg_type2}"

                # Write output file
                os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
                with open(output_path, 'wb') as f:
                    f.write(obj_data)

                elapsed = time.time() - start_time
                remote_time = response.get('elapsed', 0)
                print(f"[{job_id}] SUCCESS on {worker.name} - "
                      f"compile: {remote_time:.2f}s, total: {elapsed:.2f}s")

                with self.lock:
                    worker.total_jobs += 1
                    worker.total_time += remote_time

                return True, output_path

            else:
                return False, f"Unexpected response: {msg_type}"

        except Exception as e:
            print(f"[{job_id}] ERROR with {worker.name}: {e}")
            worker.available = False
            if self.local_fallback:
                print(f"[{job_id}] Falling back to local compile")
                return self._compile_local(source_path, output_path, compiler,
                                          args, include_paths, defines)
            return False, str(e)

        finally:
            try:
                sock.close()
            except:
                pass

    def _compile_local(self, source_path: str, output_path: str,
                       compiler: str, args: List[str],
                       include_paths: List[str], defines: List[str]) -> Tuple[bool, str]:
        """Compile locally as fallback"""

        cmd = [compiler]
        for inc in include_paths:
            cmd.extend(['-I', inc])
        for define in defines:
            cmd.extend(['-D', define])
        cmd.extend(args)
        cmd.extend(['-c', source_path, '-o', output_path])

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            return False, result.stderr or result.stdout
        return True, output_path

    def compile_many(self, jobs: List[CompileJob], max_parallel: int = None) -> Dict[str, Tuple[bool, str]]:
        """Compile multiple files in parallel across workers"""

        if max_parallel is None:
            max_parallel = sum(w.cpus for w in self.workers if w.available)
            max_parallel = max(max_parallel, 4)  # At least 4 parallel

        results = {}

        with ThreadPoolExecutor(max_workers=max_parallel) as executor:
            futures = {}
            for job in jobs:
                future = executor.submit(
                    self.compile_file,
                    job.source_path,
                    job.output_path,
                    job.compiler,
                    job.args,
                    job.include_paths,
                    job.defines
                )
                futures[future] = job.source_path

            for future in as_completed(futures):
                source = futures[future]
                try:
                    success, result = future.result()
                    results[source] = (success, result)
                except Exception as e:
                    results[source] = (False, str(e))

        return results

    def print_stats(self):
        """Print worker statistics"""
        print("\n=== Worker Statistics ===")
        for w in self.workers:
            if w.total_jobs > 0:
                avg_time = w.total_time / w.total_jobs
                print(f"{w.name}: {w.total_jobs} jobs, avg {avg_time:.2f}s")


def discover_workers_ssh():
    """Try to discover workers via SSH if they're not running the daemon"""
    print("Attempting SSH-based worker discovery...")
    # This could start the worker daemon on each machine via SSH
    # For now, just check if machines are reachable
    pass


def main():
    parser = argparse.ArgumentParser(description='PPC Distributed Compile Coordinator')
    parser.add_argument('--refresh', action='store_true',
                        help='Refresh worker list and exit')
    parser.add_argument('--test', metavar='FILE',
                        help='Test compile a single file')
    parser.add_argument('--compiler', default='gcc',
                        help='Compiler to use (default: gcc)')
    args = parser.parse_args()

    compiler = DistributedCompiler()

    if args.refresh:
        compiler.refresh_workers()
        return

    if args.test:
        if not os.path.exists(args.test):
            print(f"File not found: {args.test}")
            return 1

        output = os.path.splitext(args.test)[0] + '.o'
        success, result = compiler.compile_file(
            args.test, output, args.compiler, ['-O2']
        )

        if success:
            print(f"Success! Output: {result}")
            print(f"Size: {os.path.getsize(output)} bytes")
        else:
            print(f"Failed: {result}")
            return 1

        compiler.print_stats()
        return 0

    # Interactive mode
    print("\nDistributed Compiler ready.")
    print("Usage: dc.compile_file('source.c', 'source.o', 'gcc', ['-O2'])")


if __name__ == '__main__':
    exit(main() or 0)
