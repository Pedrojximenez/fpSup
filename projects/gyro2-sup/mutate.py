#!/usr/bin/env python3
"""Prove the tests can fail: one change at a time to a COPY of src/gyr2.S (P1),
each of which some test must catch.  The working source is never edited.

    python3 -B mutate.py
"""
import os, pathlib, subprocess, sys, tempfile

HERE = pathlib.Path(__file__).resolve().parent
SRC = HERE / 'src' / 'gyr2.S'

MUTANTS = [
    ('a sync hook does not replay its movt', '    movt    \\reg, #0xC31D              @ the displaced instruction', '    nop'),
    ('the thumb blx gets J1 wrong', '    eor     r4, r4, ip\n    eor     r4, r4, #1', '    eor     r4, r4, ip'),
    ('sync events do not stop at the block end', "    bpl     9f                          @ at or after the end: the next block's", '    nop'),
    ('sync events are not counted', '    bl      put_vd\n    ldrh    r2, [r11, #58]\n    add     r2, r2, r0', '    bl      put_vd\n    ldrh    r2, [r11, #58]\n    nop'),
    ('a sync hook records with no stream', '    tst     r1, #F_LOST                 @ no place in the stream: nothing to say', '    tst     r1, #0'),
    ('a refused vd claim is ignored', '    ADRF    r3, vd_stock\n    ldr     ip, [r5, #SVC_CLAIM]\n    blx     ip\n    add     sp, sp, #8\n    cmp     r0, #0\n    bne     9f', '    ADRF    r3, vd_stock\n    ldr     ip, [r5, #SVC_CLAIM]\n    blx     ip\n    add     sp, sp, #8\n    cmp     r0, #0\n    nop'),
    ('a sync hook stores no time', '    str     r0, [ip, #4]\n    dmb', '    nop\n    dmb'),
    ('does not forward to the layer below',
     'bx      ip                          @ the layer below, with r0 and lr as given', 'bx      lr'),
    ('never writes the commit magic',
     'ldr     r0, =MAGIC                  @ the commit, last\n    str     r0, [r11]',
     'ldr     r0, =MAGIC                  @ the commit, last\n    nop'),
    ('ignores a break in the tag counter', '    movne   r8, #1', '    movne   r8, #0'),
    ('writes over a place that is not empty',
     'region_ok:\n    ldr     r0, =MAGIC', 'region_ok:\n    mov     r0, #1\n    bx      lr\n    ldr     r0, =MAGIC'),
    ('ignores a refused claim of the header site',
     '    adr     r3, site_stock\n    ldr     ip, [r5, #SVC_CLAIM]\n    blx     ip\n    add     sp, sp, #8\n    cmp     r0, #0\n    bne     9f',
     '    adr     r3, site_stock\n    ldr     ip, [r5, #SVC_CLAIM]\n    blx     ip\n    add     sp, sp, #8\n    cmp     r0, #0\n    nop'),
    ('ignores a refused claim of the accel site',
     '    adr     r3, accel_stock\n    ldr     ip, [r5, #SVC_CLAIM]\n    blx     ip\n    add     sp, sp, #8\n    cmp     r0, #0\n    bne     9f',
     '    adr     r3, accel_stock\n    ldr     ip, [r5, #SVC_CLAIM]\n    blx     ip\n    add     sp, sp, #8\n    cmp     r0, #0\n    nop'),
    ('chains to the stock DMA instead of chain_next',
     '    str     r0, [r6, #V_NEXT]', '    ldr     r0, =0xC00FBB91\n    str     r0, [r6, #V_NEXT]'),
    ('clobbers r11',
     'push    {r0, r4, r5, r6, r7, r8, r9, r10, r11, lr}\n    sub     sp, sp, #SNAP_BYTES',
     'push    {r0, r4, r5, r6, r7, r8, r9, r10, lr}\n    sub     sp, sp, #SNAP_BYTES'),
    ('no gap after the vendor data', '.equ GAP,          64', '.equ GAP,          0'),
    ('no backfill at a take start', '.equ BACKFILL,     250', '.equ BACKFILL,     0'),
    ('copies the pad instead of z (frame, from the ring)', '    ldrh    r2, [r0, #6]', '    ldrh    r2, [r0, #4]'),
    ('copies the pad instead of z (drain)', '    ldrh    r7, [r2, #6]', '    ldrh    r7, [r2, #4]'),
    ('CRC leaves the magic out',
     '    ADRF    r1, magic_word\n    mov     r2, #4\n    bl      crc32_update',
     '    ADRF    r1, magic_word\n    mov     r2, #4\n    nop'),
    ('keeps its old block when it reparses',
     '    cmp     r0, r3\n    bne     21f', '    cmp     r0, r0\n    bne     21f\n    b       21f'),
    ('a head at the ring end is refused (the bug seen on the camera)',
     '                                        @ seen once in 474 frames, A001_036 #404)\n    bhi     8f',
     '                                        @ seen once in 474 frames, A001_036 #404)\n    bhs     8f'),
    ('accel hook does not replay mov r2, #0',
     '    mov     r2, #0                      @ the displaced instruction', '    nop'),
    ('accel hook never hands on to the layer below',
     '    cmp     r0, #0\n    bne     92f', '    cmp     r0, #0\n    nop'),
    ('accel hook does not drain', '    ADRF    r10, vars\n    bl      drain', '    ADRF    r10, vars\n    nop'),
    ('drain counts laps not from the time', '    add     r5, r5, #600', '    nop'),
    ('the frame hook drains', '    mov     r0, sp\n    bl      snapshot                    @ sp:', '    bl      drain\n    mov     r0, sp\n    bl      snapshot                    @ sp:'),
    ('drain does not mark the lost', '    strne   r2, [r10, #V_LU]', '    nop'),
    ('snapshot ignores a writer mid-way', '    tst     r5, #1\n    bne     2f', '    tst     r5, #1\n    nop'),
    ('drain keeps no set for a preempting reader', '    ldr     r0, [r10, #V_DHEAD]\n    str     r0, [r10, #V_PDH]', '    ldr     r0, [r10, #V_DHEAD]\n    nop'),
    ('mark leaves out the undrained tail', '3:  add     r0, r5, r8\n    b       9f', '3:  mov     r0, r5\n    b       9f'),
    ('snapshot does not count laps for a quiet level', '    add     r8, r8, #600', '    nop'),
    ('snapshot does not mark what the ring lost', '    str     r0, [r4, #S_GONE]           @ [W, W + n - AVAIL) is in neither place', '    nop'),
    ('a block not lapped by the buffer is called lost', '    subs    r1, r7, r0\n    bpl     32f', '    subs    r1, r7, r0\n    nop'),
    ('the frame reads the undrained tail from the buffer', '    subs    r0, r7, r9\n    bpl     52f', '    subs    r0, r7, r9\n    nop'),
    ('never truncates', '    subs    r2, r2, r1\n    bls     41f', '    subs    r2, r2, r2\n    bls     41f'),
    ('readings before the block are kept', '    bmi     8f                          @ before this block: gone by', '    nop'),
    ('a reading at the mark stays in this block', '    bpl     9f                          @ at or after this block\'s end: next one', '    nop'),
    ('n_events not stored', '    strh    r0, [r11, #58]', '    nop'),
    ('lens table not flagged', '    orr     r0, r0, #F_LENS', '    nop'),
    ('lens table one word short', '    mov     r3, #120', '    mov     r3, #119'),
    ('readout not divided by 9',
     '    umull   r2, r1, r0, r1\n    lsr     r1, r1, #1', '    mov     r1, r0\n    nop'),
    ('vertical binning ignored', '    mul     r7, r7, r3', '    nop'),
]


def run(env_src=None):
    env = dict(os.environ)
    if env_src:
        env['GYR2_SRC'] = str(env_src)
    r = subprocess.run([sys.executable, '-B', '-m', 'unittest', 'test_gyr2'], cwd=HERE,
                       env=env, capture_output=True, text=True)
    return r.returncode, r.stderr.strip().splitlines()[-1] if r.stderr.strip() else ''


def main():
    code, last = run()
    print(f'unmodified: {"PASS" if code == 0 else "FAIL"} ({last})')
    if code:
        return 1
    text = SRC.read_text()
    missed = 0
    only = sys.argv[1:]                          # substrings: run just the matching mutants
    with tempfile.TemporaryDirectory(prefix='gyr2-mut-') as t:
        for name, old, new in MUTANTS:
            if only and not any(o in name for o in only):
                continue
            if text.count(old) != 1:
                print(f'  ?? {name}: pattern not found exactly once')
                missed += 1
                continue
            m = pathlib.Path(t) / 'gyr2.S'
            m.write_text(text.replace(old, new, 1))
            code, last = run(m)
            caught = code != 0
            missed += not caught
            print(f'  {"caught" if caught else "MISSED"}: {name} ({last})')
    ran = [m for m in MUTANTS if not only or any(o in m[0] for o in only)]
    print(f'{len(ran) - missed}/{len(ran)} caught')
    return 1 if missed else 0


if __name__ == '__main__':
    sys.exit(main())
