import os, sys, json, yaml, hashlib, glob
from transformers import AutoTokenizer
from llst.capability.sample_resolver import resolve_all_pinned_samples

def compute_dataset_snapshot_hash(dataset_dir_name):
    cache_root = os.environ.get("MODELSCOPE_CACHE", os.path.expanduser("~/.cache/modelscope/hub/datasets"))
    p = os.path.join(cache_root, dataset_dir_name)
    arrows = sorted(glob.glob(f"{p}/**/*.arrow", recursive=True))
    if not arrows:
        return None
    combined_hash = hashlib.sha256()
    for a in arrows:
        with open(a, "rb") as af:
            while chunk := af.read(65536):
                combined_hash.update(chunk)
    return combined_hash.hexdigest()

def validate_runtime_protocol(protocol_path, machine_path, project_root=None):
    if project_root is None:
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

    # 1. Load Protocol & Machine Config
    with open(protocol_path, "r", encoding="utf-8") as f:
        protocol = yaml.safe_load(f)
    with open(machine_path, "r", encoding="utf-8") as f:
        machine = yaml.safe_load(f)

    if protocol.get("protocol", {}).get("version") != "1.0":
        raise ValueError("Invalid protocol version. Expected '1.0'")

    # 2. Check Dataset Snapshot Hashes
    ds_manifest_rel = protocol.get("capability", {}).get("dataset_manifest", "v1/dataset_manifest.json")
    ds_manifest_path = os.path.join(os.path.dirname(protocol_path), ds_manifest_rel)
    with open(ds_manifest_path, "r", encoding="utf-8") as f:
        ds_meta = json.load(f)

    dir_map = {
        "mmlu_pro": "TIGER-Lab___mmlu-pro",
        "ifeval": "opencompass___ifeval",
        "aime24": "evalscope___aime24",
        "ceval": "evalscope___ceval",
        "live_code_bench": "evalscope___livecodebench_code_generation_lite_parquet"
    }

    for bm, dirname in dir_map.items():
        expected_snap = ds_meta["benchmarks"][bm].get("dataset_snapshot_sha256")
        actual_snap = compute_dataset_snapshot_hash(dirname)
        if expected_snap and actual_snap and expected_snap != actual_snap:
            print(f"[ERROR] Snapshot hash mismatch for {bm}! Expected {expected_snap}, got {actual_snap}", file=sys.stderr)
            raise RuntimeError(f"DATASET_SNAPSHOT_MISMATCH: {bm} arrow snapshot hash changed")

    print("DATASET_SNAPSHOT_PASS")

    # 3. Deep Validate 102 Samples via Shared Sample Resolver
    res = resolve_all_pinned_samples(protocol_path, machine_path, check_hashes=True)
    counts = res["counts"]
    target_counts = {"mmlu_pro": 42, "ifeval": 20, "aime24": 10, "ceval": 20, "live_code_bench": 10}

    print(f"MMLU-Pro      {counts['mmlu_pro']}/{target_counts['mmlu_pro']} VERIFIED")
    print(f"IFEval        {counts['ifeval']}/{target_counts['ifeval']} VERIFIED")
    print(f"AIME24        {counts['aime24']}/{target_counts['aime24']} VERIFIED")
    print(f"CEval         {counts['ceval']}/{target_counts['ceval']} VERIFIED")
    print(f"LiveCodeBench {counts['live_code_bench']}/{target_counts['live_code_bench']} VERIFIED")
    total_verified = res["total"]
    print(f"TOTAL         {total_verified}/102 VERIFIED")

    if total_verified != 102:
        raise RuntimeError(f"PROTOCOL_SAMPLE_MISMATCH: Total verified {total_verified} != 102")

    # 4. Tokenizer Fingerprint Gate
    tok_info = machine.get("tokenizer", {})
    tok_path = tok_info.get("path", "./tokenizer")
    if not os.path.isabs(tok_path):
        tok_path = os.path.join(project_root, tok_path)

    fp_path = tok_info.get("fingerprint")
    if fp_path:
        if not os.path.isabs(fp_path):
            fp_path = os.path.join(project_root, fp_path)
        if not os.path.exists(fp_path):
            raise RuntimeError(f"TOKENIZER_FINGERPRINT_MISMATCH: Fingerprint file not found at {fp_path}")

        with open(fp_path, "r", encoding="utf-8") as f:
            fp_expected = json.load(f)

        tok = AutoTokenizer.from_pretrained(tok_path, trust_remote_code=True)
        if tok.__class__.__name__ != fp_expected.get("tokenizer_class"):
            raise RuntimeError("TOKENIZER_FINGERPRINT_MISMATCH: Tokenizer class mismatch")
        if getattr(tok, "vocab_size", 0) != fp_expected.get("vocab_size"):
            raise RuntimeError("TOKENIZER_FINGERPRINT_MISMATCH: Tokenizer vocab size mismatch")

        for fname, fmeta in fp_expected.get("files", {}).items():
            real_file = os.path.join(tok_path, fname)
            if not os.path.exists(real_file):
                real_file = os.path.join(os.path.realpath(tok_path), fname)
            if not os.path.exists(real_file):
                raise RuntimeError(f"TOKENIZER_FINGERPRINT_MISMATCH: File {fname} missing from tokenizer")
            with open(real_file, "rb") as rf:
                h = hashlib.sha256(rf.read()).hexdigest()
            if h != fmeta["sha256"]:
                raise RuntimeError(f"TOKENIZER_FINGERPRINT_MISMATCH: File {fname} hash mismatch")

        b_spec = fp_expected.get("behavioral_verification", {})
        if b_spec.get("sample_input"):
            token_ids = tok.encode(b_spec["sample_input"])
            token_hash = hashlib.sha256(str(token_ids).encode("utf-8")).hexdigest()
            if token_hash != b_spec.get("token_ids_sha256"):
                raise RuntimeError("TOKENIZER_FINGERPRINT_MISMATCH: Behavioral token sequence SHA256 mismatch")

        print("TOKENIZER_FINGERPRINT_PASS")

    print("PROTOCOL_VERIFICATION_PASS")
    return res

if __name__ == "__main__":
    p_path = sys.argv[1] if len(sys.argv) > 1 else "configs/protocols/standard_test_v1.yaml"
    m_path = sys.argv[2] if len(sys.argv) > 2 else "configs/machines/machine.local.yaml"
    try:
        validate_runtime_protocol(p_path, m_path)
    except Exception as e:
        print("[ERROR] " + str(e), file=sys.stderr)
        sys.exit(1)
