import hashlib
import json
import os
import sys
import numpy as np
from transformers import AutoTokenizer

def generate_workload_plan(
    tokenizer_path, seed=20260917, prompt_lengths=None, requests_per_length=2, trust_remote_code=False
):
    if prompt_lengths is None:
        prompt_lengths = [512, 4096, 16384, 28672]

    # Explicitly set random seed for numpy
    np.random.seed(seed)

    tok = AutoTokenizer.from_pretrained(tokenizer_path, trust_remote_code=trust_remote_code)
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

def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as workload_file:
        for chunk in iter(lambda: workload_file.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_workload_manifest(manifest, target_dir):
    """Verify the exact JSONL bytes that EvalScope will consume."""
    cases = manifest.get("cases")
    if not isinstance(cases, dict) or not cases:
        raise RuntimeError("WORKLOAD_MANIFEST_INVALID: cases must be a non-empty mapping")

    verified = {}
    for length, case in cases.items():
        if not isinstance(case, dict):
            raise RuntimeError(f"WORKLOAD_MANIFEST_INVALID: case {length} is not a mapping")
        filename = case.get("file")
        expected_hash = case.get("sha256")
        expected_count = case.get("requests_count")
        expected_length = case.get("prompt_length")
        if not isinstance(filename, str) or os.path.basename(filename) != filename:
            raise RuntimeError(f"WORKLOAD_MANIFEST_INVALID: unsafe filename for case {length}")
        if not isinstance(expected_hash, str) or len(expected_hash) != 64:
            raise RuntimeError(f"WORKLOAD_MANIFEST_INVALID: missing SHA-256 for case {length}")

        path = os.path.join(target_dir, filename)
        if not os.path.isfile(path):
            raise RuntimeError(f"WORKLOAD_FILE_MISSING: {path}")
        actual_hash = sha256_file(path)
        if actual_hash != expected_hash:
            raise RuntimeError(f"WORKLOAD_FILE_MISMATCH: {path} expected {expected_hash}, got {actual_hash}")

        records = 0
        with open(path, "r", encoding="utf-8") as workload_file:
            for line_number, line in enumerate(workload_file, start=1):
                token_ids = json.loads(line)
                if not isinstance(token_ids, list) or not all(isinstance(token, int) for token in token_ids):
                    raise RuntimeError(f"WORKLOAD_FILE_INVALID: {path}:{line_number} is not a token-ID list")
                if len(token_ids) != expected_length:
                    raise RuntimeError(
                        f"WORKLOAD_FILE_INVALID: {path}:{line_number} has {len(token_ids)} tokens, expected {expected_length}"
                    )
                records += 1
        if records != expected_count:
            raise RuntimeError(f"WORKLOAD_FILE_INVALID: {path} has {records} requests, expected {expected_count}")
        verified[str(length)] = {"path": path, "sha256": actual_hash, "requests_count": records}
    return verified


def save_workload_files(workload, target_dir, seed=20260917):
    os.makedirs(target_dir, exist_ok=True)
    manifest = {
        "generator_version": "1.1",
        "seed": seed,
        "cases": {}
    }
    for length, data in workload.items():
        fname = f"workload_isl_{length}.jsonl"
        fpath = os.path.join(target_dir, fname)
        with open(fpath, "w", encoding="utf-8") as f:
            for req_tokens in data["requests"]:
                f.write(json.dumps(req_tokens, separators=(",", ":")) + "\n")
        manifest["cases"][str(length)] = {
            "file": fname,
            "path": fpath,
            "sha256": sha256_file(fpath),
            "requests_count": data["requests_count"],
            "prompt_length": length
        }
    manifest_path = os.path.join(target_dir, "workload_manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    verify_workload_manifest(manifest, target_dir)
    return manifest_path, manifest

if __name__ == "__main__":
    tok_path = sys.argv[1] if len(sys.argv) > 1 else "./tokenizer"
    w = generate_workload_plan(tok_path)
    for length, data in w.items():
        print(f"ISL {length:5}: sha256={data['sha256']}")
