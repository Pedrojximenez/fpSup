.syntax unified
.arm
.text
/* ============================================================================
 * store_boot_slim -- store_boot.S in fewer words (build_autorun --store-slim,
 * Loader v4 cards).  Same contract, same one check, same order:
 *
 *   magic (a hash of THIS build's loader, taken from the card, never from the
 *   store) -> copy the baked length into the cave -> publish -> tail into the
 *   loader with the echo handler's lr.  A miss returns 0 having touched nothing.
 *
 * What changed: the two cache routines are direct `bl` (the cave is ~7 MB from
 * them, well inside bl's 32 MB), so they are no longer pool words loaded with a
 * second ldmia; the three constants come out in one ldmia; the source pointer
 * is post-incremented by the load that reads the magic.  Every word gone is one
 * `mem set` fewer on every Fast Start 3 boot.
 * ========================================================================== */
.equ STORE,       0xC3075264
.equ CAVE_LOW,    0xC072DE64
.equ BOOT_AT,     0xC072F700
.equ F_DCACHE,    0xC000E91C
.equ F_ICACHE,    0xC000EABC

.macro CALL target
9:  .word 0xEB000000 + ((((\target) - (BOOT_AT + (9b - _start)) - 8) >> 2) & 0xFFFFFF)
.endm

    .global _start
_start:
    push    {r4, r5, r6, lr}
    mov     r6, sp                      @ echo callers can arrive four bytes off
    bic     sp, sp, #7
8:  add     r4, pc, #(0f - 8b - 8)
    ldmia   r4, {r1, r2, r5}            @ STORE, STORE_MAGIC, CAVE_LOW
    ldr     r0, [r1], #4                @ the magic; r1 = the body
    cmp     r0, r2
    bne     7f                          @ not ours: leave everything alone
    mov     r3, r5
    movw    r2, #:lower16:STORE_LEN     @ baked, never read from the store
1:  ldr     ip, [r1], #4
    str     ip, [r3], #4
    subs    r2, r2, #4
    bne     1b
    CALL    F_DCACHE                    @ written words become instructions
    CALL    F_ICACHE
    mov     r0, r5
    mov     sp, r6
    pop     {r4, r5, r6, lr}
    bx      r0                          @ the loader's `boot`, echo handler's lr

7:  mov     r0, #0
    mov     sp, r6
    pop     {r4, r5, r6, pc}

    .align  2
0:  .word   STORE
    .word   STORE_MAGIC
    .word   CAVE_LOW
