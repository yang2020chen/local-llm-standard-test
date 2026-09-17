#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "$PROJECT_ROOT"

echo "========================================================================"
echo " Local LLM Standard Test (LLST) Environment Setup"
echo "========================================================================"

# 1. Check Python
PYTHON_BIN=""
for cand in python3.12 python3.11 python3.10 python3; do
  if command -v "$cand" >/dev/null 2>&1; then
    ver=$("$cand" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    major=$(echo "$ver" | cut -d. -f1)
    minor=$(echo "$ver" | cut -d. -f2)
    if [[ "$major" -eq 3 && "$minor" -ge 10 ]]; then
      PYTHON_BIN="$(command -v "$cand")"
      echo "[OK] Found compatible Python: $PYTHON_BIN (v$ver)"
      break
    fi
  fi
done

if [[ -z "$PYTHON_BIN" ]]; then
  echo "[ERROR] Python >= 3.10 is required. Please install Python 3.10, 3.11, or 3.12." >&2
  exit 1
fi

# 2. Virtual Environment
VENV_DIR="${PROJECT_ROOT}/.venv"
if [[ ! -d "$VENV_DIR" ]]; then
  echo "[INFO] Creating virtual environment at $VENV_DIR..."
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

echo "[INFO] Activating virtual environment..."
# shellcheck disable=SC1091
source "${VENV_DIR}/bin/activate"

# 3. Upgrade pip and install dependencies
echo "[INFO] Installing dependencies from requirements.txt..."
pip install --upgrade pip
pip install -r "${PROJECT_ROOT}/requirements.txt"

# 4. Check Docker daemon (Required for LiveCodeBench sandbox)
if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
  echo "[OK] Docker daemon is running and accessible."
else
  echo "[WARNING] Docker daemon is not accessible. Note that LiveCodeBench evaluation requires Docker sandbox isolation."
fi

echo "========================================================================"
echo " LLST Environment Installation Complete!"
echo " Next steps:"
echo " 1. Copy config: cp configs/machines/machine.example.yaml configs/machines/machine.local.yaml"
echo " 2. Configure endpoint & API key in machine.local.yaml"
echo " 3. Run preflight check: ./scripts/run_standard_test.sh --check"
echo "========================================================================"
