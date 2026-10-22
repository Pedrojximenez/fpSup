/* imx410_poff -- 14-bit back to 12-bit at power-off (SETTINGS_AREA_FIRST_RULE exception).
 *
 * 14-bit (eRawBitType 1) is a stock value the stock CINE menu does not offer:
 * persisted, the bit-depth menu is blank when the camera later boots without
 * Sensor Lab.  User decision 2026-10-01 ("可以接受風險"): run as real 14-bit,
 * revert to 12-bit at power-off.  A battery pull / freeze skips this -- accepted.
 *
 * entry     The loader's single BIN entry.  Registers OBJ on XC_PowerOffMgr's
 *           first list (the one walked BEFORE the backup stores are flushed,
 *           XC_PowerOffMgr::v1 step 2 vs step 4), then calls RESTORE exactly
 *           as stage2 would (r0 = its own address) and returns.
 * callback  vtbl[+0xC](obj, reason): mgr = C0057AE8(); if the movie bit depth
 *           (settings slot +0x198, getter C005BF28) is 1 (14-bit), set 0 via
 *           the stock setter C005BEF0 -- the same store the menu writes.
 *
 * STATE: +0 registered (POFF_ADD result)  +4 callback runs  +8 reverts  +C last read
 */
    .syntax unified
    .arm
.macro LDA reg, value
    movw    \reg, #:lower16:\value
    movt    \reg, #:upper16:\value
.endm
.equ POFF_MGR,   0xC0023A98
.equ POFF_ADD,   0xC0024118
.equ SETTINGS,   0xC0057AE8
.equ BIT_GET,    0xC005BF28
.equ BIT_SET,    0xC005BEF0

    .global entry
entry:
    push    {r4, r5, r6, lr}
    LDA     r3, POFF_MGR
    blx     r3
    movs    r4, r0
    beq     1f
    LDA     r1, OBJ
    mov     r2, #0                      @ first list
    LDA     r3, POFF_ADD
    blx     r3
    LDA     r1, STATE
    str     r0, [r1]
1:  LDA     r0, RESTORE                 @ the original entry, called as stage2 would
    blx     r0
    pop     {r4, r5, r6, pc}

callback:
    push    {r4, r5, r6, lr}
    LDA     r5, STATE
    ldr     r1, [r5, #4]
    add     r1, r1, #1
    str     r1, [r5, #4]
    LDA     r3, SETTINGS
    blx     r3
    mov     r4, r0
    LDA     r3, BIT_GET
    blx     r3
    str     r0, [r5, #12]
    cmp     r0, #1                      @ eRawBitType 1 = 14-bit
    bne     2f
    mov     r0, r4
    mov     r1, #0                      @ eRawBitType 0 = 12-bit
    mov     r2, #0
    LDA     r3, BIT_SET
    blx     r3
    ldr     r1, [r5, #8]
    add     r1, r1, #1
    str     r1, [r5, #8]
2:  pop     {r4, r5, r6, pc}

    .balign 4
    .global obj_vtbl
obj_vtbl:                               @ OBJ: { vtbl } ; vtbl: [0,0,0,callback]
    .word   0, 0, 0, CODE + (callback - entry)
