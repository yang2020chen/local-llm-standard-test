import os, sys, yaml, json

def load_resolved_config(protocol_path, machine_path):
    if not os.path.exists(protocol_path):
        raise FileNotFoundError(f"Protocol file not found: {protocol_path}")
    if not os.path.exists(machine_path):
        raise FileNotFoundError(f"Machine profile not found: {machine_path}")

    with open(protocol_path, "r", encoding="utf-8") as f:
        protocol = yaml.safe_load(f)
    with open(machine_path, "r", encoding="utf-8") as f:
        machine = yaml.safe_load(f)

    # API key resolution: check environment variable specified in machine profile
    api_key_env = machine.get("api", {}).get("api_key_env", "LLST_API_KEY")
    api_key = os.environ.get(api_key_env, machine.get("api", {}).get("api_key", "EMPTY"))

    # Resolve output directory
    output_root = machine.get("output", {}).get("root", "./outputs")
    output_root = os.path.abspath(output_root)

    merged = {
        "protocol": protocol.get("protocol", {}),
        "capability": protocol.get("capability", {}),
        "performance": protocol.get("performance", {}),
        "machine": {
            "model_name": machine.get("model", {}).get("name", "llm-model"),
            "backend": machine.get("model", {}).get("backend", "generic"),
            "api_base": machine.get("api", {}).get("base_url", "http://127.0.0.1:8000/v1"),
            "perf_url": machine.get("api", {}).get("perf_url", "http://127.0.0.1:8000/v1/completions"),
            "api_key": api_key,
            "api_key_env": api_key_env,
            "tokenizer_path": os.path.abspath(machine.get("tokenizer", {}).get("path", "./tokenizer")),
            "context_length": int(machine.get("runtime", {}).get("context_length", 32768)),
            "output_root": output_root
        },
        "meta": {
            "protocol_path": os.path.abspath(protocol_path),
            "machine_path": os.path.abspath(machine_path)
        }
    }
    return merged

if __name__ == "__main__":
    p_path = sys.argv[1] if len(sys.argv) > 1 else "configs/protocols/standard_test_v1.yaml"
    m_path = sys.argv[2] if len(sys.argv) > 2 else "configs/machines/machine.example.yaml"
    cfg = load_resolved_config(p_path, m_path)
    print(json.dumps(cfg, indent=2))
