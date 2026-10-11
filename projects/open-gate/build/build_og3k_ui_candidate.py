#!/usr/bin/env python3
"""Build the OpenGate + native OG3K UI integration package.

This is intentionally separate from ``og3k_plan.py`` and the verified product
package.  It combines the current OpenGate write plan with the UI mechanism
that has a same-firmware camera precedent in the archived FP3K v0.3.2 work, but
narrows that mechanism to OpenGate's unresolved surfaces and records exact
runtime hits so the slower current AutoRun is not assumed safe:

* collapsed Settings summary (``3`` -> ``OG3K``),
* Quick Set 20/21 MV_Resolution animation groups,
* the shared Quick Set UHD/FHD/OG3K footer and its cursor range.

No HUD ``Resolution`` group is changed; OpenGate already owns its displayed
mode name.  The default remains the USB-shell debug candidate.  ``--release``
emits the same coupled OpenGate/UI payload through the shell-free loader; its
output stays under projects/open-gate until the two shipping files are promoted
into fpSup.
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent.parent
FIRMWARE = ROOT / "out" / "MAIN_c0000000.bin"
RESEARCH_UI = ROOT / "research" / "ui"
ARCHIVE = ROOT / "research" / "other" / "external" / "FP3K-technical-handoff-2026-09-10"
LAYOUT_PLAN = ARCHIVE / "prototype" / "development" / "native-ui" / "layout-repair-plan.json"
LEGACY_PLAN = ARCHIVE / "prototype" / "development" / "native-ui" / "ui-resource-plan.json"
LAYOUT_VERIFICATION = (
    ARCHIVE / "prototype" / "development" / "native-ui" / "layout-ui-verification.json"
)
SHELL_BUILDER = ROOT / "fpSup" / "fp_usb_shell" / "build_autorun.py"
DEFAULT_OUT = HERE / "ui_runtime_candidate"
DEFAULT_RELEASE_OUT = HERE / "ui_runtime_release"
sys.path.insert(0, str(HERE))
from og3k_plan import (EXPECTED_PLAN_WORDS, FPS_CODE, FPS_HOOK, FPS_HOOKS,
                       FPS_ORIGINAL, HOOKS as OG_HOOKS, DONOR_TIMING_ADDR,
                       NOMINAL_FPS, Plan, RESTORE_CODE, T as PLAN_TARGET,
                       V3, V3_OGV, WITH_FMTGUARD, ogv)  # noqa: E402

# og3krestore 的呼叫點:loader 的 VSHL entry(build_autorun.py --vshl-entry)。
# 2026-09-23 之前是在 AutoRun 末端借 echo 槽呼叫,但那三行不看 loader 成敗 ——
# fpSup.BIN 缺失或損壞時照樣跳進沒寫過的 cave。改成 entry 之後,只有開檔、
# magic、配置都成功,stage2 放完所有 firmware-address sections(含全部 hook)並
# publish D/I cache,才會叫到它。仍在同一個 task:loader 本身就是 AutoRun 借
# echo handler 叫起來的,跑在 shell dispatcher 的工作裡。debug 版有 USB worker,
# 由 entries.S trampoline 依序叫:worker 先、restore 後。
# 這個換位尚未上機驗證。見 notes/OG_BOOT_RESTORE_STABILITY_REVIEW_2026-09-23.md。
_ECHO_SLOT = 0xC0BAC2F8


def _check_restore_entry(binary: bytes, autorun: Path) -> None:
    """restore 只能由 VSHL entry 叫到,而且只叫一次。

    release 只有一個 entry,header 直接指向 RESTORE_CODE;debug 另有 USB worker,
    header 指向 entries.S trampoline,它的表必須以 RESTORE_CODE 結尾(表以 0 終止)。
    AutoRun 裡不能再有舊的 echo 呼叫 —— 那會在載入失敗時照跑,成功時跑第二次。
    """
    entry = struct.unpack_from("<4sIII", binary)[2]
    if entry >= 0x40000000:
        if entry != RESTORE_CODE:
            raise SystemExit(f"VSHL entry 0x{entry:08X} 不是 og3krestore")
    else:
        # entry 是 trampoline 在檔內的位移;它的表在同一段裡
        tail = struct.pack("<II", RESTORE_CODE, 0)
        if entry == 0 or binary.find(tail, entry) < 0:
            raise SystemExit("trampoline 的 entry 表不以 og3krestore 結尾")
    stale = f"mem set 0x{_ECHO_SLOT:08X} 0x{RESTORE_CODE:08X}"
    if any(line.strip() == stale for line in autorun.read_text().splitlines()):
        raise SystemExit("AutoRun 仍借 echo 槽呼叫 og3krestore")

# 相機螢幕上在載入時會顯示這行。原本寫死 "OG3K-UI-test!",於是 OG2K 的卡
# 也在螢幕上自稱 OG3K。改成跟著目標的標籤走 —— OG3K 的字串逐位元不變。
DEFAULT_BANNER = f"{PLAN_TARGET['label']}-UI-test!"

sys.path.insert(0, str(ROOT / "fpSup" / "fp_usb_shell"))
from armasm import assemble, symbols  # noqa: E402

sys.path.insert(0, str(RESEARCH_UI / "tools"))
from nbr import Resource, build as build_nbr, inspect as inspect_nbr  # noqa: E402
from xci import decode as decode_xci, encode as encode_xci, text_tile  # noqa: E402


ROM_BASE = 0xC0000000
UI_CODE = 0xC0732C84
UI_CODE_END = 0xC0734C84
UI_STATE = 0xC0732700
UI_RECORD_COUNT = 360
UI_HIT_BITMAP_OFFSET = 24
UI_HIT_BITMAP_BYTES = (UI_RECORD_COUNT + 7) // 8
UI_STATE_BYTES = (UI_HIT_BITMAP_OFFSET + UI_HIT_BITMAP_BYTES + 3) & ~3
# og3k_ui.S ui_layout state (REQ), reset every load.
UI_REQ = 0xC07327C8
UI_REQ_BYTES = 48
UI_LLOG = 0xC0732800       # --ui-diag only
UI_LLOG_BYTES = 128
# --ui-diag only: og3k_ui.S's two 16-word caller-capture slots (DIAG).
UI_DIAG = UI_STATE + UI_STATE_BYTES
UI_DIAG_BYTES = 128
UI_PACK = 0xC0793060
UI_PACK_END = 0xC079585C

# These older diagnostic payloads use part of the resident-owned state/code
# range.  They remain useful in isolation, but must never be armed while this
# candidate is resident.  The firmware's built-in ``gui image log`` does not
# consume these caves and is the supported draw measurement path.
INCOMPATIBLE_DIAGNOSTICS = (
    "projects/open-gate/build/size_ctl.py",
    "projects/open-gate/build/cfgring.S",
    "projects/open-gate/build/cfgsnap.S",
    "projects/open-gate/build/dimlog.S",
    "projects/open-gate/build/entlog.S",
    "projects/open-gate/build/entseq.S",
    "projects/open-gate/build/keyring.S",
    "projects/open-gate/build/keyseq.S",
    "projects/open-gate/build/proflog.S",
    "projects/open-gate/build/profseq.S",
    "projects/open-gate/build/zoomlog.S",
    "projects/open-gate/build/og3ktile.py",
    "projects/open-gate/build/livepatch.py",
    "projects/open-gate/build/appendobs_ctl.py",
    "projects/open-gate/build/elemobs_ctl.py",
    "projects/open-gate/build/xcitrace_ctl.py",
    "research/ui/tools/appendobs_ctl.py",
    "research/ui/tools/elemobs_ctl.py",
    "research/ui/tools/xcitrace_ctl.py",
    "research/ui/tools/build_appendobs_boot_probe.py",
)

THUMB_HOOKS = (
    # Arm the passive dependency first and the record hook last.  Once
    # ui_record is live it can immediately expose synthetic string offsets to
    # the stock parser, so ui_string must already be ready even during the
    # small window between VSHL section writes.
    (0xC05E5B58, 0x3FFFF1B1, "ui_string", "NBU string resolver"),
    (0xC05E84D8, 0xB086B500, "ui_load", "NBR memory loader"),
    (0xC05E6400, 0x4FF0E92D, "ui_record", "NBU record interpreter"),
    # Last: it releases a Quick Set layout built before the hooks so the next
    # load re-parses it -- which is only useful once ui_record is live.
    (0xC05D90F0, 0x4CF0E92D, "ui_layout", "layout loader (stale Quick Set release)"),
)

# OG_UISHARE=1 (2026-10-04, fpSup/uishare/NESTED_HOOKS.md): no string hook.
# The labels are strings in OpenGate's FPUI block; ui_apply puts them in
# OpenGate's own layer of the nested string hooks and writes their offsets into
# ui_aliases (STRBASE). og3k_ui.S is assembled with UI_NESTED.
NESTED = os.environ.get("OG_UISHARE") == "1"
if NESTED:
    THUMB_HOOKS = tuple(h for h in THUMB_HOOKS if h[2] != "ui_string")
# ui_aliases[k] -> the string it names (k = alias byte - 0xF2; 3 is unused)
ALIAS_STRINGS = ((0, "OG3K_QS"), (1, "OG3K_SET"), (2, "OG3K_FONT"), (4, None))  # None: the summary

EXPECTED_FIRMWARE_SHA256 = "92a8ee993f6c3d66c251e88d45a2ccd5135c6cf7342717784321c2ed506e2fb4"
EXPECTED_UI_PREFIX_BYTES = 49_245_696
EXPECTED_UI_PREFIX_SHA256 = "aaa5208a028d9c4aebb9cc8614add723d456e96b2a95914f433079954320e622"
WANTED_GROUPS = {"20_MV_Resolution", "21_MV_Resolution"}
ALIASES = {"FP3K_QS": 0xF2, "FP3K_SET": 0xF3, "FP3K_FONT": 0xF4}


def fnv(data: bytes) -> int:
    value = 0x811C9DC5
    for byte in data:
        value = ((value ^ byte) * 0x01000193) & 0xFFFFFFFF
    return value


def thumb_branch(site: int, target: int) -> int:
    """Encode a Thumb-2 B.W T4 without changing LR."""
    delta = target - site - 4
    if delta % 2 or not -(1 << 24) <= delta < (1 << 24):
        raise ValueError("Thumb hook target is out of range or misaligned")
    sign = (delta >> 24) & 1
    i1, i2 = (delta >> 23) & 1, (delta >> 22) & 1
    j1, j2 = (~i1 ^ sign) & 1, (~i2 ^ sign) & 1
    first = 0xF000 | sign << 10 | ((delta >> 12) & 0x3FF)
    second = 0x9000 | j1 << 13 | j2 << 11 | ((delta >> 1) & 0x7FF)
    return first | second << 16


def selected_plans() -> tuple[list[dict], dict]:
    """Select only OpenGate-coupled records from the hardware-proven plan."""
    full = json.loads(LAYOUT_PLAN.read_text())
    legacy = json.loads(LEGACY_PLAN.read_text())
    if full["firmware_sha256"] != EXPECTED_UI_PREFIX_SHA256:
        raise SystemExit("archived UI layout plan targets a different firmware")

    groups = [group for group in full["groups"] if group["name"] in WANTED_GROUPS]
    addresses = {group["address"] for group in groups}
    addresses.update(address for group in groups for address in group["clips"])
    plans = [plan for plan in full["plans"] if plan["address"] in addresses]
    plans += [plan for plan in full["plans"]
              if plan["kind"] in {"summary-label", "literal-delta"}]
    limits = [plan for plan in legacy["plans"] if plan["kind"] == "QS-limit"]
    if {int(plan["address"], 16) for plan in limits} != {0xC237249F, 0xC25E405A}:
        raise SystemExit("unexpected Quick Set controller plan")
    plans += limits
    plans.sort(key=lambda plan: int(plan["address"], 16))

    if len({plan["address"] for plan in plans}) != len(plans):
        raise SystemExit("duplicate selected UI source record")
    kinds: dict[str, int] = {}
    for plan in plans:
        kinds[plan["kind"]] = kinds.get(plan["kind"], 0) + 1
    expected = {
        "layout-keys": 315,
        "state-end": 36,
        "literal-delta": 6,
        "summary-label": 1,
        "QS-limit": 2,
    }
    if kinds != expected:
        raise SystemExit(f"selected UI plan shape changed: {kinds} != {expected}")
    if len(plans) != UI_RECORD_COUNT:
        raise SystemExit(f"selected {len(plans)} records, expected {UI_RECORD_COUNT}")

    verification = json.loads(LAYOUT_VERIFICATION.read_text())
    passed = {row["case"] for row in verification["cases"] if row.get("passed")}
    expected_cases = {f"parser-copy-{plan['address'].lower()}" for plan in plans}
    missing = sorted(expected_cases - passed)
    if missing:
        raise SystemExit(
            f"archived native parser verification lacks {len(missing)} selected records"
        )
    return plans, {
        "groups": groups,
        "kinds": kinds,
        "archived_parser_cases": len(expected_cases),
    }


def record_tables(plans: list[dict], firmware: bytes) -> tuple[str, dict]:
    """Encode the resident's compact, exact-fingerprint lookup table."""
    rows: list[tuple[int, int, int]] = []
    edits = bytearray()
    maximum = 0
    for plan in plans:
        address = int(plan["address"], 16)
        source = bytes.fromhex(plan["old"])
        replacement = bytes.fromhex(plan["new"])
        maximum = max(maximum, len(replacement))
        if firmware[address - ROM_BASE:address - ROM_BASE + len(source)] != source:
            raise SystemExit(f"firmware bytes do not match UI plan at 0x{address:08X}")
        if not 8 <= len(source) <= 512 or len(replacement) > 512:
            raise SystemExit(f"UI record bounds changed at 0x{address:08X}")

        meta = len(source)
        kind = plan["kind"]
        if kind == "layout-keys":
            aliases = plan.get("aliases", {})
            if len(aliases) > 1:
                raise SystemExit("resident supports one image alias per animation record")
            property_index = int(next(iter(aliases), "-1")) + 1
            if not 0 <= property_index < 16:
                raise SystemExit("animation property index no longer fits metadata")
            alias_name = next(iter(aliases.values()), None)
            if alias_name not in ALIASES and alias_name is not None:
                raise SystemExit(f"unexpected OpenGate UI alias {alias_name}")
            alias = ALIASES.get(alias_name, 0)
            meta |= 1 << 10 | int(plan["time"]) << 13 | property_index << 20 | alias << 24
        elif kind == "state-end":
            meta |= 2 << 10 | int(plan["time"]) << 13
        elif kind == "summary-label":
            meta |= 3 << 10
        elif kind == "literal-delta":
            if len(edits) >= 1 << 19:
                raise SystemExit("UI edit table offset no longer fits metadata")
            meta |= 4 << 10 | len(edits) << 13
            for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(
                None, source, replacement, autojunk=False
            ).get_opcodes():
                if tag == "equal":
                    continue
                inserted = replacement[j1:j2]
                edits.extend(struct.pack("<HHH", i1, i2 - i1, len(inserted)))
                edits.extend(inserted)
                edits.extend(bytes(len(edits) % 2))
            edits.extend(b"\xff\xff")
        elif kind == "QS-limit":
            if len(source) != 40 or len(replacement) != 44:
                raise SystemExit("Quick Set limit record layout changed")
            if replacement != source[:32] + struct.pack(">f", 2.0) + source[32:]:
                # The generator also changes record length/mask; compare those
                # explicitly below instead of accepting unrelated changes.
                candidate = bytearray(source[:32] + struct.pack(">f", 2.0) + source[32:])
                struct.pack_into(">I", candidate, 4, 44)
                candidate[31] = 0x1A
                if bytes(candidate) != replacement:
                    raise SystemExit("Quick Set limit replacement changed")
        else:
            raise SystemExit(f"unsupported UI plan kind {kind}")
        rows.append((address, meta, fnv(source)))

    lines = [f".equ UI_RECORD_COUNT, {len(rows)}", "ui_records:"]
    lines += [f"    .word 0x{address:08x},0x{meta:08x},0x{fingerprint:08x}"
              for address, meta, fingerprint in rows]
    lines.append("ui_edits:")
    if edits:
        for offset in range(0, len(edits), 24):
            lines.append("    .byte " + ",".join(str(byte) for byte in edits[offset:offset + 24]))
    else:
        lines.append("    .byte 0")
    lines.append(".align 2")
    return "\n".join(lines) + "\n", {
        "records": len(rows), "edit_bytes": len(edits), "maximum_record_bytes": maximum
    }


def _hud_tile(text, width, height, cap=28, ink=81, ring=3,
              font="/System/Library/Fonts/Helvetica.ttc"):
    """算繪一張原廠 HUD 樣式的數字圖塊:白字、不透明黑邊,**ARGB4444**。

    ★ 像素格式不是 (亮度, alpha),也不是 RGB565,是 **ARGB4444**。
    2026-09-15 解了兩張原廠的 88x38 資源(0xC13BA6E4 / 0xC13D5AFC),
    31 個獨特值全部長成 `A<<12 | g<<8 | g<<4 | g`:

        0xFFFF  A=15 白      筆畫內部
        0xF333  A=15 深灰    筆畫抗鋸齒(不透明)
        0xF000  A=15 黑      黑邊
        0x8000  A=8  黑      黑邊的抗鋸齒
        0x0000  全透明

    規則:**alpha 取膨脹後的覆蓋率,RGB 取原覆蓋率**。
    筆畫內兩者都滿 → 白;環上覆蓋率 0 但膨脹後不為 0 → 不透明黑;
    環外兩者都 0 → 透明。

    metrics 也照原廠量的:cap 高 28、墨水寬 81/88、黑邊 3 px。
    (`text_tile` 的寬度邊界寫死 w-12 = 76,塞不到 81,所以這裡自己算繪。)

    先前兩次猜錯都是實機畫面指出來的:
      v0.1.5 當成 (亮度, alpha):黑邊寫 L=0/A=255 → 0xFF00 → 橘紅
      v0.1.6 當成 RGB565:顏色仍然怪
    第三次改成直接解原廠資源才拿到正確答案 —— **格式要解,不要猜**。
    """
    import numpy as _np
    from PIL import Image, ImageDraw, ImageFont
    ss = 8
    for size in range(96, 8, -1):
        f = ImageFont.truetype(font, size * ss)
        big = Image.new("L", (width * ss, height * ss), 0)
        ImageDraw.Draw(big).text((width * ss // 2, height * ss // 2), text,
                                 font=f, fill=255, anchor="mm")
        arr = _np.array(big)
        ys, xs = _np.where(arr > 30)
        if not len(xs):
            continue
        if ((ys.max() - ys.min() + 1) / ss <= cap
                and (xs.max() - xs.min() + 1) / ss <= ink):
            cover = _np.array(big.resize((width, height), Image.LANCZOS))
            ys, xs = _np.where(cover > 10)
            cover = _np.roll(_np.roll(
                cover, (height - (ys.max() - ys.min() + 1)) // 2 - ys.min(), 0),
                (width - (xs.max() - xs.min() + 1)) // 2 - xs.min(), 1)
            break
    else:
        raise SystemExit(f"{text!r} does not fit {width}x{height}")
    grown = cover.astype(_np.uint16)
    for dy in range(-ring, ring + 1):
        for dx in range(-ring, ring + 1):
            grown = _np.maximum(grown, _np.roll(_np.roll(
                cover.astype(_np.uint16), dy, 0), dx, 1))
    a4 = (grown >> 4) & 0xF
    g4 = (cover.astype(_np.uint16) >> 4) & 0xF
    argb = (a4 << 12) | (g4 << 8) | (g4 << 4) | g4
    return (argb & 0xFF).astype(_np.uint8), (argb >> 8).astype(_np.uint8)


def assets(out: Path, names: dict | None = None) -> tuple[bytes, list[dict]]:
    """Create three OG3K assets; retain the already-reviewed 86x49 QS tile.

    names: rename the three QS resources (uishare QS_SHARE.md §9.4: the Loader v3
    sup gives them its file-name prefix, "30OG3K_QS"); None keeps OG3K_*."""
    asset_dir = out / "assets"
    asset_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    resources = []
    # 資源名稱是內部識別字,跟著 UI 記錄走,兩個目標共用;**畫出來的字**
    # 才是目標相依的。OG3K 的 QS 圖塊釘在已經人工檢視過的那一份;
    # 其他目標一律由 text_tile 生成(同一個算繪路徑,只是文字不同)。
    label = PLAN_TARGET["label"]
    pinned = RESEARCH_UI / "captures" / "og3k_86x49.xci" if label == "OG3K" else None
    definitions = [
        ("OG3K_QS", 86, 49, 24, pinned, label, None),
        ("OG3K_SET", 86, 74, 24, None, label, None),
        ("OG3K_FONT", 150, 38, 24, None, label, None),
    ]
    if names:
        definitions = [(names.get(d[0], d[0]),) + d[1:] for d in definitions]

    # 相機用 `font_S_imageSize_<數字>` 這個資源族畫解析度標籤,**寬高各查一次**。
    # 韌體有 70 個,但不是每個數字都有:OG3K 的 3008x2000 兩個都在,
    # OG2K 的 2000x1334 缺 1334 —— 載入失敗不報錯,回放左上角就畫出彩色雜訊。
    #
    # 我們的私有 NBR 由 ui_load 註冊進**相機自己的資源 context**(見 og3k_ui.S),
    # 所以只要 pack 裡有同名資源,原廠的名稱查詢就找得到。缺哪個補哪個。
    #
    # 字型用 Helvetica —— 和相機自己的細體 grotesque 最接近;OG3K 的標籤
    # 用的 Arial Narrow Bold 太粗,擺在原廠數字旁邊會很突兀。
    firmware = FIRMWARE.read_bytes()
    for value in dict.fromkeys(PLAN_TARGET["act"]):
        resname = f"font_S_imageSize_{value}"
        if resname.encode() + b"\0" in firmware:
            continue
        definitions.append((resname, 88, 38, 28, None, str(value),
                            "/System/Library/Fonts/Helvetica.ttc"))

    for name, width, height, cap, source, text, font in definitions:
        if source is None:
            if font:
                luminance, alpha = _hud_tile(text, width, height, font=font)
            else:
                luminance, alpha = text_tile(text, width, height, cap=cap)
            blob = encode_xci(luminance, alpha)
        else:
            blob = source.read_bytes()
            got_w, got_h, luminance, alpha = decode_xci(blob)
            if (got_w, got_h) != (width, height):
                raise SystemExit(f"canonical QS tile is {got_w}x{got_h}, expected {width}x{height}")
        got_w, got_h, got_l, got_a = decode_xci(blob)
        if ((got_w, got_h) != (width, height) or got_l.shape != got_a.shape
                or got_l.tobytes() != luminance.tobytes()
                or got_a.tobytes() != alpha.tobytes()):
            raise SystemExit(f"XCI round-trip failed for {name}")
        (asset_dir / f"{name}.xci").write_bytes(blob)
        try:
            from PIL import Image
            Image.fromarray(got_a).save(asset_dir / f"{name}.png")
        except TypeError:
            Image.frombytes("L", (width, height), got_a.tobytes()).save(
                asset_dir / f"{name}.png")
        resources.append(Resource(name, f"{name}.xci", blob))
        rows.append({
            "name": name, "width": width, "height": height, "bytes": len(blob),
            "sha256": hashlib.sha256(blob).hexdigest(),
        })
    pack = build_nbr(resources)
    inventory = inspect_nbr(pack)
    if {row["name"] for row in inventory["resources"]} != {row["name"] for row in rows}:
        raise SystemExit("private NBR inventory does not match generated assets")
    (out / "OG3KUI.NBR").write_bytes(pack)
    return pack, rows


def runs(items: list[tuple[int, int, str]]) -> list[list[tuple[int, int, str]]]:
    out: list[list[tuple[int, int, str]]] = []
    current: list[tuple[int, int, str]] = []
    for item in items:
        if current and item[0] == current[-1][0] + 4:
            current.append(item)
        else:
            if current:
                out.append(current)
            current = [item]
    if current:
        out.append(current)
    return out


def build(
    out: Path | None = None,
    banner: str = DEFAULT_BANNER,
    release: bool = False,
    ui_diag: bool = False,
    compose_only: bool = False,
) -> dict:
    out = out or (DEFAULT_RELEASE_OUT if release else DEFAULT_OUT)
    firmware = FIRMWARE.read_bytes()
    firmware_sha = hashlib.sha256(firmware).hexdigest()
    if firmware_sha != EXPECTED_FIRMWARE_SHA256:
        raise SystemExit(f"unsupported firmware image {firmware_sha}")
    prefix_sha = hashlib.sha256(firmware[:EXPECTED_UI_PREFIX_BYTES]).hexdigest()
    if prefix_sha != EXPECTED_UI_PREFIX_SHA256:
        raise SystemExit(f"UI-bearing MAIN prefix has changed: {prefix_sha}")

    open_gate = Plan(firmware)
    errors = open_gate.check()
    if errors:
        raise SystemExit("OpenGate base plan failed:\n" + "\n".join(errors))

    plans, selection = selected_plans()
    table_source, table_info = record_tables(plans, firmware)
    pack, asset_rows = assets(out)
    pack += bytes((-len(pack)) % 4)
    if UI_PACK + len(pack) > UI_PACK_END:
        raise SystemExit("private NBR pack does not fit its candidate cave")

    # Assembled from a temporary directory, so og_pic.inc goes in by value.
    combined = (HERE / "og3k_ui.S").read_text().replace(
        '#include "og_pic.inc"\n', (HERE / "og_pic.inc").read_text(), 1)
    combined += f"\n.equ OG3K_UI_PACK_BYTES, {len(pack)}\n" + table_source
    with tempfile.TemporaryDirectory(prefix="og3k-ui-source-") as temp:
        source = Path(temp) / "og3k_ui_combined.S"
        source.write_text(combined)
        ui_defs = [f'UI_SUMMARY_TEXT="{PLAN_TARGET["label"]}"']
        if ui_diag:
            ui_defs.append("UI_DIAG=1")
        if NESTED:
            ui_defs.append("UI_NESTED=1")
        if V3:
            ui_defs += ["OG_V3=1", f"OGV={V3_OGV:#x}", f"OG_ORG={ogv(UI_CODE):#x}"]
        code = assemble(source, ui_defs)
        syms = symbols(source, ui_defs)
    for _, expected, label, description in THUMB_HOOKS:
        original = syms[f"{label}_original"] & ~1
        if code[original:original + 4] != struct.pack("<I", expected):
            raise SystemExit(f"{description} trampoline does not replay its stock word")
    # Seven internal transfers enter Thumb code (ui_layout adds its tail into
    # ui_layout_original and its call to the firmware's Thumb LAYOUT_FIND).
    # ORR is deliberate: clang tags
    # .thumb_func symbols with bit zero already, so ADD #1 would toggle the
    # effective target back to ARM.  The idempotent form is safe either way.
    force_thumb = struct.pack("<I", 0xE38CC001)  # orr ip, ip, #1
    bad_toggle = struct.pack("<I", 0xE28CC001)   # add ip, ip, #1
    if code.count(force_thumb) != (6 if NESTED else 7) or bad_toggle in code:
        raise SystemExit("internal Thumb trampoline state guard changed")
    if UI_CODE + len(code) > UI_CODE_END:
        raise SystemExit(
            f"UI payload 0x{len(code):X} bytes exceeds cave by "
            f"0x{UI_CODE + len(code) - UI_CODE_END:X}"
        )

    for start, size, label in ((UI_CODE, len(code), "UI code"),
                               (UI_STATE, UI_STATE_BYTES, "UI state"),
                               (UI_PACK, len(pack), "UI pack")):
        region = firmware[start - ROM_BASE:start - ROM_BASE + size]
        if len(region) != size or any(region):
            raise SystemExit(f"{label} candidate cave is not zero at 0x{start:08X}")

    og_hook_sites = {site for site, *_ in OG_HOOKS}
    base_items = list(open_gate.all())
    if len(base_items) != EXPECTED_PLAN_WORDS + open_gate.v3_growth:
        raise SystemExit(
            f"OpenGate core 有 {len(base_items)} words，預期 {EXPECTED_PLAN_WORDS}"
            f" + {open_gate.v3_growth}(OG_V3)"
        )
    armed = [item for item in base_items if item[0] in og_hook_sites]
    base_items = [item for item in base_items if item[0] not in og_hook_sites]

    ui_items = [(UI_CODE + index * 4, value, "OG3K native UI payload")
                for index, value in enumerate(struct.unpack(f"<{len(code)//4}I", code))]
    pack_items = [(UI_PACK + index * 4, value, "OG3K private NBR pack")
                  for index, value in enumerate(struct.unpack(f"<{len(pack)//4}I", pack))]
    state_items = [(UI_STATE + index * 4, 0, "OG3K UI state reset")
                   for index in range(UI_STATE_BYTES // 4)]
    region = firmware[UI_REQ - ROM_BASE:UI_REQ - ROM_BASE + UI_REQ_BYTES]
    if any(region):
        raise SystemExit("ui_layout state area is not a zero cave")
    state_items += [(UI_REQ + index * 4, 0, "OG3K ui_layout state reset")
                    for index in range(UI_REQ_BYTES // 4)]
    if ui_diag:
        if UI_DIAG != 0xC0732748:
            raise SystemExit("og3k_ui.S DIAG no longer follows the UI state block")
        region = firmware[UI_DIAG - ROM_BASE:UI_DIAG - ROM_BASE + UI_DIAG_BYTES]
        if any(region):
            raise SystemExit("UI diag capture area is not a zero cave")
        state_items += [(UI_DIAG + index * 4, 0, "OG3K UI diag reset")
                        for index in range(UI_DIAG_BYTES // 4)]
        # og3k_ui.S LLOG: ui_layout's decision log.
        region = firmware[UI_LLOG - ROM_BASE:UI_LLOG - ROM_BASE + UI_LLOG_BYTES]
        if any(region):
            raise SystemExit("ui_layout log area is not a zero cave")
        state_items += [(UI_LLOG + index * 4, 0, "OG3K ui_layout log reset")
                        for index in range(UI_LLOG_BYTES // 4)]

    ui_hooks = []
    for site, expected, label, description in THUMB_HOOKS:
        actual = struct.unpack_from("<I", firmware, site - ROM_BASE)[0]
        if actual != expected:
            raise SystemExit(
                f"{description} hook 0x{site:08X} is 0x{actual:08X}, expected 0x{expected:08X}"
            )
        # ELF symbol values for Thumb functions carry bit zero as the ISA tag;
        # B.W itself is encoded against the aligned instruction address.
        target = UI_CODE + (syms[label] & ~1)
        ui_hooks.append((site, thumb_branch(site, target), f"hook {description}"))
    if [site for site, _, _ in ui_hooks][-2:] != [0xC05E6400, 0xC05D90F0]:
        raise SystemExit("NBU record hook must be armed after its loader/string dependencies, "
                         "and the layout hook after it")

    items = base_items + ui_items + pack_items + state_items + armed + ui_hooks
    addresses: dict[int, str] = {}
    for address, _, note in items:
        if address in addresses:
            raise SystemExit(f"write collision at 0x{address:08X}: {addresses[address]} / {note}")
        addresses[address] = note

    hook_sites = og_hook_sites | {site for site, *_ in THUMB_HOOKS}
    segments = runs(items)
    for segment in segments:
        if any(address in hook_sites for address, _, _ in segment) and len(segment) != 1:
            raise SystemExit("a hook was merged into a multiword VSHL section")
    first_hook = min(index for index, segment in enumerate(segments)
                     if segment[0][0] in hook_sites)
    if any(segment[0][0] not in hook_sites for segment in segments[first_hook:]):
        raise SystemExit("a payload section appears after hook arming")

    if compose_only:
        # Loader v3 (build_v3_og.py): the planned words and what they are, before
        # any card is made. The checks above have all run; `out` holds only the
        # asset files assets() wrote.
        return {"items": items, "base_items": base_items, "armed": armed,
                "ui_hooks": ui_hooks, "code": code, "pack": pack, "syms": syms,
                "state_items": state_items, "open_gate": open_gate}
    out.mkdir(parents=True, exist_ok=True)
    (out / "OG3KUI.BIN").write_bytes(code)
    (out / "ui_records.generated.inc").write_text(table_source)
    with tempfile.TemporaryDirectory(prefix="og3k-ui-segments-") as temp:
        command = [sys.executable, str(SHELL_BUILDER), "--loader", "--banner",
                   banner, "--out", str(out / "AutoRun.txt")]
        if release:
            command.append("--no-shell")
        if WITH_FMTGUARD:
            command += ["--vshl-entry", f"0x{RESTORE_CODE:08X}"]
        temp_path = Path(temp)
        for index, segment in enumerate(segments):
            blob = b"".join(struct.pack("<I", value) for _, value, _ in segment)
            path = temp_path / f"ui_{index:03d}_{segment[0][0]:08X}.bin"
            path.write_bytes(blob)
            command += ["--also-bin", f"0x{segment[0][0]:08X}:{path}"]
        subprocess.run(command, check=True)

    binary = (out / "fpSup.BIN").read_bytes()
    magic, count, entry, body_bytes = struct.unpack_from("<4sIII", binary)
    if magic != b"VBIN":
        raise SystemExit("generated fpSup.BIN has the wrong magic")
    if WITH_FMTGUARD:
        _check_restore_entry(binary, out / "AutoRun.txt")
    got: dict[int, int] = {}
    offset = 16 + count * 8
    for index in range(count):
        destination, length = struct.unpack_from("<II", binary, 16 + index * 8)
        payload = binary[offset:offset + length]
        offset += length + (-length % 4)
        if destination >= 0x40000000:
            for inner in range(0, length, 4):
                got[destination + inner] = struct.unpack_from("<I", payload, inner)[0]
    missing = [(address, value) for address, value, _ in items if got.get(address) != value]
    if missing:
        raise SystemExit(f"VSHL readback omitted or changed {len(missing)} planned words")

    commands = [line for line in (out / "AutoRun.txt").read_text().splitlines()
                if line.strip() and not line.lstrip().startswith("#")]
    _label = PLAN_TARGET["label"]
    # 這些 status / hardware_result 字串講的是 **OG3K 的實測歷史**。其他目標
    # 沿用它,等於把別張卡的相機結果寫進一份機器可讀的清單。OG3K 保持原字串
    # 逐位元不變,其餘目標只陳述這份清單真正知道的事。
    _foreign_status = (
        f"{_label} {'release test candidate' if release else 'debug candidate'}; "
        f"no camera result is recorded in this manifest for {_label}"
    )
    manifest = {
        "status": _foreign_status if _label != "OG3K" else ((
            "release test candidate; camera-tested CINE UI payload; the previous "
            "single-callsite shutter-angle fix failed a confirmed FHD/OG3K camera "
            "comparison; after the four-callsite and I-cache fixes, a battery-out "
            "29.97/180-degree FHD/OG3K live-view comparison received a provisional "
            "visual pass; exact readback and the other frame rates remain pending; "
            "no USB shell"
        ) if release else (
            "debug candidate; predecessor FHD/UHD/OG3K resolution selection and short "
            "record start/stop transitions passed on camera; CINE/STILL switching and "
            "warm restart were not tested; the previous single-callsite shutter-angle "
            "fix failed a confirmed FHD/OG3K camera comparison; after the revised "
            "four-callsite and I-cache fixes, a battery-out 29.97/180-degree "
            "FHD/OG3K live-view comparison received a provisional visual pass; exact "
            "readback and the other frame rates remain pending"
        )),
        "firmware": "SIGMA fp 5.02",
        "firmware_sha256": firmware_sha,
        "ui_prefix_bytes": EXPECTED_UI_PREFIX_BYTES,
        "ui_prefix_sha256": prefix_sha,
        "base_opengate_writes": len(list(open_gate.all())),
        "angle_fps_fix": {
            # 沒有武裝就不要帶 OG3K 的 previous/revised_hardware_result ——
            # 那是另一張卡的相機結果。不改 donor 時序的目標(donor 的標稱 fps
            # metadata 原廠就等於真實擷取率)根本沒有東西要更正。
            "status": (
                "not armed for this target: the donor sensor timing is written "
                "unchanged, so its stock nominal-FPS metadata is already the true "
                "capture rate and there is nothing to correct"
            ) if not FPS_HOOKS else (
                "previous single-callsite build failed on camera; revised four-callsite "
                "plus I-cache build received a provisional visual pass after a "
                "battery-out cold boot at 29.97/180 degrees; exact readback and other "
                "frame rates remain pending"
            ),
            "scope": (
                "four local BL callsites in shutter-angle conversion/metadata/"
                "resolution-sync paths share one narrow wrapper; shutter-speed path "
                "unchanged"
            ),
            "callsite_count": len(FPS_HOOKS),
            "hooks": [
                {
                    "address": f"0x{site:08X}",
                    "role": role,
                    "stock_word": f"0x{stock:08X}",
                    "stock_target": f"0x{FPS_ORIGINAL:08X}",
                }
                for site, stock, role in FPS_HOOKS
            ],
            # Retain the original primary fields for older manifest consumers;
            # ``hooks`` above is the authoritative complete callsite inventory.
            "hook_address": f"0x{FPS_HOOK:08X}",
            "stock_word": f"0x{open_gate.word(FPS_HOOK):08X}",
            "stock_target": f"0x{FPS_ORIGINAL:08X}",
            "payload_address": f"0x{FPS_CODE:08X}",
            "previous_hardware_result": {
                "candidate": "single-callsite predecessor",
                "result": "failed",
                "conditions": "confirmed real FHD and OG3K modes; idle live view",
                "fhd_shutter_us": 16663,
                "og3k_shutter_us": 6411,
                "gain_unchanged": True,
            },
            "revised_hardware_result": {
                "result": "provisional visual pass",
                "conditions": (
                    "battery-out cold boot; real FHD and OG3K; 29.97 fps; "
                    "180 degrees; idle live view; no recording"
                ),
                "reported_by": "camera operator",
                "exact_shell_readback": False,
                "other_frame_rates_tested": False,
            },
            "runtime_source": (
                f"FLAG==1 plus exact mode98 timing tuple at 0x{DONOR_TIMING_ADDR:08X}"
            ),
            "stock_getter_called_first": True,
            "unknown_or_mixed_timing": "fail open to stock getter result",
            "nominal_fps": NOMINAL_FPS,
            "static_shared_mode_or_photo_fields_written": False,
            "mode98_timing_restored_when_resolution_leaves_og3k": True,
            "cine_still_transition": (
                "hardware pending; select FHD or UHD before leaving CINE until tested"
            ),
            "warm_restart": (
                "not tested or supported; battery-out cold boot is the only accepted baseline"
            ),
        },
        "ui": {
            "nested_strings": NESTED,
            "aliases": None if not NESTED else {
                "table": f"0x{UI_CODE + syms['ui_aliases']:08X}",
                "strings": [{"index": k, "text": text or PLAN_TARGET["label"],
                             "address": f"0x{UI_CODE + syms['ui_aliases'] + 4 * k:08X}"}
                            for k, text in ALIAS_STRINGS],
            },
            "code_address": f"0x{UI_CODE:08X}",
            "code_bytes": len(code),
            "code_sha256": hashlib.sha256(code).hexdigest(),
            "state_address": f"0x{UI_STATE:08X}",
            "state_bytes": UI_STATE_BYTES,
            "state_layout": {
                "resource_context": "+0x00 u32",
                "pack_status": "+0x04 u32 (0 new, 1 ready, 2 loading, 3 failed)",
                "pack_native_result": "+0x08 u32",
                "post_install_stock_records": "+0x0C u32",
                "exact_copy_calls": "+0x10 u32",
                "last_stock_record_address": "+0x14 u32",
                "unique_exact_hit_bitmap": (
                    f"+0x{UI_HIT_BITMAP_OFFSET:02X}, {UI_HIT_BITMAP_BYTES} bytes, "
                    "one bit per sorted record"
                ),
            },
            "pack_address": f"0x{UI_PACK:08X}",
            "pack_bytes": len(pack),
            "pack_sha256": hashlib.sha256(pack).hexdigest(),
            "records": table_info,
            "selection": selection,
            "assets": asset_rows,
            "hooks": [
                {"address": f"0x{site:08X}", "stock": f"0x{expected:08X}",
                 "entry": label, "target": f"0x{UI_CODE + (syms[label] & ~1):08X}",
                 "original": (
                     f"0x{UI_CODE + (syms[f'{label}_original'] & ~1):08X}"
                 )}
                for site, expected, label, _ in THUMB_HOOKS
            ],
        },
        "package": {
            "autorun_commands": len(commands),
            "autorun_sha256": hashlib.sha256((out / "AutoRun.txt").read_bytes()).hexdigest(),
            "vshl_sections": count,
            "vshl_used_bytes": 16 + count * 8 + body_bytes,
            "vshl_sha256": hashlib.sha256(binary).hexdigest(),
            "stage2_cache_sync": {
                "when": "after every VSHL section has been placed and before entry",
                "sequence": [
                    "D-cache clean/invalidate",
                    "whole I-cache invalidate",
                ],
            },
        },
        "validation": {
            "stock_record_bytes": "all 360 source records match the pinned firmware",
            "write_order": (
                "all payload/data/state sections precede every hook section; UI string "
                "and loader hooks precede the NBU record hook, which is armed last"
            ),
            "loader_cache_sync": (
                "stage2 completes all section writes, then performs D-cache clean/"
                "invalidate followed by whole I-cache invalidate before entry"
            ),
            "private_resources": "NBR structure and all three XCI decodes checked offline",
            "timing_gate": (
                "same-firmware v0.3.2 is a hardware precedent, not a timing guarantee; "
                "decode the unique exact-hit bitmap after opening each target screen"
            ),
            "runtime_ownership": {
                "ranges": [
                    f"0x{UI_STATE:08X}..0x{UI_STATE + UI_STATE_BYTES:08X} state",
                    f"0x{UI_CODE:08X}..0x{UI_CODE + len(code):08X} resident code",
                    f"0x{UI_PACK:08X}..0x{UI_PACK + len(pack):08X} private NBR",
                ],
                "incompatible_diagnostics": list(INCOMPATIBLE_DIAGNOSTICS),
                "safe_draw_measurement": "firmware built-in `gui image log`",
                "safe_screen_capture": "firmware built-in `display capture`",
            },
            "runtime_cave": (
                "0xC0793060 pack range is zero in the firmware image; the connected-camera "
                "preboot gate also found all 933 words zero in standby, Quick Set, and menu"
            ),
            "camera": (
                "hardware results are intentionally external to the reproducible build; "
                "see ui_runtime_candidate/camera_postboot/MANIFEST.md"
            ),
        },
    }
    if not FPS_HOOKS:
        # 這幾個欄位是 OG3K 的相機結果與 mode98 專屬的 runtime 條件。
        # 角度修正沒武裝時它們一個字都不成立,整組拿掉而不是留著誤導。
        for key in ("scope", "previous_hardware_result", "revised_hardware_result",
                    "runtime_source", "stock_getter_called_first",
                    "unknown_or_mixed_timing",
                    "mode98_timing_restored_when_resolution_leaves_og3k"):
            manifest["angle_fps_fix"].pop(key, None)
    if release:
        manifest["package"].update({
            "flavor": "release",
            "banner": banner,
            "usb_shell": False,
        })
    (out / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n")
    readme = (
        "# OG3K native UI runtime candidate\n\n"
        "This package is coupled OpenGate test material, not a product release.  It adds "
        "the OG3K Settings summary, both Quick Set resolution animation families, and the "
        "UHD/FHD/OG3K footer using a private NBR pack.  It does not modify stock icons or "
        "the HUD Resolution family.\n\n"
        "The parser-copy mechanism was camera-proven in archived FP3K v0.3.2 on the same "
        "firmware, but that proves only the timing of that package.  Because the current "
        "AutoRun is slower, this build records one persistent hit bit for every selected "
        "NBU record; a ready private pack alone is not evidence that an already-parsed "
        "screen was repaired.  A full cold-boot camera run validated the unchanged native "
        "CINE Settings summary/list, both Quick Set OG3K values, and the three-choice "
        "footer in v0.2.0test.  That predecessor also exercised one FHD transition plus three one-second "
        "UHD and three one-second OG3K recording transitions without a freeze, then "
        "revalidated the OG3K Quick Set assets.  Separately, the previous "
        "single-callsite shutter-angle fix failed a confirmed real-mode idle-live-view "
        "comparison: FHD reported 16663 us while OG3K reported 6411 us with gain "
        "unchanged.  The revised fix now covers all four local angle conversion, "
        "metadata, and resolution-sync BL callsites through one narrow wrapper.  After "
        "a battery-out cold boot, its 29.97/180-degree real FHD/OG3K live-view A/B "
        "received a provisional visual pass; exact shell readback and all other frame "
        "rates remain pending.  Stage2 places every section before cleaning/invalidating D-cache and "
        "then invalidating the whole I-cache, so armed branches cannot retain the old "
        "instruction stream. "
        "A CINE/STILL transition while OG3K remains selected is also hardware-pending; "
        "select FHD or UHD before leaving CINE until that transition is tested. "
        "Warm restart and hot reinstall are neither tested nor supported; use only a "
        "battery-out cold boot baseline.  The historical 2026-09-14 A001_082 freeze "
        "remains unexplained and is not the user-corrected freeze from this work.  "
        "Separately, current SD throughput is inadequate for sustained UHD/OG3K "
        "validation.  See the historical sibling evidence at "
        "`../ui_runtime_candidate/camera_postboot/MANIFEST.md` and "
        "`../ui_runtime_candidate/camera_freeze_20260914/MANIFEST.md`.  "
        "Inactive screen/style variants, "
        "playback, and faster-media duration regressions remain untested.  "
        "Do not run size_ctl, cfgring, cfgsnap, appendobs, elemobs, xcitrace, the 0xC0733400 "
        "log family, zoomlog, og3ktile, or livepatch while it is resident: those diagnostics "
        "overlap its state/code ranges.  The firmware's built-in `gui image log` and "
        "`display capture` are safe.\n\n"
        f"A fresh 0x{UI_STATE:08X}..0x{UI_STATE + UI_STATE_BYTES:08X} dump can be "
        "decoded locally with `python3 ../decode_og3k_ui_state.py STATE.BIN --summary`. "
        "Acquiring that camera dump is a separate memory read and requires explicit "
        "per-read consent.\n\n"
        "Any fresh installation still requires proving the runtime stability of "
        f"0x{UI_PACK:08X}..0x{UI_PACK + len(pack):08X}, followed by a real battery-out "
        "cold boot.  Measure only the second QS draw because the first can contain the "
        "previous frame's assets.\n"
    )
    if release:
        readme = (
            "# OG3K native UI release test package\n\n"
            "This package contains the same OpenGate core, 360-record native UI payload, "
            "private NBR pack, and three UI hooks as its paired debug candidate. The UI "
            "payload is camera-tested.  The previous single-callsite shutter-angle fix "
            "failed a confirmed real FHD/OG3K idle-live-view comparison (16663 us versus "
            "6411 us, with gain unchanged).  The revised core fix covers four local BL "
            "callsites.  After a battery-out cold boot, its real FHD/OG3K 29.97/180-degree "
            "idle-live-view A/B received a provisional visual pass; exact shell readback "
            "and all other frame rates remain pending.  Stage2 places all sections, then cleans/invalidates D-cache and "
            "invalidates the whole I-cache before entry. "
            "It is built with `--no-shell`: no USB worker, USB interface/endpoint patches, "
            "or worker state block remains resident.  It is still an alpha release and must "
            "pass the remaining angle rates, faster-media duration, playback, and inactive UHD/FHD regressions before "
            "promotion.  A CINE/STILL transition while OG3K remains selected is not yet "
            "validated; select FHD or UHD before leaving CINE until it is tested.  Warm "
            "restart and hot reinstall are not supported; begin only from a battery-out "
            "cold boot.\n\n"
            "Install only `AutoRun.txt` and `fpSup.BIN` at the card root, then perform a "
            "battery-out cold boot.  Removing or renaming `AutoRun.txt` followed by another "
            "complete cold boot restores stock firmware behavior.\n"
        )
    if PLAN_TARGET["label"] != "OG3K":
        readme = _foreign_readme(PLAN_TARGET["label"], release, len(pack))
    (out / "README.md").write_text(readme)
    return manifest


# README 原本是一整段寫死的 OG3K 證據表 —— 裡面有「OG3K 錄影轉場實測過」、
# 「四顆快門角度 callsite 的修正」這一類**只對 OG3K 成立**的敘述。其他目標
# 沿用它,等於把別張卡的實測歷史掛在一張沒上過機的卡上。
# OG3K 走原本那段(逐位元不變),其餘目標走這裡。
def _foreign_readme(label: str, release: bool, pack_bytes: int) -> str:
    facts = {
        "HSW": (
            "HSW records CinemaDNG from sensor mode 12 `MONIT1_240`: a 2016x672 "
            "raster read at a stock 330/330/910 timing, which is exactly "
            "239.760240 fps with a 3.080 ms rolling shutter.  The 3x6 reduction is "
            "asymmetric, so the field is the full 3:2 frame but the pixels are "
            "squeezed 2:1 vertically; footage must be stretched 2x vertically in "
            "post (2000x662 -> 2000x1324).  Nothing in the sensor timing is "
            "modified: the words written to mode 12's timing record are its own "
            "stock words, and its stock nominal-FPS metadata is already the true "
            "240, so the shutter-angle wrapper is not armed at all.\n\n"
            "The menu frame rate is the container rate, not the sensor rate.  All "
            "ten format rows drive the sensor at 239.76 fps.  Whether the writer "
            "follows VSYNC (giving 2x to 10x slow motion) or the frame-rate timer "
            "(giving a normal-rate clip with a 1/240 shutter ceiling) is the first "
            "thing a camera run has to measure: record about one second and count "
            "the frames.\n\n"
            "Data rate at 239.76 fps is 317 MB/s at 8-bit, 397 MB/s at 10-bit and "
            "476 MB/s at 12-bit.  Stock UHD 12-bit is 376 MB/s, so only the 8-bit "
            "case is below anything the camera is known to sustain.\n\n"
            "Known edges: the 239.76 row is enabled in all six frame-rate list "
            "variants, so selecting it with UHD or FHD builds a key no table "
            "carries and the firmware falls back to UHD30 - change the frame rate "
            "back to recover.  The frame-rate enum/row pair table at 0xC2E44EE4 "
            "has exactly nine entries and no spare, which is unresolved; if the "
            "enum that arrives is not 11 nothing fires and the camera keeps stock "
            "behaviour.\n\n"
        ),
    }.get(label, "")
    status = (
        "**This target has never been run on a camera.**  Every statement above "
        "is derived from the firmware image and the offline verifiers.\n\n"
        if label == "HSW" else
        f"This README makes no camera claim for {label}.  See the project notes "
        f"for whatever hardware evidence that target has.\n\n"
    )
    kind = "release test package" if release else "runtime candidate"
    return (
        f"# {label} native UI {kind}\n\n"
        f"This package is coupled OpenGate test material, not a product release.  "
        f"It carries the same 360-record native UI payload, private NBR pack and "
        f"three UI hooks as the OG3K package, with {label} drawn into the three "
        f"private tiles.  The resource names inside the pack stay OG3K_QS / "
        f"OG3K_SET / OG3K_FONT because the stock UI records look them up by name; "
        f"only the drawn glyphs are target-dependent.\n\n"
        + facts + status +
        "The UI parser-copy mechanism itself was camera-proven for OG3K on this "
        "firmware; that proves the mechanism, not this target.\n\n"
        "Warm restart and hot reinstall are neither tested nor supported; begin "
        "only from a battery-out cold boot.  Do not run size_ctl, cfgring, "
        "cfgsnap, appendobs, elemobs, xcitrace, the 0xC0733400 log family, "
        "zoomlog, og3ktile, or livepatch while it is resident: those diagnostics "
        "overlap its state/code ranges.  The firmware's built-in `gui image log` "
        "and `display capture` are safe.\n\n"
        "Install only `AutoRun.txt` and `fpSup.BIN` at the card root, then "
        "perform a battery-out cold boot.  Removing or renaming `AutoRun.txt` "
        "followed by another complete cold boot restores stock firmware "
        "behaviour.\n"
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the OpenGate native OG3K UI debug or release package."
    )
    parser.add_argument(
        "--release",
        action="store_true",
        help="omit the USB shell worker, endpoint/interface patches, and worker state",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help=(f"output directory (debug default: {DEFAULT_OUT}; "
              f"release default: {DEFAULT_RELEASE_OUT})"),
    )
    parser.add_argument(
        "--ui-diag",
        action="store_true",
        help="debug only: capture the caller chain of the first target NBU hits",
    )
    parser.add_argument(
        "--banner",
        default=DEFAULT_BANNER,
        help=f"camera completion banner (default: {DEFAULT_BANNER})",
    )
    args = parser.parse_args(argv)
    if args.out is None:
        args.out = DEFAULT_RELEASE_OUT if args.release else DEFAULT_OUT
    return args


if __name__ == "__main__":
    args = parse_args()
    result = build(out=args.out, banner=args.banner, release=args.release,
                   ui_diag=args.ui_diag)
    print(json.dumps({
        "status": result["status"],
        "ui_records": result["ui"]["records"]["records"],
        "ui_code_bytes": result["ui"]["code_bytes"],
        "ui_pack_bytes": result["ui"]["pack_bytes"],
        "vshl_used_bytes": result["package"]["vshl_used_bytes"],
        "output": str(args.out),
    }, indent=2))
