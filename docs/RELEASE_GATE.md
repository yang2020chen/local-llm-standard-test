# LLST release gate

A release is publishable only when all of the following are true:

1. The CI `Integrity gates` workflow passes on the exact release commit.
2. A new run directory passes preflight, protocol validation, capability execution, performance execution, and report aggregation without any `*_MISMATCH`, `*_MISSING`, or reuse error.
3. The run contains `capability/execution_manifest.json` and `performance/execution_manifest.json`; their referenced workload, prediction, SQLite, percentile, summary, and argument artifacts hash-match on disk.
4. The run's `environment.json` identifies the model file hash, tokenizer fingerprint, service version, context length, cache precision, and GPU allocation.
5. A maintainer creates an annotated and cryptographically signed Git tag pointing at that verified commit. The public report cites that tag and the execution-manifest hashes.

The Phase 0 baseline is retained as an audit artifact, not a release candidate: it predates the execution-artifact and fail-closed gates.
