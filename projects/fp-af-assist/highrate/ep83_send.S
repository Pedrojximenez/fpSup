.syntax unified
.arm
.text
/* Start one bounded transfer on EP 0x83 and wait for it, fp 5.02. OFFLINE.
 *
 * T0 of the telemetry platform: prove the transport, with a payload the host
 * wrote itself, before any hook data goes near it. Nothing here produces,
 * encodes or validates AF data; the bytes are whatever is already in the
 * buffer.
 *
 * SINGLE OWNER. The maintained text worker keeps EP 0x01 and EP 0x82; this
 * routine is reached through the borrowed echo handler, inside one ordinary
 * `shl` command, and touches only EP 0x83. It arms no second dispatcher and
 * starts nothing on the worker's endpoints, so the daemon's terminal is just
 * the worker's own reply frame. Do not pair this with the mode-5 CMD4 adapter:
 * two owners of EP01/EP82 is exactly what the transport audit forbids.
 *
 * The arm sequence is the worker's own (camera/worker.S `arm_in_block`), with
 * EP 0x83's table slot and physical number:
 *
 *     EP 0x01 OUT  logical 1  physical 2  TRB ptr @ 0xC31E3268
 *     EP 0x82 IN   logical 2  physical 5  TRB ptr @ 0xC31E326C
 *     EP 0x83 IN   logical 3  physical 7  TRB ptr @ 0xC31E3270
 *     TRB: [0] buffer bus address (CPU - 0x40000000), [4] high, [8] length,
 *          [12] control 0x813; then StartTransfer(physical).
 *
 * Assemble with EP83_P=<boot-scoped cave.claim() parameter address>.
 *
 * 32-byte P ABI (all u32), host writes 0x00/0x08/0x0C/0x10 and reads the rest:
 *   +00 op: 1 = send once. Any other value is refused without touching the TRB.
 *   +04 status (the return value mirrors it)
 *   +08 buffer, a CPU address inside the caller's own DMA-capable allocation
 *   +0C length in bytes
 *   +10 wait timeout, milliseconds
 *   +14 StartTransfer return
 *   +18 Wait return
 *   +1C TRB control word read back after the wait
 *
 * status: 0 success, 1 unknown op, 2 already used, 3 endpoint not enabled,
 * 4 invalid buffer/length, 5 no TRB, 6 start failed, 7 wait failed.
 *
 * One use per P block: op is cleared before the endpoint is touched, so a
 * repeat is refused rather than re-armed. On any failure the TRB is left as it
 * is and nothing is retried or ended -- an uncertain transfer still owns that
 * buffer, and EndTransfer here would be a second owner acting on a controller
 * state this routine cannot observe.
 */
#ifndef EP83_P
#error EP83_P is required
#endif

.equ PARAM,       EP83_P
.equ TRB_EP83,    0xC31E3270        /* endpoint TRB table [3]: EP 0x83 IN      */
.equ PHYS_EP83,   7
.equ LOG_EP83,    3
.equ TRB_ARMED,   0x813
.equ TO_BUS,      0xC0000000        /* +0xC0000000 mod 2^32 == -0x40000000     */
.equ DALEPENA,    0x2100C720        /* DWC3: bit N = physical endpoint N on     */
.equ FN_STARTX,   0xC01E6B81        /* StartTransfer(physical)        [thumb]   */
.equ FN_WAIT,     0xC01E4E81        /* Wait(logical, timeout_ms)      [thumb]   */
.equ DMA_LOW,     0x40000000
.equ DMA_HIGH,    0x80000000
.equ MAX_BYTES,   0x10000           /* the host protocol's own ceiling          */

.macro LDA reg, value
    movw \reg, #:lower16:\value
    movt \reg, #:upper16:\value
.endm

.global entry
entry:
    push {r4, r5, r6, r7, lr}
    LDA r4, PARAM
    mov r0, #0
    str r0, [r4, #0x14]
    str r0, [r4, #0x18]
    str r0, [r4, #0x1C]
    ldr r0, [r4]
    cmp r0, #1
    bne bad_op
    mov r0, #0
    str r0, [r4]                  /* one use: refuse a repeat before arming   */

    /* The controller's own record of which physical endpoints exist. EP 0x84
     * does not, which is what made v1 wait fifty seconds for nothing. */
    LDA r0, DALEPENA
    ldr r0, [r0]
    tst r0, #(1 << PHYS_EP83)
    beq not_enabled

    ldr r5, [r4, #8]              /* buffer, CPU address                      */
    ldr r6, [r4, #0xC]            /* length                                   */
    cmp r6, #0
    beq bad_buffer
    LDA r0, MAX_BYTES
    cmp r6, r0
    bhi bad_buffer
    tst r5, #3
    bne bad_buffer
    LDA r0, DMA_LOW
    cmp r5, r0
    blo bad_buffer
    LDA r0, DMA_HIGH
    sub r0, r0, r6                /* buffer + length must not leave the window */
    cmp r5, r0
    bhi bad_buffer

    LDA r0, TRB_EP83
    ldr r7, [r0]
    cmp r7, #0
    beq no_trb

    LDA r0, TO_BUS
    add r0, r5, r0                /* bus address                              */
    str r0, [r7]
    mov r0, #0
    str r0, [r7, #4]
    str r6, [r7, #8]
    movw r0, #TRB_ARMED
    str r0, [r7, #12]
    dsb                           /* payload and TRB visible before the DMA   */

    mov r0, #PHYS_EP83
    LDA r12, FN_STARTX
    blx r12
    str r0, [r4, #0x14]
    cmp r0, #0
    bne start_failed

    mov r0, #LOG_EP83
    ldr r1, [r4, #0x10]
    LDA r12, FN_WAIT
    blx r12
    str r0, [r4, #0x18]
    ldr r1, [r7, #12]
    str r1, [r4, #0x1C]           /* the TRB's own word, read back            */
    cmp r0, #0
    bne wait_failed
    mov r0, #0
    b done

bad_op:
    mov r0, #1
    b done
not_enabled:
    mov r0, #3
    b done
bad_buffer:
    mov r0, #4
    b done
no_trb:
    mov r0, #5
    b done
start_failed:
    mov r0, #6
    b done
wait_failed:
    mov r0, #7
done:
    str r0, [r4, #4]
    pop {r4, r5, r6, r7, pc}
