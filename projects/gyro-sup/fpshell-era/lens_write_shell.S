.syntax unified
.arm
.text
/* Lens identity -> text file, run from injected code over the USB shell.
 *
 * Proves the two halves the on-camera lens program needs, before any of it goes
 * near an AutoRun: the firmware's own locked L-mount block read, and the file API,
 * both called from code we injected rather than from a hook the firmware already
 * trusted. Reading the blocks is already proven from the host side (monitor/
 * lensdump.py); what is new here is doing it and writing the result ourselves.
 *
 * STATE:  [0]=0x4C ran  [4]=ctx  [8]=ok(0x2d)  [12]=ok(0x0a)  [16]=text length
 */

.equ STATE,       0xC072EC00
.equ NAMEBUF,     0xC072EC40      /* block 0x2d, 59 B */
.equ PARAMBUF,    0xC072ECC0      /* block 0x0a, 86 B */
.equ TEXTBUF,     0xC072ED40      /* formatted output */
.equ FILEOBJ,     0xC072EB00
.equ PATHBUF,     0xC072EB80      /* host writes "\LENS.TXT" here */

.equ FN_LENS_CTX,  0xC03554A0
.equ FN_LENS_READ, 0xC0355DE0

.macro la reg, value
    movw    \reg, #:lower16:\value
    movt    \reg, #:upper16:\value
.endm

.global cave_entry
cave_entry:
    push    {r4-r7, lr}
    la      r7, STATE
    mov     r0, #0x4C
    str     r0, [r7]

    la      r0, FN_LENS_CTX
    blx     r0
    str     r0, [r7, #4]
    mov     r1, #0x2d
    la      r2, NAMEBUF
    la      r3, FN_LENS_READ
    blx     r3
    str     r0, [r7, #8]

    la      r0, FN_LENS_CTX
    blx     r0
    mov     r1, #0x0a
    la      r2, PARAMBUF
    la      r3, FN_LENS_READ
    blx     r3
    str     r0, [r7, #12]

    /* ---- format ---- */
    la      r4, TEXTBUF
    adr     r0, s_lens
    mov     r1, r4
    bl      emit_str
    mov     r4, r0
    la      r0, NAMEBUF
    mov     r1, r4
    mov     r2, #59
    bl      emit_strn
    mov     r4, r0
    adr     r0, s_blk
    mov     r1, r4
    bl      emit_str
    mov     r4, r0
    la      r5, PARAMBUF
    mov     r6, #86
1:  ldrb    r0, [r5], #1
    mov     r1, r4
    bl      emit_hex8
    mov     r4, r0
    subs    r6, r6, #1
    bne     1b
    mov     r0, #10
    strb    r0, [r4], #1
    la      r0, TEXTBUF
    sub     r5, r4, r0               /* text length */
    str     r5, [r7, #16]

    /* ---- write ---- */
    la      r0, PATHBUF
    la      r1, TEXTBUF
    mov     r2, r5
    bl      write_file

    mov     r0, #0
    pop     {r4-r7, pc}

/* r0 = path, r1 = data, r2 = length */
write_file:
    push    {r4-r6, lr}
    mov     r4, r0
    mov     r5, r1
    mov     r6, r2
    la      ip, 0xC0444658
    blx     ip
    mov     r1, #0
    la      ip, 0xC0444698
    blx     ip
    mov     r1, r0
    la      r0, FILEOBJ
    la      ip, 0xC0365E90
    blx     ip
    la      r0, FILEOBJ
    mov     r1, r4
    movw    r2, #0x0402
    la      ip, 0xC0365FB0
    blx     ip
    la      r0, FILEOBJ
    mov     r1, r5
    mov     r2, r6
    la      ip, 0xC03660E8
    blx     ip
    la      r0, FILEOBJ
    la      ip, 0xC0366020
    blx     ip
    la      r0, FILEOBJ
    mov     r1, #2
    la      ip, 0xC0365ED0
    blx     ip
    pop     {r4-r6, pc}

emit_str:
    ldrb    r2, [r0], #1
    cmp     r2, #0
    beq     1f
    strb    r2, [r1], #1
    b       emit_str
1:  mov     r0, r1
    bx      lr

emit_strn:
    push    {lr}
1:  cmp     r2, #0
    beq     2f
    ldrb    r3, [r0], #1
    cmp     r3, #0x20
    blo     2f
    cmp     r3, #0x7e
    bhi     2f
    strb    r3, [r1], #1
    sub     r2, r2, #1
    b       1b
2:  mov     r0, r1
    pop     {pc}

emit_nib:
    cmp     r0, #10
    addlo   r0, r0, #'0'
    addhs   r0, r0, #('a' - 10)
    strb    r0, [r1], #1
    mov     r0, r1
    bx      lr

emit_hex8:
    push    {r4, lr}
    mov     r4, r0
    lsr     r0, r4, #4
    and     r0, r0, #0xf
    bl      emit_nib
    mov     r1, r0
    and     r0, r4, #0xf
    bl      emit_nib
    pop     {r4, pc}

.align 2
s_lens: .asciz "lens="
.align 2
s_blk:  .asciz "\nblk0a="
.align 2
