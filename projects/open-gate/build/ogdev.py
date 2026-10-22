#!/usr/bin/env python3
"""USB shell 開發工具:組譯、上傳、掛鉤、回讀。全部用 mem set/get,
不碰 host 工具的暫存區(0xC072F800-FE00),所以 open gate 的 hook 可以同時活著。

    ./ogdev.py up keylog.S 0xC0730200          組譯上傳並逐字驗證
    ./ogdev.py arm 0xC043CF38 0xC0730200       用 B 指令掛上(自動記住原值)
    ./ogdev.py off 0xC043CF38                  還原
    ./ogdev.py log                             讀 keylog 的紀錄
    ./ogdev.py clear                           清掉 log
"""
import json, pathlib, struct, sys
HERE = pathlib.Path(__file__).resolve().parent
SHELL = HERE.parent.parent.parent / "fpSup" / "fp_usb_shell"
sys.path.insert(0, str(SHELL))
from armasm import assemble
from putfile import mem_get, mem_set

STATE = HERE / ".ogdev_state.json"
LOG = 0xC0730000
SLOTS = 12


def rd(a, n=1, tries=8):
    for _ in range(tries):
        w = mem_get(a, n)
        if w and all(x is not None for x in w):
            return w
    raise SystemExit(f"read failed at 0x{a:08X}")


def wr(a, v, tries=10):
    for _ in range(tries):
        if rd(a)[0] == v:
            return True
        mem_set(a, v)
    return rd(a)[0] == v


def state():
    return json.loads(STATE.read_text()) if STATE.is_file() else {}


def save(s):
    STATE.write_text(json.dumps(s, indent=1))


def cmd_up(src, addr):
    blob = assemble(HERE / src)
    words = struct.unpack(f"<{len(blob)//4}I", blob)
    print(f"{src}: {len(blob)} bytes ({len(words)} 字) -> 0x{addr:08X}")
    for i, v in enumerate(words):
        if not wr(addr + i * 4, v):
            raise SystemExit(f"write failed at 0x{addr + i*4:08X}")
    back = rd(addr, len(words))
    bad = [i for i, (a, b) in enumerate(zip(words, back)) if a != b]
    print(f"  逐字驗證 {len(words)-len(bad)}/{len(words)}" + ("  ✓" if not bad else f"  ✗ {bad}"))


def cmd_arm(site, target):
    stock = rd(site)[0]
    br = 0xEA000000 | (((target - site - 8) >> 2) & 0xFFFFFF)
    s = state()
    key = f"{site:08X}"
    if key not in s:
        s[key] = stock
        save(s)
    print(f"0x{site:08X}: 0x{stock:08X} -> 0x{br:08X}   (B 到 0x{target:08X})")
    if not wr(site, br):
        raise SystemExit("arm failed")
    print(f"  回讀 0x{rd(site)[0]:08X}  ✓")


def cmd_off(site):
    s = state()
    key = f"{site:08X}"
    if key not in s:
        raise SystemExit(f"沒有記錄 0x{site:08X} 的原值")
    if wr(site, s[key]):
        print(f"0x{site:08X} = 0x{rd(site)[0]:08X}  ✓ 已還原")


def cmd_log():
    n = rd(LOG)[0]
    if n == 0 or n > SLOTS:
        print(f"  count = {n}" + ("  (還沒命中)" if n == 0 else "  (值不合理)"))
        return
    print(f"  {n} 筆不同的鍵:\n")
    print(f"  {'#':>2}  {'table':>10}  key")
    for i in range(n):
        w = rd(LOG + 4 + i * 24, 5)
        b = b"".join(struct.pack("<I", x) for x in w[1:])
        key = b.split(bytes([0]))[0].decode("latin1")
        print(f"  {i:>2}  0x{w[0]:08X}  {key!r}")


def cmd_clear():
    for i in range(1 + SLOTS * 6):
        wr(LOG + i * 4, 0)
    print(f"  log 0x{LOG:08X} 清空 ({1+SLOTS*6} 字)")


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a:
        raise SystemExit(__doc__)
    if a[0] == "up":
        cmd_up(a[1], int(a[2], 0))
    elif a[0] == "arm":
        cmd_arm(int(a[1], 0), int(a[2], 0))
    elif a[0] == "off":
        cmd_off(int(a[1], 0))
    elif a[0] == "log":
        cmd_log()
    elif a[0] == "clear":
        cmd_clear()
    else:
        raise SystemExit(__doc__)
