# QuetZ (Autonomous Software Engineer)

> *Named after Quetzalcoatl, the Mesoamerican deity of wisdom, learning, and wind.*

A production-grade, verifiable, fail-closed autonomous software engineering agent that resolves GitHub issues end-to-end under deterministic safety constraints.

> **Status: Production Architecture Complete (514 Passing Tests).**  
> Features full AST repository mapping, 4-tier fuzzy anchor editing, fail-then-pass reproduction verification, semantic AST blast-radius analysis, mutation testing, proof-carrying verification certificates with Ed25519/HMAC cryptographic signing, independent code review, direct automated GitHub PR delivery, interactive Chat-Centric Engineering Control Console, AST SAST scanner, copyleft license scanner, Bayesian confidence tuner, polyglot analysis (Python, JS/TS, Go, Rust), local Ollama/OpenAI/OpenRouter LLM provider routing, reusable GitHub Action, and automated SOC2 enterprise compliance exporter.

---

## Quickstart (CLI & Console)

Launch the **QuetZ Engineering Control Console**:
```bash
python -m autonomous_engineer ui --port 8080
```

Inspect system capabilities and security policies:
```bash
python -m autonomous_engineer audit
```

List registered engineering playbooks:
```bash
python -m autonomous_engineer skills
```

Run AST static application security scan (SAST):
```bash
python -m autonomous_engineer scan-security src/
```

Run supply-chain copyleft license audit:
```bash
python -m autonomous_engineer scan-licenses requirements.txt
```

Display aggregated KPI telemetry & resolution fidelity metrics:
```bash
python -m autonomous_engineer metrics
```

Export SOC2/ISO compliance and security audit report:
```bash
python -m autonomous_engineer export-audit --output artifacts/enterprise_audit.md
```

Run end-to-end autonomous resolution with Local Ollama:
```bash
python -m autonomous_engineer run \
  --repo https://github.com/owner/repo \
  --title "Fix ZeroDivisionError in calculation" \
  --body "safe_divide crashes when divisor b is 0. Should return 0.0." \
  --provider ollama \
  --model llama3.1 \
  --reproduce-cmd "pytest -k test_zero_division" \
  --require-reproduction \
  --mutation-testing \
  --submit-pr
```

Run live benchmark validation suite:
```bash
python scripts/run_pipeline_benchmark.py
```

For the comprehensive technical whitepaper, see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

---

## Scope (Explicitly Bounded)

The system is intentionally constrained to:

- **Python** repositories
- **GitHub**-based workflows
- **Small-to-medium** repositories
- **Well-defined** software-engineering issues
- **pytest**-compatible projects where practical
- **Controlled** execution environments
- **Bounded** repair iterations

Do not expand scope without explicit approval.

---

## Intended High-Level Workflow

```
GitHub Issue
    ↓
Repository Acquisition   — clone & workspace setup
    ↓
Repository Understanding — file graph, key symbols, test inventory
    ↓
Code Retrieval           — locate relevant files/symbols for the issue
    ↓
Implementation Planning  — reason about required changes
    ↓
Controlled Code Modification — apply changes via bounded tool calls
    ↓
Sandboxed Execution      — run tests in an isolated Docker container
    ↓
Test / Check Results     — parse structured pass/fail output
    ↓
Failure Analysis + Bounded Repair Loop — diagnose and retry (capped iterations)
    ↓
Independent Review       — secondary agent validates the patch
    ↓
Final Verification       — confirm tests pass on clean checkout
    ↓
Patch / Pull Request     — submit result to GitHub
```

---

## Development Approach

Implementation is deliberate and incremental across numbered milestones:

| Milestone | Focus |
|-----------|-------|
| **0** (current) | Project foundation, environment, structure, documentation |
| 1 | Domain models, configuration system |
| 2 | Repository acquisition and workspace management |
| 3 | Code retrieval strategy |
| 4 | LLM integration and planning agent |
| 5 | Coding agent with controlled tool use |
| 6 | Sandboxed execution engine |
| 7 | Bounded repair loop |
| 8 | Independent review agent |
| 9 | GitHub integration and PR creation |
| 10 | Evaluation harness and benchmarking |

Each milestone is gated on a definition-of-done checklist before proceeding.

---

## Development Principles

| Principle | Meaning |
|-----------|---------|
| **Correctness over feature count** | Fewer, verified capabilities beat more, unreliable ones |
| **Explicit state transitions** | Every phase has clear inputs, outputs, and preconditions |
| **Controlled tools** | The agent interacts with the world only through declared, auditable tools |
| **Sandboxed execution** | Code runs in isolated containers; the host system is never exposed |
| **Bounded autonomous loops** | Repair iterations are capped; the system cannot loop indefinitely |
| **Evidence-based verification** | Claims about pass/fail are grounded in actual test output |
| **Reproducibility** | Given the same inputs, the system should produce deterministic, auditable outputs |
| **Observability** | Every significant action is logged with structured, queryable output |
| **Security** | Credentials are never committed; sandboxing limits blast radius |

---

## Local Setup

### Prerequisites

- Python 3.11+
- `pip` (or `uv` / `pipx` for isolated installs)
- Docker Desktop (required for sandboxed execution — later milestones only)
- Git

### 1. Clone the repository

```bash
git clone https://github.com/Aniketkoppaka/QuetZ.git
cd QuetZ
```

### 2. Create and activate a virtual environment

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate
```

### 3. Install the package with development dependencies

```bash
pip install -e ".[dev]"
```

### 4. Configure environment variables

```bash
cp .env.example .env
# Edit .env and fill in real values
```

---

## Running the Test Suite

```bash
# Run all tests
pytest

# Run only unit tests
pytest tests/unit/

# Run with coverage
pytest --cov=autonomous_engineer --cov-report=term-missing

# Run a specific test file
pytest tests/unit/test_package_import.py -v
```

---

## Project Layout

```
autonomous-software-engineer/
├── README.md                     # This file
├── pyproject.toml                # Python project + tool configuration
├── .env.example                  # Environment variable documentation
├── .gitignore
├── docker/                       # Docker configuration (future milestones)
├── docs/
│   ├── architecture/             # Component architecture documents
│   ├── decisions/                # Architectural decision records (ADRs)
│   └── evaluation/               # Benchmark and evaluation documentation
├── src/
│   └── autonomous_engineer/      # Main Python package
│       ├── config/               # Configuration loading
│       ├── domain/               # Core data models
│       ├── orchestration/        # Agent loop and coordination
│       ├── repository/           # Repo cloning and workspace
│       ├── retrieval/            # Code retrieval strategies
│       ├── tools/                # Bounded tool definitions
│       ├── execution/            # Sandboxed test execution
│       ├── agents/               # LLM-backed agent implementations
│       ├── github/               # GitHub API integration
│       ├── review/               # Independent review agent
│       ├── evaluation/           # Evaluation harness
│       └── observability/        # Logging and tracing
├── tests/
│   ├── unit/                     # Fast, dependency-free tests
│   ├── integration/              # Tests requiring external services
│   └── fixtures/                 # Shared test data and helpers
├── scripts/                      # Developer utility scripts
└── examples/                     # Example inputs and usage
```

---

## Contributing

Development proceeds milestone-by-milestone.  Each milestone has a
definition-of-done checklist that must be satisfied before work on the
next milestone begins.  See `docs/architecture/` for current design
documentation.
