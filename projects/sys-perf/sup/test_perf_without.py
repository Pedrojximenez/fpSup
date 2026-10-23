#!/usr/bin/env python3
"""build_perf.py --without: a left-out module leaves nothing behind.

For every subset of OPTIONAL worth shipping (ic,pl = the lean card; each
module alone; all five) the built file must carry no claim, no write and no
gate for a left-out module, its control-block offset word must read 0, and
without ic the block must not reserve the 1 MiB arena.

    python3 -B test_perf_without.py            # checks
    python3 -B test_perf_without.py --mutate   # build_perf.py mutants must be caught
"""
import importlib.util, pathlib, struct, sys, tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import build_perf as P   # noqa: E402

SITES = {'ir': (0xC06D1418,), 'ic': (0xC060219C, 0xC060234C), 'pl': (0xC05DD5C8, 0xC05DD670),
         'al': (0xC0561734,), 'wf': (0xC2DF8F4C, 0xC2DF8FE4, 0xC2DF9220)}
OFFSET = {'ir': 0x54, 'ic': 0x58, 'pl': 0x5C, 'al': 0x40, 'wf': 0x44}
CASES = [{'ic', 'pl'}, set(), {'ir'}, {'ic'}, {'pl'}, {'al'}, {'wf'}, set(P.OPTIONAL)]


def problems(B, without):
    blob, info, sym = B.build(set(), 1, without=without)
    body = blob[B.HEADER:]
    out = []
    claimed = [(int(c['addr'], 16), c['bytes']) for c in info['claims']]
    written = {int(w['addr'], 16) for w in info['writes']}
    for k, sites in SITES.items():
        gone = k in without
        for a in sites:
            hit = any(c <= a < c + n for c, n in claimed)
            if hit == gone:
                out.append(f'{k} {a:#x} claimed={hit} while left out={gone}')
            w = any(a <= x < a + 8 for x in written)
            if w == gone:
                out.append(f'{k} {a:#x} written={w} while left out={gone}')
        off = struct.unpack_from('<I', body, OFFSET[k])[0]
        if gone and off:
            out.append(f'{k} offset word +{OFFSET[k]:#x} = {off:#x}, want 0')
        if not gone and off != sym.get(f'{k}_mod'):
            out.append(f'{k} offset word +{OFFSET[k]:#x} = {off:#x} != {k}_mod')
        if gone and any(s.startswith(f'pf_g_{k}') for s in sym):
            out.append(f'{k} gate assembled although left out')
    if 'ic' in without:
        if info['block_size'] >= B.IC_ARENA or info['ic_arena']:
            out.append(f'block {info["block_size"]} still reserves the arena')
    elif info['block_size'] < len(blob) + B.IC_ARENA:
        out.append('ic present but no arena')
    if sorted(info['without']) != sorted(without):
        out.append(f'info.without {info["without"]}')
    return out


def check(B=P, verbose=True):
    fails = []
    for w in CASES:
        p = problems(B, set(w))
        if verbose:
            print(('ok  ' if not p else 'BAD ') + f'without={sorted(w)}' + ('' if not p else '  ' + '; '.join(p[:3])))
        fails += p
    return fails


MUTANTS = [
    ('arena always reserved', "arena = IC_ARENA if 'ic' in mods else 0", 'arena = IC_ARENA'),
    ('left-out modules still loaded',
     "mods.update({k: LOADERS[k]() for k in OPTIONAL if k not in without})",
     "mods.update({k: LOADERS[k]() for k in OPTIONAL})"),
    ('absent offset not zero', "g.append(f'        .set    {k.upper()}_MOD_OFF, 0')",
     "g.append(f'        .set    {k.upper()}_MOD_OFF, 4')"),
    ('wf slots written but not claimed', "            claims.append((a, WF_STOCK))\n", ""),
]


def mutate():
    src = (HERE / 'build_perf.py').read_text()
    survivors = []
    for name, old, new in MUTANTS:
        if src.count(old) != 1:
            raise SystemExit(f'mutant {name!r}: pattern found {src.count(old)} times')
        with tempfile.TemporaryDirectory() as t:
            p = pathlib.Path(t) / 'build_perf_mut.py'
            p.write_text(src.replace(old, new).replace("HERE = pathlib.Path(__file__).resolve().parent",
                                                        f"HERE = pathlib.Path({str(HERE)!r})"))
            spec = importlib.util.spec_from_file_location('build_perf_mut', p)
            m = importlib.util.module_from_spec(spec)
            try:
                spec.loader.exec_module(m)
                fails = check(m, verbose=False)
            except BaseException as e:      # noqa: BLE001
                fails = [f'{type(e).__name__}: {e}']
        print(('caught   ' if fails else 'SURVIVED ') + name, fails[:1])
        if not fails:
            survivors.append(name)
    return survivors


if __name__ == '__main__':
    if '--mutate' in sys.argv:
        s = mutate()
        print('survivors:', s)
        sys.exit(1 if s else 0)
    f = check()
    print(f'{len(f)} problems' if f else 'all --without cases clean')
    sys.exit(1 if f else 0)
