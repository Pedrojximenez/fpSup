.syntax unified
.arm
.text
/* Can a file stay open across several writes and append in order?
 *
 * Everything on camera so far opens, writes once and closes. Streaming the gyro to
 * the card needs open-once / write-many / close-at-stop, and that is the mechanism
 * the whole small-buffer design rests on -- so it gets proven before anything is
 * built on top of it.
 *
 * ARG: [0]=path [4]=mode      OUT: [0]=open [4..]=each write's return, [20]=close
 */
.equ ARG,     0xC072F400
.equ OUT,     0xC072F440
.equ FILEOBJ, 0xC072F480

.macro la reg, value
    movw    \reg, #:lower16:\value
    movt    \reg, #:upper16:\value
.endm

.global cave_entry
cave_entry:
    push    {r4-r7, lr}
    la      r4, ARG
    ldr     r5, [r4]
    ldr     r6, [r4, #4]
    la      r7, OUT
    mov     r0, #0
    str     r0, [r7]
    str     r0, [r7, #4]
    str     r0, [r7, #8]
    str     r0, [r7, #12]
    str     r0, [r7, #20]

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
    mov     r1, r5
    mov     r2, r6
    la      ip, 0xC0365FB0
    blx     ip
    str     r0, [r7]
    cmp     r0, #0
    beq     9f

    adr     r4, s_a
    bl      wr1
    str     r0, [r7, #4]
    adr     r4, s_b
    bl      wr1
    str     r0, [r7, #8]
    adr     r4, s_c
    bl      wr1
    str     r0, [r7, #12]

    la      r0, FILEOBJ
    la      ip, 0xC0366020
    blx     ip
    str     r0, [r7, #20]
9:
    la      r0, FILEOBJ
    mov     r1, #2
    la      ip, 0xC0365ED0
    blx     ip
    mov     r0, #0
    pop     {r4-r7, pc}

/* r4 = NUL-terminated chunk -> write it, return the API's value */
wr1:
    push    {r4-r6, lr}
    mov     r5, r4
    mov     r6, #0
1:  ldrb    r0, [r5], #1
    cmp     r0, #0
    beq     2f
    add     r6, r6, #1
    b       1b
2:  la      r0, FILEOBJ
    mov     r1, r4
    mov     r2, r6
    la      ip, 0xC03660E8
    blx     ip
    pop     {r4-r6, pc}

.align 2
s_a: .asciz "CHUNK-A\n"
.align 2
s_b: .asciz "CHUNK-BB\n"
.align 2
s_c: .asciz "CHUNK-CCC\n"
.align 2
