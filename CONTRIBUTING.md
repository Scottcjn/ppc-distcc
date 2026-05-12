# Contributing to PPC-DistCC

Thanks for helping improve PPC-DistCC. This project supports distributed
compilation across PowerPC Macs and helper systems, so contributions should
preserve compatibility with older Python versions, legacy Mac OS X releases,
and mixed compiler environments.

## Useful Contributions

- Clarify setup steps for Tiger, Leopard, Sorbet Leopard, and POWER helper
  hosts.
- Improve examples for coordinator and worker configuration.
- Document compiler/version combinations that work or fail.
- Add small compatibility fixes that keep Python 2.5+ behavior intact.
- Improve fallback behavior or diagnostics when workers are unavailable.

## Development Workflow

1. Fork the repository and create a focused branch.
2. Keep each pull request limited to one feature, fix, or documentation update.
3. Preserve compatibility with the oldest supported runtime unless the PR
   explicitly explains why that compatibility must change.
4. Include reproduction steps, test commands, or hardware details in the PR
   description.

## Validation

Use the lightest validation that matches the change:

- Documentation-only changes: run `git diff --check`.
- Python changes: run the modified scripts with the oldest Python version you
  can reasonably access and note the version used.
- Network or distributed-build changes: include the coordinator command, worker
  command, host OS versions, compiler versions, and observed output.

## Pull Request Checklist

- The PR explains what changed and why.
- Compatibility impact is called out for Tiger/Leopard/Sorbet users.
- Commands or manual verification steps are included.
- Large logs are summarized, with only the relevant error/output included.
- No generated archives, build outputs, or machine-specific paths are committed.

## Reporting Issues

Please include the host OS, Python version, compiler version, number of workers,
the command being run, and the full error output. For performance reports,
include the source project, job count, and whether local fallback was triggered.
