#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "$PROJECT_ROOT"

PROTOCOL_PATH="configs/protocols/standard_test_v1.yaml"
MACHINE_PATH="configs/machines/machine.example.yaml"
CAPABILITY_RUN=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --protocol) PROTOCOL_PATH="$2"; shift 2 ;;
    --machine) MACHINE_PATH="$2"; shift 2 ;;
    --capability-run) CAPABILITY_RUN="$2"; shift 2 ;;
    *)
      echo "Usage: $0 --machine <profile> --capability-run <completed-run> [--protocol <path>]" >&2
      exit 1 ;;
  esac
done

if [[ -z "$CAPABILITY_RUN" || ! -f "$CAPABILITY_RUN/capability/execution_manifest.json" ]]; then
  echo "A completed capability run with capability/execution_manifest.json is required." >&2
  exit 1
fi

export PYTHONPATH="${PROJECT_ROOT}:${PYTHONPATH:-}"
if [[ -z "${PYTHON:-}" ]]; then
  if [[ -x "$HOME/.venv-evalscope/bin/python3" ]]; then
    PYTHON="$HOME/.venv-evalscope/bin/python3"
  else
    PYTHON="$(command -v python3)"
  fi
fi
if [[ -z "${EVALSCOPE:-}" ]]; then
  EVALSCOPE="$(dirname "$PYTHON")/evalscope"
fi

"$PYTHON" -m llst.preflight "$PROTOCOL_PATH" "$MACHINE_PATH"
"$PYTHON" -m llst.protocol_validator "$PROTOCOL_PATH" "$MACHINE_PATH"

RESOLVED_JSON="$("$PYTHON" -m llst.config_loader "$PROTOCOL_PATH" "$MACHINE_PATH")"
MODEL_NAME="$("$PYTHON" -c "import json, sys; print(json.loads(sys.argv[1])['machine']['model_name'])" "$RESOLVED_JSON")"
OUTPUT_ROOT="$("$PYTHON" -c "import json, sys; print(json.loads(sys.argv[1])['machine']['output_root'])" "$RESOLVED_JSON")"
RUN_DIR="${OUTPUT_ROOT}/${MODEL_NAME}/$(date +%Y%m%d_%H%M%S)_performance_retest"
mkdir -p "$RUN_DIR"/{meta,performance,logs,workload}
printf '%s\n' "$RESOLVED_JSON" > "$RUN_DIR/meta/resolved_config.json"

"$PYTHON" - "$PROTOCOL_PATH" "$MACHINE_PATH" "$RUN_DIR" "$CAPABILITY_RUN" "$EVALSCOPE" <<'PY'
import hashlib
import json
import os
import sys
from pathlib import Path

from llst.config_loader import load_resolved_config
from llst.environment import write_environment_record
from llst.performance.runner import run_performance_suite, verify_performance_execution_manifest

protocol_path, machine_path, run_dir, capability_run, evalscope_bin = sys.argv[1:]
cfg = load_resolved_config(protocol_path, machine_path)
write_environment_record(run_dir, cfg, evalscope_bin=evalscope_bin)
run_performance_suite(cfg, run_dir, evalscope_bin=evalscope_bin, smoke=False)
performance = verify_performance_execution_manifest(run_dir)

capability_path = Path(capability_run) / "capability" / "execution_manifest.json"
capability = json.loads(capability_path.read_text(encoding="utf-8"))
if capability.get("total_executed") != 102 or capability.get("smoke") is not False:
    raise RuntimeError("CAPABILITY_REFERENCE_INVALID: reference is not a complete 102-sample run")

def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        for chunk in iter(lambda: source.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()

reference = {
    "schema_version": "1.0",
    "capability_run": str(Path(capability_run).resolve()),
    "capability_execution_manifest": {
        "path": "capability/execution_manifest.json",
        "sha256": sha256_file(capability_path),
        "total_executed": capability["total_executed"],
    },
    "performance_execution_manifest": {
        "path": "performance/execution_manifest.json",
        "sha256": sha256_file(Path(run_dir) / "performance" / "execution_manifest.json"),
        "ignore_eos": performance["ignore_eos"],
        "cases": sorted(performance["cases"]),
    },
}
reference_path = Path(run_dir) / "capability_reference.json"
reference_path.write_text(json.dumps(reference, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

report = Path(run_dir) / "report.md"
report.write_text(
    "# LLST Corrected Performance Retest\n\n"
    "This run reuses the referenced, complete capability execution and reruns only performance.\n\n"
    f"- Capability manifest SHA-256: `{reference['capability_execution_manifest']['sha256']}`\n"
    f"- Performance manifest SHA-256: `{reference['performance_execution_manifest']['sha256']}`\n"
    f"- `ignore_eos`: `{reference['performance_execution_manifest']['ignore_eos']}`\n",
    encoding="utf-8",
)
print(f"[INFO] Corrected performance retest complete: {run_dir}")
PY
