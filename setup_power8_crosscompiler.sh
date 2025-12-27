#!/bin/bash
# setup_power8_crosscompiler.sh
#
# Sets up a POWER8 Linux system as a cross-compiler for PowerPC Mac OS X
# This enables distributed compilation from G4/G5 Macs to POWER8 Linux
#
# The POWER8 has 128 hardware threads - massively accelerating builds!
#
# Usage: ./setup_power8_crosscompiler.sh
#
# Requirements:
# - POWER8 running Ubuntu 20.04 (ppc64le)
# - ~10GB disk space
# - Internet connection for downloads

set -e

TOOLCHAIN_DIR="$HOME/darwin-cross-ppc/toolchain"
BUILD_DIR="$HOME/darwin-cross-ppc"
CCTOOLS_VERSION="master"
GCC_VERSION="10.5.0"

echo "=========================================="
echo "POWER8 Darwin Cross-Compiler Setup"
echo "=========================================="
echo ""
echo "This will install:"
echo "  - cctools (Apple binutils for Darwin/PPC)"
echo "  - GCC ${GCC_VERSION} cross-compiler"
echo "  - Worker daemon for distributed compilation"
echo ""
echo "Target: powerpc-apple-darwin9 (Mac OS X Leopard)"
echo "Install location: ${TOOLCHAIN_DIR}"
echo ""

# Check we're on POWER8
if ! grep -q "POWER8" /proc/cpuinfo 2>/dev/null; then
    echo "Warning: This doesn't appear to be a POWER8 system"
    echo "Continuing anyway..."
fi

# Install dependencies
echo "[1/6] Installing build dependencies..."
sudo apt-get update -qq
sudo apt-get install -y -qq \
    build-essential \
    libgmp-dev \
    libmpfr-dev \
    libmpc-dev \
    texinfo \
    bison \
    flex \
    libtool \
    automake \
    wget \
    unzip \
    clang \
    llvm-dev \
    libblocksruntime-dev

# Create directories
echo "[2/6] Creating build directories..."
mkdir -p "${BUILD_DIR}"
mkdir -p "${TOOLCHAIN_DIR}/bin"
cd "${BUILD_DIR}"

# Download and build cctools
echo "[3/6] Building cctools (Apple binutils)..."
if [ ! -f cctools.zip ]; then
    wget -q https://github.com/tpoechtrager/cctools-port/archive/refs/heads/master.zip -O cctools.zip
fi
rm -rf cctools-port-master
unzip -q cctools.zip
cd cctools-port-master/cctools

# Fix type conflicts for ppc64le Linux
cat > /tmp/glibc_fix.patch << 'PATCH'
--- a/include/foreign/ppc/types.h
+++ b/include/foreign/ppc/types.h
@@ -67,6 +67,15 @@
 #ifndef _MACHTYPES_H_
 #define _MACHTYPES_H_

+#ifdef __GLIBC__
+#include <stdint.h>
+#include <sys/types.h>
+#define _INT8_T
+#define _INT16_T
+#define _INT32_T
+#define _INT64_T
+#endif
+
 #ifndef __ASSEMBLER__
 #include <ppc/_types.h>
PATCH

# Apply the patch (may fail if already applied)
patch -p2 < /tmp/glibc_fix.patch 2>/dev/null || true

# Also add guards for u_int types
sed -i 's/^typedef.*unsigned long long.*u_int64_t;/#ifndef _U_INT64_T\n#define _U_INT64_T\ntypedef unsigned long long u_int64_t;\n#endif/' include/foreign/ppc/types.h
sed -i 's/^typedef.*unsigned int.*u_int32_t;/#ifndef _U_INT32_T\n#define _U_INT32_T\ntypedef unsigned int u_int32_t;\n#endif/' include/foreign/ppc/types.h
sed -i 's/^typedef.*unsigned short.*u_int16_t;/#ifndef _U_INT16_T\n#define _U_INT16_T\ntypedef unsigned short u_int16_t;\n#endif/' include/foreign/ppc/types.h
sed -i 's/^typedef.*unsigned char.*u_int8_t;/#ifndef _U_INT8_T\n#define _U_INT8_T\ntypedef unsigned char u_int8_t;\n#endif/' include/foreign/ppc/types.h

./autogen.sh
./configure --target=powerpc-apple-darwin9 --prefix="${TOOLCHAIN_DIR}"
make -j$(nproc)
make install

# Create 'as' symlink (GCC looks for 'as' not 'powerpc-apple-darwin9-as')
cd "${TOOLCHAIN_DIR}/bin"
ln -sf powerpc-apple-darwin9-as as

# Download and build GCC
echo "[4/6] Building GCC ${GCC_VERSION} cross-compiler..."
cd "${BUILD_DIR}"
if [ ! -f "gcc-${GCC_VERSION}.tar.xz" ]; then
    wget -q "https://ftp.gnu.org/gnu/gcc/gcc-${GCC_VERSION}/gcc-${GCC_VERSION}.tar.xz"
fi
rm -rf "gcc-${GCC_VERSION}"
tar xf "gcc-${GCC_VERSION}.tar.xz"
cd "gcc-${GCC_VERSION}"
contrib/download_prerequisites

mkdir -p ../gcc-build
cd ../gcc-build

# Create dummy fixinc.sh to avoid fixincludes issues
mkdir -p build-$(uname -m)-unknown-linux-gnu/fixincludes
echo '#!/bin/bash' > build-$(uname -m)-unknown-linux-gnu/fixincludes/fixinc.sh
chmod +x build-$(uname -m)-unknown-linux-gnu/fixincludes/fixinc.sh

export PATH="${TOOLCHAIN_DIR}/bin:$PATH"

../gcc-${GCC_VERSION}/configure \
    --target=powerpc-apple-darwin9 \
    --prefix="${TOOLCHAIN_DIR}" \
    --enable-languages=c,c++ \
    --disable-bootstrap \
    --disable-libsanitizer \
    --disable-multilib \
    --disable-nls \
    --disable-fixincludes \
    --with-headers=no \
    --without-headers

make -j$(nproc) all-gcc
make install-gcc

# Install worker script
echo "[5/6] Installing worker daemon..."
cat > "${HOME}/ppc_compile_worker_power8.py" << 'WORKER'
#!/usr/bin/env python3
"""
PPC Distributed Compile Worker - POWER8 Cross-Compilation Edition
Runs on POWER8 Linux to cross-compile for PowerPC Mac OS X.
"""

import socket
import subprocess
import os
import sys
import json
import struct
import threading
import time
import shutil
import tempfile
import base64

DEFAULT_PORT = 5555
TOOLCHAIN = os.path.expanduser("~/darwin-cross-ppc/toolchain/bin")

COMPILERS = {
    "gcc": f"{TOOLCHAIN}/powerpc-apple-darwin9-gcc",
    "g++": f"{TOOLCHAIN}/powerpc-apple-darwin9-g++",
    "gcc-10": f"{TOOLCHAIN}/powerpc-apple-darwin9-gcc",
    "g++-10": f"{TOOLCHAIN}/powerpc-apple-darwin9-g++",
}

LOCAL_HOME = os.path.expanduser("~")
PATH_TRANSLATIONS = [
    ("/Users/sophia/", LOCAL_HOME + "/"),
    ("/Users/selenamac/", LOCAL_HOME + "/"),
]

def translate_path(path):
    for from_prefix, to_prefix in PATH_TRANSLATIONS:
        if path.startswith(from_prefix):
            return to_prefix + path[len(from_prefix):]
    return path

def recv_exact(sock, n):
    data = b""
    while len(data) < n:
        chunk = sock.recv(n - len(data))
        if not chunk:
            raise IOError("Connection closed")
        data += chunk
    return data

def handle_client(client_sock, addr):
    print(f"[{addr}] Connected")
    try:
        header = recv_exact(client_sock, 8)
        msg_len = struct.unpack(">Q", header)[0]
        msg_data = recv_exact(client_sock, msg_len)
        request = json.loads(msg_data.decode("utf-8"))

        compiler = request.get("compiler", "gcc")
        compiler_path = COMPILERS.get(compiler, COMPILERS["gcc"])

        if not os.path.exists(compiler_path):
            response = {"success": False, "error": f"Compiler not found: {compiler_path}"}
        else:
            tmpdir = tempfile.mkdtemp(prefix="ppc_compile_")
            try:
                source_name = request.get("source_name", "input.c")
                source_path = os.path.join(tmpdir, source_name)
                source_content = request.get("source")
                if isinstance(source_content, str):
                    source_content = source_content.encode("utf-8")
                with open(source_path, "wb") as f:
                    f.write(source_content)

                args = [compiler_path]
                for arg in request.get("args", []):
                    if arg.startswith("-I") and len(arg) > 2:
                        args.append("-I" + translate_path(arg[2:]))
                    elif arg.startswith("-I"):
                        args.append(arg)
                    else:
                        args.append(translate_path(arg))

                output_name = request.get("output_name", "output.o")
                output_path = os.path.join(tmpdir, output_name)
                args.extend(["-c", source_path, "-o", output_path])

                print(f"[{addr}] Compiling: {source_name}")
                result = subprocess.run(args, capture_output=True, timeout=300)

                if result.returncode == 0 and os.path.exists(output_path):
                    with open(output_path, "rb") as f:
                        obj_data = f.read()
                    response = {
                        "success": True,
                        "object": base64.b64encode(obj_data).decode("ascii"),
                        "stdout": result.stdout.decode("utf-8", errors="replace"),
                        "stderr": result.stderr.decode("utf-8", errors="replace"),
                    }
                else:
                    response = {
                        "success": False,
                        "error": result.stderr.decode("utf-8", errors="replace"),
                        "stdout": result.stdout.decode("utf-8", errors="replace"),
                    }
            finally:
                shutil.rmtree(tmpdir, ignore_errors=True)

        resp_json = json.dumps(response).encode("utf-8")
        client_sock.sendall(struct.pack(">Q", len(resp_json)) + resp_json)
        print(f"[{addr}] Done: {response.get('success', False)}")

    except Exception as e:
        print(f"[{addr}] Error: {e}")
    finally:
        client_sock.close()

def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PORT
    os.environ["PATH"] = TOOLCHAIN + ":" + os.environ.get("PATH", "")

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("0.0.0.0", port))
    server.listen(128)

    print(f"POWER8 Cross-Compile Worker listening on port {port}")
    print(f"Toolchain: {TOOLCHAIN}")
    print(f"128 threads ready for distributed compilation!")

    while True:
        client_sock, addr = server.accept()
        t = threading.Thread(target=handle_client, args=(client_sock, addr))
        t.daemon = True
        t.start()

if __name__ == "__main__":
    main()
WORKER
chmod +x "${HOME}/ppc_compile_worker_power8.py"

# Create systemd service
echo "[6/6] Creating systemd service..."
sudo tee /etc/systemd/system/ppc-distcc-worker.service > /dev/null << SERVICE
[Unit]
Description=PPC-DistCC Cross-Compile Worker
After=network.target

[Service]
Type=simple
User=${USER}
ExecStart=/usr/bin/python3 ${HOME}/ppc_compile_worker_power8.py
Restart=always
RestartSec=10
Environment="PATH=${TOOLCHAIN}/bin:/usr/local/bin:/usr/bin:/bin"

[Install]
WantedBy=multi-user.target
SERVICE

sudo systemctl daemon-reload
sudo systemctl enable ppc-distcc-worker

echo ""
echo "=========================================="
echo "Installation Complete!"
echo "=========================================="
echo ""
echo "Cross-compiler installed to: ${TOOLCHAIN}"
echo ""
echo "Installed tools:"
ls -1 "${TOOLCHAIN}/bin/" | head -10
echo "..."
echo ""
echo "To start the worker:"
echo "  sudo systemctl start ppc-distcc-worker"
echo ""
echo "To test the cross-compiler:"
echo "  export PATH=${TOOLCHAIN}/bin:\$PATH"
echo "  echo 'int main() { return 0; }' > test.c"
echo "  powerpc-apple-darwin9-gcc -c test.c -o test.o"
echo "  file test.o  # Should show: Mach-O ppc object"
echo ""
echo "Add this machine to your G5 coordinator's wrapper:"
echo "  DEFAULT_HOSTS = ["
echo "      '$(hostname -I | awk '{print $1}')',  # POWER8 (128 threads!)"
echo "      ..."
echo "  ]"
echo ""
