import os, sys, glob, json, yaml, hashlib
from typing import Dict, Any, List
from evalscope.config import TaskConfig
from evalscope.run import run_task
from llst.capability.sample_resolver import resolve_all_pinned_samples, extract_prompt_texts
from llst.capability.pinned_dataset import prepare_pinned_datasets

def run_capability_suite(resolved_cfg: Dict[str, Any], run_dir: str, evalscope_bin: str = "evalscope", smoke: bool = False):
    cap_cfg = resolved_cfg["capability"]
    mach_cfg = resolved_cfg["machine"]

    model_name = mach_cfg["model_name"]
    api_base = mach_cfg["api_base"]
    api_key = mach_cfg["api_key"]
    seed = cap_cfg.get("seed", 42)

    gen_cfg = cap_cfg.get("generation", {})
    generation_dict = {
        "temperature": float(gen_cfg.get("temperature", 0.0)),
        "max_tokens": int(gen_cfg.get("max_tokens", 2048)),
        "stream": bool(gen_cfg.get("stream", True))
    }

    protocol_path = resolved_cfg.get("meta", {}).get("protocol_path", "configs/protocols/standard_test_v1.yaml")
    machine_path = resolved_cfg.get("meta", {}).get("machine_path", "configs/machines/machine.local.yaml")

    # Step 1: Resolve and verify pinned samples via shared sample_resolver
    print("[INFO] Capability: Resolving and verifying pinned samples via shared sample_resolver...")
    resolved_all = resolve_all_pinned_samples(protocol_path, machine_path, check_hashes=True)
    manifest_sha256 = resolved_all["manifest_sha256"]
    resolved_samples_sha256 = resolved_all["resolved_samples_sha256"]
    samples_by_bm = resolved_all["samples_by_benchmark"]

    benchmarks = cap_cfg.get("benchmarks", [])
    if smoke:
        # Smoke mode: only 1 sample from ifeval (sample 0)
        ifeval_samples = samples_by_bm["ifeval"][:1]
        samples_by_bm = {"ifeval": ifeval_samples}
        benchmarks = [{"name": "ifeval", "limit": 1, "label": "Instruction following (Smoke)"}]

    # Step 2: Prepare pinned offline datasets so EvalScope loads directly from disk
    print("[INFO] Capability: Preparing pinned offline datasets...")
    dataset_dir = prepare_pinned_datasets(run_dir, samples_by_bm, smoke=smoke)
    print(f"[INFO] Capability: Pinned datasets ready in {dataset_dir}.")

    results = {}
    for b in benchmarks:
        name = b["name"]
        target_samples = samples_by_bm.get(name, [])
        label = b.get("label", "")
        print(f"[INFO] Capability: Starting {name} ({label}), pinned_samples={len(target_samples)}...")

        work_dir = os.path.join(run_dir, "capability", name)
        os.makedirs(work_dir, exist_ok=True)

        # Check if already computed in work_dir
        existing_preds = glob.glob(os.path.join(work_dir, "**", "predictions", "**", "*.jsonl"), recursive=True)
        if existing_preds:
            total_existing = 0
            for ep in existing_preds:
                with open(ep, "r", encoding="utf-8") as ep_f:
                    total_existing += sum(1 for line in ep_f if line.strip())
            if total_existing == len(target_samples):
                print(f"[INFO] Capability: {name} already evaluated ({total_existing} samples found), skipping execution.")
                results[name] = work_dir
                continue

        task_dict = {
            "model": model_name,
            "api_url": api_base,
            "api_key": api_key,
            "eval_type": "openai_api",
            "datasets": [name],
            "dataset_dir": dataset_dir,
            "limit": len(target_samples),
            "eval_batch_size": int(cap_cfg.get("eval_batch_size", 1)),
            "generation_config": generation_dict,
            "seed": seed,
            "enable_progress_tracker": True,
            "work_dir": work_dir
        }

        # Handle benchmark specific args
        dataset_args = {}
        if name == "live_code_bench":
            dataset_args["live_code_bench"] = {"subset_list": ["release_latest"]}
        elif name == "ceval":
            dataset_args["ceval"] = {"subset_list": [s.subset for s in target_samples]}
        
        if dataset_args:
            task_dict["dataset_args"] = dataset_args

        if b.get("sandbox", {}).get("enabled", False):
            sb_cfg = b["sandbox"].copy()
            if "image" in sb_cfg:
                img = sb_cfg.pop("image")
                sb_cfg.setdefault("default_config", {})["image"] = img
            task_dict["sandbox"] = sb_cfg

        t_cfg = TaskConfig.from_dict(task_dict)
        run_task(t_cfg)
        print(f"[INFO] Capability: {name} completed successfully.")
        results[name] = work_dir

    # Step 3: Audit executed predictions from disk
    print("[INFO] Capability: Auditing executed predictions from output files...")
    executed_samples = []
    
    for b in benchmarks:
        name = b["name"]
        target_samples = samples_by_bm.get(name, [])
        work_dir = os.path.join(run_dir, "capability", name)
        
        # Search for prediction jsonl files
        pred_pattern = os.path.join(work_dir, "**", "predictions", "**", "*.jsonl")
        pred_files = glob.glob(pred_pattern, recursive=True)
        if not pred_files:
            raise RuntimeError(f"PROTOCOL_EXECUTION_MISMATCH: No prediction files found for {name} in {work_dir}")

        # Collect all predictions for this benchmark
        preds = []
        for pf in pred_files:
            with open(pf, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        preds.append(json.loads(line))

        print(f"[INFO] Capability: Found {len(preds)} prediction records for {name} (expected {len(target_samples)}).")
        if len(preds) != len(target_samples):
            raise RuntimeError(f"PROTOCOL_EXECUTION_MISMATCH: {name} produced {len(preds)} predictions, expected {len(target_samples)}")

        # Verify each target sample was executed
        for rs in target_samples:
            matched = False
            for p in preds:
                meta = p.get("metadata") or {}
                # Match by sample_id in metadata
                pid = None
                if name == "live_code_bench":
                    pid = meta.get("question_id")
                elif name == "ifeval":
                    pid = str(meta.get("key")) if meta.get("key") is not None else None
                elif name == "mmlu_pro":
                    pid = str(meta.get("question_id")) if meta.get("question_id") is not None else None
                elif name == "ceval":
                    pid = str(meta.get("id")) if meta.get("id") is not None else None

                if pid and rs.sample_id and str(pid) == str(rs.sample_id):
                    matched = True
                    break
                
                # Match by prompt content hash
                msgs = p.get("messages") or []
                u_text = ""
                s_text = ""
                for m in msgs:
                    if m.get("role") == "user":
                        u_text = m.get("content", "")
                    elif m.get("role") == "system":
                        s_text = m.get("content", "")
                
                full_p = (s_text + "\n" + u_text).strip() if s_text else u_text.strip()
                h_user = hashlib.sha256(u_text.strip().encode("utf-8")).hexdigest()
                h_user_raw = hashlib.sha256(u_text.encode("utf-8")).hexdigest()
                h_full = hashlib.sha256(full_p.encode("utf-8")).hexdigest()

                if rs.prompt_sha256 in (h_user, h_user_raw, h_full):
                    matched = True
                    break
            
            if not matched:
                raise RuntimeError(f"PROTOCOL_EXECUTION_MISMATCH: Target sample {rs.benchmark}/{rs.subset}/{rs.sample_id} was not executed!")
            executed_samples.append(rs)

    # Step 4: Verify cryptographic equivalence
    all_executed_records = [rs.to_dict() for rs in executed_samples]
    executed_json = json.dumps(all_executed_records, sort_keys=True, separators=(",", ":"))
    executed_samples_sha256 = hashlib.sha256(executed_json.encode("utf-8")).hexdigest()

    expected_total = 1 if smoke else 102
    if len(executed_samples) != expected_total:
        raise RuntimeError(f"PROTOCOL_EXECUTION_MISMATCH: Executed {len(executed_samples)} samples, expected {expected_total}")

    if not smoke:
        if executed_samples_sha256 != resolved_samples_sha256:
            raise RuntimeError(f"PROTOCOL_EXECUTION_MISMATCH: executed_samples_sha256 ({executed_samples_sha256}) != resolved_samples_sha256 ({resolved_samples_sha256})")

    # Step 5: Save capability execution manifest
    manifest_meta = {
        "manifest_sha256": manifest_sha256,
        "resolved_samples_sha256": resolved_samples_sha256,
        "executed_samples_sha256": executed_samples_sha256,
        "total_executed": len(executed_samples),
        "smoke": smoke,
        "benchmarks": {b["name"]: len(samples_by_bm.get(b["name"], [])) for b in benchmarks}
    }
    with open(os.path.join(run_dir, "capability", "execution_manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest_meta, f, indent=2, ensure_ascii=False)

    print(f"[INFO] Capability: Execution manifest written. Total executed: {len(executed_samples)}. EQUIVALENCE PASS.")
    return results

if __name__ == "__main__":
    from llst.config_loader import load_resolved_config
    p_path = sys.argv[1] if len(sys.argv) > 1 else "configs/protocols/standard_test_v1.yaml"
    m_path = sys.argv[2] if len(sys.argv) > 2 else "configs/machines/machine.local.yaml"
    r_dir = sys.argv[3] if len(sys.argv) > 3 else "outputs/test_run"
    cfg = load_resolved_config(p_path, m_path)
    run_capability_suite(cfg, r_dir)
