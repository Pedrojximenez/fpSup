/* predisarm_hook.S — pre-disarm our vendor endpoints BEFORE the USB reconfig
 * disables them, eliminating the record/suspend/shutdown DEPCMD-spin wedge.
 *
 * Installed by AutoRun: the 4-byte Thumb-2 PUSH.W at FUN_c01e62a8 (0xC01E62A8,
 * bytes e92d 4df0 = PUSH.W {r4-r8,r10,r11,lr}) is replaced with B.W to this stub.
 * FUN_c01e62a8(param_1): when param_1==0 it wholesale-writes DALEPENA(0x2100C720)=3,
 * disabling our EP84(ctx4)/EP05(ctx5) (bits 0x600). We fire ONLY on param_1==0 AND
 * only when our 0x600 is currently live (a genuine teardown, never the initial
 * enumeration setup), EndTransfer both endpoints (still enabled here -> DEPCMD is fast,
 * no 60s spin), clear the worker's endpoint-enable one-shot (STATE+0x3C) so it re-brings
 * them up after, then re-execute the displaced PUSH.W and continue at 0xC01E62AC.
 *
 * THUMB-2. Absolute refs via movw/movt (position-independent). r0-r3 fully preserved
 * (FUN_c01e62a8's param_1 stays in r0); r4-r11 untouched (EndTransfer is AAPCS); lr
 * saved/restored around the blx calls so the displaced PUSH.W stores the caller's lr.
 */
.syntax unified
.thumb
.global _start
_start:
    cmp   r0, #0
    bne   .Lpass                 @ param_1 != 0 -> per-ep / boot; pass through
    push  {r0-r3, lr}            @ preserve args + lr (blx clobbers lr)
    movw  r2, #0xC720
    movt  r2, #0x2100            @ DALEPENA (0x2100C720)
    ldr   r3, [r2]
    and   r3, r3, #0x600
    cmp   r3, #0x600
    bne   .Lpop                  @ our EP84/EP05 not live -> nothing to disarm
    movs  r0, #4
    movw  r12, #0x6D49
    movt  r12, #0xC01E           @ FN_ENDX (thumb 0xC01E6D49)
    blx   r12                    @ EndTransfer(4)  EP84 IN
    movs  r0, #5
    movw  r12, #0x6D49
    movt  r12, #0xC01E
    blx   r12                    @ EndTransfer(5)  EP05 OUT
    movw  r0, #0xF03C
    movt  r0, #0xC072            @ STATE+0x3C = worker endpoint-enable one-shot
    movs  r1, #0
    str   r1, [r0]               @ clear it -> worker re-runs ag_admitted after reconfig
.Lpop:
    pop   {r0-r3, lr}
.Lpass:
    push.w {r4-r8, r10, r11, lr} @ displaced original instruction (e92d 4df0)
    movw  r12, #0x62AD
    movt  r12, #0xC01E           @ continue at 0xC01E62AC (thumb, +1)
    bx    r12
