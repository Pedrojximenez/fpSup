.syntax unified
.arm
.text
#include "og_pic.inc"
#ifndef OG_ENUM
#define OG_ENUM 4
#endif
/* ============================================================================
 * og3kfmt —— 錄影格式 setter。掛在 C005BE58 進入點,原指令 push {r4,r5,r6,lr}。
 * ============================================================================
 *   r0 = obj   r1 = 新的錄影格式(0 = CinemaDNG)   r2 = flag
 *
 * 為什麼需要它(2026-09-21 實機):
 *   選了 OG3K/OG2K 之後把錄影格式切成 MOV,再按錄影 -> **相機硬凍結**,
 *   shell 與 mem_get 一起死,只能抽電池。OG3K(p83/mode98)與
 *   OG2K(p13/mode139)**都會**,徵狀逐項相同。
 *
 *   原因:MOV 不走 CinemaDNG picker,所以有 profile 守衛的 fmttable 與
 *   og3kcanvas 完全不動作;但只看 FLAG 的那一組(og3kout / og3kaspect /
 *   og3kaspect2 / og3kfps / og3kgs)全部還開著,H.264 編碼器拿到的是
 *   給 3:2 CinemaDNG 準備的輸出描述子。
 *
 *   差分證明:同一個 MOV + RecSize=4 狀態,FLAG=1 硬凍結、FLAG=0 乾淨錄完。
 *   見 notes/FLAG_AND_PICKER_DISAGREE.md §10 §12 §38。
 *
 * 修法:把 FLAG 的意思從「選單選了本目標」收緊成
 *       「選了本目標 **而且** 錄影格式是 CinemaDNG」。
 *
 * 本體與 og3ksel 的交易**逐條相同**(FLAG / donor 時序 / GTAB 分組),
 * 因為那整段本來就只由一個布林 r5 驅動。差別只有三處:
 *   1. r5 的算法      —— 這裡是 (新格式 == CinemaDNG) 且 (最後的解析度 enum == 4)
 *   2. 多寫一個 FMTLATCH —— 讓 og3ksel 也知道目前的格式
 *   3. 回跳位址        —— 0xC005BE5C 而不是 0xC005C024
 * ========================================================================== */

.equ LOG,      OGA(0xC0731C00)      /* +0x04 = og3ksel 記下的最後一個解析度 enum */
.equ FLAG,     OGA(0xC0731C08)
.equ FMTLATCH, OGA(0xC0731C20)      /* 0 = CinemaDNG,其餘(含開機值 UNKNOWN)= 非 CinemaDNG */
.equ GTAB,     OGA(0xC0732100)
.equ CINEMADNG, 0

#ifndef TARGET_MODE_TIMING
#define TARGET_MODE_TIMING 0xC0B59540
#define TARGET_MODE_W0     0x01BD01BD
#define TARGET_MODE_W1     0x0004082E
#endif
.equ DONOR_TIMING, TARGET_MODE_TIMING
.equ DONOR_W0,     TARGET_MODE_W0
.equ DONOR_W1,     TARGET_MODE_W1
.equ BACK,     0xC005BE5C

.macro LDA reg, value
#ifdef OG_V3
    OGLDA   \reg, \value
#else
    movw    \reg, #:lower16:\value
    movt    \reg, #:upper16:\value
#endif
.endm

.global entry
entry:
    push    {r2, r3, r4, r5, r6, r7, ip, lr}

    /* 先把新格式鎖存起來 —— og3ksel 靠它判斷「現在是不是 CinemaDNG」。
     * 一定要在算 r5 之前寫,這樣兩個 hook 看到的是同一個事實。 */
    LDA     ip, FMTLATCH
    str     r1, [ip]

    /* r5 = (新格式 == CinemaDNG) 且 (最後選的解析度 enum == 4) */
    mov     r5, #0
    cmp     r1, #CINEMADNG
    bne     decided
    LDA     ip, LOG
    ldr     r3, [ip, #4]
    cmp     r3, #OG_ENUM
    moveq   r5, #1
decided:

    /* 以下與 og3ksel 的交易相同:離開時先撤旗標再還原 donor 時序,
     * 進入時先把資料準備好、最後才發布 FLAG=1。遮蔽 IRQ/FIQ,
     * 避免同 CPU 的 reader 看見半組 timing。 */
    mrs     r6, cpsr
    orr     r7, r6, #0xC0
    msr     cpsr_c, r7
    cmp     r5, #0
    bne     groups
#ifdef OG_CHAIN
    /* Loader v3, OG3K and OG2K stacked: leaving is undoing what *this* layer
     * did.  Not active -> write nothing (the timing, the shared preview
     * heights): another layer may be the one just selected. */
    LDA     ip, FLAG
    ldr     r3, [ip]
    cmp     r3, #0
    beq     gdone
#endif
    LDA     ip, FLAG
    mov     r3, #0
    str     r3, [ip]
    dmb     ish
    LDA     ip, DONOR_TIMING
    LDA     r3, DONOR_W0
    str     r3, [ip, #4]
    LDA     r3, DONOR_W1
    str     r3, [ip, #8]
    dmb     ish

groups:
    LDA     ip, GTAB
    ldr     r4, [ip], #4                @ 群組數
gloop:
    cmp     r4, #0
    beq     gdone
    ldr     r2, [ip], #4                @ 這組的筆數
    ldr     r3, [ip], #4                @ 選中時的值
    ldr     lr, [ip], #4                @ 未選時的值
    cmp     r5, #0
    moveq   r3, lr
eloop:
    cmp     r2, #0
    beq     gnext
    ldr     lr, [ip], #4
    str     r3, [lr]
    sub     r2, r2, #1
    b       eloop
gnext:
    sub     r4, r4, #1
    b       gloop
gdone:
    dmb     ish
    cmp     r5, #0
    beq     published
    LDA     ip, FLAG
    mov     r3, #1
    str     r3, [ip]                    @ 最後才讓其他 hooks 看見
    dmb     ish
published:
    mrs     r7, cpsr
    bic     r7, r7, #0xC0
    and     r6, r6, #0xC0
    orr     r7, r7, r6
    msr     cpsr_c, r7

    pop     {r2, r3, r4, r5, r6, r7, ip, lr}
#ifdef OG_CHAIN
    OG_PASS                     @ Loader v3: the layer below, or og_replay
.global og_replay
og_replay:
#endif
    push    {r4, r5, r6, lr}            @ 位移的原指令
    LDA     ip, BACK
    bx      ip
