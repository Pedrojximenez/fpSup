"""鏡頭全資料下載 — 借用韌體自帶握手的 L-mount 讀取 API。

之前直接對鏡頭下請求會讀出全 FF 並跳「鏡頭異常」,原因是沒拿匯流排 mutex。
韌體的 CmdRead 路徑自己會做 PreCommunicationSequence(取鎖)/釋放,所以借用它就對了:

    ctx = FUN_c03554a0()                    @0xC03554A0  (回傳 0xC347D098)
    ok  = FUN_c0355de0(ctx, blockId, dst)   @0xC0355DE0  區塊 ID 定址(查 ROM 表)
    ok  = CmdRead(ctx, addr, len, dst, 0)   @0xC0355BE0  任意位址定址

兩支注入常式的原始碼在 camera/lens_block_read.S / camera/lens_raw_read.S。
完整 RE 說明見 notes/LENS_BLOCK_API.md。
"""
import struct, time, socket, os
import telemetry

# 注入位址(避開 fpstate 的 PEEK_CODE 0xC072F100 與 push 常式 0xC072F600)
BLOCK_CAVE = 0xC072F200
RAW_CAVE   = 0xC072F300
RESULT     = 0xC072F700     # +0 arg  +4 ok  +8 len  +0xC nzcount  +0x10 起=資料
                            # ⚠️ 與 camera/telemetry_push.S 常式重疊(兩者不會同時跑);
                            #    dump 結束會清 sh._telem_ready,下次用 telemetry 時自動重注入。
ARG0       = 0xC072F070     # STATE+0x70
ARG1       = 0xC072F074     # STATE+0x74
MAX_LEN    = 0x900          # RESULT+0x10 到 0xC0730000 的可用空間

BLOCK_WORDS = (
    0xe92d47f0,
    0xe1a04000,
    0xe5945070,
    0xe30f6700,
    0xe34c6072,
    0xe3040368,
    0xe34c00b9,
    0xe3a0100c,
    0xe0010195,
    0xe0800001,
    0xe5907000,
    0xe5865000,
    0xe3a00000,
    0xe5860004,
    0xe5867008,
    0xe586000c,
    0xe30504a0,
    0xe34c0035,
    0xe12fff30,
    0xe1a01005,
    0xe2862010,
    0xe3053de0,
    0xe34c3035,
    0xe12fff33,
    0xe5860004,
    0xe2868010,
    0xe3a09000,
    0xe3a0a000,
    0xe15a0007,
    0xaa000007,
    0xe7d8000a,
    0xe3500000,
    0x0a000002,
    0xe35000ff,
    0x0a000000,
    0xe2899001,
    0xe28aa001,
    0xeafffff5,
    0xe586900c,
    0xe8bd87f0,
)

RAW_WORDS = (
    0xe92d47f0,
    0xe1a04000,
    0xe5945070,
    0xe5947074,
    0xe30f6700,
    0xe34c6072,
    0xe5865000,
    0xe3a00000,
    0xe5860004,
    0xe5867008,
    0xe586000c,
    0xe30504a0,
    0xe34c0035,
    0xe12fff30,
    0xe1a01005,
    0xe1a02007,
    0xe2863010,
    0xe3a08000,
    0xe3a09000,
    0xe92d0300,
    0xe305abe0,
    0xe34ca035,
    0xe12fff3a,
    0xe28dd008,
    0xe5860004,
    0xe2868010,
    0xe3a09000,
    0xe3a0a000,
    0xe15a0007,
    0xaa000007,
    0xe7d8000a,
    0xe3500000,
    0x0a000002,
    0xe35000ff,
    0x0a000000,
    0xe2899001,
    0xe28aa001,
    0xeafffff5,
    0xe586900c,
    0xe8bd87f0,
)

# fp Ver.5.02 ROM 區塊表 @0xC0B94364, stride 0x0C: (addr, len, flag)
# flag==1 → FUN_c0355e10 直接拒讀。換韌體版本要重抽。
BLOCK_TABLE = (
    (0x000000, 1, 1),   # id 0x00
    (0x000001, 1, 1),   # id 0x01
    (0x000002, 2, 1),   # id 0x02
    (0x000004, 2, 1),   # id 0x03
    (0x000006, 1, 1),   # id 0x04
    (0x000007, 4, 1),   # id 0x05
    (0x00000b, 1, 1),   # id 0x06
    (0x00000c, 2, 1),   # id 0x07
    (0x0001fa, 10, 0),   # id 0x08
    (0x000204, 33, 0),   # id 0x09
    (0x000204, 86, 0),   # id 0x0a
    (0x000204, 2, 0),   # id 0x0b
    (0x000206, 2, 0),   # id 0x0c
    (0x000208, 2, 0),   # id 0x0d
    (0x00020a, 4, 0),   # id 0x0e
    (0x00020e, 4, 0),   # id 0x0f
    (0x0002ff, 1, 0),   # id 0x10
    (0x000400, 2, 2),   # id 0x11
    (0x000402, 2, 2),   # id 0x12
    (0x000404, 2, 2),   # id 0x13
    (0x000406, 1, 2),   # id 0x14
    (0x000407, 1, 2),   # id 0x15
    (0x000408, 1, 2),   # id 0x16
    (0x000409, 2, 2),   # id 0x17
    (0x00040b, 1, 2),   # id 0x18
    (0x00040c, 2, 2),   # id 0x19
    (0x00040e, 1, 2),   # id 0x1a
    (0x00040f, 1, 2),   # id 0x1b
    (0x000410, 2, 2),   # id 0x1c
    (0x000412, 1, 2),   # id 0x1d
    (0x000413, 1, 2),   # id 0x1e
    (0x000414, 2, 2),   # id 0x1f
    (0x000416, 2, 2),   # id 0x20
    (0x000418, 1, 2),   # id 0x21
    (0x000419, 1, 2),   # id 0x22
    (0x00041a, 2, 2),   # id 0x23
    (0x00041c, 1, 2),   # id 0x24
    (0x00041d, 1, 2),   # id 0x25
    (0x00041e, 2, 2),   # id 0x26
    (0x0003e0, 1, 0),   # id 0x27
    (0x0003f0, 1, 0),   # id 0x28
    (0x000c00, 6, 2),   # id 0x29
    (0x000c00, 3, 2),   # id 0x2a
    (0x000c03, 2, 2),   # id 0x2b
    (0x000c05, 1, 2),   # id 0x2c
    (0x000c06, 59, 2),   # id 0x2d
    (0x000c42, 4, 2),   # id 0x2e
    (0x000c46, 2, 2),   # id 0x2f
    (0x000c48, 2, 2),   # id 0x30
    (0x000c56, 2, 2),   # id 0x31
    (0x000c60, 2, 2),   # id 0x32
    (0x000c62, 3, 2),   # id 0x33
    (0x000c65, 3, 2),   # id 0x34
    (0x000c68, 3, 2),   # id 0x35
    (0x000c6b, 3, 2),   # id 0x36
    (0x000c80, 2, 2),   # id 0x37
    (0x000c8e, 3, 0),   # id 0x38
    (0x000c91, 3, 0),   # id 0x39
    (0x000c94, 3, 0),   # id 0x3a
    (0x000c97, 3, 0),   # id 0x3b
    (0x000dff, 1, 2),   # id 0x3c
    (0x000e00, 43, 2),   # id 0x3d
    (0x000f37, 46, 2),   # id 0x3e
    (0x000f67, 83, 2),   # id 0x3f
    (0x000fba, 83, 2),   # id 0x40
    (0x001161, 122, 2),   # id 0x41
    (0x010030, 126, 2),   # id 0x42
    (0x010062, 8, 2),   # id 0x43
    (0x000400, 1, 1),   # id 0x44
    (0x000500, 1, 0),   # id 0x45
    (0x000580, 13, 0),   # id 0x46
    (0x000520, 402, 2),   # id 0x47
    (0x000b4f, 48, 2),   # id 0x48
    (0x000b0c, 1, 2),   # id 0x49
    (0x00100d, 3, 2),   # id 0x4a
    (0x011040, 2101, 2),   # id 0x4b
    (0x012000, 2, 2),   # id 0x4c
    (0x012002, 16, 2),   # id 0x4d
    (0x012023, 600, 2),   # id 0x4e
    (0x000500, 11, 0),   # id 0x4f
    (0x000500, 24, 0),   # id 0x50
    (0x000500, 30, 0),   # id 0x51
)

# 韌體區塊表沒涵蓋、但實測有資料的位址區(Panasonic 鏡頭把校正資料放這裡)
RAW_SWEEPS = ((0x000000, 0x002000), (0x010000, 0x013000))


def _inject(sh, cave, words):
    for i, w in enumerate(words):
        sh._set_mem(cave + 4 * i, w)


def _run(sh, cave, a0, a1=None):
    """設參數 → call → 取回 (ok, nzcount, data)。整段在 shell lock 內,避免與儀表板輪詢交錯。"""
    with sh.lock():
        sh._set_mem(ARG0, a0)
        if a1 is not None:
            sh._set_mem(ARG1, a1)
        sh._call(cave)
        # 表頭 16 bytes 一次讀完 —— 用 3 次 peek32 等於 9 個 USB 來回,這樣只要 1 個
        hdr = sh.read_mem(RESULT, 16)
        _arg, ok, ln, nz = struct.unpack('<IIII', hdr)
        ln = min(ln, MAX_LEN)
        # 全空(非 0/非 FF 計數為 0)就不必逐 44 bytes 拉回來 —— 2101 bytes 要 48 個來回
        data = sh.read_mem(RESULT + 0x10, ln) if (ln and nz) else b""
    return ok, nz, data


def dump(sh, sockpath="/tmp/fpshell.sock", progress=None, do_blocks=True, do_raw=True):
    """把鏡頭能給的全部拉回來。progress(done, total, label) 供 UI 顯示進度。"""
    sh._ensure_peek()
    _inject(sh, RAW_CAVE, RAW_WORDS)

    out_blocks = []
    if do_blocks:
        # 區塊階段:一個 BATCHPUSH 把 82 幀全部帶回,零 mem read
        if progress:
            progress(0, 1, "區塊掃描(hook-push,約 35 秒)…")
        out_blocks, binfo = sweep_blocks(sh, sockpath)

    steps = []
    if do_raw:
        for lo, hi in RAW_SWEEPS:
            steps += [("raw", a) for a in range(lo, hi, 0x100)]
    total = len(steps)

    out = {"started": time.strftime("%Y-%m-%d %H:%M:%S"), "blocks": out_blocks, "raw": [],
           "lens_name": None, "firmware": "fp Ver.5.02"}
    for b in out_blocks:                      # 鏡頭名字串順手拿來當標題
        if b["id"] == 0x2d and b["nonzero"]:
            out["lens_name"] = bytes.fromhex(b["hex"]).split(b"\x00")[0].decode("ascii","replace").strip()
    for n, (kind, key) in enumerate(steps):
        if True:
            # 任意位址掃描仍走舊路徑(逐筆 call + mem read);之後也可比照改成一次推完
            ok, nz, data = _run(sh, RAW_CAVE, key, 0xFF)
            if nz:
                out["raw"].append({"addr": key, "len": 0xFF, "ok": ok,
                                   "nonzero": nz, "hex": data.hex()})
            label = f"raw 0x{key:06x}"
        if progress:
            progress(n + 1, total, label)

    # 結果暫存區(0xC072F700+)與 telemetry_push 常式重疊,dump 會把它蓋掉 → 標記需重注入
    sh._telem_ready = False
    out["finished"] = time.strftime("%Y-%m-%d %H:%M:%S")
    out["summary"] = {
        "blocks_read": len(out["blocks"]),
        "blocks_with_data": sum(1 for b in out["blocks"] if b["nonzero"]),
        "raw_pages_with_data": len(out["raw"]),
    }
    return out


def to_text(d):
    """人看的 hex dump 版本。"""
    L = [f"# SIGMA fp 鏡頭資料 dump   {d.get('started')}",
         f"# 鏡頭: {d.get('lens_name') or '(未讀到名稱)'}",
         f"# 韌體: {d.get('firmware')}", ""]
    def hexdump(hexstr, base=0):
        b = bytes.fromhex(hexstr)
        for o in range(0, len(b), 16):
            row = b[o:o + 16]
            asc = "".join(chr(c) if 32 <= c < 127 else "." for c in row)
            L.append(f"  +{base+o:04x}  {row.hex(' '):<47}  |{asc}|")
    L.append("== 韌體區塊表(ID 定址) ==")
    for b in d["blocks"]:
        tag = "" if b["nonzero"] else "   (全空)"
        L.append(f"\nid 0x{b['id']:02x}  addr 0x{b['addr']:06x}  len {b['len']}  "
                 f"ok={b['ok']}  非空 {b['nonzero']}{tag}")
        if b["nonzero"]:
            hexdump(b["hex"])
    L.append("\n\n== 韌體不讀、但有資料的位址(任意位址掃描) ==")
    for r in d["raw"]:
        L.append(f"\naddr 0x{r['addr']:06x}  非空 {r['nonzero']}/255")
        hexdump(r["hex"], r["addr"] & 0xFF)
    return "\n".join(L)


# ---------- 全區塊掃描:每塊一幀,整趟一個 BATCHPUSH(mem read 歸零) ----------
# 常式原始碼:camera/lens_block_sweep_push.S
SWEEP_CAVE  = 0xC072F600     # 與 daemon BATCHPUSH 寫死的 call 位址一致
SWEEP_FRAME = 2120           # 16 表頭 + 最大區塊 2101 + 4-align
ARG_START   = 0xC072F060     # 起始 block id

SWEEP_WORDS = (
    0xe92d4ff0,
    0xe1a04000,
    0xe5948060,
    0xe5947070,
    0xe5946078,
    0xe59f5100,
    0xe3570000,
    0x0a00003c,
    0xe304036c,
    0xe34c00b9,
    0xe3a0100c,
    0xe0010198,
    0xe7902001,
    0xe3040368,
    0xe34c00b9,
    0xe7903001,
    0xe5858000,
    0xe3a00000,
    0xe5850004,
    0xe5853008,
    0xe585000c,
    0xe3520001,
    0x0a000017,
    0xe30504a0,
    0xe34c0035,
    0xe12fff30,
    0xe1a01008,
    0xe2852010,
    0xe3053de0,
    0xe34c3035,
    0xe12fff33,
    0xe5850004,
    0xe5953008,
    0xe285a010,
    0xe3a09000,
    0xe3a0b000,
    0xe15b0003,
    0xaa000007,
    0xe7da000b,
    0xe3500000,
    0x0a000002,
    0xe35000ff,
    0x0a000000,
    0xe2899001,
    0xe28bb001,
    0xeafffff5,
    0xe585900c,
    0xe3030274,
    0xe34c031e,
    0xe590b000,
    0xe58b5000,
    0xe3a00000,
    0xe58b0004,
    0xe58b6008,
    0xe3000813,
    0xe58b000c,
    0xf57ff04f,
    0xe3a00009,
    0xe306cb81,
    0xe34cc01e,
    0xe12fff3c,
    0xe3a00004,
    0xe30c1350,
    0xe304ce81,
    0xe34cc01e,
    0xe12fff3c,
    0xe2888001,
    0xe2577001,
    0xeaffffc0,
    0xe3a00000,
    0xe8bd8ff0,
    0x4072f780,
)




def sweep_blocks(sh, sockpath, start=0, count=len(BLOCK_TABLE)):
    """掃完全部區塊並帶回,**零 mem read、只用一個 BATCHPUSH**。

    常式每讀完一個區塊就推一幀,所以 daemon 每幀只等約 0.3 秒(整批才推的話
    第一幀要等 21 秒,必然撞上 5 秒逾時 —— 踩過)。
    """
    with sh.lock():
        for i, x in enumerate(SWEEP_WORDS):
            sh._set_mem(SWEEP_CAVE + 4 * i, x)
        sh._set_mem(ARG_START, start)
        sh._telem_ready = False        # 佔用了 telemetry 的 0xC072F600 槽位
        resp = telemetry.batchpush(sockpath, SWEEP_FRAME, count, timeout=180)
        blob = b""
        if os.path.exists("/tmp/batchpush.bin"):
            with open("/tmp/batchpush.bin", "rb") as f:
                blob = f.read()
    recs = []
    for n in range(count):
        o = n * SWEEP_FRAME
        if o + 0x10 > len(blob):
            break
        bid, ok, ln, nz = struct.unpack_from("<IIII", blob, o)
        data = blob[o + 0x10: o + 0x10 + ln] if nz else b""
        addr, tlen, flag = BLOCK_TABLE[bid] if bid < len(BLOCK_TABLE) else (0, 0, 0)
        recs.append({"id": bid, "addr": addr, "flag": flag, "ok": ok,
                     "len": ln, "nonzero": nz, "hex": data.hex()})
    return recs, {"daemon": resp, "frames": len(recs)}
