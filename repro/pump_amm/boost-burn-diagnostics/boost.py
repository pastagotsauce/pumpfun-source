"""Source, original-byte and fixture bindings for five boost/burn diagnostics."""
import base64
import json
from pathlib import Path
import re
import struct
import sys

PACKAGE = Path(__file__).resolve().parent
ROOT = PACKAGE.parents[2]
PRIOR = ROOT / "repro/pump_amm/creator-fee-diagnostics"
sys.path.insert(0, str(PRIOR))
import migration as creator

sweep, liquidity, liquidity_runtime = creator.sweep, creator.liquidity, creator.liquidity_runtime
digest, require, write_json, read_report = creator.digest, creator.require, creator.write_json, creator.read_report
load_prior_builder = creator.load_prior_builder
ORIGINAL_SHA = creator.ORIGINAL_SHA
PRIOR_SHA = "7f6c301e7d39ced26a6280ae1053db6cff76a01c67dd9c4627e6022cb8384d52"
PRIOR_RECORD_SHA = "ac14e9f4477466fce3705aa6d621a965bef9a8fc6f957bab26a902b0947e65e3"
SOURCE = "programs/pump-amm/src/boost_burn.rs"
SOURCE_SHA = "92310c452df7fa7352dde64f64aaf616a6857af61732aee017c5149affbe40d4"
RECEIPT = "repro/pump_amm/owner6048-v144/runtime/runtime-01/boost_burn.json.gz"
RECEIPT_SHA = "03aa0b2865bd81ba3d51d5d0e7296bb682d898725b2f0406e47d18b840ef1e9c"
RAW_SHA = "1d703b5cbc445448f3b92e4e16aaa9cf57bcdfb3155f604cbe7752c8f80e6a69"
ORIGIN = "programs/pump-amm/src/instructions/boost.rs"
INPUTS = creator.INPUTS | {"scripts/pump_amm_boost_burn_differential.py", "scripts/pump_amm_legacy_sell_differential.py",
                          "scripts/pump_amm_trade_v2_differential.py"}
MAX = 2**64 - 1
TOKEN22 = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"
CHANGES = (
    ("require!(used > 0, PumpAmmError::ZeroQuoteAmount);", "require_gt!(used, 0, PumpAmmError::ZeroQuoteAmount);"),
    ("require!(net > 0, PumpAmmError::ZeroQuoteAmount);", "require_gt!(net, 0, PumpAmmError::ZeroQuoteAmount);"),
    ("require!(burned > 0, PumpAmmError::ZeroBaseAmount);", "require_gt!(burned, 0, PumpAmmError::ZeroBaseAmount);"),
    ("require!(burned >= minimum, PumpAmmError::ExceededSlippage);", "require_gte!(burned, minimum, PumpAmmError::ExceededSlippage);"),
    ("require!(old_base > burned, PumpAmmError::TooLittlePoolTokenLiquidity);", "require_gt!(old_base, burned, PumpAmmError::TooLittlePoolTokenLiquidity);"),
)
SITES = {250: (6002, "ZeroQuoteAmount", 41), 255: (6002, "ZeroQuoteAmount", 50),
         273: (6001, "ZeroBaseAmount", 59), 274: (6004, "ExceededSlippage", 60),
         280: (6003, "TooLittlePoolTokenLiquidity", 61)}


def normalized_logs(logs):
    result = []
    for line in logs:
        if liquidity.COMPUTE.fullmatch(line):
            continue
        for original, (code, name, reconstructed) in SITES.items():
            if f". Error Code: {name}. Error Number: {code}." in line:
                for path, number in ((ORIGIN, original), ("src/boost_burn.rs", reconstructed)):
                    prefix = f"Program log: AnchorError thrown in {path}:{number}."
                    if line.startswith(prefix):
                        line = f"Program log: AnchorError thrown in <boost-source:{original}>." + line[len(prefix):]
        result.append(line)
    return result


def patched_source(raw):
    require(digest(raw) == SOURCE_SHA, "unexpected prior boost source")
    for old, new in CHANGES:
        require(raw.count(old.encode()) == 1, "missing/duplicate boost guard")
        raw = raw.replace(old.encode(), new.encode())
    return raw


def prior_source(repo):
    build = repo / "repro/pump_amm/creator-fee-diagnostics/results/build"
    raw = (build / "combined/build-record.json").read_bytes()
    require(digest(raw) == PRIOR_RECORD_SHA, "prior build record changed")
    record = json.loads(raw)
    require(record["accepted_build"] is True and record["returncode"] == 0 and record["source_unchanged"] is True and
            record["candidate_sha256"] == PRIOR_SHA, "prior build not accepted")
    require(digest((build / "combined/candidate.so").read_bytes()) == PRIOR_SHA, "prior output changed")
    expected = record["source_sha256"]
    require(expected == record["source_after_sha256"] == creator.expected_source(repo) and len(expected) == 30 and
            expected[SOURCE] == SOURCE_SHA, "prior three-file source manifest changed")
    files = {path.relative_to(build / "source").as_posix(): path for path in (build / "source").rglob("*") if path.is_file()}
    require(set(files) == set(expected) and all(digest(path.read_bytes()) == expected[name] for name, path in files.items()),
            "complete prior source snapshot changed")
    return expected, files


def expected_source(repo):
    hashes, files = prior_source(repo)
    hashes = dict(hashes)
    hashes[SOURCE] = digest(patched_source(files[SOURCE].read_bytes()))
    return hashes


def check_build(repo, candidate, raw):
    record = json.loads(raw)
    require(record["kind"] == "liquidity-sweep-migration-boost-corrected" and record["accepted_build"] is True and
            record["returncode"] == 0 and record["source_unchanged"] is True, "build not accepted")
    require(record["candidate_sha256"] == digest(candidate), "build/binary mismatch")
    require(record["source_sha256"] == record["source_after_sha256"] == expected_source(repo), "unexpected cumulative four-file source")
    require(record["prior_candidate_sha256"] == PRIOR_SHA and record["prior_build_record_sha256"] == PRIOR_RECORD_SHA,
            "prior build binding changed")
    require(record["source_patch_sha256"] == digest((PACKAGE / "source.patch").read_bytes()), "source patch changed")
    return record


def roster(fixture):
    burned = int(fixture["pool_base_vault_amount_raw"]) // (int(fixture["pool_quote_vault_amount_raw"]) + 10**9 + 1)
    return [
        {"id": "used-zero", "amount": 0, "minimum": 0},
        {"id": "used-zero-before-slippage", "amount": 0, "minimum": MAX},
        {"id": "empty-vault", "amount": 1000, "minimum": 0, "vault_amount": 0},
        {"id": "net-zero-rounded-fee", "amount": 1, "minimum": 0, "quote_fee": [1, 1]},
        {"id": "net-zero-full-fee", "amount": 1000, "minimum": 0, "quote_fee": [10000, MAX]},
        {"id": "zero-fee-extension-success", "amount": 1000, "minimum": 0, "quote_fee": [0, 0]},
        {"id": "burn-zero", "amount": 1, "minimum": 0},
        {"id": "burn-zero-before-slippage", "amount": 1, "minimum": 1},
        {"id": "zero-base-reserve", "amount": 2, "minimum": 0, "base_amount": 0},
        {"id": "slippage-one-above", "amount": 2, "minimum": burned + 1},
        {"id": "slippage-equal-success", "amount": 2, "minimum": burned},
        {"id": "slippage-one-below-success", "amount": 2, "minimum": burned - 1},
        {"id": "slippage-max", "amount": 2, "minimum": MAX},
        {"id": "base-equals-burn", "amount": 2, "minimum": 0, "virtual": -1, "quote_amount": 1, "fees_zero": True},
        {"id": "base-greater-than-burn-success", "amount": 2, "minimum": 0, "virtual": -1, "quote_amount": 2, "fees_zero": True},
        {"id": "clamped-full-drain-success", "amount": MAX, "minimum": 0},
    ]


def account_route(case, fixture, config):
    Pubkey = sweep.Pubkey
    program = Pubkey.from_string(sweep.PROGRAM)
    boost = Pubkey.find_program_address([b"boost_vault", bytes(Pubkey.from_string(fixture["pool"]))], program)[0]
    quote_program = TOKEN22 if "quote_fee" in case else sweep.TOKEN
    vault = Pubkey.find_program_address([bytes(boost), bytes(Pubkey.from_string(quote_program)),
                                        bytes(Pubkey.from_string(fixture["keys"]["quote_mint"]))], Pubkey.from_string(sweep.ATA))[0]
    event = Pubkey.find_program_address([b"__event_authority"], program)[0]
    return [fixture["pool"], sweep.PAYER, config["address"], fixture["keys"]["base_mint"], fixture["keys"]["quote_mint"],
            fixture["keys"]["pool_base_token_account"], fixture["keys"]["pool_quote_token_account"], str(boost), str(vault),
            sweep.TOKEN, quote_program, str(event), sweep.PROGRAM]


def check_transaction(raw, case, fixture, config, instruction):
    tx = sweep.Transaction.from_bytes(raw)
    message = tx.message
    require(bytes(tx) == raw and len(tx.signatures) == message.header.num_required_signatures == 1 and
            str(message.account_keys[0]) == sweep.PAYER and tx.signatures[0].verify(message.account_keys[0], bytes(message)),
            "invalid raw signature")
    require(len(message.instructions) == 1, "extra instruction")
    ix = message.instructions[0]
    route = account_route(case, fixture, config)
    require(str(message.account_keys[ix.program_id_index]) == sweep.PROGRAM and
            bytes(ix.data) == bytes(instruction["discriminator"]) + struct.pack("<QQ", case["amount"], case["minimum"]),
            "wrong signed instruction/amount")
    require([str(message.account_keys[i]) for i in ix.accounts] == route and
            set(map(str, message.account_keys)) == set(route), "wrong signed account route")
    writable = {route[i] for i in (1, 3, 5, 6, 8)}
    header = message.header
    for i, key in enumerate(message.account_keys):
        actual = (i < header.num_required_signatures - header.num_readonly_signed_accounts or
                  header.num_required_signatures <= i < len(message.account_keys) - header.num_readonly_unsigned_accounts)
        require(actual == (str(key) in writable), "wrong signed privileges")
    return 1


def expected_case(case, before, fixture, config):
    """Bind labelled state and derive the five comparisons from its actual bytes."""
    route = account_route(case, fixture, config)
    fixture_bytes = lambda name: base64.b64decode(fixture["accounts"][name]["data_base64"], validate=True)

    def account(index, expected, owner):
        actual = before[route[index]]
        require(actual is not None and set(actual) == {"data_hex", "lamports", "owner"} and
                bytes.fromhex(actual["data_hex"]) == expected and actual["owner"] == owner,
                f"labelled {case['id']} before-state differs at account {index}")
        return expected

    pool = bytearray(fixture_bytes("pool"))
    pool[245:261] = case.get("virtual", 10**9).to_bytes(16, "little", signed=True)
    if case.get("fees_zero"):
        pool[271:287] = bytes(16)
    account(0, bytes(pool), sweep.PROGRAM)
    conf = bytearray(base64.b64decode(config["data_base64"], validate=True))
    conf[8:40] = bytes(sweep.Pubkey.from_string(sweep.PAYER))
    conf[907:939] = bytes(sweep.Pubkey.from_string(sweep.PAYER))
    conf[939] = 1
    account(2, bytes(conf), sweep.PROGRAM)
    base_vault = bytearray(fixture_bytes("pool_base_token_account"))
    if "base_amount" in case:
        base_vault[64:72] = struct.pack("<Q", case["base_amount"])
    account(5, bytes(base_vault), sweep.TOKEN)
    quote_vault = bytearray(fixture_bytes("pool_quote_token_account"))
    if "quote_amount" in case:
        quote_vault[64:72] = struct.pack("<Q", case["quote_amount"])
    quote_mint = fixture_bytes("quote_mint")
    boost_vault = bytearray(165)
    boost_vault[:32] = bytes(sweep.Pubkey.from_string(route[4]))
    boost_vault[32:64] = bytes(sweep.Pubkey.from_string(route[7]))
    boost_vault[64:72] = struct.pack("<Q", case.get("vault_amount", 10**12))
    boost_vault[108] = 1
    struct.pack_into("<IQ", boost_vault, 109, 1, 2039280)
    if "quote_fee" in case:
        bps, maximum = case["quote_fee"]
        fee_config = bytes(72) + struct.pack("<QQH", 0, maximum, bps) * 2
        quote_mint = quote_mint[:82] + bytes(83) + bytes([1]) + struct.pack("<HH", 1, len(fee_config)) + fee_config
        quote_vault = quote_vault[:165] + bytes([2]) + struct.pack("<HHQ", 2, 8, 0)
        boost_vault = boost_vault[:165] + bytes([2]) + struct.pack("<HHQ", 2, 8, 0)
    account(4, bytes(quote_mint), route[10])
    account(6, bytes(quote_vault), route[10])
    account(8, bytes(boost_vault), route[10])
    used = min(case["amount"], int.from_bytes(boost_vault[64:72], "little"))
    if used == 0:
        return 250, (0, 0)
    bps, maximum = case.get("quote_fee", [0, 0])
    net = used - min((used * bps + 9999) // 10000, maximum)
    if net == 0:
        return 255, (0, 0)
    old_base = int.from_bytes(base_vault[64:72], "little")
    old_quote = int.from_bytes(quote_vault[64:72], "little")
    fees = int.from_bytes(pool[271:279], "little") + int.from_bytes(pool[279:287], "little")
    virtual = int.from_bytes(pool[245:261], "little", signed=True)
    require(fees <= old_quote and virtual + fees != 0 and 0 <= virtual + old_quote <= MAX,
            "focused case reaches an earlier arithmetic/boost gate")
    adjusted = net - 1
    burned = old_base * adjusted // (virtual + old_quote + adjusted)
    if burned == 0:
        return 273, (0, 0)
    if burned < case["minimum"]:
        return 274, (burned, case["minimum"])
    if old_base <= burned:
        return 280, (old_base, burned)
    return None, None
