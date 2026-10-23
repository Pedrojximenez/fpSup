#!/usr/bin/env python3
"""Fetch just the headers of a clip's DNGs off the camera, over the shell.

    python3 -B fetch_heads.py A001_027 20261006 OUT_DIR [--max N] [--first K]

Never lists the clip folder (a `dir` of \\CINEMA\\A001_nnn is off limits): the
frame names are A001_nnn_DATE_000001.DNG upward, read until one is missing.
Each file is read as getfile.py --partial reads it, HEAD bytes from the start,
but all in this one process: getfile.S is assembled and uploaded once, and
each file costs only its parameters, one echo and a MEM1 read (getfile.py
per file spent ~0.6 s starting Python and re-uploading its code).
Talks to the camera.
"""
import argparse, pathlib, struct, sys, time

SHELL = pathlib.Path(__file__).resolve().parents[2] / 'fpSup' / 'fp_usb_shell'
sys.path.insert(0, str(SHELL))
HEAD = 0x15400            # the camera's header room: any header with our tag, lossless's too


class Reader:
    def __init__(self):
        import getfile as g
        from armasm import assemble
        from putfile import CODE, CODE_END, P
        self.g, self.P = g, P
        code = assemble(SHELL / 'asm' / 'getfile.S', [f'P=0x{P:08X}'])
        if CODE + len(code) > CODE_END:
            raise SystemExit('assembly source does not fit')
        self.code = CODE
        g.put(CODE, code, 'code  ')
        self.fobj = g.staging_area()
        g.check_fits(self.fobj, 0x400, 'file object')
        # The first read takes a buffer from the firmware's allocator; the
        # rest reuse it, and it goes back once at the end.  Handing it back
        # per file runs callfn, whose code lands where getfile.S sits.
        self.buf = 0

    def read(self, remote, size):
        """The file's first `size` bytes (fewer if it is shorter); None if it is not there."""
        g, P = self.g, self.P
        path = remote.encode() + b'\0'
        for off, val in ((g.P_ACTUAL, 0), (g.P_STATUS, 0), (g.P_OPENR, 0), (g.P_READR, 0),
                         (g.P_BUF, self.buf), (g.P_LEN, HEAD + 0x1000), (g.P_FOBJ, self.fobj), (g.P_MODE, 1)):
            g.mem_set(P + off, val)
        pw = path + b'\0' * (-len(path) % 4)
        for i, w in enumerate(struct.unpack(f'<{len(pw)//4}I', pw)):
            g.mem_set(P + g.P_PATH + i * 4, w)
        owner = g.mem_get(g.ECHO_SLOT)
        if not owner or owner[0] not in (g.ECHO_ORIG, self.code):
            raise SystemExit(f'echo handler is {owner}, not free to borrow')
        try:
            g.set_echo_handler(self.code)
            reply = g.sh('echo')
        finally:
            g.set_echo_handler(g.ECHO_ORIG)
        if reply.lstrip().startswith('ERR'):
            raise RuntimeError('echo reply failed; read outcome unknown')
        if not self.buf:
            self.buf = (g.mem_get(P + g.P_BUF) or [0])[0]
        st = g.mem_get(P, 5)
        if len(st) < 5 or any(w is None for w in st):
            raise RuntimeError('could not verify file read status')
        status = st[g.P_STATUS // 4]
        if status == 3:
            return None                                     # open returned 0: not there
        if status != 2 or not self.buf:
            raise RuntimeError(f'status {status} ({g.STATUS.get(status, "?")})')
        n = min(size, st[g.P_ACTUAL // 4])
        return g.read_direct(self.buf, n)

    def close(self):
        if self.buf:
            from callfn import call
            call(0xC001D7A0, r0=self.P + 0xE0, r1=2, verbose=False)   # free, as getfile.py does
            self.buf = 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('clip')
    ap.add_argument('date')
    ap.add_argument('out', type=pathlib.Path)
    ap.add_argument('--max', type=int, default=2000)
    ap.add_argument('--first', type=int, default=1)
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    rd = Reader()
    n, t0 = 0, time.time()
    try:
        n = fetch(rd, a)
    finally:
        rd.close()
    dt = time.time() - t0
    print(f'{n} headers in {a.out} ({dt:.1f} s, {dt / max(n, 1) * 1000:.0f} ms each)')
    return 0 if n else 1


def fetch(rd, a):
    n = 0
    for k in range(a.first, a.first + a.max):
        name = f'{a.clip}_{a.date}_{k:06d}.DNG'
        remote = f'\\CINEMA\\{a.clip}\\{name}'
        data, err = None, None
        for attempt in range(4):
            try:
                data = rd.read(remote, HEAD)
                err = None
                break
            except (RuntimeError, OSError) as e:                # a shell that missed a command
                err = e
                time.sleep(2 + 3 * attempt)
        if data is None:
            print(f'stopped at {name}: {err or "not there (end of clip)"}')
            break
        (a.out / name).write_bytes(data)
        n += 1
    return n


if __name__ == '__main__':
    sys.exit(main())
