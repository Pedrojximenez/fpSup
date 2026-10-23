"""Consecutive-frame burst inside a fastsweep Session (RESEARCH_DIRECTION #3): IMXB v3 frame_cb steers BUFA0 through
up to 16 buffers and logs {tick_us, done_addr} for up to CAPT_LOG (64) completions -- the interrupt-level proof of
whether every frame arrives at the set rate. Same steps as bufa_probe.cmd_burst, but on the Session's own window, and
the Session's window/scratch are put back afterwards so it can keep grabbing and close normally.
"""
import json, struct, time
import bufa_probe as B
import imxl, cave, l7


def burst(s, n=16, wait=1.0, enum=0):
    info = json.loads(B.BUS_BUILD.read_text())
    st = B.bus_state()
    cp = st + info['capt']
    cb = B.P().mem_get(cp + 0x4C)[0]
    if not cb:
        raise SystemExit('IMXB has no frame_cb (needs version 3)')
    sw = cave.claim('imxl.bufa.struct', 64)
    held = []
    try:
        B.startstop(100)
        win = bytearray(16); win[0xE] = enum                           # 0 = 12-bit, 1 = 14-bit packing
        B.P().put(sw, bytes(win) + struct.pack('<I', cb), 'window')
        B.call(B.F_WINDOW, sw)
        h, words = B.P().mem_get(0x30182110, 2)
        size = h * words * 4
        # ONE allocation carved into n+1 frame buffers (2026-10-23): n+1 separate allocs + frees borrowed the echo
        # slot 2(n+1) times per burst, and the shell wedged inside that loop (12h2, HDR 12 crop: the log stops in the
        # free calls) -- now 2 borrows per burst
        step = (size + 0x3FF) // 0x400 * 0x400
        addr, desc = imxl.heap(0, step * (n + 1))
        if not addr:
            raise SystemExit(f'allocator refused {step * (n + 1)} B')
        held.append((addr, desc))
        a0 = addr - 0x80000000 if addr >= 0xC0000000 else addr
        bufs = [a0 + i * step for i in range(n + 1)]
        park, frames = bufs[-1], bufs[:-1]
        B.wr(cp + 0, len(frames)); B.wr(cp + 4, 0); B.wr(cp + 8, B.phys(park) >> 2)
        for i, f in enumerate(frames):
            B.wr(cp + 0xC + 4 * i, B.phys(f) >> 2)
        B.call(B.F_DCACHE)
        B.call(B.F_SETADDR, park)
        B.startstop(10)
        t0 = time.time()
        while time.time() - t0 < wait and B.P().mem_get(cp + 4)[0] < info['capt_log']:
            time.sleep(0.02)
        B.startstop(100)
        done = B.P().mem_get(cp + 4)[0]
        k = min(done, info['capt_log'])
        log = B.P().mem_get(cp + 0x50, 2 * k)
        ents = [(log[2 * j], log[2 * j + 1]) for j in range(k)]
        raws = []
        for f in frames:
            B.P().mem_window(B.WIN, f, size, 1)
            try:
                raws.append(B.P().mem_read(f, size, label='burst '))
            finally:
                B.P().mem_window(B.WIN, f, size, 0)
        return dict(h=h, words=words, done=done, ents=ents, frames=[B.phys(f) >> 2 for f in frames]), raws
    finally:
        B.wr(cp + 0, 0)
        imxl.give_back(held)
        back = bytearray(20); back[0xE] = enum
        B.P().put(sw, bytes(back), 'window'); B.call(B.F_WINDOW, sw)  # back to the Session's plain window
        s.h, s.words = B.P().mem_get(0x30182110, 2)
        B.call(B.F_SETADDR, s.scratch)
        B.startstop(10)
