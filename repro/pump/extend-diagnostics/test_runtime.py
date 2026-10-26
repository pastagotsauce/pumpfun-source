"""Mutation checks against real hosted focused receipts when --built is supplied."""
import argparse
import base64
import copy
from pathlib import Path
import sys
import unittest
from solders.hash import Hash
from solders.instruction import AccountMeta, Instruction
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.transaction import Transaction
from recovery import ROOT, load_json, expected_message
from verify_runtime import validate, signed_payload, PROGRAM, PAYER, USER, TARGET, EVENT

BUILT = None


class ActualReceipts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if BUILT is None:
            raise unittest.SkipTest("requires actual hosted --built evidence; no fabricated successful receipt")
        cls.reports = {}
        for kind in ("baseline", "corrected"):
            base = BUILT / kind
            report = load_json(base / "runtime.json")
            record = (base / "build-record.json").read_bytes()
            binary = base / "candidate.so"
            validate(report, ROOT, binary, record)
            cls.reports[kind] = (report, binary, record)

    def rejects(self, mutate):
        for kind, (report, binary, record) in self.reports.items():
            with self.subTest(kind=kind):
                altered = copy.deepcopy(report)
                mutate(altered)
                with self.assertRaises((ValueError, KeyError, TypeError)):
                    validate(altered, ROOT, binary, record)

    def test_missing_diagnostic(self):
        def mutate(r):
            row = r["cases"][1]
            row["original"]["logs"].remove(expected_message(row["case"]))
        self.rejects(mutate)

    def test_extra_diagnostic(self):
        self.rejects(lambda r: r["cases"][1]["candidate"]["logs"].append(expected_message(r["cases"][1]["case"])))

    def test_reordered_diagnostic(self):
        def mutate(r):
            row = r["cases"][1]
            logs = row["original"]["logs"]
            message = expected_message(row["case"])
            logs.remove(message)
            logs.insert(0, message)
        self.rejects(mutate)

    def test_state_change(self):
        def mutate(r):
            r["cases"][1]["candidate"]["after"][str(TARGET)]["lamports"] += 1
        self.rejects(mutate)

    def test_missing_field(self):
        self.rejects(lambda r: r["cases"][0]["candidate"].pop("logs"))

    def test_build_binding_change(self):
        self.rejects(lambda r: r["build_binding"]["record"].update(returncode=1))

    def test_missing_case(self):
        self.rejects(lambda r: r["cases"].pop())

    def test_missing_pre_send_record(self):
        self.rejects(lambda r: r["pre_send_transactions"].pop())

    def test_failed_producer(self):
        self.rejects(lambda r: r["problems"].append("retained actual failure"))

    def test_different_valid_signed_transaction(self):
        idl = load_json(ROOT / "evidence/upstream/pump.json")
        discriminator = bytes(next(i for i in idl["instructions"] if i["name"] == "extend_account")["discriminator"])
        metas = [AccountMeta(TARGET, False, True), AccountMeta(USER, True, True),
                 AccountMeta(Pubkey.default(), False, False), AccountMeta(EVENT, False, False), AccountMeta(PROGRAM, False, False)]
        tx = Transaction.new_signed_with_payer([Instruction(PROGRAM, discriminator, metas)], PAYER,
            [Keypair.from_seed(bytes([227]) * 32), Keypair.from_seed(bytes([228]) * 32)], Hash.from_bytes(bytes([9]) * 32))
        encoded = base64.b64encode(bytes(tx)).decode()
        self.assertEqual(signed_payload(encoded, discriminator), 2)
        def mutate(r):
            self.assertNotEqual(r["cases"][0]["original"]["transaction_base64"], encoded)
            r["cases"][0]["candidate"]["transaction_base64"] = encoded
            r["pre_send_transactions"][1]["transaction_base64"] = encoded
        self.rejects(mutate)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--built", type=Path, required=True)
    args, rest = parser.parse_known_args()
    BUILT = args.built.resolve()
    unittest.main(argv=[sys.argv[0], *rest])
