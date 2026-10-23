#!/usr/bin/env python3
"""Offline checks only. Does not import camera clients or write a card."""
import json
import subprocess
import tempfile
import sys
from pathlib import Path
from html.parser import HTMLParser

ROOT = Path(__file__).resolve().parent


class Scripts(HTMLParser):
    def __init__(self):
        super().__init__()
        self.inside = False
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag == "script":
            self.inside = True

    def handle_endtag(self, tag):
        if tag == "script":
            self.inside = False

    def handle_data(self, data):
        if self.inside:
            self.parts.append(data)


def main():
    results = []
    subprocess.run([sys.executable, str(ROOT / "build_preview.py")], check=True)
    with tempfile.TemporaryDirectory(prefix="fp-qs-touch-") as directory:
        work = Path(directory)

        def run(name, args):
            result = subprocess.run(args, cwd=ROOT, text=True, capture_output=True, check=True)
            results.append({"name": name, "passed": True, "output": result.stdout.strip()})

        run("host_compile_sanitizers", ["clang", "-std=c11", "-Wall", "-Wextra", "-Werror",
            "-fsanitize=address,undefined", "-g", "core/qs_touch.c", "tests/test_qs_touch.c",
            "-o", str(work / "test")])
        run("interaction_invariants", [str(work / "test")])
        run("appearance_compile_sanitizers", ["clang", "-std=c11", "-Wall", "-Wextra", "-Werror",
            "-fsanitize=address,undefined", "-g", "core/qs_appearance.c", "tests/test_qs_appearance.c",
            "-o", str(work / "appearance")])
        run("appearance_invariants", [str(work / "appearance")])
        run("arm_compile_only", ["clang", "-target", "arm-none-eabi", "-mcpu=cortex-a7",
            "-mthumb", "-std=c11", "-Os", "-ffreestanding", "-fno-builtin", "-Wall",
            "-Wextra", "-Werror", "-c", "core/qs_touch.c", "-o", str(work / "qs.o")])
        run("appearance_arm_compile_only", ["clang", "-target", "arm-none-eabi", "-mcpu=cortex-a7",
            "-mthumb", "-std=c11", "-Os", "-ffreestanding", "-fno-builtin", "-Wall",
            "-Wextra", "-Werror", "-c", "core/qs_appearance.c", "-o", str(work / "appearance.o")])
        fragment = (ROOT / "preview/fp-touch-qs.html").read_text()
        parser = Scripts()
        parser.feed(fragment)
        (work / "preview.js").write_text("\n".join(parser.parts))
        run("preview_javascript_syntax", ["node", "--check", str(work / "preview.js")])
        run("page_motion_invariants", ["node", "tests/test_qs_motion.js"])
        run("recording_model_invariants", ["node", "tests/test_qs_recording.js"])
    report = {"scope": "offline only; no ARM execution, camera I/O or deployment", "checks": results}
    destination = ROOT / "validation/offline.json"
    destination.parent.mkdir(exist_ok=True)
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    for item in results:
        print("PASS", item["name"], item["output"])


if __name__ == "__main__":
    main()
