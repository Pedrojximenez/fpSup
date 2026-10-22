#!/usr/bin/env python3
"""Build an immutable evidence ledger entry to the ROADMAP section 13 schema.

Why a generator and not a hand-written JSON: the three live records from
2026-09-21 each spell their own field names, one of them overstated what was
measured, and none of them binds the result to the source that produced it. An
entry that cannot be traced to a probe binary and a worktree state is a number,
not evidence.

Two rules from the roadmap are enforced here rather than remembered:

- Historical evidence is never rewritten. A correction is recorded as its own
  field naming the original claim, so the original stays visible.
- Every `established` item has to say what level it holds at, and every entry
  carries an `explicitly_not_established` list. An entry with an empty one is
  refused: something is always unproven, and not saying so is how "passed"
  drifts into meaning more than it did.

Offline: reads files and git, writes one JSON. No camera, no network.
"""
import argparse
import datetime
import hashlib
import json
import pathlib
import subprocess

SCHEMA_VERSION = 1
REQUIRED = ("kind", "operator_scope", "camera", "source", "explicitly_established",
            "explicitly_not_established")
LEVELS = {"L", "H", "C", "I", "P"}


class LedgerError(RuntimeError):
    pass


def git(root: pathlib.Path, *args):
    try:
        done = subprocess.run(["git", "-C", str(root), *args],
                              capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return done.stdout.strip() if done.returncode == 0 else None


def source_state(root: pathlib.Path, paths):
    """Commit, dirtiness and a hash per source file.

    A commit alone is not enough: this tree is usually dirty, and a dirty tree
    means the commit does not describe what ran. The per-file hash is what
    actually ties a number to the bytes that produced it.
    """
    commit = git(root, "rev-parse", "HEAD")
    status = git(root, "status", "--porcelain")
    files = {}
    for entry in paths:
        path = pathlib.Path(entry)
        if not path.is_absolute():
            path = root / path
        if not path.is_file():
            raise LedgerError(f"source path does not exist: {entry}")
        files[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return {"commit": commit, "worktree_dirty": bool(status) if status is not None else None,
            "git_available": commit is not None, "files": files}


def check_claims(established, not_established):
    if not isinstance(established, list) or not isinstance(not_established, list):
        raise LedgerError("established/not_established must be lists")
    if not not_established:
        raise LedgerError(
            "explicitly_not_established is empty; every result has a boundary "
            "and an entry that names none is the failure mode this exists to stop")
    for item in established:
        if not isinstance(item, dict) or "level" not in item or "claim" not in item:
            raise LedgerError("each established item needs {level, claim}")
        if item["level"] not in LEVELS:
            raise LedgerError(f"unknown evidence level {item['level']!r}; use {sorted(LEVELS)}")


def build(spec: dict, root: pathlib.Path) -> dict:
    missing = [key for key in REQUIRED if key not in spec]
    if missing:
        raise LedgerError(f"missing required fields: {', '.join(missing)}")
    check_claims(spec["explicitly_established"], spec["explicitly_not_established"])
    entry = {
        "schema_version": SCHEMA_VERSION,
        "kind": spec["kind"],
        "date": spec.get("date") or datetime.date.today().isoformat(),
        "operator_scope": spec["operator_scope"],
        "camera": spec["camera"],
        "source": source_state(root, spec["source"]),
    }
    for optional in ("probe", "hook", "lease", "profile", "scene", "frames",
                     "timing", "per_frame", "integrity", "corrections", "notes"):
        if optional in spec:
            entry[optional] = spec[optional]
    entry["explicitly_established"] = spec["explicitly_established"]
    entry["explicitly_not_established"] = spec["explicitly_not_established"]
    return entry


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("spec", type=pathlib.Path, help="JSON describing the entry")
    parser.add_argument("--root", type=pathlib.Path,
                        default=pathlib.Path(__file__).resolve().parents[3])
    parser.add_argument("--out", type=pathlib.Path)
    args = parser.parse_args()
    spec = json.loads(args.spec.read_text())
    entry = build(spec, args.root.resolve())
    text = json.dumps(entry, indent=2, ensure_ascii=False) + "\n"
    if args.out:
        if args.out.exists():
            raise SystemExit(f"refusing to overwrite {args.out}: evidence is immutable")
        args.out.write_text(text)
        print(f"wrote {args.out}")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
