#!/usr/bin/env python3
"""Verify a shell-free OG3K UI release against its paired debug build.

The release is allowed to differ only where ``build_autorun.py --no-shell``
requires it to differ: its AutoRun loader has no USB interface/endpoint patches
or worker state, its VSHL has no worker section, and its VSHL entry is og3krestore
(zero when OG_FMT_GUARD=0).
Every OpenGate and UI word must remain byte-identical to the debug candidate.
The UI sidecars are pinned per target (see EXPECTED_UI for what was camera-tested).
The revised angle/FPS core has a provisional 29.97/180-degree visual pass after
a battery-out cold boot; exact readback and the other frame rates remain pending.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import sys


HERE = Path(__file__).resolve().parent
DEFAULT_OUT = HERE / "fpsup-og3k-v0.2.2a-staging"
DEFAULT_CANDIDATE = HERE / "og3k_bitdepth_candidate"

WORKER_START = 0xC072F050
WORKER_END = 0xC072F700
WORKER_STATE_SITES = set(range(0xC072F000, 0xC072F044, 4))
USB_INTERFACE_PATCH_SITES = {
    0xC0CF3740,
    0xC0CF3758,
    0xC0CF375C,
    0xC0CF3780,
    0xC0CF3784,
    0xC0CF3798,
    0xC0CF379C,
}
UI_HOOK_SITES = (0xC05E5B58, 0xC05E84D8, 0xC05E6400, 0xC05D90F0)
# UI payload 的雜湊按**目標**釘:pin 的用意是「出貨的一定是實機測過的那份」,
# 而每個目標有自己測過的那一份。2026-09-15 OG2K 加入。
EXPECTED_UI = {
    # 2026-09-24:加入第 4 個 hook ui_layout(0xC05D90F0,提早開 QS 的修正),
    # UI 程式碼因此改變;兩個 NBR 不變。
    # OG2K:與 og2k-debug-qsfix2 卡(OG2K-QsFix2!)上實測的 OG3KUI.BIN 逐位元組相同。
    # OG3K:同一份程式碼,只差摘要字串 "OG3K";這一份本身**沒有**在 OG3K 上實測。
    # 舊值(v0.2.0test 起的 OG3K c8b7bb73…、OG2K cefc34b3…)見 git 前的 build 紀錄。
    "OG3K": ("564da5ab597bd84a74606de6a4fbd0a206eadc8dd2141831f85fc377fec5cefd",
             "c199170c0701d2f26520f89cd90b0731e552452f1f8bedd9e772b157ca50fe05"),
    "OG2K": ("6cc03e385ab2567b4960b2265fa82081912caa8d504f0ab69cb40742b6f8cf7f",
             "9d840d2c4b1b56404650a48aeabe6f1a5f873529e75156757e59f55143801361"),
}
import os as _os
_LABEL = _os.environ.get("OG_TARGET", "og3k").upper()
if _LABEL not in EXPECTED_UI:
    raise SystemExit(f"{_LABEL} 還沒有已核可的 UI 雜湊 —— 新目標的第一張卡"
                     f"必須先人工檢視 assets/ 再把雜湊登記進 EXPECTED_UI")
EXPECTED_UI_CODE_SHA256, EXPECTED_UI_NBR_SHA256 = EXPECTED_UI[_LABEL]
# Either payload name: a release published before 2026-09-19 carries
# VSHL.BIN, a build made after it carries fpSup.BIN.
SHIPPING_FILES = frozenset({
    "AutoRun.txt",
    "VSHL.BIN",
    "fpSup.BIN",
    "README.txt",
    "MANIFEST.txt",
})
RELEASE_SIDECARS = ("MANIFEST.json", "OG3KUI.BIN", "OG3KUI.NBR")
# 每個目標自己的「未驗證邊界」句子。pin 的用意是逼 MANIFEST 講清楚
# 哪些沒測過,所以目標不同,要求的句子也不同。
SHIPPING_BOUNDARY_BY_LABEL = {
    "OG2K": (
        "高光餘裕 / gain_state:og3kgs 對 mode 139 的行為未測",
        "沒有做過任何格率的實機快門讀值",
        "但沒有做過長時間錄影",
        "熱重開與 hot reinstall 未驗證且不支援",
        "這對檔案本身沒有另做冷開機實測",
    ),
}
SHIPPING_BOUNDARY_FRAGMENTS = (
    "8/10-bit 的機內回放未驗證",
    "8/10-bit 的高光餘裕未驗證",
    "29.97/180° 冷開機目視通過，其他幀率待驗證",
    "當時 USB 未連線，因此尚無精確 shutter readback。",
    "23.976/24/25/48/50/59.94/100 的 idle 實機驗證仍未完成",
    "精確 no-shell 出貨 pair 還需一次實機冷開 smoke test。",
    "熱重開與 hot reinstall 未驗證且不支援",
)

sys.path.insert(0, str(HERE))
from og3k_plan import (EXPECTED_PLAN_WORDS, Plan, RESTORE_CODE,  # noqa: E402
                       WITH_FMTGUARD)


class VerificationError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationError(message)


def sha256(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def parse_vshl(path: Path) -> dict:
    blob = path.read_bytes()
    require(len(blob) >= 16, f"{path} is shorter than the VSHL header")
    magic, count, entry, body_bytes = struct.unpack_from("<4sIII", blob)
    require(magic == b"VBIN", f"{path} has bad VSHL magic {magic!r}")
    table_end = 16 + count * 8
    require(table_end <= len(blob), f"{path} has a truncated section table")

    sections = []
    section_map = {}
    offset = table_end
    for index in range(count):
        destination, length = struct.unpack_from("<II", blob, 16 + index * 8)
        require(length % 4 == 0, f"section 0x{destination:08X} is not word aligned")
        payload = blob[offset:offset + length]
        require(len(payload) == length, f"section 0x{destination:08X} is truncated")
        sections.append((destination, payload))
        # 位址 0 是「放在檔案裡原地執行」的段(worker bootstrap、entries.S
        # trampoline),可以不只一段;只有真的目的位址才要求唯一。
        if destination:
            require(destination not in section_map,
                    f"duplicate section 0x{destination:08X}")
            section_map[destination] = payload
        offset += length + (-length % 4)

    used = table_end + body_bytes
    require(offset == used, f"{path} body length disagrees with its section table")
    require(used <= len(blob), f"{path} declares data beyond end of file")
    require(not any(blob[used:]), f"{path} has non-zero bytes after its declared body")

    words = {}
    for destination, payload in sections:
        if destination < 0x40000000:
            continue
        for inner in range(0, len(payload), 4):
            address = destination + inner
            require(address not in words, f"overlapping word at 0x{address:08X}")
            words[address] = struct.unpack_from("<I", payload, inner)[0]
    return {
        "blob": blob,
        "entry": entry,
        "body_bytes": body_bytes,
        "used_bytes": used,
        "sections": sections,
        "section_map": section_map,
        "words": words,
    }


def autorun_mem_set_sites(path: Path) -> set[int]:
    sites = set()
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        fields = line.split()
        if len(fields) >= 4 and fields[:2] == ["mem", "set"]:
            sites.add(int(fields[2], 0))
    return sites


def autorun_command_count(text: str) -> int:
    return sum(
        1 for raw in text.splitlines()
        if raw.strip() and not raw.lstrip().startswith("#")
    )


def section_at(parsed: dict, address: int, label: str) -> bytes:
    payload = parsed["section_map"].get(address)
    require(payload is not None, f"missing {label} section at 0x{address:08X}")
    return payload


def _payload(d: Path) -> Path:
    """fpSup.BIN for anything built after 2026-09-19, VSHL.BIN before it."""
    for name in ("fpSup.BIN", "VSHL.BIN"):
        if (d / name).is_file():
            return d / name
    return d / "fpSup.BIN"


def verify(out: Path, candidate: Path) -> dict:
    out = out.resolve()
    candidate = candidate.resolve()
    release_autorun = out / "AutoRun.txt"
    release_vshl = _payload(out)
    candidate_autorun = candidate / "AutoRun.txt"
    candidate_vshl = _payload(candidate)
    for path in (release_autorun, release_vshl, candidate_autorun, candidate_vshl,
                 candidate / "MANIFEST.json", candidate / "OG3KUI.BIN",
                 candidate / "OG3KUI.NBR"):
        require(path.is_file(), f"missing required file: {path}")

    release_sidecar_paths = tuple(out / name for name in RELEASE_SIDECARS)
    sidecar_presence = tuple(path.is_file() for path in release_sidecar_paths)
    require(all(sidecar_presence) or not any(sidecar_presence),
            "release has a partial sidecar/JSON set; expected all or none: "
            + ", ".join(RELEASE_SIDECARS))
    has_release_sidecars = all(sidecar_presence)

    release = parse_vshl(release_vshl)
    debug = parse_vshl(candidate_vshl)
    manifest = json.loads((candidate / "MANIFEST.json").read_text())
    candidate_package = manifest["package"]
    require(sha256(candidate_autorun.read_bytes()) == candidate_package["autorun_sha256"],
            "debug AutoRun disagrees with its manifest")
    require(sha256(debug["blob"]) == candidate_package["vshl_sha256"],
            "debug VSHL disagrees with its manifest")
    require(candidate_package["vshl_sections"] == len(debug["sections"]),
            "debug section count disagrees with its manifest")
    require(candidate_package["vshl_used_bytes"] == debug["used_bytes"],
            "debug used-byte count disagrees with its manifest")
    # 2026-09-23:og3krestore 改由 VSHL entry 呼叫。release 只有它一個 entry;
    # debug 另有 USB worker,header 指向 entries.S trampoline,表以 restore 結尾。
    if WITH_FMTGUARD:
        require(release["entry"] == RESTORE_CODE,
                f"release VSHL entry 0x{release['entry']:08X} is not og3krestore")
        require(0 < debug["entry"] < 0x40000000
                and debug["blob"].find(struct.pack("<II", RESTORE_CODE, 0),
                                       debug["entry"]) >= 0,
                "debug trampoline does not end its entry table with og3krestore")
    else:
        require(release["entry"] == 0, "release VSHL entry is not zero")
        require(debug["entry"] != 0, "debug candidate unexpectedly has no worker entry")
    for name, autorun in (("release", release_autorun), ("debug", candidate_autorun)):
        require(f"0x{RESTORE_CODE:08X}" not in autorun.read_text(),
                f"{name} AutoRun still calls og3krestore through the echo slot")

    # USB patch 與 worker state 早期是 AutoRun 的 mem set,現在 build_autorun.py
    # 把它們放進 VSHL 的 section。兩處都算,否則 debug 永遠「找不到」、release
    # 的殘留也看不見。
    release_sites = autorun_mem_set_sites(release_autorun) | set(release["words"])
    debug_sites = autorun_mem_set_sites(candidate_autorun) | set(debug["words"])
    forbidden_sites = USB_INTERFACE_PATCH_SITES | WORKER_STATE_SITES
    leaked = sorted(release_sites & forbidden_sites)
    require(not leaked, "release AutoRun retains USB shell sites: "
            + ", ".join(f"0x{site:08X}" for site in leaked))
    require(USB_INTERFACE_PATCH_SITES <= debug_sites,
            "debug candidate no longer contains the expected USB interface patches")
    require(WORKER_STATE_SITES <= debug_sites,
            "debug candidate no longer clears the expected worker state")

    release_worker_sections = [
        address for address, payload in release["sections"]
        if address >= 0x40000000
        and address < WORKER_END
        and address + len(payload) > WORKER_START
    ]
    require(not release_worker_sections, "release VSHL retains a USB worker section")
    # worker 早期固定放在 WORKER_START;現在是位址 0 的原地段,自己配置 pool。
    require(WORKER_START in debug["section_map"]
            or any(address == 0 for address, _ in debug["sections"]),
            "debug candidate has no USB worker section")

    # 位址 0 是原地執行的段:兩邊都有 stage2;debug 另有 worker bootstrap,
    # 多入口時還有 entries.S trampoline。release 的每一段位址 0 都必須與
    # debug 的某一段逐位元相同,其餘段除了 worker 之外必須完全一致。
    debug_inplace = [payload for address, payload in debug["sections"] if address == 0]
    require(all(payload in debug_inplace
                for address, payload in release["sections"] if address == 0),
            "release VSHL has an in-file section the debug candidate does not")
    expected_release_sections = [
        section for section in debug["sections"]
        if section[0] not in {WORKER_START, 0, min(WORKER_STATE_SITES)}
        and section[0] not in USB_INTERFACE_PATCH_SITES
    ]
    require([section for section in release["sections"] if section[0] != 0]
            == expected_release_sections,
            "release VSHL differs from debug candidate by more than the worker section")

    base_items = list(Plan().all())
    require(len(base_items) == EXPECTED_PLAN_WORDS,
            f"OpenGate plan has {len(base_items)} words; "
            f"expected {EXPECTED_PLAN_WORDS}")
    require(len({address for address, _, _ in base_items}) == len(base_items),
            "OpenGate plan contains duplicate write addresses")
    for address, value, _ in base_items:
        require(release["words"].get(address) == value,
                f"release OpenGate word differs at 0x{address:08X}")
        require(debug["words"].get(address) == value,
                f"debug candidate OpenGate word differs at 0x{address:08X}")

    ui = manifest["ui"]
    require(ui["records"]["records"] == 360,
            f"debug candidate has {ui['records']['records']} UI records, expected 360")
    require(manifest["base_opengate_writes"] == EXPECTED_PLAN_WORDS,
            "debug manifest does not identify the current OpenGate core")

    code_address = int(ui["code_address"], 16)
    state_address = int(ui["state_address"], 16)
    pack_address = int(ui["pack_address"], 16)
    code_file = (candidate / "OG3KUI.BIN").read_bytes()
    pack_file = (candidate / "OG3KUI.NBR").read_bytes()
    require(sha256(code_file) == EXPECTED_UI_CODE_SHA256,
            "debug UI code is not the camera-tested payload")
    require(sha256(pack_file) == EXPECTED_UI_NBR_SHA256,
            "debug UI NBR is not the camera-tested payload")
    if has_release_sidecars:
        require((out / "OG3KUI.BIN").read_bytes() == code_file,
                "release OG3KUI.BIN differs from debug candidate")
        require((out / "OG3KUI.NBR").read_bytes() == pack_file,
                "release OG3KUI.NBR differs from debug candidate")
    require(sha256(code_file) == ui["code_sha256"],
            "debug OG3KUI.BIN disagrees with its manifest")
    require(sha256(pack_file) == ui["pack_sha256"],
            "debug OG3KUI.NBR disagrees with its manifest")

    for address, sidecar, label in (
        (code_address, code_file, "UI code"),
        (pack_address, pack_file, "UI NBR"),
    ):
        debug_payload = section_at(debug, address, label)
        release_payload = section_at(release, address, label)
        require(debug_payload == sidecar, f"debug {label} section differs from sidecar")
        require(release_payload == debug_payload,
                f"release {label} section differs from debug candidate")

    debug_state = section_at(debug, state_address, "UI state")
    release_state = section_at(release, state_address, "UI state")
    require(len(debug_state) == ui["state_bytes"], "debug UI state has wrong size")
    require(debug_state == bytes(ui["state_bytes"]), "debug UI state is not zero-filled")
    require(release_state == debug_state, "release UI state differs from debug candidate")

    hook_sites = tuple(int(row["address"], 16) for row in ui["hooks"])
    require(hook_sites == UI_HOOK_SITES,
            "debug manifest UI hook order/sites changed unexpectedly")
    for site in UI_HOOK_SITES:
        debug_hook = section_at(debug, site, "UI hook")
        release_hook = section_at(release, site, "UI hook")
        require(len(debug_hook) == 4, f"debug hook 0x{site:08X} is not one word")
        require(release_hook == debug_hook,
                f"release UI hook differs at 0x{site:08X}")

    release_autorun_blob = release_autorun.read_bytes()
    release_autorun_text = release_autorun_blob.decode()
    release_autorun_sha = sha256(release_autorun_blob)
    release_vshl_sha = sha256(release["blob"])
    release_commands = autorun_command_count(release_autorun_text)

    if has_release_sidecars:
        release_manifest_path = out / "MANIFEST.json"
        release_manifest = json.loads(release_manifest_path.read_text())
        require(release_manifest["package"].get("flavor") == "release",
                "release manifest has no release flavor marker")
        require(release_manifest["package"].get("usb_shell") is False,
                "release manifest does not mark the USB shell absent")
        require(release_manifest["base_opengate_writes"] == EXPECTED_PLAN_WORDS,
                "release manifest does not identify the current OpenGate core")
        require(release_manifest["ui"] == ui,
                "release UI manifest differs from the paired debug candidate")
        require(release_manifest["package"]["vshl_sections"] == len(release["sections"]),
                "release section count disagrees with its manifest")
        require(release_manifest["package"]["vshl_used_bytes"] == release["used_bytes"],
                "release used-byte count disagrees with its manifest")
        require(release_manifest["package"]["vshl_sha256"] == release_vshl_sha,
                "release VSHL hash disagrees with its manifest")
        require(release_manifest["package"]["autorun_sha256"] == release_autorun_sha,
                "release AutoRun hash disagrees with its manifest")
        banner = release_manifest["package"]["banner"]
        package_shape = "staging-with-sidecars"
    else:
        entries = {path.name for path in out.iterdir()}
        require(entries == SHIPPING_FILES,
                "shipping package must contain exactly four files; got: "
                + ", ".join(sorted(entries)))
        require(all((out / name).is_file() for name in SHIPPING_FILES),
                "shipping package entries must all be regular files")

        text_manifest = (out / "MANIFEST.txt").read_text()
        manifest_lines = text_manifest.splitlines()
        normalized_manifest = " ".join(text_manifest.split())

        def require_manifest_line(pattern: str, label: str) -> None:
            require(any(re.fullmatch(pattern, line) for line in manifest_lines),
                    f"shipping MANIFEST.txt has no exact {label} line")

        require_manifest_line(
            rf"AutoRun\.txt\s+{len(release_autorun_blob):,}B\s+sha256={release_autorun_sha}",
            "AutoRun size/hash",
        )
        require_manifest_line(
            rf"VSHL\.BIN\s+{len(release['blob']):,}B\s+sha256={release_vshl_sha}",
            "VSHL size/hash",
        )
        expected_manifest_fragments = (
            f"AutoRun 指令 {release_commands} 條",
            f"{_LABEL} 的 {len(release['words'])} 筆寫入",
            f"VSHL sections: {len(release['sections'])}",
            f"VSHL body bytes: {release['body_bytes']:,}",
            ("VSHL used bytes including header/table: "
             f"{release['used_bytes']:,} of {len(release['blob']):,}"),
            f"VSHL entry: 0x{release['entry']:08X}",
            "USB shell: absent",
            (f"OpenGate core {len(base_items)} words; native UI "
             f"{len(release['words']) - len(base_items)} words, "
             f"{ui['records']['records']} selected NBU records, "
             f"{len(UI_HOOK_SITES)} hooks."),
        ) + SHIPPING_BOUNDARY_BY_LABEL.get(_LABEL, SHIPPING_BOUNDARY_FRAGMENTS)
        for fragment in expected_manifest_fragments:
            require(fragment in normalized_manifest,
                    f"shipping MANIFEST.txt is missing exact fact/boundary: {fragment}")

        banner_rows = [
            line.partition(":")[2].strip()
            for line in manifest_lines
            if line.startswith("banner:")
        ]
        require(len(banner_rows) == 1 and banner_rows[0],
                "shipping MANIFEST.txt must contain exactly one non-empty banner line")
        banner = banner_rows[0]
        package_shape = "shipping-four-file"

    banner_line = f"display text {banner}"
    require(release_autorun.read_text().splitlines().count(banner_line) == 3,
            "release completion banner is not emitted to all three OSD buffers")

    return {
        "status": "PASS (release is paired debug build minus USB shell only)",
        "package_shape": package_shape,
        "release": str(out),
        "candidate": str(candidate),
        "release_autorun_sha256": release_autorun_sha,
        "release_vshl_sha256": release_vshl_sha,
        "release_vshl_entry": f"0x{release['entry']:08X}",
        "release_vshl_sections": len(release["sections"]),
        "debug_vshl_sections": len(debug["sections"]),
        "removed_worker_section": f"0x{WORKER_START:08X}",
        "opengate_words": len(base_items),
        "ui_records": ui["records"]["records"],
        "ui_code_sha256": sha256(code_file),
        "ui_nbr_sha256": sha256(pack_file),
        "ui_state_bytes": len(release_state),
        "ui_hooks": [f"0x{site:08X}" for site in UI_HOOK_SITES],
        "usb_shell_autorun_sites": 0,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
        help=f"release package directory (default: {DEFAULT_OUT})",
    )
    parser.add_argument(
        "--candidate",
        type=Path,
        default=DEFAULT_CANDIDATE,
        help=f"paired debug package directory (default: {DEFAULT_CANDIDATE})",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = verify(args.out, args.candidate)
    except (OSError, KeyError, ValueError, VerificationError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
