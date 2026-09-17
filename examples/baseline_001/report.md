# LLST Standard Test Report: Qwen3.8-Flash-Next

- Protocol Version: 1.0
- Execution Run: 20260917_125320

## Capability Summary

| Benchmark | Score | Samples |
| :--- | :---: | :---: |
| aime24 | 0.3 | 10 |
| ifeval | 0.95 | 20 |
| ceval | 0.9 | 20 |
| mmlu_pro | 0.8571 | 42 |
| live_code_bench | 0.8 | 10 |

## Performance Summary

| Workload Case | Avg TTFT (ms) | Avg TPOT (ms) | Output Throughput (tok/s) | Spec Accept Rate |
| :---: | :---: | :---: | :---: | :---: |
| isl_16384_osl_512 | 22128.1 | 42.24 | 9.4611 | 0.012 |
| isl_28672_osl_512 | 40937.79 | 41.67 | 7.2943 | 0.0024 |
| isl_4096_osl_512 | 5307.14 | 57.75 | 16.2629 | 0.5 |
| isl_512_osl_512 | 1280.09 | 57.52 | 22.6377 | None |
