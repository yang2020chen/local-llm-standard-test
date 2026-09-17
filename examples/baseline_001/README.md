# LLST Baseline #001: Qwen3.8-Flash-Next on Dual RX 7900 XTX

> **Status: VERIFIED STABLE (v1.0.0)**
> Full 102-question capability evaluation and 4-tier long-context performance benchmark executed with complete end-to-end cryptographic closure (`manifest_sha256 == resolved_sha256 == executed_sha256`).

## Overview
This directory contains the sanitized, reproducible baseline configuration and audited benchmark results for **LLST v1.0** evaluated on **Qwen3.8-Flash-Next (UD-Q3_K_XL)** with speculative MTP decoding on dual AMD Radeon RX 7900 XTX (48GB VRAM).

## Hardware & Inference Stack
- **GPUs**: 2x AMD Radeon RX 7900 XTX (24GB GDDR6 each, total 48GB VRAM)
- **Host**: AMD Ryzen 9 7950X, 128GB DDR5 RAM, Ubuntu 24.04 LTS
- **ROCm**: ROCm 6.3.2 / gfx1100
- **Engine**: llama.cpp (`llama-server` with FlashAttention, MTP draft model, Q8_0 KV-cache, context length 32768)

## Stage 1: Capability Summary (102 Pinned Questions)

| Benchmark | Domain | Score | Sample Count | Evaluation Method |
| :--- | :--- | :---: | :---: | :--- |
| **IFEval** | Instruction Following | **95.0%** | 20 | Native Prompt / Inst Strict & Loose Metric |
| **CEval** | Chinese Knowledge & Reasoning | **90.0%** | 20 | 20 Subjects (5-shot dev) |
| **MMLU-Pro** | Reasoning & Knowledge | **85.7%** | 42 | 14 Categories (5-shot validation) |
| **LiveCodeBench** | Coding & Execution | **80.0%** | 10 | Docker Sandbox Pass@1 (release_latest) |
| **AIME24** | Advanced Math Reasoning | **30.0%** | 10 | Strict Numeric Extraction |
| **Overall** | **All 5 Domains** | **Verified** | **102 / 102** | **100% Cryptographic Match** |

## Stage 2: Performance Summary (4 Tiers, Seed 20260917)

| Workload Case | Input Length (ISL) | Output Tokens (OSL) | Avg TTFT (ms) | Avg TPOT (ms) | Throughput (tok/s) | Spec Accept Rate |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Tier 1** | 512 | 512 | 1,280.09 | 57.52 | 22.64 | N/A |
| **Tier 2** | 4,096 | 512 | 5,307.14 | 57.75 | 16.26 | 50.0% |
| **Tier 3** | 16,384 | 512 | 22,128.10 | 42.24 | 9.46 | 1.2% |
| **Tier 4** | 28,672 | 512 | 40,937.79 | 41.67 | 7.29 | 0.24% |

## Verification Manifests
- `execution_manifest.json`: Verification record confirming all 102 target samples matched output predictions.
- `workload_manifest.json`: SHA256 hashes of deterministic token stress workloads for all 4 tiers.
- `tokenizer_fingerprint.json`: Cryptographic vocabulary and behavioral encoding fingerprint.
