#!/usr/bin/env python3
"""Build a self-contained FPShell release directory and archive."""

import hashlib
import pathlib
import shutil
import tarfile


ROOT = pathlib.Path(__file__).resolve().parent
VERSION = (ROOT / "VERSION").read_text(encoding="ascii").strip()
NAME = f"FPShell-{VERSION}-macOS-arm64"
RELEASE_ROOT = ROOT / "release"
PACKAGE = RELEASE_ROOT / NAME


def copy(source: pathlib.Path, relative: str, executable: bool = False) -> pathlib.Path:
    destination = PACKAGE / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    if executable:
        destination.chmod(0o755)
    return destination


def main() -> int:
    if PACKAGE.exists():
        shutil.rmtree(PACKAGE)
    PACKAGE.mkdir(parents=True)
    files = [
        copy(ROOT / "fpshelld", "bin/fpshelld", True),
        copy(ROOT / "fpshell", "bin/fpshell", True),
        copy(ROOT / "fpshellctl", "bin/fpshellctl", True),
        copy(ROOT / "dist" / "AutoRun.txt", "camera/AutoRun.txt"),
        copy(ROOT / "README.md", "README.md"),
        copy(ROOT / "PROTOCOL.md", "PROTOCOL.md"),
        copy(ROOT / "CAMERA_LOOP_DESIGN.md", "CAMERA_LOOP_DESIGN.md"),
        copy(pathlib.Path("/Users/dido/Documents/Codex/2026-08-16/4/libusb-1.0.dylib"),
             "lib/libusb-1.0.dylib", True),
    ]
    manifest_lines = []
    for path in sorted(files):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        manifest_lines.append(f"{digest}  {path.relative_to(PACKAGE)}\n")
    (PACKAGE / "MANIFEST.sha256").write_text("".join(manifest_lines), encoding="ascii")

    archive = RELEASE_ROOT / f"{NAME}.tar.gz"
    with tarfile.open(archive, "w:gz") as bundle:
        bundle.add(PACKAGE, arcname=NAME)
    print(PACKAGE)
    print(archive)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
