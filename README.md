# QuetZ (Autonomous Software Engineer)

> *Named after Quetzalcoatl, the Mesoamerican deity of wisdom, learning, and wind.*

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Tests](https://img.shields.io/badge/tests-517%20passed-brightgreen.svg)]()
[![Coverage](https://img.shields.io/badge/coverage-85%25-green.svg)]()
[![Security SAST](https://img.shields.io/badge/sast-fail--closed-red.svg)]()
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

QuetZ is a production-grade, verifiable, fail-closed autonomous software engineering harness that resolves real-world software engineering issues end-to-end under deterministic safety constraints.

Unlike open-ended coding assistants that execute unconstrained code or hallucinate patch success, QuetZ is built on **verifiable state machines, AST syntactic invariant parsing, multi-tier anchor editing, fail-then-pass reproduction testing, cryptographic provenance signing, and organizational policy enforcement**.

---

## Key Capabilities & Architectural Highlights

- 🛡️ **Fail-Closed AST Verification**: Every code modification is parsed into concrete syntax trees. Non-syntactic changes, syntax errors, or policy violations are rejected with automatic, atomic workspace rollback.
- 🎯 **Deterministic 4-Tier Anchor File Editing**: Replaces brittle line numbers and raw regex with Exact Match, Whitespace-Normalized, AST Symbol-Scoped, and High-Confidence Fuzzy Anchor matching.
- 🧪 **Fail-Then-Pass Reproduction Engine**: Verifies that a reproduction candidate test actually *fails* on the unpatched codebase (confirming bug reproduction) before verifying that it *passes* post-patch.
- 💥 **Semantic Blast-Radius & Change-Impact Analysis**: Analyzes caller/callee graphs and symbol dependencies to calculate downstream blast radius and restrict mutation risk.
- 🧬 **Mutation Assertion Strength Testing**: Injects AST mutation operators (operator swapping, return value negation, boundary alteration) into the target function to ensure test suites detect logic regressions.
- 🔐 **Cryptographic Provenance & Tamper-Proof Certificates**: Signs all successful `VerificationCertificate` artifacts with HMAC-SHA256 digests and bit-flip tamper detection.
- 🔍 **Static Application Security Testing (SAST)**: Built-in pure-syntactic AST security scanner checking for CWE-95 (`eval`/`exec`), CWE-78 (command injection in `subprocess`), CWE-502 (insecure `pickle`/`yaml`), CWE-798 (hardcoded API keys), and CWE-295 (disabled TLS verification).
- 📜 **Supply-Chain & License Compliance Engine**: Audits `requirements.txt` and `pyproject.toml` dependencies with PEP 508 marker parsing and case-insensitive heuristics to block viral Copyleft/AGPL/SSPL licenses.
- 🌐 **Polyglot Structural Code Analyzers**: Structural symbol indexers for **Python**, **TypeScript / JavaScript** (classes, methods, arrow properties), **Go** (with 1.18+ generic type parameters), and **Rust** (with trait implementations and `impl` blocks).
- 🤖 **Universal Multi-Provider LLM Integration**: Zero third-party proprietary SDK requirements. Supports 8 backends: **Local Ollama** (offline/free), **Groq** (ultra-low latency LPU), **Anthropic** (Claude 3.5 Sonnet native Messages API), **DeepSeek**, **Google Gemini**, **Mistral AI**, **OpenAI**, and **OpenRouter** with automatic exponential retry backoff.
- 📊 **Bayesian Feedback Calibration & KPI Telemetry**: Self-tuning adaptive trust weighting based on human review outcomes (`MERGED_AS_IS`, `MERGED_WITH_EDITS`, `REJECTED_OR_ABANDONED`) and structured JSONL run metrics.
- 🖥️ **Interactive Engineering Control Console**: Browser-based web interface (`app.js`, `style.css`) providing real-time session execution inspection, chat interactions, live diagnostic telemetry, and run histories.
- 🚀 **GitHub PR Delivery & CI/CD Integration**: Direct automated PR creation via GitHub REST API, reusable GitHub Action (`action.yml`), pre-commit hooks, and SOC2/ISO enterprise compliance exporter.

---

## High-Level Autonomous Workflow

```text
               GitHub Issue / Problem Description
                              ↓
              Repository Acquisition & File Inventory
                              ↓
               AST Code Understanding & Symbol Mapping
                              ↓
               Engineering Playbook & Skill Matching
                              ↓
                Pre-Execution Policy & SAST Guardrails
                              ↓
          Reproduction Candidate Execution (Must FAIL)
                              ↓
           Implementation Planning (LLM Multi-Provider)
                              ↓
          Deterministic 4-Tier Anchor Code Modification
                              ↓
        Static AST Syntax Verification & Symbol Confirmation
                              ↓
           Test Suite Execution & Reproduction Verification (Must PASS)
                              ↓
        Mutation Strength Testing & Blast Radius Evaluation
                              ↓
              Independent Peer Review Agent Approval
                              ↓
        Cryptographic Signing of VerificationCertificate
                              ↓
            Direct GitHub Pull Request Delivery & Audit Export
```

---

## Quickstart & CLI Reference

Both `autonomous-engineer` and `quetz` CLI binaries are installed and available.

### 1. Launch the Web Engineering Control Console
```bash
python -m autonomous_engineer ui --host 127.0.0.1 --port 8080
# Or using the alias:
quetz ui --port 8080
```
Open `http://localhost:8080` in your browser to inspect live workflows, past runs, and system summaries.

---

### 2. Run Autonomous Issue Resolution

#### A. Run completely offline with Local Ollama (Air-Gapped / Free)
```bash
quetz run \
  --repo . \
  --title "Fix ZeroDivisionError in calculation" \
  --body "safe_divide crashes when divisor b is 0. Should return 0.0." \
  --provider ollama \
  --model llama3.1 \
  --reproduce-cmd "pytest -k test_zero_division" \
  --require-reproduction \
  --mutation-testing
```

#### B. Run with Groq (Ultra-Low Latency Inference)
```bash
export GROQ_API_KEY="gsk_..."
quetz run \
  --repo https://github.com/owner/repo \
  --title "Fix race condition in session cleanup" \
  --body "Session expiry leads to KeyError during concurrent disconnects" \
  --provider groq \
  --model llama-3.3-70b-versatile \
  --submit-pr
```

#### C. Run with Anthropic (Claude 3.5 Sonnet)
```bash
export ANTHROPIC_API_KEY="sk-ant-..."
quetz run \
  --repo https://github.com/owner/repo \
  --title "Add retry backoff for rate-limited requests" \
  --body "Implement exponential backoff when encountering 429 status codes" \
  --provider anthropic \
  --model claude-3-5-sonnet-20241022
```

#### D. Run with OpenRouter, DeepSeek, or OpenAI
```bash
# OpenRouter (Default free/paid models)
export OPENROUTER_API_KEY="sk-or-..."
quetz run --repo . --title "Fix memory leak" --body "Unclosed file handles" --provider openrouter

# DeepSeek
export DEEPSEEK_API_KEY="sk-..."
quetz run --repo . --title "Refactor query builder" --body "Optimize SQL joins" --provider deepseek

# OpenAI
export OPENAI_API_KEY="sk-..."
quetz run --repo . --title "Update auth headers" --body "Support bearer tokens" --provider openai
```

---

### 3. Enterprise Security, Governance & Audit Commands

#### Inspect System Capabilities & Security Policies
```bash
quetz audit
```

#### Run AST SAST Security Scan
```bash
quetz scan-security src/
```

#### Audit Dependencies for Copyleft / Prohibited Licenses
```bash
quetz scan-licenses requirements.txt
# Or scan an entire project directory:
quetz scan-licenses .
```

#### Export Enterprise Compliance Report (SOC2 / ISO Schema)
```bash
# JSON format
quetz export-audit --path . --output artifacts/compliance_audit.json

# Markdown executive summary
quetz export-audit --path . --output artifacts/compliance_audit.md
```

#### Cryptographic Provenance: Sign and Verify Certificates
```bash
# Sign a verification certificate
quetz sign-cert certificate.json --output certificate.signed.json --key "secret-key"

# Verify signature integrity and detect tampering
quetz verify-cert certificate.signed.json --key "secret-key"
```

#### Telemetry & Adaptive Confidence Tuning
```bash
# Display aggregated resolution KPIs
quetz metrics

# Calibrate confidence weights based on PR review outcome
quetz feedback --pr-id "PR-101" --issue-id "ISSUE-42" --outcome MERGED_AS_IS
```

---

## Supported LLM Providers

QuetZ incorporates zero external proprietary SDK dependencies and provides unified JSON schema-enforced generations across 8 backends:

| Provider Flag | Backend Target | Default Model | Custom API Base Override |
|---|---|---|---|
| `--provider ollama` | Local Ollama | `llama3.1:latest` | `--api-base http://localhost:11434/v1` |
| `--provider groq` | Groq LPU Inference | `llama-3.3-70b-versatile` | `--api-base https://api.groq.com/openai/v1` |
| `--provider anthropic` | Anthropic Messages API | `claude-3-5-sonnet-20241022`| `--api-base https://api.anthropic.com/v1` |
| `--provider deepseek` | DeepSeek Platform | `deepseek-chat` | `--api-base https://api.deepseek.com/v1` |
| `--provider gemini` | Google Gemini | `gemini-1.5-pro` | `--api-base https://generativelanguage.googleapis.com/v1beta/openai` |
| `--provider mistral` | Mistral AI | `mistral-large-latest` | `--api-base https://api.mistral.ai/v1` |
| `--provider openai` | OpenAI | `gpt-4o` | `--api-base https://api.openai.com/v1` |
| `--provider openrouter`| OpenRouter Gateway | `anthropic/claude-3.5-sonnet`| `--api-base https://openrouter.ai/api/v1` |

---

## Local Development & Testing

### Prerequisites
- Python 3.11+
- Git
- Optional: Docker Desktop (for isolated sandbox container execution)

### Installation
```bash
# 1. Clone repository
git clone https://github.com/Aniketkoppaka/QuetZ.git
cd QuetZ

# 2. Setup virtual environment
python -m venv .venv
# On Windows:
.venv\Scripts\activate
# On Linux/macOS:
source .venv/bin/activate

# 3. Install development dependencies in editable mode
pip install -e ".[dev]"
```

### Running the Test Suite
QuetZ maintains a **100% passing test suite** with 517 tests covering all edge cases, AST parsing, polyglot analysis, and security rules:

```bash
# Run full test suite
pytest

# Run fast with parallel workers (requires pytest-xdist)
pytest -n auto

# Run test coverage audit
pytest --cov=autonomous_engineer --cov-report=term-missing

# Run deep edge-case stress battery
pytest tests/unit/test_comprehensive_edge_cases.py -v
```

---

## Project Structure

```text
autonomous-software-engineer/
├── action.yml                    # Reusable GitHub Action for CI/CD pipelines
├── .pre-commit-hooks.yaml        # Pre-commit hook definitions
├── pyproject.toml                # Package configuration, scripts, dependencies
├── docker/                       # Isolated container sandbox environments
│   └── sandbox/Dockerfile
├── src/autonomous_engineer/      # Core QuetZ Platform
│   ├── agents/                   # Multi-provider LLM clients, planner, validator
│   ├── config/                   # Enterprise policy engine, project config loader
│   ├── domain/                   # Data contracts, state machine, errors
│   ├── execution/                # 4-tier file editor, preflight, docker runner, verifier
│   ├── github/                   # PR bot, direct GitHub API delivery, webhooks
│   ├── observability/            # Telemetry metrics, Bayesian adaptive tuner
│   ├── orchestration/            # 12-phase finite state machine pipeline
│   ├── repository/               # Polyglot analyzers (Go, Rust, JS/TS, Python)
│   ├── retrieval/                # Structural BM25 lexical & AST retrieval
│   ├── review/                   # Independent secondary reviewer agent
│   ├── tools/                    # Gated engineering playbooks & capabilities
│   ├── verification/             # Security SAST, license scanner, crypto signing
│   └── web/                      # Control console web server & frontend assets
│       ├── server.py
│       └── static/ (index.html, style.css, app.js)
└── tests/
    └── unit/                     # 517 unit and integration tests
```

---

## Contributing & License

Distributed under the **MIT License**. Contributions, bug reports, and playbook expansions are welcome via Pull Requests. All contributions must pass full linting, AST verification, and the 517-test regression suite.
