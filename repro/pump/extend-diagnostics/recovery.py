"""Fixed inputs and exact source proposal for Pump extension diagnostics."""
import gzip
import hashlib
import json
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent
ROOT = PACKAGE.parents[2]
ORIGINAL_SHA = "7a19affaa2c6187e04a5fe0ea298cee81fa5eb8c24cfcc30d85f615e89f7b02d"
BASELINE_SHA = "71ec4d8a646eefc82ba177afbc3d08552deadd65cf2f80ec280862eb768d059c"
SOURCE = "programs/pump/src/extend.rs"
SOURCE_SHA = "e1a4e4cac477e0e9bd9d8ebe650839aa5410e7edf084f6478c1a1f404d3800f8"
CORRECTED_SHA = "950d3824e10a28495d9f54e15df6dbc5e5e76e385dc088e1df4560c41732e683"
PINS_SHA = "413e0c33491d7228fb54151c9fa151ccef9baa96798d6156f06bb21546a304e2"
TARGETS = {"BondingCurve": 166, "Global": 1088, "GlobalVolumeAccumulator": 600, "UserVolumeAccumulator": 137}
OLD = b"    if current >= size {\n        return Ok(());\n    }"
NEW = b'''    if current == size {
        msg!("Account already has the correct size");
        return Ok(());
    }
    if current > size {
        msg!("Account already has more than {} bytes: {}", size, current);
        return Ok(());
    }'''


def digest(data):
    return hashlib.sha256(data).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def load_json(path):
    raw = Path(path).read_bytes()
    return json.loads(gzip.decompress(raw) if raw.startswith(b"\x1f\x8b") else raw)


def pinned_source(repo=ROOT):
    require(digest((PACKAGE / "pins.json").read_bytes()) == PINS_SHA, "fixed input seal changed")
    pins = load_json(PACKAGE / "pins.json")
    for name, expected in pins["inputs"].items():
        path = PACKAGE / name if name == "source.patch" else PACKAGE / "inputs" / name
        require(digest(path.read_bytes()) == expected, "retained input changed: " + name)
    record = load_json(PACKAGE / "inputs/selected-build-attempt.json")
    names = record["source_sha256"]
    require(record["selected_toolchain"] == "v1.44" and record["returncode"] == 0 and
            record["source_after_sha256"] == names and len(names) == 37, "selected build input changed")
    require(names[SOURCE] == SOURCE_SHA, "selected extension source changed")
    require(all(digest((repo / name).read_bytes()) == value for name, value in names.items()), "current source differs from selected source37")
    return names


def patched_source(raw):
    require(digest(raw) == SOURCE_SHA and raw.count(OLD) == 1, "unexpected extension source")
    changed = raw.replace(OLD, NEW)
    require(digest(changed) == CORRECTED_SHA, "unexpected extension replacement")
    return changed


def expected_message(case):
    size, target = case["size"], TARGETS[case["kind"]]
    if size == target:
        return "Program log: Account already has the correct size"
    if size > target:
        return f"Program log: Account already has more than {target} bytes: {size}"
    return None


def full_logs_without_compute(logs):
    """Only compute-use lines are excluded; source origins and all other logs stay."""
    import re
    return [line for line in logs if not re.fullmatch(r"Program \S+ consumed \d+ of \d+ compute units", line)]


def focused_cases():
    return [{"name": f"{kind}-{label}", "kind": kind, "size": size}
            for kind, target in TARGETS.items()
            for label, size in (("growth", target - 1), ("equal", target), ("oversized", target + 1))]
