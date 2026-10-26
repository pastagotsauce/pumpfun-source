"""Reject changes to the evidence that would invalidate the audit's claims."""
import importlib.util
import json
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("metaplex_branch_audit", HERE / "verify.py")
audit_verify = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit_verify)


class EvidenceMutationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.audit = json.loads((HERE / "audit.json").read_bytes())
        cls.entries = {entry["id"]: entry for entry in cls.audit["repo_inputs"]}
        cls.candidate = audit_verify.repo_input(HERE.parents[2], cls.entries["candidate11"])

    def test_current_guard_is_the_error_taken_direction(self):
        actual = audit_verify.decode_guard(self.candidate, self.audit["guard_file_offset"],
                                          self.audit["guards"]["candidate11"])
        self.assertEqual(actual["target"], 238984)

    def test_complementing_opcode_without_swapping_operands_is_rejected(self):
        altered = bytearray(self.candidate)
        altered[self.audit["guard_file_offset"]] = 0x3d
        with self.assertRaisesRegex(ValueError, "guard opcode"):
            audit_verify.decode_guard(altered, self.audit["guard_file_offset"],
                                      self.audit["guards"]["candidate11"])

    def test_branch_displacement_change_is_rejected(self):
        altered = bytearray(self.candidate)
        altered[self.audit["guard_file_offset"] + 2] ^= 1
        with self.assertRaisesRegex(ValueError, "destination mismatch"):
            audit_verify.decode_guard(altered, self.audit["guard_file_offset"],
                                      self.audit["guards"]["candidate11"])

    def test_same_length_executable_change_is_rejected(self):
        altered = bytearray(self.candidate)
        altered[-1] ^= 1
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            audit_verify.checked(altered, self.entries["candidate11"])

    def test_allocation_padding_cannot_satisfy_raw_output_identity(self):
        with self.assertRaisesRegex(ValueError, "size mismatch"):
            audit_verify.checked(self.candidate + bytes(86543), self.entries["candidate11"])

    def test_revised_public_ref_receipt_is_rejected(self):
        entry = self.audit["ref_observations"][0]
        raw = bytearray((HERE / entry["path"]).read_bytes())
        raw[raw.index(b'"sha"') + 8] ^= 1
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            audit_verify.checked(raw, entry)


if __name__ == "__main__":
    unittest.main()
