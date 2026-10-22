#!/usr/bin/env python3
"""Fetch just the headers of a clip's DNGs off the camera, over the shell.

    python3 -B fetch_heads.py A001_027 20261006 OUT_DIR [--max N]

Never lists the clip folder (a `dir` of \\CINEMA\\A001_nnn is off limits): the
frame names are A001_nnn_DATE_000001.DNG upward, read until one is missing.
Each file is read with getfile.py --partial, HEAD bytes from the start.
Talks to the camera.
"""
import argparse, pathlib, subprocess, sys, time

SHELL = pathlib.Path(__file__).resolve().parents[2] / 'fpSup' / 'fp_usb_shell'
HEAD = 0x14000            # the stock header (0x13400) plus a lossless frame's new IFD


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('clip')
    ap.add_argument('date')
    ap.add_argument('out', type=pathlib.Path)
    ap.add_argument('--max', type=int, default=2000)
    ap.add_argument('--first', type=int, default=1)
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    n = 0
    for k in range(a.first, a.first + a.max):
        name = f'{a.clip}_{a.date}_{k:06d}.DNG'
        remote = f'\\CINEMA\\{a.clip}\\{name}'
        for attempt in range(4):
            r = subprocess.run([sys.executable, '-B', 'getfile.py', remote, str(a.out / name),
                                '--size', hex(HEAD), '--partial'], cwd=SHELL,
                               capture_output=True, text=True)
            text = r.stdout + r.stderr
            if not r.returncode and (a.out / name).exists():
                break
            # "open returned 0" is the file not being there: the end of the
            # clip.  Anything else (a shell that missed a command -- cave.py
            # then reports LOAD_DONE_US as zero) is worth another try.
            if 'open returned 0' in text:
                break
            time.sleep(2 + 3 * attempt)
        if r.returncode or not (a.out / name).exists():
            print(f'stopped at {name}: {text.strip().splitlines()[-1:]}')
            break
        n += 1
    print(f'{n} headers in {a.out}')
    return 0 if n else 1


if __name__ == '__main__':
    sys.exit(main())
