import os
import shutil
from typing import Dict, Any, List
from evalscope.api.dataset.hub import DatasetHub
from evalscope.api.dataset.loader import _dataset_cache_hash, safe_filename

def prepare_pinned_datasets(run_dir: str, resolved_samples_by_bm: Dict[str, List[Any]], smoke: bool = False) -> str:
    """
    Prepares offline pinned datasets for EvalScope so that run_task(TaskConfig)
    loads only the exact pinned samples natively via RemoteDataLoader disk cache.
    
    Returns the absolute path to dataset_dir (<run_dir>/workload/pinned_datasets).
    """
    dataset_dir = os.path.join(run_dir, "workload", "pinned_datasets")
    cache_dir = os.path.join(dataset_dir, "datasets")
    os.makedirs(cache_dir, exist_ok=True)

    # 1. IFEval
    if "ifeval" in resolved_samples_by_bm:
        ifeval_samples = resolved_samples_by_bm["ifeval"]
        p_ifeval = "opencompass/ifeval"
        raw_ifeval = DatasetHub(data_id_or_path=p_ifeval).load(split="train", subset="default")
        
        target_keys = set(str(s.sample_id) for s in ifeval_samples)
        matched = [i for i, row in enumerate(raw_ifeval) if str(row.get("key")) in target_keys]
        if smoke:
            matched = matched[:1]
        
        pinned_ifeval = raw_ifeval.select(matched)
        h = _dataset_cache_hash(p_ifeval, "train", "default", None, "modelscope", {})
        target = os.path.join(cache_dir, f"{safe_filename(p_ifeval)}-{h}")
        if not os.path.exists(target):
            pinned_ifeval.save_to_disk(target)

    if smoke:
        return dataset_dir

    # 2. AIME24
    if "aime24" in resolved_samples_by_bm:
        p_aime = "evalscope/aime24"
        raw_aime = DatasetHub(data_id_or_path=p_aime).load(split="test", subset="default")
        pinned_aime = raw_aime.select(range(10))
        h = _dataset_cache_hash(p_aime, "test", "default", None, "modelscope", {})
        target = os.path.join(cache_dir, f"{safe_filename(p_aime)}-{h}")
        if not os.path.exists(target):
            pinned_aime.save_to_disk(target)

    # 3. LiveCodeBench
    if "live_code_bench" in resolved_samples_by_bm:
        p_lcb = "evalscope/livecodebench_code_generation_lite_parquet"
        lcb_samples = resolved_samples_by_bm["live_code_bench"]
        lcb_ids = [str(s.sample_id) for s in lcb_samples]
        raw_lcb = DatasetHub(data_id_or_path=p_lcb).load(split="test", subset="release_latest")
        matched_lcb = []
        for eid in lcb_ids:
            for i, row in enumerate(raw_lcb):
                if str(row.get("question_id")) == eid:
                    matched_lcb.append(i)
                    break
        pinned_lcb = raw_lcb.select(matched_lcb)
        h = _dataset_cache_hash(p_lcb, "test", "release_latest", None, "modelscope", {})
        target = os.path.join(cache_dir, f"{safe_filename(p_lcb)}-{h}")
        if not os.path.exists(target):
            pinned_lcb.save_to_disk(target)

    # 4. CEval
    if "ceval" in resolved_samples_by_bm:
        p_ceval = "evalscope/ceval"
        ceval_samples = resolved_samples_by_bm["ceval"]
        for s in ceval_samples:
            sub = s.subset
            # Val split
            raw_val = DatasetHub(data_id_or_path=p_ceval).load(split="val", subset=sub)
            pinned_val = raw_val.select([s.sample_index])
            h_val = _dataset_cache_hash(p_ceval, "val", sub, None, "modelscope", {})
            target_val = os.path.join(cache_dir, f"{safe_filename(p_ceval)}-{h_val}")
            if not os.path.exists(target_val):
                pinned_val.save_to_disk(target_val)
            
            # Dev split (for few-shot)
            raw_dev = DatasetHub(data_id_or_path=p_ceval).load(split="dev", subset=sub)
            h_dev = _dataset_cache_hash(p_ceval, "dev", sub, None, "modelscope", {})
            target_dev = os.path.join(cache_dir, f"{safe_filename(p_ceval)}-{h_dev}")
            if not os.path.exists(target_dev):
                raw_dev.save_to_disk(target_dev)

    # 5. MMLU-Pro
    if "mmlu_pro" in resolved_samples_by_bm:
        p_mmlu = "TIGER-Lab/MMLU-Pro"
        mmlu_samples = resolved_samples_by_bm["mmlu_pro"]
        mmlu_ids = set(str(s.sample_id) for s in mmlu_samples)
        raw_mmlu_test = DatasetHub(data_id_or_path=p_mmlu).load(split="test", subset="default")
        matched_mmlu = [i for i, row in enumerate(raw_mmlu_test) if str(row.get("question_id")) in mmlu_ids]
        pinned_mmlu = raw_mmlu_test.select(matched_mmlu)
        h_test = _dataset_cache_hash(p_mmlu, "test", "default", None, "modelscope", {})
        target_test = os.path.join(cache_dir, f"{safe_filename(p_mmlu)}-{h_test}")
        if not os.path.exists(target_test):
            pinned_mmlu.save_to_disk(target_test)

        # Fewshot (validation split)
        raw_mmlu_val = DatasetHub(data_id_or_path=p_mmlu).load(split="validation", subset="default")
        h_val = _dataset_cache_hash(p_mmlu, "validation", "default", None, "modelscope", {})
        target_val = os.path.join(cache_dir, f"{safe_filename(p_mmlu)}-{h_val}")
        if not os.path.exists(target_val):
            raw_mmlu_val.save_to_disk(target_val)

    return dataset_dir
