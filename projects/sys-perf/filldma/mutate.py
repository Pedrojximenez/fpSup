"""Mutation check: each mutant of filldma.S must make test_filldma fail.

Mutants are written to a temporary directory (the working source is never
edited); the test reads them through FILLDMA_SRC.  The unmodified source must
pass.   python3 -B mutate.py
"""
import os, pathlib, subprocess, sys, tempfile

HERE = pathlib.Path(__file__).resolve().parent
SRC = (HERE / 'filldma.S').read_text()

MUTANTS = [
    ('no invalidate before DMA', 'mov     r0, r7                          @ drop every line, dirty or not: the DMA\n        bl      fd_inval',
     'mov r0, r7\n nop'),
    ('no invalidate after DMA', 'mov     r0, r7                          @ lines speculatively refilled during the\n        bl      fd_inval',
     'mov r0, r7\n nop'),
    ('no invalidate before CPU completion', 'beq     9f\n        mov     r0, r7\n        bl      fd_inval',
     'beq 9f\n mov r0, r7\n nop'),
    ('no threshold', 'cmp     r6, r0\n        blo     fd_decline', 'cmp r6, r0\n nop'),
    ('no init check', 'cmp     r0, #1\n        bne     fd_decline\n\n        mov     r9, #6', 'cmp r0, #1\n nop\n mov r9, #6'),
    ('no alignment check', 'tst     r0, #0x3F\n        bne     fd_decline', 'tst r0, #0x3F\n nop'),
    ('no format check', 'ldr     r0, [r4, #0x1C]\n        cmp     r0, #1\n        bne     fd_decline', 'nop'),
    ('no validity check', 'ldr     ip, [ip, #0x30]\n        blx     ip\n        cmp     r0, #0\n        beq     fd_decline',
     'ldr ip, [ip, #0x30]\n blx ip\n cmp r0, #0\n nop'),
    ('no recording check', 'cmp     r0, #0\n        bne     fd_decline\n4:', 'cmp r0, #0\n nop\n4:'),
    ('recording flag ignored', 'ldr     r0, fd_rec_ok', 'mov r0, #0'),
    ('pattern not doubled', 'orr     r5, r5, r5, lsl #16', 'nop'),
    ('cached offset wrong', 'sub     r3, r7, #0xC0000000', 'sub r3, r7, #0x80000000'),
    ('no stack realign', 'bic     sp, sp, #7', 'nop'),
    ('success reported as decline', 'str     r6, [r10, #0x30]\n        mov     r0, #0', 'str r6, [r10, #0x30]\n mov r0, #9'),
    ('remainder skipped', 'ubfx    r2, r0, #0, #13                 @ remaining words\n        cmp     r2, #0\n        beq     7f',
     'ubfx r2, r0, #0, #13\n cmp r2, #0\n b 7f'),
    ('first-chunk error ignored', 'mov     r2, #ROWW\n        bl      fd_dma\n        cmp     r0, #0\n        bne     fd_dma_failed',
     'mov r2, #ROWW\n bl fd_dma\n cmp r0, #0\n nop'),
    ('invalidate chunk unbounded', '.equ    CHUNK,          0x10000', '.equ CHUNK, 0x1000000'),
    ('uncached treated as cached', 'mov     r8, #0                          @ r8 = 1 if cached', 'mov r8, #1'),
    ('rows/width swapped', 'str     r2, [r4, #0x14]                 @ width (words)\n        str     r1, [r4, #0x18]',
     'str r1, [r4, #0x14]\n str r2, [r4, #0x18]'),
    ('uncached upper bound dropped', 'sub     r3, r7, #0x40000000\n        add     r0, r3, r6\n        cmp     r0, #0x40000000\n        bhi     fd_decline',
     'sub r3, r7, #0x40000000\n nop'),
    ('enable flag ignored', 'ldr     r0, [r10, #0x08]\n        cmp     r0, #0\n        beq     fd_decline', 'nop'),
    ('CPU completion one word short', 'add     r1, r7, r6\n        mov     r2, r5', 'add r1, r7, r6\n sub r1, r1, #8\n mov r2, r5'),
]


def run(src_path):
    env = dict(os.environ, FILLDMA_SRC=str(src_path))
    r = subprocess.run([sys.executable, '-B', '-m', 'unittest', 'test_filldma'], cwd=HERE,
                       env=env, capture_output=True, text=True)
    return r.returncode == 0, r.stderr.strip().splitlines()[-1] if r.stderr else ''


def main():
    ok, last = run(HERE / 'filldma.S')
    print('unmodified:', 'PASS' if ok else 'FAIL ' + last)
    if not ok:
        sys.exit(1)
    survivors = []
    with tempfile.TemporaryDirectory() as tmp:
        for name, old, new in MUTANTS:
            if SRC.count(old) != 1:
                print(f'  !! pattern for "{name}" found {SRC.count(old)} times')
                survivors.append(name)
                continue
            p = pathlib.Path(tmp) / f'm{MUTANTS.index((name, old, new))}.S'
            p.write_text(SRC.replace(old, new))
            passed, last = run(p)
            print(f'  {"SURVIVED" if passed else "caught  "}  {name}  ({last})')
            if passed:
                survivors.append(name)
    print(f'{len(MUTANTS) - len(survivors)}/{len(MUTANTS)} caught')
    sys.exit(1 if survivors else 0)


if __name__ == '__main__':
    main()
