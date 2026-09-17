# Phase 0: repair baseline

Recorded on 2026-09-17 before implementing the v1.0.1 integrity fixes.

## Source baseline

- Upstream source commit: `ca80c4d40c27d0b54550fd76c43ac3f947cd8d9c`.
- Repair branch: `codex/llst-v1.0.1-integrity`.
- The deployment at `192.168.0.110:/home/xin/local-llm-standard-test` is a packaged copy, not a Git checkout.
- Excluding runtime-only files (`machine.local.yaml`, `outputs/`, and Python bytecode), the deployed source files matched the source baseline at the time of this audit.

## Deployment observations

- Docker, the model service, tokenizer, and all five dataset snapshot hashes were available on the deployment host.
- The deployment's non-interactive environment did not provide `LLST_API_KEY`; `./scripts/run_standard_test.sh --check` therefore received HTTP 401 from the local model endpoint.
- The current machine profile resolves both its tokenizer and tokenizer fingerprint paths.

## Run status

`outputs/Qwen3.8-Flash-Next/20260917_125320` must not be described as a completed, verified LLST run:

- Its `run.log` ends with `PROTOCOL_EXECUTION_MISMATCH` for `aime24/default/60`.
- It has no `FULL STANDARD TEST COMPLETED SUCCESSFULLY` marker.
- The execution manifest was written after the log's failure timestamp and does not hash the raw prediction files.
- The workload manifest hashes do not equal the bytes of the four JSONL workload files.

Retain the directory for debugging. Do not delete, modify, or publish it as a verified baseline. A new run ID is required after the integrity fixes land.
