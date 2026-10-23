#!/usr/bin/env python3
"""Which harness mechanism freezes the firmware? (user 2026-10-23: "萬一用戶拍攝時也遇到呢")

The dark round (SMC_VERIFY r26) froze the whole camera about once per 50-90 configs, during close (first restore
write "0xC2F1E654 <- 0xC0B59500 did not stick"). One config touches four mechanisms; each group here repeats ONE of
them N times and nothing else:

  A  mode switch:  vmode.apply(generated rows, host 10) -> OK into magnify -> check -> OK back -> vmode.restore()
                   (the shipping path res-custom uses the same firmware switch, so a freeze here could hit users)
  B  BUFA0 grab:   stock magnify (no vmode), Session open -> pair grab -> 8-frame IMXB burst -> close
  C  IMXB subs:    stock live view, bus_on, gain/SHS substitution on/off, fixed_shutter on/off

After every iteration: shell answers, mode is back to 8, live view frame count advances. Every step is appended to
OUT/steps.jsonl before it runs, so a freeze leaves its last step on disk. Nothing writes the settings area or card.

    freeze_iso.py OUT --group A|B|C [--n 50]       touch OUT/STOP to stop cleanly
"""
import argparse, itertools, json, pathlib, struct, sys, time
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import bufa_probe as B                                                # noqa: E402

LOG = None


def step(it, name, **kw):
    LOG.write(json.dumps(dict(t=round(time.time(), 3), it=it, step=name, **kw)) + '\n'); LOG.flush()


def mode_and_count():
    txt = B.P().sh('imager mode_now')
    mode = next((l.split(',')[2] for l in txt.splitlines() if l[:3].isdigit()), '?')
    fc = int(txt.split('frame_count:')[1][:8]) if 'frame_count:' in txt else -1
    return mode, fc


def health(it, want='0008'):
    step(it, 'health')
    m0, c0 = mode_and_count(); time.sleep(0.5); m1, c1 = mode_and_count()
    ok = m1 == want and c1 - c0 > 10
    step(it, 'health_done', mode=m1, frames=c1 - c0, ok=ok)
    if not ok:
        raise SystemExit(f'iteration {it}: mode {m1}, {c1 - c0} frames in 0.5 s')


def rows_cycle():
    import readout_cfg as C, smc, smc_validate as V
    for key, crop, outsz, fps in itertools.cycle(V.matrix_set()):
        p = C.plan(key, *crop, *outsz, fps)
        a, rows, _ = smc.create(p)
        rows = {t: bytes(v) for t, v in rows.items()}
        rows['R10'] = struct.pack('<II', V.R10[a['cls']], 10)
        yield p['id'], rows, p['receiver_lines']


def group_a(n, out):
    import vmode
    vmode.KEEP_WINDOW = True
    gen = rows_cycle()
    for it in range(n):
        if (out / 'STOP').exists():
            return it
        cid, rows, lines = next(gen)
        step(it, 'apply', cfg=cid)
        vmode.apply(rows, 10, f'freeze_iso A {cid}')
        try:
            step(it, 'enter'); B.switch('key OKON'); B.switch('key OKOFF'); time.sleep(1.5)
            m, _ = mode_and_count()
            ln = min(B.P().mem_get(0x301005D8)[0] for _ in range(3))
            step(it, 'entered', mode=m, lines=ln, planned=lines)
            step(it, 'exit'); B.switch('key OKON'); B.switch('key OKOFF'); time.sleep(1.5)
        finally:
            step(it, 'restore'); vmode.restore()
        health(it)
    return n


def trace_calls(it_ref):
    """log every firmware call and register write before it goes out (B froze inside the burst, 2026-10-23)"""
    call0, wr0 = B.call, B.wr
    def call(fn, *args):
        step(it_ref[0], 'call', fn=f'0x{fn:08X}', args=[f'0x{x:X}' for x in args])
        return call0(fn, *args)
    def wr(addr, val, *a, **k):
        step(it_ref[0], 'wr', addr=f'0x{addr:08X}', val=f'0x{val:X}')
        return wr0(addr, val, *a, **k)
    B.call, B.wr = call, wr


def group_b(n, out, burst_only=False):
    import fastsweep as F, hsburst
    cur = [0]; trace_calls(cur)
    for it in range(n):
        cur[0] = it
        if (out / 'STOP').exists():
            return it
        step(it, 'session')
        (out / 'b').mkdir(exist_ok=True)
        s = F.Session(out / 'b', None, True, 10, min_alloc=48 << 20)
        try:
            ok = None if burst_only else (step(it, 'grab'), s.grab(out / 'b' / 'f'))[1]
            step(it, 'burst', grab=bool(ok)); hsburst.burst(s, n=8)
        finally:
            step(it, 'close'); s.close()
        time.sleep(1.5)
        health(it)
    return n


def group_c(n, out):
    st = B.bus_state()
    for it in range(n):
        if (out / 'STOP').exists():
            return it
        step(it, 'bus_on'); B.bus_on(st)
        try:
            for code in (0x400, 3900):
                step(it, 'subs', code=code)
                B.bus_subs(st, [(0x0005, 4), (0x0006, 0), (0x003D, code & 0xFF), (0x003E, code >> 8), (0x003F, code & 0xFF), (0x0040, code >> 8)])
                time.sleep(0.4)
            step(it, 'fixed_shutter'); B.P().sh('imager fixed_shutter 1 100'); time.sleep(0.3)
        finally:
            step(it, 'subs_off'); B.bus_subs(st, []); B.P().sh('imager fixed_shutter 0')
        health(it)
    return n


def main():
    global LOG
    ap = argparse.ArgumentParser()
    ap.add_argument('out'); ap.add_argument('--group', required=True, choices='ABC'); ap.add_argument('--n', type=int, default=50)
    ap.add_argument('--burst-only', action='store_true')
    a = ap.parse_args()
    out = pathlib.Path(a.out) / (a.group + ('2' if a.burst_only else '')); out.mkdir(parents=True, exist_ok=True)
    LOG = (out / 'steps.jsonl').open('a')
    import fastsweep as F; F.cached_assemble(); B.not_recording()
    health(-1)
    t0 = time.time()
    done = (lambda n, o: group_b(n, o, a.burst_only)) if a.group == 'B' else {'A': group_a, 'C': group_c}[a.group]
    done = done(a.n, out)
    step(done, 'finished', seconds=round(time.time() - t0))
    print(f'group {a.group}: {done} iterations clean in {time.time() - t0:.0f} s')


if __name__ == '__main__':
    main()
