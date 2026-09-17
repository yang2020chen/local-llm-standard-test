# LLST Architecture & Invocation Flow (v1.0)

## Overview
Local LLM Standard Test (LLST) separates benchmark definitions into two decoupled layers:
1. **Standard Protocol** (`configs/protocols/standard_test_v1.yaml`): The immutable benchmark standard (102 capability questions + 4-tier long-context performance load).
2. **Machine Profile** (`configs/machines/machine.example.yaml`): Host-specific inference endpoint, local tokenizer path, context limits, and hardware metadata.

## Execution Pipeline
```text
scripts/run_standard_test.sh --protocol <protocol.yaml> --machine <machine.yaml>
   │
   ▼
[1] llst/config_loader.py: Merge protocol + machine configuration
   │
   ▼
[2] llst/preflight.py: Automated Security & Health Gate
   ├─ API Endpoint Connectivity (GET /models with Bearer Auth)
   ├─ Tokenizer Validation & Fingerprint Verification
   ├─ Context Length Threshold (Context >= 28672 + 512 = 29184)
   ├─ EvalScope Registry & Dataset Health Check
   └─ Docker Sandbox Verification (Mandatory for LiveCodeBench)
   │
   ▼
[3] llst/capability/runner.py: Stage 1 Capability Evaluation
   ├─ MMLU-Pro: 14 subsets × 3 = 42 questions
   ├─ IFEval: default × 20 = 20 questions
   ├─ AIME24: default × 10 = 10 questions
   ├─ C-Eval: 20 subsets × 1 = 20 questions
   └─ LiveCodeBench: 10 problems (Isolated Docker Container)
   │
   ▼
[4] llst/performance/runner.py: Stage 2 Standardized Performance Benchmark
   ├─ Deterministic Seed Injection (seed: 20260917)
   ├─ ISL 512   -> OSL 512 (2 requests)
   ├─ ISL 4096  -> OSL 512 (2 requests)
   ├─ ISL 16384 -> OSL 512 (2 requests)
   └─ ISL 28672 -> OSL 512 (2 requests)
   │
   ▼
[5] llst/report/aggregate.py: Standardized Report Aggregation
   ├─ capability_summary.json
   ├─ performance_summary.json
   └─ report.md
```
