#!/usr/bin/env python3
"""反編譯原始碼的交叉索引 —— 呼叫圖、符號、字串、常數。

一次解析 out/decomp/full/blk_*.c(47,156 個函式,33 MB),存成 pickle,
之後查詢是毫秒級。手動 grep 33 MB 找呼叫鏈太貴,而且容易漏。

    ./fpxref.py build                 建索引
    ./fpxref.py callers c043a158      誰呼叫它
    ./fpxref.py callees c043a158      它呼叫誰
    ./fpxref.py path c043a158 8       往上追呼叫鏈,深度 8
    ./fpxref.py name LiveView         名稱包含
    ./fpxref.py body 'c0be5b50'       函式體包含
    ./fpxref.py show c043a158         印出原始碼
"""
import pathlib, pickle, re, sys

HERE = pathlib.Path(__file__).resolve().parent
FULL = next((d / "out" / "decomp" / "full" for d in HERE.parents
             if (d / "out" / "decomp" / "full").is_dir()),
            HERE.parent.parent / "out" / "decomp" / "full")
CACHE = HERE / ".fpxref.pkl"
CALL = re.compile(r'\b(FUN_c[0-9a-f]{6,7}|[A-Za-z_][A-Za-z0-9_]*__v[0-9]+|'
                  r'[A-Za-z_][A-Za-z0-9_]{3,})\s*\(')
HEAD = re.compile(r'/\* ==== ([A-Za-z_][A-Za-z0-9_:]*) @ ([0-9a-f]+) ==== \*/')


def build():
    funcs = {}
    for f in sorted(FULL.glob("blk_*.c")):
        src = f.read_text(errors="replace")
        parts = HEAD.split(src)
        for k in range(1, len(parts), 3):
            name, addr, body = parts[k], parts[k + 1], parts[k + 2]
            funcs[addr] = {"name": name, "body": body, "file": f.name}
    byname = {}
    for a, d in funcs.items():
        byname.setdefault(d["name"], []).append(a)
    # 呼叫邊:直接位址(FUN_cXXXXXX)與具名函式
    callees, callers = {}, {}
    for a, d in funcs.items():
        out = set()
        for m in CALL.finditer(d["body"]):
            t = m.group(1)
            if t.startswith("FUN_c"):
                ta = t[4:]
                if ta in funcs:
                    out.add(ta)
            elif t in byname:
                out.update(byname[t])
        out.discard(a)
        callees[a] = out
        for t in out:
            callers.setdefault(t, set()).add(a)
    idx = {"funcs": funcs, "byname": byname, "callees": callees, "callers": callers}
    CACHE.write_bytes(pickle.dumps(idx))
    print(f"  {len(funcs)} 個函式   {sum(len(v) for v in callees.values())} 條呼叫邊")
    print(f"  → {CACHE}")
    return idx


def load():
    if not CACHE.exists():
        return build()
    return pickle.loads(CACHE.read_bytes())


def label(idx, a):
    d = idx["funcs"].get(a)
    return f"{d['name']} @ {a}" if d else a


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    cmd = sys.argv[1]
    if cmd == "build":
        build(); return 0
    idx = load()
    arg = sys.argv[2] if len(sys.argv) > 2 else ""
    arg = arg.lower().removeprefix("0x").removeprefix("fun_")
    if cmd == "callers":
        cs = sorted(idx["callers"].get(arg, ()))
        print(f"{len(cs)} 個呼叫者:")
        for a in cs:
            print("  " + label(idx, a))
    elif cmd == "callees":
        cs = sorted(idx["callees"].get(arg, ()))
        print(f"{len(cs)} 個被呼叫者:")
        for a in cs:
            print("  " + label(idx, a))
    elif cmd == "path":
        depth = int(sys.argv[3]) if len(sys.argv) > 3 else 6
        seen, frontier = {arg}, [arg]
        for lv in range(depth):
            nxt = []
            for a in frontier:
                for c in sorted(idx["callers"].get(a, ())):
                    if c in seen:
                        continue
                    seen.add(c); nxt.append(c)
                    print(f"  {'  '*lv}↑ " + label(idx, c))
            frontier = nxt
            if not frontier:
                break
    elif cmd == "name":
        pat = sys.argv[2]
        hit = sorted(n for n in idx["byname"] if pat.lower() in n.lower())
        for n in hit[:40]:
            print(f"  {n} @ " + ", ".join(idx["byname"][n][:3]))
        print(f"  ({len(hit)} 個)")
    elif cmd == "body":
        pat = sys.argv[2].lower()
        hit = [(d["name"], a) for a, d in idx["funcs"].items() if pat in d["body"].lower()]
        for n, a in sorted(hit)[:40]:
            print(f"  {n} @ {a}")
        print(f"  ({len(hit)} 個)")
    elif cmd == "show":
        d = idx["funcs"].get(arg)
        print(d["body"] if d else "找不到")
    else:
        print(__doc__)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
