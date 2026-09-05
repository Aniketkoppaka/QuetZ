# Docker Configuration

This directory will contain Dockerfile(s) and related configuration for the
sandboxed execution environment used by the autonomous agent.

## Purpose

Test execution for target repositories must happen inside an isolated Docker
container to:

- Prevent the agent from affecting the host system
- Enforce resource limits (CPU, RAM, network)
- Provide a reproducible, clean environment for each execution

## Status

Docker execution engine not yet implemented (planned: Milestone 6).

## Expected Contents (Future Milestones)

- `sandbox/Dockerfile` — base image for Python project test execution
- `sandbox/entrypoint.sh` — container entrypoint
- `docker-compose.yml` — optional local development orchestration
