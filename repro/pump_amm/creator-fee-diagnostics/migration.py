"""Explicit source and fixture bindings for the migrate-only 6081 correction."""
import base64
import json
from pathlib import Path
import re
import sys

PACKAGE = Path(__file__).resolve().parent
ROOT = PACKAGE.parents[2]
PRIOR = ROOT / "repro/pump_amm/sweep-error-observation"
sys.path.insert(0, str(PRIOR))
import recovery as sweep

digest, require, write_json, read_report = sweep.digest, sweep.require, sweep.write_json, sweep.read_report
liquidity = sweep.liquidity
liquidity_runtime = sweep.liquidity_runtime
ORIGINAL_SHA = sweep.ORIGINAL_SHA
PRIOR_SHA = "64d909213b9fe0fe9447e9204e470129c0eff8fcab1a50ae628fb6ec9256a069"
PRIOR_RECORD_SHA = "cad21b8fd0e9ab05fc7e0664883eff40154632216cd54a2f3a10b22b09eab245"
SOURCE = "programs/pump-amm/src/creator_reassignment.rs"
SOURCE_SHA = "59449c2174c08bc4d093488788c8921c0594303e9a79d74d2da91d99325e5965"
RECEIPT = "repro/pump_amm/owner6048-v144/runtime/runtime-01/creator_reassignment.json.gz"
RECEIPT_SHA = "ad5ca42a325cd366f7213db431a463629c687976ea2f1b21b9c95e15e069632d"
RAW_SHA = "c4d203a1e11a95b3f53dbcca186e61052e3cc1e932b0289e9dc4e79a77a50fdb"
INPUTS = sweep.INPUTS | {"scripts/pump_amm_creator_reassignment_differential.py"}
ERROR = "TransactionErrorInstructionError((0, Tagged(InstructionErrorCustom(6081))))"
HOLDER_ERROR = "TransactionErrorInstructionError((0, Tagged(InstructionErrorCustom(6074))))"
ORIGIN = "programs/pump-amm/src/instructions/coin_creator/migrate_pool_coin_creator.rs"
LOCATION = re.compile(r"^(Program log: AnchorError thrown in )[^\r\n]+:\d+(\. Error Code: (?:CreatorFeesNotSwept|HolderRewardCreatorImmutable)\. Error Number: (?:6081|6074)\. Error Message: .*)$")


def normalized_logs(logs):
    return [LOCATION.sub(r"\1<source>\2", line) for line in liquidity.normalized_logs(logs)]


def patched_source(raw):
    guard = b" require_eq!(pool.creator_fees,0,PumpAmmError::CreatorFeesNotSwept);"
    before = (b"pub fn migrate(ctx:Context<MigratePoolCoinCreator>)->Result<()>{\n"
              b" let pool=&mut ctx.accounts.pool;\n"
              b" require!(!pool.is_holder_reward,PumpAmmError::HolderRewardCreatorImmutable);\n" + guard)
    after = before.replace(guard, b" require!(pool.creator_fees==0,PumpAmmError::CreatorFeesNotSwept);")
    require(raw.count(before) == 1 and raw.count(guard) == 2, "unexpected migration/admin guard layout")
    result = raw.replace(before, after)
    require(result.split(b"pub fn admin_cto", 1)[1] == raw.split(b"pub fn admin_cto", 1)[1], "admin_cto changed")
    require(result.count(guard) == 1, "wrong guard occurrence changed")
    return result


def load_prior_builder():
    return sweep.load_prior_builder()


def prior_source(repo):
    build = repo / "repro/pump_amm/sweep-error-observation/results/build"
    raw = (build / "combined/build-record.json").read_bytes()
    require(digest(raw) == PRIOR_RECORD_SHA, "prior build record changed")
    record = json.loads(raw)
    require(record["accepted_build"] is True and record["returncode"] == 0 and record["source_unchanged"] is True and
            record["candidate_sha256"] == PRIOR_SHA, "prior build did not pass")
    require(digest((build / "combined/candidate.so").read_bytes()) == PRIOR_SHA, "prior output changed")
    expected = record["source_sha256"]
    require(expected == record["source_after_sha256"] and len(expected) == 30 and expected[SOURCE] == SOURCE_SHA,
            "prior source manifest changed")
    actual = {path.relative_to(build / "source").as_posix(): path for path in (build / "source").rglob("*") if path.is_file()}
    require(set(actual) == set(expected) and all(digest(path.read_bytes()) == expected[name] for name, path in actual.items()),
            "complete prior source snapshot changed")
    return expected, actual


def expected_source(repo):
    expected, files = prior_source(repo)
    expected = dict(expected)
    expected[SOURCE] = digest(patched_source(files[SOURCE].read_bytes()))
    return expected


def check_build(repo, candidate, raw):
    record = json.loads(raw)
    require(record["kind"] == "liquidity-sweep-migration-corrected" and record["accepted_build"] is True and
            record["returncode"] == 0 and record["source_unchanged"] is True, "build not accepted")
    require(record["candidate_sha256"] == digest(candidate), "build/binary mismatch")
    require(record["source_sha256"] == record["source_after_sha256"] == expected_source(repo), "unexpected three-file combined source")
    require(record["prior_candidate_sha256"] == PRIOR_SHA and record["prior_build_record_sha256"] == PRIOR_RECORD_SHA,
            "prior build binding mismatch")
    require(record["source_patch_sha256"] == digest((PACKAGE / "source.patch").read_bytes()), "source patch changed")
    return record


def migration_roster():
    return [(False, fee) for fee in (0, 1, 2, 2**64 - 1)] + [(True, fee) for fee in (0, 1)]


def regression_roster():
    sweeps = [{"family": "sweep", "instruction": instruction, "mode": mode, "amount": amount}
              for instruction, mode, amount in sweep.roster()]
    pools = [{"family": "liquidity", "instruction": instruction, "user_account_index": account,
              "amount": amount, "wrong_withdraw_owner": wrong}
             for instruction, wrong in (("deposit", False), ("withdraw", False), ("withdraw", True))
             for account in (6, 7) for amount in (0, 1, 1000000)]
    return sweeps + pools


def migration_transaction(raw, fixture, idl):
    tx = sweep.Transaction.from_bytes(raw)
    message = tx.message
    require(bytes(tx) == raw and len(tx.signatures) == message.header.num_required_signatures == 1, "invalid transaction shape")
    require(str(message.account_keys[0]) == sweep.PAYER and tx.signatures[0].verify(message.account_keys[0], bytes(message)), "invalid raw signer/signature")
    require(len(message.instructions) == 1, "extra instruction")
    instruction = message.instructions[0]
    require(str(message.account_keys[instruction.program_id_index]) == sweep.PROGRAM and
            bytes(instruction.data) == bytes(idl["migrate_pool_coin_creator"]["discriminator"]), "wrong signed instruction")
    Pubkey = sweep.Pubkey
    sharing = Pubkey.find_program_address([b"sharing-config", bytes(Pubkey.from_string(fixture["keys"]["base_mint"]))],
                                          Pubkey.from_string("pfeeUxB6jkeY1Hxd7CsFCAjcbHA9rWtchMGdZ6VojVZ"))[0]
    event = Pubkey.find_program_address([b"__event_authority"], Pubkey.from_string(sweep.PROGRAM))[0]
    expected = [fixture["pool"], str(sharing), str(event), sweep.PROGRAM]
    require([str(message.account_keys[i]) for i in instruction.accounts] == expected, "wrong signed account route")
    require(set(map(str, message.account_keys)) == set(expected) | {sweep.PAYER}, "extra unused account")
    header = message.header
    for i, key in enumerate(message.account_keys):
        writable = (i < header.num_required_signatures - header.num_readonly_signed_accounts or
                    header.num_required_signatures <= i < len(message.account_keys) - header.num_readonly_unsigned_accounts)
        require(writable == (str(key) in (sweep.PAYER, fixture["pool"])), "wrong signed privileges")
    return 1
