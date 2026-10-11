#!/usr/bin/env python3
"""imx410_canvas.S:走 og3krecipe 產生的陣列,只寫該寫的欄位。

畫布就是一整列 PARAM profile(65 個字),所以「有沒有多寫到別的欄位」和
「該寫的有沒有寫對」一樣重要 —— 多寫一欄就是改了一個我們不懂的 profile 欄位。
每個測試都會比對整列 65 個字。

    python3 test_imx410_canvas.py
"""
from __future__ import annotations

import pathlib
import struct
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from unicorn import UC_ARCH_ARM, UC_MODE_ARM, Uc
from unicorn.arm_const import (UC_ARM_REG_LR, UC_ARM_REG_R0, UC_ARM_REG_R4,
                               UC_ARM_REG_R5, UC_ARM_REG_SP)

from armasm import assemble
from imx410_block import axis_words, expected_canvas
from imx410_full import Registry

CODE = 0x40000000
CANVAS = 0x40010000
OBJ = 0x40020000            # r4;畫布在 r4 + 0x5C
STACK = 0x40030000
DONE = 0x40031000
LOG = 0xC0732A00
FPSLATCH = 0xC0731C40
import imx410_plan as _PL
PROFILE = _PL.PRIVATE_PROFILE      # 我們宣告的 id(2026-10-04 起不再是原廠 p83)
PROFILE_ID = _PL.PROFILE_ID
ROW = 0x5C
NWORDS = 66                 # 0x00..0x104

REG = Registry()
DEFS = [f"CANVAS={CANVAS:#x}", f"PROFILE_ID={PROFILE_ID:#x}"]
SEED = [0xD0D00000 + i for i in range(NWORDS)]      # 可辨識的原始內容


def run(pairs, *, profile=PROFILE, count=None, fpslatch=0, published=PROFILE):
    mu = Uc(UC_ARCH_ARM, UC_MODE_ARM)
    mu.mem_map(0x40000000, 0x00040000)
    mu.mem_map(0xC0700000, 0x00100000)

    mu.mem_write(CODE, assemble("imx410_canvas.S", defines=DEFS))
    n = len(pairs) if count is None else count
    blk = struct.pack("<I", n)
    for off, val in pairs:
        blk += struct.pack("<2I", off, val)
    blk += b"\x00" * (4 + 40 * 8 - len(blk))
    mu.mem_write(CANVAS, blk)
    mu.mem_write(FPSLATCH, struct.pack("<I", fpslatch))
    mu.mem_write(PROFILE_ID, struct.pack("<I", published))
    mu.mem_write(LOG, b"\x00" * 16)
    mu.mem_write(OBJ + ROW, struct.pack(f"<{NWORDS}I", *SEED))

    mu.reg_write(UC_ARM_REG_R4, OBJ)
    mu.reg_write(UC_ARM_REG_R5, profile)
    mu.reg_write(UC_ARM_REG_R0, 0xBAD0BAD0)
    mu.reg_write(UC_ARM_REG_SP, STACK)
    mu.reg_write(UC_ARM_REG_LR, DONE)
    mu.emu_start(CODE, DONE, count=100000)

    after = list(struct.unpack(f"<{NWORDS}I", mu.mem_read(OBJ + ROW, NWORDS * 4)))
    return dict(r0=mu.reg_read(UC_ARM_REG_R0), canvas=after,
                hits=struct.unpack("<I", mu.mem_read(LOG, 4))[0],
                last_prof=struct.unpack("<I", mu.mem_read(LOG + 8, 4))[0])



def test_only_our_declared_profile_is_touched():
    """2026-10-04:守衛比的是 PROFILE_ID 這個 RAM 字,不是寫死的原廠 id。
    原廠 p83(拍照表也引用它)不再被改寫;id 還沒公布(0)時誰都不碰。"""
    pairs = [(0x00, 1234), (0x04, 567)]
    assert run(pairs)["canvas"] == _expect(pairs)
    for other in (_PL.PROFILE, 13, 0):
        r = run(pairs, profile=other)
        assert r["canvas"] == SEED and r["hits"] == 0, other
    r = run(pairs, published=0)                    # 還沒公布
    assert r["canvas"] == SEED and r["hits"] == 0

def _expect(pairs, fpslatch=0):
    """套用這些 (位移, 值) 之後整列應該長什麼樣。"""
    want = list(SEED)
    for off, val in pairs:
        want[off // 4] = val
    if fpslatch:
        want[0x30 // 4] = fpslatch
    return want


CASES = [
    ("OG3K 等價", dict(bit=12, rate="30", raster=(3032, 2012))),
    ("OG2K 等價", dict(bit=12, rate="60", raster=(2016, 1344))),
    ("HSW 等價", dict(bit=12, rate="240", raster=(2016, 672))),
    ("全幅 hbin3", dict(bit=12, rate="24", raster=(6064, 4042), hbin=3, vbin=3)),
    ("8-bit", dict(bit=8, rate="30", raster=(3032, 2012))),
    ("10-bit", dict(bit=10, rate="30", raster=(3032, 2012))),
    ("240 fps(欄位最多)", dict(bit=12, rate="240", raster=(2016, 672))),
    ("RWZM 2048", dict(bit=12, rate="24", raster=(6064, 4042),
                       hbin=3, vbin=3, rwzm=(2048, 2048))),
]


def test_canvas_block_is_big_enough():
    """模板全開時的對數,不可以超過 .S 的 MAX_PAIRS 或區塊容量。

    2026-09-28 加了 bin/RWZM 八欄之後模板從 21 筆變 29 筆,而 .S、CANVAS
    區塊與測試 harness 三處都還寫死 24 —— >60 fps 那組就寫爆出去。
    """
    import re
    from imx410_block import CANVAS_MAX_PAIRS, CANVAS_TEMPLATE
    src = pathlib.Path("imx410_canvas.S").read_text()
    m = re.search(r"\.equ\s+MAX_PAIRS,\s*(\d+)", src)
    assert m, "imx410_canvas.S 沒有 MAX_PAIRS"
    assert len(CANVAS_TEMPLATE) <= CANVAS_MAX_PAIRS, len(CANVAS_TEMPLATE)
    assert int(m.group(1)) == CANVAS_MAX_PAIRS, (m.group(1), CANVAS_MAX_PAIRS)
    worst = max(len(expected_canvas(REG, axis_words(**kw))) for _, kw in CASES)
    assert worst <= CANVAS_MAX_PAIRS, worst


def test_preview_and_producer_are_not_written():
    """★ 預覽管線只能趨近 fp 的 LCD 解析度,不能跟著錄影光柵走。

    2026-09-28:原廠 p13 預覽光柵 1920x1280、p83 是 2024x1341,而 LCD 是
    1024x682 —— 那些是顯示路徑的緩衝,約 LCD 的兩倍。把它們撐到 3024x2012
    讓總配置從 13.7 MB 變 33.5 MB,而 IMAGE 池只剩 3,520 B。

    預覽的比例由 GTAB 那一組(六個預覽 profile 的可見高)處理,不是畫布。
    OG3K 的 write_active/producer/preview 全 False 就是這個道理。
    """
    from imx410_block import R_RECH, R_RECW, expected_recipe, pick_profile
    forbidden = {0x0C, 0x10, 0x20, 0x28, 0xD8, 0xE0}
    for label, kw in CASES:
        ax = axis_words(**kw)
        r = expected_recipe(REG, ax)
        if not r[9]:
            continue
        _pid, fill, _d, _n = pick_profile((r[R_RECW], r[R_RECH]))
        offs = {o for o, _ in expected_canvas(REG, ax)}
        if fill:
            # 空殼 donor **必須**填滿 —— 不填就是拿 rec=0/act=0 去錄影
            assert forbidden <= offs, (label, "空殼沒填滿")
        else:
            # 原生完整的不要寫,預覽管線只能趨近 LCD 解析度
            assert not (offs & forbidden), (label, sorted(map(hex, offs & forbidden)))


def test_allocation_stays_under_og3k():
    """總配置不可以超過 OG3K —— 那是唯一一個已知錄得起來的組態。"""
    import importlib.util
    spec = importlib.util.spec_from_file_location("sz", pathlib.Path("sizesim.py"))
    sz = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(sz)
    except SystemExit:
        pass

    def canvas(p):
        row = sz.w32(sz.MAP + p * 4)
        return [sz.w32(b + row * 4) for b in sz.COL] + [0x17b0, 0xfca]

    from imx410_block import R_RECH, R_RECW, expected_recipe, pick_profile
    OG3K_TOTAL = 15_067_664
    for label, kw in CASES:
        r0 = expected_recipe(REG, axis_words(**kw))
        if not r0[9]:
            continue
        c = list(canvas(pick_profile((r0[R_RECW], r0[R_RECH]))[0]))
        for o, v in expected_canvas(REG, axis_words(**kw)):
            if o // 4 < len(c) - 2:
                c[o // 4] = v
        tot = sz.total(c, 1024, 682)
        assert tot <= OG3K_TOTAL, f"{label}: {tot:,} > OG3K {OG3K_TOTAL:,}"


def test_writes_exactly_the_pairs():
    """該寫的寫對,**其他 65 個字一個都不能動**。"""
    for label, kw in CASES:
        pairs = expected_canvas(REG, axis_words(**kw))
        r = run(pairs)
        want = _expect(pairs)
        assert r["canvas"] == want, (
            label,
            [(hex(i * 4), hex(a), hex(b))
             for i, (a, b) in enumerate(zip(r["canvas"], want)) if a != b])
        assert r["hits"] == 1, label


def test_engine_fps_written_separately():
    pairs = expected_canvas(REG, axis_words(bit=12, rate="30",
                                            raster=(3032, 2012)))
    r = run(pairs, fpslatch=0x41F00000)
    assert r["canvas"] == _expect(pairs, 0x41F00000)
    # 鎖存是 0 就不要寫 —— 那代表 imx410_fmt 還沒命中過
    r0 = run(pairs, fpslatch=0)
    assert r0["canvas"][0x30 // 4] == SEED[0x30 // 4]


def test_other_profile_untouched():
    """守衛:不是我們的 profile 就一個字都不碰。"""
    pairs = expected_canvas(REG, axis_words(bit=12, rate="30",
                                            raster=(3032, 2012)))
    for prof in (175, 171, 12, 14):   # 都不是我們挑到的那一個
        r = run(pairs, profile=prof)
        assert r["canvas"] == SEED, prof
        assert r["hits"] == 0, prof
        assert r["last_prof"] == prof, prof      # log 仍然記錄看到了誰


def test_empty_recipe_touches_nothing():
    """沒有配方(對數 0)-> 什麼都不寫。這是 og3krecipe 解不出來時的狀態。"""
    r = run([], count=0)
    assert r["canvas"] == SEED
    assert r["hits"] == 0


def test_absurd_count_is_refused():
    """對數不合理就當資料壞了,故障安全 —— 不要拿垃圾去寫 profile。"""
    pairs = expected_canvas(REG, axis_words(bit=12, rate="30",
                                            raster=(3032, 2012)))
    r = run(pairs, count=33)
    assert r["canvas"] == SEED
    assert r["hits"] == 0


def test_returns_r4_for_displaced_instruction():
    """位移的原指令是 mov r0, r4 —— 每一條路徑都要補做。"""
    pairs = expected_canvas(REG, axis_words(bit=12, rate="30",
                                            raster=(3032, 2012)))
    assert run(pairs)["r0"] == OBJ
    assert run(pairs, profile=83)["r0"] == OBJ
    assert run([], count=0)["r0"] == OBJ


def test_hirate_fields_only_above_60():
    lo = expected_canvas(REG, axis_words(bit=12, rate="60",
                                         raster=(2016, 1344)))
    hi = expected_canvas(REG, axis_words(bit=12, rate="240",
                                         raster=(2016, 672)))
    rlo, rhi = run(lo), run(hi)
    for off in (0xB0, 0xDC, 0xE4):
        assert rlo["canvas"][off // 4] == SEED[off // 4], hex(off)
        assert rhi["canvas"][off // 4] != SEED[off // 4], hex(off)
    # scale float 不再在 >60 寫死 2.0:它是 mode 自己的縮減倍數,由宣告列給(2026-10-04)
    for off in (0xFC, 0x100):
        assert rlo["canvas"][off // 4] == rhi["canvas"][off // 4] == SEED[off // 4], hex(off)


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
