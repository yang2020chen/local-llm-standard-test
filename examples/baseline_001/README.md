# LLST Baseline #001: Qwen3.8-Flash-Next on Dual RX 7900 XTX

> **Status: VALIDATING (Release Candidate v1.0.0-rc1)**
> Full baseline verification run (102 capability questions + 4-tier performance load) is currently in flight. Final audited metrics and signatures will be populated upon completion.

## Overview
This directory contains the sanitized, reproducible baseline configuration and preliminary results for **LLST v1.0** evaluated on **Qwen3.8-Flash-Next (UD-Q3_K_XL)** with speculative MTP decoding on dual AMD Radeon RX 7900 XTX (48GB VRAM).

## Files
- `protocol.json`: Formal metadata of the LLST v1.0 protocol.
- `environment.example.json`: Host hardware, ROCm driver, and llama-server inference parameters.
- `tokenizer_fingerprint.json`: Cryptographic SHA256 fingerprint of vocabulary files and sample encoding.
- `capability_summary.json`: Detailed accuracy scores across the 102 capability questions.
- `performance_summary.json`: TTFT, TPOT, and throughput across 512, 4096, 16384, and 28672 input lengths.
- `report.md`: Markdown summary report of the baseline run.

## Hardware & Inference Setup
- **GPUs**: 2x AMD Radeon RX 7900 XTX (24GB GDDR6 each, total 48GB VRAM)
- **Host**: AMD Ryzen 9 7950X, 128GB DDR5 RAM, Ubuntu 24.04 LTS
- **ROCm**: ROCm 6.3.2 / gfx1100
- **Engine**: llama.cpp (llama-server with FlashAttention, MTP draft model, Q8_0 KV-cache)
