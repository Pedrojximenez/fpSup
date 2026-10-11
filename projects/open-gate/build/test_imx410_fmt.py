#!/usr/bin/env python3
"""imx410_fmt.S 的 picker hook 行為,在 unicorn 上對真的 picker 表跑。

檢查四條路徑:命中、沒有 mode 對應時的 FHD fallback、不是我們的鍵時放行、
以及三張表各自鎖存正確的位元深度碼。

    python3 test_imx410_fmt.py
"""
from __future__ import annotations

import pathlib
import struct
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from unicorn import UC_ARCH_ARM, UC_HOOK_CODE, UC_MODE_ARM, Uc
from unicorn.arm_const import UC_ARM_REG_LR, UC_ARM_REG_R0, UC_ARM_REG_R1, \
    UC_ARM_REG_R2, UC_ARM_REG_R6, UC_ARM_REG_SP

from armasm import assemble, symbols
from imx410_block import (A_RATE, RATE_KEYS, RECIPE_WORDS, R_MODE, R_IDX,
                          R_TW0, R_TW1, aspect_q_table, axis_words,
                          canvas_template, expected_recipe, rate_table,
                          ratestr_table, timing_table)
from imx410_full import FIRMWARE, Registry

B = 0xC0000000
FMT_CODE = 0x40000000
RECIPE_CODE = 0x40002000
AXIS = 0x40010000
RECIPE = 0x40010040
ENTRY = 0x400100B0            # RECIPE 現為 27 字;舊 +0x80 會覆蓋後 11 字
RATETAB = 0x40010100
TMGTAB = 0x40010200
CTMPL = 0x40010400
CANVAS = 0x40010500
ASPTAB = 0x40010700
STACK = 0x40020000
DONE = 0x40030000
BACK = 0xC043CCFC
IMAGER = 0xC343B588
DESC = 0xC2F1E654

TAB = {14: 0xC0BE5B50, 12: 0xC0BE5B50, 10: 0xC0BE59B0, 8: 0xC0BE5810}
BD = {12: 0, 10: 3, 8: 4}
MENU_BD = {**BD, 14: 1}
MENU_RETURN = {8: 0xC043B8D8, 10: 0xC043B908,
               12: 0xC043B92C, 14: 0xC043B92C}
BITLATCH, PICKOK, FPSLATCH, HITS = 0xC0731C14, 0xC0731C44, 0xC0731C40, 0xC0730700
import imx410_plan as _PL
PROFILE = _PL.PRIVATE_PROFILE          # 我們宣告的 id:imx410_fmt 從 PROFILE_ID 這個 RAM 字讀
# imx410_fmt 用可重定位的絕對位址讀 PROFILE_ID；此獨立測試把它放在
# RECIPE 旁邊，並另由 USER 搬遷測試檢查實際封裝後的位址。
PROFILE_ID = None                       # 見下方,RECIPE 定義之後
FILL = _PL.PROFILE == 13               # 底列是空殼才填滿(與計畫相同)

REG = Registry()
IMG = FIRMWARE.read_bytes()

PROFILE_ID = RECIPE + (_PL.PROFILE_ID - _PL.RECIPE)

DEFS = [f"AXIS={AXIS:#x}", f"RECIPE={RECIPE:#x}", f"RATETAB={RATETAB:#x}",
        f"TMGTAB={TMGTAB:#x}", f"CTMPL={CTMPL:#x}", f"CANVAS={CANVAS:#x}",
        f"ASPTAB={ASPTAB:#x}"]
RATESTR = 0x40010800
RATE240 = 0xC0731C48                 # imx410_rate_native.RATE240(記憶體記號)
FMT_DEFS = [f"RECIPE={RECIPE:#x}", f"RECIPE_CODE={RECIPE_CODE:#x}",
            f"ENTRY={ENTRY:#x}", f"PROFILE_ID={PROFILE_ID:#x}",
            f"AXIS={AXIS:#x}", f"RATESTR={RATESTR:#x}",
            "WITH_RATE_FROM_MENU=1", "WITH_BIT_FROM_MENU=1"]


def run(axis, key: bytes, depth=12, menu_depth=None, fmt_blob=None, rate240=None):
    """模擬 picker 呼叫 hook 一次。回傳 (r0, 觀測到的各個鎖存)。"""
    mu = Uc(UC_ARCH_ARM, UC_MODE_ARM)
    mu.mem_map(0x40000000, 0x00040000)
    mu.mem_map(0xC0430000, 0x00010000)        # BACK 落點
    mu.mem_map(0xC0700000, 0x00100000)        # 鎖存
    mu.mem_map(0xC0B00000, 0x00200000)        # metadata / timing / picker 表
    mu.mem_map(0xC2F00000, 0x00100000)
    mu.mem_map(0xC3400000, 0x00100000)

    mu.mem_write(0xC0B00000, IMG[0xC0B00000 - B: 0xC0D00000 - B])
    mu.mem_write(DESC, struct.pack("<4I", 0xC0B59500, 70, 0xC0B59DC0, 70))
    mu.mem_write(IMAGER, struct.pack("<I", DESC))
    defs = FMT_DEFS + ([f"RATE240={RATE240:#x}"] if rate240 is not None else [])
    mu.mem_write(FMT_CODE, fmt_blob if fmt_blob is not None else
                 assemble("imx410_fmt.S", defines=defs))
    if rate240 is not None:
        mu.mem_write(RATE240, struct.pack("<I", rate240))
    mu.mem_write(RECIPE_CODE, assemble("og3krecipe.S", defines=DEFS))
    mu.mem_write(RATETAB, rate_table())
    mu.mem_write(TMGTAB, timing_table())
    mu.mem_write(CTMPL, canvas_template(FILL, tuple(axis)))
    mu.mem_write(ASPTAB, aspect_q_table())
    mu.mem_write(RATESTR, ratestr_table())
    mu.mem_write(AXIS, struct.pack(f"<{len(axis)}I", *axis))
    mu.mem_write(RECIPE, b"\x00" * (RECIPE_WORDS * 4))
    mu.mem_write(ENTRY, b"\x00" * 48)
    mu.mem_write(PROFILE_ID, struct.pack("<I", PROFILE))
    keybuf = 0x40011000
    mu.mem_write(keybuf, key + b"\x00" * (32 - len(key)))

    hit_back = []
    mu.hook_add(UC_HOOK_CODE,
                lambda u, a, sz, d: (hit_back.append(a), u.emu_stop())
                if a == BACK else None)

    mu.reg_write(UC_ARM_REG_R0, 0xAAAA0000)
    mu.reg_write(UC_ARM_REG_R1, TAB[depth])
    mu.reg_write(UC_ARM_REG_R2, keybuf)
    # 非原廠呼叫者的 r6 刻意不可讀,證明不會亂走 config pointer。
    config = 0x40011200 if menu_depth is not None else 0xDEAD0000
    mu.reg_write(UC_ARM_REG_R6, config)
    end = DONE
    if menu_depth is not None:
        mu.mem_write(config + 0x20, struct.pack("<I", MENU_BD[menu_depth]))
        end = MENU_RETURN[menu_depth]
    mu.reg_write(UC_ARM_REG_SP, STACK)
    mu.reg_write(UC_ARM_REG_LR, end)
    mu.emu_start(FMT_CODE, end, count=2_000_000)

    w = lambda a: struct.unpack("<I", mu.mem_read(a, 4))[0]
    return dict(r0=mu.reg_read(UC_ARM_REG_R0),
                passed=bool(hit_back),
                entry=list(struct.unpack("<12I", mu.mem_read(ENTRY, 48))),
                recipe=list(struct.unpack(f"<{RECIPE_WORDS}I",
                                          mu.mem_read(RECIPE, RECIPE_WORDS * 4))),
                axis=list(struct.unpack(f"<{len(axis)}I",
                                        mu.mem_read(AXIS, len(axis) * 4))),
                bitlatch=w(BITLATCH), pickok=w(PICKOK),
        fpslatch=w(FPSLATCH), hits=w(HITS),
                timing=lambda a: struct.unpack("<3I", mu.mem_read(a, 12)),
                sp=mu.reg_read(UC_ARM_REG_SP),
                r6=mu.reg_read(UC_ARM_REG_R6), mu=mu)


def test_native_menu_depth_overrides_stale_axis_before_recipe():
    for bit in (8, 10, 12, 14):
        raster = (5712, 3216) if bit == 14 else (3032, 2012)
        ax = axis_words(bit=12 if bit != 12 else 8, rate="30", raster=raster)
        got = run(ax, b"CUST24", depth=bit, menu_depth=bit)
        want = axis_words(bit=bit, rate="24", raster=raster)
        assert got["axis"] == list(want), (bit, got["axis"])
        assert got["recipe"] == expected_recipe(REG, want), bit
        assert got["bitlatch"] == MENU_BD[bit], bit
        assert got["pickok"] == 1, bit
        assert got["sp"] == STACK and got["r6"] == 0x40011200


def test_menu_depth_bridge_is_scoped_to_custom_key():
    got = run(OG3K, b"FHD24", depth=14, menu_depth=14)
    assert got["passed"] and got["axis"] == list(OG3K)


def test_native_callsite_contract_matches_firmware():
    # 同一 config 的 +0x20 由 r6 讀;三條 BL 返回點各自必須指向 picker。
    assert struct.unpack_from("<I", IMG, 0xC043B8B8 - B)[0] == 0xE5962020
    for end in set(MENU_RETURN.values()):
        insn = struct.unpack_from("<I", IMG, end - 4 - B)[0]
        disp = insn & 0xFFFFFF
        if disp & 0x800000:
            disp -= 0x1000000
        assert insn >> 24 == 0xEB and end + 4 + disp * 4 == 0xC043CCF8


def test_bit_bridge_mutation_is_detected():
    blob = bytearray(assemble("imx410_fmt.S", defines=FMT_DEFS))
    offset = symbols("imx410_fmt.S", defines=FMT_DEFS)["bs_store"] + 20
    assert struct.unpack_from("<I", blob, offset)[0] & 0xFFF00000 == 0x15800000
    blob[offset:offset + 4] = bytes.fromhex("0000a0e1")
    got = run(axis_words(bit=12, rate="24", raster=(5712, 3216)),
              b"CUST24", depth=14, menu_depth=14, fmt_blob=bytes(blob))
    assert got["axis"][0] != 14, "突變未改變結果:位深同步測試無效"


OG3K = axis_words(bit=12, rate="30", raster=(3032, 2012))


def test_hit_builds_entry():
    r = run(OG3K, b"CUST30")
    want = expected_recipe(REG, OG3K)
    assert not r["passed"], "不應該放行"
    assert r["r0"] == ENTRY, hex(r["r0"])
    e = r["entry"]
    assert e[0] == 5, e
    assert e[1] == PROFILE, e
    assert e[2] == want[R_MODE] == 98, e
    assert e[3] == ENTRY + 0x14, hex(e[3])
    # 鍵照抄到 +0x14
    assert struct.pack("<2I", e[5], e[6]).rstrip(b"\x00") == b"CUST30"
    assert r["pickok"] == 1 and r["bitlatch"] == 0 and r["hits"] == 1


def test_hit_writes_timing_record():
    """donor 時序記錄要被寫成 RECIPE 算出來的兩個字。"""
    r = run(OG3K, b"CUST30")
    want = expected_recipe(REG, OG3K)
    rec_addr = 0xC0B59500 + want[R_IDX] * 0x20
    assert r["entry"][4] == rec_addr, (hex(r["entry"][4]), hex(rec_addr))
    got = r["timing"](rec_addr)
    assert got[1] == want[R_TW0], (hex(got[1]), hex(want[R_TW0]))
    assert got[2] == want[R_TW1], (hex(got[2]), hex(want[R_TW1]))
    # OG3K30 = 445/735/5398,與出貨值相同
    assert got[1] == 445 | (735 << 16)
    assert got[2] == 5398 | (4 << 16)


def test_bit_depth_latch_per_table():
    for depth, code in BD.items():
        r = run(axis_words(bit=depth, rate="30", raster=(3032, 2012)),
                b"CUST30", depth=depth)
        assert not r["passed"], depth
        assert r["bitlatch"] == code, (depth, r["bitlatch"], code)


def test_foreign_key_passes_through():
    """不是我們的鍵就完整走原廠 —— 一個鎖存都不能碰。"""
    for key in (b"FHD30", b"UHD30", b"OG3K30"):
        r = run(OG3K, key)
        assert r["passed"], key
        assert r["hits"] == 0 and r["pickok"] == 0, key


def test_foreign_table_passes_through():
    """不在三張 picker 表裡的查詢一律放行。"""
    mu = Uc(UC_ARCH_ARM, UC_MODE_ARM)
    for base, size in ((0x40000000, 0x40000), (0xC0430000, 0x10000),
                       (0xC0700000, 0x100000), (0xC0B00000, 0x200000),
                       (0xC2F00000, 0x100000), (0xC3400000, 0x100000)):
        mu.mem_map(base, size)
    mu.mem_write(0xC0B00000, IMG[0xC0B00000 - B: 0xC0D00000 - B])
    mu.mem_write(FMT_CODE, assemble("imx410_fmt.S", defines=FMT_DEFS))
    hit = []
    mu.hook_add(UC_HOOK_CODE,
                lambda u, a, sz, d: (hit.append(a), u.emu_stop())
                if a == BACK else None)
    mu.mem_write(0x40011000, b"CUST30\x00\x00")
    mu.reg_write(UC_ARM_REG_R1, 0xC0BE0000)
    mu.reg_write(UC_ARM_REG_R2, 0x40011000)
    mu.reg_write(UC_ARM_REG_SP, STACK)
    mu.reg_write(UC_ARM_REG_LR, DONE)
    mu.emu_start(FMT_CODE, DONE, count=100000)
    assert hit, "不認識的表應該放行"


def test_fallback_gives_fhd_not_uhd():
    """3032x2012 跑 119.88 沒有 mode -> 回 FHD30,不是原廠那個 UHD30。"""
    ax = axis_words(bit=12, rate="120", raster=(3032, 2012))
    r = run(ax, b"CUST120")
    assert not r["passed"], "fallback 不應該放行給原廠"
    assert r["recipe"][9] == 0, "valid 應該是 0"
    assert r["pickok"] == 0, "PICKOK 要清掉,顯示鏈才會退回 16:9"
    assert r["r0"] == TAB[12] + 7 * 16, (hex(r["r0"]), hex(TAB[12] + 7 * 16))
    # 那一格在映像裡確實是 FHD30
    off = TAB[12] + 7 * 16 - B
    kp = struct.unpack_from("<I", IMG, off + 0xC)[0]
    end = IMG.index(b"\x00", kp - B)
    assert IMG[kp - B:end] == b"FHD30", IMG[kp - B:end]
    # 而原廠的退回是 TAB3[0] = UHD30 —— 確認我們真的沒給那個
    kp0 = struct.unpack_from("<I", IMG, TAB[12] - B + 0xC)[0]
    assert IMG[kp0 - B:IMG.index(b"\x00", kp0 - B)] == b"UHD30"
    assert r["r0"] != TAB[12]


def test_cached_recipe_still_fills_entry():
    """AXIS 沒變、og3krecipe 立刻返回時,ENTRY 仍然要被完整填好。

    這是最容易寫錯的地方:把「重算」與「組表項」混在一起,第二次查詢就會
    拿到空的表項。
    """
    ax = OG3K
    want = expected_recipe(REG, ax)
    # 第一次跑完之後 RECIPE 已經有快照;第二次用同一份 RECIPE 當種子
    r1 = run(ax, b"CUST30")
    assert r1["entry"][2] == want[R_MODE]
    # 手動把 RECIPE 預先填成「已算好」的狀態再跑一次
    mu = Uc(UC_ARCH_ARM, UC_MODE_ARM)
    for base, size in ((0x40000000, 0x40000), (0xC0430000, 0x10000),
                       (0xC0700000, 0x100000), (0xC0B00000, 0x200000),
                       (0xC2F00000, 0x100000), (0xC3400000, 0x100000)):
        mu.mem_map(base, size)
    mu.mem_write(0xC0B00000, IMG[0xC0B00000 - B: 0xC0D00000 - B])
    mu.mem_write(DESC, struct.pack("<4I", 0xC0B59500, 70, 0xC0B59DC0, 70))
    mu.mem_write(IMAGER, struct.pack("<I", DESC))
    mu.mem_write(FMT_CODE, assemble("imx410_fmt.S", defines=FMT_DEFS))
    mu.mem_write(RECIPE_CODE, assemble("og3krecipe.S", defines=DEFS))
    mu.mem_write(RATETAB, rate_table())
    mu.mem_write(TMGTAB, timing_table())
    mu.mem_write(CTMPL, canvas_template(FILL, tuple(ax)))
    mu.mem_write(ASPTAB, aspect_q_table())
    mu.mem_write(RATESTR, ratestr_table())
    mu.mem_write(AXIS, struct.pack(f"<{len(ax)}I", *ax))
    mu.mem_write(RECIPE, struct.pack(f"<{RECIPE_WORDS}I", *want))   # 已算好
    mu.mem_write(ENTRY, b"\xEE" * 48)
    mu.mem_write(PROFILE_ID, struct.pack("<I", PROFILE))
    mu.mem_write(0x40011000, b"CUST30\x00\x00")
    mu.reg_write(UC_ARM_REG_R1, TAB[12])
    mu.reg_write(UC_ARM_REG_R2, 0x40011000)
    mu.reg_write(UC_ARM_REG_SP, STACK)
    mu.reg_write(UC_ARM_REG_LR, DONE)
    mu.emu_start(FMT_CODE, DONE, count=2_000_000)
    e = struct.unpack("<4I", mu.mem_read(ENTRY, 16))
    assert e[0] == 5 and e[1] == PROFILE and e[2] == want[R_MODE], e


# ---- 選單的格率 -> AXIS(§8.10)----------------------------------------------

def test_key_suffix_drives_the_rate_axis():
    """鍵的尾碼就是選單選的格率 —— 接回 AXIS,不用新增 hook。

    先前 AXIS 的格率只能從主機改,而 picker 的鍵裡一直帶著使用者真正選的
    那一個。這條測試釘住「選單說了算」。
    """
    for suffix, want in (("240", RATE_KEYS.index("240")),
                         ("23_98", RATE_KEYS.index("23_98")),
                         ("60", RATE_KEYS.index("60"))):
        got = run(OG3K, b"CUST" + suffix.encode())
        assert got["axis"][A_RATE] == want, (suffix, got["axis"][A_RATE], want)


def test_matching_rate_is_left_alone():
    """尾碼與 AXIS 相同時不要寫 —— 白寫會白白觸發一次重算。"""
    got = run(OG3K, b"CUST30")
    assert got["axis"][A_RATE] == RATE_KEYS.index("30")
    assert got["axis"] == list(OG3K), got["axis"]


def test_unknown_suffix_leaves_the_axis_alone():
    """對不到就不動 —— fail-open,沿用主機值。"""
    for suffix in (b"ZZZ", b"", b"2400", b"3"):
        got = run(OG3K, b"CUST" + suffix)
        assert got["axis"][A_RATE] == OG3K[A_RATE], (suffix, got["axis"])


def test_suffix_match_requires_the_whole_string():
    """`24` 不可以命中 `240`,`240` 也不可以命中 `24` —— 兩邊都要到 NUL。"""
    a = run(OG3K, b"CUST24")["axis"][A_RATE]
    b_ = run(OG3K, b"CUST240")["axis"][A_RATE]
    assert a == RATE_KEYS.index("24"), a
    assert b_ == RATE_KEYS.index("240"), b_
    assert a != b_


def test_row_nine_ram_flag_turns_120_into_240():
    """⛔ 第一守則:原廠只存 119.88;選第十列(239.76)時只有記憶體記號 RATE240 知道。

    鍵尾碼 "120" + 記號 1 -> AXIS 240;記號 0 -> 119.88;其他尾碼不受記號影響。
    """
    i120, i240 = RATE_KEYS.index("120"), RATE_KEYS.index("240")
    assert run(OG3K, b"CUST120", rate240=0)["axis"][A_RATE] == i120
    assert run(OG3K, b"CUST120", rate240=1)["axis"][A_RATE] == i240
    for suffix in ("60", "30", "23_98", "100"):
        got = run(OG3K, b"CUST" + suffix.encode(), rate240=1)["axis"][A_RATE]
        assert got == RATE_KEYS.index(suffix), (suffix, got)
    assert RATE240 == __import__("imx410_rate_native").RATE240


def test_rate_string_table_matches_the_firmware_pool():
    """我們的字串表要和原廠 0xC0BE4800 的字串池逐字一致。

    鍵是韌體用那個池組出來的,我們比對的是同一批字。對不上就永遠不會命中。
    """
    pool = IMG[0xC0BE4800 - B: 0xC0BE4840 - B]
    have = {s for s in pool.split(b"\0") if s}
    ours = {k.encode() for k in RATE_KEYS}
    assert ours <= have, ours - have


def _run():
    fns = [(n, f) for n, f in sorted(globals().items())
           if n.startswith("test_") and callable(f)]
    bad = 0
    for n, f in fns:
        try:
            f()
            print(f"  ok   {n}")
        except AssertionError as e:
            bad += 1
            print(f"  FAIL {n}: {e}")
    print(f"\n{len(fns) - bad}/{len(fns)} passed")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(_run())
