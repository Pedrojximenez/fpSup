.syntax unified
.arm
.text
#include "og_pic.inc"
/* Native frame-rate glue. Each ROLE is an independent leaf trampoline.
 * Guards use published CUSTOM + CinemaDNG state; no firmware call or BSS writes.
 * Preserve NZCVQ and scratch registers around the displaced instruction.
 */
.macro LDA reg, value
#ifdef OG_V3
    OGLDA   \reg, \value
#else
 movw \reg, #:lower16:\value
 movt \reg, #:upper16:\value
#endif
.endm
.macro RETURN_TO address
 ldr pc, [pc, #-4]
 .word \address
.endm
.global entry
entry:
#if ROLE == 5
 /* The native lazy cache may already exist before AutoRun. Return owned data. */
 LDA r0, LEGAL_DESC
 RETURN_TO 0xC00A885C
#elif ROLE == 6 || ROLE == 7
 /* MV_FrameRate setter callbacks FUN_c057a6f8 (ROLE 6) and FUN_c05821b8 (ROLE 7),
  * r0=var, entered before their identical push {r4-r7,lr}.
  * (2026-10-01 camera: r8 hooked only the first; the Settings menu commits
  *  through the second.)
  * (2026-10-01 camera: first armed on FUN_c057a750 = MV_Binning by mistake --
  *  the flag never moved; that converter slot is +0x64, frame rate is +0x60.)
  * [r0+8] = committed row.  Row 9 (239.76) -> RATE240=1, else 0.  Stock still
  * converts the row itself (row 9 -> internal 7); this only records the choice
  * in RAM and orders the duplicate value-7 pairs so value->row finds the chosen
  * row, and points summary state for export 10 at the tenth label.  Never
  * writes a stock setting (SETTINGS_AREA_FIRST_RULE). */
 push {r1,r2,r3,ip}
 mrs r2,cpsr
 ldr r1,[r0,#8]
 cmp r1,#9
 moveq r1,#1
 movne r1,#0
 LDA r3, RATE240
 str r1,[r3]
 LDA r3, INPUT_PAIR + 0x40          /* pairs 8 and 9: (7,row),(7,row) */
 cmp r1,#0
 moveq ip,#8
 movne ip,#9
 str ip,[r3,#4]
 moveq ip,#9
 movne ip,#8
 str ip,[r3,#12]
 moveq ip,#8
 movne ip,#9
 LDA r3, SUMMARY_STATE
 str ip,[r3]
 msr cpsr_f,r2
 pop {r1,r2,r3,ip}
#ifdef LIVE
 /* Sensor Lab menu card (sl_excl.S ROLE 12/13): stock runs from there, then the
  * MODE list follows the new frame rate.  The displaced push goes with it. */
 RETURN_TO LIVE
#else
 push {r4,r5,r6,r7,lr}
#if ROLE == 6
 RETURN_TO 0xC057A6FC
#else
 RETURN_TO 0xC05821BC                /* FUN_c05821b8: the other MV_FrameRate setter */
#endif
#endif
#else
 push {r1,r2,r3,ip}
 mrs r2,cpsr
#if ROLE == 1
 mov r0,r1
#endif
 LDA r3, FLAG
 ldr r3,[r3]
 cmp r3,#1
 bne stock
 LDA r3, FMTLATCH
 ldr r3,[r3]
 cmp r3,#0
 bne stock
#if ROLE == 1
 mov r0,#0
#elif ROLE == 2
 /* r1 is restored below, so save the selected comparison operand in its slot. */
 str r6,[sp]
#else
 LDA r3, LIST
 str r3,[r0]
 mov r3,#10
 str r3,[r0,#4]
 msr cpsr_f,r2
 pop {r1,r2,r3,ip}
 bx lr
#endif
 b done
stock:
#if ROLE == 2
 str r4,[sp]
#elif ROLE == 3
 msr cpsr_f,r2
 pop {r1,r2,r3,ip}
 push {r4,r5,lr}
 RETURN_TO 0xC049A78C
#elif ROLE == 4
 msr cpsr_f,r2
 pop {r1,r2,r3,ip}
 sub sp,sp,#8
 RETURN_TO 0xC05332AC
#endif
done:
 msr cpsr_f,r2
 pop {r1,r2,r3,ip}
#if ROLE == 1
 RETURN_TO 0xC04A1220
#elif ROLE == 2
 RETURN_TO 0xC00A87E8
#endif

#endif
