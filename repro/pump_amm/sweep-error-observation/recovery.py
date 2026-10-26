"""Shared bindings for the bounded sweep recovery; prior package stays sealed."""
import base64
import gzip
import importlib.util
import json
from pathlib import Path
import sys

PACKAGE = Path(__file__).resolve().parent
ROOT = PACKAGE.parents[2]
PRIOR = ROOT / "repro/pump_amm/error-recovery-next"
sys.path.insert(0, str(PRIOR))
import verify as liquidity
import verify_runtime as liquidity_runtime
from solders.pubkey import Pubkey
from solders.transaction import Transaction

digest, require = liquidity.digest, liquidity.require
ORIGINAL_SHA = liquidity.ORIGINAL_SHA
BASELINE_SHA = "cc2326ba730ccbbe85af8e9860833382e8d3e33b7e065c6ae80cfc838f80f4aa"
PRIOR_SHA = "ec8aa1dfe54221eb19f332cac459d16a65cab0aa3064bcabf7c452211702e149"
PRIOR_RECORD_SHA = "f197e7eab61b41ac4bbca609ec180ef0e7b7fd0aded0caef95247d8201f10791"
BASE_RECORD_SHA = "5d02cfce41c1a703a006ea6fbd3a8997c73bd6b0b793e5b8bbd4c0c9e38162e1"
PROBE_SHA = "447326e1c7d5bcbc325ae4f94fab1cbece38b2c2f49d612b6fab360cdc4e7ce8"
SWEEP = "programs/pump-amm/src/sweep.rs"
OMITTED = "programs/pump-amm/vendor/solana-pubkey/.cargo_vcs_info.json"
INPUTS = liquidity_runtime.INPUTS | {
    "scripts/pump_amm_sweep_differential.py", "evidence/dependencies/associated_token/deployed.so"}
PROGRAM, PAYER, OUTSIDER = liquidity_runtime.PROGRAM, liquidity_runtime.PAYER, liquidity_runtime.OUTSIDER
TOKEN = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
ATA = "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL"


def load_prior_builder():
    spec = importlib.util.spec_from_file_location("prior_amm_linux_build", PRIOR / "linux_build.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_report(path):
    raw = path.read_bytes()
    return gzip.decompress(raw) if raw.startswith(b"\x1f\x8b") else raw


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((json.dumps(value, indent=2, sort_keys=True) + "\n").encode())


def patched_sweep(raw):
    before = (b"        require_keys_eq!(\n"
              b"            a.pool_quote_token_account.owner,\n"
              b"            a.pool.key(),\n")
    after = (b"        require!(\n"
             b"            a.pool_quote_token_account.owner == a.pool.key(),\n")
    zero = b"    if amount == 0 {\n        return Ok(());\n"
    logged = (b"    if amount == 0 {\n"
              b'        msg!("Nothing to sweep for fee bucket {}", u8::from(creator));\n'
              b"        return Ok(());\n")
    require(raw.count(before) == raw.count(zero) == 1, "unexpected sweep source layout")
    return raw.replace(before, after).replace(zero, logged)


def prior_source(repo):
    prior = repo / "repro/pump_amm/error-recovery-next/results/build"
    raw = (prior / "corrected/build-record.json").read_bytes()
    require(digest(raw) == PRIOR_RECORD_SHA, "prior build record changed")
    record = json.loads(raw)
    require(record["candidate_sha256"] == PRIOR_SHA and record["accepted_build"], "prior output changed")
    require(digest((prior / "corrected/candidate.so").read_bytes()) == PRIOR_SHA, "prior binary changed")
    expected = record["source_sha256"]
    require(expected == record["source_after_sha256"] and len(expected) == 30, "prior source manifest changed")
    snapshot = prior / "source/corrected"
    actual = {p.relative_to(snapshot).as_posix() for p in snapshot.rglob("*") if p.is_file()}
    require(actual == set(expected) - {OMITTED}, "unexpected prior source omission set")
    sources = {name: (repo / name if name == OMITTED else snapshot / name) for name in expected}
    require(all(digest(path.read_bytes()) == expected[name] for name, path in sources.items()), "source input mismatch")
    return expected, sources


def expected_source(repo):
    expected, sources = prior_source(repo)
    expected = dict(expected)
    expected[SWEEP] = digest(patched_sweep(sources[SWEEP].read_bytes()))
    return expected


def check_build(repo, candidate, record_bytes):
    record = json.loads(record_bytes)
    require(record["kind"] == "liquidity-and-sweep-corrected" and record["accepted_build"] is True and
            record["returncode"] == 0 and record["source_unchanged"] is True, "build not accepted")
    require(record["candidate_sha256"] == digest(candidate), "build/binary mismatch")
    require(record["source_sha256"] == record["source_after_sha256"] == expected_source(repo), "unexpected combined source")
    require(record["prior_build_record_sha256"] == PRIOR_RECORD_SHA and record["prior_candidate_sha256"] == PRIOR_SHA,
            "wrong prior build binding")
    require(record["source_patch_sha256"] == digest((PACKAGE / "source.patch").read_bytes()), "wrong patch binding")
    return record


def fixture_inputs(repo):
    fixture = json.loads((repo / liquidity.FIXTURE_PATH).read_bytes())
    config = json.loads((repo / "research/imported-lab/analysis/pump_fun/config-snapshot.json").read_bytes())
    config = next(row for row in config["accounts"] if row["program_name"] == "pump_amm")
    idl = json.loads((repo / "evidence/upstream/pump_amm.json").read_bytes())
    return fixture, config, {row["name"]: row for row in idl["instructions"]}


def roster(creator=True):
    rows = [("sweep_protocol_fee", mode, amount) for mode in
            ("ordinary", "alias_pool_owner", "alias_wrong_owner") for amount in (0, 1, 1000)]
    return rows + ([("sweep_creator_fee", "ordinary", n) for n in (0, 1, 1000)] if creator else [])


def check_transaction(raw, row, fixture, config, instruction):
    tx = Transaction.from_bytes(raw)
    require(bytes(tx) == raw, "transaction did not round-trip")
    message = tx.message
    require(len(tx.signatures) == message.header.num_required_signatures == 1 and str(message.account_keys[0]) == PAYER,
            "wrong signer")
    require(tx.signatures[0].verify(message.account_keys[0], bytes(message)), "invalid raw signature")
    require(len(message.instructions) == 1, "wrong instruction count")
    ix = message.instructions[0]
    require(str(message.account_keys[ix.program_id_index]) == PROGRAM and bytes(ix.data) == bytes(instruction["discriminator"]),
            "wrong signed instruction")
    pool_data = base64.b64decode(fixture["accounts"]["pool"]["data_base64"], validate=True)
    if row["mode"] != "ordinary":
        recipient = Pubkey.from_string(fixture["pool"])
    elif row["instruction"] == "sweep_creator_fee":
        recipient = Pubkey.find_program_address([b"creator_vault", pool_data[211:243]], Pubkey.from_string(PROGRAM))[0]
    else:
        config_data = base64.b64decode(config["data_base64"], validate=True)
        recipient = Pubkey.from_bytes(config_data[57:89])
    ata = Pubkey.find_program_address([bytes(recipient), bytes(Pubkey.from_string(TOKEN)),
                                      bytes(Pubkey.from_string(fixture["keys"]["quote_mint"]))], Pubkey.from_string(ATA))[0]
    expected = [PAYER, config["address"], fixture["pool"], fixture["keys"]["quote_mint"], TOKEN,
                fixture["keys"]["pool_quote_token_account"], str(recipient), str(ata), str(Pubkey.default()), ATA,
                str(Pubkey.find_program_address([b"__event_authority"], Pubkey.from_string(PROGRAM))[0]), PROGRAM]
    require([str(message.account_keys[i]) for i in ix.accounts] == expected, "wrong signed account route")
    require(set(map(str, message.account_keys)) == set(expected), "extra unused signed account")
    writable = {expected[i] for i, account in enumerate(instruction["accounts"]) if account.get("writable")}
    header = message.header
    for index, key in enumerate(message.account_keys):
        writable_actual = (index < header.num_required_signatures - header.num_readonly_signed_accounts or
                           header.num_required_signatures <= index < len(message.account_keys) - header.num_readonly_unsigned_accounts)
        require(writable_actual == (str(key) in writable), "wrong signed privileges")
    return 1
