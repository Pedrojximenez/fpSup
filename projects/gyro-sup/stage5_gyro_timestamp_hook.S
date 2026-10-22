.syntax unified
.arm
.text
.global stage5_hook

/*
 * SIGMA fp Ver.5.02 Stage-5 gyro logger.
 * Load address: 0xC072DE64. Hook site: 0xC00D0794.
 *
 * File header (48 bytes):
 *   u32 magic = 'GFS5'; u32 version = 4; u32 sample_period_us = 2500;
 *   u32 start_us; u32 camera_id; u32 reel_no; u32 clip_no; u32 initial_head;
 *   u32 frame_readout_us; u32 reserved[3].
 *
 * v4 records the exposure time each clip was shot at. NOTE: this field was first
 * labelled rolling-shutter readout, and that was wrong -- across four clips it only
 * ever returned 7989 or 16654 us, which are 1/125 s and 1/60 s, i.e. shutter speeds.
 * AF uses it as exposure/2 to find the centre of the exposure, which is what made it
 * look like a readout figure. Rolling shutter comes from the IMX410 mode tables
 * instead (see notes/ONCAMERA_GCSV_AND_LENS_PROFILE.md). FUN_c030c7f0 is the
 * firmware's own accessor (sensor-timing vtable +0x3C); reading it costs a vtable
 * fetch, so it is safe on this thread -- unlike lens identity, which needs an L-mount
 * bus transaction (~376 ms measured) and would overrun the 600-sample gyro ring
 * (240 ms). That is why the lens side is a separate program, not a pass bolted on
 * to this one's stop path.
 * Batch header (24 bytes), followed by sample_count raw 8-byte samples:
 *   u32 magic = 'GFT2'; u32 timestamp_us; u32 sample_count; u32 flags (bit0=wrap);
 *   i16 accel_x, accel_y, accel_z, pad.
 *
 * v3 adds the accelerometer (MMA8452Q, 1024 LSB/g) so Gyroflow horizon lock works.
 * One accel triple per batch, carrying the batch's own TickTimer stamp -- that puts
 * both sensors in a single clock domain, which the archive lists as the precondition
 * for emitting accel at all. The cache only refreshes at ~47 Hz (firmware polls it;
 * raising the sensor ODR past 100 Hz changes nothing -- measured 45.7/46.4/46.7/46.7 Hz
 * at ODR 100/200/400/800), and that is ample for a gravity vector.
 *
 * The sensor boots in a 6.25 Hz auto-sleep mode, which is useless for horizon lock,
 * so a one-shot init raises it. It writes CTRL_REG1/2 directly rather than calling
 * IMUDevInterface_MMA8452Q__v3: that helper does a software reset plus ~26 ms of
 * delays, and this hook runs on the 2500 Hz gyro thread where that would drop samples.
 */

/* Data lives high so the code can grow: everything below 0xC072EE00 is now code,
 * which is 3.9 KiB instead of the 1.5 KiB the old layout allowed. The ceiling is
 * 0xC072F000, where the USB shell worker starts -- the two are never loaded together
 * (different AutoRun cards), but leaving the boundary intact keeps that true. */
.equ STATE_ACTIVE,  0xC072EE80
.equ STATE_COUNT,   0xC072EE84
.equ STATE_HEAD,    0xC072EE88
.equ STATE_STARTVD, 0xC072EE8C
.equ STATE_ACCELINIT, 0xC072EE90
.equ STATE_GCSVLEN, 0xC072EE94
.equ ACCEL_IFACE,   0xC3777914      /* IMUDevInterface_MMA8452Q singleton */
.equ ACCEL_CACHE,   0xC377790C      /* i16 X, Y, Z (axis-remapped by firmware) */
.equ FN_LOCK,       0xC0010298      /* scoped-lock enter, as used by ..._v3 */
.equ FN_UNLOCK,     0xC00102D0      /* scoped-lock leave */
.equ FILE_OBJECT,   0xC072EE00
.equ FILE_PATH,     0xC072EF00
.equ GCSV_PATH,     0xC072EF40
.equ USER_BASE,     0x44F6ADC0
.equ USER_END,      0x456EADC0
.equ PATH_MGR_SD,   0xC3438400
.equ GYRO_DESC_PTR, 0xC31E3FCC

.macro ldr_addr reg, value
    movw    \reg, #:lower16:\value
    movt    \reg, #:upper16:\value
.endm

stage5_hook:
    /* Ten registers keeps the public-call stack 8-byte aligned. */
    push    {r3-r11, lr}

    /* Original instruction replaced at 0xC00D0794. */
    movw    ip, #0xC6F9
    movt    ip, #0xC01E
    blx     ip
    mov     r11, r0

    /* One-shot: lift the accelerometer out of its 6.25 Hz auto-sleep mode. */
    ldr_addr r0, STATE_ACCELINIT
    ldr     r1, [r0]
    cmp     r1, #0
    bne     accel_ready
    mov     r1, #1
    str     r1, [r0]
    bl      accel_init
accel_ready:

    /* Camera's real MovieRecording state: LensIsTr singleton + 0x157. */
    movw    ip, #0xB2D0
    movt    ip, #0xC035
    blx     ip
    ldrb    r5, [r0, #0x157]

    ldr_addr r6, STATE_ACTIVE
    ldr     r7, [r6]
    cmp     r5, #0
    beq     recording_stopped
    cmp     r7, #0
    bne     drain_ring

recording_started:
    mov     r0, #1
    str     r0, [r6]

    /* Monotonic TickTimer timestamp in microseconds. */
    movw    ip, #0xB6E0
    movt    ip, #0xC002
    blx     ip
    ldr_addr r1, STATE_STARTVD
    str     r0, [r1]

    /* Build root sidecar name. Manager holds the previous clip, so add one. */
    ldr_addr r8, PATH_MGR_SD
    ldr_addr r9, FILE_PATH
    ldrb    r0, [r8, #8]
    strb    r0, [r9, #1]
    add     r0, r9, #2
    ldr     r1, [r8, #0x0c]
    bl      put_decimal_3
    add     r0, r9, #6
    ldr     r1, [r8, #0x10]
    add     r1, r1, #1
    bl      put_decimal_3
    /* Same camera/reel/clip into the .CSV sidecar path. */
    ldr_addr r0, GCSV_PATH
    ldrb    r1, [r8, #8]
    strb    r1, [r0, #1]
    add     r0, r0, #2
    ldr     r1, [r8, #0x0c]
    bl      put_decimal_3
    ldr_addr r0, GCSV_PATH
    add     r0, r0, #6
    ldr     r1, [r8, #0x10]
    add     r1, r1, #1
    bl      put_decimal_3

    /* Initialize the 32-byte file header. */
    ldr_addr r10, USER_BASE
    movw    r0, #0x4647
    movt    r0, #0x3553              /* little-endian 'GFS5' */
    str     r0, [r10, #0]
    mov     r0, #4
    str     r0, [r10, #4]
    movw    r0, #2500
    str     r0, [r10, #8]
    ldr_addr r0, STATE_STARTVD
    ldr     r0, [r0]
    str     r0, [r10, #12]
    ldrb    r0, [r8, #8]
    str     r0, [r10, #16]
    ldr     r0, [r8, #0x0c]
    str     r0, [r10, #20]
    ldr     r0, [r8, #0x10]
    add     r0, r0, #1
    str     r0, [r10, #24]

    /* Snapshot the current gyro head; do not copy pre-record history. */
    ldr_addr r0, GYRO_DESC_PTR
    ldr     r0, [r0]
    ldr     r0, [r0, #0x60]
    ldr     r1, [r0]
    str     r1, [r10, #28]
    ldr_addr r0, STATE_HEAD
    str     r1, [r0]
    /* Readout time is filled in on the first drain, not here: at the instant the
     * record flag flips the sensor has not necessarily switched readout mode yet, so
     * sampling now sometimes captures the standby value instead (16.65 ms rather than
     * the recording one). Zero means "not captured yet". */
    mov     r0, #0
    str     r0, [r10, #0x20]
    str     r0, [r10, #0x24]
    str     r0, [r10, #0x28]
    str     r0, [r10, #0x2c]
    ldr_addr r0, STATE_COUNT
    mov     r1, #48
    str     r1, [r0]
    b       return_original

drain_ring:
    /* Refuse to append unless the header is really there. Writing the two files at stop
     * now takes a while (building ~700 KiB of text, then two file writes), and if
     * recording restarts during that the start event is missed -- the buffer then has
     * no header and everything appended to it is unusable. Bailing out here means a
     * missed start costs that one take rather than producing a file that looks valid
     * until something tries to parse it. */
    ldr_addr r0, USER_BASE
    ldr     r1, [r0]
    movw    r2, #0x4647
    movt    r2, #0x3553              /* 'GFS5' */
    cmp     r1, r2
    bne     return_original

    /* Capture the exposure time once, on the first drain.
     *
     * This field was originally taken for the rolling-shutter readout, following the
     * label in AF_AE_INTERNALS. It is not: across four takes it returned only 7989 or
     * 16654 us, which are 1/125 s and 1/60 s. AF consumes it as exposure/2 to locate
     * the exposure centre, which is consistent. Kept because per-clip exposure is
     * worth having, but the readout time still needs the sensor's line timing. */
    ldr_addr r0, USER_BASE
    ldr     r1, [r0, #0x20]
    cmp     r1, #0
    bne     1f
    movw    ip, #0xC7F0
    movt    ip, #0xC030              /* FUN_c030c7f0 */
    blx     ip
    mov     r1, r0
    ldr_addr r0, USER_BASE
    str     r1, [r0, #0x20]
    /* Sensor mode indices, from the LiveView state object (FUN_c0436590 singleton at
     * 0xC375D840, its +8 pointer is what FUN_c04375c8 hands back; HdmiLimit prints the
     * first word as "table"). Resolution and frame rate alone do not identify the mode
     * -- 1080p/29.97 matches two of them, sharing a geometry but not a line timing, so
     * the readout time differs by 35% between them. Recording the index settles it. */
    movw    r1, #0xD840
    movt    r1, #0xC375
    ldr     r1, [r1, #8]
    cmp     r1, #0
    beq     1f
    ldr     r2, [r1]
    str     r2, [r0, #0x24]
    ldr     r2, [r1, #0x10]
    str     r2, [r0, #0x28]
1:
    /* r8=ring base, r5=new head, r6=old head. */
    ldr_addr r0, GYRO_DESC_PTR
    ldr     r0, [r0]
    ldr     r8, [r0, #0x60]
    ldr     r5, [r8]
    ldr_addr r0, STATE_HEAD
    ldr     r6, [r0]
    cmp     r5, r6
    beq     return_original

    /* Read monotonic microsecond timestamp before copying. */
    movw    ip, #0xB6E0
    movt    ip, #0xC002
    blx     ip
    mov     r9, r0
    mov     r10, #0                  /* flags */
    cmp     r5, r6
    subhi   r4, r5, r6
    bhi     have_byte_count
    /* 0x12C0, not 0x12C4. The ring runs [base+4, base+0x12C4), so it holds
     * 0x12C0 bytes -- 600 samples of eight. Counting the wrap as 0x12C4 takes
     * four bytes too many, which copies one stale word and shifts every later
     * sample out of phase. Found 2026-08-26 in a stage-6 capture, where the
     * breaks fell exactly 0x12C4 apart and the samples either side were
     * continuous; every gcsv this program has produced has the same fault at
     * every wrap, which is roughly once every 240 ms of recording. */
    movw    r4, #0x12C0
    add     r4, r4, r5
    sub     r4, r4, r6
    mov     r10, #1                 /* ring wrapped */
have_byte_count:
    mov     r3, r4, lsr #3          /* sample_count */

    /* Reserve/write the batch header, failing closed if the 8 MiB buffer is full. */
    ldr_addr r7, STATE_COUNT
    ldr     r2, [r7]
    ldr_addr r1, USER_BASE
    add     r0, r1, r2
    add     ip, r0, #24
    add     ip, ip, r4
    ldr_addr r1, USER_END
    cmp     ip, r1
    bhi     return_original
    movw    r1, #0x4647
    movt    r1, #0x3254              /* little-endian 'GFT2' */
    str     r1, [r0, #0]
    str     r9, [r0, #4]
    str     r3, [r0, #8]
    str     r10, [r0, #12]
    /* Accel triple, stamped by the same TickTimer read as this batch. */
    ldr_addr r1, ACCEL_CACHE
    ldrsh   ip, [r1]
    strh    ip, [r0, #16]
    ldrsh   ip, [r1, #2]
    strh    ip, [r0, #18]
    ldrsh   ip, [r1, #4]
    strh    ip, [r0, #20]
    mov     ip, #0
    strh    ip, [r0, #22]
    add     r2, r2, #24
    str     r2, [r7]

    /* Copy one or two ring spans. copy_span takes [r0,r1). */
    add     r0, r6, #4
    cmp     r5, r6
    bhi     no_wrap_copy
    movw    r2, #0x12C4
    add     r1, r8, r2
    bl      copy_span
    add     r0, r8, #4
    add     r1, r5, #4
    bl      copy_span
    b       update_head
no_wrap_copy:
    add     r1, r5, #4
    bl      copy_span
update_head:
    ldr_addr r0, STATE_HEAD
    str     r5, [r0]
    b       return_original

recording_stopped:
    cmp     r7, #0
    beq     return_original
    mov     r0, #0
    str     r0, [r6]
    ldr_addr r0, STATE_COUNT
    ldr     r0, [r0]
    cmp     r0, #32
    bls     return_original

    /* Validated Stage-3 file API sequence. */
    movw    ip, #0x4658
    movt    ip, #0xC044
    blx     ip
    mov     r1, #0
    movw    ip, #0x4698
    movt    ip, #0xC044
    blx     ip
    mov     r1, r0
    ldr_addr r0, FILE_OBJECT
    movw    ip, #0x5E90
    movt    ip, #0xC036
    blx     ip
    ldr_addr r0, FILE_OBJECT
    ldr_addr r1, FILE_PATH
    movw    r2, #0x0402
    movw    ip, #0x5FB0
    movt    ip, #0xC036
    blx     ip
    ldr_addr r0, FILE_OBJECT
    ldr_addr r1, USER_BASE
    ldr_addr r2, STATE_COUNT
    ldr     r2, [r2]
    movw    ip, #0x60E8
    movt    ip, #0xC036
    blx     ip
    ldr_addr r0, FILE_OBJECT
    movw    ip, #0x6020
    movt    ip, #0xC036
    blx     ip
    ldr_addr r0, FILE_OBJECT
    mov     r1, #2
    movw    ip, #0x5ED0
    movt    ip, #0xC036
    blx     ip

    /* Second pass: build the Gyroflow text and drop it beside the .GYR, so the card
     * comes out with a file that opens directly -- no host conversion step. */
    bl      build_gcsv
    ldr_addr r0, STATE_GCSVLEN
    ldr     r0, [r0]
    cmp     r0, #0
    beq     return_original
    movw    ip, #0x4658
    movt    ip, #0xC044
    blx     ip
    mov     r1, #0
    movw    ip, #0x4698
    movt    ip, #0xC044
    blx     ip
    mov     r1, r0
    ldr_addr r0, FILE_OBJECT
    movw    ip, #0x5E90
    movt    ip, #0xC036
    blx     ip
    ldr_addr r0, FILE_OBJECT
    ldr_addr r1, GCSV_PATH
    movw    r2, #0x0402
    movw    ip, #0x5FB0
    movt    ip, #0xC036
    blx     ip
    ldr_addr r0, FILE_OBJECT
    ldr_addr r1, USER_BASE
    ldr_addr r2, STATE_COUNT
    ldr     r2, [r2]
    add     r1, r1, r2
    add     r1, r1, #3
    bic     r1, r1, #3               /* text begins word-aligned after the GYR */
    ldr_addr r2, STATE_GCSVLEN
    ldr     r2, [r2]
    movw    ip, #0x60E8
    movt    ip, #0xC036
    blx     ip
    ldr_addr r0, FILE_OBJECT
    movw    ip, #0x6020
    movt    ip, #0xC036
    blx     ip
    ldr_addr r0, FILE_OBJECT
    mov     r1, #2
    movw    ip, #0x5ED0
    movt    ip, #0xC036
    blx     ip

return_original:
    mov     r0, r11
    pop     {r3-r11, pc}

/* Copy bytes [r0,r1) into USER_BASE + *STATE_COUNT. r7 must point to STATE_COUNT. */
copy_span:
    ldr     r2, [r7]
    ldr_addr r3, USER_BASE
    add     r3, r3, r2
    ldr_addr ip, USER_END
1:
    cmp     r0, r1
    beq     2f
    cmp     r3, ip
    bhs     2f
    ldrb    r2, [r0], #1
    strb    r2, [r3], #1
    b       1b
2:
    ldr_addr r2, USER_BASE
    sub     r3, r3, r2
    str     r3, [r7]
    bx      lr

/* Store value 0..999 as exactly three ASCII digits. r0=dst, r1=value. */
put_decimal_3:
    mov     r2, #'0'
3:
    cmp     r1, #100
    blo     4f
    sub     r1, r1, #100
    add     r2, r2, #1
    b       3b
4:
    strb    r2, [r0], #1
    mov     r2, #'0'
5:
    cmp     r1, #10
    blo     6f
    sub     r1, r1, #10
    add     r2, r2, #1
    b       5b
6:
    strb    r2, [r0], #1
    add     r1, r1, #'0'
    strb    r1, [r0]
    bx      lr


/*
 * accel_init -- one-shot MMA8452Q rate change, mirroring the lock discipline in
 * IMUDevInterface_MMA8452Q__v3 so it cannot collide with the firmware's own reads.
 *   CTRL_REG2 = 0x02  clear SLPE (no auto-sleep), MODS = high resolution
 *   CTRL_REG1 = 0x1C  standby first -- DR bits are not writable while active
 *   CTRL_REG1 = 0x1D  same, ACTIVE -- DR = 100 Hz, LNOISE on
 * Frame: sp+0/4 = stack args 5 and 6, sp+16 = lock guard, sp+24 = value byte.
 */
accel_init:
    push    {r4-r7, lr}
    sub     sp, sp, #32
    ldr_addr r5, ACCEL_IFACE
    add     r0, sp, #16
    ldr     r1, [r5]
    ldr_addr ip, FN_LOCK
    blx     ip
    ldr     r6, [r5, #8]             /* I2C bus object */
    ldr     r0, [r6, #0x18]
    ldr     r7, [r0, #0x0c]          /* bus write entry */
    mov     r4, #0x02
    mov     r5, #0x2B
    bl      accel_write
    mov     r4, #0x1C
    mov     r5, #0x2A
    bl      accel_write
    mov     r4, #0x1D
    mov     r5, #0x2A
    bl      accel_write
    add     r0, sp, #16
    mov     r1, #2
    ldr_addr ip, FN_UNLOCK
    blx     ip
    add     sp, sp, #32
    pop     {r4-r7, pc}

/*
 * accel_write -- r5 = register, r4 = value, r6 = bus, r7 = entry.
 * The bus entry takes six arguments, so five and six arrive on the stack at the
 * sp in effect at the call. This frame therefore has to be owned here rather than
 * borrowed from the caller: writing them into the caller's frame would land on our
 * own saved lr and return into nowhere.
 */
accel_write:
    push    {r4, lr}
    sub     sp, sp, #16              /* sp+0/4 = args five and six, sp+8 = value */
    strb    r4, [sp, #8]
    mov     r0, #1
    str     r0, [sp, #0]
    mov     r0, #0
    str     r0, [sp, #4]
    mov     r0, r6
    mov     r1, r5
    mov     r2, #1
    add     r3, sp, #8
    blx     r7
    add     sp, sp, #16
    pop     {r4, pc}

/* ---------------------------------------------------------------------------
 * On-camera GCSV writer.
 *
 * Why on camera: a .gcsv is plain text whose columns are all raw integers -- the
 * scale factors live in the header -- so nothing here needs floating point, just
 * integer-to-ASCII. That means the card can carry a file Gyroflow opens directly,
 * with no host step at all, which is the whole point for anyone who just wants to
 * shoot and stabilise.
 *
 * Layout: the GYR bytes already sit at USER_BASE for STATE_COUNT bytes. The text is
 * built immediately after them, so both live in the same 8 MiB user block. A 43 s
 * take is ~914 KiB of GYR and ~3.2 MiB of text, well inside it.
 *
 * emit_u32 / emit_i32 divide by ten using the 0xCCCCCCCD reciprocal rather than a
 * divide instruction, so this does not depend on the core having one.
 * --------------------------------------------------------------------------- */

/* r0 = value (unsigned), r1 = dest. Returns r0 = dest advanced past the digits. */
emit_u32:
    push    {r4-r7, lr}
    mov     r4, r1
    mov     r5, #0                   /* digit count */
    sub     sp, sp, #16
    mov     r6, sp
1:
    ldr     r7, =0xCCCCCCCD
    umull   r2, r3, r0, r7
    lsr     r3, r3, #3               /* r3 = value / 10 */
    add     r2, r3, r3, lsl #2
    sub     r2, r0, r2, lsl #1       /* r2 = value - 10*(value/10) */
    add     r2, r2, #'0'
    strb    r2, [r6], #1
    add     r5, r5, #1
    movs    r0, r3
    bne     1b
2:                                    /* reverse into the destination */
    sub     r6, r6, #1
    ldrb    r2, [r6]
    strb    r2, [r4], #1
    subs    r5, r5, #1
    bne     2b
    add     sp, sp, #16
    mov     r0, r4
    pop     {r4-r7, pc}

/* r0 = value (signed), r1 = dest. Returns r0 = dest advanced. */
emit_i32:
    push    {lr}
    cmp     r0, #0
    bge     1f
    mov     r2, #'-'
    strb    r2, [r1], #1
    rsb     r0, r0, #0
1:
    bl      emit_u32
    pop     {pc}

/* r0 = source string (NUL terminated), r1 = dest. Returns r0 = dest advanced. */
emit_str:
    ldrb    r2, [r0], #1
    cmp     r2, #0
    beq     1f
    strb    r2, [r1], #1
    b       emit_str
1:
    mov     r0, r1
    bx      lr

/* r0 = numerator, r1 = denominator -> r0 = quotient. Shift-and-subtract, so this
 * does not assume the core has a divide instruction. */
udiv32:
    cmp     r1, #0
    moveq   r0, #0
    bxeq    lr
    mov     r2, #0
    mov     r3, #1
1:  cmp     r1, r0
    lslls   r1, r1, #1
    lslls   r3, r3, #1
    bls     1b
2:  cmp     r0, r1
    subhs   r0, r0, r1
    orrhs   r2, r2, r3
    lsrs    r3, r3, #1
    lsr     r1, r1, #1
    bne     2b
    mov     r0, r2
    bx      lr

/*
 * build_gcsv -- turn the captured GYR bytes into Gyroflow text, in place.
 *
 * Reads the GYR image at USER_BASE (STATE_COUNT bytes) and appends the .gcsv text
 * straight after it, recording the text length in STATE_GCSVLEN. Timestamps are
 * reconstructed exactly as the host decoder does: each batch carries the TickTimer
 * reading from when it was drained, and its samples are spaced backwards from that
 * at one sample period, with a clamp so the sequence never goes backwards.
 */
build_gcsv:
    push    {r4-r11, lr}
    ldr_addr r0, USER_BASE
    mov     r4, r0
    ldr_addr r0, STATE_COUNT
    ldr     r5, [r0]
    add     r6, r4, r5
    add     r6, r6, #3
    bic     r6, r6, #3               /* text starts word-aligned after the GYR */
    mov     r10, r6

    /* Header, with the clip name lifted out of the .GYR path. */
    adr     r0, gcsv_head_a
    mov     r1, r6
    bl      emit_str
    mov     r6, r0
    ldr_addr r7, FILE_PATH
    add     r7, r7, #1               /* skip the leading backslash */
1:  ldrb    r2, [r7], #1
    cmp     r2, #'.'
    beq     2f
    cmp     r2, #0
    beq     2f
    strb    r2, [r6], #1
    b       1b
2:  adr     r0, gcsv_head_b
    mov     r1, r6
    bl      emit_str
    mov     r6, r0

    /* Sample period: the header field holds the rate in Hz when it is >= 1000. */
    ldr     r0, [r4, #8]
    mov     r8, r0
    movw    r1, #1000
    cmp     r0, r1
    blo     3f
    movw    r0, #0x4240
    movt    r0, #0x000F              /* 1000000 */
    mov     r1, r8
    bl      udiv32
    mov     r8, r0
3:  ldr     r11, [r4, #12]           /* start_us */
    mov     r9, #-1                  /* last emitted timestamp */
    add     r7, r4, #48              /* first batch */
    add     r5, r4, r5               /* end of GYR image */

batch_loop:
    add     r0, r7, #24
    cmp     r0, r5
    bhi     gcsv_done
    ldr     r0, [r7]
    movw    r1, #0x4647
    movt    r1, #0x3254              /* 'GFT2' */
    cmp     r0, r1
    bne     gcsv_done
    ldr     r0, [r7, #4]
    sub     r0, r0, r11              /* batch_end, wrapping is fine */
    ldr     r1, [r7, #8]             /* sample count */
    sub     r2, r1, #1
    mul     r2, r2, r8
    sub     r0, r0, r2               /* timestamp of the first sample */
    add     r3, r7, #24              /* sample pointer */
    /* One push, so the offsets below stay put. Pushing r3 separately afterwards
     * shifts the first two down a slot and every [sp,#n] here reads the wrong
     * field -- a timestamp gets dereferenced as a pointer. */
    push    {r0, r1, r3}             /* [sp]=t, [sp+4]=remaining, [sp+8]=sample ptr */

sample_loop:
    /* Fail closed at the end of the 8 MiB block, the way drain_ring already does.
     * The text runs about four times the size of the binary it is built from, so
     * GYR + text stops fitting somewhere past a minute of recording; without this
     * check the emitter simply kept writing past USER_END and on into memory that
     * is not ours -- a 98 s take overran the block by 2.1 MB. Abandoning the CSV outright beats truncating
     * it: the .GYR is already safely on the card and the host decoder rebuilds the
     * exact same rows from it, whereas a short CSV looks complete and is not. */
    ldr_addr r0, USER_END
    sub     r0, r0, #128
    cmp     r6, r0
    bhs     gcsv_overflow
    ldr     r0, [sp, #4]
    cmp     r0, #0
    ble     batch_end
    ldr     r0, [sp, #0]
    cmp     r0, r9
    movle   r0, r9
    addle   r0, r0, #1               /* never let time run backwards */
    mov     r9, r0
    mov     r1, r6
    bl      emit_i32
    mov     r6, r0
    ldr     r3, [sp, #8]
    mov     r0, #0                   /* four gyro/accel groups follow */
    bl      emit_row_tail
    mov     r6, r0
    ldr     r0, [sp, #8]
    add     r0, r0, #8
    str     r0, [sp, #8]
    ldr     r0, [sp, #0]
    add     r0, r0, r8
    str     r0, [sp, #0]
    ldr     r0, [sp, #4]
    sub     r0, r0, #1
    str     r0, [sp, #4]
    b       sample_loop

batch_end:
    add     sp, sp, #12
    ldr     r0, [r7, #8]
    add     r7, r7, #24
    add     r7, r7, r0, lsl #3
    b       batch_loop

gcsv_overflow:
    add     sp, sp, #12
    mov     r0, #0
    ldr_addr r1, STATE_GCSVLEN
    str     r0, [r1]
    pop     {r4-r11, pc}

gcsv_done:
    sub     r0, r6, r10
    ldr_addr r1, STATE_GCSVLEN
    str     r0, [r1]
    pop     {r4-r11, pc}

/* Emit ",gx,gy,gz,ax,ay,az\n". r3 = sample pointer, r6 = text pointer, r7 = batch. */
emit_row_tail:
    push    {r4-r6, lr}
    mov     r4, r3
    mov     r5, r6
    mov     r6, #0
1:  mov     r0, #','
    strb    r0, [r5], #1
    cmp     r6, #3
    bge     2f
    add     r0, r6, r6
    ldrsh   r0, [r4, r0]
    cmp     r6, #2
    ldrshge r0, [r4, #6]             /* layout is x, y, pad, z */
    b       3f
2:  sub     r0, r6, #3
    add     r0, r0, r0
    add     r1, r7, #16
    ldrsh   r0, [r1, r0]
3:  mov     r1, r5
    bl      emit_i32
    mov     r5, r0
    add     r6, r6, #1
    cmp     r6, #6
    blt     1b
    mov     r0, #10
    strb    r0, [r5], #1
    mov     r0, r5
    pop     {r4-r6, pc}

gcsv_head_a:
    .asciz "GYROFLOW IMU LOG\nversion,1.3\nid,sigma_fp_v502_internal_icm20321\norientation,xyz\nfwversion,SIGMA fp 5.02\nvideofilename,"
.align 2
gcsv_head_b:
    .asciz "\ntscale,0.000001\ngscale,0.000137923\nascale,0.0009765625\nt,gx,gy,gz,ax,ay,az\n"
.align 2
