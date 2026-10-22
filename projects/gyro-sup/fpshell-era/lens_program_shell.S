.syntax unified
.arm
.text
/* Lens program: read the lens, write \LENS\<lens name>.TXT
 *
 * Runs once per power-up and is entirely independent of the gyro logger -- its own
 * code, its own buffers, its own file. The lens read takes the L-mount bus mutex and
 * costs ~345 ms per block, which is why it must never share the 2500 Hz gyro thread.
 *
 * The model string is used as the filename, so it has to be sanitised: "LUMIX S 40/F2"
 * carries a slash, which is a path separator, and FAT rejects several more. Anything
 * outside a conservative allowed set becomes '_', and trailing spaces and dots go --
 * the block is space-padded to a fixed 59 bytes, and a trailing dot or space would
 * either be silently dropped or reject the name outright.
 *
 * STATE: [0]=0x4C ran [4]=mkdir ret [8]=ok(0x2d) [12]=ok(0x0a) [16]=text len
 *        [20]=focal (0.1 mm) [24]=min focus (mm) [28]=name length
 */

/* Every buffer must sit ABOVE 0xC072F100. Below that is the USB shell worker's own
 * code and state: camera-side writes there succeed, so the values read back look
 * fine, but the worker overwrites them again. The file object landing at 0xC072EB00
 * was exactly this -- open failed every run after the first, silently, while an
 * identical sequence with the object at 0xC072F480 worked. Same shape as the earlier
 * bug where an injected routine at 0xC072F100 clobbered fpstate's PEEK_CODE.
 * (Under AutoRun there is no worker and the map is different -- these are the
 * addresses for shell-side testing only.) */
.equ STATE,       0xC072F600
.equ NAMEBUF,     0xC072F640
.equ PARAMBUF,    0xC072F680
.equ PATHBUF,     0xC072F6E0
.equ FILEOBJ,     0xC072F480
.equ TEXTBUF,     0xC072F7A0

.macro la reg, value
    movw    \reg, #:lower16:\value
    movt    \reg, #:upper16:\value
.endm

.global cave_entry
cave_entry:
    push    {r4-r8, lr}
    la      r7, STATE
    mov     r0, #0x4C
    str     r0, [r7]

    /* ---- \LENS directory (harmless if it already exists) ---- */
    sub     sp, sp, #8
    la      ip, 0xC0407E20
    blx     ip
    mov     r1, r0
    mov     r0, sp
    la      ip, 0xC0366918
    blx     ip
    mov     r0, sp
    adr     r1, s_dir
    mov     r2, #0
    la      ip, 0xC03669C0
    blx     ip
    str     r0, [r7, #4]
    mov     r0, sp
    mov     r1, #2
    la      ip, 0xC0366940
    blx     ip
    add     sp, sp, #8

    /* ---- lens blocks ---- */
    la      r0, 0xC03554A0
    blx     r0
    mov     r1, #0x2d
    la      r2, NAMEBUF
    la      r3, 0xC0355DE0
    blx     r3
    str     r0, [r7, #8]
    la      r0, 0xC03554A0
    blx     r0
    mov     r1, #0x0a
    la      r2, PARAMBUF
    la      r3, 0xC0355DE0
    blx     r3
    str     r0, [r7, #12]

    /* focal and closest focus are big-endian u16 at +4 and +12; both held steady
     * across reads while every other field moved with the focus ring. */
    la      r5, PARAMBUF
    ldrb    r0, [r5, #4]
    ldrb    r1, [r5, #5]
    orr     r0, r1, r0, lsl #8
    str     r0, [r7, #20]
    ldrb    r0, [r5, #12]
    ldrb    r1, [r5, #13]
    orr     r0, r1, r0, lsl #8
    str     r0, [r7, #24]

    /* ---- path = "\LENS\" + sanitised name + ".TXT" ---- */
    la      r4, PATHBUF
    adr     r0, s_dirsep
    mov     r1, r4
    bl      emit_str
    mov     r4, r0
    la      r0, NAMEBUF
    mov     r1, r4
    mov     r2, #59
    bl      emit_safe
    mov     r4, r0
    adr     r0, s_ext
    mov     r1, r4
    bl      emit_str
    mov     r4, r0
    mov     r0, #0
    strb    r0, [r4]
    la      r0, PATHBUF
    sub     r0, r4, r0
    str     r0, [r7, #28]

    /* ---- body ---- */
    la      r4, TEXTBUF
    adr     r0, s_lens
    mov     r1, r4
    bl      emit_str
    mov     r4, r0
    la      r0, NAMEBUF
    mov     r1, r4
    mov     r2, #59
    bl      emit_trim
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
    sub     r5, r4, r0
    str     r5, [r7, #16]

    la      r0, PATHBUF
    la      r1, TEXTBUF
    mov     r2, r5
    bl      write_file
    mov     r0, #0
    pop     {r4-r8, pc}

/* r0 = src, r1 = dst, r2 = max. Filename-safe copy: keeps 0-9 A-Z a-z _ - space,
 * maps everything else to '_', then drops trailing spaces. */
emit_safe:
    push    {r4-r6, lr}
    mov     r4, r1
    mov     r5, r1
2:  cmp     r2, #0
    beq     6f
    ldrb    r3, [r0], #1
    cmp     r3, #0x20
    blo     6f
    cmp     r3, #0x7e
    bhi     6f
    cmp     r3, #'0'
    blo     3f
    cmp     r3, #'9'
    bls     5f
3:  cmp     r3, #'A'
    blo     4f
    cmp     r3, #'Z'
    bls     5f
4:  cmp     r3, #'a'
    blo     7f
    cmp     r3, #'z'
    bls     5f
7:  cmp     r3, #' '
    beq     5f
    cmp     r3, #'_'
    beq     5f
    cmp     r3, #'-'
    beq     5f
    mov     r3, #'_'
5:  strb    r3, [r4], #1
    cmp     r3, #' '
    addne   r5, r4, #0               /* r5 = end of last non-space */
    sub     r2, r2, #1
    b       2b
6:  mov     r0, r5
    pop     {r4-r6, pc}

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
    mov     r2, #7                   /* 7 overwrites; 0x0402 only creates */
    la      ip, 0xC0365FB0
    blx     ip
    la      ip, STATE
    str     r0, [ip, #36]            /* open return */
    la      r0, FILEOBJ
    mov     r1, r5
    mov     r2, r6
    la      ip, 0xC03660E8
    blx     ip
    la      ip, STATE
    str     r0, [ip, #40]            /* write return */
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

/* Same as emit_strn but returns the cursor just past the last non-space, so the
 * block's fixed-width space padding does not end up in the file body. */
emit_trim:
    push    {r4-r6, lr}
    mov     r4, r1
    mov     r5, r1
1:  cmp     r2, #0
    beq     2f
    ldrb    r3, [r0], #1
    cmp     r3, #0x20
    blo     2f
    cmp     r3, #0x7e
    bhi     2f
    strb    r3, [r4], #1
    cmp     r3, #' '
    addne   r5, r4, #0
    sub     r2, r2, #1
    b       1b
2:  mov     r0, r5
    pop     {r4-r6, pc}

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
s_dir:    .asciz "\\LENS"
.align 2
s_dirsep: .asciz "\\LENS\\"
.align 2
s_ext:    .asciz ".TXT"
.align 2
s_lens:   .asciz "lens="
.align 2
s_blk:    .asciz "\nblk0a="
.align 2
