"""Consecutive-frame burst inside a fastsweep Session (RESEARCH_DIRECTION #3): IMXB v3 frame_cb steers BUFA0 through
up to 16 buffers and logs {tick_us, done_addr} for up to CAPT_LOG (64) completions -- the interrupt-level proof of
whether every frame arrives at the set rate. Same steps as bufa_probe.cmd_burst, but on the Session's own window, and
the Session's window/scratch are put back afterwards so it can keep grabbing and close normally.
"""
import json, struct, time
import bufa_probe as B
import imxl, cave, l7


GUARD_LOG = []


def burst(s, n=16, wait=1.0, enum=0, store=True):
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
        # store=False: timing only (smc_validate). Every frame lands in ONE buffer, so the allocation is 2 frames, not
        # n+1: 14-bit full frame x 9 = 390 MB, and freeing it wedged the shell with the UI blocked (full_v1, 2026-10-23)
        nbuf = n + 1 if store else 2
        # +1 MiB slack and guard words past the park buffer (the last one): in 14-bit full frame the heap went bad right
        # after a burst 4 times out of 4 (2026-10-24) -- suspected DMA writing past the size 0x30182110 reports
        SLACK, GUARDS = 1 << 20, (0, 0x40, 0x100, 0x400, 0x1000, 0x4000, 0x10000, 0x40000, 0xFFF00)
        addr, desc = imxl.heap(0, step * nbuf + SLACK)
        if not addr:
            raise SystemExit(f'allocator refused {step * nbuf + SLACK} B')
        held.append((addr, desc))
        a0 = addr - 0x80000000 if addr >= 0xC0000000 else addr
        bufs = [a0 + i * step for i in range(nbuf)]
        park, frames = bufs[-1], (bufs[:-1] if store else [bufs[0]] * n)
        for g in GUARDS:
            B.wr(park + size + g, 0x5AFE0000 | (g >> 4 & 0xFFFF), verify=False)
        head0 = B.P().mem_get(a0 - 0x40, 16)            # the allocator's own words before the block: read-only check
        B.call(B.F_DCACHE)
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
        hit = [g for g in GUARDS if B.P().mem_get(park + size + g)[0] != (0x5AFE0000 | (g >> 4 & 0xFFFF))]
        print(f'  burst guards past the frame end overwritten at: {[hex(g) for g in hit] or "none"}', flush=True)
        head1 = B.P().mem_get(a0 - 0x40, 16)
        print(f'  heap words before the block: {"unchanged" if head0 == head1 else "CHANGED"}', flush=True)
        GUARD_LOG.append(dict(size=size, step=step, hit=hit, head_changed=head0 != head1))
        done = B.P().mem_get(cp + 4)[0]
        k = min(done, info['capt_log'])
        log = B.P().mem_get(cp + 0x50, 2 * k)
        ents = [(log[2 * j], log[2 * j + 1]) for j in range(k)]
        raws = []
        for f in (frames if store else []):
            B.P().mem_window(B.WIN, f, size, 1)
            try:
                raws.append(B.P().mem_read(f, size, label='burst '))
            finally:
                B.P().mem_window(B.WIN, f, size, 0)
        return dict(h=h, words=words, done=done, ents=ents, frames=[B.phys(f) >> 2 for f in frames]), raws
    finally:
        B.wr(cp + 0, 0)
        imxl.give_back(held)
        # The window is the one the burst set (same enum, same geometry); only its completion callback has to go.
        # c06314d0 with the plain window hung here 3 times out of 3 in 14-bit full frame (2026-10-24, traced: the call
        # never returned, UI blocked); c06305d8 -- the part of it that matters -- is one store to [0xC37CF8CC].
        B.wr(B.CB_A0, 0)
        s.h, s.words = B.P().mem_get(0x30182110, 2)
        B.call(B.F_SETADDR, s.scratch)
        B.startstop(10)
