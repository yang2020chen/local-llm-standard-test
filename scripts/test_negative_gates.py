#!/usr/bin/env python3
"""
LLST Negative Test Suite: Verifies 100% Fail-Closed behavior for protocol gates (N1-N5).
"""
import os, sys, json, yaml, shutil, tempfile
from llst.protocol_validator import validate_runtime_protocol

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PROTOCOL_ORIG = os.path.join(PROJECT_ROOT, "configs/protocols/standard_test_v1.yaml")
MACHINE_ORIG = os.path.join(PROJECT_ROOT, "configs/machines/machine.local.yaml")

def setup_test_env():
    td = tempfile.mkdtemp(prefix="llst_neg_")
    proto_dir = os.path.join(td, "protocols", "v1")
    os.makedirs(proto_dir, exist_ok=True)
    mach_dir = os.path.join(td, "machines")
    os.makedirs(mach_dir, exist_ok=True)

    # Copy clean files
    proto_path = os.path.join(td, "protocols", "standard_test_v1.yaml")
    shutil.copy(PROTOCOL_ORIG, proto_path)
    
    sample_mf_path = os.path.join(proto_dir, "sample_manifest.json")
    shutil.copy(os.path.join(PROJECT_ROOT, "configs/protocols/v1/sample_manifest.json"), sample_mf_path)

    ds_mf_path = os.path.join(proto_dir, "dataset_manifest.json")
    shutil.copy(os.path.join(PROJECT_ROOT, "configs/protocols/v1/dataset_manifest.json"), ds_mf_path)

    mach_path = os.path.join(mach_dir, "machine.local.yaml")
    shutil.copy(MACHINE_ORIG, mach_path)

    fp_path = os.path.join(td, "tokenizer_fingerprint.json")
    shutil.copy(os.path.join(PROJECT_ROOT, "examples/baseline_001/tokenizer_fingerprint.json"), fp_path)

    # Update machine config to point to temp fingerprint
    with open(mach_path, "r", encoding="utf-8") as f:
        m_cfg = yaml.safe_load(f)
    m_cfg["tokenizer"]["fingerprint"] = fp_path
    with open(mach_path, "w", encoding="utf-8") as f:
        yaml.dump(m_cfg, f)

    return td, proto_path, mach_path, sample_mf_path, ds_mf_path, fp_path

def run_negative_tests():
    print("========================================================================")
    print(" LLST Negative Test Suite (N1 - N5) Asserting Fail-Closed Behavior")
    print("========================================================================")
    all_passed = True

    # -------------------------------------------------------------------------
    # N1: Tampered Prompt Hash
    # -------------------------------------------------------------------------
    td, proto, mach, smf, dmf, fp = setup_test_env()
    try:
        with open(smf, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Modify prompt hash of first sample
        data["samples"][0]["prompt_sha256"] = "0" * 64
        with open(smf, "w", encoding="utf-8") as f:
            json.dump(data, f)

        passed = False
        try:
            validate_runtime_protocol(proto, mach, project_root=PROJECT_ROOT)
        except Exception as e:
            if "PROTOCOL_SAMPLE_MISMATCH" in str(e) or "Prompt hash mismatch" in str(e):
                passed = True
                print(f"[TEST N1] Tampered Prompt Hash -> CAUGHT: {e}")
                print("         Assert Fail-Closed Passed.")
            else:
                print(f"[TEST N1] FAILED: Unexpected exception: {e}")

        if not passed:
            print("[TEST N1] FAILED: Validator did not catch tampered prompt hash!")
            all_passed = False
    finally:
        shutil.rmtree(td)

    # -------------------------------------------------------------------------
    # N2: Tampered Sample ID / LCB ID
    # -------------------------------------------------------------------------
    td, proto, mach, smf, dmf, fp = setup_test_env()
    try:
        with open(smf, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Find an LCB sample and tamper with its ID
        for s in data["samples"]:
            if s["benchmark"] == "live_code_bench":
                s["sample_id"] = "9999_TAMPERED"
                break
        with open(smf, "w", encoding="utf-8") as f:
            json.dump(data, f)

        passed = False
        try:
            validate_runtime_protocol(proto, mach, project_root=PROJECT_ROOT)
        except Exception as e:
            if "PROTOCOL_SAMPLE_MISMATCH" in str(e) or "Invalid LiveCodeBench ID" in str(e):
                passed = True
                print(f"[TEST N2] Tampered LCB ID -> CAUGHT: {e}")
                print("         Assert Fail-Closed Passed.")
            else:
                print(f"[TEST N2] FAILED: Unexpected exception: {e}")

        if not passed:
            print("[TEST N2] FAILED: Validator did not catch tampered LCB ID!")
            all_passed = False
    finally:
        shutil.rmtree(td)

    # -------------------------------------------------------------------------
    # N3: Tampered Tokenizer Hash
    # -------------------------------------------------------------------------
    td, proto, mach, smf, dmf, fp = setup_test_env()
    try:
        with open(fp, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Tamper with a file hash in tokenizer fingerprint
        for fname in data["files"]:
            data["files"][fname]["sha256"] = "f" * 64
            break
        with open(fp, "w", encoding="utf-8") as f:
            json.dump(data, f)

        passed = False
        try:
            validate_runtime_protocol(proto, mach, project_root=PROJECT_ROOT)
        except Exception as e:
            if "TOKENIZER_FINGERPRINT_MISMATCH" in str(e):
                passed = True
                print(f"[TEST N3] Tampered Tokenizer Hash -> CAUGHT: {e}")
                print("         Assert Fail-Closed Passed.")
            else:
                print(f"[TEST N3] FAILED: Unexpected exception: {e}")

        if not passed:
            print("[TEST N3] FAILED: Validator did not catch tampered tokenizer hash!")
            all_passed = False
    finally:
        shutil.rmtree(td)

    # -------------------------------------------------------------------------
    # N4: Tampered Dataset Snapshot
    # -------------------------------------------------------------------------
    td, proto, mach, smf, dmf, fp = setup_test_env()
    try:
        with open(dmf, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Tamper with dataset snapshot hash for ifeval
        data["benchmarks"]["ifeval"]["dataset_snapshot_sha256"] = "a" * 64
        with open(dmf, "w", encoding="utf-8") as f:
            json.dump(data, f)

        passed = False
        try:
            validate_runtime_protocol(proto, mach, project_root=PROJECT_ROOT)
        except Exception as e:
            if "DATASET_SNAPSHOT_MISMATCH" in str(e):
                passed = True
                print(f"[TEST N4] Tampered Dataset Snapshot -> CAUGHT: {e}")
                print("         Assert Fail-Closed Passed.")
            else:
                print(f"[TEST N4] FAILED: Unexpected exception: {e}")

        if not passed:
            print("[TEST N4] FAILED: Validator did not catch tampered dataset snapshot!")
            all_passed = False
    finally:
        shutil.rmtree(td)

    # -------------------------------------------------------------------------
    # N5: Tampered Target / Record Hash
    # -------------------------------------------------------------------------
    td, proto, mach, smf, dmf, fp = setup_test_env()
    try:
        with open(smf, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Tamper with target hash of first sample
        data["samples"][0]["target_sha256"] = "b" * 64
        with open(smf, "w", encoding="utf-8") as f:
            json.dump(data, f)

        passed = False
        try:
            validate_runtime_protocol(proto, mach, project_root=PROJECT_ROOT)
        except Exception as e:
            if "PROTOCOL_SAMPLE_MISMATCH" in str(e) or "Target hash mismatch" in str(e):
                passed = True
                print(f"[TEST N5] Tampered Target Hash -> CAUGHT: {e}")
                print("         Assert Fail-Closed Passed.")
            else:
                print(f"[TEST N5] FAILED: Unexpected exception: {e}")

        if not passed:
            print("[TEST N5] FAILED: Validator did not catch tampered target hash!")
            all_passed = False
    finally:
        shutil.rmtree(td)

    print("========================================================================")
    if all_passed:
        print(" ALL 5 NEGATIVE TESTS PASSED: 100% FAIL-CLOSED VERIFIED.")
        print("========================================================================")
        sys.exit(0)
    else:
        print(" NEGATIVE TESTS FAILED!")
        print("========================================================================")
        sys.exit(1)

if __name__ == "__main__":
    run_negative_tests()
