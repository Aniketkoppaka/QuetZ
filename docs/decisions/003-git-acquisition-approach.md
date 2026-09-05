# ADR-003: Git CLI via Subprocess Wrapper for Repository Acquisition

**Status:** Accepted
**Date:** 2026-08-28
**Milestone:** 2.1

## Context

The Autonomous Software Engineer requires a mechanism to acquire target repositories at specific revisions into isolated local workspaces. The acquisition layer must be reliable, secure, maintainable, deterministic, cross-platform (Windows/Linux/macOS), and introduce minimal external dependencies.

We evaluated three candidate approaches:
1. **Git CLI through a controlled `subprocess` wrapper**
2. **GitPython** (Python library wrapping Git CLI)
3. **pygit2** (Python bindings to the `libgit2` C library)

## Decision

We chose **Git CLI via a controlled Python `subprocess` wrapper** using the standard library.

We will NOT use `GitPython` or `pygit2`.

## Rationale

### 1. Security and Process Isolation
- Using `subprocess.run` with `shell=False` and strict list-based arguments guarantees that user input (repository URLs, branch names, commit SHAs) cannot cause shell command injection.
- We have complete control over process environment variables, allowing us to:
  - Disable interactive authentication prompts (`GIT_TERMINAL_PROMPT=0`, `GIT_ASKPASS=""`).
  - Disable global/system Git configs that could alter behavior (`GIT_CONFIG_NOSYSTEM=1`, `GIT_CONFIG_GLOBAL=NUL`/`/dev/null`).
  - Disable arbitrary hooks execution on clone/checkout (`-c core.hooksPath=""`).
- `GitPython` has a history of high-severity CVEs related to argument injection (e.g. CVE-2022-24439, CVE-2023-40267, CVE-2023-41040) due to permissive string parsing and complex internal wrappers.

### 2. Dependency Footprint and Portability
- The Git CLI is already the industry standard and must be present on any development/CI machine running this system.
- Standard library `subprocess` requires zero third-party dependencies (`pyproject.toml` remains lean).
- `pygit2` requires compiling or bundling `libgit2` binary C-extensions, introducing platform wheel compatibility risks and maintenance burden on Windows and varied Linux distros.

### 3. Maintainability and Auditability
- A dedicated wrapper class (~150 lines of Python) exposes exactly the operations our domain requires (`clone`, `fetch`, `checkout`, `rev-parse`), without the baggage of a full-featured Git object graph library.
- Error codes and stderr output map directly to explicit `FailureCategory` errors in our domain taxonomy.

## Consequences

- **Git requirement:** The host environment must have the `git` binary installed and accessible in `PATH`.
- **Structured Error Parsing:** Our wrapper must explicitly parse Git exit codes and stderr strings to categorize errors (e.g., repository not found, revision not found, network failure, timeout).
- **Process Overhead:** Each Git operation spawns a subprocess. Since repository acquisition happens once per workflow run (not in a tight loop), this overhead is negligible (<100ms).