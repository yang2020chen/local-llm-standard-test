"""Create a redacted, hash-backed environment record for each LLST run."""

import hashlib
import json
import os
import platform
import subprocess
import sys


def _sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as artifact_file:
        for chunk in iter(lambda: artifact_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _command_version(command):
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=10, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    output = (completed.stdout or completed.stderr).strip().splitlines()
    return output[0] if output else None


def write_environment_record(run_dir, resolved_cfg, evalscope_bin="evalscope"):
    """Persist runtime identity without credentials or environment-variable values."""
    machine = resolved_cfg["machine"]
    model_file = machine.get("model_file")
    record = {
        "model": {
            "name": machine["model_name"],
            "backend": machine["backend"],
            "file": os.path.abspath(model_file) if isinstance(model_file, str) and model_file else None,
            "sha256": None,
        },
        "tokenizer": {
            "fingerprint_file": machine["tokenizer_fingerprint"],
            "fingerprint_sha256": _sha256_file(machine["tokenizer_fingerprint"])
            if os.path.isfile(machine["tokenizer_fingerprint"])
            else None,
        },
        "runtime": {
            "context_length": machine["context_length"],
            "kv_cache_type": machine.get("kv_cache_type"),
            "gpu_allocation": machine.get("gpu_allocation"),
            "service_name": machine.get("service_name"),
            "service_version": machine.get("service_version"),
        },
        "software": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "evalscope": _command_version([evalscope_bin, "--version"]),
        },
    }
    if record["model"]["file"]:
        if not os.path.isfile(record["model"]["file"]):
            raise RuntimeError(f"MODEL_FILE_MISSING: {record['model']['file']}")
        record["model"]["sha256"] = _sha256_file(record["model"]["file"])

    output_path = os.path.join(run_dir, "meta", "environment.json")
    with open(output_path, "w", encoding="utf-8") as environment_file:
        json.dump(record, environment_file, indent=2, ensure_ascii=False)
    return output_path, record
