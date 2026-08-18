"""Reproducible, test-only Ruling AM mutation harness.

Run from the bakery app root with:
    python3 -m unittest bakery_manufacturing.tests.ownership_cutover_mutations
or directly with:
    python3 -m bakery_manufacturing.tests.ownership_cutover_mutations
"""
from __future__ import annotations

import hashlib
import py_compile
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "scripts" / "ownership_cutover.py"
TEST_MODULE = "bakery_manufacturing.tests.test_ownership_cutover"
TEST_CLASS = f"{TEST_MODULE}.TestOwnershipCutoverHardened"

MUTATIONS = [
    ("AM01", "_verify_protected", "if actual != m.get(\"protected_bundle_sha256\") or p.exists() != m.get(\"protected_bundle_exists\"):", "if False:", "test_verify_fails_if_protected_bundle_altered"),
    ("AM02", "_verify_protected", "if Path(repo, PROTECTED_TEST).exists() != bool(m.get(\"protected_test_present\")):", "if False:", "test_protected_test_presence_mismatch_probe"),
    ("AM03", "apply_overlay", "if git(repo, \"rev-parse\", \"HEAD\").stdout.strip() != base:", "if False:", "test_apply_HEAD_guard"),
    ("AM04", "verify_overlay", "if git(repo, \"rev-parse\", \"HEAD\").stdout.strip() != base:", "if False:", "test_verify_HEAD_guard"),
    ("AM05", "rollback_overlay", "if git(repo, \"rev-parse\", \"HEAD\").stdout.strip() != base:", "if False:", "test_rollback_HEAD_guard"),
    ("AM06", "finalize_overlay", "if git(repo, \"rev-parse\", \"HEAD\").stdout.strip() != base:", "if False:", "test_finalize_HEAD_mutation_probe"),
    ("AM07", "_assert_no_conflicts", "if code[0] == \"U\" or code[1] == \"U\":", "if False:", "test_unresolved_U_status_rejection_mutation_probe"),
    ("AM08", "generate_manifest", "if status[0] in \"RC\":", "if False:", "test_generate_manifest_rename_rejected_mutation_probe"),
    ("AM09", "generate_manifest", "canonical_path(old_path)", "pass", "test_generate_manifest_rename_rejected_mutation_probe"),
    ("AM10", "generate_manifest", "canonical_path(path)", "pass", "test_generate_manifest_canonical_path_mutation_probe"),
    ("AM11", "generate_manifest", "git(repo, \"merge-base\", \"--is-ancestor\", base_sha, target_sha)", "pass", "test_generate_ancestry_mutation_probe"),
    ("AM12", "finalize_overlay", "git(repo, \"merge-base\", \"--is-ancestor\", base, target)", "pass", "test_finalize_ancestry_mutation_probe"),
    ("AM13", "verify_overlay", "if full.exists():\n\t\t\t\traise RuntimeError(f\"deleted path exists: {p}\")", "if False:\n\t\t\t\traise RuntimeError(f\"deleted path exists: {p}\")", "test_verify_deleted_path_absent_mutation_probe"),
    ("AM14", "verify_overlay", "stat.S_IMODE(full.stat().st_mode) != stat.S_IMODE(mode)", "False", "test_verify_worktree_mode_mutation_probe"),
    ("AM15", "verify_overlay", "int(idx[0], 8) != mode", "False", "test_verify_index_mode_mutation_probe"),
    ("AM16", "verify_overlay", "raise RuntimeError(\"malformed staged status\")", "pass", "test_verify_malformed_staged_status_mutation_probe"),
    ("AM17", "apply_overlay", "for p in m[\"added\"] + m[\"modified\"]:\n\t\t_blob(repo, target, p)", "pass", "test_target_blob_prevalidation_blocks_writes_atomically"),
    ("AM18", "apply_overlay", "except BaseException:", "except Exception:", "test_base_exception_recovery_mutation_probe"),
    ("AM19", "_blob", "if not line:", "if False:", "test_missing_target_blob_mutation_probe"),
    ("AM20", "validate_manifest", "values != sorted(set(values))", "False", "test_manifest_sorted_unique_mutation_probe"),
    ("AM21", "validate_manifest", "if len(paths) != len(set(paths)):", "if False:", "test_manifest_cross_section_duplicate_mutation_probe"),
    ("AM22", "write_manifest_file", "sort_keys=True", "sort_keys=False", "test_manifest_hash_exact_bytes"),
    ("AM23", "write_manifest_file", "+ \"\\n\"", "+ \"\"", "test_manifest_hash_exact_bytes"),
    ("AM24", "_blob", "data = git(repo, \"cat-file\", \"blob\", obj, binary=True).stdout", "data = git(repo, \"cat-file\", \"blob\", obj, binary=False).stdout", "test_binary_blob_handling_mutation_probe"),
    ("AM25", "rollback_overlay", "for p in paths:\n\t\tfull = Path(repo, p)", "for p in []:\n\t\tfull = Path(repo, p)", "test_round4_parent_symlink_blocks_rollback_added_path"),
    ("AM26", "canonical_path", "part.casefold() == \".git\"", "False", "test_casefold_internal_git_path_is_rejected"),
    ("AM27", "_status", "result.append((code, orig_path))", "pass", "test_status_rename_records_both_paths"),
    ("AM28", "_assert_no_conflicts", "if not allow_staged and code[0] in \"MADRC\":", "if False:", "test_reject_unrelated_pre_existing_staged_index_mutation_probe"),
]


def run_all_mutations(verbose: bool = True) -> tuple[int, int, int]:
    """Execute 28 mutations in an isolated copy and return (caught, survived, invalid)."""
    baseline_bytes = SOURCE.read_bytes()
    baseline_sha = hashlib.sha256(baseline_bytes).hexdigest()

    caught_count = 0
    survived_count = 0
    invalid_count = 0

    with tempfile.TemporaryDirectory(prefix="ruling-am-") as temp:
        copy = Path(temp) / "bakery_manufacturing"
        shutil.copytree(ROOT, copy, symlinks=True)
        source = copy / "scripts" / "ownership_cutover.py"

        # Baseline verification: suite must run 100% green before any mutation is tested
        baseline_proc = subprocess.run(
            ["python3", "-m", "unittest", TEST_MODULE],
            cwd=copy,
            capture_output=True,
            text=True,
            env={"PYTHONPATH": str(copy)},
        )
        if baseline_proc.returncode != 0:
            if verbose:
                print(f"HARNESS-INVALID: baseline suite failed to pass cleanly:\n{baseline_proc.stderr}")
            return (0, 0, len(MUTATIONS))

        for mutation_id, guard, old, new, killer_test in MUTATIONS:
            source.write_bytes(baseline_bytes)
            text = source.read_text()
            start = text.find(f"def {guard}(")
            if start < 0:
                start = text.find(f"def {guard}")
            if start < 0:
                if verbose:
                    print(f"{mutation_id} {guard} HARNESS-INVALID missing_guard")
                invalid_count += 1
                continue

            next_def = text.find("\ndef ", start + 5)
            end = len(text) if next_def < 0 else next_def
            region = text[start:end]
            count = region.count(old)
            if count != 1:
                if verbose:
                    print(f"{mutation_id} {guard} HARNESS-INVALID replacement_count={count}")
                invalid_count += 1
                continue

            mutated_text = text[:start] + region.replace(old, new, 1) + text[end:]
            source.write_text(mutated_text)

            # Compile check
            try:
                py_compile.compile(str(source), doraise=True)
            except py_compile.PyCompileError as e:
                if verbose:
                    print(f"{mutation_id} {guard} HARNESS-INVALID compile_error: {e}")
                invalid_count += 1
                continue

            # Full test suite execution
            full_proc = subprocess.run(
                ["python3", "-m", "unittest", TEST_MODULE],
                cwd=copy,
                capture_output=True,
                text=True,
                env={"PYTHONPATH": str(copy)},
            )
            full_caught = full_proc.returncode != 0

            # Killer test execution
            killer_proc = subprocess.run(
                ["python3", "-m", "unittest", f"{TEST_CLASS}.{killer_test}"],
                cwd=copy,
                capture_output=True,
                text=True,
                env={"PYTHONPATH": str(copy)},
            )
            killer_output = killer_proc.stderr + killer_proc.stdout
            killer_caught = killer_proc.returncode != 0 and killer_test in killer_output

            if full_caught and killer_caught:
                caught_count += 1
                status = "CAUGHT"
            else:
                survived_count += 1
                status = "SURVIVED"

            if verbose:
                print(f"{mutation_id} guard={guard} killer={killer_test} full_caught={full_caught} killer_caught={killer_caught} -> {status}")

            if hashlib.sha256(SOURCE.read_bytes()).hexdigest() != baseline_sha:
                if verbose:
                    print(f"{mutation_id} HARNESS-INVALID source baseline changed")
                return (caught_count, survived_count, invalid_count + 1)

    if verbose:
        print(f"RESULT: {caught_count}/{len(MUTATIONS)} CAUGHT; {survived_count} SURVIVED; {invalid_count} HARNESS-INVALID")

    return (caught_count, survived_count, invalid_count)


class TestRulingAMMutations(unittest.TestCase):
    def test_28_mutations_caught(self):
        caught, survived, invalid = run_all_mutations(verbose=False)
        self.assertEqual(invalid, 0, f"Harness invalid count: {invalid}")
        self.assertEqual(survived, 0, f"Mutations survived: {survived}")
        self.assertEqual(caught, 28, f"Mutations caught: {caught}/28")


def main() -> int:
    caught, survived, invalid = run_all_mutations(verbose=True)
    return 0 if (caught == len(MUTATIONS) and survived == 0 and invalid == 0) else 1


if __name__ == "__main__":
    raise SystemExit(main())
