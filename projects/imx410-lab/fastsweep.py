#!/usr/bin/env python3
"""Fast register sweep: one magnify entry, one buffer allocation, BUFA0 left running into scratch, and every
point = one direct sensor write + one frame grab. Seconds per register instead of minutes.

    fastsweep.py PLAN.json OUT_DIR

PLAN: {"yend": 600, "settle": 0.12, "registers": [{"reg": "0x5D", "values": ["0x00", ...], "restore": "0x03"}, ...]}
  restore   value written after the register's last point (its power-on / stock value); without it the
            register is left at its last value and the run ends after that register with "needs reset".

Why not sweep.py: every point there re-enters magnify, re-arms BUFA0, allocates/frees ~40 MB of class 10 and
spends ~15 callfn round trips -- 4-5 s per point, and the allocations held across magnify switches froze the
whole camera about once per 400 points (2026-10-20). Here the buffers are taken once, after the switch into
mode 10, and given back before leaving it, so liveview never allocates while we hold them.

Sensor writes go out through sensor_read/spi_read.S with chip-ID 0x81 (a real write, IRQs masked so the AE
writer cannot interleave on the bus). Registers the firmware rewrites every frame (gain, shutter) cannot be swept
this way. A register that only latches at a mode set will show nothing here: check against sweep.py results.
Each frame is grabbed twice-armed (sentinel reset after the first trip) so the saved frame is a whole one.
"""
import json, pathlib, struct, sys, time

HERE = pathlib.Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE / 'sensor_read')]
import bufa_probe as B                                                  # noqa: E402
import sweep                                                            # noqa: E402

SENT = 0xA5A5A5A5


def cached_assemble():
    """callfn assembles callfn.S (a clang run) on every call; once per process is enough."""
    import callfn, armasm
    if getattr(armasm, '_memo_orig', None) is None:
        armasm._memo_orig = armasm.assemble
    orig = armasm._memo_orig
    memo = {}
    def asm(src, defines=()):
        k = (str(src), tuple(defines))
        if k not in memo:
            memo[k] = orig(src, defines)
        return memo[k]
    callfn.assemble = asm
    armasm.assemble = asm                    # imxl.heap / spi_read / bufa stubs import it per call: same memo
    import cave                              # cave.claim asks the camera for the boot id over fpsh twice per claim
    if not getattr(cave, '_boot_memo', None):    # (12 claims a config = 1.3 s); one process never spans a reboot --
        b0 = cave.boot_id                         # a reboot fails the config and the next one is a new process
        memo_b = {}
        def boot_id():
            if 'v' not in memo_b:
                memo_b['v'] = b0()
            return memo_b['v']
        cave.boot_id = boot_id
        cave._boot_memo = True
    # callfn re-uploads its code before every call (word by word: ~18 ms). getfile/putfile share that area, so the
    # bytes are still checked each time -- one readback, and the upload only when they differ (2026-10-24 profile)
    if not getattr(callfn, '_own_code', False):    # callfn in its own block too (see imxl.heap): nothing else writes it
        callfn.CODE = cave.claim('imxl.callfn.code', 160)
        callfn.CODE_END = callfn.CODE + 160
        callfn._own_code = True
    if not getattr(callfn, '_put_checked', False):
        import putfile, struct as _st
        put0 = callfn.put
        def put(addr, blob, label, *a, **k):
            n = (len(blob) + 3) // 4
            cur = putfile.mem_get(addr, n)
            if None not in cur and _st.pack(f'<{n}I', *cur) == bytes(blob) + bytes(-len(blob) % 4):
                return
            return put0(addr, blob, label, *a, **k)
        callfn.put = put
        callfn._put_checked = True


CAMERA_WAIT = True      # 2026-10-24: wait for the frame on the camera (bufa_grab2.S), not ~100 host polls a frame


class Session:
    def __init__(self, out, yend, pair=False, mode=10, min_alloc=0):
        import imxl, cave
        from armasm import assemble
        self.out, self.held, self.base, self.pair, self.mode = out, [], None, pair, mode
        self.alloc = max(0, min_alloc)
        B.not_recording()
        if 'app_current -> 2' not in B.P().sh('status get app_current'):
            raise SystemExit('not in CINE')
        if mode == 10:
            B.switch('key OKON'); B.switch('key OKOFF')                  # into magnify = mode 10
            self.entered = True
            # fixed 1.5 s again (2026-10-24): polling mode_now and going on 0.3 s after it read 10 was followed by two
            # allocator wedges in 14-bit full frame -- mode_now changes before the firmware's switch has finished
            time.sleep(1.5)
        cur = B.P().sh('imager mode_now')
        if f',{mode:04d},' not in cur:
            raise SystemExit(f'not mode {mode}: {cur.strip()[-120:]}')
        self.base = base = B.peek()
        if base[B.CB_2] or base[B.CB_A0] or base[0x30182000] & 0x1F or base[0x30002060] & 1:
            raise SystemExit('BUFA0 busy')
        st = cave.claim('imxl.bufa.struct', 64)
        B.drain_sems()
        B.wr(0x30000804, 0xFFFFFFFE, verify=False)
        B.startstop(100)
        B.P().put(st, bytes(20), 'crop  '); B.call(B.F_A0CROP, 1, st)
        B.P().put(st, struct.pack('<I', 1) + bytes(16), 'crop  '); B.call(B.F_A0CROP, 1, st)
        win = B.P().mem_get(0x30100024)[0]
        self.base_window = win              # its high half = the first image row: what decoding needs
        base[0x30100024], base[0x30100020] = win, B.P().mem_get(0x30100020)[0]
        self.window = (0 << 16) | (yend or (win & 0xFFFF))
        B.wr(0x30100024, self.window)
        B.P().put(st, bytes(20), 'window'); B.call(B.F_WINDOW, st)
        self.h, self.words = B.P().mem_get(0x30182110, 2)
        self.size = self.h * self.words * 4
        if not (0 < self.h <= 4096 and 0 < self.words <= 0x1000):
            raise SystemExit('implausible geometry')
        imxl.HEAP_CLASS = 10
        for _ in range(2):
            addr, desc = imxl.heap(0, max(self.size + 0x1000, min_alloc))
            if not addr:
                raise SystemExit('allocator refused')
            self.held.append((addr, desc))
        self.buf, self.scratch = (x[0] - 0x80000000 if x[0] >= 0xC0000000 else x[0] for x in self.held)
        self.tail = self.buf + self.size - 16
        self.guard = self.buf + self.size + 0x100
        B.wr(self.guard, 0x5AFE5AFE)
        B.call(B.F_DCACHE)
        B.call(B.F_SETADDR, self.scratch)                                 # runs into scratch between grabs
        B.startstop(10)
        code = assemble(HERE / 'sensor_read' / 'spi_read.S')
        self.spi = cave.claim('imxl.spiread', 192)
        self.res = cave.claim('imxl.spiread.res', 16)
        B.P().put(self.spi, code + bytes(-len(code) % 4), 'spird ')
        B.call(B.F_DCACHE)
        print(f'session: mode 10, frame {self.h} x {self.words} words, buf 0x{self.buf:08X} scratch 0x{self.scratch:08X}')

    def write(self, reg, val):
        hdr = 0x81 | (reg >> 8) << 8 | (reg & 0xFF) << 16
        B.call(self.spi, hdr, val, self.res)

    def _trip(self, timeout=1.0):
        for i in range(4):
            B.wr(self.tail + 4 * i, SENT)
        t0 = time.time()
        while time.time() - t0 < timeout:
            if B.P().mem_get(self.tail)[0] != SENT:
                return True
        return False

    def grab_cb(self, timeout=1.0):
        """sensor_read/bufa_grabcb.S as the BUFA0 completion callback for 3 completions: NEXT -> buf, NEXT -> scratch,
        then the finished frame's address is checked against buf. Touches nothing the firmware waits on."""
        import cave
        if not getattr(self, '_gcb', None):
            from armasm import assemble
            code = assemble(HERE / 'sensor_read' / 'bufa_grabcb.S')
            at = cave.claim('imxl.bufagrabcb', 128)
            if len(code) != 120:
                raise SystemExit(f'bufa_grabcb is {len(code)} B: data offsets below assume 120')
            B.P().put(at, code, 'grabcb')
            B.call(B.F_DCACHE)
            self._gcb = at
        at = self._gcb
        STAGE, TARGET, SCRATCH, DONE, GOT = (at + o for o in (0x64, 0x68, 0x6C, 0x70, 0x74))
        bw, sw = B.phys(self.buf) >> 2, B.phys(self.scratch) >> 2
        for i in range(4):                                          # the frame's last words: proof it landed
            B.wr(self.tail + 4 * i, SENT, verify=False)               # (done_addr comes from 0x30182184, which
        B.wr(TARGET, bw); B.wr(SCRATCH, sw); B.wr(DONE, 0); B.wr(STAGE, 0)   # reads 0 here: no use as a check)
        old = B.P().mem_get(B.CB_A0)[0]
        if old:
            raise SystemExit(f'BUFA0 callback already set (0x{old:08X}): not grabbing over it')
        B.wr(B.CB_A0, at)
        try:
            t0 = time.time()
            while time.time() - t0 < timeout and B.P().mem_get(DONE)[0] != 1:
                pass
        finally:
            B.wr(B.CB_A0, 0)
            B.wr(STAGE, 3)
            B.wr(0x30182180, sw)                                    # whatever happened, back to scratch
        done, tail = B.P().mem_get(DONE)[0], B.P().mem_get(self.tail)[0]
        ok = done == 1 and tail != SENT
        if not ok:
            print(f'  grab_cb: done={done} tail=0x{tail:08X}')
        return ok

    def grabber(self):
        """sensor_read/bufa_grab2.S (registers only; bufa_grab.S consumed the completion flag and wedged 14-bit sessions),
        loaded once per Session (cave claim: same address all boot)"""
        if not getattr(self, '_grab_at', None):
            import cave
            from armasm import assemble
            code = assemble(HERE / 'sensor_read' / 'bufa_grab2.S')
            at = cave.claim('imxl.bufagrab2', 176)
            if len(code) > 176:
                raise SystemExit(f'bufa_grab2 is {len(code)} B, claim is 176')
            B.P().put(at, code + bytes(-len(code) % 4), 'bgrab ')
            B.call(B.F_DCACHE)
            self._grab_at = at
        return self._grab_at

    def grab(self, d):
        """Steer BUFA0 to buf, let one frame complete, re-arm, take the next whole one, steer back."""
        raws = []
        for _ in range(2 if self.pair else 1):                  # pair: two consecutive whole frames (temporal noise)
            if CAMERA_WAIT:                                     # completion callback steers one whole frame
                ok = self.grab_cb()
            else:
                B.wr(0x30182180, B.phys(self.buf) >> 2)
                ok = self._trip() and self._trip()
                B.wr(0x30182180, B.phys(self.scratch) >> 2)
                time.sleep(0.03)
            if not ok:
                return False
            B.P().mem_window(B.WIN, self.buf, self.size, 1)
            try:
                raws.append(B.P().mem_read(self.buf, self.size, label='frame '))
            finally:
                B.P().mem_window(B.WIN, self.buf, self.size, 0)
            if B.P().mem_get(self.guard)[0] != 0x5AFE5AFE:
                raise SystemExit('DMA overrun past the frame end')
        d.mkdir(parents=True, exist_ok=True)
        (d / 'frame.raw').write_bytes(raws[0])
        if len(raws) > 1:
            (d / 'frame2.raw').write_bytes(raws[1])
        (d / 'frame.json').write_text(json.dumps(dict(height=self.h, line_words=self.words, mux=1, ystart=0, mode=self.mode,
                                                      window=self.base_window, fast=True, t=time.time()), indent=1))
        sweep.summarize(d)
        return True

    def close(self):
        import imxl
        try:
            if self.base:
                B.restore(self.base, self.out)
        finally:
            imxl.give_back(self.held)
            self.held = []
            if getattr(self, 'entered', False):
                B.switch('key OKON'); B.switch('key OKOFF')               # back to mode 8


def changed(out, d):
    """Did this point differ from the latest reference: black > 4 DN, any phase > 3 %, or row/column structure
    above 4x the ref-a/ref-b floor. Used only to decide whether the register must be reset before the next one."""
    if not (d / 'summary.npz').exists():
        return True
    import numpy as np
    refs = sorted([r for r in out.glob('ref_m*_*') if (r / 'summary.npz').exists()], key=lambda r: sweep.load_summary(r)[3])
    fx, xb, xs, t = sweep.load_summary(d)
    earlier = [r for r in refs if sweep.load_summary(r)[3] < t] or refs[:1]
    fr, rb, rs, _ = sweep.load_summary(earlier[-1])
    if xs != rs or abs(xb - rb) > 4:
        return True
    c = sweep.compare(fx, fr)
    fl = sweep.compare(sweep.load_summary(refs[0])[0], sweep.load_summary(refs[1])[0]) if len(refs) > 1 else dict(rows=0.05, cols=0.05)
    return (np.abs(c['phase']).max() > 0.03 or c['rows'] > 4 * max(fl['rows'], 0.01)
            or c['cols'] > 4 * max(fl['cols'], 0.01))


def main():
    import fcntl
    lock = open(HERE / 'captures' / '.sweep.lock', 'w')                  # shared with sweep.py: one at a time
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit('another sweep is running')
    plan = json.loads(pathlib.Path(sys.argv[1]).read_text())
    out = pathlib.Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    cached_assemble()
    log = open(out / 'run.log', 'a')
    say = lambda s: (print(s, flush=True), log.write(s + '\n'), log.flush())
    yend, settle = plan.get('yend', 600), plan.get('settle', 0.12)
    s = None
    def reset(why):
        nonlocal s
        say(f'{time.strftime("%T")} reset ({why})')
        if s:
            s.close()
            s = None
        sweep.KEEP = None
        sweep.fastreboot()                                # poff 1 + AF; the sensor comes back from power-on
    try:
        for k, item in enumerate(plan['registers']):
            if (out / 'STOP').exists():
                say('stopped'); break
            todo = [v for v in item['values'] if not sweep.captured(out / f'{item["reg"]}_{v}_m{plan.get("mode", 10)}')
                    and not (out / f'{item["reg"]}_{v}_m{plan.get("mode", 10)}' / 'nofail').exists()]
            if not todo:
                continue
            if s is None:
                s = Session(out, yend, plan.get('pair', False), plan.get('mode', 10))
                for wr_, wv in plan.get('with', []):            # references are taken with the context on
                    s.write(int(wr_, 16), int(wv, 16))
                time.sleep(settle)
                d = out / f'ref_m{plan.get("mode", 10)}_r{k:03d}'                 # a reference for every fresh session
                if not sweep.captured(d):
                    s.grab(d)
                for tag in ('a', 'b'):
                    d = out / f'ref_m{plan.get("mode", 10)}_{tag}'
                    if not sweep.captured(d):
                        say(f'{time.strftime("%T")} {d.name} {"ok" if s.grab(d) else "no frame"}')
            ev = plan.get('ref_every')
            if ev and k % ev == 0 and not sweep.captured(out / f'ref_m{plan.get("mode", 10)}_r{k:03d}'):
                s.grab(out / f'ref_m{plan.get("mode", 10)}_r{k:03d}')              # drift check inside a long session
            reg, t0, dead = int(item['reg'], 16), time.time(), False
            for wr_, wv in plan.get('with', []) + item.get('with', []):   # context written before every value
                s.write(int(wr_, 16), int(wv, 16))
            for v in todo:
                d = out / f'{item["reg"]}_{v}_m{plan.get("mode", 10)}'
                s.write(reg, int(v, 16))
                if plan.get('latch'):                         # 0011 0 -> 1, as a mode set does (§7): some
                    s.write(0x0011, 0)                        # registers only take effect at that restart
                    time.sleep(0.03)
                    s.write(0x0011, 1)
                time.sleep(settle)
                ok = s.grab(d)
                say(f'{time.strftime("%T")} {d.name} {"ok" if ok else "no frame"}')
                if not ok:                                    # the sensor stopped: remember, reset, next register
                    d.mkdir(parents=True, exist_ok=True)
                    (d / 'nofail').write_text('no frame seen\n')
                    dead = True
                    break
            if dead:
                reset(f'{item["reg"]} stopped the sensor')
            elif not any(changed(out, out / f'{item["reg"]}_{v}_m{plan.get("mode", 10)}') for v in item['values']):
                say(f'   {item["reg"]}: no visible effect, left as is (no reset)')   # cannot matter to the next one
            elif 'restore' in item:
                s.write(reg, int(item['restore'], 16))
                time.sleep(settle)
            else:
                reset(f'{item["reg"]} has no known stock value')
            say(f'   {item["reg"]}: {time.time() - t0:.1f} s')
        else:
            say('done')
    finally:
        if s:
            s.close()

if __name__ == '__main__':
    main()
