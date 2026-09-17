"""Fail-closed verification for LLST's locally materialized dataset snapshots."""

import glob
import hashlib
import json
import os
from pathlib import Path

import yaml


DATASET_CACHE_DIRS = {
    "mmlu_pro": "TIGER-Lab___mmlu-pro",
    "ifeval": "opencompass___ifeval",
    "aime24": "evalscope___aime24",
    "ceval": "evalscope___ceval",
    "live_code_bench": "evalscope___livecodebench_code_generation_lite_parquet",
}


class DatasetSnapshotError(RuntimeError):
    """Raised when the verified local dataset snapshot is unavailable or changed."""


def dataset_cache_root():
    return os.environ.get("MODELSCOPE_CACHE", os.path.expanduser("~/.cache/modelscope/hub/datasets"))


def compute_dataset_snapshot_hash(dataset_dir_name, cache_root=None):
    """Hash the ordered Arrow payloads used by the v1 pinned snapshots."""
    root = cache_root or dataset_cache_root()
    snapshot_dir = os.path.join(root, dataset_dir_name)
    arrows = sorted(glob.glob(f"{snapshot_dir}/**/*.arrow", recursive=True))
    if not arrows:
        return None

    combined_hash = hashlib.sha256()
    for arrow_path in arrows:
        with open(arrow_path, "rb") as arrow_file:
            for chunk in iter(lambda: arrow_file.read(65536), b""):
                combined_hash.update(chunk)
    return combined_hash.hexdigest()


def _load_dataset_manifest(protocol_path):
    with open(protocol_path, "r", encoding="utf-8") as protocol_file:
        protocol = yaml.safe_load(protocol_file) or {}
    manifest_rel = protocol.get("capability", {}).get("dataset_manifest", "v1/dataset_manifest.json")
    manifest_path = Path(protocol_path).parent / manifest_rel
    if not manifest_path.is_file():
        raise DatasetSnapshotError(f"DATASET_MANIFEST_MISSING: {manifest_path}")
    with manifest_path.open("r", encoding="utf-8") as manifest_file:
        return manifest_path, json.load(manifest_file)


def verify_dataset_snapshots(protocol_path, cache_root=None):
    """Verify every dataset required by the protocol or fail before evaluation."""
    manifest_path, manifest = _load_dataset_manifest(protocol_path)
    benchmarks = manifest.get("benchmarks")
    if not isinstance(benchmarks, dict):
        raise DatasetSnapshotError(f"DATASET_MANIFEST_INVALID: {manifest_path} has no benchmarks mapping")

    verified = {}
    for benchmark, directory_name in DATASET_CACHE_DIRS.items():
        metadata = benchmarks.get(benchmark)
        if not isinstance(metadata, dict):
            raise DatasetSnapshotError(f"DATASET_MANIFEST_INVALID: missing metadata for {benchmark}")
        expected = metadata.get("dataset_snapshot_sha256")
        if not isinstance(expected, str) or len(expected) != 64:
            raise DatasetSnapshotError(f"DATASET_SNAPSHOT_UNPINNED: {benchmark} has no SHA-256 lock")

        actual = compute_dataset_snapshot_hash(directory_name, cache_root=cache_root)
        if actual is None:
            raise DatasetSnapshotError(
                f"DATASET_SNAPSHOT_MISSING: {benchmark} is absent from {cache_root or dataset_cache_root()}"
            )
        if actual != expected:
            raise DatasetSnapshotError(
                f"DATASET_SNAPSHOT_MISMATCH: {benchmark} expected {expected}, got {actual}"
            )
        verified[benchmark] = {"dataset_dir": directory_name, "sha256": actual}
    return verified
