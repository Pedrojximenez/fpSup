#!/usr/bin/env python3
"""Assemble bayer_hook_oneshot.S and emit the AutoRun lines that install it:
  - the trampoline blob as native `mem set` words at TRAMP (cave)
  - the one-instruction patch at the LV ring-advance fn (native mem set, code region)

These lines must be added to the AutoRun (native shell mem set, boot-time, I-cache
coherent). The worker's OWN `mem set` cannot write the code site 0xC040F528 — only the
native AutoRun shell can. Prints the block ready to append.

  python3 build_bayer_hook.py
"""
import sys, pathlib, subprocess, tempfile, struct
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / 'projects/gyro-sup'))
from build_stage5_autorun import extract_and_relocate, words

HERE = pathlib.Path(__file__).resolve().parent
TRAMP  = 0xC072F600      # trampoline load addr (cave; clear of peek@F100, imu@F200-300, CAP@F1F8)
RESULT = 0xC072F800      # capture result block (matches .Lresult in the .S)
SITE   = 0xC040F528      # XC_LiveViewRawMemInterfaceSample::v3 first instr (mov ip,r0)
ORIG   = 0xE1A0C000

def build():
    with tempfile.TemporaryDirectory() as d:
        obj = pathlib.Path(d)/'b.o'
        r = subprocess.run(['clang','-target','armv7-none-eabi','-c',
                            str(HERE/'bayer_hook_oneshot.S'),'-o',str(obj)],
                           capture_output=True, text=True)
        if r.returncode: sys.stderr.write(r.stderr); sys.exit(1)
        code = extract_and_relocate(obj)
    return words(code)

def main():
    w = build()
    end = TRAMP + len(w)*4
    patch = 0xEA000000 | (((TRAMP-(SITE+8))>>2) & 0xFFFFFF)
    assert end <= RESULT, f"trampoline overruns RESULT: 0x{end:08X}"
    # verify .Lresult literal inside the blob equals RESULT (guards address drift)
    assert RESULT in w, f"blob missing RESULT literal 0x{RESULT:08X}"
    print(f"# bayer one-shot hook: trampoline {len(w)}w @0x{TRAMP:08X}..0x{end:08X}, result@0x{RESULT:08X}")
    print(f"# install via NATIVE AutoRun mem set (boot-time, I-cache coherent)")
    for i, x in enumerate(w):
        print(f"mem set 0x{TRAMP+i*4:08X} 0x{x:08X}")
    print(f"# patch LV ring-advance 0x{SITE:08X}: mov ip,r0 (0x{ORIG:08X}) -> B 0x{TRAMP:08X}")
    print(f"mem set 0x{SITE:08X} 0x{patch:08X}")
    print(f"# --- after boot + liveview: read result, check magic 0x30525942 ---")
    print(f"#   mem read 0x{RESULT:08X} 24   -> this,idx,bayer,focus0,focus1,magic")
    print(f"#   then RAWGRAB the bayer slot (0x50000000+idx<<20, 1MB) and decode")

if __name__ == '__main__':
    main()
