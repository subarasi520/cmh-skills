#!/usr/bin/env python3
"""Freeze and verify a study protocol.

冻结与核对研究协议：把协议文件（定义、提示词、分流规则、评估方案……）的哈希写进锁文件，
之后任何改动都能被查出来。

  freeze  write a lock file with the SHA-256 of each protocol file
  verify  recompute the hashes and report any change (exit 1 on mismatch)

A lock only proves that files have not changed since it was written. To show
*when* it was written, commit the lock to version control before the first
evaluation run; the commit time is the evidence, not the timestamp inside.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cmh_common import CMHError, __version__, run_cli, sha256_file, utc_now, write_json  # noqa: E402

LOCK_VERSION = 1


def _git(args: list[str], cwd: Path) -> str | None:
    try:
        result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=20, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def git_state(directory: Path) -> dict | None:
    commit = _git(["rev-parse", "HEAD"], directory)
    if commit is None:
        return None
    status = _git(["status", "--porcelain"], directory)
    return {"commit": commit, "dirty": bool(status)}


def freeze(files: list[str], out: Path, note: str, force: bool, reason: str, base_dir: str | None = None) -> dict:
    out = out.resolve()
    base = Path(base_dir).resolve() if base_dir else out.parent
    entries: dict[str, str] = {}
    for name in files:
        path = Path(name).resolve()
        if not path.is_file():
            raise CMHError(f"{name}: not a file")
        try:
            rel = path.relative_to(base).as_posix()
        except ValueError as exc:
            raise CMHError(f"{name}: protocol files must sit inside the base folder ({base})") from exc
        entries[rel] = sha256_file(path)
    supersedes = None
    if out.exists():
        if not force:
            raise CMHError(f"{out} exists. A frozen protocol should not be rewritten; "
                           "use --force with --reason to record a deliberate amendment")
        if not reason:
            raise CMHError("--force needs --reason (the amendment is recorded in the new lock)")
        supersedes = {"sha256": sha256_file(out), "reason": reason}
    lock = {
        "cmh_lock_version": LOCK_VERSION,
        "tool_version": __version__,
        "frozen_utc": utc_now(),
        "note": note,
        "base_dir": Path(os.path.relpath(base, out.parent)).as_posix(),
        "files": dict(sorted(entries.items())),
        "git": git_state(base),
        "supersedes": supersedes,
    }
    write_json(out, lock)
    return lock


def verify_lock(lock_path: str | Path) -> list[str]:
    """Return a list of problems; an empty list means every file matches."""
    lock_path = Path(lock_path).resolve()
    if not lock_path.is_file():
        return [f"{lock_path}: lock file not found"]
    try:
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"{lock_path}: not valid JSON ({exc})"]
    if lock.get("cmh_lock_version") != LOCK_VERSION or not isinstance(lock.get("files"), dict):
        return [f"{lock_path}: not a CMH protocol lock"]
    problems = []
    base = (lock_path.parent / lock.get("base_dir", ".")).resolve()
    for rel, expected in lock["files"].items():
        path = (base / rel).resolve()
        if not path.is_file():
            problems.append(f"missing: {rel}")
        elif sha256_file(path) != expected:
            problems.append(f"changed since freeze: {rel}")
    return problems


def locked_files(lock_path: str | Path) -> set[Path]:
    lock_path = Path(lock_path).resolve()
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    base = (lock_path.parent / lock.get("base_dir", ".")).resolve()
    return {(base / rel).resolve() for rel in lock.get("files", {})}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p_freeze = sub.add_parser("freeze", help="write a lock file for the protocol files")
    p_freeze.add_argument("--files", nargs="+", required=True, help="protocol files to lock")
    p_freeze.add_argument("--out", required=True, help="lock file to write, e.g. protocol.lock.json")
    p_freeze.add_argument("--note", default="", help="free text stored in the lock")
    p_freeze.add_argument("--force", action="store_true", help="replace an existing lock (records an amendment)")
    p_freeze.add_argument("--reason", default="", help="why the protocol is amended (required with --force)")
    p_freeze.add_argument("--base-dir", help="folder the file paths are stored relative to (default: the lock's folder); "
                                             "every protocol file must be inside it")

    p_verify = sub.add_parser("verify", help="check that the protocol files still match the lock")
    p_verify.add_argument("--lock", required=True)

    args = parser.parse_args()
    if args.command == "freeze":
        lock = freeze(args.files, Path(args.out), args.note, args.force, args.reason, args.base_dir)
        print(f"froze {len(lock['files'])} file(s) into {args.out}")
        if lock["git"] is None:
            print("note: not inside a git repository; commit the lock somewhere with a verifiable time", file=sys.stderr)
        elif lock["git"]["dirty"]:
            print("warning: the working tree has uncommitted changes; commit the protocol files and this lock now",
                  file=sys.stderr)
        return 0
    problems = verify_lock(args.lock)
    for problem in problems:
        print(problem)
    if problems:
        return 1
    print("protocol matches the lock")
    return 0


if __name__ == "__main__":
    run_cli(main)
