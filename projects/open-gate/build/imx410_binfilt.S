.syntax unified
.arm
.text
#include "og_pic.inc"
/* CRCT x3 binning kernels, per axis (the user 2026-10-05: every setting).
 * Replaces the two `blx` that hand the CRCT driver struct (r1, built from a
 * stock reduction record by FUN_c032d9a0) to the register writers
 * (ROLE 1: C032DDF0 -> C0635DB0, ROLE 2: C032DE70 -> C0635DC8; FUN_c0633b30
 * copies struct +0x08.. / +0x1C.. / +0x29.. to 0x300F0810.. / 0850.. / 08C4).
 * Under CUSTOM, each axis binned x3 (AXIS A_BIN) gets kernel BINFILT bits 0-3
 * (horizontal: Hbin2 + main hbin, /64) or bits 4-7 (vertical, /4096) from the
 * six below; bit 8 (record 1) is imx410_sellog's.  The stock records are not
 * touched.  r0 / r1 / lr go to the writer unchanged. */
.macro LDA reg, value
#ifdef OG_V3
    OGLDA   \reg, \value
#else
    movw    \reg, #:lower16:\value
    movt    \reg, #:upper16:\value
#endif
.endm
.equ A_BIN, 4*4
.global entry
entry:
    push    {r4, r5}
    LDA     r3, FLAG
    ldr     r3, [r3]
    cmp     r3, #1
    bne     go
    LDA     r3, AXIS
    ldr     r2, [r3, #A_BIN]
    LDA     r3, BINFILT
    ldr     r3, [r3]
    and     ip, r2, #0xFF
    cmp     ip, #3
    bne     vert
    and     ip, r3, #0xF
    cmp     ip, #6
    movhs   ip, #0
    adr     r4, h_k
    add     ip, r4, ip, lsl #2
    ldrb    r4, [ip]
    ldrb    r5, [ip, #1]
    ldrb    ip, [ip, #2]
    strb    r4, [r1, #0x29]         @ Hbin2 (the one branch C uses)
    strb    r5, [r1, #0x2A]
    strb    ip, [r1, #0x2B]
    add     r4, r1, #0x1C           @ main hbin, 4 x 3
1:  ldrb    r5, [r1, #0x29]
    strb    r5, [r4], #1
    ldrb    r5, [r1, #0x2A]
    strb    r5, [r4], #1
    ldrb    r5, [r1, #0x2B]
    strb    r5, [r4], #1
    add     r5, r1, #0x28
    cmp     r4, r5
    blo     1b
vert:
    lsr     ip, r2, #16
    cmp     ip, #3
    bne     go
    ubfx    ip, r3, #4, #4
    cmp     ip, #6
    movhs   ip, #0
    adr     r4, v_k
    add     ip, r4, ip, lsl #3
    ldrh    r4, [ip]                @ c0, 0, c1, c2: no word reads as an ARM branch
    ldrh    r5, [ip, #4]            @ (the USER packer scans payload words for B / BL)
    ldrh    ip, [ip, #6]
    add     r2, r1, #8              @ 3 x 3 u16
    mov     r3, #3
2:  strh    r4, [r2], #2
    strh    r5, [r2], #2
    strh    ip, [r2], #2
    subs    r3, r3, #1
    bne     2b
go:
    pop     {r4, r5}
    ldr     pc, [pc, #-4]           @ interworking: the writer is Thumb
    .word   TARGET + 1
    @ (1,1,1) (1,2,1) (1,4,1) (1,6,1) (1,14,1) (0,1,0)
h_k:  .byte 21, 22, 21, 0,  16, 32, 16, 0,  11, 42, 11, 0,  8, 48, 8, 0,  4, 56, 4, 0,  0, 64, 0, 0
v_k:  .hword 1365, 0, 1366, 1365,  1024, 0, 2048, 1024,  683, 0, 2730, 683,  512, 0, 3072, 512
      .hword 256, 0, 3584, 256,  0, 0, 4096, 0
