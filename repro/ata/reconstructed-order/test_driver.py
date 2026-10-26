#!/usr/bin/env python3
"""Local filesystem gates; no Docker, compiler, program or network execution."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

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
        with self.assertRaisesRegex(ValueError, "symlink"):
            run.source_manifest(self.source)

    def test_pinned_twelve_symlink_tree_shape(self):
        indexed = {name: (row["mode"], row["blob"])
                   for name, row in run.PINNED_SYMLINKS["destinations"].items()}
        self.assertEqual(len(run.PINNED_SYMLINKS["links"]), 12)
        destinations = set()
        for name, row in run.PINNED_SYMLINKS["links"].items():
            encoded = row["target"].encode()
            self.assertEqual(hashlib.sha1(b"blob " + str(len(encoded)).encode() + b"\0" + encoded).hexdigest(), row["blob"])
            destinations.add(run.symlink_destination(name, row["blob"], row["target"], indexed))
        self.assertEqual(destinations, set(run.PINNED_SYMLINKS["destinations"]))

    def test_unknown_or_escaping_link_rejected(self):
        indexed = {name: (row["mode"], row["blob"])
                   for name, row in run.PINNED_SYMLINKS["destinations"].items()}
        with self.assertRaisesRegex(ValueError, "Unknown or modified"):
            run.symlink_destination("injected-link", "0" * 40, "../outside", indexed)
        row = run.PINNED_SYMLINKS["links"]["farms/README.md"]
        with self.assertRaisesRegex(ValueError, "Unknown or modified"):
            run.symlink_destination("farms/README.md", row["blob"], "../../outside", indexed)

    def test_missing_or_chained_link_destination_rejected(self):
        row = run.PINNED_SYMLINKS["links"]["farms/README.md"]
        for indexed in ({}, {"farms/docs/intro.md": ("120000", row["blob"])}):
            with self.subTest(indexed=indexed):
                with self.assertRaisesRegex(ValueError, "missing, changed or chained"):
                    run.symlink_destination("farms/README.md", row["blob"], row["target"], indexed)

    def test_pinned_tree_topology_with_real_filesystem_symlinks(self):
        probe = self.source / "symlink-probe"
        try:
            os.symlink("Cargo.toml", probe)
        except OSError as error:
            if sys.platform != "win32":
                raise
            self.skipTest("Filesystem symlink privilege unavailable: " + str(error))
        probe.unlink()
        expected_destinations = {}
        for name, row in run.PINNED_SYMLINKS["destinations"].items():
            path = self.source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(("synthetic contents for " + name).encode())
            blob = self.git("hash-object", str(path)).decode().strip()
            expected_destinations[name] = {"mode": row["mode"], "blob": blob}
        for name, row in run.PINNED_SYMLINKS["links"].items():
            path = self.source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            os.symlink(row["target"], path)
        self.git("config", "core.symlinks", "true")
        self.git("add", "farms")
        self.git("update-index", "--chmod=+x", "farms/docs/intro.md")
        # Use exact published link names/targets, with small synthetic destination contents.
        with patch.dict(run.PINNED_SYMLINKS, {"destinations": expected_destinations}):
            manifest = run.source_manifest(self.source)
            self.assertTrue(set(run.PINNED_SYMLINKS["links"]) <= set(manifest))
            (self.source / "farms/docs/intro.md").unlink()
            with self.assertRaises((ValueError, FileNotFoundError)):
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
