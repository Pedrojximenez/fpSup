/* IMXB -- IMX410 bus logger, a loader v4 sup (fp 5.02).
 *
 * Every sensor register write goes through FUN_c0322c70(reg, val) (ARM; 570
 * callers) -> FUN_c0128898, the only writer of the sensor bus controller
 * 0x21C00114 (`0x81 | reg<<8`, data in 0x21C00118).  We hook its first two
 * words and, while the host has set `en`, append {tick_us, reg, val, caller}
 * to a ring in our BSS; then stock runs unchanged.
 *
 * Hook: C0322C70 `push {r4,r5,r8,lr}; sub sp,sp,#4` -> `ldr pc,[pc,#-4]; .word shim`.
 * The site is claimed SL_EXCL with its stock words, so the core's journal puts
 * them back at power-off (a warm restart keeps the firmware image).
 *
 * State (host reads it at block + STATE_OFF; build.json says where):
 *   +0  magic "IMXB"   +4 en (host: 1 log, 0 pass)   +8 count (all writes seen while en)
 *   +12 cap (entries)  +16 shim address
 *   +20 nsub (host, 0..8)  +24 hits (substitutions made)  +32 sub[8]: (reg << 16) | val
 *   +64 entries[cap], 16 B each: {tick_us, reg, val, lr}, slot = count & (cap-1)
 *
 * Substitution (version 2): a write to a register listed in sub[0..nsub) goes out
 * with the listed value instead -- the firmware rewrites gain and exposure every
 * frame, so this is the only way to hold, say, 3F/40 different from 3D/3E.  The
 * log records the value that went out.
 *
 * Alternation (version 3): +28 alt.  When bit 0 is set, an entry is
 * (reg << 16) | (val_odd << 8) | val_even and the phase flips each time the
 * firmware writes 0x041F -- the first register of its per-frame block -- so
 * successive frames get alternate values (temporal HDR).  Bit 31 of alt is the
 * current phase (the host reads it).
 *
 * Frame capture (version 3): `frame_cb` is a BUFA0 completion callback
 * (FUN_c0630620 calls [0xC37CF8CC](arg, done_addr) from the ISP interrupt).
 * The host puts its address in the window struct (+0x10) and fills, at +CAPT:
 *   n, i (reset 0), park (DMA word for "nowhere": scratch), addr[16] (DMA words,
 *   physical >> 2, as 0x30182180 takes them); per completion we record
 *   {tick_us, done_addr} at +CAPT+0x50 and point 0x30182180 at addr[i] (park
 *   once the list is used up).  The next-but-one frame lands there: the DMA
 *   latches 0x30182180 when a frame starts, before this interrupt runs.
 *
 * Defines from build.py: STATE_OFF (from the block's first byte), CAP (power of 2),
 * CAPT (capture block, from the state), CAPT_LOG (completions it records).
 */
.syntax unified
.arm
.text

.equ SITE,        0xC0322C70
.equ RESUME,      0xC0322C78
.equ W0,          0xE92D4130     /* push {r4, r5, r8, lr} */
.equ W1,          0xE24DD004     /* sub sp, sp, #4        */
.equ LDR_PC_M4,   0xE51FF004     /* ldr pc, [pc, #-4]     */
.equ IRQ_OFF,     0xC000EC14
.equ IRQ_RESTORE, 0xC000EC24
.equ TICK_US,     0xC002B6E0
.equ MAGIC,       0x42584D49     /* "IMXB" */
.equ SVC_CLAIM,   8
.equ SVC_PUBLISH, 24
.equ SL_EXCL,     2
.equ S_EN,        4
.equ S_COUNT,     8
.equ S_CAP,       12
.equ S_SHIM,      16
.equ S_NSUB,      20
.equ S_HITS,      24
.equ S_ALT,       28
.equ S_SUB,       32
.equ BUFA0_NEXT,  0x30182180
.equ FIRST_REG,   0x041F         /* the first write of the per-frame block   */
.equ MAX_SUB,     8
.equ S_ENT,       64

.macro LDA reg, value
    movw    \reg, #:lower16:\value
    movt    \reg, #:upper16:\value
.endm

/* int entry(void *block, const struct sl_svc *svc, const char *path) */
.global entry
entry:
    push    {r4, r5, r6, lr}
    mov     r4, r0
    mov     r5, r1
    LDA     r0, SITE                    @ the stock words, or nothing is touched
    ldr     r1, [r0]
    LDA     r2, W0
    cmp     r1, r2
    bne     fail
    ldr     r1, [r0, #4]
    LDA     r2, W1
    cmp     r1, r2
    bne     fail
    LDA     r0, STATE_OFF
    add     r6, r4, r0                  @ state (BSS: zeroed by the core)
    str     r6, g_state
    LDA     r0, MAGIC
    str     r0, [r6]
    LDA     r0, CAP
    str     r0, [r6, #S_CAP]
    adr     r0, shim
    str     r0, [r6, #S_SHIM]
    LDA     r1, CAPT + 0x4C             @ capture block +0x4C: where frame_cb is
    adr     r0, frame_cb
    str     r0, [r6, r1]
    sub     sp, sp, #8                  @ claim(svc, SITE, 8, stock, SL_EXCL): 5th on the stack
    mov     r0, #SL_EXCL
    str     r0, [sp]
    mov     r0, r5
    LDA     r1, SITE
    mov     r2, #8
    adr     r3, stock
    ldr     ip, [r5, #SVC_CLAIM]
    blx     ip
    add     sp, sp, #8
    cmp     r0, #0
    bne     fail
    mov     r0, r5                      @ g_state reaches memory before the hook
    ldr     ip, [r5, #SVC_PUBLISH]
    blx     ip
    LDA     r0, SITE                    @ armed last: the address first, then the jump
    adr     r1, shim
    str     r1, [r0, #4]
    LDA     r1, LDR_PC_M4
    str     r1, [r0]
    mov     r0, r5
    ldr     ip, [r5, #SVC_PUBLISH]
    blx     ip
    mov     r0, #0                      @ SL_KEEP
    pop     {r4, r5, r6, pc}
fail:
    mov     r0, #1                      @ SL_RELEASE
    pop     {r4, r5, r6, pc}

/* C0322C70(reg, val), lr = the caller.  The firmware may arrive with sp = 4
 * mod 8: align around the calls. */
shim:
    push    {r0, r1, r2, r3, r4, r5, r6, lr}
    mov     r6, sp
    bic     sp, sp, #7
    ldr     r4, g_state
#ifndef MUTANT_NO_SUB
    ldr     r5, [r4, #S_ALT]            @ alternation: flip the phase per frame block
    tst     r5, #1
    beq     4f
    LDA     r2, FIRST_REG
    cmp     r0, r2
    eoreq   r5, r5, #0x80000000
    streq   r5, [r4, #S_ALT]
4:  ldr     r2, [r4, #S_NSUB]           @ substitution: r0 = reg is still the caller's
    cmp     r2, #MAX_SUB
    movhi   r2, #MAX_SUB
    add     r3, r4, #S_SUB
1:  cmp     r2, #0
    beq     3f
    ldr     ip, [r3], #4
    cmp     r0, ip, lsr #16
    bne     2f
    and     r1, ip, #0xFF               @ even phase (and the only value without alt)
    ldr     r5, [r4, #S_ALT]
    tst     r5, #1
    beq     5f
    tst     r5, #0x80000000
#ifndef MUTANT_NO_ALT
    movne   r1, ip, lsr #8
    andne   r1, r1, #0xFF
#endif
5:  str     r1, [r6, #4]                @ the value stock will send (popped below)
    ldr     r5, [r4, #S_HITS]
    add     r5, r5, #1
    str     r5, [r4, #S_HITS]
2:  sub     r2, r2, #1
    b       1b
3:
#endif
    ldr     r2, [r4, #S_EN]
    cmp     r2, #0
    beq     9f
    LDA     ip, IRQ_OFF                 @ reserve a slot
    blx     ip
    mov     r5, r0
    ldr     r2, [r4, #S_COUNT]
    add     r3, r2, #1
    str     r3, [r4, #S_COUNT]
    mov     r0, r5
    mov     r5, r2
    LDA     ip, IRQ_RESTORE
    blx     ip
    ldr     r3, [r4, #S_CAP]
    sub     r3, r3, #1
    and     r5, r5, r3
    add     r5, r4, r5, lsl #4
    add     r5, r5, #S_ENT              @ r5 = entry
    LDA     ip, TICK_US
    blx     ip
    str     r0, [r5]
    ldr     r0, [r6]                    @ reg
    str     r0, [r5, #4]
    ldr     r0, [r6, #4]                @ val
    str     r0, [r5, #8]
    ldr     r0, [r6, #28]               @ caller
    str     r0, [r5, #12]
9:  mov     sp, r6
    pop     {r0, r1, r2, r3, r4, r5, r6, lr}
#ifndef MUTANT_NO_REPLAY
    push    {r4, r5, r8, lr}            @ stock C0322C70, replayed
    sub     sp, sp, #4
    ldr     pc, resume
#else
    bx      lr
#endif

/* BUFA0 completion, from the ISP interrupt (FUN_c0630620): r0 = arg, r1 = the
 * finished frame's address (uncached).  Short: one timestamp, one register. */
frame_cb:
    push    {r4, r5, r6, lr}
    mov     r6, sp
    bic     sp, sp, #7
    mov     r5, r1
    ldr     r4, g_state
    LDA     r0, CAPT
    add     r4, r4, r0                  @ r4 = capture block
    ldr     r2, [r4, #4]                @ i
    cmp     r2, #CAPT_LOG
    bhs     8f                          @ log full: just park
    LDA     ip, TICK_US
    blx     ip
    ldr     r2, [r4, #4]
    add     r3, r4, #0x50
    add     r3, r3, r2, lsl #3
    str     r0, [r3]                    @ {tick, done}
    str     r5, [r3, #4]
8:  ldr     r2, [r4, #4]                @ i
    ldr     r1, [r4]                    @ n, at most 16
    cmp     r1, #16
    movhi   r1, #16
    add     r3, r2, #1
    str     r3, [r4, #4]
    add     r0, r4, #0xC                @ addr[0..n)
    cmp     r2, r1
    ldrlo   r0, [r0, r2, lsl #2]        @ addr[i]
    ldrhs   r0, [r4, #8]                @ park
    LDA     r1, BUFA0_NEXT
    str     r0, [r1]
    mov     sp, r6
    pop     {r4, r5, r6, pc}

    .align  2
stock:      .word W0, W1
resume:     .word RESUME
g_state:    .word 0
