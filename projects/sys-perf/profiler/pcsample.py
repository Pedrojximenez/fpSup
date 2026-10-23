#!/usr/bin/env python3
"""PC-sampling profiler for the fp: install, run, read, remove.  See README.md.

    python3 -B pcsample.py check                       # read-only: confirm the static facts
    python3 -B pcsample.py install --via B --ch 3      # or --via A (wrap the OS tick)
    python3 -B pcsample.py start [--skip MS] [--limit N] [--wrap]
    python3 -B pcsample.py status
    python3 -B pcsample.py stop
    python3 -B pcsample.py read LABEL                  # -> captures/LABEL.ring + .json
    python3 -B pcsample.py names                       # tid -> task name, from stock tskmon
    python3 -B pcsample.py uninstall

Every command except `check`/`status` refuses while recording (no USB during a
take).  For a recording profile: `start --skip` long enough to press REC,
record, stop, wait 10 s, then `read`.

Install only changes pointers: A writes one word (0xC303380C, the channel-0
handler) and B registers an idle timer channel through the firmware's own
C0016210.  Both are undone by `uninstall`, and both are re-initialised by a
reboot (the timer driver rewrites its table at boot).  The code lives in a
cave.claim block and stays until reboot, so nothing can call freed code.

Uninstall order: C_EN = 0 (the ring is no longer written) -> pointer restored /
channel stopped -> calls verified to have stopped -> ring freed.

POWER OFF WITH THE PROFILER INSTALLED IS NOT TESTED: uninstall first.
"""
import argparse, json, pathlib, struct, sys, time

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SHELL = ROOT / 'fpSup' / 'fp_usb_shell'
sys.path.insert(0, str(SHELL))
from armasm import assemble, symbols  # noqa: E402

SRC = HERE / 'pcsample.S'
STATE = HERE / 'state.json'
CAPS = HERE / 'captures'

# ---------------------------------------------------------------- firmware
TICK = 0xC0016978            # channel-0 handler (OS tick)
TMR_HANDLERS = 0xC303380C    # handler table, + ch*4
TMR_HASH = 0xC3033808        # bitmap of channels with a handler
TMR_PEND_P = 0xC30337FC      # -> pending/ack page (non-zero once the driver is up)
TMR_REGS_P = 0xC30337F0      # -> channel registers, + ch*16 (+8 = running)
TIMER_START = 0xC0016210     # (ch, {count, handler, lvl, flags})
TIMER_STOP = 0xC00163F8      # (ch)
CTXTSK = 0xC3000098
SCHEDTSK = 0xC30000A0
CURTIME = 0xC301EAE4
IRQ_FRAME_PC = 0xC42F1FBC
LOWTAB = 0xC30000AC          # + irq*4 ; IRQ 4 should hold C0000E64
HLTAB = 0xC30004AC           # + irq*4 ; IRQ 4 should hold C0016000
DCACHE_ALL = 0xC000E91C
ICACHE_ALL = 0xC000EABC
ALLOC_REQ, ALLOC_GET, ALLOC_FREE = 0xC001D740, 0xC001D7F0, 0xC001D7A0

C = dict(magic=0x00, ring=0x04, mask=0x08, idx=0x0C, limit=0x10, orig=0x14, en=0x18,
         over=0x1C, frame=0x20, calls=0x24, skip=0x28, seen=0x2C)
MAGIC = 0x31534350
FREE_CHANNELS = (1, 3, 4, 6)       # no static caller of C0016210 (PC_SAMPLER_HOOKPOINTS.md)


# ------------------------------------------------------------- the camera
class Camera:
    """The live camera, through the shell tools.  Tests substitute a fake."""
    def __init__(self):
        import putfile as pf, cave, callfn
        self.pf, self.cave, self.callfn = pf, cave, callfn

    def get(self, addr, n=1):
        v = self.pf.mem_get(addr, n)
        if None in v:
            raise SystemExit(f'mem get 0x{addr:08X}: words missing {v}')
        return v

    def set(self, addr, value, tries=8):
        for _ in range(tries):
            self.pf.mem_set(addr, value)
            if self.pf.mem_get(addr)[0] == value:
                return
        raise SystemExit(f'mem set 0x{addr:08X} = 0x{value:08X} did not stick')

    def put(self, addr, blob, label):
        self.pf.put(addr, blob, label)

    def call(self, fn, r0=0, r1=0, r2=0, r3=0):
        return self.callfn.call(fn, r0=r0, r1=r1, r2=r2, r3=r3, verbose=False)

    def read(self, addr, n):
        return self.pf.read_direct(addr, n, label='ring')

    def claim(self, name, size):
        return self.cave.claim(name, size)

    def boot_id(self):
        return self.cave.boot_id()

    def sh(self, line):
        return self.pf.sh(line, retries=0, timeout_ms=15000)

    def wait(self, seconds):
        time.sleep(seconds)


def recording(cam):
    return cam.sh('status get is_recording').strip() != 'is_recording -> 0'


def guard(cam):
    if recording(cam):
        raise SystemExit('recording (or no answer): not touching the camera now')


def build():
    code = assemble(SRC)
    entry = symbols(SRC)['pcs_tick']
    assert struct.unpack_from('<I', code, 0)[0] == MAGIC and entry == 0x40
    return code, entry


def load_state(cam):
    if not STATE.exists():
        return None
    st = json.loads(STATE.read_text())
    if st.get('boot') != cam.boot_id():
        print('state.json is from another boot: the camera was restarted, nothing is installed')
        STATE.unlink()
        return None
    return st


def ctl(cam, st):
    words = cam.get(st['ctl'], 12)
    return {k: words[off // 4] for k, off in C.items()}


def rate(cam, st, seconds=0.5):
    """Handler calls per second, and whether the OS clock kept running."""
    c0, t0 = cam.get(st['ctl'] + C['calls'])[0], cam.get(CURTIME)[0]
    cam.wait(seconds)
    c1, t1 = cam.get(st['ctl'] + C['calls'])[0], cam.get(CURTIME)[0]
    return (c1 - c0) & 0xFFFFFFFF, (t1 - t0) & 0xFFFFFFFF


# ----------------------------------------------------------------- check
def cmd_check(cam, a):
    """Read-only.  Everything the static notes inferred, as the camera has it."""
    out = {}
    out['is_recording'] = recording(cam)
    out['tick_handler'] = cam.get(TMR_HANDLERS)[0]
    out['handlers'] = cam.get(TMR_HANDLERS, 8)
    out['hash'] = cam.get(TMR_HASH)[0]
    regs = cam.get(TMR_REGS_P)[0]
    out['timer_regs'] = regs
    out['running'] = [cam.get(regs + ch * 16 + 8)[0] for ch in range(8)] if regs else None
    out['ctrl'] = [cam.get(regs + ch * 16)[0] for ch in range(8)] if regs else None
    out['irq4'] = (cam.get(LOWTAB + 16)[0], cam.get(HLTAB + 16)[0])
    out['ctxtsk'], out['schedtsk'] = cam.get(CTXTSK)[0], cam.get(SCHEDTSK)[0]
    t0 = cam.get(CURTIME)[0]
    cam.wait(1.0)
    out['ms_per_s'] = (cam.get(CURTIME)[0] - t0) & 0xFFFFFFFF
    out['irq_frame'] = cam.get(IRQ_FRAME_PC - 12, 4)   # r3, spsr, ip, pc of the LAST irq
    for k, v in out.items():
        print(f'  {k:14s} {[hex(x) for x in v] if isinstance(v, (list, tuple)) else (hex(v) if isinstance(v, int) else v)}')
    ok = (out['tick_handler'] == TICK and out['irq4'] == (0xC0000E64, 0xC0016000))
    print('  expectations:', 'tick + IRQ4 as in the notes' if ok else '!! DIFFERENT FROM THE NOTES -- do not install')
    if out['running']:
        free = [ch for ch in FREE_CHANNELS
                if not out['running'][ch] and not out['handlers'][ch] and not (out['hash'] >> ch) & 1]
        print('  free channels:', free)
    print('  The IRQ frame words are whatever the last IRQ left: [0xC42F1FB4] should look like a\n'
          '  task CPSR (mode 0x13/0x1F/0x10) and [0xC42F1FBC] like a code address.')
    return out


# --------------------------------------------------------------- install
def cmd_install(cam, a):
    guard(cam)
    if load_state(cam):
        raise SystemExit('already installed this boot; uninstall first')
    if cam.get(TMR_HANDLERS)[0] != TICK or cam.get(TMR_PEND_P)[0] == 0:
        raise SystemExit('timer table is not as the notes say; run check')
    records = a.records
    if records & (records - 1):
        raise SystemExit('--records must be a power of two')
    size = records * 16
    if a.via == 'B':
        regs = cam.get(TMR_REGS_P)[0]
        if a.ch not in FREE_CHANNELS:
            raise SystemExit(f'channel {a.ch} is not one of {FREE_CHANNELS}')
        busy = (cam.get(regs + a.ch * 16 + 8)[0], cam.get(TMR_HANDLERS + a.ch * 4)[0],
                (cam.get(TMR_HASH)[0] >> a.ch) & 1)
        if any(busy):
            raise SystemExit(f'channel {a.ch} is in use: running/handler/hash = {busy}')

    code, entry = build()
    at = cam.claim('pcsample.code', len(code))
    desc = cam.claim('pcsample.desc', 16)
    st = {'boot': cam.boot_id(), 'via': a.via, 'ch': a.ch if a.via == 'B' else 0,
          'code': at, 'ctl': at, 'entry': at + entry, 'desc': desc,
          'records': records, 'ring': 0, 'period': a.period, 'stage': 'claimed'}

    # ring: firmware allocator, class 0 (not 10, which recording uses)
    for w in range(4):
        cam.set(desc + 4 * w, 0)
    cam.call(ALLOC_REQ, desc, 0, size, 0)
    ok, ring = cam.call(ALLOC_GET, desc)
    if not ok or not ring:
        raise SystemExit(f'allocator refused {size} bytes')
    st['ring'] = ring
    STATE.write_text(json.dumps(st, indent=1))
    if not 0x44000000 <= ring < 0x80000000:
        cam.call(ALLOC_FREE, desc, 2)
        raise SystemExit(f'ring at 0x{ring:08X} is not readable over MEM1')

    blob = bytearray(code)
    for k, v in (('ring', ring), ('mask', records - 1), ('limit', 0),
                 ('orig', TICK if a.via == 'A' else 0), ('en', 0), ('frame', IRQ_FRAME_PC)):
        struct.pack_into('<I', blob, C[k], v)
    cam.put(at, bytes(blob), 'pcsample')
    cam.call(DCACHE_ALL)
    cam.call(ICACHE_ALL)
    if cam.get(at, len(blob) // 4) != list(struct.unpack(f'<{len(blob)//4}I', blob)):
        raise SystemExit('code did not read back')

    st['stage'] = 'arming'               # from here an interrupted install still uninstalls
    STATE.write_text(json.dumps(st, indent=1))
    if a.via == 'A':
        cam.set(TMR_HANDLERS, st['entry'])
    else:
        info = cam.claim('pcsample.tinfo', 16)
        cam.put(info, struct.pack('<IIII', a.period, st['entry'], 0x37, 0), 'tinfo')
        ok, ret = cam.call(TIMER_START, a.ch, info)
        if not ok or ret != 0:
            raise SystemExit(f'C0016210 returned {ret} (3 = channel busy); nothing armed')
        if cam.get(TMR_HANDLERS + a.ch * 4)[0] != st['entry']:
            cam.call(TIMER_STOP, a.ch)
            raise SystemExit('channel registered with another handler?; stopped')
    st['stage'] = 'armed'
    STATE.write_text(json.dumps(st, indent=1))

    calls, ms = rate(cam, st)
    print(f'  installed via {a.via}: {calls} calls and {ms} ms of OS time in 0.5 s')
    want = 500 if a.via == 'A' else 500 * 12000 / a.period
    if ms < 250 or not 0.5 * want <= calls <= 1.5 * want:
        print('  !! rate is wrong: removing it again')
        cmd_uninstall(cam, a)
        raise SystemExit(1)


# ------------------------------------------------------------ start/stop
def cmd_start(cam, a):
    guard(cam)
    st = load_state(cam) or sys.exit('not installed')
    base = st['ctl']
    cam.set(base + C['en'], 0)
    for k in ('idx', 'over', 'seen'):
        cam.set(base + C[k], 0)
    per_ms = 1.0 if st['via'] == 'A' else 12000 / st['period']
    cam.set(base + C['skip'], int(a.skip * per_ms))
    limit = 0xFFFFFFFF if a.wrap else (a.limit or st['records'])
    cam.set(base + C['limit'], min(limit, 0xFFFFFFFF))
    cam.set(base + C['en'], 1)
    print(f'  sampling: skip {a.skip} ms, limit {"wrap" if a.wrap else limit} records')


def cmd_stop(cam, a):
    guard(cam)
    st = load_state(cam) or sys.exit('not installed')
    cam.set(st['ctl'] + C['en'], 0)
    print('  stopped', ctl(cam, st))


def cmd_status(cam, a):
    st = load_state(cam)
    if not st:
        print('  not installed')
        return
    c = ctl(cam, st)
    print(f'  via {st["via"]} ch {st["ch"]} ring 0x{st["ring"]:08X} x{st["records"]}')
    print('  ' + '  '.join(f'{k}={v:#x}' for k, v in c.items()))


def cmd_read(cam, a):
    guard(cam)
    st = load_state(cam) or sys.exit('not installed')
    c0 = ctl(cam, st)
    raw = cam.read(st['ring'], st['records'] * 16)
    c1 = ctl(cam, st)
    if c1['idx'] != c0['idx'] and c1['en']:
        print('  !! still sampling while reading: records near the index may be torn; stop first')
    CAPS.mkdir(exist_ok=True)
    stem = CAPS / a.label
    if stem.with_suffix('.ring').exists():
        raise SystemExit(f'{stem}.ring exists')
    stem.with_suffix('.ring').write_bytes(raw)
    meta = {'label': a.label, 'time': time.time(), 'via': st['via'], 'ch': st['ch'],
            'period': st['period'], 'records': st['records'], 'ctl': c0, 'ctl_after': c1,
            'note': a.note}
    stem.with_suffix('.json').write_text(json.dumps(meta, indent=1))
    print(f'  {min(c0["idx"], st["records"])} records -> {stem}.ring')


def cmd_names(cam, a):
    """tid -> name from the stock task monitor (its own allocation, released after)."""
    guard(cam)
    cam.sh('analyzer tskmon_start 32768 64 1000000 52')
    cam.wait(1.0)
    top = cam.sh('analyzer tskmon_top 0 200')
    cam.sh('analyzer tskmon_stop')
    import re
    rows = re.findall(r'^\s*(\d+)\s+\d+\s+[\d.]+\[%\]\s+\w+\s+\(\s*\d+\)\s+\d+ Byte (\S+)', top, re.M)
    (HERE / 'tasks.tsv').write_text('# tid\tname (from analyzer tskmon_top)\n' +
                                    ''.join(f'{int(t)}\t{n}\n' for t, n in rows))
    print(f'  {len(rows)} tasks -> tasks.tsv')


def cmd_uninstall(cam, a):
    guard(cam)
    st = load_state(cam)
    if not st:
        print('  not installed')
        return
    if st.get('stage') in ('arming', 'armed'):
        cam.set(st['ctl'] + C['en'], 0)
        if st['via'] == 'B' and cam.get(TMR_HANDLERS + st['ch'] * 4)[0] != st['entry']:
            pass                         # install stopped before the channel was started
        elif st['via'] == 'A':
            cur = cam.get(TMR_HANDLERS)[0]
            if cur not in (st['entry'], TICK):
                raise SystemExit(f'channel-0 handler is 0x{cur:08X}: someone else changed it; not touching')
            cam.set(TMR_HANDLERS, TICK)
        else:
            ok, ret = cam.call(TIMER_STOP, st['ch'])
            if not ok or ret != 0 or cam.get(TMR_HANDLERS + st['ch'] * 4)[0] != 0:
                raise SystemExit(f'C00163F8 returned {ret}; ring NOT freed, state kept')
        calls, ms = rate(cam, st, 0.3)
        if calls:
            raise SystemExit(f'handler still called {calls} times after removal; ring NOT freed')
        if ms < 150:
            print(f'  !! OS clock moved only {ms} ms in 0.3 s')
    if st.get('ring'):
        cam.call(ALLOC_FREE, st['desc'], 2)
    STATE.unlink()
    print('  removed')


def main(argv=None, cam=None):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)
    sub.add_parser('check')
    p = sub.add_parser('install')
    p.add_argument('--via', choices='AB', default='B')
    p.add_argument('--ch', type=int, default=3)
    p.add_argument('--period', type=int, default=12037, help='timer counts at 12 MHz (B)')
    p.add_argument('--records', type=int, default=16384)
    p = sub.add_parser('start')
    p.add_argument('--skip', type=float, default=0, help='ms to wait before recording')
    p.add_argument('--limit', type=int, default=0)
    p.add_argument('--wrap', action='store_true')
    sub.add_parser('stop'); sub.add_parser('status'); sub.add_parser('uninstall')
    sub.add_parser('names')
    p = sub.add_parser('read')
    p.add_argument('label')
    p.add_argument('--note', default='')
    a = ap.parse_args(argv)
    cam = cam or Camera()
    return globals()['cmd_' + a.cmd](cam, a)


if __name__ == '__main__':
    main()
