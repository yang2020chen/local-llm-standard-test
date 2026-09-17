# Local LLM Standard Test (LLST)

[![Release](https://img.shields.io/badge/release-v1.0.0-brightgreen.svg)](https://github.com/yang2020chen/local-llm-standard-test/releases)
[![License](https://img.shields.io/badge/license-Apache--2.0-green.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-brightgreen.svg)]()
[![Docker](https://img.shields.io/badge/docker-sandbox-2496ED.svg)]()

> **Standardized, reproducible, and cryptographically verifiable capability & long-context performance benchmark for locally deployed Large Language Models.**

---

## 🎯 Why LLST?

Benchmarking local LLMs (via `llama.cpp`, `vLLM`, `Ollama`, etc.) currently suffers from severe reproducibility and evaluation drift:
1. **Sample Drift**: Running benchmarks with naive `limit: N` randomly draws from moving upstream datasets (e.g., `release_latest` in coding benchmarks or varying test splits).
2. **Configuration Coupling**: Benchmark definitions are frequently entangled with hardcoded server IPs, local paths, and private tokens.
3. **Non-Deterministic Workloads**: Performance measurements vary across hardware runs because generated random prompts change between executions.
4. **Security Vulnerabilities**: Code evaluation suites executing untrusted LLM-generated code on the host bare metal.

**LLST solves these challenges through a strict, decoupled protocol.**

---

## 🏛️ Core Architecture Principles

```text
               ┌────────────────────────────────────────────────────────┐
               │         LLST v1.0 Immutable Standard Protocol           │
               │   (configs/protocols/standard_test_v1.yaml)            │
               └──────────────────────────┬─────────────────────────────┘
                                          │
            ┌─────────────────────────────┴─────────────────────────────┐
            ▼                                                           ▼
┌──────────────────────────────────────┐    ┌──────────────────────────────────────┐
│  Stage 1: Capability Suite (102 Qs)  │    │ Stage 2: Performance Benchmark (4-T) │
│  • MMLU-Pro: 42 pinned questions     │    │  • Tier 1: ISL 512   -> OSL 512      │
│  • IFEval: 20 pinned questions       │    │  • Tier 2: ISL 4096  -> OSL 512      │
│  • AIME24: 10 pinned questions       │    │  • Tier 3: ISL 16384 -> OSL 512      │
│  • C-Eval: 20 pinned questions       │    │  • Tier 4: ISL 28672 -> OSL 512      │
│  • LiveCodeBench: 10 pinned problems │    │  • Deterministic seed: 20260917      │
│  • Native offline disk slice cache   │    │  • Workload line_by_line sha256      │
│  • Isolated Docker execution sandbox │    │  • TTFT / TPOT / Throughput (tok/s)  │
└──────────────────┬───────────────────┘    └──────────────────┬───────────────────┘
                   │                                           │
                   └─────────────────────┬─────────────────────┘
                                         ▼
                   ┌───────────────────────────────────────────┐
                   │    Cryptographic Closure & Verification   │
                   │ manifest_hash == resolved == executed     │
                   └───────────────────────────────────────────┘
```

1. **Protocol & Profile Decoupling**: The benchmark standard protocol (`configs/protocols/standard_test_v1.yaml`) is completely immutable and decoupled from individual machine environments (`configs/machines/machine.local.yaml`).
2. **Cryptographically Pinned 102 Questions**: All 102 questions across 5 core domains are bound to immutable `sample_id`, `prompt_sha256`, `target_sha256`, and `record_sha256` in `configs/protocols/v1/sample_manifest.json`.
3. **Native Offline Dataset Pinning**: Datasets are cleanly sliced and loaded via native EvalScope `dataset_dir` disk caching without fragile runtime monkey-patching.
4. **Deterministic Token Workloads**: Performance prompts are generated with a deterministic pseudo-random seed (`20260917`) and recorded with SHA256 manifests, guaranteeing identical stress across different hardware (RTX 4090, RX 7900 XTX, Mac Studio, H100).
5. **Fail-Closed Gate Defense (N1–N5)**: Any tampering with dataset snapshots, prompt hashes, tokenizer vocab/fingerprint, or sample IDs immediately halts execution.
6. **Docker Sandbox Isolation**: Bare-metal execution is prohibited. Code benchmarks (LiveCodeBench) are executed strictly within ephemeral, non-root Docker containers.

---

## 🚀 Quickstart

### 1. Prerequisites & Installation
- OS: Linux (Ubuntu 22.04+ recommended) or macOS
- Python >= 3.10
- Docker (required for LiveCodeBench sandbox execution)

```bash
git clone https://github.com/yang2020chen/local-llm-standard-test.git
cd local-llm-standard-test

# Run automated setup
./scripts/install.sh
```

### 2. Configure Machine Profile
Copy the template and configure your local OpenAI-compatible inference endpoint (e.g. `llama-server`, `vLLM`):
```bash
cp configs/machines/machine.example.yaml configs/machines/machine.local.yaml
```

Edit `configs/machines/machine.local.yaml`:
```yaml
model:
  name: "Your-Model-Name"

api:
  base_url: "http://127.0.0.1:8082/v1"
  perf_url: "http://127.0.0.1:8082/v1/completions"
  api_key_env: "LLST_API_KEY"

tokenizer:
  path: "./tokenizer"
  fingerprint: "./tokenizer_fingerprint.json"
  trust_remote_code: false

runtime:
  context_length: 32768

output:
  root: "./outputs"
```

Export your local API key:
```bash
export LLST_API_KEY="your-local-api-key"
```

`tokenizer.fingerprint` is mandatory. Create it from the exact tokenizer used by
the server, store it outside source control when it is machine-specific, and do
not enable `trust_remote_code` unless that tokenizer code has been reviewed.

### 3. Verification & Preflight Gate
Run preflight inspection to verify network connectivity, context length limit, tokenizer fingerprint, and protocol sample integrity:
```bash
./scripts/run_standard_test.sh --check
```

Expected output:
```text
[PREFLIGHT ALL PASSED]
DATASET_SNAPSHOT_PASS
MMLU-Pro      42/42 VERIFIED
IFEval        20/20 VERIFIED
AIME24        10/10 VERIFIED
CEval         20/20 VERIFIED
LiveCodeBench 10/10 VERIFIED
TOTAL         102/102 VERIFIED
TOKENIZER_FINGERPRINT_PASS
PROTOCOL_VERIFICATION_PASS
```

### 4. Run Minimal Sanity Smoke Test
Run an end-to-end smoke test (evaluates 1 capability sample and 2 performance tiers) in ~2 minutes:
```bash
./scripts/run_standard_test.sh --smoke
```

### 5. Run Full Standard Test
Execute the full 102-question capability evaluation followed by the 4-tier long-context performance benchmark:
```bash
./scripts/run_standard_test.sh
```

All outputs, execution manifests, and summary reports are written to `outputs/<model_name>/<timestamp>/`.

---

## 🛡️ Protocol Security & Fail-Closed Gates

LLST includes an automated negative gate test suite (`scripts/test_negative_gates.py`) validating 100% Fail-Closed behavior:

| Gate | Tested Attack / Anomaly | Enforcement Mechanism |
| :--- | :--- | :--- |
| **N1** | Tampered Prompt SHA256 | `PROTOCOL_SAMPLE_MISMATCH` |
| **N2** | Tampered Sample ID / LCB Question ID | `PROTOCOL_SAMPLE_MISMATCH` |
| **N3** | Tampered Tokenizer File / Vocab Hash | `TOKENIZER_FINGERPRINT_MISMATCH` |
| **N4** | Upstream Dataset Snapshot / Revision Drift | `DATASET_SNAPSHOT_MISMATCH` |
| **N5** | Tampered Target / Answer / Record SHA256 | `PROTOCOL_SAMPLE_MISMATCH` |

Run the negative test suite:
```bash
python3 scripts/test_negative_gates.py
```

---

## 📊 Baseline Gallery

| ID | Hardware | Model | Context | Stage 1 (Capability) | Stage 2 (Perf 28k TTFT) | Status |
| :--- | :--- | :--- | :---: | :---: | :---: | :---: |
| [`#001`](examples/baseline_001/) | Dual AMD Radeon RX 7900 XTX (48GB) | Qwen3.8-Flash-Next (UD-Q3_K_XL + MTP) | 32k | **MMLU-Pro: 85.7%**<br>**IFEval: 95.0%**<br>**CEval: 90.0%**<br>**LCB: 80.0%**<br>**AIME24: 30.0%** | **TTFT: 40.9s**<br>TPOT: 41.7ms<br>Throughput: 7.29 tok/s | `VERIFIED STABLE` |

---

## 📦 Project Structure

```text
local-llm-standard-test/
├── LICENSE                                # Apache 2.0 License
├── README.md                              # Project documentation
├── requirements.txt                       # Core dependencies
│
├── configs/
│   ├── protocols/
│   │   ├── standard_test_v1.yaml          # Immutable standard test protocol
│   │   └── v1/
│   │       ├── dataset_manifest.json      # Dataset snapshot hashes & revisions
│   │       └── sample_manifest.json       # 102 cryptographically pinned questions
│   └── machines/
│       ├── machine.example.yaml           # Machine profile template
│       └── machine.local.yaml             # (Ignored by git) Local host configuration
│
├── scripts/
│   ├── install.sh                         # Environment setup script
│   ├── run_standard_test.sh               # Unified runner (--check, --smoke, full)
│   └── test_negative_gates.py             # N1-N5 Fail-Closed test suite
│
├── llst/
│   ├── preflight.py                       # Preflight health & safety inspection
│   ├── protocol_validator.py              # Cryptographic protocol runtime verifier
│   ├── config_loader.py                   # Dynamic config resolver
│   ├── capability/
│   │   ├── runner.py                      # Manifest-driven capability runner
│   │   ├── sample_resolver.py             # Exact sample extraction & hash checking
│   │   └── pinned_dataset.py              # Native offline dataset caching
│   ├── performance/
│   │   ├── runner.py                      # Deterministic 4-tier workload runner
│   │   └── workload_generator.py          # Deterministic token workload generator
│   └── report/
│       └── aggregate.py                   # Standardized report aggregator
│
└── examples/
    └── baseline_001/                      # Baseline #001 reference profile & report
```

---

## 📄 License

This project is licensed under the [Apache License 2.0](LICENSE).
