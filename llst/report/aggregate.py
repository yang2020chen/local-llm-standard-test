import glob
import hashlib
import json
import os
import sys


def _sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as artifact_file:
        for chunk in iter(lambda: artifact_file.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()

def aggregate_run_reports(run_dir, resolved_cfg):
    model_name = resolved_cfg["machine"]["model_name"]
    cap_dir = os.path.join(run_dir, "capability")
    perf_dir = os.path.join(run_dir, "performance")

    proto_ver = resolved_cfg.get("protocol", {}).get("version", "1.0")

    summary_cap = {
        "model": model_name,
        "protocol_version": proto_ver,
        "benchmarks": {}
    }
    cap_execution_manifest = os.path.join(cap_dir, "execution_manifest.json")
    if os.path.isfile(cap_execution_manifest):
        summary_cap["execution_manifest"] = {
            "path": os.path.relpath(cap_execution_manifest, run_dir),
            "sha256": _sha256_file(cap_execution_manifest),
        }

    if os.path.exists(cap_dir):
        for b in os.listdir(cap_dir):
            bp = os.path.join(cap_dir, b)
            report_files = glob.glob(f"{bp}/**/{b}.json", recursive=True)
            if report_files:
                with open(report_files[0], "r", encoding="utf-8") as f:
                    d = json.load(f)
                    score = d.get("score")
                    if score is None and d.get("metrics"):
                        primary = d.get("primary_metric_identity", {}).get("name")
                        if primary:
                            for m in d["metrics"]:
                                if m.get("identity", {}).get("name") == primary:
                                    score = m.get("score")
                                    break
                        if score is None:
                            score = d["metrics"][0].get("score")
                    
                    summary_cap["benchmarks"][b] = {
                        "score": score,
                        "num_samples": d.get("num")
                    }

    summary_perf = {
        "model": model_name,
        "protocol_version": proto_ver,
        "cases": []
    }
    perf_execution_manifest = os.path.join(perf_dir, "execution_manifest.json")
    if os.path.isfile(perf_execution_manifest):
        summary_perf["execution_manifest"] = {
            "path": os.path.relpath(perf_execution_manifest, run_dir),
            "sha256": _sha256_file(perf_execution_manifest),
        }

    if os.path.exists(perf_dir):
        for c in sorted(os.listdir(perf_dir)):
            cp = os.path.join(perf_dir, c)
            sum_files = glob.glob(f"{cp}/**/benchmark_summary.json", recursive=True)
            if sum_files:
                with open(sum_files[0], "r", encoding="utf-8") as f:
                    d = json.load(f)
                    summary_perf["cases"].append({
                        "case": c,
                        "avg_ttft_ms": d.get("Avg TTFT (ms)"),
                        "avg_tpot_ms": d.get("Avg TPOT (ms)"),
                        "output_throughput_tps": d.get("Output Throughput (tok/s)"),
                        "spec_accept_rate": d.get("Spec. Accept Rate")
                    })

    # Save JSON files
    cap_json_path = os.path.join(run_dir, "capability_summary.json")
    perf_json_path = os.path.join(run_dir, "performance_summary.json")
    with open(cap_json_path, "w", encoding="utf-8") as f:
        json.dump(summary_cap, f, indent=2, ensure_ascii=False)
    with open(perf_json_path, "w", encoding="utf-8") as f:
        json.dump(summary_perf, f, indent=2, ensure_ascii=False)

    # Save report.md
    report_md_path = os.path.join(run_dir, "report.md")
    run_basename = os.path.basename(run_dir)
    with open(report_md_path, "w", encoding="utf-8") as f:
        f.write(f"# LLST Standard Test Report: {model_name}\n\n")
        f.write(f"- Protocol Version: {proto_ver}\n")
        f.write(f"- Execution Run: {run_basename}\n\n")
        f.write("## Capability Summary\n\n")
        f.write("| Benchmark | Score | Samples |\n| :--- | :---: | :---: |\n")
        for b, v in summary_cap["benchmarks"].items():
            f.write(f"| {b} | {v.get('score')} | {v.get('num_samples')} |\n")
        f.write("\n## Performance Summary\n\n")
        f.write("| Workload Case | Avg TTFT (ms) | Avg TPOT (ms) | Output Throughput (tok/s) | Spec Accept Rate |\n| :---: | :---: | :---: | :---: | :---: |\n")
        for c in summary_perf["cases"]:
            f.write(f"| {c['case']} | {c.get('avg_ttft_ms')} | {c.get('avg_tpot_ms')} | {c.get('output_throughput_tps')} | {c.get('spec_accept_rate')} |\n")
        f.write("\n## Integrity Artifacts\n\n")
        for label, summary in (("Capability", summary_cap), ("Performance", summary_perf)):
            artifact = summary.get("execution_manifest")
            if artifact:
                f.write(f"- {label} execution manifest: `{artifact['path']}` (SHA-256: `{artifact['sha256']}`)\n")

    print(f"[INFO] Report aggregation complete: {report_md_path}")
    return cap_json_path, perf_json_path, report_md_path

if __name__ == "__main__":
    from llst.config_loader import load_resolved_config
    p_path = sys.argv[1]
    m_path = sys.argv[2]
    r_dir = sys.argv[3]
    cfg = load_resolved_config(p_path, m_path)
    aggregate_run_reports(r_dir, cfg)
