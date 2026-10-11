.syntax unified
.arm
.text
/* Bounded shell-handler helper for a single AF publication capture, fp 5.02.
 * Assemble with AF_PROBE_P=<boot-scoped cave.claim() parameter address>.
 * The installer owns code publication, echo borrowing, AF hook/restore and
 * readback. This helper never installs a hook, drives AF, sends USB, or frees.
 *
 * 64-byte P ABI (all u32):
 * +00 op: 0 allocate, 1 export; +04 status (return r0 mirrors it)
 * +08 allocation_attempted (sticky, including failure)
 * +0C raw allocation; +10 aligned128 base; +14 allocation bytes (0x10000)
 * +18 expected nonce; +1C expected capacity (1..256), both supplied by host
 * +20 exported pointer; +24 exported length; +28 raw H_GET return
 * +2C mapping passed on this invocation; +30..3F allocator descriptor
 * Initialize P once to zero, then set the operation-specific inputs. Never
 * clear attempted to retry: a timeout is an uncertain allocation outcome.
 *
 * Status: 0 success, 1 unknown op, 2 already attempted/nonempty owner,
 * 3 null allocation, 4 invalid owner/range, 5 invalid export configuration,
 * 6 capture incomplete, 7 capture header mismatch, 8 mapping rejected.
 *
 * Fixed layout in the independent USER allocation: resident code at base,
 * 64-byte state at base+0x1040, records at base+0x1080. No alias conversion.
 * Export validates an immutable full capture, then performs one task-context
 * D-cache publication before setting worker CAP_PTR/LEN. worker.S only uses
 * DSB here. D-cache publication is not a detach/DMA-completion proof. Storage
 * and code remain owned after export; no reclaim path exists in this helper.
 */
#ifndef AF_PROBE_P
#error AF_PROBE_P is required
#endif

.equ PARAM,      AF_PROBE_P
.equ H_GET,      0xC001D740
.equ H_ADDR,     0xC001D7F0
.equ F_DCACHE,   0xC000E91C
.equ CAP_PTR,    0xC072F04C
.equ CAP_LEN,    0xC072F040
.equ ALLOC,      0x10000
.equ STATE_OFF,  0x1040

.macro LDA reg, value
    movw \reg, #:lower16:\value
    movt \reg, #:upper16:\value
.endm

.macro HEADER offset, value
    ldr r0, [r6, #\offset]
    LDA r1, \value
    cmp r0, r1
    bne bad_header
.endm

.global entry
entry:
    push {r4-r8, lr}              /* 24 bytes: preserve SP8 at every ROM call */
    LDA r4, PARAM
    mov r0, #0
    LDA r1, CAP_LEN
    str r0, [r1]
    LDA r1, CAP_PTR
    str r0, [r1]
    str r0, [r4, #0x20]
    str r0, [r4, #0x24]
    str r0, [r4, #0x2C]
    ldr r0, [r4]
    cmp r0, #0
    beq allocate
    cmp r0, #1
    beq export
    mov r0, #1
    b done

allocate:
    ldr r0, [r4, #8]
    ldr r1, [r4, #0x0C]
    orr r0, r0, r1
    ldr r1, [r4, #0x10]
    orrs r0, r0, r1
    bne repeated
    mov r0, #1
    str r0, [r4, #8]             /* commit attempt before a potentially blocking call */
    LDA r0, ALLOC
    str r0, [r4, #0x14]
    add r5, r4, #0x30
    mov r0, #0
    str r0, [r5]
    str r0, [r5, #4]
    str r0, [r5, #8]
    str r0, [r5, #12]
    mov r0, r5
    mov r1, #0                   /* USER, not CinemaDNG frame class 10 */
    LDA r2, ALLOC
    mov r3, #0
    LDA ip, H_GET
    blx ip
    str r0, [r4, #0x28]          /* H_ADDR, not an invented H_GET status convention */
    mov r0, r5
    LDA ip, H_ADDR
    blx ip
    str r0, [r4, #0x0C]
    cmp r0, #0
    beq null_allocation
    mov r5, r0
    LDA r1, 0x40000000
    cmp r5, r1
    blo bad_owner
    LDA r1, 0x7FFF0000
    cmp r5, r1
    bhi bad_owner
    mov r0, r5
    bl validate_mapping
    cmp r0, #1
    bne bad_mapping
    str r0, [r4, #0x2C]
    add r0, r5, #127
    bic r0, r0, #127
    str r0, [r4, #0x10]
    mov r0, #0
    b done

export:
    ldr r0, [r4, #8]
    cmp r0, #1
    bne bad_owner
    ldr r5, [r4, #0x0C]
    LDA r0, 0x40000000
    cmp r5, r0
    blo bad_owner
    LDA r0, 0x7FFF0000
    cmp r5, r0
    bhi bad_owner
    ldr r0, [r4, #0x14]
    cmp r0, #ALLOC
    bne bad_owner
    add r0, r5, #127
    bic r0, r0, #127
    ldr r1, [r4, #0x10]
    cmp r0, r1
    bne bad_owner
    LDA r6, STATE_OFF
    add r6, r0, r6
    ldr r8, [r4, #0x1C]
    cmp r8, #1
    blo bad_config
    cmp r8, #256
    bhi bad_config
    ldr r0, [r4, #0x18]
    cmp r0, #0
    beq bad_config
    lsl r7, r8, #7
    add r7, r7, #64
    add r0, r6, r7
    add r1, r5, #ALLOC
    cmp r0, r1
    bhi bad_owner
    mov r0, r5
    bl validate_mapping
    cmp r0, #1
    bne bad_mapping
    str r0, [r4, #0x2C]

    ldr r0, [r6, #28]
    cmp r0, #1
    bne incomplete
    dmb sy                       /* pair with publication's full marker */
    ldr r0, [r6, #20]
    cmp r0, #0
    bne incomplete
    ldr r0, [r6, #24]
    cmp r0, r8
    bne incomplete
    HEADER 0, 0x31464841
    HEADER 4, 1
    HEADER 8, 128
    ldr r0, [r6, #12]
    cmp r0, r8
    bne bad_header
    ldr r0, [r6, #16]
    ldr r1, [r4, #0x18]
    cmp r0, r1
    bne bad_header
    HEADER 32, 0xC022C858
    HEADER 36, 0xC023E9D0
    HEADER 40, 0xC022C85C
    HEADER 44, 64
    HEADER 48, 0
    HEADER 52, 0
    HEADER 56, 0
    HEADER 60, 0

    LDA ip, F_DCACHE              /* once per full export, never in the AF hook */
    blx ip
    str r6, [r4, #0x20]
    str r7, [r4, #0x24]
    LDA r0, CAP_PTR
    str r6, [r0]
    dmb sy
    LDA r0, CAP_LEN
    str r7, [r0]                 /* length last; worker sends only after return */
    mov r0, #0
    b done

repeated:
    mov r0, #2
    b done
null_allocation:
    mov r0, #3
    b done
bad_owner:
    mov r0, #4
    b done
bad_config:
    mov r0, #5
    b done
incomplete:
    mov r0, #6
    b done
bad_header:
    mov r0, #7
    b done
bad_mapping:
    mov r0, #8
done:
    str r0, [r4, #4]
    pop {r4-r8, pc}

/* r0=raw allocation, fixed 64 KiB; return 1 only for the current fp 5.02
 * short-descriptor noncache mapping. Same conditions as af_ep83_noncache_span_ok
 * in af_ep83_memory.c, without its legacy pool publication dependency.
 * Leaf, exactly 16 iterations maximum, all callee-saved registers retained.
 */
validate_mapping:
    push {r4-r8, lr}
    mov r4, r0
    LDA r1, 0x40000000
    cmp r4, r1
    blo mapping_no
    LDA r1, 0x7FFF0000
    cmp r4, r1
    bhi mapping_no
mrc_sctlr:
    mrc p15, 0, r0, c1, c0, 0
    LDA r1, 0x12000001
    and r0, r0, r1
    cmp r0, #1
    bne mapping_no
mrc_ttbcr:
    mrc p15, 0, r0, c2, c0, 2
    cmp r0, #0
    bne mapping_no
mrc_ttbr0:
    mrc p15, 0, r0, c2, c0, 0
    LDA r1, 0x44300040
    cmp r0, r1
    bne mapping_no
mrc_dacr:
    mrc p15, 0, r0, c3, c0, 0
    LDA r1, 0x55555555
    cmp r0, r1
    bne mapping_no
    LDA r1, 0xFFFF
    add r5, r4, r1
    lsr r6, r4, #20
    bic r6, r6, #15
    lsr r7, r5, #20
    bic r7, r7, #15
    LDA r0, 0x44300000
    add r6, r0, r6, lsl #2
    add r7, r0, r7, lsl #2
    and r4, r4, #0xFF000000
    and r5, r5, #0xFF000000
    LDA r0, 0x00044C02
    orr r4, r4, r0
    orr r5, r5, r0
    mov r8, #16
    dsb sy
mapping_loop:
    ldr r0, [r6], #4
    cmp r0, r4
    bne mapping_no
    ldr r0, [r7], #4
    cmp r0, r5
    bne mapping_no
    subs r8, r8, #1
    bne mapping_loop
    mov r0, #1
    pop {r4-r8, pc}
mapping_no:
    mov r0, #0
    pop {r4-r8, pc}
