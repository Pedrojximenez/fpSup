/* bayer_hook_oneshot.S — ONE-SHOT LV Bayer frame-ready capture hook.
 *
 * Installed at BOOT by AutoRun (native mem set, I-cache coherent) by patching the
 * ARM instruction at the LV ring-advance fn XC_LiveViewRawMemInterfaceSample::v3
 * @0xC040F528 (`mov ip,r0` = 0xE1A0C000) with `B trampoline`. On the next LV frame
 * the trampoline fires ONCE: records {this, idx, bayer_ptr, focus0, focus1, magic},
 * SELF-RESTORES the original instruction, re-runs the displaced `mov ip,r0`, and
 * continues the original function at 0xC040F52C. Idempotent if it fires a few times
 * before the I-cache drops the patched line (re-cache + re-restore are harmless).
 *
 * Loaded at a FIXED cave address (assembler-agnostic: only PC-relative literals).
 * RESULT block layout @RESULT:
 *   +0x00 this (heap singleton ptr)   +0x0C focus0 = *(0xC32914E0) g_afpos
 *   +0x04 idx (just-completed slot)    +0x10 focus1 = *(0xC3291958) mposm
 *   +0x08 bayer = 0x50000000+idx<<20   +0x14 magic 'BYR0'=0x30525942
 * At entry r0=this, flags dead (fresh vtable call), lr=caller. We preserve r0-r4,lr.
 */
.syntax unified
.arm
.text
.global _start
_start:
    push  {r0-r4, lr}          @ r0-r4 clobbered; keep lr (original fn returns via it)
    ldr   r1, [r0, #4]         @ idx = *(this+4) = just-completed slot
    ldr   r4, .Lresult
    str   r0, [r4, #0x00]      @ this
    str   r1, [r4, #0x04]      @ idx
    movw  r0, #0x0000
    movt  r0, #0x5000          @ r0 = 0x50000000 (Bayer ring base)
    add   r0, r0, r1, lsl #20  @ bayer = base + idx*0x100000
    str   r0, [r4, #0x08]
    ldr   r0, .Lfocus0
    ldr   r0, [r0]
    str   r0, [r4, #0x0C]      @ focus0 (g_afpos)
    ldr   r0, .Lfocus1
    ldr   r0, [r0]
    str   r0, [r4, #0x10]      @ focus1 (mposm)
    ldr   r0, .Lmagic
    str   r0, [r4, #0x14]      @ magic (proves hook fired)
    ldr   r1, .Lsite           @ self-restore the patched instruction
    ldr   r0, .Lorig
    str   r0, [r1]
    pop   {r0-r4, lr}
    mov   ip, r0               @ displaced original instruction
    ldr   pc, .Lcont           @ continue original fn at +4 (position-independent)
.align 2
.Lresult: .word 0xC072F800
.Lfocus0: .word 0xC32914E0
.Lfocus1: .word 0xC3291958
.Lmagic:  .word 0x30525942
.Lsite:   .word 0xC040F528
.Lorig:   .word 0xE1A0C000
.Lcont:   .word 0xC040F52C
