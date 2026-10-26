"""Offline checks against authenticated actual successful and failed receipts."""
import json
from pathlib import Path
import shutil
import tempfile
import unittest
import test_runtime as actual_tests
from recovery import ROOT, PACKAGE, load_json
from verify_runtime import validate
from verify_saved import verify, replay_contents, extract_for_checks, rows_for_files, executable_comparison


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


class ExecutableExtentGuards(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = (ROOT / "evidence/original/pump/deployed.so").read_bytes()
        contents = replay_contents((PACKAGE / "results/replay-2/artifact.zip").read_bytes())
        cls.candidates = {kind: contents[kind + "/candidate.so"] for kind in ("baseline", "corrected")}

    def test_full_declared_file_extent_keeps_terminal_zero_bytes(self):
        result = executable_comparison(self.original, self.candidates)
        self.assertEqual(result["original_layout"]["elf_extent"], 1934800)
        self.assertEqual(self.original[1934800 - 1], 0)
        self.assertEqual(result["original_allocation_remainder"]["bytes"], 8550915)
        for row in result["outputs"].values():
            self.assertEqual(row["comparison"]["original_bytes"], 1934800)
            self.assertEqual(row["layout"]["trailing_bytes"], 0)
            self.assertFalse(row["comparison"]["full_byte_equality"])

    def test_nonzero_allocation_remainder_rejected(self):
        altered = bytearray(self.original)
        altered[1934800] = 1
        with self.assertRaisesRegex(ValueError, "allocation remainder is nonzero"):
            executable_comparison(bytes(altered), self.candidates)

    def test_extra_zero_after_compiler_elf_rejected(self):
        altered = dict(self.candidates)
        altered["corrected"] += b"\0"
        with self.assertRaisesRegex(ValueError, "beyond its declared ELF extent"):
            executable_comparison(self.original, altered)


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
