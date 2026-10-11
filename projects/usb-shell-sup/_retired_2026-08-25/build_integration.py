#!/usr/bin/env python3
"""Compose the INTEG AutoRun: v27 reference setup (through `echo`) + autonomous
worker + gyro-hook starter + GO/readback. Reproducibility per Codex review.

Usage: python3 build_integration.py   (writes dist/AutoRun_INTEG1.txt)
"""
import sys, pathlib, subprocess, tempfile, hashlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from build_stage5_autorun import extract_and_relocate, words

HERE = pathlib.Path(__file__).resolve().parent
LOAD = 0xC072E800          # worker code (above all v27 usage <=0xC072E780)
STATE = 0xC072EC00         # worker state; GO = STATE+16
HOOK = 0xC00D0794          # gyro one-shot hook
POST_GO_SLEEP_MS = 45000   # host window after GO (forgiving; ping lands after worker arms)

def build_worker():
    with tempfile.TemporaryDirectory() as d:
        obj = pathlib.Path(d) / 'w.o'
        r = subprocess.run(['clang','-target','armv7-none-eabi','-c',
                            str(HERE/'camera/integration_worker.S'),'-o',str(obj)],
                           capture_output=True, text=True)
        if r.returncode:
            sys.stderr.write(r.stderr); sys.exit(1)
        return extract_and_relocate(obj)

def main():
    code = build_worker()
    assert LOAD + len(code) <= STATE, f"worker overflow {LOAD+len(code):08X}"
    act = 0xEB000000 | (((LOAD - (HOOK+8)) >> 2) & 0xFFFFFF)
    ref = (HERE/'camera/AutoRun_v27_reference.txt').read_text().splitlines()
    splice = next(i for i,l in enumerate(ref) if 'Allocate the shared' in l)
    echo_end = next(i for i,l in enumerate(ref) if l.strip()=='mem save \\DWCINIT.BIN 0x2100C880,,0x40') + 1

    inj = ["","# === Claude integration: load autonomous worker + install A5 gyro-hook starter EARLY",
           "# (before builder/init hooks, per Codex order). worker @0x%08X state @0x%08X GO @0x%08X." % (LOAD,STATE,STATE+16),
           "# Worker is created shortly by the gyro thread and BLOCKS polling GO until after echo."]
    inj += [f"mem set 0x{LOAD+i*4:08X} 0x{w:08X}" for i,w in enumerate(words(code))]
    inj += [f"mem set 0x{STATE+o:08X} 0x00000000" for o in range(0,0x40,4)]
    inj += [f"# activate gyro one-shot starter: 0x{HOOK:08X} -> b 0x{LOAD:08X} (cave self-restores)",
            f"mem set 0x{HOOK:08X} 0x{act:08X}",""]
    tail = ["","# === Claude integration: GO (immediately after echo) + one host round + readback ===",
            "# echo returned => registration done, ctx4 mode2 restored, ctx4/ctx5 init complete.",
            "# Host: fpshelld --arm-wait 40 --limit 1 claimed; send exactly one `fpshell ping` after GO.",
            f"mem set 0x{STATE+16:08X} 0x00000001",
            f"ctrl sleep {POST_GO_SLEEP_MS}",
            f"mem save \\WORKER.BIN 0x{STATE:08X},,0x40"]
    out = '\n'.join(ref[:splice] + inj + ref[splice:echo_end] + tail) + '\n'
    dest = HERE/'dist/AutoRun_INTEG1.txt'
    dest.write_text(out)
    print(f"worker {LOAD:08X}..{LOAD+len(code):08X} ({len(code)}B) act={act:08X}")
    print(f"{dest}: {len(out.splitlines())} lines SHA={hashlib.sha256(out.encode()).hexdigest()[:16]}")

if __name__ == '__main__':
    main()
