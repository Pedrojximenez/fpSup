#!/usr/bin/env python3
"""BUFA0 one-frame probe: the CRCT -> BUFA0 DMA armed by hand in plain liveview.
Recipe: notes/BUFA_FRONT_TAP.md "單幀 arm 步驟" (offline RE 2026-10-20).

    bufa_probe.py peek                 baseline of every register the probe touches
    bufa_probe.py frame OUT [--mux 1]  configure, arm, take one frame, restore, pull

Once `frame` has written anything, it stops BUFA0 and puts every
touched register back, then compares against the baseline.
Not while recording or in playback; one step at a time (skill fp-firmware-call).
"""
import argparse, json, pathlib, struct, sys, time

HERE = pathlib.Path(__file__).resolve().parent
SHELL = HERE.parents[1] / 'fpSup' / 'fp_usb_shell'
sys.path[:0] = [str(HERE), str(SHELL)]

T = lambda a: a | 1                         # Thumb entry (first halfwords checked: push.w)
F_STARTSTOP = T(0xC06316B8)                 # (n): 10 run, 100 stop -- use startstop(): it waits forever on a mutex
F_SIG_SEM = 0xC01F8CDC                      # ARM (id, cnt)
BUFA_MUTEX = 0xC2F14B1C                     # c06316b8 takes it with TMO_FEVR first thing
F_A0CROP = T(0xC06340C8)                    # (1, {en,x0,x1,y0,y1})
F_WINDOW = T(0xC06314D0)                    # (struct 0x14)
F_SETADDR = T(0xC0631640)                   # (addr)
F_CBCLR = T(0xC06305F0)                     # cb = 0, 2000 &= ~0x1F
F_WAI_SEM = 0xC01F8E8C                      # ARM (id, cnt, tmo)
F_CLR_FLG = 0xC00169C8                      # ARM (id, clrptn)
F_DCACHE = 0xC000E91C                       # ARM

SEM_IDS = (0xC2F14B28, 0xC2F14C40)          # the ISR signals these per BUFA0 frame
FLG_ID = 0xC2F14C98                         # the ISR sets bit 0
CB_A0, CB_2 = 0xC37CF8CC, 0xC37CF8D0
REC_FLAG = 0xC347E08F
WIN = 7                                     # MEM1 window slot

PEEK = [(0x30182000, 32), (0x30182040, 16), (0x30182100, 64), (0x30182280, 16), (0x30182380, 4),
        (0x30002060, 1), (0x30000804, 1), (0x30100000, 16), (0x300F0004, 1), (0x300F021C, 1),
        (0x300F06B0, 1), (0x300F06C0, 4), (0x300F06D0, 1), (0xC37CF8B8, 8),
        (0x300F0308, 6)]                    # CRCT digital gain 310/320 (Q8.8) and pedestal 318/31C (IMX410_RULES §12)
# put back to baseline after the frame (the recipe's restore list; all readable)
RESTORE = ([0x30182100, 0x30182104, 0x3018210C, 0x30182110, 0x30182114, 0x30182118]
           + list(range(0x3018211C, 0x30182134, 4)) + [0x30182168, 0x3018216C]
           + list(range(0x30182174, 0x30182184, 4)) + [0x301821E8]
           + [0x300F06C0, 0x300F06C4, 0x300F06C8, 0x300F06CC, 0x300F0004, 0x300F06B0, 0x30100024, 0x30100020]
           + [0xC37CF8BC, 0xC37CF8C0, 0xC37CF8C4, 0xC37CF8C8])


def P():
    import putfile
    return putfile


def call(fn, *args):
    from callfn import call as c
    ok, v = c(fn, *args)
    if not ok:
        raise SystemExit(f'call 0x{fn:08X}{args} did not return')
    return v


_STOP = {}


def safe_stop(tmo_ms=500):
    """Stop BUFA0 right after a completion, as the firmware does (sensor_read/bufa_stop.S); one camera-side call,
    since a USB round trip is longer than the blanking gap. Returns tk_wai_flg's result (nonzero = no frame came
    within tmo_ms, so no DMA was in flight; stopped anyway)."""
    import cave
    if 'at' not in _STOP:
        from armasm import assemble
        code = assemble(HERE / 'sensor_read' / 'bufa_stop.S')
        at = cave.claim('imxl.bufastop', 112)
        if len(code) > 112:
            raise SystemExit(f'bufa_stop is {len(code)} B, claim is 112')
        P().put(at, code + bytes(-len(code) % 4), 'bstop ')
        call(F_DCACHE)
        _STOP['at'] = at
    if not P().mem_get(0x30182000)[0] & 0x1F:               # BUFA0 not running: no DMA to cut, no frame to wait for
        call(F_STARTSTOP, 100)
        print('  safe stop: BUFA0 idle')
        return None
    r = call(_STOP['at'], P().mem_get(FLG_ID)[0], tmo_ms)
    print(f'  safe stop: wait -> {r}')
    return r


def startstop(n):
    """c06316b8(n) without the risk of blocking the shell: it opens with wai_sem(BUFA_MUTEX, 1, forever),
    and when liveview holds that mutex (seen 2026-10-20 at the restore stop) the shell task never comes
    back -- not even poff gets through. Probe the mutex with a 500 ms timeout and give it straight back."""
    if n == 100:                            # stop: c06316b8(100) takes no mutex, but cutting a frame's DMA in half
        return safe_stop()                  # froze the camera ~1 in 100 (freeze_iso B, 2026-10-23)
    sid = P().mem_get(BUFA_MUTEX)[0]
    if sid is None:
        raise SystemExit('could not read the BUFA mutex id')
    if call(F_WAI_SEM, sid, 1, 500) != 0:
        raise SystemExit(f'BUFA mutex busy for 500 ms: not calling start/stop({n})')
    call(F_SIG_SEM, sid, 1)
    call(F_STARTSTOP, n)


def peek():
    out = {}
    for base, n in PEEK:
        for i, v in enumerate(P().mem_get(base, n)):
            if v is None:
                raise SystemExit(f'0x{base + 4 * i:08X} did not come back')
            out[base + 4 * i] = v
    return out


def wr(addr, val, verify=True):
    # SoC VMAX (high half of 0x30100020, minus 1) is a 14-bit field: 16385 wrapped and wedged the shell (longexp
    # 2026-10-23), h3shs r2 asked 16624 -- refuse it here so no tool can send it
    if addr == 0x30100020 and (val >> 16) + 1 > 16384:
        raise SystemExit(f'VMAX {(val >> 16) + 1} > 16384 refused (14-bit SoC field)')
    for _ in range(6):
        P().mem_set(addr, val)
        if not verify or P().mem_get(addr)[0] == val:
            return
    raise SystemExit(f'0x{addr:08X} <- 0x{val:08X} did not stick')


def drain_sems():
    for cell in SEM_IDS:
        sid = P().mem_get(cell)[0]
        for _ in range(64):
            if call(F_WAI_SEM, sid, 1, 0) != 0:     # E_TMOUT: empty
                break


def not_recording():
    v = P().mem_get(REC_FLAG & ~3)[0]
    if v is None or (v >> (8 * (REC_FLAG & 3))) & 0xFF:
        raise SystemExit('recording (or unreadable flag): not touching BUFA')


# Native switches a capture may be bracketed with (--pre before, --post after,
# --post also on failure).  Nothing else: this is not a general shell.
SWITCHES = ('imager dclp_off ', 'imager crmf_off ', 'imager defect_collect_off ',
            'imager pdaf_cor_off ', 'menu SetIsoSensitivity',
            # RAM only; `fixed_gain 0` prints "off" but releases nothing (FUN_c03eb238):
            # a fixed gain stays until reboot
            'imager fixed_gain ', 'imager fixed_shutter ',
            'imager testpattern ',          # 0 = off
            # stock settings that pick the live-view sensor mode (supported values only;
            # the original goes back with --post)
            'menu SetMovRecSize', 'menu SetMovFramerate', 'menu SetMovBiningSupport', 'menu SetCropMode',
            # live-view magnify (1:1 readout) toggles on the centre button
            'key OKON', 'key OKOFF',
            # the firmware's own mode-register override (<=10 slots, applied when that mode is set;
            # `mode_reg_test 0 <mode>` clears).  Values in 0x: the parser is strtoul(.., 0)
            'imager mode_reg_add ', 'imager mode_reg_test ')


def switch(line):
    if not line.startswith(SWITCHES):
        raise SystemExit(f'not an allowed switch: {line!r}')
    r = P().sh(line)
    print(f'  {line} -> {r.strip()[:120]}')
    return r


def cmd_info(a):
    print(P().sh('imager mode_now').strip())
    for s in ('SetIsoSensitivity', 'SetMovRecSize', 'SetMovFramerate', 'SetMovBiningSupport', 'SetCropMode',
              'SetMovRecFormat'):
        print(P().sh(f'menu {s}').strip())
    print(P().sh('imager').strip()[:3000])
    if a.menu:
        print(P().sh('menu').strip())


# ---- IMXB bus logger (buslog/): every sensor register write --------------------
BUS_BUILD = HERE / 'buslog' / 'build' / 'build.json'


def bus_state():
    """The logger's state (cached alias), from this boot's LOAD.LOG."""
    import re, subprocess, cave
    cache = HERE / 'captures' / '.bus_state.json'            # one LOAD.LOG read per boot (0.8 s each, twice a config)
    boot = cave.boot_id()
    try:
        c = json.loads(cache.read_text())
        if c['boot'] == boot and P().mem_get(c['st'])[0] == 0x42584D49:
            return c['st']
    except Exception:                                        # noqa: BLE001 -- no cache, or a stale one
        pass
    log = HERE / 'captures' / '.LOAD.LOG'
    log.parent.mkdir(exist_ok=True)
    subprocess.run([sys.executable, '-B', str(SHELL / 'getfile.py'), r'\fpSup\LOAD.LOG', str(log),
                    '--size', '0x2000', '--partial'], check=True, cwd=SHELL, capture_output=True)
    for line in log.read_text('ascii', 'replace').splitlines():
        m = re.match(r'^0A ([0-9A-F]{8}) [0-9A-F]{8} ?IMXB\.BIN', line.strip(), re.I)
        if m:
            st = int(m.group(1), 16) + json.loads(BUS_BUILD.read_text())['state_off']
            if P().mem_get(st)[0] != 0x42584D49:
                raise SystemExit(f'no IMXB state at 0x{st:08X}')
            cache.write_text(json.dumps(dict(boot=boot, st=st)))
            return st
    raise SystemExit('IMXB.BIN is not loaded this boot')


def bus_on(st):
    wr(st + 4, 0)
    wr(st + 8, 0)
    wr(st + 4, 1)


def bus_subs(st, pairs):
    """IMXB v2 substitution table: [(reg, val)], at most 8; [] turns it off."""
    if len(pairs) > 8:
        raise SystemExit('at most 8 substitutions')
    wr(st + 20, 0)                                   # off while the table changes
    for i, (reg, val) in enumerate(pairs):
        wr(st + 32 + 4 * i, (reg << 16) | (val & 0xFF))
    wr(st + 20, len(pairs))


def bus_dump(st):
    """[(tick_us, reg, val, caller)] since bus_on; logging stops first."""
    wr(st + 4, 0)
    n, cap = P().mem_get(st + 8, 2)
    call(F_DCACHE)                                   # the shim writes through the cached alias
    k = min(n, cap)
    if not k:
        return []
    first = n - k
    raw_at = st - 0x80000000 if st >= 0xC0000000 else st      # read memory, not cache
    length = (64 + 16 * cap + 1023) & ~1023
    P().mem_window(WIN, raw_at, length, 1)
    try:
        ring = P().mem_read(raw_at, length, label='buslog')
    finally:
        P().mem_window(WIN, raw_at, length, 0)
    out = []
    for i in range(first, n):
        out.append(struct.unpack_from('<4I', ring, 64 + 16 * (i & (cap - 1))))
    return out


def cmd_bus(a):
    st = bus_state()
    if a.op == 'on':
        bus_on(st)
        print(f'logging at 0x{st:08X}')
    elif a.op == 'off':
        wr(st + 4, 0)
    else:
        ents = bus_dump(st)
        rows = [dict(t=t, reg=f'0x{r:04X}', val=f'0x{v:02X}', lr=f'0x{lr:08X}') for t, r, v, lr in ents]
        pathlib.Path(a.out).write_text(json.dumps(rows, indent=0))
        print(f'{len(rows)} writes -> {a.out}')


def pulse_rec():
    """One complete movie-button press (fp-camera-control §3).  Never retried:
    a timed-out reply may still have toggled recording."""
    P().sh('key MOVON', retries=0)
    time.sleep(0.12)
    P().sh('key MOVOFF', retries=0)


def cmd_rec(a):
    """A short take with the bus logger on.  USB carries only the two pulses;
    nothing else is sent until 10 s after the stop (no-usb-during-rec-or-playback)."""
    st = bus_state()
    if 'app_current -> 2' not in P().sh('status get app_current'):
        raise SystemExit('not in CINE')
    if 'is_recording -> 0' not in P().sh('status get is_recording'):
        raise SystemExit('already recording')
    out = pathlib.Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    bus_on(st)
    for line in a.pre:
        switch(line)
    if a.pre:
        time.sleep(3)
    pulse_rec()
    time.sleep(a.secs)
    pulse_rec()
    time.sleep(10)
    rec = P().sh('status get is_recording').strip()
    print(rec)
    if 'is_recording -> 0' not in rec:
        print('still recording: one more pulse')
        pulse_rec()
        time.sleep(10)
    ents = bus_dump(st)
    (out / 'bus.json').write_text(json.dumps(
        [dict(t=t, reg=f'0x{r:04X}', val=f'0x{v:02X}', lr=f'0x{lr:08X}') for t, r, v, lr in ents], indent=0))
    took = P().mem_get(0xC343B590)[0]                  # the mode the take used (mode-after-take-probe)
    for line in a.post:
        switch(line)
    (out / 'mode_now.txt').write_text(P().sh('imager mode_now') + f'\ntake_mode {took}\n')
    print(f'bus: {len(ents)} sensor writes; take mode {took}')


def cmd_focus(a):
    """CINE: a half press (S1) runs AF; S2 would start a recording."""
    if 'app_current -> 2' not in P().sh('status get app_current'):
        raise SystemExit('not in CINE: not pressing anything')
    P().sh('key S1ON', retries=0)
    time.sleep(a.hold)
    P().sh('key S1OFF', retries=0)
    print('focus: S1 held', a.hold, 's')


def phys(addr):
    return addr - 0x40000000 if addr < 0xC0000000 else addr - 0xC0000000


def cmd_peek(a):
    base = peek()
    path = HERE / 'captures' / f'bufa_peek_{time.strftime("%Y%m%d-%H%M%S")}.json'
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps({f'0x{k:08X}': f'0x{v:08X}' for k, v in base.items()}, indent=1))
    for k in sorted(base):
        if base[k]:
            print(f'0x{k:08X} = 0x{base[k]:08X}')
    print('saved', path)


def restore(base, out):
    startstop(100)
    call(F_CBCLR)
    wr(0x30182048, 0xFFFFFFFE, verify=False)        # status: write 0 clears
    for addr in RESTORE:
        wr(addr, base[addr])
    drain_sems()
    call(F_CLR_FLG, P().mem_get(FLG_ID)[0], 0xFFFFFFFE)
    after = peek()
    diff = {f'0x{k:08X}': [f'0x{base[k]:08X}', f'0x{after[k]:08X}'] for k in base if base[k] != after[k]}
    (out / 'restore_diff.json').write_text(json.dumps(diff, indent=1))
    print('differs from baseline after restore:', diff or 'nothing')


NOW_MS = 0xC301EAE4                              # camera uptime in ms: drops when it reboots


def keep_load(path, size):
    """--keep: the two frame buffers from an earlier capture of this same boot, or None.
    Allocating ~40 MB of class 10 per capture raced liveview's own allocations on the mode switch and
    blocked the shell inside the allocator (2026-10-20, three wedges); one allocation per boot avoids it."""
    if not path or not pathlib.Path(path).exists():
        return None
    k = json.loads(pathlib.Path(path).read_text())
    now = P().mem_get(NOW_MS)[0]
    if now is None or now < k['seen'] or k['size'] < size:
        pathlib.Path(path).unlink()                  # another boot (or too small): those addresses are not ours
        if k['size'] < size and now is not None and now >= k['seen']:
            import imxl
            imxl.give_back([tuple(h) for h in k['held']])
        return None
    k['seen'] = now
    pathlib.Path(path).write_text(json.dumps(k))
    return [tuple(h) for h in k['held']]


def keep_save(path, held, size):
    if path:
        pathlib.Path(path).write_text(json.dumps(dict(held=held, size=size, seen=P().mem_get(NOW_MS)[0] or 0)))


def release(path, held):
    """Give the buffers back unless --keep holds them for the next capture."""
    if not path:
        import imxl
        imxl.give_back(held)


def cmd_frame(a):
    import imxl
    import cave
    not_recording()
    base = peek()
    if base[CB_2] or base[CB_A0]:
        raise SystemExit(f'BUFA0 callbacks are in use: {base[CB_A0]:#x} {base[CB_2]:#x}')
    if base[0x30182000] & 0x1F or base[0x30002060] & 1:
        raise SystemExit('BUFA0 is already running')
    out = pathlib.Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / 'baseline.json').write_text(json.dumps({f'0x{k:08X}': f'0x{v:08X}' for k, v in base.items()}, indent=1))

    imxl.HEAP_CLASS = a.heap_class
    st = cave.claim('imxl.bufa.struct', 64)
    held, done, h, words, guards = [], None, 0, 0, []
    subs = [tuple(int(x, 0) for x in s.split('=')) for s in a.sub]
    bst = bus_state() if (a.bus or subs) else None
    if bst:
        bus_on(bst)
    if subs:
        bus_subs(bst, subs)
    try:
        for line in a.pre:
            switch(line)
        if a.pre:
            time.sleep(a.settle)
        mode_now = P().sh('imager mode_now')
        (out / 'mode_now.txt').write_text(mode_now)
        print('  mode:', next((l.strip() for l in mode_now.splitlines() if l[:3].isdigit()), '?'))
        # (a) configure --------------------------------------------------------
        drain_sems()
        wr(0x30000804, 0xFFFFFFFE, verify=False)       # pulse register: no read-back
        startstop(100)
        P().put(st, bytes(20), 'crop  ')
        call(F_A0CROP, 1, st)
        P().put(st, struct.pack('<I', 1) + bytes(16), 'crop  ')
        call(F_A0CROP, 1, st)
        win, vm = P().mem_get(0x30100024)[0], P().mem_get(0x30100020)[0]   # the running mode's
        base[0x30100024], base[0x30100020] = win, vm    # restore to them, not to the pre-switch ones
        if a.ystart is not None or a.yend is not None:  # receiver window: shared with liveview
            y0 = win >> 16 if a.ystart is None else a.ystart
            y1 = win & 0xFFFF if a.yend is None else a.yend
            wr(0x30100024, (y0 << 16) | y1)
        if a.vmax:                                      # SoC frame length: VMAX-1 in the high half
            wr(0x30100020, ((a.vmax - 1) << 16) | (vm & 0xFFFF))
            c0 = int(P().sh('imager mode_now').split('frame_count:')[1][:8], 10)   # printed in decimal
            t0 = time.time()
            time.sleep(2.0)
            c1 = int(P().sh('imager mode_now').split('frame_count:')[1][:8], 10)
            fps = (c1 - c0) / (time.time() - t0)
            (out / 'fps.txt').write_text(f'{fps:.3f}\n')
            print(f'  vmax {a.vmax}: {fps:.2f} fps measured')
        P().put(st, bytes(20), 'window')                # kind 0 = receiver window, 12-bit, no cb
        call(F_WINDOW, st)
        h, words = P().mem_get(0x30182110, 2)
        size = h * words * 4
        print(f'height {h}  line {words} words ({words * 4} B)  frame {size} B')
        if not (0 < h <= 4096 and 0 < words <= 0x1000):
            raise SystemExit('implausible geometry: stopping before arm')
        if a.mux != 1:
            wr(0x300F06B0, (base[0x300F06B0] & ~7) | a.mux)

        # (b) arm --------------------------------------------------------------
        kept = keep_load(a.keep, size)
        if kept:
            held = kept
        else:
            for _ in range(2):
                addr, desc = imxl.heap(0, max(size, a.keep_size))
                if not addr:
                    raise SystemExit('allocator refused')
                held.append((addr, desc))
            keep_save(a.keep, held, max(size, a.keep_size))
        buf, scratch = (x[0] - 0x80000000 if x[0] >= 0xC0000000 else x[0] for x in held)
        print(f'buf 0x{buf:08X}  scratch 0x{scratch:08X}')
        tail = buf + size - 16                          # MEM1 pads to 1 KiB: mem set instead
        for i in range(4):
            wr(tail + 4 * i, 0xA5A5A5A5)
        guards = [x + size + 0x100 for x in (buf, scratch)]   # past the frame: a DMA overrun lands here
        for g in guards:
            wr(g, 0x5AFE5AFE)
        call(F_DCACHE)
        call(F_SETADDR, buf)
        a180 = P().mem_get(0x30182180)[0]
        if a180 != phys(buf) >> 2:
            raise SystemExit(f'0x30182180 = {a180:#x}, expected {phys(buf) >> 2:#x}')
        t0 = time.time()
        startstop(10)

        # (c) one frame into buf, then steer the next ones to scratch -----------
        while time.time() - t0 < 2.0:
            s, a184 = P().mem_get(0x30182048)[0], P().mem_get(0x30182184)[0]
            sent = P().mem_get(tail)[0]
            if sent != 0xA5A5A5A5 or (a184 and a184 != phys(buf) >> 2):
                done = dict(t=round(time.time() - t0, 3), status=s, a184=a184, sentinel=sent)
                break
        wr(0x30182180, phys(scratch) >> 2)
        time.sleep(0.15)
        print('first frame:', done)
    except BaseException:
        if subs:
            bus_subs(bst, [])
        restore(base, out)
        release(a.keep, held)
        for line in a.post:
            switch(line)
        raise
    # (d) stop and restore ---------------------------------------------------
    over = [hex(g) for g in guards if P().mem_get(g)[0] != 0x5AFE5AFE]
    (out / 'guard.txt').write_text(f'overrun past frame end: {over or "none"}\n')
    if over:
        print('DMA OVERRUN past the frame end at', over)
    if subs:
        bus_subs(bst, [])
    restore(base, out)
    for line in a.post:
        switch(line)
    if bst:
        ents = bus_dump(bst)
        (out / 'bus.json').write_text(json.dumps(
            [dict(t=t, reg=f'0x{r:04X}', val=f'0x{v:02X}', lr=f'0x{lr:08X}') for t, r, v, lr in ents], indent=0))
        print(f'bus: {len(ents)} sensor writes')

    if done is None:
        print('no frame seen')
        release(a.keep, held)
        return
    P().mem_window(WIN, buf, size, 1)
    try:
        raw = P().mem_read(buf, size, label='frame ')
    finally:
        P().mem_window(WIN, buf, size, 0)
    release(a.keep, held)
    (out / 'frame.raw').write_bytes(raw)
    (out / 'frame.json').write_text(json.dumps(dict(height=h, line_words=words, mux=a.mux, ystart=a.ystart,
                                                    pre=a.pre, post=a.post, sub=a.sub,
                                                    window=base[0x30100024], first=done), indent=1))
    print('saved', out / 'frame.raw')


def cmd_burst(a):
    """N consecutive BUFA0 frames into N buffers via IMXB v3's frame_cb, with the
    completion time of each; optionally alternating register values per frame."""
    import imxl
    import cave
    import numpy as np
    not_recording()
    st = bus_state()
    info = json.loads(BUS_BUILD.read_text())
    cp = st + info['capt']
    cb = P().mem_get(cp + 0x4C)[0]
    if not cb:
        raise SystemExit('IMXB has no frame_cb (needs version 3)')
    base = peek()
    if base[CB_2] or base[CB_A0] or base[0x30182000] & 0x1F or base[0x30002060] & 1:
        raise SystemExit('BUFA0 busy')
    out = pathlib.Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    imxl.HEAP_CLASS = a.heap_class
    alts = []
    for s in a.alt:
        reg, vals = s.split('=')
        ev, od = (int(x, 0) for x in vals.split(','))
        alts.append((int(reg, 0), (od << 8) | ev))
    s_ = cave.claim('imxl.bufa.struct', 64)
    held = []
    try:
        if alts:
            bus_subs(st, alts)
            wr(st + 28, 1)
        for line in a.pre:
            switch(line)
        time.sleep(a.settle)
        drain_sems()
        wr(0x30000804, 0xFFFFFFFE, verify=False)
        startstop(100)
        P().put(s_, bytes(20), 'crop  ')
        call(F_A0CROP, 1, s_)
        P().put(s_, struct.pack('<I', 1) + bytes(16), 'crop  ')
        call(F_A0CROP, 1, s_)
        P().put(s_, bytes(16) + struct.pack('<I', cb), 'window')   # kind 0, 12-bit, cb = frame_cb
        call(F_WINDOW, s_)
        h, words = P().mem_get(0x30182110, 2)
        size = h * words * 4
        for _ in range(a.n + 1):
            addr, desc = imxl.heap(0, size)
            if not addr:
                raise SystemExit(f'allocator refused after {len(held)} buffers')
            held.append((addr, desc))
        bufs = [x[0] - 0x80000000 if x[0] >= 0xC0000000 else x[0] for x in held]
        park, frames = bufs[-1], bufs[:-1]
        wr(cp + 0, len(frames)); wr(cp + 4, 0); wr(cp + 8, phys(park) >> 2)
        for i, f in enumerate(frames):
            wr(cp + 0xC + 4 * i, phys(f) >> 2)
        call(F_DCACHE)
        call(F_SETADDR, park)              # the first frame or two land in the park buffer
        startstop(10)
        t0 = time.time()
        while time.time() - t0 < 5 and P().mem_get(cp + 4)[0] < len(frames) + 2:
            time.sleep(0.05)
        startstop(100)
        n_done = P().mem_get(cp + 4)[0]
        log = P().mem_get(cp + 0x50, 2 * min(n_done, info['capt_log']))
    finally:
        if alts:
            wr(st + 28, 0)
            bus_subs(st, [])
        restore(base, out)
        for line in a.post:
            switch(line)
    ents = [(log[2 * k], log[2 * k + 1]) for k in range(len(log) // 2)]
    meta = dict(n=len(frames), height=h, line_words=words, done=n_done, alt=a.alt, pre=a.pre,
                buffers=[f'0x{f:08X}' for f in frames], park=f'0x{park:08X}',
                completions=[dict(t=t, addr=f'0x{d:08X}') for t, d in ents])
    dts = np.diff([t for t, _ in ents]) if ents else []
    print(f'{n_done} completions; intervals µs: {list(dts)[:12]}')
    # each buffer's last completed frame (the DMA writes it next-but-one after we pointed there)
    for i, f in enumerate(frames):
        P().mem_window(WIN, f, size, 1)
        try:
            (out / f'f{i:02d}.raw').write_bytes(P().mem_read(f, size, label=f'f{i:02d}  '))
        finally:
            P().mem_window(WIN, f, size, 0)
    imxl.give_back(held)
    (out / 'burst.json').write_text(json.dumps(meta, indent=1))
    print('saved', out)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    sub.add_parser('peek').set_defaults(f=cmd_peek)
    s = sub.add_parser('info')
    s.set_defaults(f=cmd_info)
    s.add_argument('--menu', action='store_true', help='also list the menu commands (read only)')
    s = sub.add_parser('bus')
    s.set_defaults(f=cmd_bus)
    s.add_argument('op', choices=('on', 'off', 'dump'))
    s.add_argument('out', nargs='?', default='captures/bus.json')
    s = sub.add_parser('burst')
    s.set_defaults(f=cmd_burst)
    s.add_argument('out')
    s.add_argument('--n', type=int, default=6, choices=range(1, 17))
    s.add_argument('--alt', action='append', default=[], metavar='REG=EVEN,ODD',
                   help='IMXB v3: REG alternates between two values frame by frame')
    s.add_argument('--pre', action='append', default=[])
    s.add_argument('--post', action='append', default=[])
    s.add_argument('--settle', type=float, default=1.0)
    s.add_argument('--heap-class', type=int, default=0)
    s = sub.add_parser('rec')
    s.set_defaults(f=cmd_rec)
    s.add_argument('out')
    s.add_argument('--secs', type=float, default=3.0)
    s.add_argument('--pre', action='append', default=[], help='allowed switch before the take')
    s.add_argument('--post', action='append', default=[], help='its undo, after the take')
    s = sub.add_parser('focus')
    s.set_defaults(f=cmd_focus)
    s.add_argument('--hold', type=float, default=2.0)
    s = sub.add_parser('frame')
    s.add_argument('--pre', action='append', default=[], help='allowed switch before the capture')
    s.add_argument('--post', action='append', default=[], help='its undo, run after (and on failure)')
    s.add_argument('--settle', type=float, default=1.0, help='seconds after --pre')
    s.add_argument('--bus', action='store_true', help='record every sensor write (IMXB) around it')
    s.add_argument('--heap-class', type=int, default=0, help='firmware allocator class for the two buffers')
    s.add_argument('--keep', help='JSON file: reuse two buffers across captures of one boot (allocated once)')
    s.add_argument('--keep-size', type=int, default=0, help='--keep: allocate at least this many bytes per buffer')
    s.add_argument('--sub', action='append', default=[], metavar='REG=VAL',
                   help='IMXB v2: every write of REG goes out as VAL during the capture (<= 8)')
    s.set_defaults(f=cmd_frame)
    s.add_argument('out')
    s.add_argument('--mux', type=int, default=1, choices=range(6))
    s.add_argument('--ystart', type=int, help='receiver window first row (0x30100024 high half)')
    s.add_argument('--yend', type=int, help='receiver window end row (0x30100024 low half)')
    s.add_argument('--vmax', type=int, help='SoC VMAX (0x30100020 high half = VMAX-1); fps measured')
    a = ap.parse_args()
    a.f(a)


if __name__ == '__main__':
    main()
