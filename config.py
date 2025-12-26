#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
PPC-DistCC Configuration

Edit this file to add/remove PowerPC Mac workers.
Compatible with Python 2.5+ (Tiger/Leopard/Sorbet)
"""

# Worker nodes on the network
# Each entry: {'host': 'IP', 'port': 5555, 'name': 'friendly-name', 'weight': 1.0}
# Weight determines job priority: higher = more jobs
#   - G5 dual-core: weight 2.0
#   - G4 dual-core: weight 1.5
#   - G4 single:    weight 1.0

WORKERS = [
    # === G5 Machines (PowerPC 970, faster) ===
    {
        'host': '192.168.0.130',
        'port': 5555,
        'name': 'g5-130',
        'user': 'sophia',
        'password': 'Elyanlabs12@',
        'weight': 2.0,
        'cpus': 2,
    },
    {
        'host': '192.168.0.179',
        'port': 5555,
        'name': 'selenamac-g5',
        'user': 'selenamac',
        'password': 'Elyanlabs12@',
        'weight': 2.0,
        'cpus': 2,
    },

    # === G4 Machines (PowerPC 74xx, slower but still useful) ===
    {
        'host': '192.168.0.125',
        'port': 5555,
        'name': 'dual-g4-125',
        'user': 'sophia',
        'password': 'Elyanlabs12@',
        'weight': 1.5,
        'cpus': 2,
    },
    {
        'host': '192.168.0.115',
        'port': 5555,
        'name': 'g4-powerbook-115',
        'user': 'sophia',
        'password': 'Elyanlabs12@',
        'weight': 1.0,
        'cpus': 1,
    },

    # === Add more machines below ===
    # {
    #     'host': '192.168.0.xxx',
    #     'port': 5555,
    #     'name': 'my-ppc-mac',
    #     'user': 'username',
    #     'password': 'password',
    #     'weight': 1.0,
    #     'cpus': 1,
    # },
]

# Default compiler paths on worker machines
COMPILERS = {
    # System compilers
    'gcc': '/usr/bin/gcc',
    'g++': '/usr/bin/g++',

    # Tigerbrew GCC 7
    'gcc-7': '/usr/local/bin/gcc-7',
    'g++-7': '/usr/local/bin/g++-7',

    # Custom GCC 10
    'gcc-10': '/usr/local/bin/gcc-10',
    'g++-10': '/usr/local/bin/g++-10',

    # LLVM/Clang (paths vary by machine)
    'clang': [
        '/Users/sophia/llvm-3.9-build/bin/clang',
        '/Users/sophia/llvm-3.4-build/Release/bin/clang',
        '/usr/local/bin/clang',
    ],
    'clang++': [
        '/Users/sophia/llvm-3.9-build/bin/clang++',
        '/Users/sophia/llvm-3.4-build/Release/bin/clang++',
        '/usr/local/bin/clang++',
    ],
}

# Network settings
DEFAULT_PORT = 5555
CONNECT_TIMEOUT = 2.0      # Seconds to wait for connection
COMPILE_TIMEOUT = 300.0    # 5 minutes max per file

# SSH settings for auto-starting workers
SSH_KEY = None  # Path to SSH key, or None for password auth
SSH_TIMEOUT = 10.0

# Logging
LOG_FILE = '/tmp/ppc-distcc.log'
VERBOSE = False
