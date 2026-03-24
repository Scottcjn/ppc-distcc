# Contributing to ppc-distcc

Thank you for your interest in contributing to ppc-distcc! This project enables distributed compilation for PowerPC systems, making builds faster across multiple machines.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Environment](#development-environment)
- [How to Contribute](#how-to-contribute)
- [Style Guidelines](#style-guidelines)
- [Testing](#testing)
- [Submitting Changes](#submitting-changes)
- [Communication](#communication)

## Code of Conduct

This project adheres to a code of conduct that expects all participants to:
- Be respectful and inclusive
- Welcome newcomers and help them learn
- Focus on constructive feedback
- Respect differing viewpoints and experiences

## Getting Started

### Prerequisites

To contribute to ppc-distcc, you'll need:

- **PowerPC hardware or emulator**: G3, G4, G5, or QEMU with ppc emulation
- **Operating System**: Linux (Debian, Ubuntu, Fedora) or Mac OS X Tiger/Leopard
- **Compiler**: GCC or Clang with PowerPC support
- **Git**: For version control
- **distcc**: The distributed compiler (usually installed via package manager)

### Quick Start

```bash
# Clone the repository
git clone https://github.com/Scottcjn/ppc-distcc.git
cd ppc-distcc

# Build the project
make

# Run tests
make test
```

## Development Environment

### Setting Up QEMU for PowerPC Development

If you don't have physical PowerPC hardware, use QEMU:

```bash
# Install QEMU
sudo apt-get install qemu-system-ppc

# Download a PowerPC Linux image or use your own
# For Debian PowerPC:
qemu-system-ppc -m 512 -hda debian-powerpc.qcow2 -netdev user,id=net0 -device sungem,netdev=net0
```

### Mac OS X Tiger Development

For Tiger-specific development:

```bash
# Install Xcode 2.5 from Apple Developer Connection
# Ensure /usr/bin/gcc is in your PATH

# Build with Tiger-specific flags
make CFLAGS="-arch ppc -mmacosx-version-min=10.4"
```

### Cross-Compilation Setup

If developing on x86/x64 for PowerPC targets:

```bash
# Install PowerPC cross-compiler
sudo apt-get install gcc-powerpc-linux-gnu

# Set environment variables
export CC=powerpc-linux-gnu-gcc
export CXX=powerpc-linux-gnu-g++

# Build
make
```

## How to Contribute

### Reporting Bugs

When reporting bugs, please include:

- **PowerPC architecture**: G3, G4, G5, or specific model
- **Operating system**: Distribution and version
- **Compiler version**: `gcc --version` or `clang --version`
- **distcc version**: `distcc --version`
- **Steps to reproduce**: Clear, minimal steps
- **Expected vs actual behavior**: What you expected vs what happened
- **Logs**: Relevant error messages or log output

### Suggesting Enhancements

Enhancement suggestions are welcome! Please:

- Check existing issues first to avoid duplicates
- Describe the use case and benefits
- Consider backward compatibility with older PowerPC systems
- Be open to discussion and alternative approaches

### Contributing Code

#### Finding Issues to Work On

- Look for issues labeled `good first issue` or `help wanted`
- Check the [issue tracker](https://github.com/Scottcjn/ppc-distcc/issues)
- Comment on an issue before starting work to avoid duplication

#### Making Changes

1. **Fork the repository** on GitHub
2. **Clone your fork**:
   ```bash
   git clone https://github.com/YOUR_USERNAME/ppc-distcc.git
   cd ppc-distcc
   ```
3. **Create a branch**:
   ```bash
   git checkout -b feature/your-feature-name
   ```
4. **Make your changes** following our style guidelines
5. **Test your changes** on PowerPC hardware or emulator
6. **Commit with clear messages**:
   ```bash
   git commit -m "feat: add support for G5 quad-core detection"
   ```
7. **Push to your fork**:
   ```bash
   git push origin feature/your-feature-name
   ```
8. **Open a Pull Request** with a clear description

## Style Guidelines

### C Code Style

We follow the Linux kernel coding style with PowerPC-specific considerations:

```c
/* Function declarations */
int ppc_detect_cpu_type(void);

/* Use tabs for indentation, width 8 */
void configure_distcc_hosts(void)
{
	struct host_config *hosts;
	int num_hosts;

	hosts = parse_host_file("/etc/distcc/hosts");
	if (!hosts) {
		fprintf(stderr, "Failed to parse hosts file\n");
		return;
	}

	/* Rest of function */
}

/* PowerPC-specific register usage */
static inline void ppc_sync(void)
{
	__asm__ __volatile__("sync" ::: "memory");
}
```

### Shell Script Style

For shell scripts in this project:

```bash
#!/bin/bash
# Use bash for compatibility

# Variables: lowercase with underscores
ppc_hosts="powermac-g4.local,powerbook-g4.local"

# Functions: descriptive names
configure_distcc_ppc() {
    local num_hosts=$1
    local host_list=$2

    for host in $(echo "$host_list" | tr ',' '\n'); do
        echo "Adding host: $host"
    done
}

# Error handling
set -euo pipefail
```

### Documentation Style

- Use clear, concise language
- Include code examples where helpful
- Document PowerPC-specific behaviors
- Keep README and man pages in sync

## Testing

### Running Tests

```bash
# Run all tests
make test

# Run specific test
make test-unit
make test-integration

# Run with verbose output
make test VERBOSE=1
```

### Test Categories

1. **Unit Tests**: Test individual functions in isolation
2. **Integration Tests**: Test distcc with actual compilation
3. **Hardware Detection Tests**: Verify CPU type detection on various PowerPC models
4. **Network Tests**: Test distributed compilation across multiple hosts

### Testing on Real Hardware

If you have access to PowerPC hardware:

```bash
# Test on G4
make test TARGET=powerpc-g4

# Test on G5
make test TARGET=powerpc-g5

# Test distributed compilation
make test-distcc HOSTS="g4-host.local,g5-host.local"
```

### Continuous Integration

Tests are run automatically on:
- Every Pull Request
- Daily on the main branch
- Before each release

## Submitting Changes

### Pull Request Process

1. **Update documentation** if your change affects usage
2. **Add tests** for new functionality
3. **Ensure all tests pass**:
   ```bash
   make test
   ```
4. **Update CHANGELOG.md** if applicable
5. **Fill out the PR template** with:
   - Description of changes
   - Motivation for the change
   - Testing performed
   - PowerPC hardware tested on

### PR Review Process

- All PRs require at least one review
- Address review feedback promptly
- Keep discussions focused and technical
- Be patient - reviewers are volunteers

### Commit Message Format

Follow conventional commits:

```
<type>(<scope>): <subject>

<body>

<footer>
```

Types:
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style changes (formatting, no logic change)
- `refactor`: Code refactoring
- `test`: Adding or updating tests
- `chore`: Build process or auxiliary tool changes

Examples:
```
feat(cpu): add support for G5 quad-core detection

Implements CPU detection for PowerMac G5 Quad models,
distinguishing between dual-core and quad-core configurations.

Tested on: PowerMac G5 Quad 2.5GHz

Closes #123
```

## Communication

### Issue Tracker

- [GitHub Issues](https://github.com/Scottcjn/ppc-distcc/issues): Bug reports and feature requests

### Discussions

- [GitHub Discussions](https://github.com/Scottcjn/ppc-distcc/discussions): General questions and ideas

### Real-Time Chat

- IRC: `#ppc-distcc` on Libera.Chat

### Bounties

Some issues have bounties attached! Check the [rustchain-bounties](https://github.com/Scottcjn/rustchain-bounties) repository for opportunities to earn RTC tokens for your contributions.

## PowerPC-Specific Notes

### CPU Architecture Detection

The project