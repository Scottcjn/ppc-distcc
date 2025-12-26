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
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
        ▼                     ▼                     ▼
   ┌─────────┐          ┌─────────┐          ┌─────────┐
   │ G5 Mac  │          │ G4 Mac  │          │ G4 Mac  │
   │ 2x 970  │          │ 2x 7447 │          │ 1x 7455 │
   └─────────┘          └─────────┘          └─────────┘
```

## Features

- **Python 2.5+ Compatible** - Works on Tiger (10.4) and later
- **Automatic Load Balancing** - Sends jobs to fastest available machine
- **Local Fallback** - Falls back to local compile if workers unavailable
- **Drop-in Replacement** - Use `ppc-gcc` instead of `gcc`
- **Multi-compiler Support** - GCC, Clang, G++, Clang++

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
| Power Mac G5 | PPC 970 (2.0-2.7GHz) | 2.0 | Dual-core recommended |
| Power Mac G4 (MDD) | PPC 7447 (1.25-1.42GHz) | 1.5 | Dual-processor |
| PowerBook G4 | PPC 7447/7455 | 1.0 | Single core |
| iMac G4/G5 | Various | 1.0-1.5 | |
| Mac mini G4 | PPC 7447 (1.25-1.5GHz) | 1.0 | |

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
| `config.py` | Worker configuration |

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

## TODO

- [ ] Automatic header dependency tracking
- [ ] Precompiled header support
- [ ] SSH-based worker auto-start
- [ ] Web dashboard for monitoring
- [ ] Pump mode (preprocessing on coordinator)

## License

MIT License

## Credits

Inspired by distcc and icecc. Built for the PowerPC Mac preservation community.
