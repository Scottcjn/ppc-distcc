#!/bin/bash
# sync_generated_files.sh - Sync generated build files across distributed workers
#
# For complex builds (LLVM, etc.) that generate .inc, .def, .gen files during compilation,
# these files need to be synced from the coordinator to all workers periodically.
#
# Usage:
#   ./sync_generated_files.sh [build_dir] [interval_seconds]
#
# Example:
#   ./sync_generated_files.sh ~/llvm-3.9-build 120
#
# Environment:
#   PPC_DISTCC_WORKERS - Comma-separated list of worker hosts (user@host format)
#   PPC_DISTCC_PASSWORD - SSH password for workers (or use SSH keys)

BUILD_DIR="${1:-$HOME/build}"
INTERVAL="${2:-120}"

# Default workers from config
WORKERS="${PPC_DISTCC_WORKERS:-}"
PASSWORD="${PPC_DISTCC_PASSWORD:-}"

# SSH options for legacy Macs
SSH_OPTS="-o StrictHostKeyChecking=no -o HostKeyAlgorithms=ssh-rsa -o PubkeyAcceptedKeyTypes=ssh-rsa"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

sync_to_worker() {
    local worker="$1"
    local tarball="$2"

    if [ -n "$PASSWORD" ]; then
        sshpass -p "$PASSWORD" scp -q $SSH_OPTS "$tarball" "$worker:~/" 2>/dev/null
        sshpass -p "$PASSWORD" ssh $SSH_OPTS "$worker" \
            "cd ~/$(basename $BUILD_DIR) && tar xzf ~/$(basename $tarball) 2>/dev/null" 2>/dev/null
    else
        scp -q $SSH_OPTS "$tarball" "$worker:~/" 2>/dev/null
        ssh $SSH_OPTS "$worker" \
            "cd ~/$(basename $BUILD_DIR) && tar xzf ~/$(basename $tarball) 2>/dev/null" 2>/dev/null
    fi
}

if [ -z "$WORKERS" ]; then
    echo "Error: No workers configured. Set PPC_DISTCC_WORKERS environment variable."
    echo "Example: export PPC_DISTCC_WORKERS='selenamac@192.168.0.179,sophia@192.168.0.125'"
    exit 1
fi

if [ ! -d "$BUILD_DIR" ]; then
    echo "Error: Build directory not found: $BUILD_DIR"
    exit 1
fi

log "Starting generated file sync"
log "Build directory: $BUILD_DIR"
log "Sync interval: ${INTERVAL}s"
log "Workers: $WORKERS"

# Convert comma-separated workers to array
IFS=',' read -ra WORKER_ARRAY <<< "$WORKERS"

while true; do
    # Find and package generated files
    cd "$BUILD_DIR"
    GEN_FILES=$(find . \( -name "*.inc" -o -name "*.def" -o -name "*.gen" -o -name "*.td.d" \) 2>/dev/null)

    if [ -n "$GEN_FILES" ]; then
        TARBALL="/tmp/ppc-distcc-gen-$(date +%s).tar.gz"
        tar czf "$TARBALL" $GEN_FILES 2>/dev/null
        FILE_COUNT=$(echo "$GEN_FILES" | wc -l)

        log "Syncing $FILE_COUNT generated files..."

        # Sync to each worker
        for worker in "${WORKER_ARRAY[@]}"; do
            worker=$(echo "$worker" | xargs)  # trim whitespace
            sync_to_worker "$worker" "$TARBALL" &
        done
        wait

        rm -f "$TARBALL"
        log "Sync complete"
    else
        log "No generated files found"
    fi

    sleep "$INTERVAL"
done
