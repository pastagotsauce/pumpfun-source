"""Offline checks against authenticated actual successful and failed receipts."""
import json
from pathlib import Path
import shutil
import tempfile
import unittest
import test_runtime as actual_tests
from recovery import ROOT, PACKAGE, load_json
from verify_runtime import validate
from verify_saved import verify, replay_contents, extract_for_checks, rows_for_files


class SavedArtifactGuards(unittest.TestCase):
    def test_actual_saved_evidence(self):
        result = verify()
        self.assertEqual(result["corrected_inherited"]["raw_signature_checks"], 1208)
        self.assertEqual(result["replay_new_builds"], 0)
        self.assertFalse(result["whole_original_comparison"]["corrected"]["full_byte_equality"])

    def test_modified_actual_zip_rejected(self):
        with self.assertRaisesRegex(ValueError, "ZIP differs"):
            replay_contents((PACKAGE / "results/replay-2/artifact.zip").read_bytes() + b"\0")

    def assert_rehashed_receipt_rejected(self, relative, mutate):
        with tempfile.TemporaryDirectory(prefix="pump-evidence-mutation-") as temporary:
            package = Path(temporary) / "package"
            shutil.copytree(PACKAGE, package, ignore=shutil.ignore_patterns("__pycache__"))
            path = package / relative
            data = load_json(path)
            mutate(data)
            path.write_bytes((json.dumps(data, indent=2) + "\n").encode())
            manifest = {"files": rows_for_files(package, exclude_manifest=True)}
            (package / "manifest.json").write_bytes((json.dumps(manifest, indent=2) + "\n").encode())
            with self.assertRaisesRegex(ValueError, "immutable provider/raw evidence seal"):
                verify(package, ROOT)

    def test_rehashed_provider_rewrite_rejected(self):
        self.assert_rehashed_receipt_rejected("results/replay-2/run.json", lambda data: data.update(head_sha="0" * 40))

    def test_rehashed_historical_failure_relabel_rejected(self):
        self.assert_rehashed_receipt_rejected("results/attempt-1/run.json", lambda data: data.update(conclusion="success"))


class SavedActualReceipts(actual_tests.ActualReceipts):
    """Run the same ten mutations on real sealed receipts during offline discovery."""
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="pump-saved-receipts-")
        cls.addClassCleanup(cls.temporary.cleanup)
        folder = Path(cls.temporary.name) / "evidence"
        contents = replay_contents((PACKAGE / "results/replay-2/artifact.zip").read_bytes())
        extract_for_checks(contents, folder)
        cls.reports = {}
        for kind in ("baseline", "corrected"):
            base = folder / kind
            report = load_json(base / "runtime.json")
            record = (base / "build-record.json").read_bytes()
            binary = base / "candidate.so"
            validate(report, ROOT, binary, record)
            cls.reports[kind] = (report, binary, record)


if __name__ == "__main__":
    unittest.main()
