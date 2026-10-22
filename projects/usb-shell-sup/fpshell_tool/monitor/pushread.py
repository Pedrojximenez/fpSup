"""pushread.py — 記憶體回讀,走 hook-push,取代 read_mem。

專案紀律(memory prefer-hook-push):功能實作一律用 hook-push,不用 read_mem。
read_mem 另外還有兩個會騙人的限制(notes/SHELL_MEM_RANGE_LIMITS.md):超出可讀
範圍時它回傳「指令字串本身」而不是報錯,那是可列印位元組,擺進 hexdump 看起來
像真資料;而且一趟只有 44 bytes。

push 沒有這兩個問題:來源可以是任意位址(0xC375xxxx / 0xC37Cxxxx 這些 read_mem
到不了的區域都可以),速度是 MB/s 級,而且失敗會回報 LIBUSB 錯誤。

自證方式(每次改動都該重跑):push 一段 ROM 跟 out/MAIN_c0000000.bin 比對。

常式:camera/push_addr.S,注入在 CODE(daemon 的 BATCHPUSH 呼叫位址寫死於此)。
參數在 worker state:+0x60 來源(bus 視角 = CPU 位址 - 0x80000000)、+0x70 幀數、
+0x78 幀大小。用 +0x60 帶來源是因為 BATCHPUSH 自己會覆寫 +0x74。
"""
import struct, subprocess, tempfile, pathlib, sys, time

CODE = 0xC072F600
SRC  = 0xC072F060
NFR  = 0xC072F070
FSZ  = 0xC072F078
DUMP = "/tmp/batchpush.bin"
ROOT = pathlib.Path(__file__).resolve().parent.parent


def _routine():
    sys.path.insert(0, str(ROOT.parent))
    from build_stage5_autorun import extract_and_relocate
    with tempfile.TemporaryDirectory() as d:
        obj = pathlib.Path(d) / "push_addr.o"
        subprocess.run(["clang", "-target", "armv7-none-eabi", "-c",
                        str(ROOT / "camera" / "push_addr.S"), "-o", str(obj)], check=True)
        code = extract_and_relocate(obj)
    return [struct.unpack_from("<I", code, i)[0] for i in range(0, len(code), 4)]


def install(sh):
    """注入推送常式。每次 daemon 重啟或相機重開後都要重來。"""
    words = _routine()
    with sh.lock():
        for i, w in enumerate(words):
            sh._set_mem(CODE + 4 * i, w)
    return len(words) * 4


def verify(sh):
    """推送前確認常式還在。被蓋掉時 BATCHPUSH 會去執行垃圾,直接掛掉相機 ——
    這已經發生過:某個測試把它的狀態區放在 0xC072F600,清空狀態就把常式抹了。
    檢查只花一次 read,比再拔一次電池便宜。"""
    want = _routine()[0]
    got = struct.unpack("<I", sh.read_mem(CODE, 4))[0]
    if got != want:
        raise RuntimeError(
            f"push 常式已被覆寫 @{CODE:#010x}: {got:#010x} != {want:#010x}。"
            f"有東西佔用了 {CODE:#x}..{CODE + len(_routine()) * 4:#x};先看 SHELL_MEMORY_MAP.md")
    return True


def read(sh, sockpath, cpu_addr, nbytes, frames=1):
    """從 cpu_addr 取回 nbytes*frames。回傳 bytes。"""
    import telemetry
    verify(sh)
    # bus 視角:0xCxxxxxxx 的 CPU 位址要減 0x80000000;DRAM 位址(0x4xxxxxxx / 0x5xxxxxxx)
    # 本身就是 bus 視角,再減會繞到完全不相干的地方。我一度用錯,讀 bufmem 池讀到
    # 0xC4F6ADC0,拿著假資料判斷「程式沒寫進去」。
    bus = cpu_addr - 0x80000000 if cpu_addr >= 0x80000000 else cpu_addr
    with sh.lock():
        sh._set_mem(SRC, bus)
        sh._set_mem(NFR, frames)
        sh._set_mem(FSZ, nbytes)
    telemetry.batchpush(sockpath, nbytes, frames)
    time.sleep(1.2)                      # BATCHPUSH 後的靜默期,見 memory hookpush-quiet-period
    return open(DUMP, "rb").read()[: nbytes * frames]


def selftest(sh, sockpath):
    """把一段 ROM 推回來跟本地韌體比對。任何記憶體工具都該先過這關。"""
    firmware = (ROOT.parent.parent / "out" / "MAIN_c0000000.bin").read_bytes()
    for addr in (0xC0016A58, 0xC03554A0):
        got = read(sh, sockpath, addr, 64)
        want = firmware[addr - 0xC0000000: addr - 0xC0000000 + 64]
        if got != want:
            raise AssertionError(f"pushread 自證失敗 @{addr:#010x}: {got[:12].hex()} != {want[:12].hex()}")
    return True
