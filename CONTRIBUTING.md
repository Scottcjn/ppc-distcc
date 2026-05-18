# Contributing to ppc-distcc

Thanks for helping improve ppc-distcc. This project supports vintage PowerPC
Mac build workflows, so changes should be careful about Python compatibility,
network behavior, and host-specific paths.

## Setup

1. Fork the repository and create a topic branch:

   ```sh
   git checkout -b fix/short-description
   ```

2. Use Python 3 for the coordinator and modern tooling:

   ```sh
   python3 --version
   python3 -m py_compile ppc_compile_coordinator.py
   ```

3. Use Python 2.5-compatible syntax for scripts intended to run on Tiger or
   Leopard:

   ```sh
   python -m py_compile ppc_compile_worker.py ppc_compile_wrapper.py config.py
   ```

4. For POWER8 cross-compiler changes, review `setup_power8_crosscompiler.sh`
   and test on a ppc64le Linux host when hardware is available.

## Pull Request Guidelines

- Keep one logical change per PR.
- Explain which host platform you tested on, such as Tiger, Leopard, Sorbet
  Leopard, or POWER8 Linux.
- Include exact commands used to validate the change.
- Do not commit generated build directories, object files, logs, or local host
  configuration.
- For worker or coordinator changes, mention whether local fallback behavior was
  exercised.

## Code Style

- Preserve compatibility with the Python version used by each script.
- Keep network timeouts and fallback paths explicit.
- Avoid hard-coded local paths unless they are documented examples.
- Prefer small functions with clear error messages over broad exception
  handling.
- Shell scripts should be POSIX-oriented where practical and should quote paths.

## Validation Checklist

- [ ] Python files compile with the appropriate interpreter.
- [ ] Shell scripts pass a syntax check, for example `bash -n script.sh`.
- [ ] README or patch documentation is updated for behavior changes.
- [ ] No secrets, host-specific credentials, or generated artifacts are included.
- [ ] The PR description lists the tested platform and commands.
