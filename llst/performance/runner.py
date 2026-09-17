import glob
import hashlib
import json
import os
import sqlite3
import subprocess
import sys

from llst.performance.workload_generator import (
    generate_workload_plan,
    save_workload_files,
    verify_workload_manifest,
)


def _sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as artifact_file:
        for chunk in iter(lambda: artifact_file.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_perf_database(database_path, expected_requests):
    with sqlite3.connect(database_path) as connection:
        total, successful = connection.execute(
            "SELECT COUNT(*), COALESCE(SUM(success), 0) FROM result"
        ).fetchone()
    if total != expected_requests or successful != expected_requests:
        raise RuntimeError(
            f"PERFORMANCE_EXECUTION_MISMATCH: {database_path} has {successful}/{total} successful requests; "
            f"expected {expected_requests}/{expected_requests}"
        )
    return {"records": total, "successful": successful}


def _collect_perf_artifacts(out_dir, expected_requests):
    required_names = {
        "benchmark_args.json",
        "benchmark_data.db",
        "benchmark_percentile.json",
        "benchmark_summary.json",
    }
    artifacts = {}
    for path in sorted(glob.glob(os.path.join(out_dir, "**", "*"), recursive=True)):
        if not os.path.isfile(path) or os.path.basename(path) not in required_names:
            continue
        relative_path = os.path.relpath(path, out_dir)
        artifacts[relative_path] = {"sha256": _sha256_file(path), "bytes": os.path.getsize(path)}

    names_found = {os.path.basename(path) for path in artifacts}
    missing = required_names - names_found
    if missing:
        raise RuntimeError(f"PERFORMANCE_ARTIFACT_MISSING: {out_dir} missing {', '.join(sorted(missing))}")

    database_paths = [path for path in artifacts if os.path.basename(path) == "benchmark_data.db"]
    if len(database_paths) != 1:
        raise RuntimeError(f"PERFORMANCE_ARTIFACT_INVALID: expected one benchmark_data.db in {out_dir}")
    database_path = os.path.join(out_dir, database_paths[0])
    return artifacts, _verify_perf_database(database_path, expected_requests)

def run_performance_suite(resolved_cfg, run_dir, evalscope_bin="evalscope", smoke=False):
    perf_cfg = resolved_cfg["performance"]
    mach_cfg = resolved_cfg["machine"]

    model_name = mach_cfg["model_name"]
    perf_url = mach_cfg["perf_url"]
    api_key = mach_cfg["api_key"]
    tok_path = mach_cfg["tokenizer_path"]
    outtok = perf_cfg.get("output_tokens", 512)
    seed = perf_cfg.get("seed", 20260917)
    parallel = perf_cfg.get("parallel", 1)
    temp = perf_cfg.get("temperature", 0.0)

    prompt_lengths = [512, 4096] if smoke else perf_cfg.get("prompt_lengths", [512, 4096, 16384, 28672])
    requests_per_length = 1 if smoke else perf_cfg.get("requests_per_length", 2)

    workload_dir = os.path.join(run_dir, "workload")
    print(f"[INFO] Generating deterministic performance workload (seed={seed})...")
    workload = generate_workload_plan(
        tok_path,
        seed=seed,
        prompt_lengths=prompt_lengths,
        requests_per_length=requests_per_length,
        trust_remote_code=mach_cfg.get("tokenizer_trust_remote_code", False),
    )
    manifest_path, manifest = save_workload_files(workload, workload_dir, seed=seed)
    verify_workload_manifest(manifest, workload_dir)
    print(f"[INFO] Workload saved to {workload_dir}, manifest: {manifest_path}")

    perf_results = {}
    execution_cases = {}
    for length in prompt_lengths:
        case_info = manifest["cases"][str(length)]
        wl_file = case_info["path"]
        verify_workload_manifest(manifest, workload_dir)
        print(f"[INFO] Performance: ISL {length} -> OSL {outtok}, reqs={requests_per_length}, sha256={case_info['sha256'][:16]}...")

        out_dir = os.path.join(run_dir, "performance", f"isl_{length}_osl_{outtok}")
        log_file = os.path.join(run_dir, "logs", f"perf_{length}.log")

        cmd = [
            evalscope_bin, "perf",
            "--url", perf_url,
            "--api-key", api_key,
            "--model", model_name,
            "--dataset", "line_by_line",
            "--dataset-path", wl_file,
            "--tokenizer-path", tok_path,
            "--min-tokens", str(outtok),
            "--max-tokens", str(outtok),
            "--parallel", str(parallel),
            "--number", str(requests_per_length),
            "--temperature", str(temp),
            "--tokenize-prompt",
            "--stream",
            "--outputs-dir", out_dir
        ]

        with open(log_file, "w", encoding="utf-8") as out_f:
            p = subprocess.run(cmd, stdout=out_f, stderr=subprocess.STDOUT)
            if p.returncode != 0:
                print(f"[ERROR] Performance run for length {length} failed. Log: {log_file}", file=sys.stderr)
                raise RuntimeError(f"Performance run for length {length} failed")
        verify_workload_manifest(manifest, workload_dir)
        artifacts, database_audit = _collect_perf_artifacts(out_dir, requests_per_length)
        print(f"[INFO] Performance: ISL {length} completed successfully.")
        perf_results[length] = out_dir
        execution_cases[str(length)] = {
            "workload_file": case_info["file"],
            "workload_sha256": case_info["sha256"],
            "artifacts": artifacts,
            "database": database_audit,
        }

    execution_manifest = {
        "workload_manifest": os.path.basename(manifest_path),
        "workload_manifest_sha256": _sha256_file(manifest_path),
        "smoke": smoke,
        "cases": execution_cases,
    }
    execution_path = os.path.join(run_dir, "performance", "execution_manifest.json")
    with open(execution_path, "w", encoding="utf-8") as manifest_file:
        json.dump(execution_manifest, manifest_file, indent=2, ensure_ascii=False)
    print(f"[INFO] Performance: Execution manifest written: {execution_path}")

    return perf_results

if __name__ == "__main__":
    from llst.config_loader import load_resolved_config
    p_path = sys.argv[1]
    m_path = sys.argv[2]
    r_dir = sys.argv[3]
    cfg = load_resolved_config(p_path, m_path)
    run_performance_suite(cfg, r_dir)
