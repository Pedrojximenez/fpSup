.syntax unified
.arm
.text
/* ============================================================================
 * lhook_stub -- the Fast Start 2 (loader hook) entry, carried in the BIN.
 * ============================================================================
 *
 * build_autorun --lhook-in-file (Loader v4 cards).  This is loader.S's `lhook`
 * moved out of the words the AutoRun spells: stage2 places it in the cave right
 * after the loader (STUB_AT), checks its first word, and points 0xC03DA420 at
 * it.  The power switch is a warm restart -- the cave, this stub and the loader
 * all survive -- so the next boot comes here with the AutoRun's two arguments
 * in r0/r1: load; on success return and the AutoRun never starts; otherwise
 * start the AutoRun exactly as the firmware would have.
 *
 * The caller has pushed three words, so sp may be 4 off; aligned here and put
 * back from r4, which the push saves and the callee may not destroy.
 * ========================================================================== */
.equ AR_START,    0xC03DA758

.macro CALL target
9:  .word 0xEB000000 + ((((\target) - (STUB_AT + (9b - _start)) - 8) >> 2) & 0xFFFFFF)
.endm
.macro JUMP target
9:  .word 0xEA000000 + ((((\target) - (STUB_AT + (9b - _start)) - 8) >> 2) & 0xFFFFFF)
.endm

    .global _start
_start:
    push    {r0, r1, r4, lr}
    mov     r4, sp
    bic     sp, sp, #7
    CALL    LOAD_AT                     @ the loader's `load`, in the cave
    mov     sp, r4
    cmp     r0, #0
    pop     {r0, r1, r4, lr}
    movne   r0, #0
    bxne    lr
    JUMP    AR_START                    @ lr is still the firmware's
