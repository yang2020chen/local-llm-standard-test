import os, sys, json, subprocess
from llst.performance.workload_generator import generate_workload_plan, save_workload_files

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
    workload = generate_workload_plan(tok_path, seed=seed, prompt_lengths=prompt_lengths, requests_per_length=requests_per_length)
    manifest_path, manifest = save_workload_files(workload, workload_dir)
    print(f"[INFO] Workload saved to {workload_dir}, manifest: {manifest_path}")

    perf_results = {}
    for length in prompt_lengths:
        case_info = manifest["cases"][str(length)]
        wl_file = case_info["path"]
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
        print(f"[INFO] Performance: ISL {length} completed successfully.")
        perf_results[length] = out_dir

    return perf_results

if __name__ == "__main__":
    from llst.config_loader import load_resolved_config
    p_path = sys.argv[1]
    m_path = sys.argv[2]
    r_dir = sys.argv[3]
    cfg = load_resolved_config(p_path, m_path)
    run_performance_suite(cfg, r_dir)
