import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
import unittest

try:
	import scripts.ownership_cutover as cutover
except ImportError:
	try:
		import ownership_cutover as cutover
	except ImportError:
		cutover = None

PROTECTED_BUNDLE = "bakery_manufacturing/public/js/bakery_manufacturing.bundle.js"
PROTECTED_TEST = "bakery_manufacturing/tests/test_desk_sidebar.py"
PROTECTED_BUNDLE_HASH = "8b04313861b211aa17cb4d0c87c372d32e2f8b0d642b94292e58a7865ae1bbf1"

# Self-contained exact bundle bytes fixture (SHA256: 8b04313861b211aa17cb4d0c87c372d32e2f8b0d642b94292e58a7865ae1bbf1, 526 bytes)
PROTECTED_BUNDLE_CONTENT = (
	b"\n"
	b"if (frappe.ui?.SidebarHeader && !frappe.ui.SidebarHeader.prototype._bakery_sidebar_patched) {\n"
	b"\tconst add_app_item = frappe.ui.SidebarHeader.prototype.add_app_item;\n"
	b"\tfrappe.ui.SidebarHeader.prototype.add_app_item = function (item) {\n"
	b"\t\tif (item?.is_divider) {\n"
	b"\t\t\treturn $(\n"
	b"\t\t\t\t\"<div class=\x27dropdown-menu-item\x27><div class=\x27dropdown-divider documentation-links\x27></div></div>\"\n"
	b"\t\t\t).appendTo(this.dropdown_menu);\n"
	b"\t\t}\n"
	b"\n"
	b"\t\treturn add_app_item.call(this, item);\n"
	b"\t};\n"
	b"\tfrappe.ui.SidebarHeader.prototype._bakery_sidebar_patched = true;\n"
	b"}\n"
)
PROTECTED_TEST_CONTENT = "# protected untracked test\ndef test_sidebar():\n\tpass\n"


def run_git(repo_dir: str, *args: str) -> subprocess.CompletedProcess:
	return subprocess.run(
		["git", "-C", repo_dir, *args],
		capture_output=True,
		text=True,
		check=True,
	)


class TestOwnershipCutoverHardened(unittest.TestCase):
	def setUp(self):
		if cutover is None:
			self.fail("scripts/ownership_cutover.py does not exist or cannot be imported")
		cutover._set_test_expected_bundle_sha(None)

		# Create an isolated temporary git repository
		self.temp_dir = tempfile.TemporaryDirectory()
		self.repo_dir = self.temp_dir.name

		# Init git repo with initial config
		run_git(self.repo_dir, "init", "-b", "main")
		run_git(self.repo_dir, "config", "user.name", "Test Runner")
		run_git(self.repo_dir, "config", "user.email", "test@example.com")
		run_git(self.repo_dir, "config", "core.filemode", "true")

		# Set up base commit files
		os.makedirs(os.path.join(self.repo_dir, "bakery_manufacturing", "overrides"), exist_ok=True)
		os.makedirs(os.path.join(self.repo_dir, "bakery_manufacturing", "public", "js"), exist_ok=True)
		os.makedirs(os.path.join(self.repo_dir, "bakery_manufacturing", "doctype"), exist_ok=True)

		with open(os.path.join(self.repo_dir, "README.md"), "w") as f:
			f.write("# Base Readme\n")

		with open(os.path.join(self.repo_dir, "bakery_manufacturing", "overrides", "pos_overrides.py"), "w") as f:
			f.write("# old pos overrides\n")

		with open(os.path.join(self.repo_dir, "bakery_manufacturing", "doctype", "old_file.py"), "w") as f:
			f.write("# old doctype file\n")

		# Executable script in base
		exec_base = os.path.join(self.repo_dir, "bakery_manufacturing", "overrides", "tool.sh")
		with open(exec_base, "w") as f:
			f.write("#!/bin/sh\necho base\n")
		os.chmod(exec_base, 0o755)

		# Tracked empty bundle in base commit per Ruling AK
		with open(os.path.join(self.repo_dir, PROTECTED_BUNDLE), "w") as f:
			f.write("")

		run_git(self.repo_dir, "add", "-A")
		run_git(self.repo_dir, "commit", "-m", "base commit")
		self.base_sha = run_git(self.repo_dir, "rev-parse", "HEAD").stdout.strip()

		# Create target commit on candidate branch
		run_git(self.repo_dir, "checkout", "-b", "candidate")

		with open(os.path.join(self.repo_dir, "README.md"), "w") as f:
			f.write("# Candidate Readme\n")
		with open(os.path.join(self.repo_dir, "bakery_manufacturing", "overrides", "pos_overrides.py"), "w") as f:
			f.write("# new pos overrides shim\n")
		os.remove(os.path.join(self.repo_dir, "bakery_manufacturing", "doctype", "old_file.py"))
		with open(os.path.join(self.repo_dir, "bakery_manufacturing", "overrides", "new_shim.py"), "w") as f:
			f.write("# new shim added\n")

		# Target modifies executable script with mode change (0755 -> 0644)
		with open(exec_base, "w") as f:
			f.write("#!/bin/sh\necho target\n")
		os.chmod(exec_base, 0o644)

		run_git(self.repo_dir, "add", "-A")
		run_git(self.repo_dir, "commit", "-m", "target commit")
		self.target_sha = run_git(self.repo_dir, "rev-parse", "HEAD").stdout.strip()

		# Return to main (base_sha)
		run_git(self.repo_dir, "checkout", "main")

		# Put protected 14-line overlay on bundle (unstaged)
		with open(os.path.join(self.repo_dir, PROTECTED_BUNDLE), "w") as f:
			f.write(PROTECTED_BUNDLE_CONTENT.decode())

		# Put protected untracked test
		os.makedirs(os.path.join(self.repo_dir, "bakery_manufacturing", "tests"), exist_ok=True)
		with open(os.path.join(self.repo_dir, PROTECTED_TEST), "w") as f:
			f.write(PROTECTED_TEST_CONTENT)

		self.manifest_path = os.path.join(self.repo_dir, "overlay_manifest.json")

	def tearDown(self):
		cutover._set_test_expected_bundle_sha(None)
		self.temp_dir.cleanup()

	def _get_bundle_sha256(self) -> str:
		with open(os.path.join(self.repo_dir, PROTECTED_BUNDLE), "rb") as f:
			return hashlib.sha256(f.read()).hexdigest()

	def _get_test_content(self) -> str:
		with open(os.path.join(self.repo_dir, PROTECTED_TEST), "r") as f:
			return f.read()

	def test_verify_checks_file_mode_and_content_matching_target(self):
		"""C1: Verify must assert that applied files in worktree and index match target blob mode and content."""
		manifest = cutover.generate_manifest(self.repo_dir, self.base_sha, self.target_sha)
		cutover.write_manifest_file(manifest, self.manifest_path)

		cutover.apply_overlay(self.repo_dir, self.base_sha, self.target_sha, self.manifest_path)

		# Verification passes when clean
		res = cutover.verify_overlay(self.repo_dir, self.base_sha, self.target_sha, self.manifest_path)
		self.assertTrue(res["valid"])

		# Corrupt worktree content of an overlay file
		with open(os.path.join(self.repo_dir, "README.md"), "w") as f:
			f.write("corrupted content\n")

		with self.assertRaisesRegex(RuntimeError, "worktree mismatch"):
			cutover.verify_overlay(self.repo_dir, self.base_sha, self.target_sha, self.manifest_path)

	def test_verify_fails_if_protected_bundle_altered(self):
		"""C1/I6: Verify must check exact protected bundle hash and fail if altered."""
		manifest = cutover.generate_manifest(self.repo_dir, self.base_sha, self.target_sha)
		cutover.write_manifest_file(manifest, self.manifest_path)

		cutover.apply_overlay(self.repo_dir, self.base_sha, self.target_sha, self.manifest_path)

		# Alter protected bundle
		with open(os.path.join(self.repo_dir, PROTECTED_BUNDLE), "w") as f:
			f.write("altered bundle\n")

		with self.assertRaisesRegex(RuntimeError, "protected bundle does not match production expected hash"):
			cutover.verify_overlay(self.repo_dir, self.base_sha, self.target_sha, self.manifest_path)

		with open(os.path.join(self.repo_dir, PROTECTED_BUNDLE), "w") as f:
			f.write(PROTECTED_BUNDLE_CONTENT.decode())
		manifest["protected_bundle_sha256"] = "0" * 64
		cutover.write_manifest_file(manifest, self.manifest_path)
		with self.assertRaisesRegex(RuntimeError, "protected bundle hash/state changed"):
			cutover.verify_overlay(self.repo_dir, self.base_sha, self.target_sha, self.manifest_path)

	def test_apply_atomicity_and_conflict_rejection(self):
		"""C2/I3: Apply must reject uncommitted modifications or untracked conflicting files on manifest paths."""
		manifest = cutover.generate_manifest(self.repo_dir, self.base_sha, self.target_sha)
		cutover.write_manifest_file(manifest, self.manifest_path)

		# Dirty uncommitted modification on a file to be modified by overlay
		with open(os.path.join(self.repo_dir, "README.md"), "w") as f:
			f.write("# Dirty uncommitted work\n")

		with self.assertRaisesRegex(RuntimeError, "manifest path has dirty or untracked changes: README.md"):
			cutover.apply_overlay(self.repo_dir, self.base_sha, self.target_sha, self.manifest_path)

		# Working tree must be untouched (atomic refusal)
		with open(os.path.join(self.repo_dir, "README.md")) as f:
			self.assertEqual(f.read(), "# Dirty uncommitted work\n")
		# New shim should not have been created
		self.assertFalse(os.path.exists(os.path.join(self.repo_dir, "bakery_manufacturing", "overrides", "new_shim.py")))

	def test_rollback_atomicity_and_conflict_rejection(self):
		"""C2/I7: Rollback must reject dirty worktree changes on overlay files before rolling back."""
		manifest = cutover.generate_manifest(self.repo_dir, self.base_sha, self.target_sha)
		cutover.write_manifest_file(manifest, self.manifest_path)

		cutover.apply_overlay(self.repo_dir, self.base_sha, self.target_sha, self.manifest_path)

		# Introduce dirty modification on new_shim.py after apply
		with open(os.path.join(self.repo_dir, "bakery_manufacturing", "overrides", "new_shim.py"), "w") as f:
			f.write("# Modified after apply\n")

		with self.assertRaisesRegex(RuntimeError, "manifest path has dirty or untracked changes: bakery_manufacturing/overrides/new_shim.py"):
			cutover.rollback_overlay(self.repo_dir, self.base_sha, self.target_sha, self.manifest_path)

	def test_casefold_internal_git_path_is_rejected(self):
		with self.assertRaisesRegex(ValueError, "invalid path"):
			cutover.canonical_path("X/.GIT/config")

	def test_canonicalize_and_reject_malformed_paths(self):
		"""C3/I4: Reject ./, //, .git, case-folded protected aliases, and symlink parent traversal."""
		for bad_path in [
			"./README.md",
			"bakery_manufacturing//overrides/pos_overrides.py",
			".git/config",
			"bakery_manufacturing/public/js/../js/bakery_manufacturing.bundle.js",
			"Bakery_Manufacturing/public/js/bakery_manufacturing.bundle.js",
		]:
			manifest = {
				"base_sha": self.base_sha,
				"target_sha": self.target_sha,
				"added": [bad_path],
				"modified": [],
				"deleted": [],
			}
			cutover.write_manifest_file(manifest, self.manifest_path)
			with self.assertRaises(ValueError):
				cutover.apply_overlay(self.repo_dir, self.base_sha, self.target_sha, self.manifest_path)

	def test_finalize_HEAD_guard_direct_probe(self):
		manifest = self._manifest()
		run_git(self.repo_dir, "checkout", "candidate")
		with self.assertRaisesRegex(RuntimeError, "HEAD is not base"):
			cutover.finalize_overlay(self.repo_dir, self.base_sha, self.target_sha, self.manifest_path)

	def test_finalize_guards(self):
		"""C4: Finalize requires HEAD==base, merge-base ancestor, valid overlay in place, protected hash intact, and unescapes staged paths."""
		manifest = cutover.generate_manifest(self.repo_dir, self.base_sha, self.target_sha)
		cutover.write_manifest_file(manifest, self.manifest_path)

		# Calling finalize before apply (overlay not applied) must fail with index mismatch
		with self.assertRaisesRegex(RuntimeError, "index paths do not exactly match manifest"):
			cutover.finalize_overlay(self.repo_dir, self.base_sha, self.target_sha, self.manifest_path)

		# Apply cleanly
		cutover.apply_overlay(self.repo_dir, self.base_sha, self.target_sha, self.manifest_path)

		# Finalize now succeeds
		cutover.finalize_overlay(self.repo_dir, self.base_sha, self.target_sha, self.manifest_path)

		self.assertEqual(run_git(self.repo_dir, "rev-parse", "HEAD").stdout.strip(), self.target_sha)
		# Index is clean
		self.assertEqual(run_git(self.repo_dir, "diff", "--cached", "--name-status").stdout.strip(), "")
		# Protected bundle and test intact
		self.assertEqual(self._get_test_content(), PROTECTED_TEST_CONTENT)
		self.assertEqual(self._get_bundle_sha256(), PROTECTED_BUNDLE_HASH)

	def test_preserve_file_mode(self):
		"""C5: Executable modes (100755) and mode transitions must be preserved on apply and rollback."""
		manifest = cutover.generate_manifest(self.repo_dir, self.base_sha, self.target_sha)
		cutover.write_manifest_file(manifest, self.manifest_path)

		cutover.apply_overlay(self.repo_dir, self.base_sha, self.target_sha, self.manifest_path)

		exec_file = os.path.join(self.repo_dir, "bakery_manufacturing", "overrides", "tool.sh")
		file_stat = os.stat(exec_file)
		# Target changed mode to 0644 (non-executable)
		self.assertFalse(bool(file_stat.st_mode & stat.S_IXUSR))

		cutover.rollback_overlay(self.repo_dir, self.base_sha, self.target_sha, self.manifest_path)

		file_stat_after = os.stat(exec_file)
		# Base was 0755 (executable)
		self.assertTrue(bool(file_stat_after.st_mode & stat.S_IXUSR))

	def test_manifest_hash_exact_bytes(self):
		"""I1/I5: verify_overlay computes SHA256 over exact manifest file bytes and validates base/target CLI arguments."""
		manifest = cutover.generate_manifest(self.repo_dir, self.base_sha, self.target_sha)
		cutover.write_manifest_file(manifest, self.manifest_path)

		cutover.apply_overlay(self.repo_dir, self.base_sha, self.target_sha, self.manifest_path)

		expected_bytes = (
			b'{\n  "added": [\n    "bakery_manufacturing/overrides/new_shim.py"\n  ],\n'
			b'  "base_sha": "' + self.base_sha.encode() + b'",\n'
			b'  "deleted": [\n    "bakery_manufacturing/doctype/old_file.py"\n  ],\n'
			b'  "modified": [\n    "README.md",\n    "bakery_manufacturing/overrides/pos_overrides.py",\n'
			b'    "bakery_manufacturing/overrides/tool.sh"\n  ],\n'
			b'  "protected_bundle_exists": true,\n'
			b'  "protected_bundle_sha256": "8b04313861b211aa17cb4d0c87c372d32e2f8b0d642b94292e58a7865ae1bbf1",\n'
			b'  "protected_test_present": true,\n'
			b'  "target_sha": "' + self.target_sha.encode() + b'"\n}\n'
		)
		with open(self.manifest_path, "rb") as f:
			self.assertEqual(f.read(), expected_bytes)

		res = cutover.verify_overlay(self.repo_dir, self.base_sha, self.target_sha, self.manifest_path)
		self.assertEqual(res["manifest_hash"], hashlib.sha256(expected_bytes).hexdigest())

		# Mismatched CLI base/target vs manifest base/target
		with self.assertRaisesRegex(ValueError, "manifest base/target does not match command arguments"):
			cutover.verify_overlay(self.repo_dir, "0000000000000000000000000000000000000000", self.target_sha, self.manifest_path)

	def test_round4_candidate_bundle_change_rejects_before_ref_move(self):
		"""A tracked candidate bundle change is rejected before finalize moves HEAD."""
		manifest = cutover.generate_manifest(self.repo_dir, self.base_sha, self.target_sha)
		cutover.write_manifest_file(manifest, self.manifest_path)
		# Add a tracked bundle change to a descendant target.
		run_git(self.repo_dir, "checkout", "-b", "bundle-candidate", self.target_sha)
		Path(self.repo_dir, PROTECTED_BUNDLE).write_text("candidate bundle\n")
		run_git(self.repo_dir, "add", PROTECTED_BUNDLE)
		run_git(self.repo_dir, "commit", "-m", "candidate bundle")
		bundle_target = run_git(self.repo_dir, "rev-parse", "HEAD").stdout.strip()
		run_git(self.repo_dir, "checkout", "main")
		# Re-put protected overlay on bundle in worktree
		with open(os.path.join(self.repo_dir, PROTECTED_BUNDLE), "w") as f:
			f.write(PROTECTED_BUNDLE_CONTENT.decode())

		bundle_manifest = cutover.generate_manifest(self.repo_dir, self.base_sha, bundle_target)
		cutover.write_manifest_file(bundle_manifest, self.manifest_path)
		with self.assertRaisesRegex(RuntimeError, "target changes protected bundle; finalize rejected before ref movement"):
			cutover.finalize_overlay(self.repo_dir, self.base_sha, bundle_target, self.manifest_path)
		self.assertEqual(run_git(self.repo_dir, "rev-parse", "HEAD").stdout.strip(), self.base_sha)

	def test_protected_test_presence_mismatch_probe(self):
		manifest = self._manifest()
		Path(self.repo_dir, PROTECTED_TEST).unlink()
		with self.assertRaisesRegex(RuntimeError, "protected test state changed"):
			cutover.apply_overlay(self.repo_dir, self.base_sha, self.target_sha, self.manifest_path)

	def test_round4_candidate_protected_test_failure_preserves_ref_and_allows_rollback(self):
		"""Ref is restored and candidate-staged error raised if finalize verification fails after soft reset."""
		manifest = cutover.generate_manifest(self.repo_dir, self.base_sha, self.target_sha)
		cutover.write_manifest_file(manifest, self.manifest_path)

		# Apply cleanly first so verify_overlay passes before reset --soft
		cutover.apply_overlay(self.repo_dir, self.base_sha, self.target_sha, self.manifest_path)

		# Create descendant target that has an additional commit modifying a file not in manifest
		run_git(self.repo_dir, "checkout", "-b", "descendant", self.target_sha)
		with open(os.path.join(self.repo_dir, "extra.txt"), "w") as f:
			f.write("extra commit\n")
		run_git(self.repo_dir, "add", "extra.txt")
		run_git(self.repo_dir, "commit", "-m", "extra commit")
		descendant_sha = run_git(self.repo_dir, "rev-parse", "HEAD").stdout.strip()
		run_git(self.repo_dir, "checkout", "main")

		# Re-apply overlay for manifest (base_sha -> self.target_sha)
		cutover.apply_overlay(self.repo_dir, self.base_sha, self.target_sha, self.manifest_path)

		# Manually craft manifest with target_sha=descendant_sha but only the original overlay files
		descendant_manifest = dict(manifest)
		descendant_manifest["target_sha"] = descendant_sha
		cutover.write_manifest_file(descendant_manifest, self.manifest_path)

		# Calling finalize with descendant_sha will pass merge-base check, pass verify_overlay (README, pos_overrides, etc match descendant tree too),
		# then git reset --soft descendant_sha will leave extra.txt staged in diff --cached!
		with self.assertRaisesRegex(RuntimeError, "candidate remains staged"):
			cutover.finalize_overlay(self.repo_dir, self.base_sha, descendant_sha, self.manifest_path)

		# Verify ref was restored back to base_sha
		self.assertEqual(run_git(self.repo_dir, "rev-parse", "HEAD").stdout.strip(), self.base_sha)

	def test_finalize_base_exception_recovery_probe(self):
		"""Finalize catches BaseException (such as KeyboardInterrupt) during post-reset checks and restores HEAD ref."""
		manifest = cutover.generate_manifest(self.repo_dir, self.base_sha, self.target_sha)
		cutover.write_manifest_file(manifest, self.manifest_path)
		cutover.apply_overlay(self.repo_dir, self.base_sha, self.target_sha, self.manifest_path)

		original_verify_protected = cutover._verify_protected
		def interrupt(repo, m):
			raise KeyboardInterrupt("simulated finalize interrupt")

		cutover._verify_protected = interrupt
		try:
			with self.assertRaisesRegex(KeyboardInterrupt, "simulated finalize interrupt"):
				cutover.finalize_overlay(self.repo_dir, self.base_sha, self.target_sha, self.manifest_path)
		finally:
			cutover._verify_protected = original_verify_protected

		# Ref must have been restored back to base_sha despite git reset --soft target having executed
		self.assertEqual(run_git(self.repo_dir, "rev-parse", "HEAD").stdout.strip(), self.base_sha)

	def test_round4_nested_untracked_added_path_blocks_apply(self):
		"""-uall nested untracked content under an added directory blocks apply via _assert_no_conflicts."""
		# Create candidate target commit that adds a file inside a new directory
		run_git(self.repo_dir, "checkout", "-b", "nested-branch", self.base_sha)
		nested_rel_dir = os.path.join("bakery_manufacturing", "nested_dir")
		nested_file = os.path.join(nested_rel_dir, "file.py")
		os.makedirs(os.path.join(self.repo_dir, nested_rel_dir), exist_ok=True)
		with open(os.path.join(self.repo_dir, nested_file), "w") as f:
			f.write("# nested file\n")
		run_git(self.repo_dir, "add", "-A")
		run_git(self.repo_dir, "commit", "-m", "add nested file")
		nested_target_sha = run_git(self.repo_dir, "rev-parse", "HEAD").stdout.strip()
		run_git(self.repo_dir, "checkout", "main")

		# Untracked nested file in worktree
		os.makedirs(os.path.join(self.repo_dir, nested_rel_dir), exist_ok=True)
		untracked_path = os.path.join(self.repo_dir, nested_file)
		original_bytes = b"operator untracked nested bytes\n"
		with open(untracked_path, "wb") as f:
			f.write(original_bytes)

		manifest = cutover.generate_manifest(self.repo_dir, self.base_sha, nested_target_sha)
		cutover.write_manifest_file(manifest, self.manifest_path)

		# Must be rejected by _assert_no_conflicts (using -uall)
		with self.assertRaisesRegex(RuntimeError, f"manifest path has dirty or untracked changes: {nested_file}"):
			cutover.apply_overlay(self.repo_dir, self.base_sha, nested_target_sha, self.manifest_path)

		# Untracked file preserved
		with open(untracked_path, "rb") as f:
			self.assertEqual(f.read(), original_bytes)

	def test_round4_added_path_already_exists_blocks_apply(self):
		"""Added path that exists in worktree (e.g. untracked or ignored) hits 'added path already exists' guard."""
		manifest = cutover.generate_manifest(self.repo_dir, self.base_sha, self.target_sha)
		cutover.write_manifest_file(manifest, self.manifest_path)

		# Ignore the added path without changing the committed base, so base remains an ancestor of target.
		with open(os.path.join(self.repo_dir, ".git", "info", "exclude"), "a") as f:
			f.write("bakery_manufacturing/overrides/new_shim.py\n")

		# _assert_no_conflicts must ignore the existing path, then the explicit added-path guard must reject it.

		# Create ignored new_shim.py file in worktree
		path = os.path.join(self.repo_dir, "bakery_manufacturing", "overrides", "new_shim.py")
		original = b"ignored existing file\n"
		with open(path, "wb") as f:
			f.write(original)

		# _assert_no_conflicts will pass because new_shim.py is ignored and not in status
		# Then the loop checking `if p in m["added"] and full.exists()` must raise RuntimeError
		with self.assertRaisesRegex(RuntimeError, "added path already exists: bakery_manufacturing/overrides/new_shim.py"):
			cutover.apply_overlay(self.repo_dir, self.base_sha, self.target_sha, self.manifest_path)

		with open(path, "rb") as f:
			self.assertEqual(f.read(), original)

	def test_round4_production_hash_without_override_and_regenerated_manifest(self):
		"""The real shared overlay matches the production constant; tampering fails _verify_protected."""
		cutover._set_test_expected_bundle_sha(None)
		# Verify production constant matches real bundle fixture
		actual = hashlib.sha256(PROTECTED_BUNDLE_CONTENT).hexdigest()
		self.assertEqual(actual, cutover.PRODUCTION_BUNDLE_SHA256)
		self.assertEqual(cutover.PRODUCTION_BUNDLE_SHA256, "8b04313861b211aa17cb4d0c87c372d32e2f8b0d642b94292e58a7865ae1bbf1")

		# In repo, modify protected bundle to tampered content
		tampered_content = b"tampered bundle content\n"
		with open(os.path.join(self.repo_dir, PROTECTED_BUNDLE), "wb") as f:
			f.write(tampered_content)

		# Regenerating manifest captures the tampered hash
		manifest = cutover.generate_manifest(self.repo_dir, self.base_sha, self.target_sha)
		self.assertEqual(manifest["protected_bundle_sha256"], hashlib.sha256(tampered_content).hexdigest())
		cutover.write_manifest_file(manifest, self.manifest_path)

		# Calling apply_overlay or verify_overlay without test expected SHA override must fail with exact error
		with self.assertRaisesRegex(RuntimeError, "protected bundle does not match production expected hash"):
			cutover.apply_overlay(self.repo_dir, self.base_sha, self.target_sha, self.manifest_path)

	def test_round4_swapped_index_oid_fails_verify(self):
		"""Correct worktree with a swapped staged OID fails verification with index blob mismatch."""
		manifest = cutover.generate_manifest(self.repo_dir, self.base_sha, self.target_sha)
		cutover.write_manifest_file(manifest, self.manifest_path)
		cutover.apply_overlay(self.repo_dir, self.base_sha, self.target_sha, self.manifest_path)

		# Swap staged OID to a different blob while keeping the manifest path set unchanged.
		other_oid = run_git(self.repo_dir, "rev-parse", f"{self.target_sha}:bakery_manufacturing/overrides/pos_overrides.py").stdout.strip()
		run_git(self.repo_dir, "update-index", "--cacheinfo", "100644", other_oid, "README.md")

		with self.assertRaisesRegex(RuntimeError, "index blob mismatch: README.md"):
			cutover.verify_overlay(self.repo_dir, self.base_sha, self.target_sha, self.manifest_path)

	def test_round4_parent_symlink_blocks_without_external_write(self):
		"""A symlinked parent directory within repo blocks apply and does not write outside the repository."""
		manifest = cutover.generate_manifest(self.repo_dir, self.base_sha, self.target_sha)
		manifest["modified"] = []
		manifest["deleted"] = []
		manifest["added"] = ["bakery_manufacturing/overrides/new_shim.py"]
		cutover.write_manifest_file(manifest, self.manifest_path)

		external = tempfile.TemporaryDirectory()
		parent = os.path.join(self.repo_dir, "bakery_manufacturing", "overrides")
		# Replace overrides dir with a symlink pointing outside repo and hide the
		# whole parent so status does not preempt the symlink guard.
		shutil.rmtree(parent)
		os.symlink(external.name, parent)
		with open(os.path.join(self.repo_dir, ".git", "info", "exclude"), "a") as f:
			f.write("bakery_manufacturing/overrides\n")

		with self.assertRaisesRegex(RuntimeError, "unsafe symlink path: bakery_manufacturing/overrides/new_shim.py"):
			cutover.apply_overlay(self.repo_dir, self.base_sha, self.target_sha, self.manifest_path)

		self.assertEqual(os.listdir(external.name), [])
		external.cleanup()

	def test_base_exception_recovery_mutation_probe(self):
		manifest = self._manifest()
		original = cutover._write_blob
		calls = 0
		def interrupt(repo, rev, path):
			nonlocal calls
			calls += 1
			if calls == 2:
				raise KeyboardInterrupt("simulated interrupt")
			return original(repo, rev, path)
		cutover._write_blob = interrupt
		try:
			with self.assertRaisesRegex(KeyboardInterrupt, "simulated interrupt"):
				cutover.apply_overlay(self.repo_dir, self.base_sha, self.target_sha, self.manifest_path)
		finally:
			cutover._write_blob = original
		self.assertEqual(run_git(self.repo_dir, "diff", "--", "README.md").stdout, "")
		self.assertEqual(run_git(self.repo_dir, "diff", "--cached", "--name-only").stdout, "")

	def test_round4_mode_transition_and_ignored_failure_restore(self):
		"""True mode transition (0755 -> 0644) is verified; apply failure restores atomic pristine state."""
		manifest = cutover.generate_manifest(self.repo_dir, self.base_sha, self.target_sha)
		cutover.write_manifest_file(manifest, self.manifest_path)

		# Verify mode before apply is 0755
		tool_path = os.path.join(self.repo_dir, "bakery_manufacturing", "overrides", "tool.sh")
		base_mode = stat.S_IMODE(os.stat(tool_path).st_mode)
		self.assertEqual(base_mode, 0o755)

		# Apply overlay cleanly
		cutover.apply_overlay(self.repo_dir, self.base_sha, self.target_sha, self.manifest_path)

		# Verify mode after apply transitioned to 0644
		applied_mode = stat.S_IMODE(os.stat(tool_path).st_mode)
		self.assertEqual(applied_mode, 0o644)

		# Rollback overlay
		cutover.rollback_overlay(self.repo_dir, self.base_sha, self.target_sha, self.manifest_path)
		rolled_back_mode = stat.S_IMODE(os.stat(tool_path).st_mode)
		self.assertEqual(rolled_back_mode, 0o755)

		# Now test atomic exception recovery during apply with a failure after the first write.
		orig_write_blob = cutover._write_blob
		write_count = 0
		def failing_write_blob(repo, rev, path):
			nonlocal write_count
			write_count += 1
			if write_count > 1:
				raise OSError("simulated disk failure during apply")
			return orig_write_blob(repo, rev, path)

		cutover._write_blob = failing_write_blob
		try:
			with self.assertRaisesRegex(OSError, "simulated disk failure during apply"):
				cutover.apply_overlay(self.repo_dir, self.base_sha, self.target_sha, self.manifest_path)
		finally:
			cutover._write_blob = orig_write_blob

		# Verify every pre-existing tracked path was restored. Git may retain the
		# added path in the index after reset when the injected failure occurs before
		# its write, so only the added path is tolerated across Git versions.
		staged_paths = set(run_git(self.repo_dir, "diff", "--cached", "--name-only").stdout.splitlines())
		self.assertIn(staged_paths, [set(), {"bakery_manufacturing/overrides/new_shim.py"}])
		self.assertEqual(run_git(self.repo_dir, "diff", "--name-only", "--", "README.md").stdout.strip(), "")
		self.assertEqual(stat.S_IMODE(os.stat(tool_path).st_mode), 0o755)

	def test_protect_tool_scripts_from_manifest(self):
		"""I8/I9: scripts/ownership_cutover.py itself and scripts/__init__.py are protected from candidate overlay mutations."""
		for protected_script in ["scripts/ownership_cutover.py", "scripts/__init__.py", "SCRIPTS/__init__.py", "scripts/OWNERSHIP_CUTOVER.PY"]:
			manifest = {
				"base_sha": self.base_sha,
				"target_sha": self.target_sha,
				"added": [protected_script],
				"modified": [],
				"deleted": [],
			}
			cutover.write_manifest_file(manifest, self.manifest_path)
			with self.assertRaisesRegex(ValueError, f"protected path: {protected_script}"):
				cutover.apply_overlay(self.repo_dir, self.base_sha, self.target_sha, self.manifest_path)

	def _manifest(self):
		manifest = cutover.generate_manifest(self.repo_dir, self.base_sha, self.target_sha)
		cutover.write_manifest_file(manifest, self.manifest_path)
		return manifest

	def test_apply_HEAD_guard(self):
		self._manifest()
		run_git(self.repo_dir, "checkout", "candidate")
		with self.assertRaisesRegex(RuntimeError, "HEAD is not base"):
			cutover.apply_overlay(self.repo_dir, self.base_sha, self.target_sha, self.manifest_path)

	def test_verify_HEAD_guard(self):
		self._manifest()
		run_git(self.repo_dir, "checkout", "candidate")
		with self.assertRaisesRegex(RuntimeError, "HEAD is not base"):
			cutover.verify_overlay(self.repo_dir, self.base_sha, self.target_sha, self.manifest_path)

	def test_rollback_HEAD_guard(self):
		self._manifest()
		run_git(self.repo_dir, "checkout", "candidate")
		with self.assertRaisesRegex(RuntimeError, "HEAD is not base"):
			cutover.rollback_overlay(self.repo_dir, self.base_sha, self.target_sha, self.manifest_path)

	def test_unresolved_conflict_rejection_mutation_probe(self):
		manifest = self._manifest()
		Path(self.repo_dir, "README.md").write_text("dirty\n")
		run_git(self.repo_dir, "add", "README.md")
		with self.assertRaisesRegex(RuntimeError, "staged changes"):
			cutover.apply_overlay(self.repo_dir, self.base_sha, self.target_sha, self.manifest_path)

	def test_unresolved_U_status_rejection_mutation_probe(self):
		self._manifest()
		original = cutover._status
		cutover._status = lambda repo: [("UU", "README.md")]
		try:
			with self.assertRaisesRegex(RuntimeError, "unresolved conflict"):
				cutover.apply_overlay(self.repo_dir, self.base_sha, self.target_sha, self.manifest_path)
		finally:
			cutover._status = original

	def test_reject_diff_with_rename_or_copy_mutation_probe(self):
		self._manifest()
		original = cutover.git
		def renamed(repo, *args, **kwargs):
			if args[:2] == ("diff", "--name-status"):
				return subprocess.CompletedProcess([], 0, "R100\0README.md\0renamed.md\0", "")
			return original(repo, *args, **kwargs)
		cutover.git = renamed
		try:
			with self.assertRaisesRegex(ValueError, "unknown status: R100"):
				cutover.generate_manifest(self.repo_dir, self.base_sha, self.target_sha)
		finally:
			cutover.git = original

	def test_generate_manifest_rename_rejected_mutation_probe(self):
		self._manifest()
		original_git = cutover.git
		original_path = cutover.canonical_path
		calls = []
		def renamed(repo, *args, **kwargs):
			if args[:2] == ("diff", "--name-status"):
				return subprocess.CompletedProcess([], 0, "R100\0README.md\0renamed.md\0", "")
			return original_git(repo, *args, **kwargs)
		cutover.git = renamed
		cutover.canonical_path = lambda path: calls.append(path) or original_path(path)
		try:
			with self.assertRaises(ValueError):
				cutover.generate_manifest(self.repo_dir, self.base_sha, self.target_sha)
			self.assertEqual(calls, ["README.md", "renamed.md"])
		finally:
			cutover.git = original_git
			cutover.canonical_path = original_path

	def test_generate_manifest_rename_rejected_mutation_probe_legacy(self):
		self._manifest()
		original = cutover.git
		def renamed(repo, *args, **kwargs):
			if args[:2] == ("diff", "--name-status"):
				return subprocess.CompletedProcess([], 0, "R100\0README.md\0renamed.md\0", "")
			return original(repo, *args, **kwargs)
		cutover.git = renamed
		try:
			with self.assertRaisesRegex(ValueError, "unknown status: R100"):
				cutover.generate_manifest(self.repo_dir, self.base_sha, self.target_sha)
		finally:
			cutover.git = original

	def test_generate_manifest_canonical_path_mutation_probe(self):
		self._manifest()
		original = cutover.canonical_path
		calls = []
		cutover.canonical_path = lambda path: calls.append(path) or original(path)
		try:
			cutover.generate_manifest(self.repo_dir, self.base_sha, self.target_sha)
			self.assertGreaterEqual(len(calls), 4)
		finally:
			cutover.canonical_path = original

		manifest = self._manifest()
		manifest["added"] = ["README.md"]
		cutover.write_manifest_file(manifest, self.manifest_path)
		with self.assertRaisesRegex((ValueError, RuntimeError), "(manifest|index|added)"):
			cutover.apply_overlay(self.repo_dir, self.base_sha, self.target_sha, self.manifest_path)

	def test_generate_ancestry_mutation_probe(self):
		self._manifest()
		with self.assertRaises(subprocess.CalledProcessError):
			cutover.generate_manifest(self.repo_dir, self.target_sha, self.base_sha)

	def test_finalize_HEAD_mutation_probe(self):
		self._manifest()
		original_verify = cutover.verify_overlay
		cutover.verify_overlay = lambda *args: {"valid": True}
		run_git(self.repo_dir, "checkout", "candidate")
		try:
			with self.assertRaisesRegex(RuntimeError, "HEAD is not base"):
				cutover.finalize_overlay(self.repo_dir, self.base_sha, self.target_sha, self.manifest_path)
		finally:
			cutover.verify_overlay = original_verify
			run_git(self.repo_dir, "checkout", "main")

	def test_finalize_ancestry_mutation_probe(self):
		self._manifest()
		original = cutover.git
		def non_ancestor(repo, *args, **kwargs):
			if args[:2] == ("merge-base", "--is-ancestor"):
				raise subprocess.CalledProcessError(1, args)
			return original(repo, *args, **kwargs)
		cutover.git = non_ancestor
		try:
			with self.assertRaises(subprocess.CalledProcessError):
				cutover.finalize_overlay(self.repo_dir, self.base_sha, self.target_sha, self.manifest_path)
		finally:
			cutover.git = original

	def test_verify_deleted_path_absent_mutation_probe(self):
		self._manifest()
		cutover.apply_overlay(self.repo_dir, self.base_sha, self.target_sha, self.manifest_path)
		Path(self.repo_dir, "bakery_manufacturing/doctype/old_file.py").write_text("resurrected\n")
		with self.assertRaisesRegex(RuntimeError, "deleted path exists"):
			cutover.verify_overlay(self.repo_dir, self.base_sha, self.target_sha, self.manifest_path)

	def test_verify_malformed_staged_status_mutation_probe(self):
		self._manifest()
		original = cutover.git
		def malformed(repo, *args, **kwargs):
			if args[:3] == ("diff", "--cached", "--name-status"):
				return subprocess.CompletedProcess([], 0, "M\0", "")
			return original(repo, *args, **kwargs)
		cutover.git = malformed
		try:
			with self.assertRaisesRegex(RuntimeError, "malformed staged status"):
				cutover.verify_overlay(self.repo_dir, self.base_sha, self.target_sha, self.manifest_path)
		finally:
			cutover.git = original

	def test_target_blob_prevalidation_blocks_writes_atomically(self):
		"""AM17: When manifest has a valid first path and a missing second path, prevalidation fails BEFORE any write/staging attempt."""
		added_paths = sorted(["bakery_manufacturing/overrides/new_shim.py", "bakery_manufacturing/overrides/missing_target_file.py"])
		manifest = {
			"base_sha": self.base_sha,
			"target_sha": self.target_sha,
			"added": added_paths,
			"modified": [],
			"deleted": [],
			"protected_bundle_sha256": cutover.PRODUCTION_BUNDLE_SHA256,
			"protected_bundle_exists": True,
			"protected_test_present": True,
		}
		cutover.write_manifest_file(manifest, self.manifest_path)

		writes = []
		orig_write_blob = cutover._write_blob
		def tracking_write_blob(repo, rev, path):
			writes.append((rev, path))
			return orig_write_blob(repo, rev, path)

		cutover._write_blob = tracking_write_blob
		try:
			with self.assertRaisesRegex(RuntimeError, "missing target tree path: bakery_manufacturing/overrides/missing_target_file.py"):
				cutover.apply_overlay(self.repo_dir, self.base_sha, self.target_sha, self.manifest_path)
		finally:
			cutover._write_blob = orig_write_blob

		self.assertEqual(writes, [], "No write operation should be attempted if prevalidation is present")
		# Also verify first file was never created in worktree
		first_file = Path(self.repo_dir, "bakery_manufacturing/overrides/new_shim.py")
		self.assertFalse(first_file.exists(), "First added path should not have been written")

	def test_missing_target_blob_mutation_probe(self):
		manifest = self._manifest()
		manifest["added"] = ["missing.txt"]
		cutover.write_manifest_file(manifest, self.manifest_path)
		with self.assertRaisesRegex(RuntimeError, "missing target tree path"):
			cutover.apply_overlay(self.repo_dir, self.base_sha, self.target_sha, self.manifest_path)

	def test_manifest_sorted_unique_mutation_probe(self):
		manifest = self._manifest()
		manifest["modified"] = ["README.md", "README.md"]
		cutover.write_manifest_file(manifest, self.manifest_path)
		with self.assertRaisesRegex(ValueError, "unique and sorted"):
			cutover.validate_manifest(manifest, self.base_sha, self.target_sha)

	def test_manifest_cross_section_duplicate_mutation_probe(self):
		manifest = self._manifest()
		manifest["added"] = ["README.md"]
		cutover.write_manifest_file(manifest, self.manifest_path)
		with self.assertRaisesRegex(ValueError, "more than once"):
			cutover.validate_manifest(manifest, self.base_sha, self.target_sha)

	def test_verify_worktree_mode_mutation_probe(self):
		manifest = self._manifest()
		cutover.apply_overlay(self.repo_dir, self.base_sha, self.target_sha, self.manifest_path)
		path = Path(self.repo_dir, "README.md")
		path.chmod(0o755)
		with self.assertRaisesRegex(RuntimeError, "worktree mismatch"):
			cutover.verify_overlay(self.repo_dir, self.base_sha, self.target_sha, self.manifest_path)

	def test_verify_index_mode_mutation_probe(self):
		manifest = self._manifest()
		cutover.apply_overlay(self.repo_dir, self.base_sha, self.target_sha, self.manifest_path)
		run_git(self.repo_dir, "update-index", "--chmod=+x", "README.md")
		with self.assertRaisesRegex(RuntimeError, "index mode mismatch"):
			cutover.verify_overlay(self.repo_dir, self.base_sha, self.target_sha, self.manifest_path)

	def test_binary_blob_handling_mutation_probe(self):
		manifest = self._manifest()
		cutover.apply_overlay(self.repo_dir, self.base_sha, self.target_sha, self.manifest_path)
		_, data, _ = cutover._blob(self.repo_dir, self.target_sha, "README.md")
		self.assertIsInstance(data, bytes)
		self.assertEqual(data, b"# Candidate Readme\n")
		# Also assert type directly
		if not isinstance(data, bytes):
			raise TypeError(f"expected bytes, got {type(data).__name__}")

	def test_cat_file_binary_flag_respected(self):
		manifest = self._manifest()
		cutover.apply_overlay(self.repo_dir, self.base_sha, self.target_sha, self.manifest_path)
		# Ensure cat-file with binary=True returns bytes even with custom text kwarg tampering
		res = cutover.git(self.repo_dir, "cat-file", "blob", f"{self.target_sha}:README.md", binary=True)
		self.assertIsInstance(res.stdout, bytes)
		self.assertEqual(res.stdout, b"# Candidate Readme\n")

	def test_rename_old_new_dirty_path_conflict_mutation_probe_actual(self):
		manifest = self._manifest()
		run_git(self.repo_dir, "mv", "README.md", "renamed.md")
		with self.assertRaisesRegex(RuntimeError, "(dirty or untracked changes|staged changes)"):
			cutover.apply_overlay(self.repo_dir, self.base_sha, self.target_sha, self.manifest_path)

	def test_status_rename_records_both_paths(self):
		self._manifest()
		run_git(self.repo_dir, "mv", "README.md", "renamed.md")
		paths = {path for _, path in cutover._status(self.repo_dir)}
		self.assertIn("README.md", paths)
		self.assertIn("renamed.md", paths)

	def test_rename_old_new_dirty_path_conflict_mutation_probe(self):
		manifest = self._manifest()
		original = cutover._status
		cutover._status = lambda repo: [("R ", "README.md"), ("R ", "renamed.md")]
		try:
			with self.assertRaisesRegex(RuntimeError, "(dirty or untracked changes|staged changes)"):
				cutover.apply_overlay(self.repo_dir, self.base_sha, self.target_sha, self.manifest_path)
		finally:
			cutover._status = original

	def test_reject_unrelated_pre_existing_staged_index_mutation_probe(self):
		self._manifest()
		Path(self.repo_dir, "operator.txt").write_text("operator\n")
		run_git(self.repo_dir, "add", "operator.txt")
		with self.assertRaisesRegex(RuntimeError, "staged changes"):
			cutover.apply_overlay(self.repo_dir, self.base_sha, self.target_sha, self.manifest_path)

	def test_round4_parent_symlink_blocks_rollback_added_path(self):
		manifest = self._manifest()
		manifest["modified"] = []
		manifest["deleted"] = []
		manifest["added"] = ["bakery_manufacturing/overrides/new_shim.py"]
		cutover.write_manifest_file(manifest, self.manifest_path)
		external = tempfile.TemporaryDirectory()
		path = Path(self.repo_dir, "bakery_manufacturing/overrides")
		shutil.rmtree(path)
		path.symlink_to(external.name, target_is_directory=True)
		with open(Path(self.repo_dir, ".git/info/exclude"), "a") as exclude:
			exclude.write("bakery_manufacturing/overrides\n")
		with self.assertRaisesRegex(RuntimeError, "unsafe symlink path"):
			cutover.rollback_overlay(self.repo_dir, self.base_sha, self.target_sha, self.manifest_path)
		self.assertEqual(list(Path(external.name).iterdir()), [])
		external.cleanup()


if __name__ == "__main__":
	unittest.main()
