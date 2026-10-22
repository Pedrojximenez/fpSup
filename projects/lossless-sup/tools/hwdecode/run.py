#!/usr/bin/env python3
"""Decode one recorded fpLossless frame with the camera's hardware decoder.

    python3 run.py /Volumes/fpSup/CINEMA/A001_267/A001_267_20261001_000001.DNG

Standby only: never in playback, never while recording. Reads the DNG's tile
layout on the Mac, loads probe.c into the cave, calls it once through the
shell (callfn), saves the decoded raster to the card with `mem save`, fetches
it, frees the camera buffer, and compares it with rawpy's decode of the same
file. The camera's file is opened by name; no clip folder is listed.
"""
import pathlib, struct, subprocess, sys, time

HERE = pathlib.Path(__file__).resolve().parent
SHELL = HERE.parents[3] / 'fpSup' / 'fp_usb_shell'
sys.path.insert(0, str(SHELL))
import cave, callfn                                        # noqa: E402
from putfile import sh, mem_set, mem_get, put             # noqa: E402

FIELDS = ['mode'] + [f'path{i}' for i in range(16)] + [
    'file_bytes', 'stream_off', 'out_bytes', 'w', 'h', 'fmt', 'tw', 'th',
    'stage', 'obj0', 'obj1', 'obj2', 'obj3', 'base', 'file', 'out', 'actual', 'open_ok',
    'read_ok', 'init_ret', 'dec_ret', 't_read0', 't_dec0', 't_dec1',
    'e0', 'e1', 'e2', 'e3', 'flag', 'open_r', 'submit_r', 'start_r', 'pattern', 'close_r', 'tiles', 'patch_n', 'patch_val'] + [f'patch_at{i}' for i in range(16)] + ['sub_off', 'sub_len', 'sub']
OFF = {n: 4 * i for i, n in enumerate(FIELDS)}
FMT = {12: 0, 14: 1, 16: 2, 10: 3}
MODE = int(__import__('os').environ.get('HWD_MODE', '2'))   # 0: C05A69E0; 2: its steps; 3: last tile row alone


def layout(path):
    b = open(path, 'rb').read()
    root = struct.unpack_from('<I', b, 4)[0]
    n = struct.unpack_from('<H', b, root)[0]
    tags = {}
    for i in range(n):
        t, ty, c, v = struct.unpack_from('<HHII', b, root + 2 + 12 * i)
        tags[t] = (ty, c, v)

    def arr(t):
        ty, c, v = tags[t]
        return [v] if c == 1 else list(struct.unpack_from(f'<{c}{"I" if ty == 4 else "H"}', b, v))
    assert tags[259][2] & 0xFFFF == 7, 'not a compressed frame'
    offs, lens = arr(324), arr(325)
    assert all(offs[i] + lens[i] == offs[i + 1] for i in range(len(offs) - 1)), 'tiles not contiguous'
    bits = tags[258][2] & 0xFFFF
    across = -(-tags[256][2] // tags[322][2])
    sof = []
    for o in offs[-across:]:
        i = b.index(b'\xff\xc3', o, o + 256)
        sof.append(i + 5)                       # FFC3, length(2), precision(1) -> lines
    return dict(sof=sof, last_off=offs[-across], size=len(b), w=tags[256][2], h=tags[257][2], bits=bits,
                tw=tags[322][2], th=tags[323][2], off=offs[0], stream=offs[-1] + lens[-1] - offs[0])


def compile_probe():
    """(text, entry offset): one strict .text, no relocations (elf_text checks)."""
    sys.path.insert(0, str(HERE.parents[1] / 'probes' / 'fplossless_native_port'))
    import elf_text
    obj = HERE / 'probe.o'
    subprocess.run(['clang', '--target=armv7a-none-eabi', '-mcpu=cortex-a9', '-mthumb',
                    '-mfloat-abi=soft', '-mfpu=none', '-ffreestanding', '-fno-builtin', '-nostdlib',
                    '-fno-jump-tables', '-fropi', '-fno-addrsig', '-fno-unwind-tables',
                    '-fno-asynchronous-unwind-tables', '-O2', '-std=c11', '-Wall', '-Wextra',
                    '-Werror', '-c', str(HERE / 'probe.c'), '-o', str(obj)], check=True)
    text = elf_text.load_text(obj)
    return bytes(text.code), text.functions['hwd_entry']


def main():
    local = pathlib.Path(sys.argv[1])
    L = layout(local)
    camera_path = '\\' + '\\'.join(local.parts[-3:])          # \CINEMA\A001_x\file.DNG
    # Rows as the recorder lays the raster out (C0135D40: 4-byte rows).
    # The last tile row's SOF3 says a full tile, but only the frame's rows were
    # encoded: in memory, its line count is set to what is there.
    pitch = (L['w'] * L['bits'] // 8 + 3) & ~3
    padded = -(-L['h'] // L['th']) * L['th']
    last = L['h'] - (padded - L['th'])
    # The engine writes whole tiles: the buffer always holds the padded height
    # (2026-10-01: a 2010-row buffer was overrun by the last tile row).
    rows = L['th'] if MODE == 3 else padded
    told = rows if MODE == 3 or __import__('os').environ.get('HWD_H') == 'pad' else L['h']
    out_bytes = pitch * rows
    print(f'{local.name}: {L["w"]}x{L["h"]} {L["bits"]}-bit, tiles {L["tw"]}x{L["th"]}, '
          f'stream {L["stream"]:,} B at 0x{L["off"]:X}; file {L["size"]:,} B; out {out_bytes:,} B')
    assert L['off'] % 1024 == 0
    st = sh('status get is_recording')
    assert 'is_recording -> 0' in st, st

    code, entry = compile_probe()
    # fixed sizes: a claim of a new size is a new claim, and the arena only
    # comes back at a reboot
    assert len(code) <= 0x400 and len(FIELDS) * 4 <= 0x200
    code_at = cave.claim('hwdecode.code2', 0x400)
    fn = code_at + (entry & ~1)
    block = cave.claim('hwdecode.block2', 0x200)
    put(code_at, code + b'\0' * (-len(code) % 4), 'hwdecode probe')
    words = [0] * len(FIELDS)
    words[0] = MODE
    pb = camera_path.encode() + b'\0'
    assert len(pb) <= 64
    pb += b'\0' * (64 - len(pb))
    words[1:17] = struct.unpack('<16I', pb)
    vals = dict(file_bytes=L['size'], stream_off=L['off'], out_bytes=out_bytes, w=L['w'],
                h=told, fmt=FMT[L['bits']], tw=L['tw'], th=L['th'],
                tiles=-(-L['w'] // L['tw']) * -(-rows // L['th']),
                patch_n=0, patch_val=last)
    if MODE == 3:
        vals.update(sub_off=L['last_off'], sub_len=L['stream'] + L['off'] - L['last_off'])
    for i, at in enumerate(L['sof']):
        vals[f'patch_at{i}'] = at
    for k, v in vals.items():
        words[FIELDS.index(k)] = v
    for i, v in enumerate(words):
        mem_set(block + 4 * i, v)

    ok, ret = callfn.call(fn | 1, r0=block)
    r = dict(zip(FIELDS, mem_get(block, len(FIELDS))))
    print({k: (hex(r[k]) if k in ('base', 'file', 'out') else r[k]) for k in FIELDS[17:]})
    if not ok or r['stage'] != 8:
        print('decode did not succeed; freeing'); r['stage'] < 3 or free(block, fn)
        return 1
    print(f'decode done in {(r["t_dec1"] - r["t_dec0"]) / 1000:.1f} ms '
          f'(file read {(r["t_dec0"] - r["t_read0"]) / 1000:.1f} ms before it)')
    save = f'\\HWD{int(time.time()) % 100000:05d}.BIN'    # mem save does not overwrite
    print(sh(f'mem save {save} 0x{r["out"]:08X},0x{r["out"] + out_bytes:08X},'))
    free(block, fn)
    dst = HERE / 'hwdec.bin'
    subprocess.run([sys.executable, str(SHELL / 'getfile.py'), save, str(dst), '--size',
                    str(out_bytes)], check=True)
    compare(local, dst.read_bytes(), L, pitch, first_row=(L['h'] - last) if MODE == 3 else 0)
    return 0


def free(block, fn):
    mem_set(block, 1)
    callfn.call(fn | 1, r0=block)


def compare(local, raw, L, pitch, first_row=0):
    import numpy as np, rawpy
    with rawpy.imread(str(local)) as im:
        ref = im.raw_image.astype(np.int32)[first_row:]
    w, h = L['w'], L['h'] - first_row
    a = np.frombuffer(raw[:pitch * h], dtype=np.uint8).reshape(h, pitch)[:, :w * 3 // 2].astype(np.int32)
    b0, b1, b2 = a[:, 0::3], a[:, 1::3], a[:, 2::3]
    for name, (p0, p1) in {'MSB first (DNG)': ((b0 << 4) | (b1 >> 4), ((b1 & 15) << 8) | b2),
                           'LSB first': (b0 | ((b1 & 15) << 8), (b1 >> 4) | (b2 << 4))}.items():
        got = np.empty((h, w), np.int32)
        got[:, 0::2], got[:, 1::2] = p0, p1
        d = got != ref[:h, :w]
        print(f'  {name}: {d.sum():,} of {w * h:,} pixels differ'
              + ('' if not d.any() else f'; first at {tuple(np.argwhere(d)[0])}'))


if __name__ == '__main__':
    sys.exit(main())
