"""Offline regression tests for LLST's release-critical integrity gates."""

import hashlib
import json
import os
import sqlite3
import sys
import tempfile
import types
import unittest
from pathlib import Path

import yaml

# These tests exercise persisted artifacts only; model loading is deliberately
# outside their scope.  Provide the import surface needed by the workload
# module so a developer can run the integrity suite without a model runtime.
if "transformers" not in sys.modules:
    transformers_stub = types.ModuleType("transformers")
    transformers_stub.AutoTokenizer = object
    sys.modules["transformers"] = transformers_stub

from llst.config_loader import ConfigError, load_resolved_config, redacted_config
from llst.dataset_lock import DatasetSnapshotError, compute_dataset_snapshot_hash, verify_dataset_snapshots
from llst.performance.runner import _collect_perf_artifacts, verify_performance_execution_manifest
from llst.performance.workload_generator import sha256_file, verify_workload_manifest


class IntegrityGateTests(unittest.TestCase):
    def _write_yaml(self, path, value):
        path.write_text(yaml.safe_dump(value), encoding="utf-8")

    def _machine_profile(self):
        return {
            "model": {"name": "test-model", "backend": "test"},
            "api": {
                "base_url": "http://127.0.0.1:8082/v1",
                "perf_url": "http://127.0.0.1:8082/v1",
                "api_key_env": "LLST_TEST_API_KEY",
            },
            "tokenizer": {"path": "/tmp/tokenizer", "fingerprint": "/tmp/fingerprint.json"},
            "runtime": {"context_length": 131072},
            "output": {"root": "/tmp/llst-output"},
        }

    def test_config_requires_complete_contract_and_redacts_key(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            protocol_path = root / "protocol.yaml"
            machine_path = root / "machine.yaml"
            self._write_yaml(protocol_path, {"protocol": {"version": "1.0"}})
            machine = self._machine_profile()
            machine["api"].pop("perf_url")
            self._write_yaml(machine_path, machine)
            with self.assertRaisesRegex(ConfigError, "api.perf_url"):
                load_resolved_config(protocol_path, machine_path)

            machine = self._machine_profile()
            self._write_yaml(machine_path, machine)
            old_value = os.environ.get("LLST_TEST_API_KEY")
            os.environ["LLST_TEST_API_KEY"] = "secret-must-not-be-persisted"
            try:
                resolved = load_resolved_config(protocol_path, machine_path)
            finally:
                if old_value is None:
                    os.environ.pop("LLST_TEST_API_KEY", None)
                else:
                    os.environ["LLST_TEST_API_KEY"] = old_value
            self.assertEqual(resolved["machine"]["api_key"], "secret-must-not-be-persisted")
            self.assertEqual(redacted_config(resolved)["machine"]["api_key"], "<redacted>")

    def test_dataset_snapshot_is_required_and_byte_locked(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            protocol_dir = root / "protocols"
            manifest_dir = protocol_dir / "v1"
            manifest_dir.mkdir(parents=True)
            protocol_path = protocol_dir / "standard.yaml"
            self._write_yaml(protocol_path, {"capability": {"dataset_manifest": "v1/dataset_manifest.json"}})

            empty_manifest = {"benchmarks": {}}
            (manifest_dir / "dataset_manifest.json").write_text(json.dumps(empty_manifest), encoding="utf-8")
            with self.assertRaisesRegex(DatasetSnapshotError, "DATASET_MANIFEST_INVALID"):
                verify_dataset_snapshots(protocol_path, cache_root=root / "cache")

            from llst.dataset_lock import DATASET_CACHE_DIRS

            cache_root = root / "cache"
            benchmarks = {}
            for benchmark, directory in DATASET_CACHE_DIRS.items():
                arrow_dir = cache_root / directory / "snapshot"
                arrow_dir.mkdir(parents=True)
                (arrow_dir / "data.arrow").write_bytes(f"{benchmark}-locked".encode("utf-8"))
                benchmarks[benchmark] = {
                    "dataset_snapshot_sha256": compute_dataset_snapshot_hash(directory, cache_root=cache_root)
                }
            (manifest_dir / "dataset_manifest.json").write_text(
                json.dumps({"benchmarks": benchmarks}), encoding="utf-8"
            )
            verified = verify_dataset_snapshots(protocol_path, cache_root=cache_root)
            self.assertEqual(set(verified), set(DATASET_CACHE_DIRS))

            changed = cache_root / DATASET_CACHE_DIRS["ifeval"] / "snapshot" / "data.arrow"
            changed.write_bytes(b"tampered")
            with self.assertRaisesRegex(DatasetSnapshotError, "DATASET_SNAPSHOT_MISMATCH"):
                verify_dataset_snapshots(protocol_path, cache_root=cache_root)

    def test_workload_manifest_rejects_byte_and_shape_tampering(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workload = root / "workload_isl_4.jsonl"
            workload.write_text("[1,2,3,4]\n[5,6,7,8]\n", encoding="utf-8")
            manifest = {
                "cases": {
                    "4": {
                        "file": workload.name,
                        "sha256": sha256_file(workload),
                        "requests_count": 2,
                        "prompt_length": 4,
                    }
                }
            }
            verified = verify_workload_manifest(manifest, root)
            self.assertEqual(verified["4"]["requests_count"], 2)

            workload.write_text("[1,2,3,4]\n[5,6,7,999]\n", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "WORKLOAD_FILE_MISMATCH"):
                verify_workload_manifest(manifest, root)

    def test_performance_artifact_audit_rejects_incomplete_or_failed_database(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for filename in ("benchmark_args.json", "benchmark_percentile.json", "benchmark_summary.json"):
                (root / filename).write_text("{}", encoding="utf-8")
            database = root / "benchmark_data.db"
            with sqlite3.connect(database) as connection:
                connection.execute("CREATE TABLE result (success INTEGER)")
                connection.executemany("INSERT INTO result VALUES (?)", [(1,), (0,)])

            with self.assertRaisesRegex(RuntimeError, "PERFORMANCE_EXECUTION_MISMATCH"):
                _collect_perf_artifacts(root, expected_requests=2)

            with sqlite3.connect(database) as connection:
                connection.execute("UPDATE result SET success = 1")
            artifacts, audit = _collect_perf_artifacts(root, expected_requests=2)
            self.assertEqual(audit, {"records": 2, "successful": 2})
            self.assertEqual(len(artifacts), 4)

    def test_performance_execution_manifest_requires_unambiguous_artifact_root(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workload_dir = root / "workload"
            output_dir = root / "performance" / "isl_4_osl_1" / "result"
            workload_dir.mkdir(parents=True)
            output_dir.mkdir(parents=True)
            workload_file = workload_dir / "workload_isl_4.jsonl"
            workload_manifest = workload_dir / "workload_manifest.json"
            workload_file.write_text("[1,2,3,4]\n", encoding="utf-8")
            workload_manifest.write_text("{}", encoding="utf-8")
            for filename in ("benchmark_args.json", "benchmark_percentile.json", "benchmark_summary.json"):
                (output_dir / filename).write_text("{}", encoding="utf-8")
            database = output_dir / "benchmark_data.db"
            with sqlite3.connect(database) as connection:
                connection.execute("CREATE TABLE result (success INTEGER)")
                connection.execute("INSERT INTO result VALUES (1)")
            artifacts, database_audit = _collect_perf_artifacts(output_dir, expected_requests=1)
            manifest = {
                "workload_manifest": workload_manifest.name,
                "workload_manifest_sha256": sha256_file(workload_manifest),
                "smoke": False,
                "cases": {
                    "4": {
                        "workload_file": workload_file.name,
                        "workload_sha256": sha256_file(workload_file),
                        "output_dir": str(output_dir.relative_to(root)),
                        "artifacts": artifacts,
                        "database": database_audit,
                    }
                },
            }
            execution_path = root / "performance" / "execution_manifest.json"
            execution_path.write_text(json.dumps(manifest), encoding="utf-8")
            self.assertEqual(verify_performance_execution_manifest(root)["cases"]["4"]["database"]["records"], 1)

            manifest["cases"]["4"]["output_dir"] = "../outside"
            execution_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "PERFORMANCE_EXECUTION_MANIFEST_INVALID"):
                verify_performance_execution_manifest(root)


if __name__ == "__main__":
    unittest.main()
