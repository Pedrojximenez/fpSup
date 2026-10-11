.syntax unified
.arm
.text

/*
 * Read-only RAW DMA transition logger for Cont_Pause.
 *
 * Hook site: 0xC031CC98 (ARM), function entry.  Incoming r1 is the non-zero
 * RAW capture destination passed from frame+0x4c through FUN_c030cff0.
 * Cont_Pause subsequently applies that address to every enabled RAW buffer
 * bank.  Geometry has already been programmed by ContSet_Adr1 at this point.
 *
 * The hook replaces and later replays:
 *     push {r4, r5, r6, r7, r8, r11, lr}
 * It records only transitions in the enable/height/pitch tuple, deliberately
 * excluding the per-frame destination from the signature.  This prevents the
 * rotating capture buffers from filling every slot before recording starts.
 *
 * State at 0xC072FA10:
 *   +0x00 magic ('RDL1')
 *   +0x04 number of stored transitions (maximum four)
 *   +0x08 last observed signature
 *   +0x0c reserved
 *   +0x10 four records, 0x30 bytes each:
 *          signature, incoming destination, enable bytes word,
 *          A0 height/pitch/destination,
 *          A7 height/pitch/destination,
 *          A1 height/pitch/destination
 *
 * Enable bytes at 0xC343A974 are ordered A0, A7, A1.  The MMIO banks are:
 *   A0 0x301821xx, A1 0x301822xx, A7 0x301823xx.
 * Pitch is expressed in 32-bit words: packed RAW12 1936 -> 0x2d6, while
 * packed RAW12 3032 -> 0x471.
 */

.equ ORIGIN,       0xC072F900
.equ RESUME,       0xC031CC9C
.equ LOG,          0xC072FA10
.equ ENABLES,      0xC343A974
.equ A0_GEOM,      0x30182110
.equ RECORDS,      4
.equ RECORD_SIZE,  0x30

.macro LDA reg, value
    movw    \reg, #:lower16:\value
    movt    \reg, #:upper16:\value
.endm

.macro MIX_BANK rot_h, rot_p
    ldrd    r0, r1, [r8]
    eor     r6, r6, r0, ror #\rot_h
    eor     r6, r6, r1, ror #\rot_p
.endm

.macro STORE_BANK
    ldrd    r0, r1, [r8]
    /* The record's H/P pair is only word-aligned for every other bank. */
    stmia   r12!, {r0, r1}
    ldr     r0, [r8, #0x70]       /* bank +0x80 destination */
    str     r0, [r12], #4
.endm

.global entry
entry:
    /* Fourteen words keep the temporary stack eight-byte aligned. */
    stmdb   sp!, {r0-r12, lr}

    /* Ignore pause/null calls.  The incoming r1 is saved at [sp,#4]. */
    ldr     r0, [sp, #4]
    cmp     r0, #0
    beq     done

    LDA     r5, LOG

    /* Signature = enables plus the three banks' height/pitch pairs. */
    LDA     r8, ENABLES
    ldr     r6, [r8]
    ubfx    r6, r6, #0, #24         /* only the three documented enable bytes */
    LDA     r8, A0_GEOM
    MIX_BANK 3, 7                  /* A0 */
    add     r8, r8, #0x200
    MIX_BANK 11, 17                /* A7 */
    sub     r8, r8, #0x100
    MIX_BANK 19, 23                /* A1 */
    orr     r6, r6, #0x80000000    /* zero marks no previous signature */

    ldr     r2, [r5, #8]
    cmp     r2, r6
    beq     done
    str     r6, [r5, #8]

    ldr     r2, [r5, #4]
    cmp     r2, #RECORDS
    bhs     done

    /* r7 = LOG+0x10 + transition_index*0x30. */
    add     r7, r5, #0x10
    add     r7, r7, r2, lsl #5
    add     r7, r7, r2, lsl #4
    add     r12, r7, #4

    ldr     r0, [sp, #4]           /* incoming RAW capture destination */
    str     r0, [r12], #4
    LDA     r8, ENABLES
    ldr     r0, [r8]
    str     r0, [r12], #4

    LDA     r8, A0_GEOM
    STORE_BANK                     /* A0 = 0x301821xx */
    add     r8, r8, #0x200
    STORE_BANK                     /* A7 = 0x301823xx */
    sub     r8, r8, #0x100
    STORE_BANK                     /* A1 = 0x301822xx */

    dmb     ish
    str     r6, [r7]               /* publish complete record last */
    add     r2, r2, #1
    str     r2, [r5, #4]

done:
    ldmia   sp!, {r0-r12, lr}

    /* Replay the displaced prologue exactly, then resume at C031CC9C. */
    stmdb   sp!, {r4, r5, r6, r7, r8, r11, lr}
    .word   0xEA000000 | (((RESUME - (ORIGIN + (. - entry)) - 8) >> 2) & 0x00ffffff)
