[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0) [![PowerPC](https://img.shields.io/badge/PowerPC-G4%2FG5-orange)](https://github.com/Scottcjn/ppc-distcc) [![distcc](https://img.shields.io/badge/distcc-Distributed-green)](https://github.com/Scottcjn/ppc-distcc)
[![BCOS Certified](https://img.shields.io/badge/BCOS-Certified-brightgreen?style=flat&logo=data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAyNCAyNCIgZmlsbD0id2hpdGUiPjxwYXRoIGQ9Ik0xMiAxTDMgNXY2YzAgNS41NSAzLjg0IDEwLjc0IDkgMTIgNS4xNi0xLjI2IDktNi40NSA5LTEyVjVsLTktNHptLTIgMTZsLTQtNCA1LjQxLTUuNDEgMS40MSAxLjQxTDEwIDE0bDYtNiAxLjQxIDEuNDFMMTAgMTd6Ii8+PC9zdmc+)](BCOS.md)

# PPC-DistCC

Distributed compilation system for PowerPC Macs running Mac OS X Tiger (10.4), Leopard (10.5), and Sorbet Leopard.

## Overview

PPC-DistCC distributes C/C++ compilation jobs across multiple PowerPC Macs on your network, dramatically speeding up large builds like LLVM, GCC, or the Linux kernel.

```
┌─────────────────────────────────────────────────────────────┐
│                    COORDINATOR MAC                           │
│  make -j8 CC=ppc-gcc CXX=ppc-g++                            │
└─────────────────────────────────────────────────────────────┘
                              │
   ┌──────────────────────────┼──────────────────────────┐
   │                          │                          │
   ▼                          ▼                          ▼
┌─────────┐            ┌─────────────┐            ┌─────────┐
│ G5 Mac  │            │ POWER8 S824 │            │ G5 Mac  │
│ 2x 970  │            │ 128 threads │            │ 2x 970  │
└─────────┘            │ (cross-comp)│            └─────────┘
                       └─────────────┘
```

## Features

- **Python 2.5+ Compatible** - Works on Tiger (10.4) and later
- **Automatic Load Balancing** - Sends jobs to fastest available machine
- **Local Fallback** - Falls back to local compile if workers unavailable
- **Drop-in Replacement** - Use `ppc-gcc` instead of `gcc`
- **Multi-compiler Support** - GCC, Clang, G++, Clang++

## Prerequisites

**All worker machines must have matching development environments:**

| Requirement | Description |
|------------|-------------|
| **Compiler** | Same compiler version (e.g., gcc-10) on all machines |
| **Headers** | System headers and SDK at compatible versions |
| **Libraries** | Required libraries (libiconv, libstdc++, etc.) |
| **Source Tree** | For complex builds, source at same relative path |

### Known Compatibility Issues

| Machine | Issue | Solution |
|---------|-------|----------|
| G4 (Tiger/Leopard) | libiconv 5.0 (gcc-10 needs 7.0) | Install libiconv 7.0 or use gcc-7 |
| G5 (Leopard) | Works with gcc-10 | ✓ Ready |

### Setting Up G4 Machines for gcc-10

```bash
# Option 1: Install newer libiconv
curl -O https://ftp.gnu.org/pub/gnu/libiconv/libiconv-1.17.tar.gz
tar xzf libiconv-1.17.tar.gz && cd libiconv-1.17
./configure --prefix=/usr/local && make && sudo make install

# Option 2: Use gcc-7 instead (already compatible with Tiger/Leopard)
# Configure build with: CC=ppc-gcc-7 CXX=ppc-g++-7
```

## Quick Start

### 1. Start Workers (on each Mac)

```bash
# Copy worker script to each machine
scp ppc_compile_worker.py user@192.168.0.130:~/

# SSH to each machine and start worker
ssh user@192.168.0.130
python ~/ppc_compile_worker.py &
```

### 2. Install Wrapper (on build machine)

```bash
# Copy wrapper
sudo cp ppc_compile_wrapper.py /usr/local/bin/

# Create symlinks
sudo ln -s /usr/local/bin/ppc_compile_wrapper.py /usr/local/bin/ppc-gcc
sudo ln -s /usr/local/bin/ppc_compile_wrapper.py /usr/local/bin/ppc-g++
sudo ln -s /usr/local/bin/ppc_compile_wrapper.py /usr/local/bin/ppc-clang
sudo ln -s /usr/local/bin/ppc_compile_wrapper.py /usr/local/bin/ppc-clang++
```

### 3. Build!

```bash
# Simple usage
ppc-gcc -O2 -c hello.c -o hello.o

# With make
make CC=ppc-gcc CXX=ppc-g++ -j8

# With cmake
cmake .. -DCMAKE_C_COMPILER=ppc-gcc -DCMAKE_CXX_COMPILER=ppc-g++
make -j8
```

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `PPC_DISTCC_HOSTS` | Comma-separated worker IPs | See config.py |
| `PPC_DISTCC_FALLBACK` | Fall back to local on failure | `1` |
| `PPC_DISTCC_VERBOSE` | Show verbose output | unset |
| `PPC_DISTCC_DISABLED` | Disable distribution | unset |
| `PPC_DISTCC_COMPILER` | Override compiler | from script name |

### Example

```bash
export PPC_DISTCC_HOSTS="192.168.0.130,192.168.0.179,192.168.0.125"
export PPC_DISTCC_VERBOSE=1
make CC=ppc-gcc -j12
```

## Supported Machines

| Machine | CPU | Weight | Notes |
|---------|-----|--------|-------|
| **IBM POWER8 S824** | POWER8 (128 threads) | 10.0 | Cross-compiler, Linux ppc64le |
| Power Mac G5 | PPC 970 (2.0-2.7GHz) | 2.0 | Dual-core recommended |
| Power Mac G4 (MDD) | PPC 7447 (1.25-1.42GHz) | 1.5 | Dual-processor |
| PowerBook G4 | PPC 7447/7455 | 1.0 | Single core |
| iMac G4/G5 | Various | 1.0-1.5 | |
| Mac mini G4 | PPC 7447 (1.25-1.5GHz) | 1.0 | |

## POWER8 Cross-Compilation (Linux → Darwin/PPC)

The IBM POWER8 can cross-compile Darwin/PPC code from Linux, providing massive parallelism (128 hardware threads) to accelerate builds.

```
┌────────────────────────────────────────────────────────┐
│              POWER8 S824 (Linux ppc64le)               │
│  ┌─────────────────────────────────────────────────┐   │
│  │  cctools (powerpc-apple-darwin9-as, ld, etc.)   │   │
│  │  GCC 10.5.0 cross-compiler                       │   │
│  │  Target: powerpc-apple-darwin9 (Mac OS X)       │   │
│  └─────────────────────────────────────────────────┘   │
│         128 hardware threads (SMT8)                    │
│         576 GB RAM                                     │
└────────────────────────────────────────────────────────┘
```

### How It Works

The POWER8 runs Linux (ppc64le) but uses a cross-compiler to produce Mach-O object files for Mac OS X (powerpc-apple-darwin9). The worker script receives source files, compiles them with the cross-compiler, and returns Darwin-compatible `.o` files.

### Quick Setup

```bash
# On the POWER8 (Ubuntu 20.04 ppc64le):
./setup_power8_crosscompiler.sh

# This installs:
# - cctools (Apple binutils: as, ld, etc.)
# - GCC 10.5.0 (powerpc-apple-darwin9-gcc)
# - Worker daemon (ppc_compile_worker_power8.py)
# - systemd service (ppc-distcc-worker)

# Start the worker:
sudo systemctl start ppc-distcc-worker

# Add POWER8 to your coordinator's wrapper hosts:
export PPC_DISTCC_HOSTS="192.168.0.50,192.168.0.130,192.168.0.179"
```

### Manual Installation

If the script fails or you need custom configuration:

```bash
# 1. Install dependencies
sudo apt-get install build-essential libgmp-dev libmpfr-dev libmpc-dev \
    texinfo bison flex libtool automake wget clang llvm-dev

# 2. Build cctools
wget https://github.com/tpoechtrager/cctools-port/archive/refs/heads/master.zip
unzip master.zip && cd cctools-port-master/cctools
./autogen.sh
./configure --target=powerpc-apple-darwin9 --prefix=$HOME/darwin-cross-ppc/toolchain
make -j$(nproc) && make install

# 3. Create 'as' symlink (GCC needs it)
ln -sf powerpc-apple-darwin9-as $HOME/darwin-cross-ppc/toolchain/bin/as

# 4. Build GCC cross-compiler
wget https://ftp.gnu.org/gnu/gcc/gcc-10.5.0/gcc-10.5.0.tar.xz
tar xf gcc-10.5.0.tar.xz && cd gcc-10.5.0
contrib/download_prerequisites
mkdir ../gcc-build && cd ../gcc-build
../gcc-10.5.0/configure \
    --target=powerpc-apple-darwin9 \
    --prefix=$HOME/darwin-cross-ppc/toolchain \
    --enable-languages=c,c++ \
    --disable-bootstrap --disable-multilib --disable-nls
make -j$(nproc) all-gcc && make install-gcc
```

### Testing the Cross-Compiler

```bash
export PATH=$HOME/darwin-cross-ppc/toolchain/bin:$PATH

# Compile a test file
echo 'int main() { return 42; }' > test.c
powerpc-apple-darwin9-gcc -c test.c -o test.o

# Verify it's a Mach-O object
file test.o
# Output: test.o: Mach-O ppc_7400 object
```

### Known Issues (POWER8)

| Issue | Solution |
|-------|----------|
| Type conflicts (int64_t redefinition) | Script patches cctools headers automatically |
| fixincludes error during GCC build | Script creates dummy fixinc.sh |
| Wrong assembler used | Script creates `as` symlink in toolchain/bin |
| Ubuntu 22.04+ not supported | Use Ubuntu 20.04 (last POWER8-supported) |

### Performance with POWER8

With POWER8 (128 threads) + 2x G5 (4 threads each):

| Build | Without POWER8 | With POWER8 | Speedup |
|-------|---------------|-------------|---------|
| LLVM 3.9 | ~3 hours | ~45 min | 4x |
| GCC 10 | ~4 hours | ~1 hour | 4x |

The POWER8 handles the bulk of compilation jobs while G5s process overflow.

## Compilers Supported

- GCC 4.0.1 (system default on Leopard)
- GCC 7.5.0 (via Tigerbrew)
- GCC 10.5.0 (custom build)
- Clang 3.4.2 (custom build)
- Clang 3.9.1 (custom build)

## Files

| File | Description |
|------|-------------|
| `ppc_compile_worker.py` | Worker daemon (runs on each Mac) |
| `ppc_compile_coordinator.py` | Coordinator library/daemon |
| `ppc_compile_wrapper.py` | Drop-in gcc/clang replacement |
| `sync_generated_files.sh` | Sync generated .inc/.def files to workers |
| `config.py` | Worker configuration |
| `setup_power8_crosscompiler.sh` | **NEW:** One-script POWER8 cross-compiler setup |

## Systemd/Launchd Service

### launchd (Mac OS X)

Create `~/Library/LaunchAgents/com.ppc-distcc.worker.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.ppc-distcc.worker</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python</string>
        <string>/Users/sophia/ppc_compile_worker.py</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
</dict>
</plist>
```

Load with:
```bash
launchctl load ~/Library/LaunchAgents/com.ppc-distcc.worker.plist
```

## Performance

Typical speedup with 7 PPC Macs (3x G4, 4x G5):

| Build | Single Mac | Distributed | Speedup |
|-------|-----------|-------------|---------|
| LLVM 3.4 | ~8 hours | ~1.5 hours | 5.3x |
| GCC 10 | ~12 hours | ~2 hours | 6x |
| Linux kernel | ~4 hours | ~45 min | 5.3x |

## Troubleshooting

### Worker not responding
```bash
# Check if worker is running
ps aux | grep ppc_compile_worker

# Test connection
python -c "import socket; s=socket.socket(); s.connect(('192.168.0.130', 5555)); print('OK')"
```

### Compilation fails on remote
```bash
# Enable verbose mode
export PPC_DISTCC_VERBOSE=1
ppc-gcc -c test.c -o test.o
```

### Headers not found
The system currently doesn't transfer headers. Use `-I` with absolute paths to system headers.

## Building Complex Projects (LLVM, etc.)

For projects that generate intermediate files (`.inc`, `.def`, `.gen`) during compilation, you need to:

### 1. Deploy Source to All Workers

Each worker needs the source tree at the same relative path:

```bash
# Package source on coordinator
cd ~ && tar czf project-src.tar.gz project-src project-build/include

# Copy to each worker
scp project-src.tar.gz user@192.168.0.179:~
ssh user@192.168.0.179 'cd ~ && tar xzf project-src.tar.gz'
```

### 2. Sync Generated Files Periodically

Generated files are created during build and must be synced to workers:

```bash
# Set up workers
export PPC_DISTCC_WORKERS="selenamac@192.168.0.179"
export PPC_DISTCC_PASSWORD="your_password"

# Start sync script (syncs every 2 minutes)
./sync_generated_files.sh ~/llvm-3.9-build 120 &

# Start build
make -j4
```

### Path Translation

The worker automatically translates paths between machines. Paths like `/Users/sophia/...` on the coordinator are translated to `/Users/selenamac/...` on the worker (based on `$HOME`).

Configure additional translations in `ppc_compile_worker.py`:

```python
PATH_TRANSLATIONS = [
    ('/Users/sophia/', LOCAL_HOME + '/'),
    ('/Users/selenamac/', LOCAL_HOME + '/'),
]
```

## TODO

- [x] Cross-machine path translation
- [x] Generated file sync script
- [x] **POWER8 cross-compiler support** (128 threads!)
- [ ] Automatic header dependency tracking
- [ ] Precompiled header support
- [ ] SSH-based worker auto-start
- [ ] Web dashboard for monitoring
- [ ] Pump mode (preprocessing on coordinator)

## Related Projects & Documentation

### PPC Compiler Builds
| Project | Description | Link |
|---------|-------------|------|
| **LLVM 3.4.2 PPC** | Pre-built LLVM/Clang for Leopard | [GitHub](https://github.com/Scottcjn/llvm-3.4.2-ppc-leopard) |
| **GCC 10 PPC** | Building GCC 10 for PowerPC | Coming soon |
| **Tigerbrew** | Package manager for Tiger/Leopard | [GitHub](https://github.com/mistydemeo/tigerbrew) |

### Setup Guides
- **Leopard Development Setup** - Install Xcode, Tigerbrew, and modern compilers
- **Tiger Compatibility** - Working with Python 2.3/2.5 limitations
- **Cross-Compilation** - Building PPC binaries on modern Macs

### Building the Compilers

Before using ppc-distcc, each worker needs compilers installed:

```bash
# Install Tigerbrew (on each Mac)
ruby -e "$(curl -fsSkL raw.github.com/mistydemeo/tigerbrew/go/install)"

# Install GCC 7 (works on Tiger/Leopard)
brew install gcc@7

# For GCC 10, build from source (Leopard G5 only, or G4 with libiconv update)
# See: https://github.com/Scottcjn/gcc-10-ppc-build (coming soon)
```

### AltiVec Optimization

PowerPC G4/G5 chips have AltiVec (Velocity Engine) SIMD instructions. When building compilers, enable AltiVec for faster compilation:

```bash
# GCC configure with AltiVec
./configure --with-cpu=G4 --enable-altivec

# Or for G5 (also has AltiVec)
./configure --with-cpu=970 --enable-altivec

# CFLAGS for AltiVec-optimized builds
export CFLAGS="-O3 -maltivec -mabi=altivec -mcpu=7450"  # G4
export CFLAGS="-O3 -maltivec -mabi=altivec -mcpu=970"   # G5
```

**Potential speedups:** String operations, hashing, and certain compiler internals can benefit from AltiVec vectorization.

### Network Requirements
- All machines on same subnet (or with routing configured)
- Port 5555 open for worker communication
- SSH access for deployment and sync scripts

## License

MIT License

## Credits

Inspired by distcc and icecc. Built for the PowerPC Mac preservation community.
