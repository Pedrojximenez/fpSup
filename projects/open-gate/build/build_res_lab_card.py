#!/usr/bin/env python3
"""Offline Sensor Lab test card, using the maintained shared loader.

No camera transport, card deployment or merge support is implied.
Run with --out NEW_DIRECTORY [--debug] [--fast] [--axis-preset A].

--fast builds a Fast Start 3 dev card (skill `fp-merged-card`): the shared
builder's `--store-boot --loader-hook --four-box-bar`, all from this one run --
bootstrap, stage2, abort, magic and hook entry must never be mixed across builds.
It WRITES THE SETTINGS BLOCK, which survives a battery pull and outlives
deleting AutoRun.txt, so it is a dev card only, never a release. The card also
needs the generated FPSUPUI/ folder beside the two files. With --debug it adds
`--loader-hook-mark` so `loader_hook_check.py` can read which boot path ran.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SHELL = ROOT / "fpSup/fp_usb_shell"
sys.path.insert(0, str(HERE))
import imx410_plan as PL
import res_lab_cave_audit as CAVE_AUDIT
from res_lab_user_pack import CORE_MAGIC, res_lab_pack
from res_lab_user_launch import build_blob as build_core_launcher
from imx410_full import TIMING
from imx410_block import _PROFILE_JSON
sys.path.insert(0, str(SHELL))
from patches import IFACE, PUSH

# The mark other Fast cards use (skill `fp-merged-card`); outside our cave.
LOADER_HOOK_MARK = 0xC072E040
FAST_FLAGS = ("--store-boot", "--loader-hook", "--four-box-bar")


AUTORUN_EXTRA = []      # --autorun-flag, passed through to build_autorun.py


@contextmanager
def source_directory():
    before = Path.cwd()
    os.chdir(HERE)
    try:
        yield
    finally:
        os.chdir(before)


def runtime_restore_words(image):
    """Register all native words that the resident hooks may change later.

    The picker/recipe restores the previous donor on a mode change, but the
    last donor and preview heights still need the shared power-off journal.
    Mode-table relocation by another product is outside this standalone card.
    """
    addresses = set(PL.PREV_PROFILES)
    for index in range(70):
        addresses.update((TIMING + index * 0x20 + 4, TIMING + index * 0x20 + 8))
    return [(a, struct.unpack_from("<I", image, a - PL.B)[0], "runtime restore")
            for a in sorted(addresses)]


def card_items(axis=None):
    with source_directory():
        items = PL.plan(recipe_axis=axis)
        bad = PL.layout_errors() + PL.hook_errors() + PL.order_errors(items)
    if bad:
        raise ValueError("; ".join(bad))
    image = PL.FIRMWARE.read_bytes()
    restore = runtime_restore_words(image)
    if len({a for a, _, _ in items + restore}) != len(items) + len(restore):
        raise ValueError("duplicate destination in plan or runtime journal declarations")
    # Code/state first, original-value journal declarations next, data next,
    # hooks last in the plan's dependency order. Never sort hooks by address.
    hooks = [x for x in items if "hook" in x[2]]
    body = [x for x in items if "hook" not in x[2]]
    private = [x for x in body if PL.CAVE_LO <= x[0] < PL.CAVE_HI]
    external = [x for x in body if not PL.CAVE_LO <= x[0] < PL.CAVE_HI]
    return private + restore + external + hooks


def sections(items):
    """Coalesce adjacent words without changing publication order."""
    result = []
    for address, value, _ in items:
        if result and address == result[-1][0] + len(result[-1][1]):
            result[-1][1].extend(struct.pack("<I", value))
        else:
            result.append((address, bytearray(struct.pack("<I", value))))
    return [(a, bytes(b)) for a, b in result]


def decode(blob):
    magic, count, entry, length = struct.unpack_from("<4sIII", blob)
    if magic != b"VBIN" or count > (len(blob) - 16) // 8:
        raise ValueError("invalid VBIN header")
    cursor = 16 + count * 8
    end = cursor + length
    if end > len(blob):
        raise ValueError("truncated VBIN body")
    records = []
    for i in range(count):
        address, size = struct.unpack_from("<II", blob, 16 + i * 8)
        if size % 4 or cursor + size > end:
            raise ValueError("invalid section length")
        records.append((address, cursor, blob[cursor:cursor + size]))
        cursor += size
    if cursor != end or any(blob[end:]):
        raise ValueError("body length or padding mismatch")
    occupied = sorted((a, a + len(b)) for a, _, b in records if a)
    if any(hi > next_lo for (_, hi), (next_lo, _) in zip(occupied, occupied[1:])):
        raise ValueError("overlapping sections")
    return entry, records


def check_entry_chain(directory, *, debug, core_blob, menu_blob=None):
    """Check the emitted run-in-place call sequence from exact VBIN bytes."""
    from armasm import assemble, symbols

    blob = (directory / "fpSup.BIN").read_bytes()
    entry, records = decode(blob)
    worker = assemble(SHELL / "camera/worker.S") if debug else None
    expected_payloads = [(core_blob, 0)]
    if menu_blob is not None:
        expected_payloads.append((menu_blob, 0))
    if debug:
        expected_payloads.insert(0, (worker, symbols(SHELL / "camera/worker.S")["spawn"]))
    expected = []
    for payload, delta in expected_payloads:
        matches = [offset for address, offset, data in records
                   if address == 0 and data == payload]
        if len(matches) != 1:
            raise ValueError("run-in-place entry payload missing or duplicated")
        expected.append(matches[0] + delta)
    if len(expected) == 1:
        actual = [entry]
    else:
        tramp = [(offset, data) for address, offset, data in records
                 if address == 0 and offset == entry]
        if len(tramp) != 1:
            raise ValueError("VBIN entry does not name its entry trampoline")
        tr_off, tr_data = tramp[0]
        source = SHELL / "asm/entries.S"
        table = symbols(source)["table"]
        if tr_data[:table] != assemble(source)[:table]:
            raise ValueError("entry trampoline code differs")
        expected_table = (entry + table, *expected, 0)
        if tr_data[table:] != struct.pack(f"<{len(expected_table)}I", *expected_table):
            raise ValueError("entry trampoline sequence differs")
        actual = expected
    if actual != expected:
        raise ValueError("VBIN entry is not the Sensor Lab launch sequence")
    autorun = (directory / "AutoRun.txt").read_bytes()
    return dict(directory=str(directory), entries=[f"0x{x:08X}" for x in actual],
                sections=len(records), bin_sha256=hashlib.sha256(blob).hexdigest(),
                autorun_sha256=hashlib.sha256(autorun).hexdigest())


def slmp_limit_of(test_page):
    """The largest SLMP block the installer must take, per test page."""
    import sl_b25_page as SP
    # the SIZE sub page (or a whole stock test page) needs a larger block
    # (a ceiling, not padding; lab, 2026-10-03: B2_5 without MODE / Output rows,
    #  ~60 KB less than r19)
    return {"white": SP.SLMP_BYTES, "lab": 0x60000}.get(test_page, 0x50000)


def slmp_block(test_page, b25_stock_lists, custom_lists, slmp_limit):
    """The private B2_5 page's "SLMP" block (the installer's data).  Shared by
    this card (appended past the loader's 0xF000) and the Loader v3 sup
    (build_v3_reslab.py, inside the block)."""
    sys.path.insert(0, str(HERE / "sl_menu"))
    import sl_b25_page as SP
    import sl_lists as SLL
    SP.WITH_PRIVATE_LISTS = not b25_stock_lists
    SP.WITH_CUSTOM_LISTS = custom_lists
    SP.SIZE_JUMP_TO = {"lab": "SL_LAB", "size": "SL_SIZE_PG"}.get(test_page, "SL_TEST")
    res = SP.build()
    SP.audit(res)
    import sl_pages as SPG
    img = PL.FIRMWARE.read_bytes()
    # the private pages (sl_pages.py): stage 1 is the small SL_TEST that
    # SIZE's Right key jumps to (sl_b25_page.WITH_SIZE_JUMP)
    pages, pages_refs = b"", []
    if SP.WITH_SIZE_JUMP and not b25_stock_lists:
        if test_page in ("lab", "size"):
            import sl_size_page as SZ
            if test_page == "lab":
                import sl_lab_page as LAB
                plist, refs_by = SPG.lab_pages(img, res["pool"])
                LAB.check_page(plist[0][1], res["pool"], img)
                # first rule: no field, no word names a stock frame-guide variable
                for _n, pg, _p in plist:
                    stray = LAB.check_settings_free(pg, res["pool"], SP.load_schemas(img))
                    if stray:
                        raise RuntimeError(f"{_n} words equal frame-guide strings at {stray[:5]}")
            else:
                plist, prefs = SPG.size_pages(img, res["pool"])
                SZ.check_page(plist[0][1], res["pool"], img)
                refs_by = {plist[0][0]: prefs}
            for name, pg, _p in plist:
                SZ.check_refs(pg, refs_by[name], res["pool"])
            pages = SPG.build_pack(plist)
            pages_refs = SPG.pack_refs(pages, plist, refs_by)
        else:                                     # the stage-1 SL_TEST pages
            SPG.TEST_CONTENT = test_page
            pages = SPG.build_pack(SPG.test_pages(img))
    return SP.pack(res, SLL.build_pack(img) if custom_lists else b"", pages, slmp_limit,
                   pages_refs)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(output, debug=False, axis=None, fast=False, b25_menu=False, b25_stock_lists=False,
          custom_lists=True, test_page="lab"):
    output = Path(output).resolve()
    if output.exists():
        raise ValueError(f"output must be new: {output}")
    # CUSTOM-only frame-rate / bit-depth lists (sl_lists.py, sl_excl.S): only with
    # the private page.  The stock lists then stay stock (no 239.76 / 14-bit rows,
    # stock caps); set before anything reads the plan.
    custom_lists = b25_menu and custom_lists
    saved_flags = (PL.WITH_SL_EXCL, PL.WITH_RATE_ROW, PL.WITH_BIT_ROW)
    if custom_lists:
        PL.WITH_SL_EXCL, PL.WITH_RATE_ROW, PL.WITH_BIT_ROW = True, False, False
    try:
        # Keep even a late verification failure from leaving a complete-looking
        # card at the requested path.  A sibling staging directory makes the
        # final rename atomic on the same filesystem.
        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=f".{output.name}.building-",
                                         dir=output.parent) as staging_root:
            staged = Path(staging_root) / "card"
            manifest = _build(staged, debug, axis, fast, b25_menu,
                              b25_stock_lists, custom_lists, test_page)
            manifest["entry_check"]["directory"] = str(output)
            (staged / "MANIFEST.json").write_text(
                json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
            if output.exists():
                raise ValueError(f"output appeared during build: {output}")
            staged.rename(output)
            return manifest
    finally:
        PL.WITH_SL_EXCL, PL.WITH_RATE_ROW, PL.WITH_BIT_ROW = saved_flags


def _build(output, debug, axis, fast, b25_menu, b25_stock_lists, custom_lists, test_page="lab"):
    if output.exists():
        raise ValueError(f"output must be new: {output}")
    sources = {Path(__file__), PL.FIRMWARE, HERE / "imx410_plan.py",
               HERE / "res_lab_cave_audit.py", HERE / "test_res_lab_artifact.py",
               HERE / "res_lab_user_pack.py", HERE / "res_lab_user_launch.py",
               HERE / "res_lab_user_launch.S", HERE / "res_lab_journal_gate.S",
               HERE / "test_res_lab_migrated_boot.py", HERE / "test_res_lab_record_picker.py",
               HERE / "test_res_lab_exact_picker.py",
               HERE / "imx410_block.py", HERE / "imx410_full.py",
               HERE / "armasm.py", HERE / "og3k_plan.py",
               HERE / "imx410_rate_native.py", HERE / "imx410_rate_ui.py",
               HERE / "imx410_poff.S",
               HERE / "imx410_rate_lv.py", ROOT / "research/ui/tools/native_ui_audit.py",
               ROOT / "research/ui/tools/nbu_probe/nbu_format.py", ROOT / _PROFILE_JSON,
               SHELL / "build_autorun.py", SHELL / "armasm.py",
               SHELL / "patches.py", SHELL / "boot_splash.py"}
    sources.update(HERE / source for _, source, _ in PL.payloads())
    sources.update((SHELL / "asm").glob("*.S"))
    sources.update((SHELL / "camera").glob("*.S"))
    if b25_menu:
        sources.update({HERE / "sl_lists.py", HERE / "sl_excl.py", HERE / "sl_excl.S",
                        ROOT / "research/ui/tools/nbr.py",
                        HERE / "sl_b25_page.py", HERE / "sl_menu/sl_menu.c", HERE / "sl_menu/sl_menu.h",
                        HERE / "sl_pages.py", HERE / "sl_menu/sl_modes.c",
                        HERE / "sl_menu/sl_ui_hooks.c", HERE / "sl_size_page.py",
                        HERE / "sl_lab_page.py", HERE / "sl_wh_page.py",
                        HERE / "sl_menu/sl_menu_launch.S", HERE / "sl_menu/build_sl_menu.py",
                        ROOT / "fpSup/uishare/ui_pool.c", ROOT / "fpSup/uishare/ui_pool.h",
                        ROOT / "fpSup/uishare/ui_strings_code.h"})
    source_hashes = {str(p.relative_to(ROOT)): sha(p) for p in sorted(sources)}
    source_items = card_items(axis)
    image = PL.FIRMWARE.read_bytes()
    pack = res_lab_pack(source_items, firmware=image)
    # The sparse historical cave layout is an input format only.  The actual
    # product writes contain no Sensor Lab cave section: dynamic sites carry
    # their factory words so the shared stage2 journals them before arming.
    items = list(pack.static_words) + [
        (site, stock, "deferred Sensor Lab journal site")
        for site, stock in pack.dynamic_journal_words]
    if len({a for a, _, _ in items}) != len(items):
        raise ValueError("duplicate migrated Sensor Lab destination")
    CAVE_AUDIT.assert_pristine_cave_plan(items, image)
    CAVE_AUDIT.assert_no_res_lab_static_cave_plan(items)
    placed = sections(items)
    CAVE_AUDIT.assert_no_res_lab_static_cave_sections(
        [(address, 0, data) for address, data in placed])
    journal_max = sum(a >= 0x40000000 and not 0xC072D000 <= a < 0xC0735000
                      for a, _ in placed) + (len(IFACE) + len(PUSH) if debug else 0)
    core = build_core_launcher(pack, journal_max)
    output.mkdir(parents=True)
    with tempfile.TemporaryDirectory(prefix="res-lab-sections-") as tmp:
        command = [sys.executable, "-B", str(SHELL / "build_autorun.py"),
                   "--loader", "--banner", "Sensor Lab test", "--out",
                   str(output / "AutoRun.txt")]
        if not debug:
            command.append("--no-shell")
        command += AUTORUN_EXTRA
        if fast:
            command += list(FAST_FLAGS)
            if debug:
                command += ["--loader-hook-mark", hex(LOADER_HOOK_MARK)]
        core_path = Path(tmp) / "res_lab_core.bin"
        core_path.write_bytes(core.blob)
        command += ["--boot-bin", f"{core_path}:0"]
        menu_blob = menu_facts = menu_block = None
        if b25_menu:
            # The private B2_5 page (MODE / SIZE rows): an installer that runs
            # in place (--boot-bin) and its "SLMP" block, appended to fpSup.BIN
            # past the loader's 0xF000 below. Memory only: six registered
            # integers, no settings-store write (sl_menu/sl_menu.h).
            sys.path.insert(0, str(HERE / "sl_menu"))
            import build_sl_menu as BSM
            import sl_b25_page as SP
            slmp_limit = slmp_limit_of(test_page)
            menu_blob, menu_facts = BSM.build_blob(
                slmp_limit, core_offsets=pack.named_offsets,
                core_bytes=core.core_bytes,
                ui_hooks=[(h.site, h.stock_word, h.target_offset, h.kind)
                          for h in pack.late_ui_hooks],
                journal_gate_off=core.journal_gate_off, journal_max=journal_max)
            menu_block = slmp_block(test_page, b25_stock_lists, custom_lists, slmp_limit)
            path = Path(tmp) / "sl_menu.bin"
            path.write_bytes(menu_blob)
            command += ["--late-boot-bin", f"{path}:0"]
        for i, (address, data) in enumerate(placed):
            path = Path(tmp) / f"{i:03d}-{address:08x}.bin"
            path.write_bytes(data)
            command += ["--also-bin", f"{address:#x}:{path}"]
        result = subprocess.run(command, capture_output=True, text=True)
        (output / "build.log").write_text(result.stdout + result.stderr)
        if result.returncode:
            # The sibling staging directory is deleted on failure, including
            # build.log.  Preserve the actual diagnostic in the exception.
            raise RuntimeError("shared builder failed:\n" +
                               (result.stdout + result.stderr)[-4000:])
    entry, records = decode((output / "fpSup.BIN").read_bytes())
    # Audit the shared builder's actual VBIN too.  The planned sections alone
    # cannot rule out an additional fixed section emitted by the common chain.
    CAVE_AUDIT.assert_pristine_cave_sections(records, image)
    CAVE_AUDIT.assert_no_res_lab_static_cave_sections(records)
    words = {a + i: struct.unpack_from("<I", data, i)[0]
             for a, _, data in records if a >= 0x40000000
             for i in range(0, len(data), 4)}
    if any(words.get(a) != v for a, v, _ in items):
        raise ValueError("packaged bytes differ from the Sensor Lab plan")
    actual_journal = sum(a >= 0x40000000 and not 0xC072D000 <= a < 0xC0735000
                         for a, _, _ in records)
    if actual_journal != journal_max:
        raise ValueError(f"journal record count changed: expected {journal_max}, got {actual_journal}")
    check = check_entry_chain(output, debug=debug, core_blob=core.blob,
                              menu_blob=menu_blob)
    if b25_menu:
        binary = (output / "fpSup.BIN").read_bytes()
        if len(binary) > SP.SLMP_AT:
            raise RuntimeError(f"fpSup.BIN is {len(binary)} bytes: past the loader MAXLEN {SP.SLMP_AT:#x}")
        (output / "fpSup.BIN").write_bytes(binary + b"\0" * (SP.SLMP_AT - len(binary)) + menu_block)
    if source_hashes != {str(p.relative_to(ROOT)): sha(p) for p in sorted(sources)}:
        raise RuntimeError("source changed during build")
    ui = sorted((output / "FPSUPUI").glob("*.BIN")) if fast else []
    if fast and len(ui) != 5:
        raise RuntimeError(f"Fast card needs FPSUPUI/0..4.BIN, got {len(ui)}")
    if fast and PL.CAVE_LO <= LOADER_HOOK_MARK < PL.CAVE_HI:
        raise RuntimeError("loader hook mark lands in the Sensor Lab cave")
    manifest = dict(product="Sensor Lab", kind="offline-test-card", debug=debug,
                    hardware_verified=False, fast=fast, merge_supported=False,
                    persistent_settings_write=fast,
                    b25_menu=dict(installer={k: v for k, v in menu_facts.items() if k != "defines"},
                                  stock_lists=b25_stock_lists, custom_lists=custom_lists, test_page=test_page,
                                  block_at=SP.SLMP_AT, block_bytes=len(menu_block),
                                  file_bytes=SP.SLMP_AT + len(menu_block)) if b25_menu else None,
                    core=dict(launcher_bytes=len(core.blob), core_bytes=core.core_bytes,
                              core_blob_off=core.table_offsets["IMAGE_OFF"],
                              core_blob_sha256=hashlib.sha256(
                                  core.blob[core.table_offsets["IMAGE_OFF"]:]).hexdigest(),
                              journal_gate_off=core.journal_gate_off,
                              journal_max=journal_max,
                              core_magic_off=pack.named_offsets["core_magic"],
                              core_magic_word=CORE_MAGIC,
                              core_offsets=pack.named_offsets,
                              core_hook_sites=[f"0x{h.site:08X}" for h in pack.core_hooks],
                              late_ui_hook_sites=[f"0x{h.site:08X}" for h in pack.late_ui_hooks],
                              hook_sites=[f"0x{h.site:08X}" for h in pack.external_hooks],
                              pointer_sites=[f"0x{site:08X}" for p in pack.external_pointers
                                             for site in (p.low_site, p.high_site)],
                              dynamic_stock_sites={f"0x{site:08X}":f"0x{stock:08X}"
                                                   for site, stock in pack.dynamic_journal_words},
                              relocations=dict(offset=core.table_offsets["RELOCS_OFF"],
                                               count=len(pack.relocations), record_bytes=8,
                                               format="source_offset|kind<<30,target_offset"),
                              table_offsets=core.table_offsets),
                    loader_hook_mark=hex(LOADER_HOOK_MARK) if fast and debug else None,
                    axis=list(axis or PL.INITIAL_AXIS), entry=entry,
                    entry_check=check, plan_words=len(items), sections=len(records),
                    runtime_restore_addresses=[hex(a) for a, _, _ in runtime_restore_words(PL.FIRMWARE.read_bytes())],
                    source_sha256=source_hashes,
                    artifacts={**{n: sha(output / n) for n in ("AutoRun.txt", "fpSup.BIN")},
                               **{f"FPSUPUI/{u.name}": sha(u) for u in ui}},
                    limitations=list(PL.MISSING))
    from test_res_lab_artifact import shared_lower_cave
    shared_lower_cave(records, manifest)
    (output / "MANIFEST.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    if b25_menu:
        # EntryCheck above validates the VBIN before the large private page is
        # appended.  Inspect the delivered fpSup.BIN as well; a valid prefix
        # cannot stand in for a valid final file.
        from test_res_lab_artifact import verify_card
        verify_card(output)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--autorun-flag", action="append", default=[],
                        help="passed to build_autorun.py as is (e.g. --strip-comments, --fast-echo)")
    parser.add_argument("--fast", action="store_true",
                        help="Fast Start 3 dev card: writes the settings block")
    parser.add_argument("--axis-preset")
    parser.add_argument("--b25-menu", action="store_true",
                        help="private B2_5 page with MODE / SIZE rows (sl_b25_page.py); "
                             "uses the private SL_MODE / SL_SIZE lists")
    parser.add_argument("--test-page", choices=("lab", "size", "white", "b2_6_2"), default="lab",
                        help="with --b25-menu: what SIZE's Right key opens -- the SIZE sub page, or the "
                             "stage-1 SL_TEST (white / whole stock headphone page)")
    parser.add_argument("--no-custom-lists", action="store_true",
                        help="with --b25-menu: keep the 239.76 / 14-bit rows in the stock lists (r3)")
    parser.add_argument("--b25-stock-lists", action="store_true",
                        help="with --b25-menu: both rows use the stock frame-rate lists (test step)")
    args = parser.parse_args()
    AUTORUN_EXTRA[:] = [f if f.startswith("--") else "--" + f for f in args.autorun_flag]
    axis = None
    if args.axis_preset:
        from imx410_axis import preset_axis
        axis, _ = preset_axis(PL.Registry(), args.axis_preset)
    manifest = build(args.out, debug=args.debug, axis=axis, fast=args.fast, b25_menu=args.b25_menu,
                     b25_stock_lists=args.b25_stock_lists, custom_lists=not args.no_custom_lists,
                     test_page=args.test_page)
    print(json.dumps({k: manifest[k] for k in ("kind", "debug", "fast", "sections", "plan_words", "artifacts")}, indent=2))


if __name__ == "__main__":
    main()
