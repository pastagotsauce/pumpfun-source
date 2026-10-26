#!/usr/bin/env python3
"""Synthetic parser/order regressions; these are not executable equivalence tests."""
import copy
import hashlib
import struct
import unittest
from unittest.mock import patch

import prepare_order as order


def functions():
    return [
        {"name": "before", "address": 288, "bytes": 28304},
        {"name": "_ZN5alloc7raw_vecRawVec16reserve_for_push17hu8E", "address": 28592, "bytes": 352},
        {"name": "_ZN5alloc7raw_vecRawVec16reserve_for_push17hmetaE", "address": 28944, "bytes": 440},
        {"name": "after", "address": 29384, "bytes": 62960},
    ]


def fixture(rows=None):
    rows = functions() if rows is None else rows
    data = bytearray(288 + 92056)
    data[:16] = b"\x7fELF\x02\x01\x01" + bytes(9)
    struct.pack_into("<HHI", data, 16, 3, 247, 1)
    names = b"\0.text\0.shstrtab\0.strtab\0.symtab\0"
    names_offset = len(data)
    data += names
    strings = b"\0"
    symbols = bytes(24)
    for row in rows:
        name_offset = len(strings)
        strings += row["name"].encode("ascii") + b"\0"
        symbols += struct.pack("<IBBHQQ", name_offset, 2, 0, 1,
                               row["address"], row["bytes"])
    strings_offset = len(data)
    data += strings
    symbols_offset = len(data)
    data += symbols
    sections_offset = len(data)
    sections = [
        (0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
        (1, 1, 6, 288, 288, 92056, 0, 0, 8, 0),
        (7, 3, 0, 0, names_offset, len(names), 0, 0, 1, 0),
        (17, 3, 0, 0, strings_offset, len(strings), 0, 0, 1, 0),
        (25, 2, 0, 0, symbols_offset, len(symbols), 3, 1, 8, 24),
    ]
    for row in sections:
        data += struct.pack("<IIQQQQIIQQ", *row)
    struct.pack_into("<Q", data, 40, sections_offset)
    struct.pack_into("<HHHHHH", data, 52, 64, 0, 0, 64, len(sections), 2)
    return bytes(data)


class OrderTests(unittest.TestCase):
    def test_only_pair_reversed_and_input_unchanged(self):
        rows = functions()
        before = copy.deepcopy(rows)
        actual, pair = order.reorder(rows)
        self.assertEqual(actual, [rows[0], rows[2], rows[1], rows[3]])
        self.assertEqual(rows, before)
        self.assertEqual(pair["index"], 1)

    def test_missing_pair_rejected(self):
        with self.assertRaisesRegex(ValueError, "Missing or ambiguous"):
            order.reorder(functions()[:2])

    def test_alias_at_pair_rejected(self):
        rows = functions()
        rows.insert(1, dict(rows[1], name="alias"))
        with self.assertRaisesRegex(ValueError, "Missing or ambiguous"):
            order.reorder(rows)

    def test_changed_pair_size_rejected(self):
        rows = functions()
        rows[1]["bytes"] += 8
        with self.assertRaisesRegex(ValueError, "Unexpected RawVec"):
            order.reorder(rows)

    def test_wrong_symbol_at_known_address_rejected(self):
        rows = functions()
        rows[2]["name"] = "unrelated"
        with self.assertRaisesRegex(ValueError, "Unexpected RawVec"):
            order.reorder(rows)

    def test_overlapping_symbol_rejected(self):
        rows = functions()
        rows[0]["bytes"] += 8
        with self.assertRaisesRegex(ValueError, "overlaps"):
            order.reorder(rows)

    def test_baseline_hash_is_mandatory(self):
        with self.assertRaisesRegex(ValueError, "does not reproduce"):
            order.prepare(fixture(), fixture())

    def test_synthetic_elf_and_order(self):
        data = fixture()
        # Test the parser with a synthetic file, never accept this fixture in production.
        with patch.object(order, "BASELINE_SHA256", hashlib.sha256(data).hexdigest()), \
                patch.object(order, "BASELINE_BYTES", len(data)):
            contents, report = order.prepare(data, data)
        self.assertEqual(contents.decode().splitlines(),
                         [functions()[i]["name"] for i in (0, 2, 1, 3)])
        self.assertFalse(report["reference_executable_read"])
        self.assertFalse(report["executable_bytes_written"])

    def test_changed_unstripped_text_rejected(self):
        data = fixture()
        bad = bytearray(data)
        bad[288] ^= 1
        with patch.object(order, "BASELINE_SHA256", hashlib.sha256(data).hexdigest()), \
                patch.object(order, "BASELINE_BYTES", len(data)):
            with self.assertRaisesRegex(ValueError, "text does not match"):
                order.prepare(data, bytes(bad))

    def test_linked_order_accepts_only_the_requested_placement(self):
        data = fixture()
        with patch.object(order, "BASELINE_SHA256", hashlib.sha256(data).hexdigest()), \
                patch.object(order, "BASELINE_BYTES", len(data)):
            _, report = order.prepare(data, data)
        rows = functions()
        rows[1]["address"] = 29032
        rows[2]["address"] = 28592
        order.verify_linked_order(fixture(rows), report)
        rows[-1]["address"] += 8
        rows[-1]["bytes"] -= 8
        with self.assertRaisesRegex(ValueError, "beyond the requested"):
            order.verify_linked_order(fixture(rows), report)

    def test_ignored_linker_order_rejected(self):
        data = fixture()
        with patch.object(order, "BASELINE_SHA256", hashlib.sha256(data).hexdigest()), \
                patch.object(order, "BASELINE_BYTES", len(data)):
            _, report = order.prepare(data, data)
        with self.assertRaisesRegex(ValueError, "beyond the requested"):
            order.verify_linked_order(data, report)

    def test_duplicate_symbol_names_rejected(self):
        rows = functions()
        rows[-1]["name"] = rows[0]["name"]
        data = fixture(rows)
        with self.assertRaisesRegex(ValueError, "Duplicate function names"):
            order.text_functions(data, order.parse_elf(data))

    def test_truncated_elf_rejected(self):
        with self.assertRaisesRegex(ValueError, "outside the file"):
            order.parse_elf(fixture()[:-1])

    def test_wrong_architecture_rejected(self):
        data = bytearray(fixture())
        struct.pack_into("<H", data, 18, 62)
        with self.assertRaisesRegex(ValueError, "BPF shared ELF"):
            order.parse_elf(data)

    def test_symbol_newline_rejected(self):
        rows = functions()
        rows[0]["name"] = "before\nextra"
        data = fixture(rows)
        with self.assertRaisesRegex(ValueError, "Invalid function name"):
            order.text_functions(data, order.parse_elf(data))


if __name__ == "__main__":
    unittest.main()
