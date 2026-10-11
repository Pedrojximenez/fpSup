#!/usr/bin/env python3
"""Install the pinned r86 debug test card on the already mounted fpSup2.

Back up only the boot assets.  CINEMA/DCIM media is never opened for writing.
Every replacement is staged on the card, checked, then renamed in place.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil


ROOT = Path(__file__).resolve().parents[4]
SOURCE = Path(__file__).resolve().parent / "debug"
CARD = Path("/Volumes/fpSup2")
BACKUP = ROOT / "archive/fpSup2-20261004-pre-r86"
OLD = {
    "AutoRun.txt": "5dc89b8506e8ce408276a9eab61fbb9fda94d4a194b65f2fd17c9e410b8fe642",
    "fpSup.BIN": "37bcf712af5d152f12561f42d4e617c2e0b5c9a4b9fdde4eab9434c7ea95a73f",
    "MANIFEST.json": "227ea118a897363a74a6d35fd94013b89605900dfc3871ae5bf17d8b8756d4b9",
}
NEW = {
    "AutoRun.txt": OLD["AutoRun.txt"],
    "fpSup.BIN": "28ac9adb81a0070b979066a43aa81d7d8f5b71f240c2ea092b181ffc19db81ce",
    "MANIFEST.json": "ca82441fe8314c939d210462baddfe91aad8b44e2d6fd1403a7c52bb9548b45b",
}
FILES = tuple(f"FPSUPUI/{i}.BIN" for i in range(5)) + (
    "fpSup.BIN", "MANIFEST.json", "AutoRun.txt"
)


def digest(path: Path) -> str:
    state = hashlib.sha256()
    with path.open("rb") as stream:
        while True:
            chunk = stream.read(1024 * 1024)
            if not chunk:
                break
            state.update(chunk)
    return state.hexdigest()


def checked_copy(source: Path, destination: Path, expected: str) -> None:
    temporary = destination.with_name(destination.name + ".r86-staging")
    if temporary.exists():
        raise RuntimeError(f"unexpected staging file: {temporary}")
    try:
        with source.open("rb") as inp, temporary.open("xb") as out:
            shutil.copyfileobj(inp, out, 1024 * 1024)
            out.flush()
            os.fsync(out.fileno())
        if digest(temporary) != expected:
            raise RuntimeError(f"staged checksum mismatch: {destination}")
        temporary.replace(destination)
        if digest(destination) != expected:
            raise RuntimeError(f"read-back checksum mismatch: {destination}")
    finally:
        if temporary.exists():
            temporary.unlink()


def main() -> None:
    if not CARD.is_mount():
        raise RuntimeError("fpSup2 is not mounted at the expected path")
    if BACKUP.exists():
        raise RuntimeError(f"backup already exists: {BACKUP}")
    if not (CARD / "FPSUPUI").is_dir():
        raise RuntimeError("fpSup2 has no FPSUPUI directory")
    for name, expected in OLD.items():
        if digest(CARD / name) != expected:
            raise RuntimeError(f"fpSup2 is not the pinned r83 card: {name}")
    for name, expected in NEW.items():
        if digest(SOURCE / name) != expected:
            raise RuntimeError(f"source r86 checksum mismatch: {name}")
    source_hashes = {name: digest(SOURCE / name) for name in FILES}
    original_hashes = {name: digest(CARD / name) for name in FILES}

    # A completed local snapshot exists before the first removable-card write.
    BACKUP.mkdir(parents=True)
    for name in FILES:
        target = BACKUP / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(CARD / name, target)
        if digest(target) != original_hashes[name]:
            raise RuntimeError(f"backup checksum mismatch: {name}")

    changed = []
    try:
        for name in FILES:
            if source_hashes[name] == original_hashes[name]:
                continue
            changed.append(name)
            checked_copy(SOURCE / name, CARD / name, source_hashes[name])
        os.sync()
        after = {name: digest(CARD / name) for name in FILES}
        if after != source_hashes:
            raise RuntimeError("final card read-back differs from r86")
    except Exception:
        for name in reversed(changed):
            checked_copy(BACKUP / name, CARD / name, original_hashes[name])
        os.sync()
        raise

    report = {
        "card": str(CARD), "source": str(SOURCE), "backup": str(BACKUP),
        "before_sha256": original_hashes, "after_sha256": after,
        "changed": changed,
        "media_directories_untouched": ["CINEMA", "DCIM"],
    }
    (BACKUP / "write_report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
