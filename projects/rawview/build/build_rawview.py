#!/usr/bin/env python3
"""build_rawview.py — 建 rawview 卡(AutoRun.txt + fpSup.BIN)。

    python3 build_rawview.py              開發卡:合併 USB shell(與合併器 'shell' 範本同旗標 --no-ep-patches)
    python3 build_rawview.py --fast       開發卡＋快載入(--store-boot;四樣東西出自同一次建置)
    python3 build_rawview.py --fs2 --out DIR   開發卡＋Fast Start 3(--store-boot --loader-hook --four-box-bar);
                                               DIR/FPSUPUI/ 要一起放上卡(skill fp-merged-card)
    python3 build_rawview.py --release    不含 shell(--no-shell)

執行期改的每個韌體位址都宣告成一個「內容 = 原廠字」的區段(hook_sites,同 gyro):
stage2 先記進 journal 再寫原廠字(也修好上次關機漏跑留下的補丁),關機回呼寫回 → 相機關機後是原廠。

照 SUP_BUILD_RULES:沿用共用 build_autorun.py 的 --loader 路徑,rawview 是一個 --boot-bin(destination 0)。
blob = rv_launch(程式)| rv_resident | 表格資料(rv_tables.blob)
"""
import argparse, pathlib, struct, subprocess, sys, tempfile

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parents[2]
SHELL = REPO / 'fpSup' / 'fp_usb_shell'
sys.path.insert(0, str(SHELL))
from armasm import assemble, symbols  # noqa: E402
import rv_tables                       # noqa: E402
import rv_uidata                       # noqa: E402
import rv_color                        # noqa: E402
import rv_dngcm                        # noqa: E402


def write_csv_inc():
    """rv_resident.S 的 #include:fvtab 與三個 CSV(rv_uidata 是唯一定義)。"""
    files = rv_uidata.blobs() + rv_uidata.icon_blobs()          # 三個 CSV + RAW 圖示
    glyphs = rv_uidata.glyph_blobs()                             # 條件式:SA/GA 字形
    (HERE / 'rv_fv.inc').write_text(f'/* 由 build_rawview.py 產生,勿手改 */\n.equ NFV, {len(files)}\n.equ NGL, {len(glyphs)}\n')
    out = ['/* 由 build_rawview.py 產生,勿手改 */', '.align 2', 'fvtab:']
    for i, (name, at, data) in enumerate(files):
        out.append(f'    .word 0x{at:08X}, csv{i} - params, {len(data)}   /* {name} */')
    out.append('gltab:')
    for j, (name, at, data) in enumerate(glyphs):
        out.append(f'    .word 0x{at:08X}, csv{len(files) + j} - params, {len(data)}   /* {name} */')
    files = files + glyphs
    for i, (name, at, data) in enumerate(files):
        out.append('.align 2')
        out.append(f'csv{i}:')
        for j in range(0, len(data), 16):
            out.append('    .byte ' + ', '.join(f'0x{b:02X}' for b in data[j:j + 16]))
    out.append('.align 2')
    (HERE / 'rv_csv.inc').write_text('\n'.join(out) + '\n')

MAXLEN = 0xF000                        # loader.S:整個合併 BIN 的上限
ROM = REPO / 'out' / 'MAIN_c0000000.bin'
# launcher／stub 在執行期會改的位址(與 rv_launch.S 的 GUARD、rv_resident.S 一致;測試逐一核對)
RUNTIME_SITES = [
    (0xC0313244, 'hook A gain_state'), (0xC032F728, 'hook B RAW_CORR'),
    (0xC0568950, 'GUI→enum COLOR 鍵'), (0xC056D028, 'GUI→enum 選單'), (0xC05818B8, 'GUI→enum QS'),
    (0xC0595734, 'enum→GUI CM_COLFIX'), (0xC0075CF4, 'setter cmp'),
    (0xC06C07CC, 'getter movw'), (0xC06C07D0, 'getter movt'), (0xC06C07D8, 'getter count'),
    (0xC05E5BEC, 'H1 取檔位置'),
    (0xC2F1A0D4, 'root+0x70 mode→tone(stub_gs 改)'),
    (0xC059DA1C, 'enum→GUI LV_ColorMode'),
    (rv_color.ROOT_P08, 'root+0x08 色彩矩陣表(stub_gs 改,RAW 生效時)'),
    (0xC0568A3C, '上下框回呼 bl(SA/GA)'), (0xC0595908, 'v87 Effect 發布 bl'),
    (0xC056D5F8, '飽和度 AJ bl'), (0xC056D498, '飽和度 FIX bl'),
    (0xC059588C, 'v85 COLFIX 飽和度 bl'), (0xC05959E4, 'v90 COLAJ 飽和度 bl'),
    (0xC05689A8, 'GUI→enum COLOR 鍵預覽(AJ)'), (0xC05957B0, 'v82 COLFIX Effect 發布 bl'),
] + [(a, f'DNG writer {why}') for a, _, why in rv_dngcm.SITES] + [
    (0xC0D119FC, 'ColorButtonMenu vtable v25(開啟)'), (0xC0D11A00, 'ColorButtonMenu vtable v26(關閉)')] + [
    (a, f'對比/清晰鎖 0 bl {a:08X}') for a in (0xC056D548, 0xC056D3E8, 0xC056D5A0, 0xC056D440,
                                              0xC059581C, 0xC0595974, 0xC0595854, 0xC05959AC)] + [
    (0xC05E2200, '關鍵影格圖名 bl(Thumb BL → stub_ai,SA/GA)'),
    (0xC0088C60, '關機存檔 bl(→ stub_sv,RAW 存成 0x10–0x17)'),
    (0xC02B8E64, '畫質管理器指令 bl(→ stub_pq,回放換回原廠)')] + [(a, f'ColorButtonMenu 頁面 0x{a:08X}') for a, _, _ in rv_uidata.PAGE]


SEG1, SEG1_BASE = REPO / 'out' / 'seg1_c2ef6e00.bin', 0xC2EF6E00


def stock_word(a):
    """原廠字。0xC2EF6E00 以上是 .data(seg1,開機時由另一段載入初值),MAIN 映像在那裡不是執行期的值。"""
    if a >= SEG1_BASE:
        return SEG1.read_bytes()[a - SEG1_BASE:a - SEG1_BASE + 4]
    return ROM.read_bytes()[a - 0xC0000000:a - 0xC0000000 + 4]


def hook_sites():
    """每個執行期位址一個 4-byte 區段,內容 = 原廠字。"""
    out = [(a, stock_word(a), why) for a, why in RUNTIME_SITES]
    import struct
    assert struct.unpack('<I', stock_word(0xC2F1A0D4))[0] == 0xC0B3D670, 'root+0x70 原廠值不是 C0B3D670'
    assert struct.unpack('<I', stock_word(rv_color.ROOT_P08))[0] == rv_color.MAT_TAB, 'root+0x08 原廠值不符'
    return out
ALLOWED_CALLS = {0xC001D740, 0xC001D7F0, 0xC000E91C, 0xC000EABC,   # 配置、D/I cache
                 0xC0057AE8, 0xC005C958}   # 開機還原 RAW(只在色彩是 0x10–0x17 時;常駐的 stub_ef 另呼叫 0xC0593F30)


def write_page_inc():
    """rv_launch.S 的 #include:頁面表(rv_uidata.PAGE 是唯一定義)。"""
    out = ['/* 由 build_rawview.py 產生,勿手改 */', '.align 2', 'page_tab:']
    for a, old, new in rv_uidata.PAGE:
        out.append(f'    .word 0x{a:08X}, 0x{old:08X}, 0x{new:08X}')
    out.append('    .word 0')
    (HERE / 'rv_page.inc').write_text('\n'.join(out) + '\n')


def write_mat_inc():
    """rv_launch.S 的 #include:OFF 那筆的原廠字(guard)與新矩陣(rv_color 是唯一定義)。"""
    rom = ROM.read_bytes()[rv_color.OFF_REC - 0xC0000000:rv_color.OFF_REC - 0xC0000000 + 24]
    stock = rv_color.off_words(False)
    assert struct.unpack('<6I', rom) == stock, 'OFF 矩陣原廠值不符'
    out = ['/* 由 build_rawview.py 產生,勿手改 */', '.align 2',
           'mat_stock: .word ' + ', '.join(f'0x{w:08X}' for w in stock),
           'mat_new:   .word ' + ', '.join(f'0x{w:08X}' for w in rv_color.off_words(True))]
    (HERE / 'rv_mat.inc').write_text('\n'.join(out) + '\n')


def write_sat_inc():
    """rv_resident.S 的 #include:矩陣程度表(rv_color.sat_words,SAT_MAX + 1 筆 × 24 B),放在參數區 +0x1D0。"""
    w = rv_color.sat_words()
    out = ['/* 由 build_rawview.py 產生,勿手改 */', f'.equ SAT_MAX, {rv_color.SAT_MAX}', 'sat_tab:']
    for i in range(0, len(w), 6):
        out.append('    .word ' + ', '.join(f'0x{x:08X}' for x in w[i:i + 6]) + f'   /* 飽和度 {rv_color.SAT_LEVELS[i // 6]} */')
    (HERE / 'rv_sat.inc').write_text('\n'.join(out) + '\n')


def write_dngcm_inc():
    """rv_resident.S 的 #include:DNG ColorMatrix(SAT_MAX + 1)級 × (CM1, CM2) × 9 double(rv_dngcm 是唯一定義)。"""
    b = rv_dngcm.blob()
    out = ['/* 由 build_rawview.py 產生,勿手改 */', 'cm_buf:        /* 初值 = 第 0 級(原廠 OFF),stub_gs 改寫 */']
    words = lambda d: ['    .word ' + ', '.join(f'0x{w:08X}' for w in struct.unpack('<6I', d[i:i + 24]))
                       for i in range(0, len(d), 24)]
    out += words(b[:144]) + ['cm_tab:'] + words(b)
    (HERE / 'rv_dngcm.inc').write_text('\n'.join(out) + '\n')


def write_kf_inc():
    """rv_resident.S 的 kftab(stub_mc 切換)與 rv_launch.S 的 kf_guard(開機核對),rv_uidata.KEYFRAMES 是唯一定義。"""
    kf = rv_uidata.KEYFRAMES
    (HERE / 'rv_kfn.inc').write_text(f'/* 由 build_rawview.py 產生,勿手改 */\n.equ NKF, {len(kf)}\n')
    out = ['/* 由 build_rawview.py 產生,勿手改 */', '.align 2', 'kftab:']
    out += [f'    .word 0x{a:08X}, 0x{o:X}, 0x{n:X}   /* {why} */' for a, o, n, why in kf]
    (HERE / 'rv_kf.inc').write_text('\n'.join(out) + '\n')
    g = ['/* 由 build_rawview.py 產生,勿手改 */', '.align 2', 'kf_guard:']
    g += [f'    .word 0x{wa:08X}, 0x{w:08X}' for wa, w in rv_uidata.keyframe_words()] + ['    .word 0']
    (HERE / 'rv_kfg.inc').write_text('\n'.join(g) + '\n')


def build_blob(uishare=True):
    write_csv_inc()
    write_page_inc()
    write_mat_inc()
    write_sat_inc()
    write_dngcm_inc()
    res_src = HERE / 'rv_resident.S'
    res = assemble(res_src)
    rs = symbols(res_src)
    assert rs['sat_tab'] - rs['params'] == 0x1D0, f'sat_tab 在 +0x{rs["sat_tab"] - rs["params"]:X}'
    assert rs['cm_buf'] % 8 == 0 and rs['cm_tab'] - rs['cm_buf'] == 144, 'cm_buf 對齊/大小'
    assert rs['stub_gs'] - rs['cm_tab'] == len(rv_color.SAT_LEVELS) * 144, 'cm_tab 之後應接 stub_gs'
    res += b'\0' * (-len(res) % 4)
    assert 0x3E200 + len(res) <= 0x40800 and 0x40800 + 0x348 + 0xFFF <= 0x42000, f'常駐 {len(res)} B 蓋到矩陣副本(T0 + 0x40800)'
    tdata = rv_tables.blob()
    defs = [f'RES_LEN=0x{len(res):X}', f'TDATA_OFF=0x{len(res):X}',
            f'STUB_GS=0x{rs["stub_gs"]:X}', f'STUB_DG=0x{rs["stub_dg"]:X}',
            f'STUB_MA=0x{rs["stub_ma"]:X}', f'STUB_MB=0x{rs["stub_mb"]:X}', f'STUB_MC=0x{rs["stub_mc"]:X}',
            f'STUB_FV=0x{rs["stub_fv"]:X}', f'STUB_ML=0x{rs["stub_ml"]:X}',
            f'STUB_EF=0x{rs["stub_ef"]:X}', f'STUB_EN=0x{rs["stub_en"]:X}',
            f'STUB_SA=0x{rs["stub_sa"]:X}', f'STUB_SN=0x{rs["stub_sn"]:X}', f'STUB_MJ=0x{rs["stub_mj"]:X}',
            f'CMBUF=0x{rs["cm_buf"] - rs["params"]:X}', f'CMTAB=0x{rs["cm_tab"] - rs["params"]:X}',
            f'STUB_MO=0x{rs["stub_mo"]:X}', f'STUB_MX=0x{rs["stub_mx"]:X}',
            f'STUB_ZC=0x{rs["stub_zc"]:X}', f'STUB_ZS=0x{rs["stub_zs"]:X}',
            f'STUB_ZNC=0x{rs["stub_znc"]:X}', f'STUB_ZNS=0x{rs["stub_zns"]:X}', f'STUB_AI=0x{rs["stub_ai"]:X}', f'STUB_SV=0x{rs["stub_sv"]:X}', f'STUB_PQ=0x{rs["stub_pq"]:X}']
    defs.append(f'UISHARE={1 if uishare else 0}')
    launch_src = HERE / 'rv_launch.S'
    launch = assemble(launch_src, defs)
    ls = symbols(launch_src, defs)
    if ls['blob'] != len(launch):
        raise SystemExit(f'launcher blob label at {ls["blob"]:#x} but code is {len(launch):#x} bytes')
    check_calls(launch)
    blob = launch + res + tdata
    return blob, {'launch': len(launch), 'resident': len(res), 'tables': len(tdata),
                  'stub_gs': rs['stub_gs'], 'stub_dg': rs['stub_dg'],
                  'stub_ma': rs['stub_ma'], 'stub_mb': rs['stub_mb'], 'stub_mc': rs['stub_mc'],
                  'stub_fv': rs['stub_fv'], 'stub_ml': rs['stub_ml'], 'stub_ef': rs['stub_ef'],
                  'stub_en': rs['stub_en'], 'stub_sa': rs['stub_sa'], 'stub_sn': rs['stub_sn'], 'stub_mj': rs['stub_mj'],
                  'cm_buf': rs['cm_buf'] - rs['params'], 'cm_tab': rs['cm_tab'] - rs['params'],
                  'stub_mo': rs['stub_mo'], 'stub_mx': rs['stub_mx'], 'gltab': rs['gltab'] - rs['params'],
                  'stub_zc': rs['stub_zc'], 'stub_zs': rs['stub_zs'], 'stub_znc': rs['stub_znc'], 'stub_zns': rs['stub_zns'],
                  'stub_ai': rs['stub_ai'], 'stub_il': rs['stub_il'], 'stub_sv': rs['stub_sv'], 'stub_pq': rs['stub_pq']}


def check_calls(code):
    """launcher 只能 blx 到四個允許的函式(movw/movt ip 之後的 blx ip)。"""
    import capstone
    md = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_ARM)
    lo = hi = None
    for i in md.disasm(code, 0):
        if i.mnemonic == 'movw' and i.op_str.startswith('ip,'):
            lo = int(i.op_str.split('#')[1], 0)
        elif i.mnemonic == 'movt' and i.op_str.startswith('ip,'):
            hi = int(i.op_str.split('#')[1], 0)
        elif i.mnemonic == 'blx':
            target = (hi << 16) | lo
            if target not in ALLOWED_CALLS:
                raise SystemExit(f'launcher calls 0x{target:08X}, not an allowed routine')
        elif i.mnemonic == 'bl':
            raise SystemExit(f'launcher has a direct bl at {i.address:#x}')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--release', action='store_true', help='不含 USB shell')
    ap.add_argument('--no-shell', action='store_true',
                    help='Fast Start 3 卡不含 USB shell(使用者 2026-09-26:加速卡也不要 shell)。仍是開發卡包裝,'
                         '非單一產品正式版;無法 USB 熱更新,要回原廠用恢復卡')
    ap.add_argument('--fs3', '--fs2', dest='fs2', action='store_true', help='Fast Start 3(開發卡;--fs2 為舊名)')
    ap.add_argument('--fast', action='store_true',
                    help='快載入(只用於開發卡):第一次開機把 loader 種進 XC_CommonSaveData,拔電池也還在')
    ap.add_argument('--out', type=pathlib.Path, default=None)
    ap.add_argument('--banner', default=None)
    ap.add_argument('--legacy-ui', action='store_true',
                    help='v0.2.2test 的做法:啟動器自己換 CSV/圖示/頁面字(H1)。預設改用 fpSup/uishare 的'
                         ' UI 段落(2026-10-03),以添加方式加 RAW 列,才能和其他改選單的 sup 合併')
    a = ap.parse_args()
    if a.fs2:
        a.fast = True
    if a.fast and a.release:
        raise SystemExit('--fast 只用於開發卡(同 build_og3k_gyro.py 的規則)')
    out = a.out or HERE / 'out' / ('release' if a.release else 'dev-fast' if a.fast else 'dev')
    if a.no_shell and not a.fs2:
        raise SystemExit('--no-shell 只用於 --fs2(單卡請用 --release)')
    if a.banner is None:
        a.banner = ('fpSup-RAW-REL!' if a.release else 'fpSup-RAW-FS3!' if a.no_shell else 'fpSup-DEV-RAW-FS3!' if a.fs2 else
                    'fpSup-DEV-RAW-Fast!' if a.fast else 'fpSup-DEV-RAW!')
    blob, info = build_blob(uishare=not a.legacy_ui)
    if len(blob) > MAXLEN:
        raise SystemExit(f'blob {len(blob)} bytes exceeds MAXLEN {MAXLEN}')
    tmp = pathlib.Path(tempfile.mkdtemp())
    bf = tmp / 'rawview.bin'
    bf.write_bytes(blob)
    cmd = [sys.executable, str(SHELL / 'build_autorun.py'), '--loader', '--banner', a.banner,
           '--boot-bin', f'{bf}:0', '--out', str(out / 'AutoRun.txt')]
    ui_info = None
    if not a.legacy_ui:
        sys.path.insert(0, str(REPO / 'fpSup' / 'uishare'))
        from ui import options as ui_options
        import build_section
        ui_blob, ui_info = build_section.section(
            ui_options.color_raw(rv_uidata.ICONS[0][3].read_bytes()).encode())
        declared = {s for s, *_ in hook_sites()}
        missing = [s for s, _ in ui_info['sites'] if s not in declared]
        if missing:
            raise SystemExit(f'UI section changes undeclared sites: {missing}')
        uf = tmp / 'ui.bin'
        uf.write_bytes(ui_blob)
        cmd += ['--boot-bin', f'{uf}:0']
    if a.release or a.no_shell:
        cmd.append('--no-shell')
    else:
        cmd.append('--no-ep-patches')          # 合併器 'shell' 範本:shell 在、EP 0x83 push 不開
    if a.fast:
        cmd.append('--store-boot')
    if a.fs2:
        cmd += ['--loader-hook', '--four-box-bar', '--loader-hook-mark', '0xC072E040']
    for site, word, why in hook_sites():
        f = tmp / f'site_{site:08x}.bin'
        f.write_bytes(word)
        cmd += ['--also-bin', f'0x{site:08X}:{f}']
    out.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(cmd, capture_output=True, text=True)
    sys.stdout.write(r.stdout)
    if r.returncode:
        sys.stderr.write(r.stderr)
        raise SystemExit('build_autorun failed')
    (out / 'rawview.bin').write_bytes(blob)
    print(f'\n  rawview blob {len(blob)} bytes  ' + '  '.join(f'{k} {v}' for k, v in info.items()))
    print(f'  {out / "fpSup.BIN"}  {(out / "fpSup.BIN").stat().st_size} bytes')
    if ui_info:
        print(f'  UI section {ui_info["bytes"]} bytes (applier {ui_info["c_text"]}, block {ui_info["block_len"]})')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
