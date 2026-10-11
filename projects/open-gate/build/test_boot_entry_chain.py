#!/usr/bin/env python3
"""Offline build regression for OpenGate entry forwarding; never opens a camera.

Builds into --out (a fresh temporary directory by default).  Catalogue tests
call refs() with explicit artifact fixtures, never its website-writing main().
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SHELL = ROOT / "fpSup/fp_usb_shell"
GYRO = ROOT / "fpSup/gyro"
sys.path[:0] = [str(SHELL), str(GYRO)]
from armasm import assemble, symbols
from build_base_card import launch
from og3k_plan import RESTORE_CODE


def read_card(directory):
    payload = next(directory / name for name in ("fpSup.BIN", "VSHL.BIN")
                   if (directory / name).is_file())
    blob = payload.read_bytes()
    magic, count, entry, body_bytes = struct.unpack_from("<4sIII", blob)
    assert magic == b"VBIN"
    offset = 16 + count * 8
    records = []
    for index in range(count):
        address, length = struct.unpack_from("<II", blob, 16 + index * 8)
        data = blob[offset:offset + length]
        assert len(data) == length
        records.append((address, offset, data))
        offset += length + (-length % 4)
    assert offset == 16 + count * 8 + body_bytes
    return blob, entry, records


class EntryCheck:
    def __init__(self):
        self.worker = assemble(SHELL / "camera/worker.S")
        self.spawn = symbols(SHELL / "camera/worker.S")["spawn"]
        self.gyro = launch("gcsv")[0]
        self.trampoline = assemble(SHELL / "asm/entries.S")
        self.table_offset = symbols(SHELL / "asm/entries.S")["table"]

    def check(self, directory, *, debug, combined, restore, boot_bins=()):
        """boot_bins: further run-in-place payloads (--boot-bin, entry offset 0)
        the card must carry once each; their entries follow gyro's."""
        blob, entry, records = read_card(directory)
        expected = []
        for payload, delta, present in ((self.worker, self.spawn, debug),
                                        (self.gyro, 0, combined),
                                        *((b, 0, True) for b in boot_bins)):
            matches = [offset for address, offset, data in records
                       if address == 0 and data == payload]
            assert len(matches) == int(present), (directory, "payload count", matches)
            if present:
                expected.append(matches[0] + delta)
        if restore:
            assert any(address <= RESTORE_CODE < address + len(data)
                       for address, _, data in records if address >= 0x40000000)
            expected.append(RESTORE_CODE)
        if len(expected) <= 1:
            actual = [entry] if entry else []
        else:
            tramp = [data for address, offset, data in records
                     if address == 0 and offset == entry]
            assert len(tramp) == 1, (directory, "entry must name trampoline")
            data = tramp[0]
            assert data[:self.table_offset] == self.trampoline[:self.table_offset]
            table = struct.unpack_from(f"<{len(expected) + 2}I", data, self.table_offset)
            assert table[0] == entry + self.table_offset and table[-1] == 0
            actual = list(table[1:-1])
        assert actual == expected, (directory, actual, expected)
        ar = (directory / "AutoRun.txt").read_bytes()
        assert f"mem set 0xC0BAC2F8 0x{RESTORE_CODE:08X}".encode() not in ar
        return {"directory": str(directory), "entries": [f"0x{x:08X}" for x in actual],
                "sections": len(records), "bin_sha256": hashlib.sha256(blob).hexdigest(),
                "autorun_sha256": hashlib.sha256(ar).hexdigest()}


def run(command, directory, env=None):
    directory.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=180)
    (directory / "build.log").write_text(result.stdout + result.stderr)
    assert result.returncode == 0, f"build failed: {directory / 'build.log'}"


_UI_SECTIONS = {}


def expected_ui_section(target):
    """The UI section an OG_UISHARE card must carry: build_og3k_gyro.ui_block
    over the native UI's own manifest (built once per target)."""
    if target not in _UI_SECTIONS:
        sys.path.insert(0, str(ROOT / "fpSup" / "uishare"))
        import build_section
        import build_og3k_gyro
        saved = os.environ.get("OG_TARGET")
        os.environ["OG_TARGET"] = target
        try:
            with tempfile.TemporaryDirectory(prefix="og-ui-manifest-") as tmp:
                _, manifest, _ = build_og3k_gyro.canonical_ui_sections(Path(tmp))
        finally:
            if saved is None:
                os.environ.pop("OG_TARGET")
            else:
                os.environ["OG_TARGET"] = saved
        block = build_og3k_gyro.ui_block(target.upper(), manifest)
        _UI_SECTIONS[target] = build_section.section(block.encode())[0]
    return _UI_SECTIONS[target]


def build_case(case, output, checker):
    target, name, combined, debug, fast, guard = case
    directory = output / f"{target}-{name}"
    command = [sys.executable, str(HERE / "build_og3k_gyro.py"), "--out", str(directory)]
    command += ["--dev-card"] if fast else (["--reference"] if combined else ["--no-gyro"])
    if combined:
        # refs() uses the current four-box packaging. Comparing its BIN with
        # the legacy text-splash configuration changes stage2 and offsets.
        command.append("--four-box-bar")
    if not debug:
        command.append("--release")
    if fast:
        command.append("--fast")
    env = dict(os.environ, OG_TARGET=target, OG_FMT_GUARD=str(int(guard)))
    run(command, directory, env)
    boot_bins = ()
    if os.environ.get("OG_UISHARE") == "1":
        # the resolution row by addition: its UI section is one more payload,
        # called after gyro's and before the restore
        boot_bins = (expected_ui_section(target),)
    result = checker.check(directory, debug=debug, combined=combined, restore=guard,
                           boot_bins=boot_bins)
    result.update(name=directory.name, command=command, target=target, fmt_guard=guard)
    print(f"PASS {directory.name}: {' -> '.join(result['entries']) or 'entry 0'}", flush=True)
    return result


def autorun_independence(output):
    results = []
    stub = output / "entry-bx-lr.bin"
    stub.write_bytes(struct.pack("<I", 0xE12FFF1E))
    for name, flags in (("plain", ["--no-shell"]), ("debug", []),
                        ("fast-debug", ["--store-boot"])):
        paths = []
        for enabled in (False, True):
            directory = output / f"autorun-{name}-entry{int(enabled)}"
            command = [sys.executable, str(SHELL / "build_autorun.py"), "--loader",
                       *flags, "--banner", "Entry-Contract!", "--also-bin",
                       f"0x{RESTORE_CODE:08X}:{stub}", "--out", str(directory / "AutoRun.txt")]
            if enabled:
                command += ["--vshl-entry", f"0x{RESTORE_CODE:08X}"]
            run(command, directory)
            paths.append(directory)
        assert (paths[0] / "AutoRun.txt").read_bytes() == (paths[1] / "AutoRun.txt").read_bytes()
        assert (paths[0] / "fpSup.BIN").read_bytes() != (paths[1] / "fpSup.BIN").read_bytes()
        results.append({"name": name, "directories": list(map(str, paths))})
        print(f"PASS same AutoRun, different BIN entry: {name}", flush=True)
    return results


def catalogue_references(output, checker, frozen):
    spec = importlib.util.spec_from_file_location(
        "catalogue_entry_regression", ROOT / "fpSup/tools/card-composer/build_catalogue.py")
    catalogue = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(catalogue)
    catalogue.GYRO = GYRO
    results = []
    for target in ("og3k", "og2k"):
        for label, source in (("frozen", frozen[target]),
                              ("source", output / f"{target}-standalone-release")):
            _, entry, _ = read_card(source)
            uishare = label == "source" and os.environ.get("OG_UISHARE") == "1"
            # with the UI section the source card's entry is its trampoline
            assert entry == (0 if label == "frozen" else RESTORE_CODE) or (uishare and entry < 0x40000000)
            # OG2K's wrapper deliberately emits no MANIFEST.txt; refs() needs
            # its UI-record attestation.  Derive that fixture from the actual
            # built MANIFEST.json rather than changing release artifacts.
            fixture = output / f"catalogue-input-{target}-{label}"
            fixture.mkdir()
            shutil.copy2(catalogue.payload(source), fixture / "fpSup.BIN")
            manifest = json.loads((source / "MANIFEST.json").read_text())
            count = manifest["ui"]["records"]["records"]
            assert count == catalogue.NATIVE_UI_RECORDS
            (fixture / "MANIFEST.txt").write_text(f"Offline test fixture: {count} selected NBU records\n")
            catalogue.latest = lambda product, fixture=fixture: fixture
            catalogue.REFS.clear()
            references = catalogue.refs(target)
            try:
                for flavor, debug in (("plain", False), ("shell", True)):
                    destination = output / f"catalogue-{target}-{label}-{flavor}"
                    shutil.copytree(references[flavor], destination)
                    boot_bins = ()
                    if uishare:
                        boot_bins = (expected_ui_section(target),)
                    result = checker.check(destination, debug=debug, combined=True,
                                           restore=bool(entry), boot_bins=boot_bins)
                    if label == "source":
                        direct = output / f"{target}-combined-{'debug' if debug else 'release'}"
                        assert catalogue.payload(destination).read_bytes() == catalogue.payload(direct).read_bytes()
                    result.update(name=destination.name, input=str(source))
                    results.append(result)
                    print(f"PASS {destination.name}", flush=True)
            finally:
                shutil.rmtree(references["_tmp"])
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--jobs", type=int, default=3)
    parser.add_argument("--frozen-og3k", type=Path, default=HERE / "fpsup-og3k-v0.2.4a")
    parser.add_argument("--frozen-og2k", type=Path, default=HERE / "fpsup-og2k-v0.1.1a")
    args = parser.parse_args()
    output = args.out or Path(tempfile.mkdtemp(prefix="boot-entry-chain-"))
    output.mkdir(parents=True, exist_ok=True)
    checker = EntryCheck()
    cases = [(target, *case) for target in ("og3k", "og2k") for case in (
        ("standalone-release", False, False, False, True),
        ("standalone-debug", False, True, False, True),
        ("combined-release", True, False, False, True),
        ("combined-debug", True, True, False, True),
        ("combined-fast-debug", True, True, True, True),
        ("guard-off-standalone", False, False, False, False),
        ("guard-off-combined", True, True, False, False),
    )]
    report = {"output": str(output), "build_matrix": [], "failures": []}
    if os.environ.get("OG_UISHARE") == "1":
        for target in ("og3k", "og2k"):     # before the threads: it sets OG_TARGET
            expected_ui_section(target)
    with ThreadPoolExecutor(max_workers=max(1, min(args.jobs, 3))) as executor:
        futures = {executor.submit(build_case, case, output, checker): case for case in cases}
        for future in as_completed(futures):
            try:
                report["build_matrix"].append(future.result())
            except Exception as error:
                report["failures"].append({"case": futures[future], "error": str(error)})
                print(f"FAIL {futures[future]}: {error}", flush=True)
    if not report["failures"]:
        report["autorun_independence"] = autorun_independence(output)
        report["catalogue_references"] = catalogue_references(
            output, checker, {"og3k": args.frozen_og3k, "og2k": args.frozen_og2k})
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    assert not report["failures"], f"See {output / 'report.json'}"
    print(f"PASS 14 build cases, 3 AutoRun comparisons, 8 catalogue references: {output}")


if __name__ == "__main__":
    main()
