/* Gyro2, stages P1-P3 with the two-buffer design (GYRO2_CAMERA_DESIGN.md 13): each CinemaDNG frame carries its own gyro samples,
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
.equ AVAIL,        584                /* records the ring still holds safely: 600
                                         less the few being overwritten now      */
.equ US_PER_REC,   400                /* 400.085 us; whole us is close enough to
                                         count laps                              */
.equ LAP_US,       240051             /* 600 records                           */
.equ MAX_LAPS,     16                 /* a drain gap past this is not counted   */

/* The two buffers, in the block past the file (the loader zeroes it). */
.equ GLOG_N,       8192               /* gyro records, 6 bytes: 48 KB, 3.3 s    */
.equ GLOG_BYTES,   (GLOG_N * 6)
.equ LAG_MARGIN,   1024               /* a reader this close to being lapped: lost */
.equ ELOG_N,       256                /* level readings, 12 bytes: 5 s at 47 Hz */
.equ ELOG_BYTES,   (ELOG_N * 12)

/* snapshot(): what it hands back */
.equ S_W,      0
.equ S_DHEAD,  4
.equ S_LU,     8
.equ S_RING,   12
.equ S_MARK,   16
.equ S_FLAGS,  20
.equ S_GONE,   24                     /* records before this are in neither place */
.equ SNAP_BYTES, 32

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
.equ EV_MAX,       16                 /* per block                             */
.equ VEV_MAX,      4                  /* Vd events per block                   */
.equ EV_RESERVE,   (EV_MAX * 10 + VEV_MAX * 8)  /* level: pos, type, len, 3 x i16; Vd: pos, type, len, tick */
.equ EVENT_LEVEL,  1
.equ EVENT_VD,     3                  /* the sensor's Vd interrupt (IRQ 0x79); 2 is focus */

/* The sensor's frame sync, Vd (IRQ 0x79): once a frame, at a fixed point of
 * the readout (2026-10-07, A001_012/016: +-5 us, no double fires; it moves
 * with the readout, not with the exposure).  Each frame's time comes from
 * it.  The handler is Thumb: push.w; movw; movt.  The movt (4 bytes, word
 * aligned) becomes a BLX to our ARM code, which replays it.  Gyro1 hooked
 * the same word (GYRO_RESEARCH.md section 6). */
.equ VD_SITE,      0xC0125480         /* movt r4, #0xC31D, in FUN_c0125478     */
.equ VLOG_N,       32                 /* {position, TickTimer}                 */
.equ VLOG_BYTES,   (VLOG_N * 8)
.equ SL_EXCL,      2

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
.equ V_W,      56                     /* gyro records drained ever (global index) */
.equ V_DHEAD,  60                     /* ring offset drained up to; -1 = not yet */
.equ V_MAXN,   64                     /* samples the tail can hold             */
.equ V_LOSTS,  68                     /* blocks marked lost                    */
.equ V_LU,     72                     /* records before this index were lost   */
.equ V_ANEXT,  76                     /* the accel site's layer below, 0 = none */
.equ V_EW,     80                     /* level readings written (level task)    */
.equ V_ER,     84                     /* level readings taken (MovRec task)     */
.equ V_PREV,   88                     /* the last frame's mark (global)         */
.equ V_ORIGIN, 92                     /* the take's first record (global)       */
.equ V_SPARE,  96
.equ V_RO,     100                    /* readout, ns                            */
.equ V_MODE,   104
.equ V_CXY,    108                    /* crop x | y << 16                       */
.equ V_CWH,    112                    /* crop w | h << 16                       */
.equ V_WANTLENS, 116
.equ V_LDRAIN, 120                    /* TickTimer at the last drain            */
.equ V_SEQ,    124                    /* odd while drain() publishes            */
.equ V_PW,     128                    /* the set before that publish            */
.equ V_PDH,    132
.equ V_PLU,    136
.equ V_VW,     140                    /* Vd records written (IRQ 0x79)          */
.equ V_VR,     144                    /* Vd records taken (MovRec task)         */
.equ VARS_BYTES, 148

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
    mvn     r0, #0                      @ nothing drained yet
    str     r0, [r6, #V_DHEAD]

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

    /* Vd: sole owner (a Thumb site cannot stack), and needed: without it
     * the frames have no time. */
    mov     r0, #SL_EXCL                @ claim(svc, VD_SITE, 4, stock, EXCL)
    sub     sp, sp, #8
    str     r0, [sp]
    mov     r0, r5
    ldr     r1, =VD_SITE
    mov     r2, #4
    ADRF    r3, vd_stock
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
    mov     r1, #24                     @ three veneers
    ldr     ip, [r5, #SVC_CAVE]
    blx     ip
    cmp     r0, #0
    beq     9f
    mov     r7, r0                      @ three veneers: ldr pc, [pc, #-4]; .word x
    ldr     r1, =0xE51FF004
    str     r1, [r7]
    str     r1, [r7, #8]
    str     r1, [r7, #16]
    adr     r1, hook
    str     r1, [r7, #4]
    ADRF    r1, accel_hook
    str     r1, [r7, #12]
    ADRF    r1, vd_hook
    str     r1, [r7, #20]

    ldr     r2, =SITE                   @ each site: bl its veneer
    mov     r0, r7
    bl      put_bl
    ldr     r2, =ACCEL_SITE
    add     r0, r7, #8
    bl      put_bl
    ldr     r2, =VD_SITE                @ the Thumb site: blx to its veneer
    add     r0, r7, #16
    bl      put_blx_t

    mov     r0, r5
    ldr     ip, [r5, #SVC_PUBLISH]
    blx     ip
    mov     r0, #0                      @ SL_KEEP
    pop     {r4, r5, r6, r7, r8, pc}
9:  mov     r0, #1                      @ SL_RELEASE: nothing was written
    pop     {r4, r5, r6, r7, r8, pc}

/* put_blx_t: r2 = a word-aligned Thumb site, r0 = a word-aligned ARM target.
 * Writes a Thumb-2 BLX (T2) over the four bytes.  Clobbers r1, r3, ip. */
put_blx_t:
    push    {r4, r5}
    add     r1, r2, #4
    bic     r1, r1, #3
    sub     r1, r0, r1                  @ offset from Align(pc, 4)
    ubfx    r3, r1, #12, #10            @ imm10H
    ubfx    ip, r1, #24, #1             @ S
    orr     r3, r3, ip, lsl #10
    orr     r3, r3, #0xF000             @ first halfword: 11110 S imm10H
    ubfx    r4, r1, #23, #1             @ I1 = NOT(J1 XOR S): J1 = I1 XOR S XOR 1
    eor     r4, r4, ip
    eor     r4, r4, #1
    ubfx    r5, r1, #22, #1             @ J2 likewise from I2
    eor     r5, r5, ip
    eor     r5, r5, #1
    ubfx    r1, r1, #2, #10             @ imm10L
    lsl     r1, r1, #1                  @ H = 0
    orr     r1, r1, #0xC000             @ second halfword: 11 J1 0 J2 imm10L H
    orr     r1, r1, r4, lsl #13
    orr     r1, r1, r5, lsl #11
    orr     r3, r3, r1, lsl #16
    str     r3, [r2]
    pop     {r4, r5}
    bx      lr

/* put_bl: r2 = site, r0 = target.  Writes an ARM BL.  Clobbers r1. */
put_bl:
    sub     r1, r0, r2
    sub     r1, r1, #8
    asr     r1, r1, #2
    bic     r1, r1, #0xFF000000
    orr     r1, r1, #0xEB000000
    str     r1, [r2]
    bx      lr
    .ltorg                              @ entry's constants, within reach

/* Data sits between entry and hook so every adr stays within reach (an ARM
 * adr encodes a rotated 8-bit immediate: any word distance under 1 KB). */
.align 2
site_stock: .word 0xFAF5BD03          @ blx #0xC00FBB90, from the image
accel_stock: .word 0xE3A02000         @ mov r2, #0, from the image
vd_stock:   .word 0x341DF2CC          @ movt r4, #0xC31D (Thumb-2), from the image
magic_word: .word MAGIC               @ the CRC runs over it before it is stored
vars:       .space VARS_BYTES

/* ------------------------------------------------------------------- hook */
/* In place of the DMA call.  r0 = the copy descriptor.
 *
 * Reads only: the gyro buffer (filled by drain(), on the level's hook) and
 * the coprocessor's ring for the last few records not yet drained.  The
 * block is exactly [the last frame's mark, this frame's mark). */
hook:
    push    {r0, r4, r5, r6, r7, r8, r9, r10, r11, lr}
    sub     sp, sp, #SNAP_BYTES         @ the snapshot
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
    ldr     r3, [r10, #V_LCOUNT]
    str     r7, [r10, #V_LCOUNT]
    add     r3, r3, #1

    /* A new take: the tag counter is not last + 1.  It restarts at 3 each
     * take (measured, A001_028/029).  No pause rule: with the gyro buffer a
     * long stall inside a take loses nothing, and calling it a new take
     * would split the take (A001_041 stalled 200+ ms under lossless). */
    mov     r8, #0
    cmp     r7, r3
    movne   r8, #1
    cmp     r8, #0
    beq     10f
    mov     r1, #0
    str     r1, [r10, #V_FRAMES]
    ldr     r1, [r10, #V_NOW]
    str     r1, [r10, #V_CLIP]
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

30: /* Where the stream is now.  Only the level's hook moves gyro records
     * into the buffer; this hook reads.  If the level has gone quiet, the
     * undrained tail is read from the ring as long as the ring still holds
     * it (snapshot() marks the block lost past that). */
    mov     r0, sp
    bl      snapshot                    @ sp: W, dhead, lost_until, ring, mark, flags
    ldr     r5, [sp, #S_FLAGS]          @ F_LOST when the ring could not be read
    ldr     r6, [sp, #S_MARK]           @ r6 = this frame's mark (global)

    ldr     r7, [r10, #V_PREV]          @ r7 = this block's first record (global)
    cmp     r8, #0
    beq     31f
    ldr     r0, =BACKFILL               @ a take starts: reach back
    sub     r7, r6, r0
    str     r7, [r10, #V_ORIGIN]
31: str     r6, [r10, #V_PREV]

    /* The oldest record still good: not before a lost stretch, and not so
     * far behind the writer that the buffer may have gone round under us. */
    ldr     r0, [sp, #S_LU]
    ldr     r1, [sp, #S_W]
    ldr     r2, =(GLOG_N - LAG_MARGIN)
    sub     r1, r1, r2
    cmp     r1, r0                      @ global indices: compare as signed gaps
    movpl   r0, r1                      @ the later of the two
    ldr     r1, [sp, #S_GONE]           @ and not in the stretch the ring lost
    cmp     r1, r0
    movpl   r0, r1
    subs    r1, r7, r0
    bpl     32f
    orr     r5, r5, #F_LOST
    mov     r7, r0
    subs    r1, r6, r7                  @ nothing left at all
    movmi   r7, r6
32:
    ldr     r0, [r10, #V_WOFF]
    cmp     r0, #0
    bne     40f
    ldr     r0, [r10, #V_SKIPS]         @ no place this frame
    add     r0, r0, #1
    str     r0, [r10, #V_SKIPS]
    b       90f

40: ldr     r1, [r10, #V_MAXN]          @ keep the newest that fit
    ldr     r0, [r10, #V_WANTLENS]
    cmp     r0, #0
    subne   r1, r1, #LENS_SAMPLES
    sub     r2, r6, r7                  @ n
    subs    r2, r2, r1
    bls     41f
    orr     r5, r5, #F_TRUNC
    sub     r7, r6, r1
41: ldr     r0, [r10, #V_FRAMES]
    add     r0, r0, #1
    str     r0, [r10, #V_FRAMES]
    cmp     r0, #1
    orreq   r5, r5, #F_FIRST
    tst     r5, #F_LOST
    ldrne   r0, [r10, #V_LOSTS]
    addne   r0, r0, #1
    strne   r0, [r10, #V_LOSTS]

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
    sub     r2, r6, r7                  @ n = frame_mark: the hook is at the end
    lsr     r0, r1, #16                 @ crop_h | frame_mark << 16
    orr     r0, r0, r2, lsl #16
    str     r0, [r11, #48]
    ldr     r0, [r10, #V_ORIGIN]        @ base_idx, from the take's first record
    sub     r0, r7, r0
    str     r0, [r11, #52]
    str     r2, [r11, #56]              @ n_samples (n_events written later)

    /* The samples: [r7, r6).  Below W from the gyro buffer, from W on from
     * the coprocessor's ring at dhead. */
    add     r1, r11, #60
    ADRF    r8, gbuf
    ldr     r9, [sp, #S_W]
50: cmp     r7, r6
    beq     51f
    subs    r0, r7, r9
    bpl     52f
    ldr     r0, =(GLOG_N - 1)           @ from the buffer
    and     r0, r7, r0
    add     r0, r0, r0, lsl #1          @ x 6
    add     r0, r8, r0, lsl #1
    ldrh    r2, [r0]
    strh    r2, [r1]
    ldrh    r2, [r0, #2]
    strh    r2, [r1, #2]
    ldrh    r2, [r0, #4]
    strh    r2, [r1, #4]
    b       53f
52: ldr     r2, [sp, #S_DHEAD]          @ from the ring: dhead + 8 * (r7 - W)
    add     r0, r2, r0, lsl #3
    ldr     r2, =GYRO_SPAN
54: cmp     r0, r2
    subhs   r0, r0, r2
    bhs     54b
    ldr     r2, [sp, #S_RING]
    add     r0, r2, r0
    add     r0, r0, #4
    ldrh    r2, [r0]
    strh    r2, [r1]
    ldrh    r2, [r0, #2]
    strh    r2, [r1, #2]
    ldrh    r2, [r0, #6]
    strh    r2, [r1, #4]
53: add     r1, r1, #6
    add     r7, r7, #1
    b       50b

51: ldr     r7, [r11, #52]              @ the block's first record, again
    ldr     r0, [r10, #V_ORIGIN]
    add     r7, r7, r0
    mov     r0, r1                      @ the level readings in [r7, r6)
    mov     r2, r7
    mov     r3, r6
    bl      put_events
    strh    r0, [r11, #58]
    mov     r2, r7                      @ then the frame syncs
    mov     r3, r6
    bl      put_vd
    ldrh    r2, [r11, #58]
    add     r2, r2, r0
    strh    r2, [r11, #58]
    ldr     r0, [r10, #V_WANTLENS]      @ a take's first block: the lens table
    cmp     r0, #0
    beq     55f
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
55: sub     r6, r1, r11                 @ the payload's end, from the block
    sub     r0, r6, #12
    str     r0, [r11, #8]
    /* CRC over the magic (from magic_word, not yet stored) and bytes 4.. */
    mvn     r0, #0
    ADRF    r1, magic_word
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
56: mcr     p15, 0, r0, c7, c10, 1      @ DCCMVAC
    add     r0, r0, #LINE
    cmp     r0, r1
    blo     56b
    dsb

90: add     sp, sp, #SNAP_BYTES
    pop     {r0, r4, r5, r6, r7, r8, r9, r10, r11, lr}
    ADRF    ip, vars
    ldr     ip, [ip, #V_NEXT]
    bx      ip                          @ the layer below, with r0 and lr as given

/* drain: move the coprocessor's new records into the gyro buffer.  Called
 * only from the level's hook, so the buffer has one writer and needs no lock
 * (an LDREX/STREX lock in the block's memory froze the boot, 2026-10-06).
 * r10 = vars.  Keeps r4-r11. */
drain:
    push    {r4, r5, r6, r7, r8, r9, r11, lr}
    ldr     ip, =F_TICK
    blx     ip
    ldr     r1, [r10, #V_LDRAIN]
    str     r0, [r10, #V_LDRAIN]
    sub     r7, r0, r1                  @ microseconds since the last drain
    bl      ring_head
    cmn     r0, #1
    beq     80f
    mov     r4, r0                      @ head offset
    mov     r8, r2                      @ ring
    ldr     r6, [r10, #V_DHEAD]
    cmn     r6, #1
    bne     2f
    mov     r5, #0                      @ the first drain: start here
    mov     r9, #0
    b       70f
2:  subs    r5, r4, r6                  @ records since, modulo a lap
    ldrlo   r0, =GYRO_SPAN
    addlo   r5, r5, r0
    lsr     r5, r5, #3
    /* More than a lap since the last drain (nobody drained for 240 ms):
     * the time says how many; the indices stay true, the lost are counted. */
    mov     r3, #US_PER_REC
    mul     r3, r5, r3
    ldr     r1, =(LAP_US / 2)
    add     r3, r3, r1
    ldr     r1, =LAP_US
    mov     r11, #MAX_LAPS
3:  cmp     r7, r3
    bls     4f
    subs    r11, r11, #1                @ longer than any stall worth counting
    beq     4f
    add     r5, r5, #600
    add     r3, r3, r1
    b       3b
4:  mov     r9, #0                      @ r9 = records lost
    subs    r0, r5, #AVAIL
    movhi   r9, r0
    sub     r0, r5, r9                  @ r0 = records to copy, newest
    ldr     r11, [r10, #V_W]
    add     r11, r11, r9                @ the first copied record's index
    sub     r2, r4, r0, lsl #3          @ its ring offset
    cmp     r2, #0
    ldrlt   r1, =GYRO_SPAN
    addlt   r2, r2, r1
    add     r6, r8, #4                  @ the ring's first record
    add     r2, r6, r2
    ldr     r1, =GYRO_SPAN
    add     r3, r6, r1                  @ one past its last
    ADRF    ip, gbuf
5:  cmp     r0, #0
    beq     70f
    cmp     r2, r3
    movhs   r2, r6
    ldr     r1, =(GLOG_N - 1)
    and     r1, r11, r1
    add     r1, r1, r1, lsl #1
    add     r1, ip, r1, lsl #1
    ldrh    r7, [r2]
    strh    r7, [r1]
    ldrh    r7, [r2, #2]
    strh    r7, [r1, #2]
    ldrh    r7, [r2, #6]
    strh    r7, [r1, #4]
    add     r2, r2, #8
    add     r11, r11, #1
    sub     r0, r0, #1
    b       5b

70: /* Publish {W, dhead, lost_until} under the sequence word.  First keep
     * the current set: a reader that preempts this task while the word is odd
     * cannot wait for it, and reads the kept set instead. */
    ldr     r0, [r10, #V_W]
    str     r0, [r10, #V_PW]
    ldr     r0, [r10, #V_DHEAD]
    str     r0, [r10, #V_PDH]
    ldr     r0, [r10, #V_LU]
    str     r0, [r10, #V_PLU]
    dmb
    ldr     r0, [r10, #V_SEQ]
    add     r0, r0, #1
    str     r0, [r10, #V_SEQ]           @ odd: being written
    dmb
    ldr     r1, [r10, #V_W]
    add     r2, r1, r9
    cmp     r9, #0
    strne   r2, [r10, #V_LU]            @ everything before here is gone
    add     r1, r1, r5
    str     r1, [r10, #V_W]
    str     r4, [r10, #V_DHEAD]
    dmb
    add     r0, r0, #1
    str     r0, [r10, #V_SEQ]           @ even: consistent
80: pop     {r4, r5, r6, r7, r8, r9, r11, pc}

/* snapshot: r0 = SNAP_BYTES of room.  A consistent {W, dhead, lost_until}
 * (retried while drain() is writing them), the ring, and the mark: W plus
 * the records the ring holds that are not drained yet.  r10 = vars.
 * Keeps r4-r11. */
snapshot:
    push    {r4, r5, r6, r7, r8, lr}
    mov     r4, r0
    mov     r8, #8                      @ tries
1:  ldr     r5, [r10, #V_SEQ]
    dmb
    tst     r5, #1
    bne     2f
    ldr     r0, [r10, #V_W]
    ldr     r1, [r10, #V_DHEAD]
    ldr     r2, [r10, #V_LU]
    b       4f
2:  ldr     r0, [r10, #V_PW]            @ the writer is mid-way: its kept set
    ldr     r1, [r10, #V_PDH]
    ldr     r2, [r10, #V_PLU]
4:  dmb
    ldr     r3, [r10, #V_SEQ]
    cmp     r3, r5
    beq     3f
    subs    r8, r8, #1
    bne     1b
3:  str     r0, [r4, #S_W]
    str     r1, [r4, #S_DHEAD]
    str     r2, [r4, #S_LU]
    mov     r5, r0
    mov     r6, r1
    mov     r7, #0                      @ flags
    str     r2, [r4, #S_GONE]           @ nothing lost: no tighter than LU
    bl      ring_head
    str     r2, [r4, #S_RING]
    cmn     r0, #1
    beq     8f
    cmn     r6, #1                      @ nothing drained yet
    beq     8f
    subs    r8, r0, r6                  @ records not drained yet, modulo a lap
    ldrlo   r1, =GYRO_SPAN
    addlo   r8, r8, r1
    lsr     r8, r8, #3
    /* The level has gone quiet for more than a lap: the offsets alias.  The
     * time since its last drain says how many laps; what the ring no longer
     * holds is gone, but the mark stays at its true place. */
    ldr     ip, =F_TICK
    blx     ip
    ldr     r1, [r10, #V_LDRAIN]
    sub     r0, r0, r1                  @ microseconds since the last drain
    mov     r3, #US_PER_REC
    mul     r3, r8, r3
    ldr     r1, =(LAP_US / 2)
    add     r3, r3, r1
    ldr     r1, =LAP_US
    mov     r2, #MAX_LAPS
1:  cmp     r0, r3
    bls     2f
    subs    r2, r2, #1
    beq     2f
    add     r8, r8, #600
    add     r3, r3, r1
    b       1b
2:  subs    r0, r8, #AVAIL              @ more than the ring keeps
    bls     3f
    orr     r7, r7, #F_LOST
    add     r0, r5, r0
    str     r0, [r4, #S_GONE]           @ [W, W + n - AVAIL) is in neither place
3:  add     r0, r5, r8
    b       9f
8:  orr     r7, r7, #F_LOST
    mov     r0, r5
9:  str     r0, [r4, #S_MARK]
    str     r7, [r4, #S_FLAGS]
    pop     {r4, r5, r6, r7, r8, pc}

/* ring_head: r0 = the ring's next-record offset, or -1 when the ring cannot
 * be read; r2 = the ring.  Clobbers r0-r3. */
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
 * x, y, z.  Drains the gyro first, then records the reading at the stream's
 * position now -- its place among the gyro samples is its time.  Then the
 * layer below, or the displaced instruction.  The level buffer's only writer. */
accel_hook:
    push    {r0, r1, r2, r3, r5, r10, ip, lr}
    sub     sp, sp, #SNAP_BYTES
    ADRF    r10, vars
    bl      drain
    mov     r0, sp
    bl      snapshot
    ldr     r1, [sp, #S_FLAGS]
    tst     r1, #F_LOST                 @ no ring: no place to put it
    bne     91f
    ldr     r1, [sp, #S_MARK]
    ldr     r2, [r10, #V_EW]
    and     r3, r2, #(ELOG_N - 1)
    ADRF    ip, ebuf
    add     r3, r3, r3, lsl #1          @ x 12
    add     ip, ip, r3, lsl #2
    str     r1, [ip]                    @ position
    ldrh    r3, [r4]
    strh    r3, [ip, #4]
    ldrh    r3, [r4, #2]
    strh    r3, [ip, #6]
    ldrh    r3, [r4, #4]
    strh    r3, [ip, #8]
    dmb
    add     r2, r2, #1
    str     r2, [r10, #V_EW]
91: add     sp, sp, #SNAP_BYTES
    pop     {r0, r1, r2, r3, r5, r10, ip, lr}
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

/* put_events: r0 = where events go, [r2, r3) = this block's records
 * (global).  Writes the readings whose position falls inside, as
 * {pos u16 from r2, type 1, len 6, x, y, z}; skips older ones; leaves later
 * ones for the next block.  Returns r0 = count, r1 = the next byte.
 * r10 = vars. */
put_events:
    push    {r4, r5, r6, r7, r8, r9, r11, lr}
    mov     r1, r0
    mov     r8, r2
    mov     r9, r3
    mov     r4, #0                      @ count
    ldr     r5, [r10, #V_ER]
    ldr     r6, [r10, #V_EW]
    dmb
    sub     r0, r6, r5                  @ more than it holds: the oldest are gone
    cmp     r0, #ELOG_N
    subhi   r5, r6, #ELOG_N
    ADRF    r11, ebuf
1:  cmp     r5, r6
    beq     9f
    and     r0, r5, #(ELOG_N - 1)
    add     r0, r0, r0, lsl #1
    add     r7, r11, r0, lsl #2
    ldr     r0, [r7]                    @ position
    subs    r0, r0, r8
    bmi     8f                          @ before this block: gone by
    ldr     r2, [r7]
    subs    r2, r2, r9
    bpl     9f                          @ at or after this block's end: next one
    cmp     r4, #EV_MAX
    beq     8f                          @ room for no more: drop it
    strh    r0, [r1]
    mov     r0, #EVENT_LEVEL
    orr     r0, r0, #0x600              @ type 1, len 6
    strh    r0, [r1, #2]
    ldrh    r0, [r7, #4]
    strh    r0, [r1, #4]
    ldrh    r0, [r7, #6]
    strh    r0, [r1, #6]
    ldrh    r0, [r7, #8]
    strh    r0, [r1, #8]
    add     r1, r1, #10
    add     r4, r4, #1
8:  add     r5, r5, #1
    b       1b
9:  str     r5, [r10, #V_ER]
    mov     r0, r4
    pop     {r4, r5, r6, r7, r8, r9, r11, pc}

/* The frame sync.  Entered by a Thumb BLX from VD_SITE through an ARM
 * veneer; lr has the Thumb bit.  At interrupt level:
 * no waiting and no system calls.  Each records where the gyro stream is now
 * (the same global position as a level reading) and the TickTimer, then
 * replays the movt it displaced.  The only writer of its own ring. */
.macro SYNC_HOOK name, ring, wvar, reg
\name:
    push    {r0, r1, r2, r3, r5, r10, ip, lr}
    sub     sp, sp, #SNAP_BYTES
    ADRF    r10, vars
    mov     r0, sp
    bl      snapshot
    ldr     r1, [sp, #S_FLAGS]
    tst     r1, #F_LOST                 @ no place in the stream: nothing to say
    bne     1f
    ldr     ip, =F_TICK
    blx     ip
    ldr     r1, [sp, #S_MARK]
    ldr     r2, [r10, #\wvar]
    and     r3, r2, #(VLOG_N - 1)
    ADRF    ip, \ring
    add     ip, ip, r3, lsl #3
    str     r1, [ip]
    str     r0, [ip, #4]
    dmb
    add     r2, r2, #1
    str     r2, [r10, #\wvar]
1:  add     sp, sp, #SNAP_BYTES
    pop     {r0, r1, r2, r3, r5, r10, ip, lr}
    movt    \reg, #0xC31D              @ the displaced instruction
    bx      lr
.endm
    SYNC_HOOK vd_hook, vbuf, V_VW, r4

/* put_vd: r1 = where events go, [r2, r3) = this block's records
 * (global).  Like put_events, as {pos u16, type, len 4, TickTimer u32}.
 * Returns r0 = count, r1 = the next byte.  r10 = vars. */
.macro PUT_SYNC name, ring, wvar, rvar, type
\name:
    push    {r4, r5, r6, r7, r8, r9, lr}
    mov     r8, r2
    mov     r9, r3
    mov     r4, #0
    ldr     r5, [r10, #\rvar]
    ldr     r6, [r10, #\wvar]
    dmb
    sub     r0, r6, r5                  @ more than it holds: the oldest are gone
    cmp     r0, #VLOG_N
    subhi   r5, r6, #VLOG_N
    ADRF    r7, \ring
1:  cmp     r5, r6
    beq     9f
    and     r0, r5, #(VLOG_N - 1)
    add     ip, r7, r0, lsl #3
    ldr     r0, [ip]                    @ position
    subs    r0, r0, r8
    bmi     8f                          @ before this block: already past
    ldr     r2, [ip]
    subs    r2, r2, r9
    bpl     9f                          @ at or after the end: the next block's
    cmp     r4, #VEV_MAX
    beq     8f
    strh    r0, [r1]
    mov     r0, #\type
    orr     r0, r0, #0x400              @ len 4
    strh    r0, [r1, #2]
    ldr     r0, [ip, #4]
    strh    r0, [r1, #4]
    lsr     r0, r0, #16
    strh    r0, [r1, #6]
    add     r1, r1, #8
    add     r4, r4, #1
8:  add     r5, r5, #1
    b       1b
9:  str     r5, [r10, #\rvar]
    mov     r0, r4
    pop     {r4, r5, r6, r7, r8, r9, pc}
.endm
    PUT_SYNC put_vd, vbuf, V_VW, V_VR, EVENT_VD

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

/* Past the file: the loader zeroes block_size - file_len (build.py). */
.align 3
gbuf:
.set ebuf, gbuf + GLOG_BYTES
.set vbuf, ebuf + ELOG_BYTES
