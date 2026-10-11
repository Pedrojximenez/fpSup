/* Gyro2, stage P0: the probe.
 *
 * A loader v3 sup (projects/usb-shell-sup/notes/LOADER_V3.md) that hooks the
 * one place every CinemaDNG frame's header passes through, and proves the
 * place before any gyro data goes near it.
 *
 * The firmware serializes the DNG header once per take into a template, and
 * for every frame, on the RAW-complete event in the MovRec task, patches the
 * template and DMAs it in front of the frame's RAW:
 *
 *     C038C778  add  r0, sp, #0x1c        r0 = { src template, dst, len, flags }
 *     C038C77C  blx  #0xC00FBB90           the DMA copy               <- here
 *
 * This happens before XC_StillCreateFile__v2 and before the lossless sup sees
 * the frame (GYRO2_CAMERA_DESIGN.md section 11).  A block written into the
 * TEMPLATE here rides into the frame with the firmware's own copy.
 *
 * Where: the MakerNote's last tag, 0x0200, is a fixed 16 KB area whose end is
 * unused zeros (3.2-11 KB seen).  The tail is found from the template itself
 * at the first frame of a take, never from a fixed address.
 *
 * The probe block (64 bytes, at tail start + GAP):
 *     +0  'FSGP'           written last: the commit
 *     +4  1                version
 *     +8  [r6 + 0x174]     the tag manager's frame counter (+1 per frame; on the
 *                          camera it started at 3, not 1)
 *     +12 [r5 + 0x10FC]    the request's index (on the camera: 0..95, then wraps)
 *     +16 TickTimer        microseconds, FUN_c002b6e0
 *     +20 frames written this take, from 1
 *     +24 tail offset in the template    +28 tail length
 *     +32 src   +36 dst   +40 len        +44 boot id
 *     +48 A0 A1 .. AF      a pattern
 *
 * Register contract at the site (verified in the image): r4 = DataPool,
 * r5 = request, r6 = tag manager; the callee takes r0 only and its return
 * value is not used.  The hook keeps r0 and r4-r11 and tail-calls whatever
 * the site branched to before it (chain_next), so other CHAIN layers stack.
 *
 * Position-independent: adr and pc-relative only; firmware addresses are
 * constants.  Header bytes are read with ldrb: TIFF entries are 2 mod 4. */
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
.equ O_TAG_COUNT,  0x174              /* tag manager: +1 per frame          */
.equ O_REQ_FRAME,  0x10FC             /* request index, wraps at 96         */

.equ MAGIC,        0x50475346         /* 'FSGP'                             */
.equ GAP,          64                 /* clear of the vendor's last byte    */
.equ BLK,          64
.equ LINE,         32                 /* Cortex-A9 D-cache line             */

/* vars: one block of words, in this file, zero at load */
.equ V_SVC,    0
.equ V_BOOT,   4
.equ V_NEXT,   8
.equ V_SRC,    12
.equ V_WOFF,   16                     /* block offset in the template, 0 = none */
.equ V_TOFF,   20
.equ V_TLEN,   24
.equ V_FRAMES, 28
.equ V_CALLS,  32
.equ V_SKIPS,  36
.equ V_LCOUNT, 40                     /* the tag counter at the last frame       */
.equ V_LTICK,  44                     /* TickTimer at the last frame             */
.equ V_NOW,    48
.equ NEW_TAKE_US, 500000              /* a pause this long starts a new take     */

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

    mov     r0, r5                      @ what the site branches to now
    ldr     r1, =SITE
    mov     r2, #0
    ldr     ip, [r5, #SVC_CHAIN]
    blx     ip
    cmp     r0, #0
    beq     9f
    str     r0, [r6, #V_NEXT]

    mov     r0, r5
    mov     r1, #8
    ldr     ip, [r5, #SVC_CAVE]
    blx     ip
    cmp     r0, #0
    beq     9f
    mov     r7, r0                      @ the veneer: ldr pc, [pc, #-4]; .word hook
    ldr     r1, =0xE51FF004
    str     r1, [r7]
    adr     r1, hook
    str     r1, [r7, #4]

    ldr     r2, =SITE                   @ the site: bl veneer
    sub     r1, r7, r2
    sub     r1, r1, #8
    asr     r1, r1, #2
    bic     r1, r1, #0xFF000000
    orr     r1, r1, #0xEB000000
    str     r1, [r2]

    mov     r0, r5
    ldr     ip, [r5, #SVC_PUBLISH]
    blx     ip
    mov     r0, #0                      @ SL_KEEP
    pop     {r4, r5, r6, r7, r8, pc}
9:  mov     r0, #1                      @ SL_RELEASE: nothing was written
    pop     {r4, r5, r6, r7, r8, pc}

/* Data sits between entry and hook so every adr stays within reach (an ARM
 * adr encodes a rotated 8-bit immediate: any word distance under 1 KB). */
.align 2
site_stock: .word 0xFAF5BD03          @ blx #0xC00FBB90, from the image
vars:       .space 52

/* ------------------------------------------------------------------- hook */
/* In place of the DMA call.  r0 = the copy descriptor. */
hook:
    push    {r0, r4, r5, r6, r7, r8, r9, r10, r11, lr}
    mov     r8, r5                      @ request
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

    /* A new take: the tag counter is not last + 1 (measured on the camera,
     * it runs on by one per frame within a take but does not start at 1),
     * or a pause no take has inside it.  Then, or on a new template, parse
     * the template again. */
    ldr     r1, [r10, #V_SRC]
    cmp     r1, r4
    bne     20f
    cmp     r7, r3
    bne     20f
    ldr     r1, =NEW_TAKE_US
    cmp     r6, r1
    bhi     20f
    ldr     r1, [r10, #V_WOFF]
    cmp     r1, #0
    beq     20f
    add     r2, r4, r1                  @ the place must still be ours or empty
    bl      region_ok
    cmp     r0, #0
    bne     30f

20: mov     r0, r4
    mov     r1, r11
    bl      find_tail                   @ r0 = tail offset or 0, r1 = length
    str     r4, [r10, #V_SRC]
    mov     r2, #0
    str     r2, [r10, #V_FRAMES]
    cmp     r0, #0
    beq     40f
    cmp     r1, #(GAP + BLK)
    blo     40f
    str     r0, [r10, #V_TOFF]
    str     r1, [r10, #V_TLEN]
    add     r0, r0, #GAP
    str     r0, [r10, #V_WOFF]
    add     r2, r4, r0
    bl      region_ok                   @ a fresh tail is zero; check anyway
    cmp     r0, #0
    beq     41f

30: ldr     r0, [r10, #V_WOFF]
    add     r5, r4, r0                  @ r5 = the block
    ldr     r0, [r10, #V_NOW]
    str     r0, [r5, #16]
    mov     r0, #1
    str     r0, [r5, #4]
    str     r7, [r5, #8]
    add     r0, r8, #(O_REQ_FRAME & 0xF000)
    ldr     r0, [r0, #(O_REQ_FRAME & 0xFFF)]
    str     r0, [r5, #12]
    ldr     r0, [r10, #V_FRAMES]
    add     r0, r0, #1
    str     r0, [r10, #V_FRAMES]
    str     r0, [r5, #20]
    ldr     r0, [r10, #V_TOFF]
    str     r0, [r5, #24]
    ldr     r0, [r10, #V_TLEN]
    str     r0, [r5, #28]
    str     r4, [r5, #32]
    ldr     r0, [sp]                    @ the descriptor
    ldr     r1, [r0, #4]
    str     r1, [r5, #36]
    str     r11, [r5, #40]
    ldr     r0, [r10, #V_BOOT]
    str     r0, [r5, #44]
    ldr     r0, =0xA3A2A1A0
    ldr     r1, =0x04040404
    str     r0, [r5, #48]
    add     r0, r0, r1
    str     r0, [r5, #52]
    add     r0, r0, r1
    str     r0, [r5, #56]
    add     r0, r0, r1
    str     r0, [r5, #60]
    dmb
    ldr     r0, =MAGIC                  @ the commit, last
    str     r0, [r5]
    bic     r0, r5, #(LINE - 1)         @ clean the block's lines for the DMA
    add     r1, r5, #BLK
31: mcr     p15, 0, r0, c7, c10, 1      @ DCCMVAC
    add     r0, r0, #LINE
    cmp     r0, r1
    blo     31b
    dsb
    b       50f

41: mov     r0, #0                      @ the place was not empty: leave it
    str     r0, [r10, #V_WOFF]
40: ldr     r0, [r10, #V_SKIPS]
    add     r0, r0, #1
    str     r0, [r10, #V_SKIPS]

50: pop     {r0, r4, r5, r6, r7, r8, r9, r10, r11, lr}
    adr     ip, vars
    ldr     ip, [ip, #V_NEXT]
    bx      ip                          @ the layer below, with r0 and lr as given

/* region_ok: r2 = BLK bytes.  r0 = 1 when they are all zero or begin with
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
    cmp     r3, #BLK
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

