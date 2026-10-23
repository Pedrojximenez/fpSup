#!/usr/bin/env python3
"""Read and flip 70PERF.BIN's switches on the camera, over the USB shell.

    python3 -B perfctl.py find                       # ctl address from \\fpSup\\LOAD.LOG
    python3 -B perfctl.py status --ctl 0xC5A1B020
    python3 -B perfctl.py set dc=1 nb=0 --ctl 0xC5A1B020
    python3 -B perfctl.py set master=0 --ctl ...     # everything stock at once

Switches: master (pf +08), nb (pf +0C), lz (pf +10), dc (dirtyclean C_EN),
fd (filldma fd_enable), fd_thresh (bytes); layout 2 (pf +04 == 2) adds
ir (inputredraw enable), ir_rec_ok, ir_min_ms, ic (iconcache EN),
pl (pagelru enable), pl_capacity; layout 3 (pf +04 == 3) adds
al (alphalut enable); layout 4 adds wf (waveform enable).  A module left
out of the build (--without) has offset 0: shown n/a, set refused.  Every write is read back and
retried (mem set drops commands).  Refuses to run while recording: no USB
traffic during a take (memory: no-usb-during-rec-or-playback).
"""
import argparse, pathlib, re, subprocess, sys, time

HERE = pathlib.Path(__file__).resolve().parent
SHELL = HERE.parents[2] / 'fpSup' / 'fp_usb_shell'
sys.path.insert(0, str(SHELL))

PF = {'magic': 0x00, 'master': 0x08, 'nb': 0x0C, 'lz': 0x10, 'state': 0x14, 'veneers': 0x18,
      'n_fill': 0x1C, 'n_dma': 0x20, 'n_neon': 0x24, 'n_stock': 0x28, 'dc_off': 0x2C,
      'fd_off': 0x30, 'nb_off': 0x34, 'lz_off': 0x38, 'build': 0x3C, 'layout': 0x04,
      'ir_off': 0x54, 'ic_off': 0x58, 'pl_off': 0x5C, 'al_off': 0x40, 'wf_off': 0x44}
DC = {'dc': 0x04, 'C_CLEAR': 0x08, 'C_COPY': 0x0C, 'C_CALLS': 0x10, 'C_FAST': 0x14, 'C_FALL': 0x18,
      'C_LINES': 0x1C, 'C_WHY': 0x20, 'C_FULLS': 0x24}
FD = {'fd': 0x08, 'fd_thresh': 0x0C, 'fd_rec_ok': 0x10, 'fd_calls': 0x14, 'fd_dma_ok': 0x18,
      'fd_dma_bytes': 0x1C, 'fd_declined': 0x20, 'fd_cpu_done': 0x24, 'fd_last_code': 0x28}
LZ = {'lz_calls': 0x04, 'lz_out_bytes': 0x08}
IR = {'ir': 0x08, 'ir_rec_ok': 0x0C, 'ir_min_ms': 0x10, 'ir_calls': 0x14, 'ir_kicks': 0x18,
      'ir_preloads': 0x1C, 'ir_skip_rec': 0x20, 'ir_skip_pending': 0x24}
IC = {'ic': 0x04, 'ic_arena': 0x08, 'ic_arena_size': 0x0C, 'ic_hits': 0x14, 'ic_misses': 0x18,
      'ic_inserts': 0x1C, 'ic_evicts': 0x20, 'ic_skips': 0x24, 'ic_alloc_fail': 0x28, 'ic_rejects': 0x48}
PL = {'pl': 0x04, 'pl_capacity': 0x08, 'pl_count': 0x0C, 'pl_hits': 0x10, 'pl_kept': 0x14,
      'pl_evictions': 0x18, 'pl_bypass': 0x1C, 'pl_why': 0x20, 'pl_flushed': 0x24}
WF = {'wf': 0x04, 'wf_calls': 0x08, 'wf_fallbacks': 0x0C}
AL = {'al': 0x08, 'al_calls': 0x0C, 'al_blocks': 0x10, 'al_zero_skips': 0x14, 'al_fallbacks': 0x18}
MAGIC = 0x46524550


def pf():
    import putfile
    return putfile


def not_recording():
    out = pf().sh('status get is_recording', retries=0, timeout_ms=5000).strip()
    if out != 'is_recording -> 0':
        raise SystemExit(f'not idle ({out!r}); no USB traffic while recording')


def find():
    r = subprocess.run([sys.executable, '-B', str(SHELL / 'getfile.py'), '\\fpSup\\LOAD.LOG'],
                       capture_output=True, text=True)
    hits = re.findall(r'PERF ctl ([0-9A-F]{8})', r.stdout + r.stderr)
    if not hits:
        raise SystemExit('no "PERF ctl" line in LOAD.LOG (sup not loaded, or released: see the log)')
    return int(hits[-1], 16)


def read_all(ctl):
    g = pf().mem_get
    w = g(ctl, 24)
    if w[0] != MAGIC:
        raise SystemExit(f'{ctl:#x}: no PERF magic ({w[0]})')
    if None in w:
        raise SystemExit(f'{ctl:#x}: a word did not come back; run again')
    out = {k: w[o // 4] for k, o in PF.items()}
    if out['layout'] < 2:
        out.update(ir_off=0, ic_off=0, pl_off=0)
    if out['layout'] < 3:
        out.update(al_off=0)          # +40 was the log buffer before layout 3
    if out['layout'] < 4:
        out.update(wf_off=0)
    dc, fd = ctl + out['dc_off'], ctl + out['fd_off']
    dw, fw = g(dc, 10), g(fd, 11)
    out.update({k: dw[o // 4] for k, o in DC.items()})
    out.update({k: fw[o // 4] for k, o in FD.items()})
    if out['lz_off']:
        lw = g(ctl + out['lz_off'], 3)
        out.update({k: lw[o // 4] for k, o in LZ.items()})
    for key, tab, n in (('ir_off', IR, 10), ('ic_off', IC, 19), ('pl_off', PL, 10), ('al_off', AL, 7), ('wf_off', WF, 4)):
        if out[key]:
            mw = g(ctl + out[key], n)
            out.update({k: mw[o // 4] for k, o in tab.items()})
    return out


def addr_of(ctl, name, st):
    if name in ('master', 'nb', 'lz'):
        if name == 'lz' and not st['lz_off']:
            raise SystemExit('this build has no lz4fast')
        return ctl + PF[name]
    if name == 'dc':
        return ctl + st['dc_off'] + DC['dc']
    if name in ('fd', 'fd_thresh', 'fd_rec_ok'):
        return ctl + st['fd_off'] + FD[name]
    for key, tab, names in (('ir_off', IR, ('ir', 'ir_rec_ok', 'ir_min_ms')), ('ic_off', IC, ('ic',)),
                            ('pl_off', PL, ('pl', 'pl_capacity')), ('al_off', AL, ('al',)),
                            ('wf_off', WF, ('wf',))):
        if name in names:
            if not st[key]:
                raise SystemExit(f'{name} is n/a in this build (left out, or layout {st["layout"]})')
            return ctl + st[key] + tab[name]
    raise SystemExit(f'unknown switch {name}')


def set_word(a, v, tries=6):
    p = pf()
    for _ in range(tries):
        p.mem_set(a, v)
        time.sleep(0.05)
        if p.mem_get(a)[0] == v:
            return
    raise SystemExit(f'{a:#x} did not take {v:#x}')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=('find', 'status', 'set'))
    ap.add_argument('assign', nargs='*', help='name=value')
    ap.add_argument('--ctl', type=lambda s: int(s, 0))
    a = ap.parse_args()
    not_recording()
    ctl = a.ctl if a.ctl is not None else find()
    if a.cmd == 'find':
        print(f'{ctl:#010x}')
        return
    st = read_all(ctl)
    if a.cmd == 'set':
        for kv in a.assign:
            k, v = kv.split('=')
            set_word(addr_of(ctl, k, st), int(v, 0))
        st = read_all(ctl)
    print(f'ctl {ctl:#010x} build {st["build"]:08x} state {st["state"]:#x}')
    sw = []
    for k in ('master', 'dc', 'nb', 'fd', 'lz', 'ir', 'ic', 'pl', 'al', 'wf'):
        off = {'lz': 'lz_off', 'ir': 'ir_off', 'ic': 'ic_off', 'pl': 'pl_off', 'al': 'al_off', 'wf': 'wf_off'}.get(k)
        sw.append(f'{k}=n/a' if off and not st[off] else f'{k}={st[k]}')
    print('switches  ' + '  '.join(sw))
    print(f'fill      calls {st["n_fill"]}  dma {st["n_dma"]}  neon {st["n_neon"]}  stock {st["n_stock"]}')
    print(f'dirtycln  calls {st["C_CALLS"]}  fast {st["C_FAST"]}  fallback {st["C_FALL"]} '
          f'(why {st["C_WHY"]})  lines {st["C_LINES"]}  whole-buffer {st["C_FULLS"]}')
    print(f'filldma   calls {st["fd_calls"]}  dma {st["fd_dma_ok"]}  declined {st["fd_declined"]} '
          f'(last {st["fd_last_code"]})  cpu-completed {st["fd_cpu_done"]}  thresh {st["fd_thresh"]}')
    if st['lz_off']:
        print(f'lz4fast   calls {st["lz_calls"]}  out bytes {st["lz_out_bytes"]}')
    if st['ir_off']:
        print(f'inputrdr  calls {st["ir_calls"]}  kicks {st["ir_kicks"]}  preloads {st["ir_preloads"]}  '
              f'skip-rec {st["ir_skip_rec"]}  skip-pending {st["ir_skip_pending"]}  '
              f'rec_ok {st["ir_rec_ok"]}  min_ms {st["ir_min_ms"]}')
    if st['ic_off']:
        print(f'iconcach  hits {st["ic_hits"]}  misses {st["ic_misses"]}  inserts {st["ic_inserts"]}  '
              f'evicts {st["ic_evicts"]}  skips {st["ic_skips"]}  rejects {st["ic_rejects"]}  '
              f'alloc-fail {st["ic_alloc_fail"]}  arena {st["ic_arena"]:#x}+{st["ic_arena_size"]:#x}')
    if st['pl_off']:
        print(f'pagelru   cap {st["pl_capacity"]}  kept-now {st["pl_count"]}  hits {st["pl_hits"]}  '
              f'kept {st["pl_kept"]}  evict {st["pl_evictions"]}  bypass {st["pl_bypass"]} (why {st["pl_why"]})  '
              f'flushed {st["pl_flushed"]}')
    if st['wf_off']:
        print(f'waveform  calls {st["wf_calls"]}  fallbacks {st["wf_fallbacks"]}')
    if st['al_off']:
        print(f'alphalut  calls {st["al_calls"]}  neon-blocks {st["al_blocks"]}  zero-skips {st["al_zero_skips"]}  '
              f'fallbacks {st["al_fallbacks"]}')


if __name__ == '__main__':
    main()
