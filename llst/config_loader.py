import copy
import json
import os
import sys

import yaml


class ConfigError(ValueError):
    """Raised when a machine profile cannot safely run LLST."""


def _require_mapping(data, path):
    if not isinstance(data, dict):
        raise ConfigError(f"CONFIG_INVALID: {path} must be a mapping")
    return data


def _require_string(data, path):
    if not isinstance(data, str) or not data.strip():
        raise ConfigError(f"CONFIG_MISSING: {path} must be a non-empty string")
    return data.strip()


def _load_yaml(path, label):
    if not os.path.exists(path):
        raise FileNotFoundError(f"{label} file not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return _require_mapping(yaml.safe_load(f) or {}, label)


def load_resolved_config(protocol_path, machine_path):
    protocol = _load_yaml(protocol_path, "Protocol")
    machine = _load_yaml(machine_path, "Machine profile")

    model = _require_mapping(machine.get("model"), "model")
    api = _require_mapping(machine.get("api"), "api")
    tokenizer = _require_mapping(machine.get("tokenizer"), "tokenizer")
    runtime = _require_mapping(machine.get("runtime"), "runtime")
    output = _require_mapping(machine.get("output"), "output")

    model_name = _require_string(model.get("name"), "model.name")
    api_base = _require_string(api.get("base_url"), "api.base_url").rstrip("/")
    perf_url = _require_string(api.get("perf_url"), "api.perf_url")
    api_key_env = _require_string(api.get("api_key_env"), "api.api_key_env")
    tokenizer_path = _require_string(tokenizer.get("path"), "tokenizer.path")
    fingerprint_path = _require_string(tokenizer.get("fingerprint"), "tokenizer.fingerprint")
    output_root = _require_string(output.get("root"), "output.root")

    try:
        context_length = int(runtime.get("context_length"))
    except (TypeError, ValueError) as exc:
        raise ConfigError("CONFIG_INVALID: runtime.context_length must be an integer") from exc
    if context_length <= 0:
        raise ConfigError("CONFIG_INVALID: runtime.context_length must be positive")

    # Keep credentials in memory only. The command-line JSON representation below
    # is redacted before the runner persists it to a run directory.
    api_key = os.environ.get(api_key_env)
    return {
        "protocol": protocol.get("protocol", {}),
        "capability": protocol.get("capability", {}),
        "performance": protocol.get("performance", {}),
        "machine": {
            "model_name": model_name,
            "backend": model.get("backend", "generic"),
            "model_file": model.get("file"),
            "api_base": api_base,
            "perf_url": perf_url,
            "api_key": api_key,
            "api_key_env": api_key_env,
            "tokenizer_path": os.path.abspath(tokenizer_path),
            "tokenizer_fingerprint": os.path.abspath(fingerprint_path),
            "tokenizer_trust_remote_code": bool(tokenizer.get("trust_remote_code", False)),
            "context_length": context_length,
            "kv_cache_type": runtime.get("kv_cache_type"),
            "gpu_allocation": runtime.get("gpu_allocation"),
            "service_name": runtime.get("service_name"),
            "output_root": os.path.abspath(output_root),
        },
        "meta": {
            "protocol_path": os.path.abspath(protocol_path),
            "machine_path": os.path.abspath(machine_path),
        },
    }


def redacted_config(resolved_cfg):
    """Return a copy that is safe to store in output metadata and logs."""
    safe_cfg = copy.deepcopy(resolved_cfg)
    safe_cfg["machine"]["api_key"] = "<redacted>" if safe_cfg["machine"].get("api_key") else None
    return safe_cfg


if __name__ == "__main__":
    p_path = sys.argv[1] if len(sys.argv) > 1 else "configs/protocols/standard_test_v1.yaml"
    m_path = sys.argv[2] if len(sys.argv) > 2 else "configs/machines/machine.example.yaml"
    cfg = load_resolved_config(p_path, m_path)
    print(json.dumps(redacted_config(cfg), indent=2))
