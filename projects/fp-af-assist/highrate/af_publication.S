.syntax unified
.arm
.text

/* fp 5.02, fixed C022C858 publication callsite only. OFFLINE CANDIDATE.
 * AF_STATE, AF_RECORDS and AF_CAPACITY are mandatory build definitions, not
 * claims of free/owned camera RAM. No installer is included.
 *
 * Preserve exact incoming SP and r0/r1/r2. Run native producer ONCE with its
 * original stack, return here, then branch to C022C85C. Recorder is a bounded
 * leaf: r0/r1 scratch only, r4 read as the original model, no SP writes/calls,
 * USB, MMIO, allocation, wait or back-edge. CMP modifies only dead NZCV, not
 * APSR Q/GE. Original callee-saved registers remain intact.
 *
 * Single scheduler writer; finite append-only capture. The caller must establish
 * buffer ownership, initialization, source identity and attach/detach quiescence.
 * Reader may consume only committed records; it must never clear/reuse a buffer
 * while hooked. DMB orders CPU publication, NOT DMA cache cleaning.
 *
 * One invocation is one CPU producer return, NOT an exposure/frame ID. Fields
 * are consecutive RAM reads, not an interrupt-atomic/exposure-aligned snapshot.
 * Offset 24 is the native cached lens position, not measured optical distance.
 * Offset 120 separately retains the AF manager's position for comparison.
 *
 * Staged level (header word 12, host-written, never stored here):
 *   0 off     replay the producer and nothing else; not even counted
 *   1 count   count producer returns only; no record, no field reads
 *   3 record  the full 128-byte record
 * Any other value is treated as off, so a damaged word fails closed. Level 1 is
 * the safe first live step: one number rising proves the site runs.
 *
 * Re-entrancy (header words 14 in_body, 15 overlaps): the body marks itself on
 * entry and clears it on every exit, and an invocation that finds the mark set
 * publishes nothing and latches overlaps. Once overlaps is non-zero no further
 * record is ever published, until a cold boot rebuilds the header. This is
 * plain load/store: LDREX/STREX needs a third scratch register, and
 * HOOK_ABI_AUDIT deliberately does not clear r2/r3/r12 for this callsite. So it
 * detects overlap unless two bodies pass the mark in the same instant -- not a
 * mutual-exclusion proof. The reader's in-order commit/complement check is what
 * catches a record damaged by that remaining window.
 */
#ifndef AF_STATE
#error AF_STATE is required
#endif
#ifndef AF_RECORDS
#error AF_RECORDS is required
#endif
#ifndef AF_CAPACITY
#error AF_CAPACITY is required
#endif
#ifndef AF_SCHEMA
#error AF_SCHEMA is required
#endif
#ifndef AF_LEVEL_COUNT
#error AF_LEVEL_COUNT is required
#endif
#ifndef AF_LEVEL_RECORD
#error AF_LEVEL_RECORD is required
#endif

.equ STATE, AF_STATE
.equ RECORDS, AF_RECORDS
.equ CAPACITY, AF_CAPACITY
.equ MAGIC, 0x31464841
.equ SCHEMA, AF_SCHEMA
.equ LEVEL_COUNT, AF_LEVEL_COUNT
.equ LEVEL_RECORD, AF_LEVEL_RECORD
.equ H_ENABLED, 20
.equ H_COUNT, 24
.equ H_FULL, 28
.equ H_LEVEL, 48
.equ H_HITS, 52
.equ H_IN_BODY, 56
.equ H_OVERLAPS, 60
.equ PRODUCER, 0xC023E9D0
.equ CONTINUATION, 0xC022C85C

.macro LDA reg, value
    movw \reg, #:lower16:\value
    movt \reg, #:upper16:\value
.endm

.macro COPY_WORD address, offset
    LDA r1, \address
    ldr r1, [r1]
    str r1, [r0, #\offset]
.endm

.macro COPY_BYTE address, offset
    LDA r1, \address
    ldrb r1, [r1]
    str r1, [r0, #\offset]
.endm

.global entry
entry:
    adr lr, after_native
    ldr pc, native_address

after_native:
    LDA r0, 0xC32044D8          /* exact model at this producer callsite */
    cmp r4, r0
    bne leave                   /* nothing marked: leave without clearing */
    LDA r0, STATE
    ldr r1, [r0]
    LDA r0, MAGIC
    cmp r0, r1
    bne leave
    LDA r0, STATE
    ldr r1, [r0, #4]
    cmp r1, #SCHEMA
    bne leave
    ldr r1, [r0, #8]
    cmp r1, #128
    bne leave
    ldr r1, [r0, #12]
    cmp r1, #CAPACITY
    bne leave
    ldr r1, [r0, #16]
    cmp r1, #0
    beq leave
    ldr r1, [r0, #H_LEVEL]      /* off or any other value: wholly inert, no mark */
    cmp r1, #LEVEL_COUNT
    beq staged
    cmp r1, #LEVEL_RECORD
    bne leave
staged:
    ldr r1, [r0, #H_IN_BODY]    /* a body is already running: never join it */
    cmp r1, #0
    bne overlap
    mov r1, #1
    str r1, [r0, #H_IN_BODY]
    dmb sy
    ldr r1, [r0, #H_HITS]       /* producer returns seen at level 1 and 3 */
    add r1, r1, #1
    str r1, [r0, #H_HITS]
    ldr r1, [r0, #H_OVERLAPS]   /* latched: publishing stays off for this boot */
    cmp r1, #0
    bne resume
    ldr r1, [r0, #H_LEVEL]      /* level 1 counts and stops here */
    cmp r1, #LEVEL_RECORD
    bne resume
    ldr r1, [r0, #H_ENABLED]
    cmp r1, #1
    bne resume
    ldr r1, [r0, #H_FULL]       /* never write a buffer already marked full */
    cmp r1, #0
    bne resume
    ldr r1, [r0, #H_COUNT]
    cmp r1, #CAPACITY
    bhs resume
    LDA r0, RECORDS
    add r0, r0, r1, lsl #7

    mov r1, #0
    str r1, [r0]                 /* record remains uncommitted until the end */
    COPY_WORD (STATE + 16), 4    /* capture nonce */
    COPY_WORD (STATE + 24), 8
    ldr r1, [r0, #8]
    add r1, r1, #1
    str r1, [r0, #8]             /* local publication sequence, 1..capacity */
    str r4, [r0, #12]            /* model at this fixed callsite */
    COPY_WORD 0xC31F8CB4, 28     /* scheduler phase before field reads */
    COPY_WORD 0xC31F8CB8, 32     /* scheduler mode before field reads */
    COPY_WORD 0xC32985E8, 16     /* processed H, area 0 */
    COPY_WORD 0xC32986B4, 20     /* processed L, area 0 */
    COPY_WORD 0xC3476418, 24     /* native cached lens position, F+4 */
    COPY_WORD 0xC3291514, 36     /* chosen area */
    COPY_WORD 0xC3291534, 40     /* reference area */
    COPY_WORD 0xC32915B0, 44     /* AF route */
    COPY_WORD 0xC343B5A0, 48     /* IMX410 relative gain */
    COPY_WORD 0xC343B5A8, 52     /* analog code */
    COPY_WORD 0xC343B5B4, 56     /* analog ratio, firmware fixed-point raw */
    COPY_BYTE 0xC343B5BC, 60     /* HCG flag */
    COPY_WORD 0xC32915B4, 64     /* AF RGB gain */
    COPY_WORD 0xC3291694, 68     /* AF sensitivity */
    COPY_WORD 0xC329169C, 72     /* AF shutter */
    COPY_WORD 0xC32916B0, 76     /* AF f-number */
    COPY_WORD 0xC30338C8, 80     /* four capture busy bytes */
    COPY_BYTE 0xC30338D0, 84     /* actual movie-recording byte */
    COPY_WORD 0xC3033A6C, 88     /* full shutter-sequence gate */
    COPY_WORD 0xC32046A4, 92     /* AF area mode raw */
    COPY_WORD 0xC32065A0, 96     /* AF drive mode raw */
    COPY_WORD 0xC3298918, 100    /* ROI count */
    COPY_WORD 0xC343B7BC, 104    /* HPF context 0 */
    COPY_WORD 0xC343B7C0, 108    /* HPF context 1 */
    COPY_WORD 0xC32914E0, 120    /* AF manager position, separate raw field */
    COPY_WORD 0xC31F8CB4, 112    /* scheduler phase after */
    COPY_WORD 0xC31F8CB8, 116    /* scheduler mode after */

    ldr r1, [r0, #8]
    mvn r1, r1
    str r1, [r0, #124]
    dmb sy
    mvn r1, r1
    str r1, [r0]                /* commit sequence after the complete body */
    dmb sy
    LDA r0, STATE
    str r1, [r0, #H_COUNT]      /* committed-prefix length */
    cmp r1, #CAPACITY
    bne resume
    mov r1, #0
    str r1, [r0, #H_ENABLED]    /* finite capture: no wrap or overwrite */
    dmb sy
    mov r1, #1
    str r1, [r0, #H_FULL]       /* full, safe-to-read DATA marker; not detach */

resume:
    LDA r0, STATE               /* leave the body: publish the count first */
    dmb sy
    mov r1, #0
    str r1, [r0, #H_IN_BODY]
leave:
    ldr pc, continuation_address

overlap:
    /* r0 is still STATE. A plain store of the same constant from either racing
     * invocation agrees, so this needs no exclusive access. */
    mov r1, #1
    str r1, [r0, #H_OVERLAPS]
    dmb sy
    ldr pc, continuation_address
code_end:
    .align 2
native_address:
    .word PRODUCER
continuation_address:
    .word CONTINUATION
