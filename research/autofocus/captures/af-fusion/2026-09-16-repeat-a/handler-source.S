.syntax unified
.arm
.text

/*
 * af_fusion_snapshot — one coherent, read-only AF observation.
 *
 * This temporarily replaces the USB shell's `echo` handler.  It only reads
 * fixed firmware state (plus the confirmed monotonic-tick getter), writes one
 * record into the shell parameter page, then CPU-copies it to the worker's
 * existing DMA reply buffer. It never calls a focus-drive or exposure setter.
 *
 * Record layout is documented by af_fusion_collector.py.  The two index pairs
 * are deliberate:
 *
 *   0xC3291534 -> AF-area index for saf_jdat_h/l (51 entries)
 *   0xC329153C -> sweep-sample index for mposm[] (up to 1000 entries)
 *
 * The handler samples each index before and after gathering.  Host code must
 * reject `indices_stable == false` for DFD fitting.  The host writes a
 * per-install session nonce in a separate seed word at 0xC072F7D0.  Only an
 * executing handler copies it to record + 0xCC.  This distinction matters:
 * a delayed USB reply retains a pointer to RECORD, not a payload copy, so the
 * host must not stamp the new nonce directly into the old record.
 */

.equ RECORD,       0xC072F700
.equ RECORD_SIZE,  0xD0
.equ SESSION_NONCE,0xC072F7D0
.equ CAP_LEN,      0xC072F040
.equ CAP_PTR,      0xC072F04C
.equ FRAMEBUF,     0xC3757A7C
.equ TICK_US,      0xC002B6E0

.equ MAGIC,        0x31464641      /* bytes "AFF1" */
.equ TRAILER,      0x45464641      /* bytes "AFFE" */

.equ AF_AREA_IDX,  0xC3291534
.equ AF_SAMPLE_IDX,0xC329153C
.equ AF_DRIVE,     0xC32065A0
.equ AF_AREA,      0xC32046A4
.equ AF_ROUTE,     0xC32915B0
.equ AF_HI,        0xC32985E8
.equ AF_LO,        0xC32986B4
.equ AF_PEAK_NOW,  0xC32915C4
.equ AF_PEAK_MAX,  0xC32915C8
.equ AF_PEAK_MIN,  0xC32915CC
.equ AF_POSITION,  0xC32914E0
.equ AF_MPOSM,     0xC3291958
.equ AF_BODY_MOVE, 0xC340467C
.equ AF_DIR_VOTE,  0xC33D5144
.equ AF_SPEED_LPF, 0xC33D5148
.equ AF_STEP_STATE,0xC3291518
.equ AF_PEAK_ARGMAX,0xC32915F2
.equ AF_AREA0_REF, 0xC32914FC

.equ AAT_BOX,      0xC3033E00
.equ AAT_CONF,     0xC3033E26
.equ FACE_MODE,    0xC37CCE6C      /* DetectionResultMgr + 0x3D0 */
.equ FACE_RECT,    0xC37CCE7C      /* DetectionResultMgr + 0x3E0 */
.equ FACE0_VALID,  0xC37CCADC      /* manager + 0x10 + 0x30 */
.equ FACE0_TRACK,  0xC37CCAE0      /* manager + 0x10 + 0x34 */

.equ IMX_REL_GAIN, 0xC343B5A0      /* IMX410 obj 0xC343B588 + 0x18 */
.equ IMX_ANALOG_CODE,0xC343B5A8    /* applied 12-bit sensor gain code */
.equ IMX_ANALOG_RATIO,0xC343B5B4   /* linear analog ratio x100 */
.equ IMX_HCG,      0xC343B5BC      /* byte: v30 decision, 0=LCG/1=HCG */
.equ AF_RGB_GAIN,  0xC32915B4
.equ AF_SENS,      0xC3291694
.equ AF_SHUTTER,   0xC329169C
.equ AF_FNO,       0xC32916B0
.equ CAPTURE_STATE,0xC3033A54      /* capture singleton + 0x220, u16 */
.equ MOVIE_RECORD, 0xC347E08F      /* movie object 0xC347DF38 + 0x157 */

.macro LDA reg, value
    movw    \reg, #:lower16:\value
    movt    \reg, #:upper16:\value
.endm

.macro COPY_WORD address, offset
    LDA     r0, \address
    ldr     r1, [r0]
    str     r1, [r4, #\offset]
.endm

.global entry
entry:
    push    {r4, r5, r6, r7, r8, r9, r10, r11, r12, lr}
    LDA     r4, RECORD

    /* Continue a valid prior sequence, otherwise start at zero. */
    ldr     r0, [r4, #0x00]
    LDA     r1, MAGIC
    cmp     r0, r1
    ldreq   r5, [r4, #0x08]
    mvnne   r5, #0
    add     r5, r5, #1
    mov     r0, #0
    str     r0, [r4, #0x00]       /* invalidate until the record is complete */
    str     r5, [r4, #0x08]
    str     r0, [r4, #0x0C]       /* flags, filled below */
    mov     r6, #0

    mov     r0, #2
    strh    r0, [r4, #0x04]
    mov     r0, #RECORD_SIZE
    strh    r0, [r4, #0x06]

    LDA     r12, TICK_US
    blx     r12
    str     r0, [r4, #0x10]

    /* Area index selects the current H/L cells. */
    LDA     r0, AF_AREA_IDX
    ldr     r7, [r0]
    str     r7, [r4, #0x18]
    cmp     r7, #51
    movlo   r8, r7
    movhs   r8, #0
    orrlo   r6, r6, #1
    str     r8, [r4, #0x20]

    /* Sweep-sample index selects exposure-centre mposm[]. */
    LDA     r0, AF_SAMPLE_IDX
    ldr     r9, [r0]
    str     r9, [r4, #0x24]
    cmp     r9, #1000
    movlo   r10, r9
    movhs   r10, #0
    orrlo   r6, r6, #2
    str     r10, [r4, #0x2C]

    COPY_WORD AF_DRIVE,      0x30
    COPY_WORD AF_AREA,       0x34
    COPY_WORD AF_ROUTE,      0x38

    LDA     r0, AF_HI
    add     r0, r0, r8, lsl #2
    ldr     r1, [r0]
    str     r1, [r4, #0x3C]
    LDA     r0, AF_LO
    add     r0, r0, r8, lsl #2
    ldr     r1, [r0]
    str     r1, [r4, #0x40]

    COPY_WORD AF_PEAK_NOW,   0x44
    COPY_WORD AF_PEAK_MAX,   0x48
    COPY_WORD AF_PEAK_MIN,   0x4C
    COPY_WORD AF_POSITION,   0x50
    COPY_WORD AF_MPOSM,      0x54
    LDA     r0, AF_MPOSM
    add     r0, r0, r10, lsl #2
    ldr     r1, [r0]
    str     r1, [r4, #0x58]
    COPY_WORD AF_BODY_MOVE,  0x5C
    COPY_WORD AF_DIR_VOTE,   0x60
    COPY_WORD AF_SPEED_LPF,  0x64
    COPY_WORD AF_STEP_STATE, 0x68
    LDA     r0, AF_PEAK_ARGMAX
    ldrsh   r1, [r0]
    str     r1, [r4, #0x6C]
    COPY_WORD AF_AREA0_REF,  0x70

    /* AAT is four packed i16 fields; keep the original packing. */
    LDA     r0, AAT_BOX
    ldr     r1, [r0]
    str     r1, [r4, #0x74]
    ldr     r1, [r0, #4]
    str     r1, [r4, #0x78]
    LDA     r0, AAT_CONF
    ldrb    r1, [r0]
    str     r1, [r4, #0x7C]
    cmp     r1, #19
    orrgt   r6, r6, #0x10

    /* The consolidated AF-facing face rectangle is four i32 fields. */
    COPY_WORD FACE_MODE,     0x80
    LDA     r0, FACE_RECT
    ldr     r1, [r0]
    str     r1, [r4, #0x84]
    ldr     r1, [r0, #4]
    str     r1, [r4, #0x88]
    ldr     r1, [r0, #8]
    str     r1, [r4, #0x8C]
    mov     r11, r1
    ldr     r1, [r0, #12]
    str     r1, [r4, #0x90]
    cmp     r11, #0
    ble     3f
    cmp     r1, #0
    orrgt   r6, r6, #8
3:
    LDA     r0, FACE0_TRACK
    ldr     r1, [r0]
    str     r1, [r4, #0x94]
    LDA     r0, FACE0_VALID
    ldrb    r1, [r0]
    str     r1, [r4, #0x98]

    COPY_WORD IMX_REL_GAIN,       0x9C
    COPY_WORD IMX_ANALOG_CODE,    0xA0
    COPY_WORD IMX_ANALOG_RATIO,   0xA4
    LDA     r0, IMX_HCG
    ldrb    r1, [r0]
    str     r1, [r4, #0xA8]
    COPY_WORD AF_RGB_GAIN,   0xAC
    COPY_WORD AF_SENS,       0xB0
    COPY_WORD AF_SHUTTER,    0xB4
    COPY_WORD AF_FNO,        0xB8
    LDA     r0, CAPTURE_STATE
    ldrh    r1, [r0]
    str     r1, [r4, #0xBC]
    LDA     r0, MOVIE_RECORD
    ldrb    r1, [r0]
    str     r1, [r4, #0xC0]
    cmp     r1, #0
    orrne   r6, r6, #0x20

    /* Re-read indices.  Bit 2 means both stayed fixed during the snapshot. */
    LDA     r0, AF_AREA_IDX
    ldr     r1, [r0]
    str     r1, [r4, #0x1C]
    cmp     r1, r7
    bne     1f
    LDA     r0, AF_SAMPLE_IDX
    ldr     r1, [r0]
    str     r1, [r4, #0x28]
    cmp     r1, r9
    orreq   r6, r6, #4
    b       2f
1:
    LDA     r0, AF_SAMPLE_IDX
    ldr     r1, [r0]
    str     r1, [r4, #0x28]
2:
    str     r6, [r4, #0x0C]

    LDA     r12, TICK_US
    blx     r12
    str     r0, [r4, #0x14]

    LDA     r0, TRAILER
    str     r0, [r4, #0xC4]
    mvn     r0, r5
    str     r0, [r4, #0xC8]
    LDA     r0, SESSION_NONCE
    ldr     r1, [r0]
    str     r1, [r4, #0xCC]
    dsb

    LDA     r0, MAGIC
    str     r0, [r4, #0x00]       /* final commit marker */
    dsb

    /* The C-region code cave is CPU-readable but not a coherent USB DMA
     * payload. DSB alone does not clean dirty cache lines. Follow dumpraw.S:
     * copy to the worker's already allocated capture buffer (pool + 0x2000).
     * The host validates the pool pointer before installing this handler. */
    LDA     r0, FRAMEBUF
    ldr     r1, [r0]
    add     r1, r1, #0x2000
    mov     r0, #0
4:
    ldr     r2, [r4, r0]
    str     r2, [r1, r0]
    add     r0, r0, #4
    cmp     r0, #RECORD_SIZE
    blo     4b
    dsb
    LDA     r0, CAP_PTR
    mov     r1, #0
    str     r1, [r0]             /* select worker's default capture buffer */
    LDA     r0, CAP_LEN
    mov     r1, #RECORD_SIZE
    str     r1, [r0]
    mov     r0, #0
    pop     {r4, r5, r6, r7, r8, r9, r10, r11, r12, pc}
