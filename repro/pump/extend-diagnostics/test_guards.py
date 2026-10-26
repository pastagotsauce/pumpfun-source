"""Offline guard regressions; no compiler or target execution."""
import base64
import copy
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
from solders.hash import Hash
from solders.instruction import AccountMeta, Instruction
from solders.keypair import Keypair
from solders.transaction import Transaction
import recovery
from recovery import PACKAGE, ROOT, SOURCE, load_json, require
from verify_evidence import original_proof, saved_receipts
from verify_runtime import signed_payload, PAYER, USER, TARGET, EVENT, PROGRAM
from linux_build import source_hashes


class Guards(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = (ROOT / "evidence/original/pump/deployed.so").read_bytes()
        cls.source = (ROOT / SOURCE).read_bytes()
        cls.idl = load_json(ROOT / "evidence/upstream/pump.json")
        cls.discriminator = bytes(next(i for i in cls.idl["instructions"] if i["name"] == "extend_account")["discriminator"])
        cls.receipts = load_json(PACKAGE / "inputs/selected-extension.json.gz")

    def test_real_original_and_raw_receipts(self):
        self.assertEqual(original_proof(self.original)["shared_log_call"], 245032)
        result = saved_receipts()
        self.assertEqual(result["surfpool_signature_slots"], 62)
        self.assertEqual(result["differential_signatures"], 1208)

    def test_original_branch_mutation_rejected(self):
        raw = bytearray(self.original)
        raw[244768] = 0x5d
        with self.assertRaises(ValueError):
            original_proof(bytes(raw))

    def test_formatter_pointer_mutation_rejected(self):
        raw = bytearray(self.original)
        raw[1825608:1825624], raw[1825624:1825640] = raw[1825624:1825640], raw[1825608:1825624]
        with self.assertRaises(ValueError):
            original_proof(bytes(raw))

    def test_source_patch_is_single_bounded_replacement(self):
        new = recovery.patched_source(self.source)
        self.assertEqual(new.replace(recovery.NEW, recovery.OLD), self.source)
        self.assertEqual(recovery.digest(new), recovery.CORRECTED_SHA)

    def test_different_source_is_rejected(self):
        with self.assertRaises(ValueError):
            recovery.patched_source(self.source.replace(b"current >= size", b"current > size"))

    def test_rehashed_input_cannot_replace_fixed_seal(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp)
            pins = load_json(PACKAGE / "pins.json")
            pins["inputs"]["selected-signed.json.gz"] = "0" * 64
            (target / "pins.json").write_text(json.dumps(pins))
            with patch.object(recovery, "PACKAGE", target), self.assertRaises(ValueError):
                recovery.pinned_source()

    def test_hidden_cargo_config_is_an_extra_source(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "lib.rs").write_text("fn f() {}")
            names = {"lib.rs"}
            self.assertEqual(set(source_hashes(root, names)), names)
            (root / ".cargo").mkdir()
            (root / ".cargo/config.toml").write_text('[build]\nrustflags = ["-Copt-level=0"]')
            with self.assertRaises(ValueError):
                source_hashes(root, names)

    def test_real_selected_signature_and_routing(self):
        row = next(r for r in self.receipts["cases"] if r["case"]["name"] == "BondingCurve-166")
        self.assertEqual(signed_payload(row["original"]["transaction_base64"], self.discriminator), 2)

    def test_raw_signature_corruption_rejected(self):
        raw = bytearray(base64.b64decode(self.receipts["cases"][8]["original"]["transaction_base64"]))
        raw[2] ^= 1
        with self.assertRaises(ValueError):
            signed_payload(base64.b64encode(raw).decode(), self.discriminator)

    def signed_test_input(self, data, writable=True):
        metas = [AccountMeta(TARGET, False, writable), AccountMeta(USER, True, True),
                 AccountMeta(recovery_pubkey_default(), False, False), AccountMeta(EVENT, False, False), AccountMeta(PROGRAM, False, False)]
        tx = Transaction.new_signed_with_payer([Instruction(PROGRAM, data, metas)], PAYER,
            [Keypair.from_seed(bytes([227]) * 32), Keypair.from_seed(bytes([228]) * 32)], Hash.default())
        return base64.b64encode(bytes(tx)).decode()

    def test_valid_signature_wrong_instruction_rejected(self):
        with self.assertRaises(ValueError):
            signed_payload(self.signed_test_input(b"\0" * 8), self.discriminator)

    def test_valid_signature_wrong_privilege_rejected(self):
        with self.assertRaises(ValueError):
            signed_payload(self.signed_test_input(self.discriminator, False), self.discriminator)

    def test_only_compute_logs_are_excluded(self):
        lines = ["Program abc consumed 10 of 20 compute units", "Program log: Left: 1",
                 "Program log: Account already has the correct size", "Program log: Account already has the correct size"]
        self.assertEqual(recovery.full_logs_without_compute(lines), lines[1:])

    def test_focused_domains_include_all_four_growth_equal_and_oversized(self):
        cases = recovery.focused_cases()
        self.assertEqual(len(cases), 12)
        for kind, target in recovery.TARGETS.items():
            self.assertEqual([c["size"] for c in cases if c["kind"] == kind], [target - 1, target, target + 1])


def recovery_pubkey_default():
    from solders.pubkey import Pubkey
    return Pubkey.default()


if __name__ == "__main__":
    unittest.main()
