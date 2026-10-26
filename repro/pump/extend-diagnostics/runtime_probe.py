"""Twelve ordinary signed local extension cases; no RPC, deployment or bypass."""
import argparse
import importlib.metadata
import json
from pathlib import Path
import sys
import traceback
from recovery import ROOT, PACKAGE, ORIGINAL_SHA, digest, require, focused_cases, load_json
from verify_runtime import validate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=ROOT)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--candidate-sha256", required=True)
    parser.add_argument("--expect", choices=("rebuilt-baseline", "corrected"), required=True)
    parser.add_argument("--build-record", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    require(not args.output.exists(), "output already exists")
    require(digest(args.candidate.read_bytes()) == args.candidate_sha256, "candidate changed")
    require(digest((args.repo / "evidence/original/pump/deployed.so").read_bytes()) == ORIGINAL_SHA, "original changed")
    record = args.build_record.read_bytes()
    names = ["scripts/pump_extend_differential.py", "evidence/upstream/pump.json",
             "repro/pump/extend-diagnostics/runtime_probe.py", "repro/pump/extend-diagnostics/recovery.py",
             "repro/pump/extend-diagnostics/verify_runtime.py"]
    pins = load_json(PACKAGE / "pins.json")
    require(all(digest((args.repo / name).read_bytes()) == expected for name, expected in pins["runtime_inputs"].items()), "inherited runtime input changed")
    report = {"status": "running", "problems": [], "mode": args.expect, "cases_spec": focused_cases(), "cases": [],
              "pre_send_transactions": [], "attempting": None,
              "original_sha256": ORIGINAL_SHA, "candidate_sha256": args.candidate_sha256,
              "build_binding": {"sha256": digest(record), "record": json.loads(record)},
              "inputs": {name: digest((args.repo / name).read_bytes()) for name in names},
              "solders_version": importlib.metadata.version("solders")}
    def save():
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n")
    save()
    try:
        require(report["solders_version"] == "0.27.1", "wrong runtime dependency")
        sys.path.insert(0, str(args.repo / "scripts"))
        import pump_extend_differential as inherited
        original_vm_class = inherited.LiteSVM
        class ObservedVM:
            def __init__(self):
                self.inner = original_vm_class()
            def with_transaction_history(self, count):
                self.inner.with_transaction_history(count)
                return self
            def __getattr__(self, name):
                return getattr(self.inner, name)
            def send_transaction(self, transaction):
                import base64
                transaction.verify()
                report["pre_send_transactions"].append({**report["attempting"],
                    "transaction_base64": base64.b64encode(bytes(transaction)).decode()})
                save()
                return self.inner.send_transaction(transaction)
        inherited.LiteSVM = ObservedVM
        for index, case in enumerate(focused_cases()):
            row = {"case": case}
            report["cases"].append(row)
            for side, binary in (("original", inherited.ORIGINAL), ("candidate", args.candidate)):
                report["attempting"] = {"case_index": index, "side": side, "case": case}
                save()
                row[side] = inherited.run(case, binary)
                save()
        inherited.LiteSVM = original_vm_class
        report["attempting"] = None
        report["status"] = "passed"
        report["validation"] = validate(report, args.repo, args.candidate, record)
    except Exception as error:
        report["status"] = "failed"
        report["problems"].append(str(error))
        report["traceback"] = traceback.format_exc()
        raise
    finally:
        save()


if __name__ == "__main__":
    main()
