.syntax unified
.arm
.text
/* ============================================================================
 * dispfit — tell the live-view compositor its source is 3:2, not 16:9.
 * ============================================================================
 *
 * FUN_c0437e98(obj, idx) is an accessor: `return *(obj + idx*8)`, idx < 4.
 * Entry 0 of two LiveViewState objects is the geometry descriptor the display
 * path sizes itself from, and it still describes a 16:9 source, which is why
 * open gate records correctly and previews as garbage.
 *
 *   C0437EC4  add r2, r5, r4, lsl #3
 *   C0437EC8  ldr r2, [r2]          r2 = the descriptor
 *   C0437ECC  mov r0, r2            <- hooked; displaced, replayed on the way out
 *   C0437ED0  pop {r4, r5, pc}
 *
 * Hooking here rather than at the prologue keeps this the same shape as the
 * C043A19C hook that already works: one displaced `mov`, r5 = obj and r4 = idx
 * both still live, and lr returns to the instruction after.
 *
 * Two differences from the FP3K build this was learned from:
 *
 *   - the descriptor is copied from the firmware's own at run time and only the
 *     geometry is rewritten, so every field we do not understand keeps whatever
 *     the firmware put there, rather than being frozen at build time;
 *   - the height is derived as width x 2/3 rather than fixed at 1080, so it
 *     stays right if the panel geometry is not what we assumed.
 *
 * v2, 2026-09-11.  v1 derived the WIDTH from the height and shrank 1620x911
 * to 1366x911.  Both are 3:2, but the buffer behind the descriptor is
 * 1920x1088 (the 0x003FC000 size field), and narrowing the width below the
 * buffer's usable width made the menu overlay render at the wrong pitch.
 * Read back from the camera after v1 was armed:
 *
 *     0xC072FA20:  1366 x 911   1366 x 911   ...  0x003FC000
 *
 * so the firmware's own descriptor was 1620x911 and 911 was the height.
 * Growing the height to 1080 keeps the width at the buffer's width and
 * 1080 still fits inside 1088.  That is also the shape the FP3K build
 * substitutes wholesale.
 *
 * Guarded: idx must be 0, obj must be one of the two known objects, and both
 * dimensions must be plausible. Anything else falls through untouched.
 *
 * Result buffer at 0xC072FA20 (clear of the C043A19C telemetry at 0xC072FA00).
 * ========================================================================== */

.equ FLAG,  0xC0731C08         /* OG3K 生效才動手 */
.equ DESC,  0xC072FA20         /* 44 bytes */
.equ OBJ_A, 0xC375EB68
.equ OBJ_B, 0xC375ED3C
.equ SPAN,  44
.equ LIMIT, 8192

.macro LDA reg, value
    movw    \reg, #:lower16:\value
    movt    \reg, #:upper16:\value
.endm

.global entry
entry:
    push    {r1, r2, r3, r6, ip, lr}    @ six: the stack stays eight-byte aligned

    LDA     ip, FLAG                    @ v3: OG3K 沒被選中就完全不動手
    ldr     r6, [ip]
    cmp     r6, #0
    beq     pass

    cmp     r4, #0                      @ entry 0 only
    bne     pass
    LDA     ip, OBJ_A
    cmp     r5, ip
    beq     known
    LDA     ip, OBJ_B
    cmp     r5, ip
    bne     pass

known:
    cmp     r2, #0
    beq     pass
    ldr     r6, [r2]                    @ width must be plausible
    cmp     r6, #0
    beq     pass
    LDA     ip, LIMIT
    cmp     r6, ip
    bhi     pass
    ldr     r6, [r2, #4]                @ height must be plausible
    cmp     r6, #0
    beq     pass
    cmp     r6, ip
    bhi     pass

    LDA     r3, DESC                    @ copy the firmware's own descriptor
    mov     ip, #0
copy:
    ldr     r6, [r2, ip]
    str     r6, [r3, ip]
    add     ip, ip, #4
    cmp     ip, #SPAN
    blt     copy

    movw    r1, #21846                  @ 21846/65536 = 1/3 to 1 part in 2e6

    ldr     r6, [r3, #0x00]             @ first pair: h := w * 2/3
    mul     ip, r6, r1
    lsr     ip, ip, #16
    lsl     ip, ip, #1
    str     ip, [r3, #0x04]

    ldr     r6, [r3, #0x10]             @ second pair, same transform
    cmp     r6, #0
    beq     done
    mul     ip, r6, r1
    lsr     ip, ip, #16
    lsl     ip, ip, #1
    str     ip, [r3, #0x14]

done:
    mov     r0, r3
    b       out

pass:
    mov     r0, r2                      @ the displaced instruction

out:
    pop     {r1, r2, r3, r6, ip, lr}
    bx      lr
