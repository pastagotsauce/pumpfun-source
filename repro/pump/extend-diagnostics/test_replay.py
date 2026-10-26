"""Regression checks using the actual failed attempt, without relabelling it."""
import copy
import json
import unittest
from recovery import ROOT, PACKAGE, load_json, BASELINE_SHA
from replay import authenticated_members, verify_build, inherited_acceptance
from verify_runtime import fixture_effects, PAYER, TARGET, signed_payload


class ReplayGuards(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        folder = PACKAGE / "results/attempt-1"
        cls.archive = (folder / "artifact.zip").read_bytes()
        cls.metadata = load_json(folder / "artifact.json")
        cls.members = authenticated_members(cls.archive, cls.metadata)
        cls.failed = json.loads(cls.members["baseline/runtime.json"])
        idl = load_json(ROOT / "evidence/upstream/pump.json")
        cls.accounts = {r["name"]: bytes(r["discriminator"]) for r in idl["accounts"]}
        cls.instruction = bytes(next(r for r in idl["instructions"] if r["name"] == "extend_account")["discriminator"])

    def test_authentic_builds_survive_failed_runtime(self):
        records = verify_build(self.members, ROOT)
        self.assertEqual(set(records), {"baseline", "corrected"})
        self.assertEqual(self.failed["status"], "failed")
        self.assertEqual(self.failed["problems"], ["no-growth path changed effects"])

    def test_all_actual_case_shapes_with_new_schema_check(self):
        checks = 0
        unique = set()
        for row in self.failed["cases"]:
            case = row["case"]
            self.assertEqual(row["original"]["transaction_base64"], row["candidate"]["transaction_base64"])
            for side in ("original", "candidate"):
                fixture_effects(row[side], case, self.accounts[case["kind"]])
                checks += signed_payload(row[side]["transaction_base64"], self.instruction)
                unique.add(row[side]["transaction_base64"])
        self.assertEqual((checks, len(unique)), (48, 1))
        self.assertEqual(self.failed["status"], "failed")

    def test_wrong_empty_inner_shapes_rejected(self):
        for wrong in ([], [[], []], [[{"instruction": "unexpected"}]]):
            with self.subTest(shape=wrong):
                row = copy.deepcopy(self.failed["cases"][1])
                row["original"]["inner"] = wrong
                with self.assertRaises(ValueError):
                    fixture_effects(row["original"], row["case"], self.accounts["BondingCurve"])

    def test_changed_target_rejected(self):
        row = copy.deepcopy(self.failed["cases"][1])
        row["original"]["after"][str(TARGET)]["lamports"] += 1
        with self.assertRaises(ValueError):
            fixture_effects(row["original"], row["case"], self.accounts["BondingCurve"])

    def test_unauthorized_payer_delta_rejected(self):
        row = copy.deepcopy(self.failed["cases"][1])
        row["original"]["after"][str(PAYER)]["lamports"] -= 1
        with self.assertRaises(ValueError):
            fixture_effects(row["original"], row["case"], self.accounts["BondingCurve"])

    def test_wrong_growth_rent_rejected(self):
        row = copy.deepcopy(self.failed["cases"][0])
        row["original"]["after"][str(TARGET)]["lamports"] += 1
        with self.assertRaises(ValueError):
            fixture_effects(row["original"], row["case"], self.accounts["BondingCurve"])

    def test_changed_zip_rejected(self):
        with self.assertRaises(ValueError):
            authenticated_members(self.archive + b"\0", self.metadata)

    def test_changed_provider_identity_rejected(self):
        altered = copy.deepcopy(self.metadata)
        altered["id"] += 1
        with self.assertRaises(ValueError):
            authenticated_members(self.archive, altered)

    def test_changed_build_source_rejected(self):
        altered = dict(self.members)
        altered["source/baseline/programs/pump/src/extend.rs"] += b"\n"
        with self.assertRaises(ValueError):
            verify_build(altered, ROOT)

    def test_existing_inherited_schema_and_signatures(self):
        prior = load_json(PACKAGE / "inputs/selected-extension.json.gz")
        checked = inherited_acceptance(prior, BASELINE_SHA)
        self.assertEqual(checked["raw_signature_checks"], 1208)


if __name__ == "__main__":
    unittest.main()
