#!/usr/bin/env python3
"""Compiler-free input, provenance and failed-output retention regressions."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
from evidence import Elf, compare, same_location_payload, sha
import run
from verify_inputs import verify

REPO = run.P.parents[2]


class Guards(unittest.TestCase):
    def test_actual_selected_location_and_source(self):
        self.assertEqual(verify(REPO)["source_files"], 14)

    def test_changed_instruction_rejected(self):
        frozen = run.pins()
        data = bytearray((REPO / frozen["selected"]["path"]).read_bytes())
        data[464840] = 0
        with self.assertRaisesRegex(ValueError, "LDDW"):
            Elf(bytes(data)).location(464840)

    def test_missing_pointer_relocation_rejected(self):
        elf = Elf((REPO / run.pins()["selected"]["path"]).read_bytes())
        del elf.relocations[558880]
        with self.assertRaisesRegex(ValueError, "Location pointer"):
            elf.location(464840)

    def test_incomplete_section_table_rejected(self):
        with self.assertRaises(ValueError):
            Elf(b"\x7fELF\x02\x01" + bytes(58))

    def test_changed_source_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "lib.rs").write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "source bytes"):
                run.check_source(root, {"lib.rs": sha(b"original")})

    def test_extra_source_config_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "lib.rs").write_bytes(b"source")
            (root / ".cargo").mkdir()
            (root / ".cargo/config.toml").write_bytes(b"[build]\nrustflags=['injection']\n")
            with self.assertRaisesRegex(ValueError, "inventory"):
                run.check_source(root, {"lib.rs": sha(b"source")})

    def test_ancestor_config_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / ".cargo").mkdir()
            (root / ".cargo/config").write_bytes(b"injection")
            child = root / "source"
            child.mkdir()
            with self.assertRaisesRegex(ValueError, "Ambient"):
                run.reject_parent_config(child)

    def test_rewritten_input_pin_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "inputs.json").write_bytes(b"{}")
            with patch.object(run, "P", root), self.assertRaisesRegex(ValueError, "pins changed"):
                run.pins()

    def test_failed_process_and_existing_outputs_retained(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            attempt = run.Attempt(root / "attempt")
            status = attempt.command("failure-control", [sys.executable, "-c", "print('partial');raise SystemExit(7)"], root, {}, check=False)
            self.assertEqual(status, 7)
            generated = root / "unstripped.so"
            generated.write_bytes(b"known-partial-output")
            attempt.retain(generated, root / "absent.so")
            self.assertEqual((attempt.evidence / "unstripped.so").read_bytes(), generated.read_bytes())
            self.assertEqual(json.loads((attempt.evidence / "commands.json").read_bytes())[0]["exit"], 7)

    def test_existing_attempt_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with self.assertRaises(FileExistsError):
                run.Attempt(root)

    def test_changed_source_is_recorded_before_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            source.mkdir()
            (source / "lib.rs").write_bytes(b"changed")
            attempt = run.Attempt(root / "attempt")
            self.assertIsNone(attempt.state["source_changed"])
            self.assertFalse(run.measure_source(attempt, source, {"lib.rs": sha(b"original")}, "source-after"))
            self.assertTrue(json.loads((attempt.evidence / "result.json").read_bytes())["source_changed"])

    def test_raw_comparison_never_accepts_zero_padding(self):
        result = compare(b"ELF\0", b"ELF")
        self.assertFalse(result["full_byte_equality"])
        self.assertEqual(result["length_difference"], -1)

    def test_location_comparison_keeps_raw_nul_and_length(self):
        original = {"file_raw_hex": b"source.rs\0".hex(), "file_length": 10, "line": 2830, "column": 14}
        changed = dict(original, file_raw_hex=b"source.rs".hex(), file_length=9)
        self.assertFalse(same_location_payload(original, changed))


if __name__ == "__main__":
    unittest.main()
