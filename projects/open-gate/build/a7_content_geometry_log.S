.syntax unified
.arm
.text

/*
 * Read-only A7 content-geometry snapshot logger.
 *
 * Hook site: 0xC031C79C (ARM), inside ContSet_Adr1 after:
 *   - FUN_C0631D38 has programmed the A7 DMA geometry,
 *   - FUN_C0635CD0 has selected the A7 correction tap,
 * and immediately before FUN_C0632058 applies the capture destination.
 *
 * Live ABI at the hook:
 *   r5       current RawInfo
 *   r6       ContSet parameter block
 *   sp+B8    20-byte A7 rectangle descriptor
 *
 * The hook replaces and replays:
 *     ldr r0, [r6, #0x38]
 *
 * State at 0xC072FA10:
 *   +00 magic ('A7G1')
 *   +04 total hook calls
 *   +08 non-null capture snapshots
 *   +0C reserved
 *   +10 latest non-null snapshot (35 words; see the host decoder)
 *
 * This intentionally keeps only the latest non-null A7 setup.  Stop/pause
 * does not pass this point, so the recording setup survives until readout.
 */

.equ ORIGIN,  0xC072F900
.equ RESUME,  0xC031C7A0
.equ LOG,     0xC072FA10
.equ PATH,    0xC343A974
.equ BANKSEL, 0xC37CF948

.macro LDA reg, value
    movw    \reg, #:lower16:\value
    movt    \reg, #:upper16:\value
.endm

.global entry
entry:
    /* Fourteen words preserve all caller state and keep SP aligned. */
    stmdb   sp!, {r0-r12, lr}

    LDA     r12, LOG
    ldr     r0, [r12, #4]
    add     r0, r0, #1
    str     r0, [r12, #4]

    ldr     r7, [r6, #0x38]
    cmp     r7, #0
    beq     done

    add     r9, r12, #0x10
    str     r7, [r9], #4             /* raw capture destination */
    str     r5, [r9], #4             /* RawInfo pointer */

    ldmia   r5, {r0, r1}             /* rec width, height */
    stmia   r9!, {r0, r1}
    add     r8, r5, #0x48
    ldmia   r8, {r0-r3}              /* rec RWZM H/V, bin H/V */
    stmia   r9!, {r0-r3}
    add     r8, r5, #0x58
    ldmia   r8, {r0, r1}             /* live width, height */
    stmia   r9!, {r0, r1}
    add     r8, r5, #0xA0
    ldmia   r8, {r0-r3}              /* live RWZM H/V, bin H/V */
    stmia   r9!, {r0-r3}

    LDA     r8, PATH
    ldr     r0, [r8]                 /* packed A0/A7/A1 enable bytes */
    ldr     r1, [r8, #8]             /* A7 correction selector */
    ldr     r2, [r8, #0x18]          /* A7 start/route selector */
    stmia   r9!, {r0-r2}

    /* Original SP is 56 bytes above the logger's save frame. */
    add     r8, sp, #56
    add     r8, r8, #0xB8
    ldmia   r8, {r0-r3, r7}          /* complete 20-byte A7 descriptor */
    stmia   r9!, {r0-r3, r7}

    LDA     r8, BANKSEL
    ldr     r0, [r8]
    str     r0, [r9], #4

    /* Main correction bank: routing/tap and RAW-ZOOM state. */
    LDA     r8, 0x300F0000
    ldr     r0, [r8, #0x004]
    ldr     r1, [r8, #0x6D0]
    ldr     r2, [r8, #0x900]
    ldr     r3, [r8, #0x908]
    ldr     r4, [r8, #0x90C]
    stmia   r9!, {r0-r4}

    /* Mirrored/sub correction bank. */
    add     r8, r8, #0x2000
    ldr     r0, [r8, #0x004]
    ldr     r1, [r8, #0x6D0]
    ldr     r2, [r8, #0x900]
    ldr     r3, [r8, #0x908]
    ldr     r4, [r8, #0x90C]
    stmia   r9!, {r0-r4}

    /* A7 output height and packed-RAW pitch, already programmed here. */
    LDA     r8, 0x30182310
    ldmia   r8, {r0, r1}
    stmia   r9!, {r0, r1}

    ldr     r0, [r12, #8]
    add     r0, r0, #1
    dmb     ish
    str     r0, [r12, #8]            /* publish completed snapshot last */

done:
    ldmia   sp!, {r0-r12, lr}

    /* Replay the displaced instruction, then resume at C031C7A0. */
    ldr     r0, [r6, #0x38]
    .word   0xEA000000 | (((RESUME - (ORIGIN + (. - entry)) - 8) >> 2) & 0x00ffffff)
