.syntax unified
.arm
.text
#include "ogc_layout.h"
/* ============================================================================
 * res-custom, the multi-format OpenGate core's hook shims (32RESCUS.BIN).
 * notes/OG_MULTIFORMAT_CORE_DESIGN.md §3.2, §4.
 *
 * Assembled at OGC_LAYOUT0; every LDA is a movw/movt pair that og_pic.py
 * rewrites PC-relative when it names the layout (OG_V3_PAIR, res-lab's way).
 * Each shim keeps the firmware's registers exactly as the displaced code
 * expects, aligns the stack to 8 before calling C (ogc.c, through S.FN), and
 * goes down through its S.NEXT word: the layer below, or its *_replay (the
 * displaced instruction and the way back).
 *
 * Stack: a function-entry site is entered with the caller's 8-aligned stack;
 * a call site (BL) likewise.  Pushes here are even, and the C calls realign
 * explicitly anyway (memory arm-stack-alignment).
 * ========================================================================== */

.macro LDA reg, value
    movw    \reg, #:lower16:\value
    movt    \reg, #:upper16:\value
.endm

.equ S, OGC_S_COORD

/* way down: the word S.NEXT[slot] (absolute, written by the entry) */
.macro PASS nx
    LDA     ip, (S + \nx)
    ldr     ip, [ip]
    bx      ip
.endm

/* call S.FN[fn] with r0 = S; r1..r3 already set; r4 must be saved by the
 * caller and holds the old sp across the call */
.macro CALLC fn
    mov     r4, sp
    bic     ip, r4, #7
    mov     sp, ip
    LDA     r0, S
    ldr     ip, [r0, #\fn]
    blx     ip
    mov     sp, r4
.endm

.global shims_start
shims_start:

/* C00FBB90(copy descriptor). Only the native DNG caller may use the CPU
 * path. Gyro2 has already prepared its MakerNote before reaching this entry.
 * Other callers retain the exact original prologue and return semantics. */
.global hdrcopy
hdrcopy:
    push    {r0, r1, r2, r3, r4, lr}
    mov     r1, r0
    mov     r2, r5
    mov     r3, lr
    CALLC   FN_HDRCOPY
    cmp     r0, #0
    bne     1f
    pop     {r0, r1, r2, r3, r4, lr}
    PASS    NX_HDRCOPY
1:  mov     r0, #0                     @ native synchronous success
    str     r0, [sp]
    pop     {r0, r1, r2, r3, r4, pc}
.global hdrcopy_replay
hdrcopy_replay:                         @ push.w {r4, r5, r8, lr}
    push    {r4, r5, r8, lr}
    LDA     ip, 0xC00FBB95
    bx      ip

/* Clamp only this writer's stack-local batch descriptor, then make the
 * original configuration call with all arguments and its LR intact. */
.global bulk
bulk:
    push    {r0, r1, r2, r3, r4, lr}
    ldr     r1, [sp, #4]
    CALLC   FN_BULK
    pop     {r0, r1, r2, r3, r4, lr}
    PASS    NX_BULK

/* Run the original recorder getter, then adjust its rational without entering
 * interactive settings. Retain the original function's r0 return as well. */
.global recrate
recrate:
    push    {r0, r1, r2, r3, r4, lr}
    LDA     ip, (S + NX_RECRATE)
    ldr     ip, [ip]
    blx     ip
    ldr     r1, [sp]
    str     r0, [sp]
    CALLC   FN_RECRATE
    pop     {r0, r1, r2, r3, r4, pc}
.global recrate_replay
recrate_replay:
    push    {r4, r5, r6, r7, r8, lr}
    LDA     ip, 0xC00C9BD4
    bx      ip

/* CRCT: original selector first; adjust only an active RCD binning recipe. */
.global binpath
binpath:
    push    {r0, r1, r2, r3, r4, r5, r6, lr}
    LDA     ip, (S + NX_BINPATH)
    ldr     ip, [ip]
    blx     ip
    str     r0, [sp]
    ldr     r1, [sp, #4]
    ldr     r2, [sp, #8]
    CALLC   FN_BINPATH
    pop     {r0, r1, r2, r3, r4, r5, r6, pc}
.global binpath_replay
binpath_replay:
    push    {r4, r5, r6, r7}
    LDA     ip, 0xC032522C
    bx      ip

.macro BIN_WRITER name, nx, target
.global \name
\name:
    push    {r0, r1, r2, r3, r4, lr}
    CALLC   FN_BINKERNEL
    pop     {r0, r1, r2, r3, r4, lr}
    PASS    \nx
.global \name\()_replay
\name\()_replay:
    LDA     ip, \target
    bx      ip
.endm
BIN_WRITER binkernel1, NX_BINKERNEL1, 0xC0635DB1
BIN_WRITER binkernel2, NX_BINKERNEL2, 0xC0635DC9

/* Generic dynamic-format settings alias. Other names retain every argument. */
.global vrcgui
vrcgui:
    push    {r0, r1, r2, r3, r4, lr}
    CALLC   FN_VGUI
    cmn     r0, #1
    beq     2f
    cmp     r0, #0
    beq     1f
    add     sp, sp, #4
    pop     {r1, r2, r3, r4, lr}
    bx      lr
1:  pop     {r0, r1, r2, r3, r4, lr}
    adr     r1, .Lvrc_stock_help
    PASS    NX_VRCGUI
2:  pop     {r0, r1, r2, r3, r4, lr}
    PASS    NX_VRCGUI
.balign 4
.Lvrc_stock_help:
    .asciz  "SetupHelpMenu"
.balign 4

/* ---- C043CCF8 picker: r0 obj, r1 table, r2 key -> entry or stock ------------ */
.global picker
picker:
    push    {r0, r1, r2, r3, r4, lr}
    CALLC   FN_PICK
    cmp     r0, #0
    beq     1f
    add     sp, sp, #4
    pop     {r1, r2, r3, r4, lr}
    bx      lr
1:  pop     {r0, r1, r2, r3, r4, lr}
    PASS    NX_PICKER
.global picker_replay
picker_replay:
    push    {r4, r5, r6, r7, r10, r11, lr}
    LDA     ip, 0xC043CCFC
    bx      ip

/* ---- C005C020 resolution setter: r1 = value -----------------------------------
 * Through: ours before (phase 0), the firmware's setter, ours after (phase 1:
 * the live-view reload the value change did not cause). */
.global setter
setter:
    push    {r0, r1, r2, r3, r4, lr}
    mov     r2, #0
    CALLC   FN_SEL
    ldm     sp, {r0, r1, r2, r3}        @ the firmware's arguments, as they came
    LDA     ip, (S + NX_SETTER)
    ldr     ip, [ip]
    blx     ip                          @ the setter (or the layer below)
    str     r0, [sp]
    mov     r2, #1
    CALLC   FN_SEL
    pop     {r0, r1, r2, r3, r4, pc}
.global setter_replay
setter_replay:
    push    {r4, r5, r6, lr}
    LDA     ip, 0xC005C024
    bx      ip

/* ---- C005BE58 recording-format setter: r1 = format (MOV guard) --------------- */
.global fmtset
fmtset:
    push    {r0, r1, r2, r3, r4, lr}
    CALLC   FN_FMT
    pop     {r0, r1, r2, r3, r4, lr}
    PASS    NX_FMTSET
.global fmtset_replay
fmtset_replay:
    push    {r4, r5, r6, lr}
    LDA     ip, 0xC005BE5C
    bx      ip

/* ---- C043A19C (bl, was `mov r0, r4`): r4 = holder, r5 = profile id ----------- */
.global canvas
canvas:
    push    {r0, r1, r2, r3, r4, r6, ip, lr}
    add     r1, r4, #0x5C
    mov     r2, r5
    CALLC   FN_CANVAS
    pop     {r0, r1, r2, r3, r4, r6, ip, lr}
    PASS    NX_CANVAS
.global canvas_replay
canvas_replay:
    mov     r0, r4
    bx      lr

/* ---- C043A18C (bl, was `ldr r1, [ip, r5, lsl #2]`): the virtual profile ------
 * ip = the mapping base and r0 are live; r1 is what this instruction makes.
 * A virtual id (one of S's variants: a row's default or an entry's own) gets
 * its base row, everything else the mapping. */
.global vpro
vpro:
    push    {r2, r3, r4, r5}
    LDA     r2, S
    ldr     r3, [r2, #S_NVAR]
    ldr     r4, [r2, #S_VARS]
    add     r4, r2, r4
1:  subs    r3, r3, #1
    bmi     2f
    ldr     r1, [r4, #VAR_PID]
    cmp     r1, r5
    addne   r4, r4, #VAR_SIZE
    bne     1b
    ldr     r1, [r4, #VAR_BASE]
    pop     {r2, r3, r4, r5}
    bx      lr
2:  pop     {r2, r3, r4, r5}
    LDA     r1, (S + NX_VPRO)          @ ip is live: go down through r1
    ldr     r1, [r1]
    bx      r1
.global vpro_replay
vpro_replay:
    ldr     r1, [ip, r5, lsl #2]
    bx      lr

/* ---- C0437B48 resolution name: r1 out, r2 sizes; lr = the caller ------------- */
.global name
name:
    push    {r0, r1, r2, r3, r4, lr}
    mov     r3, lr
    CALLC   FN_NAME
    cmp     r0, #0
    pop     {r0, r1, r2, r3, r4, lr}
    bxne    lr
    PASS    NX_NAME
.global name_replay
name_replay:
    push    {r4, r5, r6, r7, r8, sb, fp, lr}
    LDA     ip, 0xC0437B4C
    bx      ip

/* ---- C0306EA0 / C0306EEC (was `mov r0, #3`): only r0 and ip are free --------- */
.global aspect
aspect:
    LDA     ip, (S + S_ASPECT)
    ldr     ip, [ip]
    cmp     ip, #0
    beq     1f
    mov     r0, ip
    LDA     ip, 0xC0306EA4
    bx      ip
1:  PASS    NX_ASPECT
.global aspect_replay
aspect_replay:
    mov     r0, #3
    LDA     ip, 0xC0306EA4
    bx      ip

.global aspect2
aspect2:
    LDA     ip, (S + S_ASPECT)
    ldr     ip, [ip]
    cmp     ip, #0
    beq     1f
    mov     r0, ip
    LDA     ip, 0xC0306EF0
    bx      ip
1:  PASS    NX_ASPECT2
.global aspect2_replay
aspect2_replay:
    mov     r0, #3
    LDA     ip, 0xC0306EF0
    bx      ip

/* ---- C02DAFA0: ratio pair for a live/picked or recognized 2:1 clip ---------
 * Sigma's getter asserts at enum >= 9. Keep its own path for every stock
 * enum and for an unowned enum 9. The pair lives beside this PIC shim. */
.global ratio
ratio:
    cmp     r0, #9
    bne     3f
    push    {r1, r2, r3, ip}
    LDA     r1, S
    ldr     r2, [r1, #S_ASPECT]
    cmp     r2, #9
    beq     2f
    ldr     r2, [r1, #S_PBROW]
    cmp     r2, #0
    beq     1f
    sub     r2, r2, #1
    ldr     r3, [r1, #S_NROWS]
    cmp     r2, r3
    bhs     1f
    ldr     r3, [r1, #S_ROWS]
    add     r3, r1, r3
    mov     ip, #ROW_SIZE
    mla     r2, r2, ip, r3
    ldr     r2, [r2, #ROW_ASPECT]
    cmp     r2, #9
    bne     1f
2:  adr     r0, .Lratio_2to1
    pop     {r1, r2, r3, ip}
    bx      lr
1:  pop     {r1, r2, r3, ip}
3:  PASS    NX_RATIO
.global ratio_replay
ratio_replay:
    push    {r4, lr}
    LDA     ip, 0xC02DAFA4
    bx      ip
.balign 4
.Lratio_2to1:
    .word   2, 1

/* ---- C0437E98 main output descriptor: r0 obj, r1 idx ------------------------- */
.global out
out:
    push    {r0, r1, r2, r3, r4, lr}
    mov     r2, r1
    mov     r1, r0
    CALLC   FN_OUT
    cmp     r0, #0
    beq     1f
    add     sp, sp, #4
    pop     {r1, r2, r3, r4, lr}
    bx      lr
1:  pop     {r0, r1, r2, r3, r4, lr}
    PASS    NX_OUT
.global out_replay
out_replay:
    push    {r4, r5, lr}
    LDA     ip, 0xC0437E9C
    bx      ip

/* ---- C03A6DD8 gain dispatch: "raw movie" for our own canvases (og3kgs) ------- *
 * () -> the current LV canvas's raw-movie class bit.  Ours: 1; else the firmware's. */
.global gs
gs:
    push    {r0, r1, r2, r3, r4, lr}
    CALLC   FN_GS
    cmp     r0, #0
    pop     {r0, r1, r2, r3, r4, lr}
    movne   r0, #1
    bxne    lr
    PASS    NX_GS
.global gs_replay
gs_replay:
    push    {r4, lr}
    LDA     ip, 0xC03A6DDC
    bx      ip

/* ---- the seven index lookups: r0 obj, r1 mode id -> index ---------------------
 * Not one of our virtual ids: straight down, no C.  Ours: ogc_vlook returns
 * r0 = index, r1 = 1 (or r1 = 0: down after all). */
.macro LOOKUP name, kind, nx, back, regs:vararg
.global \name
\name:
    push    {r2, r3}
    LDA     r2, S
    ldr     r3, [r2, #S_VMID0]
    sub     r3, r1, r3
    ldr     r2, [r2, #S_NVM]
    cmp     r3, r2
    pop     {r2, r3}
    bhs     9f
    push    {r0, r1, r2, r3, r4, lr}
    mov     r3, r1
    mov     r2, r0
    mov     r1, #\kind
    CALLC   FN_VLOOK
    cmp     r1, #0
    beq     8f
    add     sp, sp, #8
    pop     {r2, r3, r4, lr}
    bx      lr
8:  pop     {r0, r1, r2, r3, r4, lr}
9:  PASS    \nx
.global \name\()_replay
\name\()_replay:
    push    {\regs}
    LDA     ip, \back
    bx      ip
.endm

LOOKUP lk_tim,  T_TIM,  NX_LK_TIM,  0xC0320BA4, r4, r5, r6, r7
LOOKUP lk_meta, T_META, NX_LK_META, 0xC0320B3C, r4, r5, r6, r7
LOOKUP lk_r28,  T_R28,  NX_LK_R28,  0xC0320E94, r4, r5, r6, r7, sl
LOOKUP lk_r38,  T_R38,  NX_LK_R38,  0xC0320F64, r4, r5, r6, r7, sl
LOOKUP lk_r14,  T_R14,  NX_LK_R14,  0xC0320EFC, r4, r5, r6, r7, sl
LOOKUP lk_r68,  T_R68,  NX_LK_R68,  0xC0320C04, r4, r5, r6, r7
LOOKUP lk_reg,  T_REG,  NX_LK_REG,  0xC0326DBC, r4, r5, r6, r7, sl
LOOKUP lk_r10,  T_R10,  NX_LK_R10,  0xC031FFA4, r4, r5, r6, r7

/* ---- the four `bl FUN_c032c750(mode)` shutter-angle sites (og3kfps) ---------- */
.macro FPS name, nx
.global \name
\name:
    push    {r4, r5, r6, lr}
    mov     r5, r0
    LDA     ip, (S + \nx)
    ldr     ip, [ip]
    blx     ip                          @ the getter (or the layer below)
    mov     r2, r0
    mov     r1, r5
    CALLC   FN_FPS                      @ r4 holds the old sp
    pop     {r4, r5, r6, pc}
.endm
FPS fps1, NX_FPS1
FPS fps2, NX_FPS2
FPS fps3, NX_FPS3
FPS fps4, NX_FPS4

/* ---- the magnifier (descriptor +0x128) ---------------------------------------- */
/* r3 (r1 when the id is in r3) -> the donor id if it is one of our virtual ids */
.macro TO_DONOR reg
    push    {r1, r2}
    LDA     r1, S
    ldr     r2, [r1, #S_VMID0]
    sub     r2, \reg, r2
    ldr     ip, [r1, #S_NVM]
    cmp     r2, ip
    addlo   r1, r1, #S_VMDONOR
    ldrlo   \reg, [r1, r2, lsl #2]
    pop     {r1, r2}
.endm

/* C031AC38(dst, _, mode): our row for our ids */
.global ac38
ac38:
    push    {r0, r1, r2, r3, r4, lr}
    mov     r1, r0
    CALLC   FN_AC38
    cmp     r0, #0
    pop     {r0, r1, r2, r3, r4, lr}
    bxne    lr
    PASS    NX_AC38
.global ac38_replay
ac38_replay:
    push    {r4, r5, r6, r7, sl, fp, lr}
    LDA     ip, 0xC031AC3C
    bx      ip

/* C031ACD8(_, _, _, mode in r3): its own inline scan sees the donor */
.global acd8
acd8:
    push    {r0}
    mov     r0, r3
    TO_DONOR r0
    mov     r3, r0
    pop     {r0}
    PASS    NX_ACD8
.global acd8_replay
acd8_replay:
    push    {r4, r5, r6, r7, r8, sb, fp, lr}
    LDA     ip, 0xC031ACDC
    bx      ip

/* C031B660 (bl c03212f8, the current mode, then an inline scan): the donor */
.global zg
zg:
    push    {r4, lr}
    LDA     ip, (S + NX_ZG)
    ldr     ip, [ip]
    blx     ip
    TO_DONOR r0
    pop     {r4, pc}

/* C03249A0 XC_ImageSensorIMX410::v32(imager, i): our row for our ids */
.global v32
v32:
    push    {r0, r1, r2, r3, r4, lr}
    mov     r2, r1
    mov     r1, r0
    CALLC   FN_V32
    cmp     r0, #0
    pop     {r0, r1, r2, r3, r4, lr}
    bxne    lr
    PASS    NX_V32
.global v32_replay
v32_replay:
    push    {r4, r5, r6, r7, r8, sl, fp, lr}
    LDA     ip, 0xC03249A4
    bx      ip

/* ---- FUN_c057a6a0 / FUN_c05824d0: the menu committed a resolution row (r0 = var) */
.macro COMMIT name, nx, back, fn=FN_CMT
.global \name
\name:
    push    {r0, r1, r2, r3, r4, lr}
    mov     r1, r0
    CALLC   \fn
    pop     {r0, r1, r2, r3, r4, lr}
    PASS    \nx
.global \name\()_replay
\name\()_replay:
    push    {r4, r5, r6, r7, lr}
    LDA     ip, \back
    bx      ip
.endm
COMMIT cmt_set, NX_CMT_SET, 0xC057A6A4
COMMIT cmt_qs,  NX_CMT_QS,  0xC05824D4
/* ---- C0088C60 (bl FUN_c0088660): the settings save; then ours ---------------- */
.global save
save:
    push    {r4, r5, r6, lr}
    LDA     ip, (S + NX_SAVE)
    ldr     ip, [ip]
    blx     ip                          @ the firmware's save (or the layer below)
    mov     r5, r0
    CALLC   FN_SAVE
    mov     r0, r5
    pop     {r4, r5, r6, pc}

/* ---- §13: the Quick Set layers.  Thumb sites: a B.W to a Thumb veneer
 * (ldr.w pc, [pc]) that enters these in ARM state, as a call.  The C half calls
 * the way down itself (S.NEXT); the replays are ARM: the displaced Thumb
 * instruction(s), the same effect, then the rest in Thumb. */
.global qsrec
qsrec:                                  @ C05E6400(reader)
    push    {r4, lr}
    mov     r1, r0
    CALLC   FN_QSREC
    pop     {r4, pc}
.global qsrec_replay
qsrec_replay:                           @ push.w {r4-r11, lr}
    push    {r4, r5, r6, r7, r8, r9, r10, r11, lr}
    LDA     ip, 0xC05E6405
    bx      ip

.global qslay
qslay:                                  @ C05D90F0(layout)
    push    {r4, lr}
    mov     r1, r0
    CALLC   FN_QSLAY
    pop     {r4, pc}
.global qslay_replay
qslay_replay:                           @ push.w {r4-r7, r10, r11, lr}
    push    {r4, r5, r6, r7, r10, r11, lr}
    LDA     ip, 0xC05D90F5
    bx      ip

.global qsload
qsload:                                 @ C05E84D8(ctx, pack, bytes, 0): the four as an array
    push    {r0, r1, r2, r3, r4, lr}
    mov     r1, sp
    CALLC   FN_QSLOAD
    add     sp, sp, #16
    pop     {r4, pc}
.global qsload_replay
qsload_replay:                          @ push {lr}; sub sp, #24
    push    {lr}
    sub     sp, sp, #24
    LDA     ip, 0xC05E84DD
    bx      ip

/* ---- Crop Mode / frame-rate gates: S.FN GATE(kind, value) -> value --------------
 * Mid-function sites: every register kept but the one the gate decides, which is
 * read from and written back to its slot on the stack (r0..r4). */
.macro GATE name, kind, slot, nx
.global \name
\name:
    push    {r0, r1, r2, r3, r4, lr}
    ldr     r2, [sp, #\slot]
    mov     r1, #\kind
    CALLC   FN_GATE
    str     r0, [sp, #\slot]
    pop     {r0, r1, r2, r3, r4, lr}
    PASS    \nx
.endm

/* C04A1788 FUN_c04a1788(settings): Crop Mode available?  Ours says 0 (greyed) or down */
.global cropst
cropst:
    push    {r0, r1, r2, r3, r4, lr}
    mov     r1, #0
    mov     r2, #0
    CALLC   FN_GATE
    cmp     r0, #0
    pop     {r0, r1, r2, r3, r4, lr}
    movne   r0, #0
    bxne    lr
    PASS    NX_CROPST
.global cropst_replay
cropst_replay:
    push    {r4, lr}
    mov     r4, r0
    LDA     ip, 0xC04A1790
    bx      ip

GATE cropeff, 1, 12, NX_CROPEFF         @ C00A93BC `mov r0, r3`: r3 = the effective Crop Mode
.global cropeff_replay
cropeff_replay:
    mov     r0, r3
    pop     {r4, r5, r6, r7, r8, pc}

GATE frmax, 2, 16, NX_FRMAX             @ C00A87E4 `mov r1, r4`: r4 = the fastest rate allowed
.global frmax_replay
frmax_replay:
    mov     r1, r4
    LDA     ip, 0xC00A87E8
    bx      ip

GATE frclass, 3, 4, NX_FRCLASS          @ C04A121C `mov r0, r1`: r1 = the rate list's class
.global frclass_replay
frclass_replay:
    mov     r0, r1
    LDA     ip, 0xC04A1220
    bx      ip

GATE bitclass, 5, 4, NX_BITCLASS       @ C04A13E4 `mov r0, r1`: native list class
.global bitclass_replay
bitclass_replay:
    mov     r0, r1
    pop     {r4, pc}

/* C00A7FFC `mov r0,r3`: r7 is the original requested bit enum, r3 the
 * native result (possibly forced to 8 by UHD/SD). Preserve that stock result
 * for formats without an RCD declaration. The native stack is 4-aligned;
 * CALLC realigns it and restores it before continuing. */
.global bitnorm
bitnorm:
    push    {r0, r1, r2, r3, r4, lr}
    mov     r1, r7
    mov     r2, r3
    CALLC   FN_BIT
    str     r0, [sp, #12]
    pop     {r0, r1, r2, r3, r4, lr}
    PASS    NX_BITNORM
.global bitnorm_replay
bitnorm_replay:
    mov     r0, r3
    LDA     ip, 0xC00A8000
    bx      ip

/* C043B6A4 `movw r1, #0x46f0` ("MAG4" at 0xC0BE46F0): the displaced instruction
 * first, then the gate on its result; the movt at C043B6A8 completes either */
.global mag
mag:
    movw    r1, #0x46f0
    push    {r0, r1, r2, r3, r4, lr}
    ldr     r2, [sp, #4]
    mov     r1, #4
    CALLC   FN_GATE
    str     r0, [sp, #4]
    pop     {r0, r1, r2, r3, r4, lr}
    PASS    NX_MAG
.global mag_replay
mag_replay:
    LDA     ip, 0xC043B6A8
    bx      ip

/* ---- a declared rate's shutter range and angle: S.FN VTV(kind, v, enum) -------------
 * kind 0 (Tv): 1/n of the slowest shutter or 0; kind 2: the angle-to-Tv fps x 100.
 * enum ~0 = the C side asks the settings. */
/* C007F5B4 / C0553CDC `bl c0085ac0` (r0 -> the running min, r1 -> {num, den} per fps) */
.macro TVMIN name, nx
.global \name
\name:
    push    {r0, r1, r4, lr}
    mov     r1, #0
    mov     r2, #0
    mvn     r3, #0
    CALLC   FN_VTV
    cmp     r0, #0
    ldr     r1, [sp, #4]
    movne   r2, #1
    strne   r2, [r1]
    strne   r0, [r1, #4]
    pop     {r0, r1, r4, lr}
    PASS    \nx
.endm
TVMIN tvmin, NX_TVMIN

/* C052DCFC `movw r2, #0x2400`: r6 = fps x 100, [sp] = the rate enum */
.global angtv
angtv:
    push    {r0, r1, r2, r3, r4, lr}
    ldr     r3, [sp, #24]
    mov     r2, r6
    mov     r1, #2
    CALLC   FN_VTV
    mov     r6, r0
    pop     {r0, r1, r2, r3, r4, lr}
    PASS    NX_ANGTV
.global angtv_replay
angtv_replay:
    movw    r2, #0x2400
    LDA     ip, 0xC052DD00
    bx      ip

.global shims_end
shims_end:
