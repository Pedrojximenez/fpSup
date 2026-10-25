.syntax unified
.arm
.text
/* bufa_stopcb -- a BUFA0 completion callback that stops BUFA0 from inside the completion interrupt (2026-10-24).
 * Stopping at a random moment cut a frame's DMA in half (~1 in 100 froze the camera); waiting on the completion flag
 * and stopping from the shell task fixed that but consumed a flag the firmware's own 14-bit path waits on (4 wedges).
 * Here the ISR (FUN_c0630620 calls [0xC37CF8CC](arg, done_addr) per completion, IRQs off) does the two writes of
 * c06316b8(100) itself, right at the frame boundary, touching nothing shared.
 * The host points [0xC37CF8CC] here with REQ = 1, waits for DONE, and puts the old callback back.
 *   +0x00 code   ...   REQ / DONE: the two words at the end (offsets from the build: req_word / done_word)
 */
    .global bufa_stopcb
bufa_stopcb:
    ldr     r2, req_word
    cmp     r2, #0
    bxeq    lr
    ldr     r2, =0x30002060
    ldr     r3, [r2]
    bic     r3, r3, #1                  @ as c06316b8(100): BUFA0 enable off
    str     r3, [r2]
    ldr     r2, =0x30182000
    mov     r3, #0
    str     r3, [r2]                    @ BUFA0 mode 0
    str     r3, req_word
    mov     r3, #1
    str     r3, done_word
    bx      lr
    .ltorg
    .global req_word
req_word:   .word 0
    .global done_word
done_word:  .word 0
