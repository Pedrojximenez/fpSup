#!/usr/bin/env python3
"""Generate the USB shell AutoRun.

The camera keeps its stock PTP gadget — firmware-built descriptors, firmware-
created endpoints, firmware-rebuilt after a record-mode reconfig.  We change two
words so nothing competes for the bulk pipes, load a worker, and start it.

  build_shell_autorun.py            -> dist/AutoRun.shell.txt
  build_shell_autorun.py --diag     -> dist/AutoRun.shell-diag.txt  (adds a
                                       45 s window and post-attach card dumps)
"""
import sys, pathlib, subprocess, tempfile, hashlib
sys.path.insert(0, '/Users/dido/Developer.localized/SIGMAfp_re/codex')
from build_stage5_autorun import extract_and_relocate, words

HERE  = pathlib.Path('/Users/dido/Developer.localized/SIGMAfp_re/codex/fpshell_tool')
SRC   = HERE / 'camera/usbshell_worker.S'
DIAG  = '--diag' in sys.argv
DEST  = HERE / ('dist/AutoRun.shell-diag.txt' if DIAG else 'dist/AutoRun.shell.txt')

LOAD  = 0xC072E000      # worker code
STATE = 0xC072F000      # worker state, 16 words
CAPOF = 0xC072F040      # shell-output capture offset
HOOK  = 0xC00D0794      # gyro callback site, used once to create the task

NOP = 0xE320F000
PATCHES = [
    # FUN_c0031a40 @0xC0031ADC: `beq -> 0xC04DBC10` for gadget mode 5.  That
    # handler answers only the PTP class control requests 0x64/0x66/0x67 and
    # never touches a bulk endpoint, so dropping it frees the pipes without
    # affecting enumeration (the host issues no class request while enumerating).
    (0xC0031ADC, NOP,
     "mode 5 class handler -> NULL (frees the bulk pipes)"),
    # PTP interface template @0xC0CF3740, bytes {bNumEndpoints, class, sub, proto}
    # 03/06/01/01 -> 03/ff/ff/ff.  Keeps every length and the endpoint set intact;
    # only stops the host's PTP stack from binding interface 0 before we can.
    (0xC0CF3740, 0xFFFFFF03,
     "interface class 06/01/01 -> ff/ff/ff (host PTP stack keeps its hands off)"),
]

DUMPS = [
    ("PATCH", 0xC0031AD0, 0x20),   # +0x0C must read E320F000
    ("IFACE", 0xC0CF373C, 0x10),   # the patched interface template
    ("PDESC", 0xC3774820, 0x140),  # PTP staging: the descriptor set actually built
    ("REG",   0xC30792B0, 0x20),   # +0x14 = the desc set the firmware registered
    ("EPTBL", 0xC31E3260, 0x40),   # endpoint TRB-pointer table
    ("USBST", 0xC31E3740, 0x20),   # USB_STATE
    ("DALEP", 0x2100C700, 0x40),   # DWC3 DCFG / DCTL / DSTS / DALEPENA
    ("VSHL",  0xC072F000, 0x40),   # worker state
]

# --- assemble ---------------------------------------------------------------
with tempfile.TemporaryDirectory() as d:
    obj = pathlib.Path(d) / 'w.o'
    r = subprocess.run(['clang', '-target', 'armv7-none-eabi', '-c', str(SRC), '-o', str(obj)],
                       capture_output=True, text=True)
    if r.returncode:
        sys.stderr.write(r.stderr); sys.exit(1)
    code = extract_and_relocate(obj)
w   = words(code)
end = LOAD + len(code)
assert end <= STATE, f"worker overruns STATE: 0x{end:08X}"

disp = (LOAD - (HOOK + 8)) >> 2
assert -(1 << 23) <= disp < (1 << 23)
hook_bl = 0xEB000000 | (disp & 0xFFFFFF)

# --- emit -------------------------------------------------------------------
o = []
A = o.append
A("# ============================================================================")
A("# USB shell — the camera's own PTP gadget, repurposed.")
A("#")
A("# The gadget itself is stock: the firmware builds the descriptors, creates and")
A("# enables EP 0x01 OUT / 0x82 IN, and rebuilds them after a record-mode")
A("# reconfig.  That is the whole point — the previous shell bolted on endpoints")
A("# the firmware did not know about, which is why recording tore it down.")
A("#")
A("# Two words are changed; everything else is worker code.")
A("#")
A("#   command set: `shl <line>` only.  The firmware shell's own commands,")
A("#   `mem set` and `mem save` included, are reachable through it.")
A("#")
A("# Boot with the USB cable UNPLUGGED, then attach: the gadget is built on")
A("# attach, so the patches must land first, and the patched words sit in code")
A("# that has not run yet, so no stale I-cache line can shadow them.")
A("#")
A("# Recovery: delete the two `mem set` lines under PATCHES and reboot.")
A("# ============================================================================")
A("")
A("# One pulse: AutoRun is running.")
A("display monitor 0 1")
A("display colorbar 1 0")
A("ctrl sleep 400")
A("display colorbar 0 0")
A("")
A("# --- PATCHES ----------------------------------------------------------------")
for a, v, why in PATCHES:
    A(f"# {why}")
    A(f"mem set 0x{a:08X} 0x{v:08X}")
A("")
A(f"# --- worker state @0x{STATE:08X} (16 words) + capture offset ----------------")
for i in range(16):
    A(f"mem set 0x{STATE + i*4:08X} 0x00000000")
A(f"mem set 0x{CAPOF:08X} 0x00000000")
A("")
A(f"# --- worker code @0x{LOAD:08X}..0x{end:08X} ({len(code)} bytes) --------------")
for i, x in enumerate(w):
    A(f"mem set 0x{LOAD + i*4:08X} 0x{x:08X}")
A("")
A("# --- shared 4 KiB DMA frame buffer (address lands in 0xC3757A7C) -------------")
A("memmgr bufmem get 0 0x1000 0x40")
A("")
A("# --- start the worker -------------------------------------------------------")
A("# One-shot branch from the gyro callback: cave_entry calls the displaced")
A("# accessor, creates the task, and restores this word.")
A(f"mem set 0x{HOOK:08X} 0x{hook_bl:08X}")
A("")
A("# Two pulses: worker armed. A colorbar that never clears means the load failed.")
for _ in range(2):
    A("display colorbar 1 0")
    A("ctrl sleep 400")
    A("display colorbar 0 0")
    A("ctrl sleep 300")

if DIAG:
    A("")
    A("# ======================== DIAGNOSTIC BUILD ==================================")
    A("# Attach the USB cable NOW. 45 s from the two pulses above.")
    A("ctrl sleep 45000")
    A("")
    for name, addr, n in DUMPS:
        A(f"mem save \\{name}.BIN 0x{addr:08X},,0x{n:X}")
    A("")
    A("# Three short pulses: dumps written. Power off and read the card.")
    for _ in range(3):
        A("display colorbar 1 0")
        A("ctrl sleep 250")
        A("display colorbar 0 0")
        A("ctrl sleep 250")

text = '\n'.join(o) + '\n'
DEST.write_text(text)
print(f"worker  : {len(code)} B, {len(w)} words, 0x{LOAD:08X}..0x{end:08X}")
print(f"hook    : 0x{HOOK:08X} = 0x{hook_bl:08X} -> 0x{LOAD:08X}")
for a, v, why in PATCHES:
    print(f"patch   : 0x{a:08X} = 0x{v:08X}  {why}")
print(f"WROTE   : {DEST.name}  ({len(o)} lines, sha={hashlib.sha256(text.encode()).hexdigest()[:16]})")
for bad in ("0xC04DC618", "0xC31E38C8", "0xC01E62A9", "0x2100C720", "0xC0031C54", "echo"):
    assert bad not in text, f"legacy artefact leaked: {bad}"
print("clean   : no descriptor hook / ctx4 / EP enable / DALEPENA / builder swap / echo")
