#!/usr/bin/env python3
"""Local filesystem gates; no Docker, compiler, program or network execution."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

import run


class DriverTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.source = self.root / "source"
        self.source.mkdir()
        self.git("init", "--quiet")
        self.git("config", "core.autocrlf", "false")
        (self.source / "Cargo.toml").write_bytes(b"[package]\nname = 'fixture'\n")
        (self.source / ".gitignore").write_bytes(b"target/\n.cargo/\n")
        self.git("add", "Cargo.toml", ".gitignore")

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.source), *args], stderr=subprocess.STDOUT)

    def test_clean_files_are_bound(self):
        manifest = run.source_manifest(self.source)
        self.assertEqual(set(manifest), {"Cargo.toml", ".gitignore"})
        self.assertEqual(manifest["Cargo.toml"], hashlib.sha256((self.source / "Cargo.toml").read_bytes()).hexdigest())

    def test_untracked_input_rejected(self):
        (self.source / "unexpected.rs").write_text("// fixture")
        with self.assertRaisesRegex(ValueError, "untracked or ignored"):
            run.source_manifest(self.source)

    def test_ignored_cargo_configuration_rejected(self):
        (self.source / ".cargo").mkdir()
        (self.source / ".cargo/config.toml").write_text("[build]\nrustflags = []")
        for allow_target in (False, True):
            with self.subTest(allow_target=allow_target):
                with self.assertRaisesRegex(ValueError, "untracked or ignored"):
                    run.source_manifest(self.source, allow_target=allow_target)

    def test_generated_target_allowed_only_after_control_build(self):
        (self.source / "target").mkdir()
        (self.source / "target/output.o").write_bytes(b"fixture")
        with self.assertRaisesRegex(ValueError, "untracked or ignored"):
            run.source_manifest(self.source)
        self.assertEqual(set(run.source_manifest(self.source, allow_target=True)), {"Cargo.toml", ".gitignore"})

    def test_changed_tracked_bytes_rejected(self):
        (self.source / "Cargo.toml").write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "differ from Git"):
            run.source_manifest(self.source)

    def test_missing_tracked_file_rejected(self):
        (self.source / "Cargo.toml").unlink()
        with self.assertRaisesRegex(ValueError, "missing"):
            run.source_manifest(self.source)

    def test_symlink_index_mode_rejected(self):
        blob = self.git("hash-object", "Cargo.toml").decode().strip()
        self.git("update-index", "--cacheinfo", "120000," + blob + ",Cargo.toml")
        with self.assertRaisesRegex(ValueError, "symlink, submodule"):
            run.source_manifest(self.source)

    def test_reference_inside_source_rejected(self):
        with self.assertRaisesRegex(ValueError, "outside the source mount"):
            run.resolve_reference(self.source, self.source / "captured.so")
        self.assertEqual(run.resolve_reference(self.source, self.root / "captured.so"), self.root / "captured.so")

    def test_reference_resolved_path_is_checked(self):
        # A path that lexically leaves the root but resolves inside must still fail.
        with self.assertRaisesRegex(ValueError, "outside the source mount"):
            run.resolve_reference(self.source, self.root / "elsewhere/../source/captured.so")

    def test_baseline_outputs_retained_before_acceptance(self):
        output = self.root / "output"
        output.mkdir()
        artifact = self.source / "target/deploy" / run.LIBRARY
        artifact.parent.mkdir(parents=True)
        artifact.write_bytes(b"a deliberately unequal control build")
        records = run.retain_baseline(self.source, output)
        self.assertEqual((output / "baseline.so").read_bytes(), artifact.read_bytes())
        self.assertEqual(records["baseline.so"]["sha256"], hashlib.sha256(artifact.read_bytes()).hexdigest())
        self.assertFalse(records["baseline.symbols.so"]["available"])
        self.assertEqual(json.loads((output / "baseline-artifacts.json").read_text()), records)


if __name__ == "__main__":
    unittest.main()
