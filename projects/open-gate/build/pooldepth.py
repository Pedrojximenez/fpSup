#!/usr/bin/env python3
"""把 CinemaDNG 的描述子池從原廠的 96 格加大 —— 240 fps 爆發長度的天花板。

`vbuf` 每一格跟 `MPoolFixed<4380U, 96U>` 要一個描述子,寫完才歸還。感測器
給 240 而寫入端只吃得下約 130,淨流失約 110 格/秒,所以 96 格 = 約 0.87 秒
就抽乾,然後 `FUN_c0374268` 回 -1、錄影正常停止(§53)。塊數是編譯期常數,
不是設定。

每一格在途要的記憶體:
    描述子   4,392 B  (4380 + 12 表頭)          <- 這支加大的東西
    影格緩衝 0x15400 + round512(frame)          <- 從 RAW(heap 10)配,實測剩 518 MB

所以加大幾乎不花錢:300 格的池子本身只有 1.3 MB,影格那邊 413 MB 落在 RAW
的餘裕內(MOVIE_REC_DNG 模式下 RAW 比 STILL_REC 還大)。

    ./pooldepth.py show
    ./pooldepth.py on 300
    ./pooldepth.py off

★ 必須在相機**已經切到 CINE / CinemaDNG**(mem mode = MOVIE_REC_DNG)之後才做:
  記憶體分割是按功能模式重配的,換模式會把這塊配置丟掉。換了模式就要重跑
  `on`。拔電池一切還原。
"""
import argparse, json, pathlib, re, sys, time

HERE = pathlib.Path(__file__).resolve().parent
SHELL = HERE.parent.parent.parent / "fpSup" / "fp_usb_shell"
sys.path.insert(0, str(SHELL))
from armasm import assemble                                    # noqa: E402
from putfile import sh, mem_get, mem_set, put                   # noqa: E402
import callfn                                                   # noqa: E402

POOL_PTR = 0xC2F1F3D8          # 池物件指標
VPTR     = 0xC0B99474          # MPoolFixed<4380U,96U> 的 vtable
HDR      = 0x1130              # 表頭長度 = node0 的位移
STRIDE   = 0x1128              # 4380 + 12
COUNT    = 0x112C              # free count 的位移
STOCK_N  = 96

# 兩顆界線常數,各由一對 movw/movt 組成,值都是 (N-1) * STRIDE
BOUNDS = (
    (0xC0380CB8, 0xC0380CBC, "MPoolFixed::v2 釋放界線"),
    (0xC0380EF0, 0xC0380EF4, "MPoolFixed::v4 範圍界線"),
)

MEMSET = 0xC0015058            # FUN_c0015058(dst, val, len)
CAVE   = 0xC0730600            # poolbuild payload

# 池子要配在**原廠放它的那個 heap**,不是 NonCacheBuffer。
# 2026-09-21 第一次上機用 `memmgr bufmem get 10`(RAW)配,相機在 240 fps 下把
# USB worker 一起拖死。RAW 是給 DMA 影格資料的非快取區,而描述子是每一格都要
# 密集讀寫的 4,380 位元組結構 —— 放在非快取記憶體上每格的成本高一個數量級。
# 原廠的 0xC3520CD0 來自全域 C++ heap(FUN_c001D9B8 -> DAT_c2ef7244 的 vtable+0xC),
# 所以這裡走同一條路。
CHEAP_NEW = 0xC001D9B8         # new(size) -> ptr
CHEAP_PTR = 0xC2EF7244         # heap 物件指標;free 是它 vtable 的 +0x10
STATE  = HERE / ".pooldepth_state.json"


def cheap_free(ptr):
    """呼叫那個 heap 自己的 delete。"""
    obj = rd(CHEAP_PTR)[0]
    fn = rd(rd(obj)[0] + 0x10)[0]
    return callfn.call(fn, r0=obj, r1=ptr, verbose=False)[0]


def heap_free_bytes():
    m = re.search(r"free (\d+) : max_free (\d+)",
                  sh("memmgr heapmem", timeout_ms=6000))
    return (int(m.group(1)), int(m.group(2))) if m else (None, None)


def rd(a, n=1, tries=8):
    for _ in range(tries):
        w = mem_get(a, n)
        if w and all(x is not None for x in w):
            return w
    raise SystemExit(f"讀不到 0x{a:08X}")


def wr(a, v, tries=10):
    for _ in range(tries):
        if rd(a)[0] == v:
            return
        mem_set(a, v & 0xFFFFFFFF)
    raise SystemExit(f"寫不進 0x{a:08X} = 0x{v:08X}")


def imm16(word, value):
    """把 movw / movt 的 16 位立即數換掉,其餘位元不動。"""
    return (word & ~0x000F0FFF) | (((value >> 12) & 0xF) << 16) | (value & 0xFFF)


def mem_mode():
    out = sh("memmgr bufuse", timeout_ms=5000)
    m = re.search(r"mem mode = (\w+) \((\d+)\)", out)
    return (m.group(1), int(m.group(2))) if m else (None, None)


def raw_free():
    out = sh("memmgr bufuse", timeout_ms=5000)
    m = re.search(r"RAW\s+\(10\):.*?\[total:\s*(\d+)\].*?\[remaining:\s*(\d+)\]", out)
    return (int(m.group(1)), int(m.group(2))) if m else (None, None)


def show():
    mode, mid = mem_mode()
    total, free = raw_free()
    obj = rd(POOL_PTR)[0]
    cnt = rd(obj + COUNT)[0]
    print(f"mem mode        {mode} ({mid})")
    if total:
        print(f"RAW(10)         total {total/2**20:.0f} MB   remaining {free/2**20:.0f} MB")
    print(f"池物件          0x{obj:08X}   vptr 0x{rd(obj)[0]:08X}")
    print(f"free count      {cnt}")
    print(f"sentinel        next 0x{rd(obj+4)[0]:08X}  prev 0x{rd(obj+8)[0]:08X}")
    for lo, hi, what in BOUNDS:
        w0, w1 = rd(lo)[0], rd(hi)[0]
        span = ((w0 & 0xFFF) | ((w0 >> 4) & 0xF000)) | \
               (((w1 & 0xFFF) | ((w1 >> 4) & 0xF000)) << 16)
        print(f"{what}  0x{span:X} = {span // STRIDE + 1} 格")
    st = json.loads(STATE.read_text()) if STATE.is_file() else {}
    if st:
        print(f"狀態檔          已安裝 N={st['n']} @ 0x{st['obj']:08X}")


def on(n, force=False, dry=False, allow_orphans=False):
    if not 96 < n <= 4096:
        raise SystemExit("N 要在 97..4096 之間")
    mode, mid = mem_mode()
    if mid != 3 and not force and not dry:
        raise SystemExit(f"mem mode 是 {mode}({mid}),不是 MOVIE_REC_DNG(3)。"
                         "先把相機切到 CINE + CinemaDNG,或用 --force。")
    if STATE.is_file() and not dry:
        raise SystemExit("已經裝過了,先跑 off")

    old = rd(POOL_PTR)[0]
    cnt = rd(old + COUNT)[0]
    if cnt != STOCK_N:
        # 舊池子少了幾格有兩種可能,結果天差地遠:
        #   (a) 真的有描述子在途 —— 它們遲早會被釋放,而釋放會落到**新**池子,
        #       位址過不了 MPoolFixed::v2 的界線檢查,串列會被寫壞。絕對不能換。
        #   (b) 上一段錄影的停止路徑把它們漏掉了(FUN_c0377118 只把在途的請求
        #       從串列上摘掉,沒有歸還描述子)—— 那些格子永遠不會再被釋放,
        #       所以換過去是安全的。
        # 分辨的方法:(b) 的計數是死的。所以要求「沒在錄影 + 計數穩定 + 串列
        # 長度與計數欄一致」三件事同時成立,才允許在漏格的池子上換。
        if not allow_orphans:
            raise SystemExit(
                f"舊池子只剩 {cnt}/{STOCK_N}。若是上一段錄影漏掉的(停止路徑的已知缺陷),"
                "用 --allow-orphans 明示;若不確定,冷開一次最乾淨。")
        if "-> 0" not in sh("status get is_recording", timeout_ms=3000):
            raise SystemExit("相機還在錄影,不能換")
        seen, cur = 0, rd(old + 4)[0]
        while cur != old + 4 and seen <= STOCK_N * 2:
            cur = rd(cur)[0]
            seen += 1
        if seen != cnt:
            raise SystemExit(f"自由串列長度 {seen} != count 欄 {cnt},池子狀態不一致,先冷開")
        time.sleep(5)
        if rd(old + COUNT)[0] != cnt:
            raise SystemExit("計數還在動 —— 真的有描述子在途,不能換")
        print(f"舊池子 {cnt}/{STOCK_N};{STOCK_N - cnt} 格是上一段錄影漏掉的,"
              "計數五秒內沒動,視為永不歸還")

    size = HDR + n * STRIDE
    hfree, hmax = heap_free_bytes()
    _, rawfree = raw_free()
    print(f"C heap 剩 {hfree/2**20:.2f} MB(最大連續 {hmax/2**20:.2f} MB),"
          f"池子要 {size/2**20:.2f} MB")
    print(f"RAW 剩 {rawfree/2**20:.0f} MB,{n} 格在途的影格要約 "
          f"{n*1441792/2**20:.0f} MB")
    if hmax is not None and size > hmax:
        raise SystemExit("C heap 的最大連續區塊放不下")
    if rawfree is not None and n * 1441792 > rawfree:
        raise SystemExit("RAW 放不下這麼多在途影格")

    ok, obj = callfn.call(CHEAP_NEW, r0=size, verbose=False)
    if not ok or not obj:
        raise SystemExit(f"C heap 配置失敗(回傳 {obj})")
    print(f"配到 0x{obj:08X}  {size} bytes(C heap,與原廠 0x{old:08X} 同一個)")

    ok, _ = callfn.call(MEMSET, r0=obj, r1=0, r2=size, verbose=False)
    if not ok:
        raise SystemExit("memset 沒有回來")
    print(f"清零 {size} bytes")

    put(CAVE, assemble(HERE / "poolbuild.S"), "poolbuild")
    ok, ret = callfn.call(CAVE, r0=obj, r1=n, verbose=False)
    if not ok or ret != n:
        raise SystemExit(f"poolbuild 失敗(回傳 {ret})")

    # 驗:表頭、哨兵、每一格的 guard 與鏈結
    wr(obj, VPTR)
    node0, last = obj + HDR, obj + HDR + (n - 1) * STRIDE
    checks = [(obj + COUNT, n), (obj + 4, node0), (obj + 8, last),
              (node0 + 4, obj + 4), (last, obj + 4)]
    for a, want in checks:
        got = rd(a)[0]
        if got != want:
            raise SystemExit(f"驗證失敗 0x{a:08X} = 0x{got:08X},應該是 0x{want:08X}")
    for i in (1, n // 2, n - 1):
        node = obj + HDR + i * STRIDE
        if rd(node + 8)[0] != 0xFAFAFEFE:
            raise SystemExit(f"node[{i}] 的 guard 不對")
        if rd(node + 4)[0] != node - STRIDE:
            raise SystemExit(f"node[{i}] 的 prev 不對")
    print(f"串列驗過:{n} 格,node0 0x{node0:08X} .. last 0x{last:08X}")

    if dry:
        cheap_free(obj)
        print("\n★ dry:串列蓋得出來也驗得過,記憶體已歸還,韌體一個位元都沒動。")
        return

    span = (n - 1) * STRIDE
    saved = []
    for lo, hi, what in BOUNDS:
        w0, w1 = rd(lo)[0], rd(hi)[0]
        saved.append((lo, w0, hi, w1))
        wr(lo, imm16(w0, span & 0xFFFF))
        wr(hi, imm16(w1, (span >> 16) & 0xFFFF))
        print(f"{what} -> 0x{span:X}")

    wr(POOL_PTR, obj)
    STATE.write_text(json.dumps({"n": n, "obj": obj, "size": size,
                                 "old": old, "bounds": saved}))
    print(f"\n★ 池深 {STOCK_N} -> {n}。同樣條件下 240 fps 的爆發長度變成約 "
          f"{n / 110:.1f} 秒(寫入端 130 fps 時)。")
    print("  換 CINE/STILL 模式會丟掉這塊記憶體 —— 換過就要重跑 on。")


def off():
    if not STATE.is_file():
        raise SystemExit("沒有狀態檔,沒有東西要還原")
    st = json.loads(STATE.read_text())
    obj, n = st["obj"], st["n"]
    if rd(POOL_PTR)[0] == obj:
        cnt = rd(obj + COUNT)[0]
        if cnt != n:
            raise SystemExit(f"池子剩 {cnt}/{n} —— 有描述子在途,現在換回去會壞。")
        wr(POOL_PTR, st["old"])
        print(f"池物件指標還原 0x{st['old']:08X}")
    for lo, w0, hi, w1 in st["bounds"]:
        wr(lo, w0)
        wr(hi, w1)
    print("界線常數還原")
    cheap_free(obj)
    for i in range(0, 124, 4):
        mem_set(CAVE + i, 0)
    STATE.unlink()
    print("記憶體歸還、payload 清掉")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("cmd", choices=("show", "on", "off"))
    ap.add_argument("n", nargs="?", type=lambda s: int(s, 0), default=300)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--allow-orphans", action="store_true",
                    help="舊池子有上一段錄影漏掉的格子時仍然安裝(會先驗計數是死的)")
    ap.add_argument("--dry", action="store_true",
                    help="配置、蓋串列、驗完就歸還,不改韌體也不換指標")
    a = ap.parse_args()
    {"show": show, "on": lambda: on(a.n, a.force, a.dry, a.allow_orphans), "off": off}[a.cmd]()


if __name__ == "__main__":
    main()
