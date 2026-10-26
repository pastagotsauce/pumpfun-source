#!/usr/bin/env python3
"""Emit a linker order file from an independently built ATA symbol table.

This never reads the captured executable or writes executable bytes. The only
reconstruction choice is the evidenced order of two adjacent RawVec functions.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct

BASELINE_SHA256 = "ba8dd8a42ca7bff4b668c72e1b5614e9363b271924d520253f5724760ba2d65b"
BASELINE_BYTES = 105032
U8_ADDRESS, U8_SIZE = 28592, 352
META_ADDRESS, META_SIZE = 28944, 440


def require(condition, message):
    if not condition:
        raise ValueError(message)


def region(data, offset, size):
    require(0 <= offset <= len(data) and 0 <= size <= len(data) - offset,
            "ELF range is outside the file")
    return data[offset:offset + size]


def string(table, offset):
    require(0 <= offset < len(table), "Invalid ELF string offset")
    end = table.find(b"\0", offset)
    require(end >= 0, "Unterminated ELF string")
    return table[offset:end].decode("ascii")


def parse_elf(data):
    require(len(data) >= 64 and data[:7] == b"\x7fELF\x02\x01\x01",
            "Expected little-endian ELF64")
    require(struct.unpack_from("<HH", data, 16) == (3, 247),
            "Expected a BPF shared ELF")
    shoff = struct.unpack_from("<Q", data, 40)[0]
    stride, count, strings_index = struct.unpack_from("<HHH", data, 58)
    require(stride == 64 and count > 0 and strings_index < count,
            "Unsupported section table")
    region(data, shoff, count * stride)
    sections = []
    for index in range(count):
        values = struct.unpack_from("<IIQQQQIIQQ", data, shoff + index * stride)
        row = dict(zip(("name_offset", "type", "flags", "address", "offset",
                        "size", "link", "info", "alignment", "entry_size"), values))
        row["index"] = index
        if row["type"] != 8:  # NOBITS sections have no file extent.
            region(data, row["offset"], row["size"])
        sections.append(row)
    names = sections[strings_index]
    names = region(data, names["offset"], names["size"])
    for row in sections:
        row["name"] = string(names, row["name_offset"])
    return sections


def section(sections, name):
    matches = [row for row in sections if row["name"] == name]
    require(len(matches) == 1, "Expected exactly one " + name + " section")
    return matches[0]


def text_functions(data, sections):
    text = section(sections, ".text")
    symbols = section(sections, ".symtab")
    require(symbols["entry_size"] == 24 and symbols["size"] % 24 == 0,
            "Invalid ELF symbol entry size")
    require(symbols["link"] < len(sections), "Invalid symbol string table")
    strings = sections[symbols["link"]]
    strings = region(data, strings["offset"], strings["size"])
    functions = []
    for at in range(symbols["offset"], symbols["offset"] + symbols["size"], 24):
        name, info, _, index, address, size = struct.unpack_from("<IBBHQQ", data, at)
        if index != text["index"] or info & 15 != 2:
            continue
        name = string(strings, name)
        require(name and not any(c.isspace() for c in name), "Invalid function name")
        require(text["address"] <= address < text["address"] + text["size"]
                and 0 < size <= text["address"] + text["size"] - address,
                "Invalid function extent")
        functions.append({"name": name, "address": address, "bytes": size})
    require(functions, "No named text functions")
    require(len({f["name"] for f in functions}) == len(functions),
            "Duplicate function names cannot identify linker input sections")
    return sorted(functions, key=lambda f: (f["address"], f["name"]))


def reorder(functions):
    def one(address, size):
        matches = [f for f in functions if f["address"] == address]
        require(len(matches) == 1, "Missing or ambiguous RawVec function")
        row = matches[0]
        require(row["bytes"] == size and "RawVec" in row["name"]
                and "reserve_for_push" in row["name"], "Unexpected RawVec symbol or size")
        return row

    u8 = one(U8_ADDRESS, U8_SIZE)
    account_meta = one(META_ADDRESS, META_SIZE)
    index = functions.index(u8)
    require(index + 1 < len(functions) and functions[index + 1] == account_meta,
            "RawVec functions are not adjacent")
    require(U8_ADDRESS + U8_SIZE == META_ADDRESS, "Unexpected baseline adjacency")
    require(all(f == u8 or f == account_meta or
                f["address"] + f["bytes"] <= U8_ADDRESS or
                f["address"] >= META_ADDRESS + META_SIZE for f in functions),
            "Another symbol overlaps the RawVec pair")
    ordered = list(functions)
    ordered[index:index + 2] = [account_meta, u8]
    return ordered, {"u8": u8, "account_meta": account_meta, "index": index}


def prepare(baseline, unstripped):
    require(len(baseline) == BASELINE_BYTES and
            hashlib.sha256(baseline).hexdigest() == BASELINE_SHA256,
            "Source-built baseline does not reproduce selected candidate2")
    original_sections = parse_elf(baseline)
    symbols_sections = parse_elf(unstripped)
    baseline_text = section(original_sections, ".text")
    symbols_text = section(symbols_sections, ".text")
    require(baseline_text["address"] == symbols_text["address"] and
            region(baseline, baseline_text["offset"], baseline_text["size"]) ==
            region(unstripped, symbols_text["offset"], symbols_text["size"]),
            "Unstripped text does not match the source-built baseline")
    functions = text_functions(unstripped, symbols_sections)
    ordered, pair = reorder(functions)
    contents = "".join(f["name"] + "\n" for f in ordered).encode("ascii")
    report = {
        "scope": "Reconstructed linker order; historical uploader recipe is unknown",
        "baseline_sha256": hashlib.sha256(baseline).hexdigest(),
        "unstripped_sha256": hashlib.sha256(unstripped).hexdigest(),
        "order_sha256": hashlib.sha256(contents).hexdigest(),
        "function_symbols": len(functions), "pair": pair,
        "baseline_order": functions,
        "requested_symbol_order": [f["name"] for f in ordered],
        "reference_executable_read": False,
        "executable_bytes_written": False,
    }
    return contents, report


def verify_linked_order(unstripped, report):
    """Require the supported linker to apply exactly the requested placement."""
    functions = text_functions(unstripped, parse_elf(unstripped))
    actual = {row["name"]: row for row in functions}
    expected = {row["name"]: dict(row) for row in report["baseline_order"]}
    expected[report["pair"]["account_meta"]["name"]]["address"] = U8_ADDRESS
    expected[report["pair"]["u8"]["name"]]["address"] = U8_ADDRESS + META_SIZE
    require(actual == expected, "Linked symbols differ beyond the requested RawVec placement")
    require([row["name"] for row in functions] == report["requested_symbol_order"],
            "Linker did not preserve the requested symbol order")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--unstripped", type=Path, required=True)
    parser.add_argument("--order", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    require(not args.order.exists() and not args.report.exists(), "Output already exists")
    contents, report = prepare(args.baseline.read_bytes(), args.unstripped.read_bytes())
    args.order.write_bytes(contents)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({key: report[key] for key in
                      ("function_symbols", "baseline_sha256", "order_sha256")}))


if __name__ == "__main__":
    main()
