/* Loader v4 (copied from v3/sloader_entry.S; allsups removed, strs 4 words).
 * Loader v3: the first bytes of LOADER.BIN's code (file offset 16, a VBIN with
 * no sections -- loader.S branches to buffer + 16 + count*8 = +16 with
 * r0 = the buffer).  build_v3.py lays it out as
 *
 *     [this stub] [c_base: sloader.c, one .text, no relocations]
 *
 * and passes C_BOOT (sl_boot's offset from `entry`, Thumb bit set), SL_DIR and
 * SL_SELF.  The stub does three things the C cannot: say where it is (adr),
 * carry the strings (the C has no .rodata), and carry the power-off routine,
 * which is ARM and must be exactly the one stage2 has used since 2026-09-25. */
.syntax unified
.arm
.text

.equ F_DCACHE,  0xC000E91C
.equ F_ICACHE,  0xC000EABC

entry:
    push    {r4, r5, r6, lr}            @ even count: 8-aligned at the call
    mov     r4, sp
    bic     sp, sp, #7
#ifdef SL_FILE_OFFSET
    /* Shared stage2 passes the resolved entry. Recover the OUTER VBIN so
     * SupManager saves the entire boot envelope, including its FSDS tail. */
    adr     r0, entry
    movw    ip, #:lower16:SL_FILE_OFFSET
    movt    ip, #:upper16:SL_FILE_OFFSET
    sub     r0, r0, ip
#endif
    adr     r3, strs                    @ struct strings { dir, self }
    adr     r1, dir_s
    str     r1, [r3]
    adr     r1, self_s
    str     r1, [r3, #4]
    adr     r1, log_s
    str     r1, [r3, #8]
#ifdef SPLASH_FINISH
    adr     r1, splash
    str     r1, [r3, #12]
#endif
#ifdef UI_PATH
    adr     r1, ui_s
    str     r1, [r3, #16]
#endif
    adr     r1, unhook
    adr     r2, entry                   @ a local label: armasm relocates none
    movw    ip, #:lower16:C_BOOT
    movt    ip, #:upper16:C_BOOT
    add     ip, r2, ip
    blx     ip                          @ sl_boot(vbin, unhook, base, strs)
    mov     sp, r4
    pop     {r4, r5, r6, pc}

/* The power-off routine, copied with the rest into the resident block and run
 * from there.  Called as vtbl[+0xC](obj, reason) from both of XC_PowerOffMgr's
 * lists, so possibly twice; writing a stock word back twice is harmless.
 * [obj+8] is the journal: { address, bytes, words }..., 0. */
unhook:
    push    {r4, r5, r6, lr}
    mov     r6, sp
    bic     sp, sp, #7
#ifdef POFF_HOOK
    ldr     r3, [r0, #12]               @ poff_hook (Thumb): --pwroff-log / --pwroff-file
    cmp     r3, #0
    beq     4f
    push    {r0, r1}                    @ 8 bytes: sp stays 8-aligned
    blx     r3                          @ pl_early(poff, reason)
    pop     {r0, r1}
4:
#endif
    ldr     r4, [r0, #8]
1:  ldr     r0, [r4]
    cmp     r0, #0
    beq     3f
    ldr     r2, [r4, #4]
    add     r4, r4, #8
2:  cmp     r2, #0
    beq     1b
    ldr     r3, [r4], #4
    str     r3, [r0], #4
    sub     r2, r2, #4
    b       2b
3:  movw    r3, #:lower16:F_DCACHE
    movt    r3, #:upper16:F_DCACHE
    blx     r3
    movw    r3, #:lower16:F_ICACHE
    movt    r3, #:upper16:F_ICACHE
    blx     r3
    mov     sp, r6
    pop     {r4, r5, r6, pc}

.align 2
strs:   .word 0, 0, 0, 0, 0          @ dir, self, logname, splash, ui (0: none)
dir_s:  .asciz SL_DIR
self_s: .asciz SL_SELF
log_s:  .asciz "LOAD.LOG"
#ifdef UI_PATH
ui_s:   .asciz UI_PATH
#endif
#ifdef SPLASH_FINISH
/* The four-box completion (frame 4, the hold, the redraw restore), exactly as
 * stage2 ran it: same file, its path passed in as SPLASH_PATH.  Called by the
 * C after LOAD_DONE_US, so the hold is not load time. */
.align 2
splash:
#include "../asm/splash_finish.S"
#endif

.align 2
.global c_base
c_base:
