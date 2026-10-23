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
    ('never writes the commit magic',
     'ldr     r0, =MAGIC                  @ the commit, last\n    str     r0, [r11]',
     'ldr     r0, =MAGIC                  @ the commit, last\n    nop'),
    ('ignores a refused claim of the accel site',
     '    adr     r3, accel_stock\n    ldr     ip, [r5, #SVC_CLAIM]\n    blx     ip\n    add     sp, sp, #8\n    cmp     r0, #0\n    bne     9f',
     '    adr     r3, accel_stock\n    ldr     ip, [r5, #SVC_CLAIM]\n    blx     ip\n    add     sp, sp, #8\n    cmp     r0, #0\n    nop'),
    ('no backfill at a take start', '.equ BACKFILL,     250', '.equ BACKFILL,     0'),
    ('copies the pad instead of z (frame, from the ring)', '    ldrh    r2, [r0, #6]', '    ldrh    r2, [r0, #4]'),
    ('copies the pad instead of z (drain)', '    ldrh    r7, [r2, #6]', '    ldrh    r7, [r2, #4]'),
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
    ('readings before the block are kept', '    bmi     8f                          @ before this block: gone by', '    nop'),
    ('a reading at the mark stays in this block', '    bpl     9f                          @ at or after this block\'s end: next one', '    nop'),
    ('n_events not stored', '    strh    r0, [r11, #58]', '    nop'),
    ('the commit magic is not cleared first', '    mov     r0, #0\n    str     r0, [r11]\n', '    mov     r0, #0\n    nop\n'),
    ('carries the newest, not the oldest, when more is due', '    addhi   r6, r7, r1', '    subhi   r7, r6, r1'),
    ('the next block does not start where this one ended', '    str     r6, [r10, #V_PREV]\n    ldr     r0, [r10, #V_FRAMES]', '    ldr     r0, [sp, #S_MARK]\n    str     r0, [r10, #V_PREV]\n    ldr     r0, [r10, #V_FRAMES]'),
    ('frame_mark is the block end, not the hook', '    ldr     r1, [sp, #S_MARK]\n    sub     r1, r1, r7', '    mov     r1, r6\n    sub     r1, r1, r7'),
    ('the block is not word aligned', '    add     r0, r0, #3\n    bic     r0, r0, #3\n    subs    r1, r8, r0', '    nop\n    nop\n    subs    r1, r8, r0'),
    ('looks for another tag', '.equ GTAG,         0x4653', '.equ GTAG,         0x4654'),
    ('a bogus calibrated focal length is kept', '    movhs   r0, #0                      @ not a focal length: none', '    nop'),
    ('the calibrated focal length is not stored', '    ldr     r0, =LENS_FOCAL             @ calibrated focal | frame_mark << 16\n    ldr     r0, [r0]', '    ldr     r0, =LENS_FOCAL             @ calibrated focal | frame_mark << 16\n    mov     r0, #0'),
    ('lines are not stored', '    ldrh    r6, [r0, #8]                @ lines read', '    mov     r6, #0'),
    ('vertical binning not stored', '    ldrh    r6, [r0, #0x48]             @ and vertical', '    mov     r6, #0'),
    ('hmax not stored', '    orr     r5, r4, r5, lsl #16\n    str     r5, [r10, #V_MHM]', '    mov     r5, r4\n    str     r5, [r10, #V_MHM]'),
    ('the writer build is left out', '    ldr     r0, =(2 | (2 << 8) | (WRITER << 16))', '    ldr     r0, =(2 | (2 << 8))'),
    ('the observer adds the tag in any mode', '    cmp     r1, #EV_BUILD\n    bne     9f', '    cmp     r1, #EV_BUILD\n    nop'),
    ('the observer does not check the builder', '    movs    r5, r0\n    beq     9f\n    /* The size', '    movs    r5, r0\n    nop\n    /* The size'),
    ('the observer returns 0 and is detached', '9:  mov     r0, #1\n    add     sp, sp, #24', '9:  mov     r0, #0\n    add     sp, sp, #24'),
    ('the tag is not capped', '    cmp     r6, r0\n    movhi   r6, r0', '    cmp     r6, r0\n    nop'),
    ('the tag is sized for 3 frames', '.equ GTAG_FRAMES,  4', '.equ GTAG_FRAMES,  3'),
    ('a zero rate divides by zero', '    cmp     r0, #0\n    cmpne   r1, #0\n    beq     1f', '    nop\n    cmp     r1, #0\n    beq     1f'),
    ('the samples a frame round down', '    add     r1, r1, r0\n    sub     r1, r1, #1\n    bl      udiv', '    nop\n    nop\n    bl      udiv'),
    ('a full Subject is attached to anyway', '    cmp     r2, #0\n    beq     9f\n    add     r1, r6, #V_OVT', '    cmp     r2, #0\n    nop\n    add     r1, r6, #V_OVT'),
    ('the observer is never attached', '    ldr     ip, =F_ATTACH\n    blx     ip', '    nop\n    nop'),
    ('a take start is not marked', '9:  mov     r0, #1\n    str     r0, [r10, #V_NEWTAKE]', '9:  mov     r0, #0\n    str     r0, [r10, #V_NEWTAKE]'),
    ('the new-take mark is never cleared', '    mov     r1, #0\n    str     r1, [r10, #V_NEWTAKE]', '    mov     r1, #0\n    nop'),
    ('frames write into a template take_start never saw', '    cmp     r1, r4\n    movne   r1, #0\n    strne   r1, [r10, #V_WOFF]', '    cmp     r1, r4\n    nop\n    nop'),
    ('other types of notify write frames', '    cmp     r1, #EV_TAKE_TYPE\n    bne     9f\n    ldr     r1, [r0]                    @ mode', '    cmp     r1, #EV_TAKE_TYPE\n    nop\n    ldr     r1, [r0]                    @ mode'),
    ('the mode-2 notify is not handled', '    cmp     r1, #EV_SERIALIZED\n    beq     20f', '    cmp     r1, #EV_SERIALIZED\n    nop'),
    ('frame clobbers r11', 'frame:\n    push    {r4, r5, r6, r7, r8, r9, r10, r11, lr}', 'frame:\n    push    {r4, r5, r6, r7, r8, r9, r10, lr}\n    push    {r0}'),
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
