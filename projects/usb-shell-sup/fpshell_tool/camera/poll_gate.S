.syntax unified
.arm
.text
/* Record-safe admission poll, loaded at 0xC072FE00. Detoured-to from 0xC072DF00 (whose first
 * instruction `push {r4,lr}` we displace here). Poll movie-recording flag 0xC347E08F until 3
 * consecutive clear reads (~200ms apart, FN_DLY yields), then continue the original endpoint-enable
 * handler at 0xC072DF04. All absolute addresses -> position-independent. */
.equ REC_FLAG, 0xC347E08F
.equ FN_DLY,   0xC01F89C4
.equ CONT,     0xC072DF04     /* original handler, just after its displaced push {r4,lr} */

.global poll_gate
poll_gate:
    push    {r4, lr}          @ = displaced 0xC072DF00 (E92D4010)
    mov     r4, #0            @ consecutive-clear counter (reloaded by CONT before use)
pg_poll:
    movw    r0, #:lower16:REC_FLAG
    movt    r0, #:upper16:REC_FLAG
    ldrb    r1, [r0]
    cmp     r1, #0
    bne     pg_busy
    add     r4, r4, #1
    cmp     r4, #3
    bge     pg_done
    b       pg_delay
pg_busy:
    mov     r4, #0
pg_delay:
    mov     r0, #200
    movw    r12, #:lower16:FN_DLY
    movt    r12, #:upper16:FN_DLY
    blx     r12
    b       pg_poll
pg_done:
    movw    r12, #:lower16:CONT
    movt    r12, #:upper16:CONT
    bx      r12               @ ARM target (bit0=0) -> resume original handler
