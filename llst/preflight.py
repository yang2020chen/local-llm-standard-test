import os, sys, requests
from transformers import AutoTokenizer

def run_preflight(resolved_cfg, check_sandbox=True):
    errors = []
    warnings = []
    
    m = resolved_cfg["machine"]
    api_base = m["api_base"]
    api_key = m["api_key"]
    tok_path = m["tokenizer_path"]
    ctx_len = m["context_length"]
    
    # 1. API Connectivity Check
    models_url = f"{api_base.rstrip('/')}/models"
    headers = {"Authorization": f"Bearer {api_key}"} if api_key and api_key != "EMPTY" else {}
    try:
        resp = requests.get(models_url, headers=headers, timeout=5)
        if resp.status_code == 200:
            print(f"[PREFLIGHT PASS] API Endpoint reachable: {models_url} (HTTP 200)")
        else:
            errors.append(f"API Endpoint returned HTTP {resp.status_code}: {models_url}")
    except Exception as e:
        errors.append(f"Cannot connect to API endpoint {models_url}: {e}")

    # 2. Tokenizer Check
    if not os.path.exists(tok_path):
        errors.append(f"Tokenizer directory does not exist: {tok_path}")
    else:
        try:
            tok = AutoTokenizer.from_pretrained(tok_path, trust_remote_code=True)
            vocab = getattr(tok, "vocab_size", "unknown")
            print(f"[PREFLIGHT PASS] Tokenizer loaded successfully: class={tok.__class__.__name__}, vocab={vocab}")
        except Exception as e:
            errors.append(f"Failed to load tokenizer from {tok_path}: {e}")

    # 3. Context Length Threshold
    perf_lengths = resolved_cfg.get("performance", {}).get("prompt_lengths", [28672])
    perf_outtok = resolved_cfg.get("performance", {}).get("output_tokens", 512)
    max_isl = max(perf_lengths) if perf_lengths else 28672
    required_ctx = max_isl + perf_outtok
    if ctx_len < required_ctx:
        errors.append(f"Configured context_length ({ctx_len}) is below required minimum ({required_ctx}) for full LLST v1.0")
    else:
        print(f"[PREFLIGHT PASS] Context length ({ctx_len}) satisfies minimum requirement ({required_ctx})")

    # 4. Docker Sandbox Check
    sandbox_healthy = False
    try:
        import docker
        client = docker.from_env()
        if client.ping():
            sandbox_healthy = True
            print("[PREFLIGHT PASS] Docker daemon responsive and accessible")
    except Exception as e:
        warnings.append(f"Docker sandbox warning: {e}")

    # Check if LiveCodeBench requires sandbox
    benchmarks = resolved_cfg.get("capability", {}).get("benchmarks", [])
    lcb_requires_sandbox = any(b.get("name") == "live_code_bench" and b.get("sandbox", {}).get("enabled", False) for b in benchmarks)
    if lcb_requires_sandbox and not sandbox_healthy:
        errors.append("LiveCodeBench strictly requires Docker sandbox, but Docker daemon is inaccessible.")

    return len(errors) == 0, errors, warnings

if __name__ == "__main__":
    from llst.config_loader import load_resolved_config
    p_path = sys.argv[1] if len(sys.argv) > 1 else "configs/protocols/standard_test_v1.yaml"
    m_path = sys.argv[2] if len(sys.argv) > 2 else "configs/machines/machine.example.yaml"
    cfg = load_resolved_config(p_path, m_path)
    ok, errs, warns = run_preflight(cfg)
    if not ok:
        print(f"[PREFLIGHT FAILED] Errors: {errs}", file=sys.stderr)
        sys.exit(1)
    print("[PREFLIGHT ALL PASSED]")
