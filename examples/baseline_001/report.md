# LLST Benchmark Report: Baseline #001

- **Model**: Qwen3.8-Flash-Next (UD-Q3_K_XL)
- **Engine**: llama-server with MTP speculative draft
- **Hardware**: Dual AMD Radeon RX 7900 XTX (48GB total VRAM)
- **Protocol**: LLST Standard Test v1.0

## 1. Capability Results (102 Questions)
| Benchmark | Domain / Focus | Samples | Accuracy / Metric |
| :--- | :--- | :---: | :---: |
| **MMLU-Pro** | Comprehensive Reasoning | 42 | Available in `capability_summary.json` |
| **IFEval** | Instruction Following | 20 | Available in `capability_summary.json` |
| **AIME-2024** | Olympiad Mathematics | 10 | Available in `capability_summary.json` |
| **C-Eval** | Chinese Academic Knowledge | 20 | Available in `capability_summary.json` |
| **LiveCodeBench** | Python Code Generation (Sandbox) | 10 | Available in `capability_summary.json` |

## 2. Performance Results (Standardized Random Token Load)
| Input Length (ISL) | Output Length (OSL) | Concurrency | Avg TTFT (ms) | Avg TPOT (ms) | Output Throughput (tok/s) | MTP Accept Rate |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **512** | 512 | 1 | 1242.1 | 35.4 | 26.5 | 31.1% |
| **4096** | 512 | 1 | 2470.9 | 36.1 | 26.1 | 30.8% |
| **16384** | 512 | 1 | 7416.7 | 37.8 | 25.0 | 30.5% |
| **28672** | 512 | 1 | 14890.3 | 40.2 | 23.9 | 29.8% |
