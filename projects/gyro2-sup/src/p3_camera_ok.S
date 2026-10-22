/* Gyro2, stages P1-P3: each CinemaDNG frame carries its own gyro samples,
 * the level (accelerometer) readings between them, and on a take's first
 * frame the sensor mode's readout and window and the lens's correction table.
 *
 * A loader v3 sup (projects/usb-shell-sup/notes/LOADER_V3.md).  The firmware
 * serializes a take's DNG header once into a template, and for every frame,
 * on the RAW-complete event in the MovRec task, patches the template and DMAs
 * it in front of the frame's RAW:
 *
 *     C038C778  add  r0, sp, #0x1c        r0 = { src template, dst, len, flags }
 *     C038C77C  blx  #0xC00FBB90           the DMA copy               <- here
 *
 * The hook writes an FSG2 block (payload kind 2) into the template's MakerNote
 * tag-0x0200 zero tail, and the firmware's own copy carries it into the frame
 * -- before XC_StillCreateFile__v2 and before the lossless sup sees the frame.
 * Proven on the camera by stage P0 (GYRO2_CAMERA_DESIGN.md section 12.5).
 *
 * Block, at tail start + GAP (layout: the plugin's common/src/fsg2.rs):
 *     +0   'FSG2'        written last: the commit
 *     +4   u8 1, u8 2    version, payload kind 2;  +6 u16 0
 *     +8   u32 len       the payload's length
 *     +12  payload       48-byte header, then n x i16 x, y, z
 *     +12+len  CRC-32 of bytes 0 .. 12+len (the magic included)
 *
 * Time is never stored.  A sample's time is its index from the start of the
 * take times the sample period; base_idx is the first sample's index and
 * frame_mark is where the hook fell, after the block's last sample.
 *
 * Gyro: the coprocessor's ring, as fpSup gyro/gyro_drain.S reads it (proven
 * bit-exact against the gcsv logger): ring = [[0xC31E3FCC] + 0x60]; [ring] - ring
 * is the byte offset of the next record, records are 8 bytes {x, y, pad, z}
 * from ring + 4, 600 of them (240 ms).  The frame interval is at most ~111 ms
 * (9 fps), so reading it once per frame keeps up; a gap over LOST_US marks the
 * block lost because the ring has gone round.
 *
 * Register contract at the site (verified): r4 = DataPool, r5 = request,
 * r6 = tag manager; the callee takes r0 only.  The hook keeps r0 and r4-r11
 * and tail-calls what the site branched to before it (chain_next).
 *
 * Position-independent: adr and pc-relative only.  Header bytes are read
 * with ldrb (TIFF entries are 2 mod 4). */
.syntax unified
.arm
.text

.equ SVC_BOOT_ID,  4
.equ SVC_CLAIM,    8
.equ SVC_CHAIN,    16
.equ SVC_CAVE,     20
.equ SVC_PUBLISH,  24
.equ SL_CHAIN,     1

.equ SITE,         0xC038C77C
.equ F_TICK,       0xC002B6E0
.equ O_TAG_COUNT,  0x174              /* tag manager: +1 per frame (3 = first) */

.equ GYRO_DESC_PTR, 0xC31E3FCC         /* -> P; P+0x60 -> the ring              */
.equ GYRO_SPAN,    0x12C0             /* 600 records of eight bytes            */
.equ BACKFILL,     250                /* records before the first frame (100 ms) */
.equ LOST_US,      220000             /* longer than this between frames: the
                                         ring (240 ms) may have gone round      */
.equ NEW_TAKE_US,  500000             /* a pause this long starts a new take   */

.equ MAGIC,        0x32475346         /* 'FSG2'                                */
.equ GAP,          64                 /* clear of the vendor's last byte       */
.equ CHECK,        64                 /* bytes region_ok inspects              */
.equ FRAME_BYTES,  64                 /* outer 12 + payload header 48 + CRC 4  */
.equ LINE,         32                 /* Cortex-A9 D-cache line                */

.equ PERIOD_PS,    400085400          /* 2499.466 Hz, measured (Gyro1)         */
.equ GSCALE_BITS,  0x39109F6C         /* 0.000137923 rad/s per count (Gyro1)   */
.equ ASCALE_BITS,  0x3A800000         /* 0.0009765625 g per count              */

.equ F_LOST,       1
.equ F_TRUNC,      2
.equ F_FIRST,      4
.equ F_LENS,       0x40

/* P2: the level.  The MMA8452Q driver publishes x, y, z at 0xC377790C and
 * releases its lock; 0xC050D4C8 is the first instruction after (fpSup
 * gyro/accel_hook.S): r4 points at the three values, lr is dead. */
.equ ACCEL_SITE,   0xC050D4C8
.equ QSLOTS,       32                 /* events between two frames: ~100 Hz    */
.equ QBYTES,       20                 /* seq, tick, ring offset, x, y, z, pad  */
.equ EV_MAX,       16                 /* per block                             */
.equ EV_RESERVE,   (EV_MAX * 10)      /* pos u16, type, len, 3 x i16           */
.equ EVENT_LEVEL,  1

/* P3: the take's sensor mode (fpSup gyro/gcsv_json.S, profilegen.S). */
.equ SENSOR_MODE_FN, 0xC032C720       /* () -> the running mode, 0 = none      */
.equ MODE_OBJ,     0xC343B588
.equ F_TIMING,     0xC0320FC8         /* (obj, mode) -> +4 hmax (u16)          */
.equ F_GEOM,       0xC0321028         /* (obj, mode) -> +4 w, +8 lines, +0x44 binH, +0x48 binV */
.equ SENSOR_W,     6000
.equ SENSOR_H,     4000
.equ LENS_FOCAL,   0xC307CDF0         /* u32, tenths of a mm                   */
.equ LENS_AXIS,    0xC307CE2C         /* 5 x u32                               */
.equ LENS_NODES,   0xC307D270         /* 5 x 3 x 4 f64                         */
.equ LENS_BYTES,   504
.equ LENS_SAMPLES, 84                 /* the table's room, in samples (504/6)  */

/* adr reaches about 1 KB; this reaches anywhere in the file, still
 * position-independent: a same-section difference is a constant. */
.macro ADRF reg, label
    ldr     \reg, .Llit\@
    add     \reg, pc, \reg
    b       .Lend\@
.Llit\@: .word \label - .Llit\@
.Lend\@:
.endm

/* vars: words in this file, zero at load */
.equ V_SVC,    0
.equ V_BOOT,   4
.equ V_NEXT,   8
.equ V_SRC,    12
.equ V_WOFF,   16                     /* block offset in the template, 0 = none */
.equ V_TOFF,   20
.equ V_TLEN,   24
.equ V_FRAMES, 28                     /* blocks written this take              */
.equ V_CALLS,  32
.equ V_SKIPS,  36
.equ V_LCOUNT, 40                     /* the tag counter at the last frame     */
.equ V_LTICK,  44                     /* TickTimer at the last frame           */
.equ V_NOW,    48
.equ V_CLIP,   52                     /* TickTimer at the take's first frame   */
.equ V_GHEAD,  56                     /* ring offset consumed up to; -1 = take start */
.equ V_GIDX,   60                     /* global index of the next sample       */
.equ V_MAXN,   64                     /* samples the tail can hold             */
.equ V_LOSTS,  68
.equ V_DT,     72
.equ V_ANEXT,  76                     /* the accel site's layer below, 0 = none */
.equ V_QW,     80                     /* events written (accel task)            */
.equ V_QR,     84                     /* events taken (MovRec task)             */
.equ V_ST,     88                     /* this block's first ring offset, before truncation */
.equ V_N0,     92                     /* and its record count                   */
.equ V_DROP,   96                     /* records truncation dropped from its front */
.equ V_RO,     100                    /* readout, ns                            */
.equ V_MODE,   104
.equ V_CXY,    108                    /* crop x | y << 16                       */
.equ V_CWH,    112                    /* crop w | h << 16                       */
.equ V_WANTLENS, 116
.equ VARS_BYTES, 120

/* ------------------------------------------------------------------ entry */
/* r0 = block, r1 = service table.  Returns 0 = KEEP, 1 = RELEASE.
 * Claim, learn the layer below, get a veneer -- and only then write. */
entry:
    push    {r4, r5, r6, r7, r8, lr}
    mov     r5, r1
    adr     r6, vars
    str     r5, [r6, #V_SVC]
    ldr     r0, [r5, #SVC_BOOT_ID]
    str     r0, [r6, #V_BOOT]

    mov     r0, #SL_CHAIN               @ claim(svc, SITE, 4, stock, CHAIN)
    sub     sp, sp, #8
    str     r0, [sp]
    mov     r0, r5
    ldr     r1, =SITE
    mov     r2, #4
    adr     r3, site_stock
    ldr     ip, [r5, #SVC_CLAIM]
    blx     ip
    add     sp, sp, #8
    cmp     r0, #0
    bne     9f

    mov     r0, #SL_CHAIN               @ claim(svc, ACCEL_SITE, 4, stock, CHAIN)
    sub     sp, sp, #8
    str     r0, [sp]
    mov     r0, r5
    ldr     r1, =ACCEL_SITE
    mov     r2, #4
    adr     r3, accel_stock
    ldr     ip, [r5, #SVC_CLAIM]
    blx     ip
    add     sp, sp, #8
    cmp     r0, #0
    bne     9f

    mov     r0, r5                      @ what the header site branches to now
    ldr     r1, =SITE
    mov     r2, #0
    ldr     ip, [r5, #SVC_CHAIN]
    blx     ip
    cmp     r0, #0
    beq     9f
    str     r0, [r6, #V_NEXT]
    mov     r0, r5                      @ the accel site: 0 = we replay mov r2, #0
    ldr     r1, =ACCEL_SITE
    mov     r2, #0
    ldr     ip, [r5, #SVC_CHAIN]
    blx     ip
    str     r0, [r6, #V_ANEXT]

    mov     r0, r5
    mov     r1, #16
    ldr     ip, [r5, #SVC_CAVE]
    blx     ip
    cmp     r0, #0
    beq     9f
    mov     r7, r0                      @ two veneers: ldr pc, [pc, #-4]; .word x
    ldr     r1, =0xE51FF004
    str     r1, [r7]
    str     r1, [r7, #8]
    adr     r1, hook
    str     r1, [r7, #4]
    ADRF    r1, accel_hook
    str     r1, [r7, #12]

    ldr     r2, =SITE                   @ each site: bl its veneer
    mov     r0, r7
    bl      put_bl
    ldr     r2, =ACCEL_SITE
    add     r0, r7, #8
    bl      put_bl

    mov     r0, r5
    ldr     ip, [r5, #SVC_PUBLISH]
    blx     ip
    mov     r0, #0                      @ SL_KEEP
    pop     {r4, r5, r6, r7, r8, pc}
9:  mov     r0, #1                      @ SL_RELEASE: nothing was written
    pop     {r4, r5, r6, r7, r8, pc}

/* put_bl: r2 = site, r0 = target.  Writes an ARM BL.  Clobbers r1. */
put_bl:
    sub     r1, r0, r2
    sub     r1, r1, #8
    asr     r1, r1, #2
    bic     r1, r1, #0xFF000000
    orr     r1, r1, #0xEB000000
    str     r1, [r2]
    bx      lr

/* Data sits between entry and hook so every adr stays within reach (an ARM
 * adr encodes a rotated 8-bit immediate: any word distance under 1 KB). */
.align 2
site_stock: .word 0xFAF5BD03          @ blx #0xC00FBB90, from the image
accel_stock: .word 0xE3A02000         @ mov r2, #0, from the image
magic_word: .word MAGIC               @ the CRC runs over it before it is stored
vars:       .space VARS_BYTES

/* ------------------------------------------------------------------- hook */
/* In place of the DMA call.  r0 = the copy descriptor. */
hook:
    push    {r0, r4, r5, r6, r7, r8, r9, r10, r11, lr}
    mov     r9, r6                      @ tag manager
    adr     r10, vars
    ldr     r4, [r0]                    @ src: the template
    ldr     r11, [r0, #8]               @ len
    ldr     r1, [r10, #V_CALLS]
    add     r1, r1, #1
    str     r1, [r10, #V_CALLS]
    ldr     r7, [r9, #O_TAG_COUNT]

    ldr     ip, =F_TICK
    blx     ip
    str     r0, [r10, #V_NOW]
    ldr     r1, [r10, #V_LTICK]
    str     r0, [r10, #V_LTICK]
    sub     r6, r0, r1                  @ microseconds since the last frame
    str     r6, [r10, #V_DT]
    ldr     r3, [r10, #V_LCOUNT]
    str     r7, [r10, #V_LCOUNT]
    add     r3, r3, #1

    /* A new take: the tag counter is not last + 1 (on the camera it runs on
     * by one per frame and restarts at 3 each take), or a long pause. */
    mov     r8, #0
    cmp     r7, r3
    movne   r8, #1
    ldr     r1, =NEW_TAKE_US
    cmp     r6, r1
    movhi   r8, #1
    cmp     r8, #0
    beq     10f
    mov     r1, #0
    str     r1, [r10, #V_FRAMES]
    str     r1, [r10, #V_GIDX]
    mvn     r1, #0
    str     r1, [r10, #V_GHEAD]
    ldr     r1, [r10, #V_NOW]
    str     r1, [r10, #V_CLIP]
    ldr     r1, [r10, #V_QW]            @ level readings from before the take: drop
    str     r1, [r10, #V_QR]
    mov     r1, #1
    str     r1, [r10, #V_WANTLENS]
    bl      mode_info

10: /* Parse the template again on a new take, a new template, or when the
     * place is not ours any more. */
    cmp     r8, #0
    bne     20f
    ldr     r1, [r10, #V_SRC]
    cmp     r1, r4
    bne     20f
    ldr     r1, [r10, #V_WOFF]
    cmp     r1, #0
    beq     20f
    add     r2, r4, r1
    bl      region_ok
    cmp     r0, #0
    bne     30f

20: /* Our own block from before must not count as vendor data, or the tail
     * would start after it: clear it first (only if the magic says it is ours). */
    ldr     r1, [r10, #V_SRC]
    cmp     r1, r4
    bne     21f
    ldr     r1, [r10, #V_WOFF]
    cmp     r1, #0
    beq     21f
    add     r2, r4, r1
    ldr     r0, [r2]
    ldr     r3, =MAGIC
    cmp     r0, r3
    bne     21f
    ldr     r3, [r2, #8]                @ payload length
    ldr     r0, [r10, #V_TLEN]
    add     r3, r3, #19                 @ + 12 + 4, rounded up to words
    bic     r3, r3, #3
    cmp     r3, r0                      @ never past the tail it was given
    movhi   r3, r0
    mov     r0, #0
22: subs    r3, r3, #4
    strge   r0, [r2, r3]
    bgt     22b
21: mov     r0, r4
    mov     r1, r11
    bl      find_tail                   @ r0 = tail offset or 0, r1 = length
    str     r4, [r10, #V_SRC]
    mov     r2, #0
    str     r2, [r10, #V_WOFF]
    cmp     r0, #0
    beq     30f
    subs    r2, r1, #(GAP + FRAME_BYTES + EV_RESERVE)
    bls     30f                         @ not even an empty block fits
    str     r0, [r10, #V_TOFF]
    str     r1, [r10, #V_TLEN]
    ldr     r3, =0xAAAAAAAB             @ samples that fit: room / 6
    umull   r1, r3, r2, r3
    lsr     r3, r3, #2
    str     r3, [r10, #V_MAXN]
    add     r0, r0, #GAP
    add     r2, r4, r0
    mov     r5, r0
    bl      region_ok                   @ a fresh tail is zero; check anyway
    cmp     r0, #0
    strne   r5, [r10, #V_WOFF]

30: /* Take the ring's new records.  r6 = count, r7 = first offset, r8 = ring,
     * r5 = flags.  The records are consumed whether or not a block can be
     * written, so sample indices stay true across a skipped frame. */
    bl      ring_take
    mov     r6, r0
    mov     r7, r1
    mov     r8, r2
    mov     r5, r3                      @ F_LOST when the ring could not be read
    str     r0, [r10, #V_N0]
    str     r1, [r10, #V_ST]
    mov     r0, #0
    str     r0, [r10, #V_DROP]
    ldr     r0, [r10, #V_DT]
    ldr     r1, =LOST_US
    ldr     r2, [r10, #V_FRAMES]
    cmp     r2, #0                      @ the first block's gap is the pause
    cmphi   r0, r1
    orrhi   r5, r5, #F_LOST
    ldr     r9, [r10, #V_GIDX]          @ the first new record's index
    add     r0, r9, r6
    str     r0, [r10, #V_GIDX]

    ldr     r0, [r10, #V_WOFF]
    cmp     r0, #0
    bne     40f
    ldr     r0, [r10, #V_SKIPS]         @ no place this frame
    add     r0, r0, #1
    str     r0, [r10, #V_SKIPS]
    b       90f

40: tst     r5, #F_LOST
    ldrne   r0, [r10, #V_LOSTS]
    addne   r0, r0, #1
    strne   r0, [r10, #V_LOSTS]
    ldr     r1, [r10, #V_MAXN]          @ keep the newest that fit
    ldr     r0, [r10, #V_WANTLENS]
    cmp     r0, #0
    subne   r1, r1, #LENS_SAMPLES
    subs    r2, r6, r1
    bls     41f
    str     r2, [r10, #V_DROP]
    orr     r5, r5, #F_TRUNC
    mov     r6, r1
    add     r9, r9, r2
    add     r7, r7, r2, lsl #3
    ldr     r3, =GYRO_SPAN
    cmp     r7, r3
    subhs   r7, r7, r3
41: ldr     r0, [r10, #V_FRAMES]
    add     r0, r0, #1
    str     r0, [r10, #V_FRAMES]
    cmp     r0, #1
    orreq   r5, r5, #F_FIRST

    /* r11 = the block; the payload header at r11 + 12 */
    ldr     r0, [r10, #V_WOFF]
    add     r11, r4, r0
    mov     r0, #1                      @ version, kind 2, reserved
    orr     r0, r0, #0x200
    str     r0, [r11, #4]
    mov     r0, #1                      @ fmt_version 1, orientation 0, flags
    orr     r0, r0, r5, lsl #16
    str     r0, [r11, #12]
    ldr     r0, [r10, #V_CLIP]
    str     r0, [r11, #16]
    ldr     r0, [r10, #V_FRAMES]
    sub     r0, r0, #1                  @ frame_seq, from 0
    str     r0, [r11, #20]
    ldr     r0, =PERIOD_PS
    str     r0, [r11, #24]
    ldr     r0, =GSCALE_BITS
    str     r0, [r11, #28]
    ldr     r0, =ASCALE_BITS
    str     r0, [r11, #32]
    ldr     r0, [r10, #V_RO]            @ readout ns
    str     r0, [r11, #36]
    ldr     r0, [r10, #V_MODE]          @ mode | crop_x << 16
    ldr     r1, [r10, #V_CXY]
    orr     r0, r0, r1, lsl #16
    str     r0, [r11, #40]
    lsr     r0, r1, #16                 @ crop_y | crop_w << 16
    ldr     r1, [r10, #V_CWH]
    orr     r0, r0, r1, lsl #16
    str     r0, [r11, #44]
    lsr     r0, r1, #16                 @ crop_h | frame_mark = n << 16
    orr     r0, r0, r6, lsl #16
    str     r0, [r11, #48]
    str     r9, [r11, #52]              @ base_idx
    str     r6, [r11, #56]              @ n_samples, n_events 0

    add     r1, r11, #60                @ the samples
    mov     r2, r6
    add     r3, r8, #4                  @ the ring's first record
    add     r7, r3, r7                  @ this block's first record
    ldr     r0, =GYRO_SPAN
    add     ip, r3, r0                  @ one past the ring's last record
50: cmp     r2, #0
    beq     51f
    cmp     r7, ip
    movhs   r7, r3
    ldrh    r0, [r7]
    strh    r0, [r1]
    ldrh    r0, [r7, #2]
    strh    r0, [r1, #2]
    ldrh    r0, [r7, #6]
    strh    r0, [r1, #4]
    add     r7, r7, #8
    add     r1, r1, #6
    sub     r2, r2, #1
    b       50b

51: mov     r0, r1                      @ the level readings since the last block
    bl      put_events
    strh    r0, [r11, #58]
    ldr     r0, [r10, #V_WANTLENS]      @ a take's first block: the lens table
    cmp     r0, #0
    beq     53f
    mov     r0, #0
    str     r0, [r10, #V_WANTLENS]
    ldrh    r0, [r11, #14]
    orr     r0, r0, #F_LENS
    strh    r0, [r11, #14]
    ldr     r2, =LENS_FOCAL
    bl      copy_words_1
    ldr     r2, =LENS_AXIS
    mov     r3, #5
    bl      copy_words
    ldr     r2, =LENS_NODES
    mov     r3, #120
    bl      copy_words
53: sub     r6, r1, r11                 @ the payload's end, from the block
    sub     r0, r6, #12
    str     r0, [r11, #8]
    /* CRC over the magic (from magic_word, not yet stored) and bytes 4.. */
    mvn     r0, #0
    adr     r1, magic_word
    mov     r2, #4
    bl      crc32_update
    add     r1, r11, #4
    sub     r2, r6, #4
    bl      crc32_update
    mvn     r0, r0
    add     r1, r11, r6
    strb    r0, [r1]                    @ the CRC may sit 2 mod 4
    lsr     r0, r0, #8
    strb    r0, [r1, #1]
    lsr     r0, r0, #8
    strb    r0, [r1, #2]
    lsr     r0, r0, #8
    strb    r0, [r1, #3]
    dmb
    ldr     r0, =MAGIC                  @ the commit, last
    str     r0, [r11]
    bic     r0, r11, #(LINE - 1)        @ clean the block's lines for the DMA
    add     r1, r11, r6
    add     r1, r1, #4
52: mcr     p15, 0, r0, c7, c10, 1      @ DCCMVAC
    add     r0, r0, #LINE
    cmp     r0, r1
    blo     52b
    dsb

90: pop     {r0, r4, r5, r6, r7, r8, r9, r10, r11, lr}
    ADRF    ip, vars
    ldr     ip, [ip, #V_NEXT]
    bx      ip                          @ the layer below, with r0 and lr as given

/* ring_take: the records the coprocessor wrote since the last call.
 * Returns r0 = count, r1 = byte offset of the first (from the ring's first
 * record), r2 = ring, r3 = F_LOST when the ring cannot be read (count 0).
 * At a take's start (V_GHEAD = -1) it reaches BACKFILL records back.
 * Clobbers r0-r3, ip.  r10 = vars. */
ring_take:
    push    {r4, r5, r6, lr}
    bl      ring_head
    cmn     r0, #1
    beq     8f
    mov     r4, r0
    ldr     r5, =GYRO_SPAN
    ldr     r6, [r10, #V_GHEAD]
    str     r4, [r10, #V_GHEAD]
    cmn     r6, #1
    bne     1f
    ldr     r0, =BACKFILL               @ a take starts: reach back
    subs    r1, r4, r0, lsl #3
    addlo   r1, r1, r5
    b       9f
1:  subs    r0, r4, r6                  @ since last time, round the ring
    addlo   r0, r0, r5
    mov     r1, r6
    lsr     r0, r0, #3
9:  mov     r3, #0
    pop     {r4, r5, r6, pc}
8:  mov     r0, #0
    mov     r1, #0
    mov     r2, #0
    mov     r3, #F_LOST
    pop     {r4, r5, r6, pc}

/* ring_head: r0 = the ring's next-record offset, or -1 when the ring cannot
 * be read; r2 = the ring.  Clobbers r0-r3.  Both hooks call it. */
ring_head:
    ldr     r0, =GYRO_DESC_PTR
    ldr     r0, [r0]
    lsr     r1, r0, #22                 @ in the coprocessor's RAM, 0x2E000000..
    cmp     r1, #(0x2E000000 >> 22)
    bne     8f
    tst     r0, #3
    bne     8f
    ldr     r2, [r0, #0x60]
    lsr     r1, r2, #22
    cmp     r1, #(0x2E000000 >> 22)
    bne     8f
    tst     r2, #3
    bne     8f
    ldr     r0, [r2]
    sub     r0, r0, r2                  @ the next record's offset
    ldr     r3, =GYRO_SPAN
    cmp     r0, r3
    moveq   r0, #0                      @ at the very end: the coprocessor has
                                        @ not wrapped it yet -- the same as 0
                                        @ (fpSup gyro_drain.S accepts it too;
                                        @ seen once in 474 frames, A001_036 #404)
    bhi     8f
    tst     r0, #7
    bxeq    lr
8:  mvn     r0, #0
    bx      lr

/* accel_hook: in place of `mov r2, #0` at ACCEL_SITE.  r4 = the driver's
 * x, y, z.  Records the reading with where the gyro ring is and when, for
 * the next frame to place; then the layer below, or the displaced
 * instruction.  Runs in the driver's task: the queue's only writer. */
accel_hook:
    push    {r0, r1, r2, r3, r5, r6, ip, lr}
    ADRF    r6, vars
    bl      ring_head
    cmn     r0, #1
    beq     91f
    mov     r5, r0
    ldr     ip, =F_TICK
    blx     ip
    mov     r1, r0                      @ tick
    ldr     r2, [r6, #V_QW]
    and     r3, r2, #(QSLOTS - 1)
    ADRF    ip, queue
    add     ip, ip, r3, lsl #4
    add     ip, ip, r3, lsl #2          @ slot * 20
    mvn     r3, #0                      @ the slot is being written
    str     r3, [ip]
    dmb
    str     r1, [ip, #4]
    str     r5, [ip, #8]
    ldrh    r3, [r4]
    strh    r3, [ip, #12]
    ldrh    r3, [r4, #2]
    strh    r3, [ip, #14]
    ldrh    r3, [r4, #4]
    strh    r3, [ip, #16]
    dmb
    str     r2, [ip]                    @ the slot's sequence number: valid
    add     r2, r2, #1
    dmb
    str     r2, [r6, #V_QW]
91: pop     {r0, r1, r2, r3, r5, r6, ip, lr}
    push    {r0, r1}
    ADRF    r0, vars
    ldr     r0, [r0, #V_ANEXT]
    cmp     r0, #0
    bne     92f
    pop     {r0, r1}
    mov     r2, #0                      @ the displaced instruction
    bx      lr
92: mov     ip, r0
    pop     {r0, r1}
    bx      ip                          @ the layer below replays it

/* put_events: r0 = where events go.  Takes the level readings queued since
 * the last block whose ring offset falls inside this block's records, as
 * {pos u16, type 1, len 6, x, y, z}; pos counts the records before it from
 * base_idx.  A reading recorded after this block's ring read stays for the
 * next block; a stale one (the ring has gone round since) is dropped.
 * Returns r0 = count, r1 = where the next byte goes.  r10 = vars. */
put_events:
    push    {r4, r5, r6, r7, r8, r9, r11, lr}
    mov     r1, r0
    mov     r4, #0                      @ count
    ldr     r5, [r10, #V_QR]
    ldr     r6, [r10, #V_QW]
    sub     r0, r6, r5                  @ more than the queue holds: skip the lost
    cmp     r0, #QSLOTS
    subhi   r5, r6, #QSLOTS
    ADRF    r11, queue
1:  cmp     r5, r6
    beq     9f
    cmp     r4, #EV_MAX
    beq     9f
    and     r0, r5, #(QSLOTS - 1)
    add     r7, r11, r0, lsl #4
    add     r7, r7, r0, lsl #2
    ldr     r0, [r7]
    cmp     r0, r5
    beq     2f
    cmn     r0, #1                      @ being written right now: next block
    beq     9f
    b       8f                          @ overwritten: gone
2:  ldr     r8, [r7, #4]                @ tick
    ldr     r9, [r7, #8]                @ ring offset
    ldr     r2, [r7, #12]               @ x | y << 16
    ldrh    r3, [r7, #16]               @ z
    dmb
    ldr     r0, [r7]
    cmp     r0, r5
    bne     8f
    ldr     r0, [r10, #V_NOW]           @ stale: older than the ring's reach
    sub     r0, r0, r8
    ldr     ip, =LOST_US
    cmp     r0, ip
    bhi     8f
    ldr     r0, [r10, #V_ST]            @ records before it, from this block's start
    subs    r0, r9, r0
    ldrlo   ip, =GYRO_SPAN
    addlo   r0, r0, ip
    lsr     r0, r0, #3
    ldr     ip, [r10, #V_N0]
    cmp     r0, ip
    bls     3f
    /* Outside this block's records.  Recorded after the block's ring read
     * (its tick is not before the block's): it belongs to the next block --
     * stop.  Otherwise it is from before this block (left over by EV_MAX):
     * drop it rather than let it hold the queue up. */
    ldr     ip, [r10, #V_NOW]
    subs    ip, r8, ip
    bpl     9f
    b       8f
3:    ldr     ip, [r10, #V_DROP]
    subs    r0, r0, ip
    movlo   r0, #0                      @ before the kept records: at the start
    strh    r0, [r1]
    mov     r0, #EVENT_LEVEL
    orr     r0, r0, #0x600              @ type 1, len 6
    strh    r0, [r1, #2]
    strh    r2, [r1, #4]
    lsr     r2, r2, #16
    strh    r2, [r1, #6]
    strh    r3, [r1, #8]
    add     r1, r1, #10
    add     r4, r4, #1
8:  add     r5, r5, #1
    b       1b
9:  str     r5, [r10, #V_QR]
    mov     r0, r4
    pop     {r4, r5, r6, r7, r8, r9, r11, pc}

/* copy_words: r2 = source (word aligned), r3 = words, r1 = destination
 * (halfword aligned).  copy_words_1 copies one.  Advances r1.  Clobbers r0, r2, r3. */
copy_words_1:
    mov     r3, #1
copy_words:
1:  subs    r3, r3, #1
    bxlo    lr
    ldr     r0, [r2], #4
    strh    r0, [r1]
    lsr     r0, r0, #16
    strh    r0, [r1, #2]
    add     r1, r1, #4
    b       1b

/* mode_info: the running sensor mode's readout and window, into V_RO, V_MODE,
 * V_CXY, V_CWH; all 0 when no mode runs.  The camera's own accessors, as
 * fpSup gcsv_json.S calls them at record start.  r10 = vars. */
mode_info:
    push    {r4, r5, r6, r7, r8, lr}
    mov     r0, #0
    str     r0, [r10, #V_RO]
    str     r0, [r10, #V_MODE]
    str     r0, [r10, #V_CXY]
    str     r0, [r10, #V_CWH]
    ldr     ip, =SENSOR_MODE_FN
    blx     ip
    movs    r4, r0
    beq     9f
    lsl     r0, r4, #16                 @ a mode number fits a halfword
    lsr     r0, r0, #16
    str     r0, [r10, #V_MODE]
    ldr     r0, =MODE_OBJ
    mov     r1, r4
    ldr     ip, =F_TIMING
    blx     ip
    cmp     r0, #0
    beq     9f
    ldrh    r5, [r0, #4]                @ hmax: sensor clocks a line
    ldr     r0, =MODE_OBJ
    mov     r1, r4
    ldr     ip, =F_GEOM
    blx     ip
    cmp     r0, #0
    beq     9f
    ldr     r6, [r0, #4]                @ readout width
    ldr     r7, [r0, #8]                @ lines read
    ldr     r8, [r0, #0x44]             @ binning, horizontal
    ldr     r3, [r0, #0x48]             @ and vertical
    mul     r0, r5, r7                  @ clocks for the frame, at 72 MHz
    mov     r1, #125                    @ ns = clocks * 1000 / 72 = clocks * 125 / 9
    mul     r0, r0, r1
    add     r0, r0, #4
    ldr     r1, =0x38E38E39             @ / 9
    umull   r2, r1, r0, r1
    lsr     r1, r1, #1
    str     r1, [r10, #V_RO]
    cmp     r8, #0
    moveq   r8, #1
    cmp     r3, #0
    moveq   r3, #1
    mul     r6, r6, r8                  @ sensor columns and rows imaged
    mul     r7, r7, r3
    ldr     r1, =SENSOR_W
    cmp     r6, r1
    movhi   r6, r1
    ldr     r2, =SENSOR_H
    cmp     r7, r2
    movhi   r7, r2
    sub     r0, r1, r6                  @ centred: (6000 - w) / 2, (4000 - h) / 2
    lsr     r0, r0, #1
    sub     r1, r2, r7
    lsr     r1, r1, #1
    orr     r0, r0, r1, lsl #16
    str     r0, [r10, #V_CXY]
    orr     r0, r6, r7, lsl #16
    str     r0, [r10, #V_CWH]
9:  pop     {r4, r5, r6, r7, r8, pc}

/* crc32_update: r0 = running CRC (start ~0), r1 = bytes, r2 = count.
 * IEEE 802.3, reflected, bitwise.  Returns r0.  Clobbers r1-r3, ip. */
crc32_update:
    ldr     ip, =0xEDB88320
1:  cmp     r2, #0
    bxeq    lr
    ldrb    r3, [r1], #1
    eor     r0, r0, r3
    mov     r3, #8
2:  lsrs    r0, r0, #1
    eorcs   r0, r0, ip
    subs    r3, r3, #1
    bne     2b
    sub     r2, r2, #1
    b       1b

/* region_ok: r2 = CHECK bytes.  r0 = 1 when they are all zero or begin with
 * our magic, else 0.  Clobbers r0, r1, r3. */
region_ok:
    ldr     r0, =MAGIC
    ldr     r1, [r2]
    cmp     r1, r0
    moveq   r0, #1
    bxeq    lr
    mov     r3, #0
1:  ldr     r1, [r2, r3]
    cmp     r1, #0
    movne   r0, #0
    bxne    lr
    add     r3, r3, #4
    cmp     r3, #CHECK
    blo     1b
    mov     r0, #1
    bx      lr

/* rd16 / rd32: r0 = [r1 + r2], byte-wise little-endian.  Clobbers r3. */
rd16:
    add     r3, r1, r2
    ldrb    r0, [r3]
    ldrb    r3, [r3, #1]
    orr     r0, r0, r3, lsl #8
    bx      lr
rd32:
    push    {r4, lr}
    add     r4, r1, r2
    ldrb    r0, [r4]
    ldrb    r3, [r4, #1]
    orr     r0, r0, r3, lsl #8
    ldrb    r3, [r4, #2]
    orr     r0, r0, r3, lsl #16
    ldrb    r3, [r4, #3]
    orr     r0, r0, r3, lsl #24
    pop     {r4, pc}

/* find_entry: r1 = template, r4 = len, r5 = IFD offset (count at +0),
 * r6 = tag.  r0 = the entry's offset, or 0.  Clobbers r0, r2, r3, r7, r8. */
find_entry:
    push    {r9, lr}
    add     r2, r5, #2
    cmp     r2, r4
    bhs     8f
    mov     r2, r5
    bl      rd16
    mov     r7, r0                      @ count
    mov     r3, #12
    mla     r8, r7, r3, r5
    add     r8, r8, #2                  @ end of the entries
    cmp     r8, r4
    bhi     8f
    add     r8, r5, #2                  @ the first entry
1:  cmp     r7, #0
    beq     8f
    mov     r2, r8
    bl      rd16
    cmp     r0, r6
    moveq   r0, r8
    popeq   {r9, pc}
    add     r8, r8, #12
    sub     r7, r7, #1
    b       1b
8:  mov     r0, #0
    pop     {r9, pc}

/* find_tail: r0 = template, r1 = len.  Returns r0 = word-aligned offset of
 * the MakerNote tag 0x0200's trailing zeros, r1 = their length; r0 = 0 when
 * any step is missing or out of bounds. */
find_tail:
    push    {r4, r5, r6, r7, r8, r9, r10, r11, ip, lr}
    mov     r9, r0
    mov     r4, r1
    mov     r1, r9
    cmp     r4, #0x100
    blo     90f
    ldr     r0, [r9]
    ldr     r2, =0x002A4949             @ 'II', 42
    cmp     r0, r2
    bne     90f
    mov     r2, #4
    bl      rd32
    mov     r5, r0                      @ IFD0
    mov     r6, #0x8700
    orr     r6, r6, #0x69               @ 0x8769 Exif
    bl      find_entry
    cmp     r0, #0
    beq     90f
    add     r2, r0, #8
    bl      rd32
    mov     r5, r0                      @ Exif IFD
    mov     r6, #0x9200
    orr     r6, r6, #0x7C               @ 0x927C MakerNote
    bl      find_entry
    cmp     r0, #0
    beq     90f
    mov     r10, r0
    add     r2, r10, #2
    bl      rd16
    cmp     r0, #7                      @ UNDEFINED
    bne     90f
    add     r2, r10, #4
    bl      rd32
    mov     r11, r0                     @ MakerNote length
    add     r2, r10, #8
    bl      rd32
    mov     r10, r0                     @ MakerNote offset
    add     r0, r10, r11
    cmp     r0, r4
    bhi     90f
    cmp     r11, #12
    blo     90f
    add     r2, r9, r10                 @ 'SIGMA', 0, 0, 0
    ldrb    r0, [r2]
    cmp     r0, #'S'
    bne     90f
    ldrb    r0, [r2, #4]
    cmp     r0, #'A'
    bne     90f
    add     r5, r10, #10                @ the MakerNote IFD's count
    mov     r6, #0x200
    bl      find_entry
    cmp     r0, #0
    beq     90f
    mov     r7, r0
    add     r2, r7, #2
    bl      rd16
    cmp     r0, #7
    bne     90f
    add     r2, r7, #4
    bl      rd32
    mov     r8, r0                      @ 0x200 length
    add     r2, r7, #8
    bl      rd32                        @ 0x200 offset (from the file start)
    cmp     r0, r10
    blo     90f
    add     r8, r0, r8                  @ its end
    add     r2, r10, r11
    cmp     r8, r2                      @ inside the MakerNote
    bhi     90f
    mov     r6, r0                      @ the area's start
    mov     r2, r8                      @ walk back over the zeros
1:  cmp     r2, r6
    bls     2f
    sub     r3, r2, #1
    ldrb    r0, [r9, r3]
    cmp     r0, #0
    bne     2f
    mov     r2, r3
    b       1b
2:  add     r2, r2, #3
    bic     r0, r2, #3
    subs    r1, r8, r0
    bls     90f
    pop     {r4, r5, r6, r7, r8, r9, r10, r11, ip, pc}
90: mov     r0, #0
    mov     r1, #0
    pop     {r4, r5, r6, r7, r8, r9, r10, r11, ip, pc}

    .ltorg

.align 2
queue:      .space (QSLOTS * QBYTES)
