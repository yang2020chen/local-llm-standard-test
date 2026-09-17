#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "$PROJECT_ROOT"

PROTOCOL_PATH="configs/protocols/standard_test_v1.yaml"
MACHINE_PATH="configs/machines/machine.example.yaml"
if [[ -f "configs/machines/machine.local.yaml" ]]; then
  MACHINE_PATH="configs/machines/machine.local.yaml"
fi

CHECK_ONLY=false
DRY_RUN=false
SMOKE_MODE=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --protocol)
      PROTOCOL_PATH="$2"; shift 2 ;;
    --machine)
      MACHINE_PATH="$2"; shift 2 ;;
    --check|--preflight)
      CHECK_ONLY=true; shift ;;
    --dry-run)
      DRY_RUN=true; shift ;;
    --smoke)
      SMOKE_MODE=true; shift ;;
    *)
      echo "Unknown option: $1" >&2
      echo "Usage: $0 [--protocol <path>] [--machine <path>] [--check] [--dry-run] [--smoke]" >&2
      exit 1 ;;
  esac
done

export PYTHONPATH="${PROJECT_ROOT}:${PYTHONPATH:-}"

if [[ -z "${PYTHON:-}" ]]; then
  if [[ -n "${VIRTUAL_ENV:-}" && -x "${VIRTUAL_ENV}/bin/python3" ]]; then
    PYTHON="${VIRTUAL_ENV}/bin/python3"
  elif command -v evalscope >/dev/null 2>&1 && [[ -x "$(dirname "$(command -v evalscope)")/python3" ]]; then
    PYTHON="$(dirname "$(command -v evalscope)")/python3"
  elif [[ -x "$HOME/.venv-evalscope/bin/python3" ]]; then
    PYTHON="$HOME/.venv-evalscope/bin/python3"
  elif [[ -x "${PROJECT_ROOT}/.venv/bin/python3" ]]; then
    PYTHON="${PROJECT_ROOT}/.venv/bin/python3"
  else
    PYTHON="$(command -v python3 || echo python3)"
  fi
fi

if [[ -z "${EVALSCOPE:-}" ]]; then
  if [[ -x "$(dirname "$PYTHON")/evalscope" ]]; then
    EVALSCOPE="$(dirname "$PYTHON")/evalscope"
  else
    EVALSCOPE="$(command -v evalscope || echo evalscope)"
  fi
fi

echo "========================================================================"
echo " Local LLM Standard Test (LLST) Runner v1.0"
echo " Protocol: $PROTOCOL_PATH"
echo " Machine:  $MACHINE_PATH"
echo " Python:   $PYTHON"
echo "========================================================================"

# 1. Validate and Resolve Configuration
RESOLVED_JSON="$("$PYTHON" -m llst.config_loader "$PROTOCOL_PATH" "$MACHINE_PATH")"

# 2. Run Preflight Inspection
"$PYTHON" -m llst.preflight "$PROTOCOL_PATH" "$MACHINE_PATH"

# 3. Run Protocol Runtime Verification
"$PYTHON" -m llst.protocol_validator "$PROTOCOL_PATH" "$MACHINE_PATH"

if [[ "$CHECK_ONLY" == "true" ]]; then
  echo "[INFO] Preflight and Protocol validation passed successfully. Exiting (--check mode)."
  exit 0
fi

MODEL_NAME="$("$PYTHON" -c "import json, sys; print(json.loads(sys.argv[1])['machine']['model_name'])" "$RESOLVED_JSON")"
OUTPUT_ROOT="$("$PYTHON" -c "import json, sys; print(json.loads(sys.argv[1])['machine']['output_root'])" "$RESOLVED_JSON")"

RUN_ID="$(date +%Y%m%d_%H%M%S)"
RUN_DIR="${OUTPUT_ROOT}/${MODEL_NAME}/${RUN_ID}"
mkdir -p "$RUN_DIR"/{meta,capability,performance,logs,workload}

# Duplicate all subsequent outputs into $RUN_DIR/run.log
exec > >(tee -a "$RUN_DIR/run.log") 2>&1

echo "[INFO] Target Run Directory: $RUN_DIR"
echo "[INFO] Run log initialized: $RUN_DIR/run.log"
ln -sfn "$RUN_DIR/run.log" "${OUTPUT_ROOT}/${MODEL_NAME}/latest.log"
echo "$RESOLVED_JSON" > "$RUN_DIR/meta/resolved_config.json"

if [[ "$DRY_RUN" == "true" ]]; then
  echo "[INFO] DRY RUN MODE: Verifying Full Execution Graph & Generating Workload..."
  "$PYTHON" -c "
from llst.config_loader import load_resolved_config
from llst.performance.workload_generator import generate_workload_plan, save_workload_files

cfg = load_resolved_config('$PROTOCOL_PATH', '$MACHINE_PATH')
tok_path = cfg['machine']['tokenizer_path']
w = generate_workload_plan(tok_path, seed=20260917, prompt_lengths=[512, 4096, 16384, 28672], requests_per_length=2)
mf_path, mf = save_workload_files(w, '$RUN_DIR/workload')
print(f'[DRY RUN] Generated workload files for 4 tiers. Manifest: {mf_path}')
for length, d in mf['cases'].items():
    print(f'  • Tier ISL {length:5}: {d[\"file\"]} (sha256={d[\"sha256\"][:16]}...)')

benchmarks = cfg['capability']['benchmarks']
print(f'[DRY RUN] Planned Capability Benchmarks (Total 102 Questions):')
for b in benchmarks:
    print(f'  • {b[\"name\"]:16}: limit={b[\"limit\"]} ({b.get(\"label\", \"\")})')
"
  echo "[INFO] DRY RUN COMPLETED SUCCESSFULLY: All execution paths verified."
  exit 0
fi

if [[ "$SMOKE_MODE" == "true" ]]; then
  echo "[INFO] Executing in SMOKE mode (Minimal sanity validation)..."
  "$PYTHON" -c "
from llst.config_loader import load_resolved_config
from llst.capability.runner import run_capability_suite
from llst.performance.runner import run_performance_suite
from llst.report.aggregate import aggregate_run_reports

cfg = load_resolved_config('$PROTOCOL_PATH', '$MACHINE_PATH')
run_capability_suite(cfg, '$RUN_DIR', evalscope_bin='$EVALSCOPE', smoke=True)
run_performance_suite(cfg, '$RUN_DIR', evalscope_bin='$EVALSCOPE', smoke=True)
aggregate_run_reports('$RUN_DIR', cfg)
"
  echo "[INFO] Smoke run completed successfully! Run dir: $RUN_DIR"
  exit 0
fi

# Full Standard Test Mode
echo "========================================================================"
echo " STAGE 1: Capability Evaluation (102 Fixed Questions)"
echo "========================================================================"
"$PYTHON" -c "
from llst.config_loader import load_resolved_config
from llst.capability.runner import run_capability_suite

cfg = load_resolved_config('$PROTOCOL_PATH', '$MACHINE_PATH')
run_capability_suite(cfg, '$RUN_DIR', evalscope_bin='$EVALSCOPE', smoke=False)
"

echo "========================================================================"
echo " STAGE 2: Long-Context Performance Benchmark (4 Tiers × 2 Reqs)"
echo "========================================================================"
"$PYTHON" -c "
from llst.config_loader import load_resolved_config
from llst.performance.runner import run_performance_suite

cfg = load_resolved_config('$PROTOCOL_PATH', '$MACHINE_PATH')
run_performance_suite(cfg, '$RUN_DIR', evalscope_bin='$EVALSCOPE', smoke=False)
"

echo "========================================================================"
echo " STAGE 3: Final Aggregation & Report Generation"
echo "========================================================================"
"$PYTHON" -c "
from llst.config_loader import load_resolved_config
from llst.report.aggregate import aggregate_run_reports

cfg = load_resolved_config('$PROTOCOL_PATH', '$MACHINE_PATH')
aggregate_run_reports('$RUN_DIR', cfg)
"

echo "========================================================================"
echo " FULL STANDARD TEST COMPLETED SUCCESSFULLY"
echo " Results Directory: $RUN_DIR"
echo " Summary Report:    $RUN_DIR/report.md"
echo " Log File:          $RUN_DIR/run.log"
echo "========================================================================"
