import os
import sys
import json
import yaml
import hashlib
from typing import Dict, List, Any, Optional, Tuple
from evalscope.config import TaskConfig
from evalscope.api.registry import get_benchmark

def get_canonical_record(benchmark_name: str, sample: Any) -> Dict[str, Any]:
    if benchmark_name == "ifeval":
        return {
            "key": sample.metadata.get("key"),
            "prompt": sample.metadata.get("prompt"),
            "instruction_id_list": sample.metadata.get("instruction_id_list"),
            "kwargs": sample.metadata.get("kwargs")
        }
    elif benchmark_name == "live_code_bench":
        return {
            "evaluation_sample": sample.metadata.get("evaluation_sample"),
            "contest_date": str(sample.metadata.get("contest_date", ""))
        }
    elif benchmark_name == "mmlu_pro":
        return {
            "question_id": sample.metadata.get("question_id"),
            "category": sample.metadata.get("subject"),
            "choices": sample.choices,
            "target": sample.target
        }
    elif benchmark_name == "ceval":
        return {
            "id": sample.metadata.get("id"),
            "subject": sample.metadata.get("subject"),
            "choices": sample.choices,
            "target": sample.target
        }
    elif benchmark_name == "aime24":
        return {
            "target": str(sample.target)
        }
    return sample.metadata or {}

def extract_prompt_texts(sample: Any, default_system: str = "") -> Tuple[str, str]:
    user_cnt = ""
    sys_cnt = ""
    if isinstance(sample.input, list):
        for msg in sample.input:
            role = getattr(msg, "role", None)
            if role == "user":
                user_cnt = getattr(msg, "content", "")
            elif role == "system":
                sys_cnt = getattr(msg, "content", "")
    elif isinstance(sample.input, str):
        user_cnt = sample.input

    if not sys_cnt and default_system:
        sys_cnt = default_system

    full_prompt = (sys_cnt + "\n" + user_cnt).strip() if sys_cnt else user_cnt.strip()
    return full_prompt, user_cnt.strip()

def check_target_hash(sample: Any, expected_sha256: str) -> bool:
    candidates = [
        str(sample.target),
        str([sample.target]),
        "None" if sample.target in (None, "", []) else str(sample.target),
        repr(sample.target)
    ]
    for c in candidates:
        if hashlib.sha256(c.encode("utf-8")).hexdigest() == expected_sha256:
            return True
    return False

class ResolvedSample:
    def __init__(self, benchmark: str, subset: str, sample_index: int, sample_id: Optional[str],
                 prompt_sha256: str, target_sha256: str, record_sha256: str, sample: Any):
        self.benchmark = benchmark
        self.subset = subset
        self.sample_index = sample_index
        self.sample_id = sample_id
        self.prompt_sha256 = prompt_sha256
        self.target_sha256 = target_sha256
        self.record_sha256 = record_sha256
        self.sample = sample

    def to_dict(self) -> Dict[str, Any]:
        return {
            "benchmark": self.benchmark,
            "subset": self.subset,
            "sample_index": self.sample_index,
            "sample_id": self.sample_id,
            "prompt_sha256": self.prompt_sha256,
            "target_sha256": self.target_sha256,
            "record_sha256": self.record_sha256
        }

def resolve_benchmark_samples(benchmark_name: str, manifest_samples: List[Dict[str, Any]],
                              protocol_bench_cfg: Dict[str, Any], seed: int = 42,
                              check_hashes: bool = True) -> List[ResolvedSample]:
    bm_manifest = [s for s in manifest_samples if s["benchmark"] == benchmark_name]
    expected_count = len(bm_manifest)
    if expected_count == 0:
        return []

    # Map by sample_id if available, and by (subset, sample_index)
    id_map = {}
    index_map = {}
    for m in bm_manifest:
        if m.get("sample_id"):
            id_map[(m["subset"], str(m["sample_id"]))] = m
        index_map[(m["subset"], m["sample_index"])] = m

    # Instantiate official benchmark adapter to load data
    t_dict = {
        "model": "resolver",
        "api_url": "http://127.0.0.1:8000/v1",
        "api_key": "dummy",
        "eval_type": "openai_api",
        "datasets": [benchmark_name],
        "limit": protocol_bench_cfg.get("limit"),
        "seed": seed
    }
    if "subset_list" in protocol_bench_cfg:
        t_dict["dataset_args"] = {benchmark_name: {"subset_list": protocol_bench_cfg["subset_list"]}}

    t_cfg = TaskConfig.from_dict(t_dict)
    bm_adapter = get_benchmark(benchmark_name, t_cfg)
    full_ds = bm_adapter.load_dataset()

    resolved_samples: List[ResolvedSample] = []
    default_sys = getattr(bm_adapter, "system_prompt", "") or ""

    for subset_name, ds in full_ds.items():
        for idx, s in enumerate(ds.samples):
            # Try to match by sample_id first, then (subset, index)
            sid = None
            if benchmark_name == "live_code_bench":
                sid = getattr(s, "id", None) or (s.metadata.get("question_id") if s.metadata else None)
            elif benchmark_name == "ifeval":
                sid = str(s.metadata.get("key")) if s.metadata else None
            elif benchmark_name == "mmlu_pro":
                sid = str(s.metadata.get("question_id")) if s.metadata else None
            elif benchmark_name == "ceval":
                sid = str(s.metadata.get("id")) if s.metadata else None

            m_entry = None
            if sid and (subset_name, str(sid)) in id_map:
                m_entry = id_map[(subset_name, str(sid))]
            elif (subset_name, idx) in index_map:
                m_entry = index_map[(subset_name, idx)]

            if not m_entry:
                continue

            if check_hashes:
                # 1. Check prompt hash
                full_p, user_p = extract_prompt_texts(s, default_sys)
                p_hash = hashlib.sha256(full_p.encode("utf-8")).hexdigest()
                expected_p = m_entry["prompt_sha256"]
                if p_hash != expected_p:
                    u_hash = hashlib.sha256(user_p.encode("utf-8")).hexdigest()
                    if u_hash != expected_p:
                        raise RuntimeError(f"PROTOCOL_SAMPLE_MISMATCH: Prompt hash mismatch in {benchmark_name}/{subset_name}/{idx}")

                # 2. Check target hash
                expected_t = m_entry.get("target_sha256") or m_entry.get("answer_sha256")
                if not check_target_hash(s, expected_t):
                    raise RuntimeError(f"PROTOCOL_SAMPLE_MISMATCH: Target hash mismatch in {benchmark_name}/{subset_name}/{idx}")

                # 3. Check record hash
                if "record_sha256" in m_entry:
                    rec = get_canonical_record(benchmark_name, s)
                    rec_json = json.dumps(rec, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
                    rec_hash = hashlib.sha256(rec_json.encode("utf-8")).hexdigest()
                    if rec_hash != m_entry["record_sha256"]:
                        raise RuntimeError(f"PROTOCOL_SAMPLE_MISMATCH: Record hash mismatch in {benchmark_name}/{subset_name}/{idx}")

                # 4. Check specific constraints (e.g. LCB question IDs)
                if benchmark_name == "live_code_bench":
                    lcb_expected = ["1873_A", "1873_B", "1873_D", "1883_B", "1883_C", "1899_A", "1899_B", "1899_C", "1899_D", "2727"]
                    if m_entry.get("sample_id") not in lcb_expected:
                        raise RuntimeError(f"PROTOCOL_SAMPLE_MISMATCH: Invalid LiveCodeBench ID {m_entry.get('sample_id')}")

            rs = ResolvedSample(
                benchmark=benchmark_name,
                subset=subset_name,
                sample_index=m_entry["sample_index"],
                sample_id=m_entry.get("sample_id"),
                prompt_sha256=m_entry["prompt_sha256"],
                target_sha256=m_entry.get("target_sha256") or m_entry.get("answer_sha256"),
                record_sha256=m_entry.get("record_sha256", ""),
                sample=s
            )
            resolved_samples.append(rs)

    if len(resolved_samples) != expected_count:
        raise RuntimeError(f"PROTOCOL_SAMPLE_MISMATCH: {benchmark_name} resolved {len(resolved_samples)} samples, expected {expected_count}")

    return resolved_samples

def resolve_all_pinned_samples(protocol_path: str, machine_path: str, check_hashes: bool = True) -> Dict[str, Any]:
    with open(protocol_path, "r", encoding="utf-8") as f:
        protocol = yaml.safe_load(f)

    manifest_rel = protocol.get("capability", {}).get("manifest", "v1/sample_manifest.json")
    manifest_path = os.path.join(os.path.dirname(protocol_path), manifest_rel)
    with open(manifest_path, "rb") as f:
        manifest_raw = f.read()
    manifest_sha256 = hashlib.sha256(manifest_raw).hexdigest()
    manifest = json.loads(manifest_raw.decode("utf-8"))
    manifest_samples = manifest.get("samples", [])

    seed = protocol.get("capability", {}).get("seed", 42)
    bench_configs = {b["name"]: b for b in protocol.get("capability", {}).get("benchmarks", [])}

    resolved_by_benchmark = {}
    counts = {}
    all_resolved_records = []

    for b_name in ["mmlu_pro", "ifeval", "aime24", "ceval", "live_code_bench"]:
        b_cfg = bench_configs.get(b_name, {})
        res_samples = resolve_benchmark_samples(b_name, manifest_samples, b_cfg, seed=seed, check_hashes=check_hashes)
        resolved_by_benchmark[b_name] = res_samples
        counts[b_name] = len(res_samples)
        for rs in res_samples:
            all_resolved_records.append(rs.to_dict())

    total_resolved = sum(counts.values())
    if total_resolved != 102:
        raise RuntimeError(f"PROTOCOL_SAMPLE_MISMATCH: Total resolved {total_resolved} != 102")

    # Canonical hash over all resolved records
    resolved_json = json.dumps(all_resolved_records, sort_keys=True, separators=(",", ":"))
    resolved_samples_sha256 = hashlib.sha256(resolved_json.encode("utf-8")).hexdigest()

    return {
        "samples_by_benchmark": resolved_by_benchmark,
        "counts": counts,
        "total": total_resolved,
        "manifest_sha256": manifest_sha256,
        "resolved_samples_sha256": resolved_samples_sha256,
        "manifest": manifest
    }
