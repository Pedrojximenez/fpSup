#!/usr/bin/env python3
"""OG3K + gyro logger + USB shell,一張卡。

AutoRun.txt 只寫那個 loader(約 130 條 mem set),其餘全部走 \\fpSup.BIN ——
指令數不再隨內容成長,未來加模式是免費的。

錄影 core 來自 og3k_plan；原生 Settings/QS UI 與純 OG3K 產品共用
build_og3k_ui_candidate.py 的 360-record section source，所以純 OG3K、
gyro merge reference 與實機測試版不會分歧。

    ./build_og3k_gyro.py --no-gyro --release   只有 OG3K
    ./build_og3k_gyro.py --reference --out DIR  合成器的暫存驗證基準
"""
import hashlib, json, os, pathlib, shutil, struct, subprocess, sys, tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from og3k_plan import Plan, HOOKS, RESTORE_CODE


def _payload(d):
    """The card's payload container in <d>.

    A build writes fpSup.BIN; every release published before 2026-09-19 carries
    VSHL.BIN as frozen bytes.  Writing is one name, reading is two.
    """
    for name in ("fpSup.BIN", "VSHL.BIN"):
        if (d / name).is_file():
            return d / name
    return d / "fpSup.BIN"


ROOT  = HERE.parent.parent.parent     # projects/open-gate/build -> SIGMA_re
SHELL = ROOT / "fpSup" / "fp_usb_shell" / "build_autorun.py"
UI_BUILDER = HERE / "build_og3k_ui_candidate.py"
GYRO  = ROOT / "fpSup" / "gyro"
CARD  = GYRO / "build_base_card.py"  # 出貨版 gyro 是這支建的,不是 build_card.py
TPL   = SHELL.parent / "asm"
OUT_DEV = HERE / "og3k_gyro"        # 純 OG3K debug；歷史預設路徑
# The banner is the only thing that tells the two open-gate builds apart once
# the card is in the camera: they place the same number of sections at the same
# addresses and their AutoRun files are byte-identical, because the AutoRun does
# not depend on the section list.  It said OG3K on both until 2026-09-19, which
# is the failure build_base_card.py's own comment warns about -- "which build is
# in there" being guessed at.
# Lower case is the tag and the directory -- releases/TAGS.md: the tag and the
# folder are the same string -- and upper case is the banner, which has said
# OG3K since the first card.  The two are not the same convention and neither
# follows the other.
# 2026-09-20:原本是 og2k/og3k 二選一,加第三張卡(hsw)時就會靜靜地把它
# 建成 OG3K。改成照 OG_TARGET 直接走,未知的名字寧可當場報錯。
_TARGET = os.environ.get("OG_TARGET", "og3k")
_LABEL = _TARGET.upper()
BANNER = f"fpSup-{_LABEL}-Gyro!"
# A version each.  They shared one constant, which meant an OG2K card announced
# whatever number OG3K had reached -- and they ship on their own schedules: og3k
# is at 0.2.x with three releases behind it, og2k is still on its first.
# hsw 是 2026-09-20 才有的第一版,還沒上過機。
# 2026-09-27:0.2.4a -> 0.2.7a / 0.1.1a -> 0.1.4a。
# 2026-10-03:0.2.8a / 0.1.5a —— 字串別名接受 fpSup/uishare 的共用字串池(FSPL),
# 才能跟 Lossless 合併。
# 中間的 0.2.5a/0.2.6a 與 0.1.2a/0.1.3a 是用 repack_release.py 切的,
# 沒回頭更新這個常數,所以它一直落後於 releases/ 裡實際存在的版本。
# **訂版本前先 git tag**(releases/TAGS.md);這次沒辦法照做 —— 這個工作目錄
# 不是 git repo,所以版號是照 releases/ 現有的資料夾往下接,由使用者確認。
VERSIONS = {"og3k": "0.2.8a", "og2k": "0.1.5a", "hsw": "0.1.0test"}
if _TARGET not in VERSIONS:
    # og6k 刻意不在這裡:它是給 HDMI RAW 的,不是給卡的(og3k_plan 的
    # TARGETS["og6k"] 檔頭)。先前這個腳本把任何不是 og2k 的名字都當成
    # og3k,於是 OG_TARGET=og6k 會靜靜地建出一張標著 OG3K 的卡。
    raise SystemExit(f"OG_TARGET={_TARGET!r} 沒有登記版本號 —— "
                     f"可用的是 {sorted(VERSIONS)}")
OG_VERSION = VERSIONS[_TARGET]
OUT_OG = HERE / f"fpsup-{_TARGET}-v{OG_VERSION}"   # 純 open gate,不含陀螺儀
BANNER_OG = f"fpSup-{_LABEL}-v{OG_VERSION}!"
VERSION = "og3k+gyro-v1.11b"
UI_RECORD_COUNT = 360

GYRO_AT, PARK_AT, F_WRITE_AT = 0xC072E064, 0xC072EFB4, 0xC03660E8
PGEN = GYRO / ".pgen.bin"      # 後處理(GYR → gcsv → JSON)的池映像


def ui_block(label, ui_manifest):
    """OpenGate's FPUI block: the resolution option (fpSup/uishare
    options.resolution) and, when the native UI was built with nested strings,
    its labels handed out into ui_aliases -- word 0 last, since og3k_ui.S arms
    on it (fpSup/uishare/NESTED_HOOKS.md)."""
    sys.path.insert(0, str(ROOT / "fpSup" / "uishare"))
    from ui import options as ui_options
    geometry = {"OG3K": "OG3K 3008x2000", "OG2K": "OG2K 2000x1334"}[label]
    block = ui_options.resolution(geometry, label)
    aliases = ui_manifest["ui"].get("aliases")
    if aliases:
        table = int(aliases["table"], 16)
        pairs = sorted(((s["text"], int(s["address"], 16)) for s in aliases["strings"]),
                       key=lambda p: p[1] == table)
        ui_options.hand_out(block, pairs)
    return block


def canonical_ui_sections(tmp):
    """Build once through the native-UI source of truth and return its sections.

    The generic loader owns the destination-zero helper section (and, for a
    debug card, the USB worker), so callers merge only the firmware-addressed
    OpenGate sections.  Building the source as ``--release`` keeps this
    extraction independent of whether the final card is plain or carries the
    shell.
    """
    out = tmp / "og3k_ui_source"
    cmd = [sys.executable, str(UI_BUILDER), "--release", "--out", str(out),
           "--banner", BANNER_OG]
    rc = subprocess.run(cmd).returncode
    if rc:
        raise SystemExit(f"native UI OG3K 建置器失敗:{rc}")

    manifest = json.loads((out / "MANIFEST.json").read_text(encoding="utf-8"))
    if manifest["ui"]["records"]["records"] != UI_RECORD_COUNT:
        raise SystemExit(
            f"native UI record 數變成 {manifest['ui']['records']['records']},"
            f"預期 {UI_RECORD_COUNT}")
    package = manifest["package"]
    if package.get("flavor") != "release" or package.get("usb_shell") is not False:
        raise SystemExit("native UI section source 不是 no-shell release flavor")

    blob = _payload(out).read_bytes()
    magic, count, entry, body_bytes = struct.unpack_from("<4sIII", blob)
    if magic != b"VBIN" or entry not in (0, RESTORE_CODE):
        raise SystemExit("native UI release VSHL header 不合預期")
    offset = 16 + count * 8
    sections, helper_sections = [], 0
    for index in range(count):
        destination, length = struct.unpack_from("<II", blob, 16 + index * 8)
        payload = blob[offset:offset + length]
        if len(payload) != length:
            raise SystemExit("native UI release VSHL 被截斷")
        offset += length + (-length % 4)
        if destination < 0x40000000:
            if destination != 0:
                raise SystemExit(
                    f"native UI source 有未預期的 pool section 0x{destination:08X}")
            helper_sections += 1
            continue
        if length % 4:
            raise SystemExit(
                f"native UI section 0x{destination:08X} 不是 word aligned")
        sections.append([
            (destination + inner, struct.unpack_from("<I", payload, inner)[0],
             "canonical OpenGate + native UI")
            for inner in range(0, length, 4)
        ])
    if helper_sections != 1 or len(sections) + 1 != count:
        raise SystemExit("native UI release VSHL helper section shape 改變")
    if offset != 16 + count * 8 + body_bytes or any(blob[offset:]):
        raise SystemExit("native UI release VSHL body/padding 不一致")
    return sections, manifest, blob


def main():
    no_gyro = "--no-gyro" in sys.argv
    release = "--release" in sys.argv
    dev_card = "--dev-card" in sys.argv
    fast = "--fast" in sys.argv
    reference = "--reference" in sys.argv or dev_card

    # 2026-09-13 政策:**合併版只在網頁上產生。**
    #
    # 這支腳本以前直接吐出 OG3K+gyro 的卡,而那正是「兩個來源悄悄分岔」的
    # 溫床 —— 卡片名稱裡有 gyro,裡面裝的卻不是出貨的那個 gyro,沒有人發現。
    # 現在合併交給 fpSup/tools/card-composer:它從出貨產物本身組,
    # 而且逐位元組驗證過 gyro+og3k 與這裡建出來的完全相同。
    #
    # 還留著 --reference 是因為目錄產生器需要一份「腳本建出來的合併卡」
    # 當比對基準。那是**驗證用的,不是拿去插相機的**。
    #
    # 2026-09-20 補:開發時確實需要把合併卡插進相機 —— 2026-09-19 那三張
    # 實機測試卡(trampoline、og3k+gyro+shell、og2k+gyro+shell)就是這樣建的,
    # 而當時網頁產不出來(目錄裡的 shell 卡落後兩代)。與其偷用 --reference,
    # 不如給那件事一個名字:**--dev-card**。位元組完全一樣,差別只在它會說
    # 自己是什麼,以及它跟使用者下載到的那張差在哪(見下面印出來的兩行)。
    # --out 讓 reference 只能建到呼叫者管理的暫存目錄。組合版不能以成品
    # 形式躺在樹裡；真正給使用者的組合一律由 fpSup-Merge 網頁產生。
    outarg = None
    if "--out" in sys.argv:
        outarg = pathlib.Path(sys.argv[sys.argv.index("--out") + 1])
    if not no_gyro and not reference:
        raise SystemExit(
            "合併版請用 fpSup/tools/card-composer/index.html 產生。\n"
            "  這支腳本現在只建純 OG3K:  ./build_og3k_gyro.py --no-gyro --release\n"
            "  目錄產生器要的暫存基準:    ./build_og3k_gyro.py --reference "
            "--out TMP [--release]\n"
            "  開發用、要插相機的合併卡:  ./build_og3k_gyro.py --dev-card "
            "--out DIR [--fast]")
    if fast and not dev_card:
        raise SystemExit(
            "--fast 只跟 --dev-card 一起用。快載入是「裝箱」這一層加的,不是"
            "「建一張卡」這一層 —— 出貨的合併卡走 fpSup-Merge 網頁,純 OG3K "
            "的發布卡本來就不該帶。")
    if reference and outarg is None:
        raise SystemExit(
            ("--dev-card" if dev_card else "--reference")
            + " 必須同時指定 --out DIR;組合版不能以成品形式躺在樹裡。")
    OUT = outarg or (OUT_OG if release else OUT_DEV)
    p = Plan()
    bad = p.check()
    if bad:
        for b in bad:
            print("  " + b)
        raise SystemExit("靜態檢查失敗")
    if getattr(p, "trial", None):
        f = ", ".join(f"+0x{o:03X}={v}" for o, v in sorted(p.trial.items()))
        raise SystemExit(f"rowpatch 含試驗中的預覽欄位({f})。"
                         "先解 DNG 確認錄影無損再建置。")

    core_items = list(p.all())
    OUT.mkdir(parents=True, exist_ok=True)
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="og3k-"))
    segs, ui_manifest, canonical_vshl = canonical_ui_sections(tmp)
    # The UI release may request restore after its sections are placed.  Keep
    # that entry when repackaging, including the entry-zero format-guard-off build.
    ui_entry = struct.unpack_from("<I", canonical_vshl, 8)[0]
    canonical_sidecars = {}
    if no_gyro and release:
        canonical_out = tmp / "og3k_ui_source"
        for relative in (
            "README.md",
            "OG3KUI.BIN",
            "OG3KUI.NBR",
            "ui_records.generated.inc",
        ):
            canonical_sidecars[pathlib.Path(relative)] = (
                canonical_out / relative
            ).read_bytes()
        for source in sorted((canonical_out / "assets").iterdir()):
            if source.is_file():
                canonical_sidecars[pathlib.Path("assets") / source.name] = (
                    source.read_bytes()
                )
    if ui_manifest["base_opengate_writes"] != len(core_items):
        raise SystemExit(
            "native UI builder 的 OpenGate core write count 與 og3k_plan 分歧")
    items = [item for segment in segs for item in segment]
    got_items = {(address, value) for address, value, _ in items}
    missing_core = [
        (address, value) for address, value, _ in core_items
        if (address, value) not in got_items
    ]
    if missing_core:
        raise SystemExit(
            f"native UI source 少了 {len(missing_core)} 筆 OpenGate core writes")
    # The ui_layout state block (UI_REQ, 48 bytes, og3k v0.2.5a) is reset by its
    # own section and is not part of the manifest's state_bytes.
    from build_og3k_ui_candidate import UI_REQ_BYTES
    expected_ui_words = (
        ui_manifest["ui"]["code_bytes"] // 4
        + ui_manifest["ui"]["pack_bytes"] // 4
        + ui_manifest["ui"]["state_bytes"] // 4
        + UI_REQ_BYTES // 4
        + len(ui_manifest["ui"]["hooks"])
    )
    if len(items) != len(core_items) + expected_ui_words:
        raise SystemExit(
            f"native UI source 共 {len(items)} words,預期 "
            f"{len(core_items)} core + {expected_ui_words} UI")
    ui_hooksites = {
        int(hook["address"], 16) for hook in ui_manifest["ui"]["hooks"]
    }
    hooksites = {s for s, _, _, _, _ in HOOKS} | ui_hooksites
    for seg in segs:
        if any(a in hooksites for a, _, _ in seg) and len(seg) != 1:
            raise SystemExit("hook 被併進了多字區段 —— hook 必須是自己的一段")
    last_payload = max(i for i, s in enumerate(segs)
                       if s[0][0] not in hooksites)
    if any(s[0][0] in hooksites for s in segs[:last_payload]):
        raise SystemExit("有 hook 排在 payload 之前,順序不安全")

    # 交給 gyro 自己的 build_base_card.py --edition gcsv。
    #
    # ⚠️ 2026-09-13 訂正:這裡本來呼叫 build_card.py --gcsv-stream,而**出貨的
    # v1.11b 不是那支建的**。實測:build_base_card.py --edition gcsv 的
    # 產出的 payload 跟發布的 v1.11b 逐位元組相同;build_card.py --gcsv-stream 不是。
    # 兩者的酬載完全不同 —— build_card 走單一 logger_stream.S,base_card 走
    # gsup_entry + accel/drain/start/stop/mode + 四個 stream 函式指標 + space,
    # 再加 pool+0x44000 的 10,552 B gcsv_task。
    # 所以舊的 og3k_gyro_release **沒有** v1.11b 的陀螺儀,少了那一整組區段。
    #
    # build_base_card.py 的介面跟 build_card.py 不同:
    #   --out 是目錄(不是 AutoRun.txt 的路徑)
    #   預設就不含 shell;--debug 才把 shell 留著(跟 --no-shell 相反)
    # OG3K core + native UI 的區段走 --also-bin,會跟原本的區段一起過 check():
    # 重疊、落進載入器讀取視窗、越過 park stub,都會在建置時失敗而不是在相機上。
    if no_gyro:
        # 純 OG3K:不經過 gyro 的建置器,直接用通用的 build_autorun.py。
        # 兩個 edition(base / gcsv)都會帶進整組 gyro 區段,而出貨版不要那些。
        # --loader 把內容放進 fpSup.BIN、AutoRun 只留載入器。
        ban = (sys.argv[sys.argv.index("--banner") + 1]
               if "--banner" in sys.argv else BANNER_OG)
        cmd = [sys.executable, str(SHELL), "--loader",
               "--banner", ban, "--out", str(OUT / "AutoRun.txt")]
        if release:
            cmd.append("--no-shell")
        # 暖開機 loader hook(LOADER_V2.md):原樣傳給 build_autorun.py。
        for flag in ("--loader-hook", "--four-box-bar"):
            if flag in sys.argv:
                cmd.append(flag)
        if "--loader-hook-mark" in sys.argv:
            cmd += ["--loader-hook-mark",
                    sys.argv[sys.argv.index("--loader-hook-mark") + 1]]
    else:
        cmd = [sys.executable, str(CARD), "--edition", "gcsv",
               "--version", VERSION, "--banner", BANNER, "--out", str(OUT)]
        if not release:
            cmd.append("--debug")      # 保留 USB shell,開發用
        if fast:
            # 一路傳到 build_autorun.py。快載入的四樣東西必須出自同一次
            # --store-boot 建置,而那次就是這裡呼叫的這一次。
            cmd.append("--store-boot")
        # 暖開機 loader hook(LOADER_V2.md);--fast --loader-hook --four-box-bar
        # 就是合併頁面的 Fast Start 3。
        for flag in ("--loader-hook", "--four-box-bar"):
            if flag in sys.argv:
                cmd.append(flag)
        if "--loader-hook-mark" in sys.argv:
            cmd += ["--loader-hook-mark",
                    sys.argv[sys.argv.index("--loader-hook-mark") + 1]]
    ui_section = None
    if os.environ.get("OG_UISHARE") == "1":
        # The resolution row by addition (fpSup/uishare): its section runs as
        # an entry before the restore; the site its handler hangs on is
        # declared with the stock word so stage2 journals it.
        sys.path.insert(0, str(ROOT / "fpSup" / "uishare"))
        import build_section
        ui_blob, ui_section = build_section.section(ui_block(_LABEL, ui_manifest).encode())
        uf = tmp / "ui_section.bin"
        uf.write_bytes(ui_blob)
        cmd += ["--boot-bin", f"{uf}:0"]
        for at, word in ui_section["sites"]:
            sf = tmp / f"site_{at:08X}.bin"
            sf.write_bytes(struct.pack("<I", word))
            cmd += ["--also-bin", f"0x{at:08X}:{sf}"]
    if ui_entry:
        cmd += ["--vshl-entry", f"0x{ui_entry:08X}"]
    for n, seg in enumerate(segs):
        f = tmp / f"og3k_{n:02d}_{seg[0][0]:08X}.bin"
        f.write_bytes(b"".join(struct.pack("<I", v) for _, v, _ in seg))
        cmd += ["--also-bin", f"0x{seg[0][0]:08X}:{f}"]

    print(f"  OG3K {len(items)} 筆 → {len(segs)} 個區段"
          + ("" if no_gyro else "   + gyro logger")
          + ("   (release,無 shell)" if release else "   + USB shell"))
    rc = subprocess.run(cmd).returncode
    shutil.rmtree(tmp, ignore_errors=True)
    if rc:
        raise SystemExit(f"shell 建置器失敗:{rc}")

    ar, vb = OUT / "AutoRun.txt", OUT / "fpSup.BIN"
    text = ar.read_text(encoding="utf-8")
    cmds = [l for l in text.splitlines()
            if l.strip() and not l.lstrip().startswith("#")]
    blob = vb.read_bytes()
    magic, count, entry, nbody = struct.unpack_from("<4sIII", blob)
    if magic != b"VBIN":
        raise SystemExit("fpSup.BIN 的 magic 不對")
    if no_gyro and release and ui_section is None and blob != canonical_vshl:
        raise SystemExit(
            "純 OG3K release 沒有逐位元重現 canonical native UI VSHL")
    if no_gyro and release and ui_section is not None:
        # OG_UISHARE: canonical 的每一段都原樣在(stage2 除外),多的只能是
        # UI 段落、它宣告的站點原廠字、以及 build_autorun 的入口跳板。
        def vbin(b):
            _, c, e, _ = struct.unpack_from("<4sIII", b)
            off, out = 16 + 8 * c, []
            for i in range(c):
                d, l = struct.unpack_from("<II", b, 16 + 8 * i)
                out.append((d, b[off:off + l]))
                off += l + (-l % 4)
            return out
        ours, canon = vbin(blob)[1:], vbin(canonical_vshl)[1:]
        lost = [d for d, b in canon if (d, b) not in ours]
        extra = [(d, len(b)) for d, b in ours if (d, b) not in canon]
        sites = {at for at, _ in ui_section["sites"]}
        allowed = all(d in sites or (d == 0 and n in (ui_section["bytes"], 84)) for d, n in extra)
        if lost or not allowed or len(extra) not in (len(sites) + 1, len(sites) + 2):   # + trampoline when 2+ entries
            raise SystemExit(f"OG_UISHARE 卡與 canonical 的差異不只 UI 段落: lost {lost} extra {extra}")

    # 回讀自檢:BIN 裡的區段必須逐字重現計畫
    got = []
    off = 16 + count * 8
    for i in range(count):
        dst, ln = struct.unpack_from("<II", blob, 16 + i * 8)
        data = blob[off:off + ln]
        off += ln + (-ln % 4)
        if dst >= 0x40000000:
            for k in range(0, ln, 4):
                got.append((dst + k, struct.unpack_from("<I", data, k)[0]))
    want = [(a, v) for a, v, _ in items]
    missing = [x for x in want if x not in set(got)]
    print(f"  AutoRun {len(cmds)} 條指令   fpSup.BIN {len(blob):,}B   {count} 個區段")
    print(f"  計畫回讀:{'✓ 全部重現' if not missing else f'★ 少了 {len(missing)} 筆'}")
    if missing:
        for a, v in missing[:8]:
            print(f"     0x{a:08X} = 0x{v:08X}")
        raise SystemExit(1)

    if no_gyro and release:
        for relative, data in canonical_sidecars.items():
            destination = OUT / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
        release_manifest = json.loads(json.dumps(ui_manifest))
        release_manifest["package"].update({
            "autorun_commands": len(cmds),
            "autorun_sha256": hashlib.sha256(text.encode()).hexdigest(),
            "vshl_sections": count,
            "vshl_used_bytes": 16 + count * 8 + nbody,
            "vshl_sha256": hashlib.sha256(blob).hexdigest(),
            "flavor": "release",
            "banner": ban,
            "usb_shell": False,
        })
        (OUT / "MANIFEST.json").write_text(
            json.dumps(release_manifest, indent=2) + "\n", encoding="utf-8"
        )

    man = [("SIGMA fp — OG3K 3:2 open gate" if no_gyro
            else "SIGMA fp — OG3K 3:2 open gate + gyro logger")
           + ("" if not release else " (release-format candidate)"),
           f"banner: {ban if no_gyro else BANNER}", "",
           f"AutoRun.txt  {len(text.encode()):,}B  sha256={hashlib.sha256(text.encode()).hexdigest()}",
           f"fpSup.BIN    {len(blob):,}B  sha256={hashlib.sha256(blob).hexdigest()}",
           f"reference_firmware sha256={p.sha}", "",
           f"AutoRun 指令 {len(cmds)} 條(上限 648);OG3K 的 {len(items)} 筆寫入全在 fpSup.BIN 裡,",
           "所以未來加格率/模式不會增加開機指令數。", "",
           f"canonical source: {UI_BUILDER.name} --release",
           f"OpenGate core {len(core_items)} words; native UI {expected_ui_words} words, "
           f"{UI_RECORD_COUNT} selected NBU records, {len(ui_hooksites)} hooks.",
           f"UI code sha256={ui_manifest['ui']['code_sha256']}",
           f"private NBR sha256={ui_manifest['ui']['pack_sha256']}", "",
           "卡上放:AutoRun.txt 與 fpSup.BIN(根目錄),沒有別的。", ""]
    man += ([] if no_gyro else [
           "gyro = build_base_card.py --edition gcsv,與發布的 v1.11b **完全同一組區段**",
           f"(逐位元組驗證:v1.11b 的 15 個區段全部原封不動在裡面,"
           f"另加 OG3K core + native UI 的 {len(segs)} 個區段)。",
           "錄製當下就把 .gcsv 與 .json",
           "寫進片段自己的資料夾,不需要 PGEN.BIN 也不需要 GYRO 資料夾。", ""])
    man += [
           "OG3K 錄影幾何:3024x2010,DNG 裁切 3008x2000 @ (8,5)。",
           "  遵守 fp 自己的影片邊界慣例:原廠三個錄影 profile 全是",
           "  「裁切 +16 寬 / +10 高」而且寬度 16 對齊",
           "  (p171 3856x2170/3840x2160、p173 1936x1090/1920x1080)。", "",
           "  2026-09-13 解檔驗證(A001_036):標頭 3024x2010、裁切 3008x2000 @ (8,5)、",
           "  StripByteCounts 9,117,360 = 3024x2010x1.5,整幅清晰、邊到邊、無剪切。", "",
           "借用的 profile 是 **p83**(S 尺寸 12-bit 照片的拍攝 profile)。",
           "  它的 PARAM 列與 p43 只差 +0x030,而張數原廠就是 3,所以不需要",
           "  寫畫格率。**所有幾何都只改畫布的 RAM 複本,原廠 PARAM 列一個位元都不動。**",
           "  早先借 p43 要寫畫格率,那會讓 S 尺寸照片檢視多要三張 RAW 緩衝 ——",
           "  拍一張 S 尺寸照片就會凍結。改用 p83 之後已驗證消失。", "",
           "live view:待機、半按、錄影三個狀態都已驗證正確。",
           "  錄影期截圖 SS__0413 對比待機 SS__0408:水平 1.000x、垂直 1.000x、",
           "  異向比 1.0000、相關 0.9787。", "",
           "機內回放:**正常**(2026-09-13 解決)。",
           "  兩個原因:(1) 記錄尺寸沒遵守 +16/+10 慣例,3032 只有 8 對齊;",
           "  (2) 回放 profile 的柵格就是來源列距,而原廠柵格正好等於該格式片子的",
           "  記錄尺寸(p53 1936x1090 = FHD 片、p51 3856x2170 = UHD 片),",
           "  我們的片子沒有對應 profile,退回值與實際寬度不符。",
           "  修法 og3kcanvas.S:一個 hook 兩個 case,只改畫布 RAM 複本。",
           "  播放中的畫面比例由 og3kout 處理(守衛擴成 FLAG 或 PBFLAG)。",
           "  驗證:A001_037 回放截圖 SS__0426(暫停)與 SS__0427 之後(播放中)均正常。",
           "  詳見 notes/OG3K_PLAYBACK_PROFILE_CLASSES.md 第 14 節。", "",
           "原生 ISO / 高光餘裕:**已修正**(2026-09-14)。",
           "  OG3K 的擷取原本拿到 gain_state 3(雙原生 HCG 門檻 ISO 640),",
           "  在 ISO 640 以上就切到高轉換增益 —— 比原廠 12-bit CinemaDNG",
           "  (gain_state 7,門檻 3200)**少約 2.7 檔高光餘裕**,而且因為機內回放",
           "  固定補 +3 EV,回放會過曝 2.7 檔。",
           "  實測:修正前 raw 比原廠 FHD 亮 2.675 EV、BaselineExposure +0.322;",
           "  修正後兩者完全一致(+3.000,同場景中位−黑階 3.0 vs 3.0)。",
           "  修法 og3kgs.S:只 hook 增益分派的判斷 FUN_c03a6dd8,不動感測器模式。",
           "  同時把預覽平面格式 +0x080 補成 12-bit(原廠影片是 7,照片 profile 是 10),",
           "  否則錄影預覽會偏綠並閃爍。", "",
           "快門角度曝光:**29.97/180° 冷開機目視通過，其他幀率待驗證**(2026-09-15)。",
           "  mode98 的共用 nominal-fps metadata 是 78，角度路徑因此把 29.97/180°",
           "  算成約 1/156（-1.380 EV）。fmttable 只接受 CinemaDNG table3，並把",
           "  timing pair 當成一個 transaction；og3kfps.S 先完整呼叫原 getter，",
           "  再依 FLAG 與精確 timing tuple 覆寫回傳值，混合/未知 tuple 皆 fail-open。",
           "  四條已確認的角度換算/同步 BL 都導向同一個窄 wrapper；全域",
           "  getter 與快門速度路徑不動。離開 OG3K 時會先撤 FLAG 並還原 mode98 stock timing；",
           "  mode98 metadata 與 p83 照片欄位零寫入；",
           "  stage2 完成所有 section 寫入後，依序同步 D-cache 並清 I-cache，",
           "  避免 AutoRun 較慢時 CPU 繼續執行舊的 stock 指令。",
           f"  {len(core_items)}-word core 已與生成的 VSHL 離線逐字對帳。",
           "  使用者已在拔電池冷開機後目視確認 29.97/180° 的 FHD/OG3K",
           "  idle live-view 曝光一致；當時 USB 未連線，因此尚無精確 shutter readback。",
           "  23.976/24/25/48/50/59.94/100 的 idle 實機驗證仍未完成，故版本標 a。", "",
           "  CINE/STILL 切換時若仍選著 OG3K 尚未實機驗證；完成前請先切回 FHD/UHD。", "",
           "  熱重開與 hot reinstall 未驗證且不支援；目前只接受拔電池冷開機。", "",
           f"原生 Settings / Quick Set UI (v{OG_VERSION}):",
           "  - MENU 收合摘要與三選項清單的 OG3K 名稱已在實機驗證。",
           "  - QS 大/小 OG3K 值與 UHD/FHD/OG3K 底列、游標已在實機驗證。",
           "  - 這是 alpha build:實機測的是含 USB shell 但 UI payload 逐位元相同的版本;",
           "    精確 no-shell 出貨 pair 還需一次實機冷開 smoke test。",
           "  - 短轉場通過 FHD 1 次、UHD 3 次、OG3K 3 次;UHD/OG3K 約 1 秒。",
           "    2026-09-14 A001_082 曾凍結且未能重現;這不是本次新回報的事件。",
           "    慢 SD 卡不足以驗證持續錄影。",
           "  - v0.2 full-UI 回放、非當前 screen/style variants 與快速媒體長時錄影尚未回歸。"]
    # These two documents are OG3K's, word for word: the geometry, the exposure
    # work, the UI verification history, the frame rates.  Writing them for OG2K
    # produced an OG2K release whose README opened "OG3K native UI release test
    # package" and whose MANIFEST claimed 3024x2010 -- shipped once, on
    # 2026-09-19, over a hand-written OG2K text that had been correct.
    #
    # So they are not written for OG2K at all.  OG2K's README and MANIFEST are
    # carried forward from its previous release and edited, which is what they
    # were before a generator overwrote them.
    # 2026-09-20:這個守衛原本只擋 og2k。加第三、第四個目標時它就漏了 ——
    # HSW 的合併卡拿到的 MANIFEST 開頭寫「OG3K 3:2 open gate」。
    # 條件改成「不是 OG3K 就不要寫」。
    if _TARGET != "og3k":
        for name in ("MANIFEST.txt", "README.md"):
            (OUT / name).unlink(missing_ok=True)
        print(f"  MANIFEST.txt / README.md NOT written: they are OG3K's text.")
        print(f"  Carry {_LABEL}'s forward from the previous release and edit them.")
    else:
        (OUT / "MANIFEST.txt").write_text("\n".join(man) + "\n", encoding="utf-8")
    if dev_card:
        # ★ gyro 的 README.txt 最後一段對**開發卡**是假的,而且是危險的假:
        #     "This card carries no USB shell.  Nothing is flashed: take the
        #      two files off the card, or pull the battery, and the camera is
        #      exactly as it was."
        # 開發卡本來就合併了 USB shell;而 --fast 會把 loader 種進
        # XC_CommonSaveData —— 那是設定區,**拔電池也還在**,刪掉 AutoRun.txt
        # 也還在。照原文做並不會讓相機回到原樣。
        readme = OUT / "README.txt"
        if readme.exists():
            text = readme.read_text(encoding="utf-8")
            stale = ("This card carries no USB shell.  Nothing is flashed: take "
                     "the two files off\nthe card, or pull the battery, and the "
                     "camera is exactly as it was.\n")
            if stale not in text:
                raise SystemExit("README.txt 的結尾段落與預期不符,不敢盲改 —— "
                                 "先看過 gyro/build_base_card.py 的原文")
            fixed = (
                "This is a DEVELOPMENT card, not the card a user downloads.\n\n"
                "It carries the USB shell: the camera exposes a command channel "
                "over USB\nwhile this card is booted.\n\n")
            if fast:
                fixed += (
                    "It also carries FAST START, which writes a loader into the "
                    "camera's settings\nblock (XC_CommonSaveData) on the first "
                    "boot.  That write SURVIVES A BATTERY\nPULL and survives "
                    "deleting AutoRun.txt.  Removing the two files does NOT put "
                    "the\ncamera back exactly as it was; the seeded block stays "
                    "until it is cleared.\n\n"
                    "Fast start has been booted on a shell-only card.  It has "
                    "NOT been booted on a\ncombined card like this one.\n\n")
            else:
                fixed += ("Nothing is flashed: take the two files off the card, "
                          "or pull the battery, and\nthe camera is exactly as it "
                          "was.\n\n")
            readme.write_text(text.replace(stale, fixed), encoding="utf-8")
            print("  README.txt: 結尾段落改成開發卡的實話"
                  + ("(含快載入會寫設定區的警告)" if fast else ""))
        # 說清楚這張卡跟使用者拿到的那張差在哪,免得測試結論被默默套用到
        # 另一個東西上。2026-09-20 逐區段比對過:97 個區段裡 96 個逐位元組
        # 相同,AutoRun.txt 完全相同。
        print()
        print("  這是開發卡,不是使用者下載到的那張。與 fpSup-Merge 的差別:")
        if fast:
            print("    0. 帶快載入(--store-boot):第一次開機慢並種設定區,"
                  "之後 26 條")
        print("    1. 沒有 EP 0x83 的 push 補丁(六個字)—— --debug 傳 "
              "--no-ep-patches")
        print("    2. 區段順序不同,因此 trampoline 表格裡的偏移也不同")
        print("  其餘逐位元組相同,AutoRun.txt 完全相同。要給人的卡走網頁。")
    print(f"  → {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
