#!/usr/bin/env python3
"""Guarded candidate overlay operations for the shared bakery checkout."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import subprocess
from pathlib import Path

PROTECTED_BUNDLE = "bakery_manufacturing/public/js/bakery_manufacturing.bundle.js"
PROTECTED_TEST = "bakery_manufacturing/tests/test_desk_sidebar.py"
PRODUCTION_BUNDLE_SHA256 = "8b04313861b211aa17cb4d0c87c372d32e2f8b0d642b94292e58a7865ae1bbf1"
PROTECTED_PATHS = {
	PROTECTED_BUNDLE,
	PROTECTED_TEST,
	"scripts/ownership_cutover.py",
	"scripts/__init__.py",
}
_TEST_EXPECTED_BUNDLE_SHA256 = None


def _expected_bundle_sha() -> str:
	return _TEST_EXPECTED_BUNDLE_SHA256 or PRODUCTION_BUNDLE_SHA256


def _set_test_expected_bundle_sha(value: str | None) -> None:
	"""Test-only injection; CLI never calls this function."""
	global _TEST_EXPECTED_BUNDLE_SHA256
	_TEST_EXPECTED_BUNDLE_SHA256 = value


def git(repo: str, *args: str, check: bool = True, binary: bool = False):
	return subprocess.run(
		["git", "-C", repo, *args],
		check=check,
		capture_output=True,
		text=not binary,
	)


def canonical_path(path: str) -> str:
	if not path or path.startswith("/") or "\\" in path or "//" in path or path.startswith("./"):
		raise ValueError(f"invalid path: {path}")
	parts = path.split("/")
	if any(part in ("", ".", "..") for part in parts) or any(part.casefold() == ".git" for part in parts):
		raise ValueError(f"invalid path: {path}")
	if path != "/".join(parts):
		raise ValueError(f"non-canonical path: {path}")
	if path.casefold() in {p.casefold() for p in PROTECTED_PATHS}:
		raise ValueError(f"protected path: {path}")
	if path in PROTECTED_PATHS:
		raise ValueError(f"protected path: {path}")
	return path


def validate_manifest(manifest: dict, base: str, target: str) -> None:
	if manifest.get("base_sha") != base or manifest.get("target_sha") != target:
		raise ValueError("manifest base/target does not match command arguments")
	paths = []
	for section in ("added", "modified", "deleted"):
		values = manifest.get(section, [])
		if not isinstance(values, list) or values != sorted(set(values)):
			raise ValueError("manifest paths must be unique and sorted")
		paths.extend(canonical_path(p) for p in values)
	if len(paths) != len(set(paths)):
		raise ValueError("manifest path appears more than once")


def _status(repo: str) -> list[tuple[str, str]]:
	out = git(repo, "status", "--porcelain=v1", "-z", "-uall").stdout
	items = out.split("\0")
	result = []
	i = 0
	while i < len(items) - 1:
		record = items[i]
		i += 1
		if not record:
			continue
		code, path = record[:2], record[3:]
		result.append((code, path))
		if code[0] in "RC" or code[1] in "RC":
			if i < len(items) - 1:
				orig_path = items[i]
				i += 1
				result.append((code, orig_path))
	return result


def _manifest_paths(m: dict) -> set[str]:
	return set(m.get("added", []) + m.get("modified", []) + m.get("deleted", []))


def _assert_no_conflicts(repo: str, paths: set[str], allow_staged: bool = False) -> None:
	for code, path in _status(repo):
		if code[0] == "U" or code[1] == "U":
			raise RuntimeError("repository has unresolved conflict")
		if not allow_staged and code[0] in "MADRC":
			raise RuntimeError(f"repository has staged changes before apply: {path}")
		if path not in paths:
			continue
		if allow_staged and code[0] in "AMD" and code[1] == " ":
			continue
		raise RuntimeError(f"manifest path has dirty or untracked changes: {path}")


def _blob(repo: str, rev: str, path: str) -> tuple[str, bytes, int]:
	line = git(repo, "ls-tree", rev, "--", path).stdout
	if not line:
		raise RuntimeError(f"missing target tree path: {path}")
	mode, _, rest = line.partition(" ")
	_, _, name = rest.partition("\t")
	obj = git(repo, "rev-parse", f"{rev}:{path}").stdout.strip()
	data = git(repo, "cat-file", "blob", obj, binary=True).stdout
	return obj, data, int(mode, 8)


def _assert_safe_path(repo: str, path: str) -> Path:
	root = Path(repo).resolve()
	full = Path(repo, path)
	resolved = full.parent.resolve(strict=False) / full.name
	if resolved != root and root not in resolved.parents:
		raise RuntimeError(f"unsafe path outside repository: {path}")
	if full.is_symlink() or any(
		parent.is_symlink()
		for parent in full.parents
		if parent != Path(repo) and parent.is_relative_to(Path(repo))
	):
		raise RuntimeError(f"unsafe symlink path: {path}")
	return full


def _write_blob(repo: str, rev: str, path: str) -> None:
	_, data, mode = _blob(repo, rev, path)
	full = _assert_safe_path(repo, path)
	full.parent.mkdir(parents=True, exist_ok=True)
	full.write_bytes(data)
	os.chmod(full, stat.S_IMODE(mode))


def _protected_snapshot(repo: str) -> tuple[str, bool, str | None]:
	p = Path(repo, PROTECTED_BUNDLE)
	return (
		hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else "",
		p.exists(),
		PROTECTED_TEST if Path(repo, PROTECTED_TEST).exists() else None,
	)


def generate_manifest(repo: str, base_sha: str, target_sha: str) -> dict:
	git(repo, "merge-base", "--is-ancestor", base_sha, target_sha)
	out = git(repo, "diff", "--name-status", "-z", base_sha, target_sha).stdout
	parts = out.split("\0")
	added = []
	modified = []
	deleted = []
	i = 0
	while i < len(parts) - 1:
		status = parts[i]
		i += 1
		if not status:
			continue
		path = parts[i]
		i += 1
		if status[0] in "RC":
			if i >= len(parts) - 1:
				raise ValueError(f"malformed rename/copy status: {status}")
			old_path = path
			path = parts[i]
			i += 1
			canonical_path(old_path)
		if status[0] == "U":
			raise ValueError(f"unsupported status: {status}")
		if path.casefold() in {p.casefold() for p in PROTECTED_PATHS}:
			continue
		canonical_path(path)
		if status == "A":
			added.append(path)
		elif status == "M":
			modified.append(path)
		elif status == "D":
			deleted.append(path)
		else:
			raise ValueError(f"unknown status: {status}")
	bundle_hash, bundle_exists, test_path = _protected_snapshot(repo)
	return {
		"base_sha": base_sha,
		"target_sha": target_sha,
		"added": sorted(added),
		"modified": sorted(modified),
		"deleted": sorted(deleted),
		"protected_bundle_sha256": bundle_hash,
		"protected_bundle_exists": bundle_exists,
		"protected_test_present": bool(test_path),
	}


def write_manifest_file(manifest: dict, path: str) -> None:
	Path(path).write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")


def read_manifest_file(path: str) -> dict:
	return json.loads(Path(path).read_text())


def _verify_protected(repo: str, m: dict) -> None:
	p = Path(repo, PROTECTED_BUNDLE)
	actual = hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else ""
	if actual != _expected_bundle_sha():
		raise RuntimeError("protected bundle does not match production expected hash")
	if actual != m.get("protected_bundle_sha256") or p.exists() != m.get("protected_bundle_exists"):
		raise RuntimeError("protected bundle hash/state changed")
	if Path(repo, PROTECTED_TEST).exists() != bool(m.get("protected_test_present")):
		raise RuntimeError("protected test state changed")


def apply_overlay(repo: str, base: str, target: str, manifest_path: str) -> None:
	m = read_manifest_file(manifest_path)
	validate_manifest(m, base, target)
	if git(repo, "rev-parse", "HEAD").stdout.strip() != base:
		raise RuntimeError("HEAD is not base")
	paths = _manifest_paths(m)
	_assert_no_conflicts(repo, paths)
	_verify_protected(repo, m)
	# Complete prevalidation, including ignored/untracked paths and symlink parents.
	for p in paths:
		full = Path(repo, p)
		if full.is_symlink() or any(
			parent.is_symlink()
			for parent in full.parents
			if parent != Path(repo) and parent.is_relative_to(Path(repo))
		):
			raise RuntimeError(f"unsafe symlink path: {p}")
		if p in m["added"] and full.exists():
			raise RuntimeError(f"added path already exists: {p}")
	for p in m["added"] + m["modified"]:
		_blob(repo, target, p)
	for p in m["deleted"]:
		_blob(repo, base, p)
	try:
		for p in m["added"] + m["modified"]:
			_write_blob(repo, target, p)
			git(repo, "add", "--", p)
		for p in m["deleted"]:
			full = Path(repo, p)
			if full.exists():
				full.unlink()
			git(repo, "rm", "--cached", "--ignore-unmatch", "--", p)
	except BaseException:
		# Restore the index/worktree using the base tree, without touching protected paths.
		for p in paths:
			if p in m["added"]:
				full = Path(repo, p)
				if full.exists():
					full.unlink()
			elif p in m["modified"] or p in m["deleted"]:
				_write_blob(repo, base, p)
			git(repo, "reset", "HEAD", "--", p, check=False)
		raise


def verify_overlay(repo: str, base: str, target: str, manifest_path: str) -> dict:
	m = read_manifest_file(manifest_path)
	validate_manifest(m, base, target)
	if git(repo, "rev-parse", "HEAD").stdout.strip() != base:
		raise RuntimeError("HEAD is not base")
	_verify_protected(repo, m)
	status = git(repo, "diff", "--cached", "--name-status", "-z").stdout
	parts = status.split("\0")
	staged = set()
	i = 0
	while i < len(parts) - 1:
		if not parts[i]:
			i += 1
			continue
		code = parts[i]
		i += 1
		if i >= len(parts) - 1:
			raise RuntimeError("malformed staged status")
		staged.add(parts[i])
		i += 1
	paths = _manifest_paths(m)
	if staged != paths:
		raise RuntimeError("index paths do not exactly match manifest")
	for p in paths:
		_, data, mode = _blob(repo, target, p) if p not in m["deleted"] else _blob(repo, base, p)
		full = Path(repo, p)
		if p in m["deleted"]:
			if full.exists():
				raise RuntimeError(f"deleted path exists: {p}")
			continue
		if not full.is_file() or full.read_bytes() != data or stat.S_IMODE(full.stat().st_mode) != stat.S_IMODE(mode):
			raise RuntimeError(f"worktree mismatch: {p}")
		idx = git(repo, "ls-files", "-s", "--", p).stdout.split()
		if not idx or int(idx[0], 8) != mode:
			raise RuntimeError(f"index mode mismatch: {p}")
		index_oid = idx[1]
		target_oid = git(repo, "rev-parse", f"{target}:{p}").stdout.strip()
		if index_oid != target_oid:
			raise RuntimeError(f"index blob mismatch: {p}")
	with open(manifest_path, "rb") as f:
		digest = hashlib.sha256(f.read()).hexdigest()
	return {
		"valid": True,
		"base_sha": base,
		"target_sha": target,
		"manifest_hash": digest,
		"path_count": len(paths),
	}


def rollback_overlay(repo: str, base: str, target: str, manifest_path: str) -> None:
	m = read_manifest_file(manifest_path)
	validate_manifest(m, base, target)
	if git(repo, "rev-parse", "HEAD").stdout.strip() != base:
		raise RuntimeError("HEAD is not base")
	paths = _manifest_paths(m)
	_assert_no_conflicts(repo, paths, allow_staged=True)
	_verify_protected(repo, m)
	# Check symlinks and parent containment before rollback writes
	for p in paths:
		full = Path(repo, p)
		if full.is_symlink() or any(
			parent.is_symlink()
			for parent in full.parents
			if parent != Path(repo) and parent.is_relative_to(Path(repo))
		):
			raise RuntimeError(f"unsafe symlink path: {p}")
		_assert_safe_path(repo, p)
	for p in m["modified"] + m["deleted"]:
		_blob(repo, base, p)
	for p in m["modified"]:
		_write_blob(repo, base, p)
		git(repo, "reset", "HEAD", "--", p)
	for p in m["added"]:
		full = Path(repo, p)
		if full.exists():
			full.unlink()
		git(repo, "reset", "HEAD", "--", p)
	for p in m["deleted"]:
		_write_blob(repo, base, p)
		git(repo, "reset", "HEAD", "--", p)


def finalize_overlay(repo: str, base: str, target: str, manifest_path: str) -> None:
	m = read_manifest_file(manifest_path)
	validate_manifest(m, base, target)
	if git(repo, "rev-parse", "HEAD").stdout.strip() != base:
		raise RuntimeError("HEAD is not base")
	git(repo, "merge-base", "--is-ancestor", base, target)
	# A tracked bundle change cannot be represented by this overlay workflow.
	bundle_diff = git(repo, "diff", "--name-only", base, target, "--", PROTECTED_BUNDLE).stdout.strip()
	if bundle_diff:
		raise RuntimeError("target changes protected bundle; finalize rejected before ref movement")
	verify_overlay(repo, base, target, manifest_path)
	# Snapshot ref and index state before movement; reset is performed only after all checks.
	old_head = git(repo, "rev-parse", "HEAD").stdout.strip()
	git(repo, "reset", "--soft", target)
	try:
		if git(repo, "diff", "--cached", "--name-only", "-z").stdout.strip():
			raise RuntimeError("candidate remains staged")
		_verify_protected(repo, m)
	except BaseException:
		git(repo, "reset", "--soft", old_head, check=False)
		raise


def main():
	p = argparse.ArgumentParser()
	s = p.add_subparsers(dest="command", required=True)
	for name in ("manifest", "apply", "verify", "rollback", "finalize"):
		q = s.add_parser(name)
		q.add_argument("--base", required=True)
		q.add_argument("--target", required=True)
		q.add_argument("--manifest", required=(name != "manifest"))
		q.add_argument("--repo", default=".")
	a = p.parse_args()
	if a.command == "manifest":
		print(json.dumps(generate_manifest(a.repo, a.base, a.target), indent=2, sort_keys=True))
	else:
		fn = {
			"apply": apply_overlay,
			"verify": verify_overlay,
			"rollback": rollback_overlay,
			"finalize": finalize_overlay,
		}[a.command]
		out = fn(a.repo, a.base, a.target, a.manifest)
		if out is not None:
			print(json.dumps(out, indent=2, sort_keys=True))


if __name__ == "__main__":
	main()
