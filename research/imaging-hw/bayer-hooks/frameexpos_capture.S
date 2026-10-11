/* frameexpos_capture.S — ONE-SHOT capture of the LIVE raw_addr at RAW-frame exposure.
 *
 * Intercepts the `BL FrameExpos_s` at 0xC030D148 (inside ImageController FUN_c030d0c0).
 * AutoRun patches that BL to `BL trampoline`. Per RAW frame the trampoline:
 *   1. calls the real FrameExpos_s (0xC0315C10) with the original r0,r1 args (r1=&desc 0xC3439404),
 *      which runs the exposure and COMMITS raw_addr into the descriptor,
 *   2. reads the now-live descriptor 0xC3439404 fields into RESULT,
 *   3. SELF-RESTORES the original BL (0xEB0022B0) at 0xC030D148 (one-shot),
 *   4. returns to 0xC030D14C.
 * Caller tolerates r0-r3 clobber (it reloads r0 from r5, r1=#2 right after); r4-r11 untouched.
 *
 * RESULT @RESULT: +0x00 raw_addr(desc+0x38)  +0x04 small_raw(desc+0x3c)
 *                 +0x08 bit(desc+0x20)        +0x0c opcode(desc+0x00)  +0x10 magic 'FEX0'
 */
.syntax unified
.arm
.text
.global _start
_start:
    push  {lr}                 @ save return to 0xC030D14C
    ldr   ip, .Lframeexpos
    blx   ip                   @ FrameExpos_s(r0,r1) -> commits raw_addr
    ldr   r0, .Ldesc           @ 0xC3439404 descriptor base
    ldr   r2, .Lresult
    ldr   r1, [r0, #0x38]      @ raw_addr (full-frame)
    str   r1, [r2, #0x00]
    ldr   r1, [r0, #0x3c]      @ small_raw_addr
    str   r1, [r2, #0x04]
    ldr   r1, [r0, #0x20]      @ bit-depth enum
    str   r1, [r2, #0x08]
    ldr   r1, [r0, #0x00]      @ opcode
    str   r1, [r2, #0x0c]
    ldr   r1, .Lmagic
    str   r1, [r2, #0x10]
    ldr   r0, .Lsite           @ self-restore original BL at 0xC030D148
    ldr   r1, .Lorigbl
    str   r1, [r0]
    pop   {pc}                 @ return to 0xC030D14C
.align 2
.Lframeexpos: .word 0xC0315C10
.Ldesc:       .word 0xC3439404
.Lresult:     .word 0xC072F480
.Lmagic:      .word 0x30584546
.Lsite:       .word 0xC030D148
.Lorigbl:     .word 0xEB0022B0
