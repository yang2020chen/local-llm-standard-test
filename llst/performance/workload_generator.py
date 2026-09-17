import os, sys, json, hashlib
import numpy as np
from transformers import AutoTokenizer

def generate_workload_plan(tokenizer_path, seed=20260917, prompt_lengths=None, requests_per_length=2):
    if prompt_lengths is None:
        prompt_lengths = [512, 4096, 16384, 28672]

    # Explicitly set random seed for numpy
    np.random.seed(seed)

    tok = AutoTokenizer.from_pretrained(tokenizer_path, trust_remote_code=True)
    vocab_size = getattr(tok, "vocab_size", 248044)
    # Range of allowed tokens excluding control/special tokens
    allowed_tokens = np.arange(100, vocab_size - 100, dtype=np.int64)

    workload = {}
    for length in prompt_lengths:
        case_requests = []
        for req_idx in range(requests_per_length):
            # Deterministic selection of tokens
            tokens = np.random.choice(allowed_tokens, size=length, replace=True).tolist()
            case_requests.append(tokens)

        payload_bytes = json.dumps(case_requests, separators=(",", ":")).encode("utf-8")
        h = hashlib.sha256(payload_bytes).hexdigest()
        workload[length] = {
            "prompt_length": length,
            "requests": case_requests,
            "requests_count": requests_per_length,
            "sha256": h
        }
    return workload

def save_workload_files(workload, target_dir):
    os.makedirs(target_dir, exist_ok=True)
    manifest = {
        "generator_version": "1.0",
        "seed": 20260917,
        "cases": {}
    }
    for length, data in workload.items():
        fname = f"workload_isl_{length}.jsonl"
        fpath = os.path.join(target_dir, fname)
        with open(fpath, "w", encoding="utf-8") as f:
            for req_tokens in data["requests"]:
                f.write(json.dumps(req_tokens) + "\n")
        manifest["cases"][str(length)] = {
            "file": fname,
            "path": fpath,
            "sha256": data["sha256"],
            "requests_count": data["requests_count"],
            "prompt_length": length
        }
    manifest_path = os.path.join(target_dir, "workload_manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    return manifest_path, manifest

if __name__ == "__main__":
    tok_path = sys.argv[1] if len(sys.argv) > 1 else "./tokenizer"
    w = generate_workload_plan(tok_path)
    for length, data in w.items():
        print(f"ISL {length:5}: sha256={data['sha256']}")
