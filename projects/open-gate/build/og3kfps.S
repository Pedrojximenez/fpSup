.syntax unified
.arm
.text
#include "og_pic.inc"
/* ============================================================================
 * og3kfps — 修正 donor 模式的快門角度 nominal-fps 查詢。
 *
 * 只取代四條已確認的快門角度換算／同步路徑裡的本地
 *     BL FUN_c032c750(mode)
 * 不動全域 getter，因為 donor 模式通常也被照片路徑共用。
 * r0 進來是 sensor mode，回去必須是整數 nominal fps。
 *
 * 一律先呼叫原 getter，保留它的同步/初始化副作用。只有 FLAG==1 且 donor 的
 * timing record 兩個完整 words 精確命中白名單 tuple 才覆寫原結果；stock、
 * 混合、損壞或切換中的 tuple 全部 fail-open。
 *
 * TARGET_MODE 沒定義時的預設是 OG3K:donor = mode 98，它的 ROM metadata
 * +0x40 是 78，而 OG3K 借它承載七組 <=60fps timing，所以 78 是謊報值；
 * OG3K100 走 mode 117 不在白名單內，直接保留原 getter 的 100。
 *
 * **不改 donor 時序的目標不需要這支** —— HSW 寫回 mode 12 的就是它自己的
 * 原廠時序，而它的 +0x40 原廠就是真實的 240,所以四顆 BL 一顆都不武裝
 * (og3k_plan 的 _ANGLE_FIX_TARGETS)。
 * ========================================================================== */

.equ FLAG,             OGA(0xC0731C08)
.equ ORIGINAL,         0xC032C750
/* 目標參數:donor 模式、它的 timing record,以及白名單 tuple。
 * word0 = hmax | tail<<16;word1 = vmax | x<<16。
 * 沒定義時就是 OG3K(mode98,七組 <=60fps;100fps 走 mode117 不在表內)。 */
#ifndef TARGET_MODE
#define TARGET_MODE         98
#define TARGET_MODE_TIMING  0xC0B59540
#define TARGET_T0_W0 0x024901BD
#define TARGET_T0_W1 0x00041A5C
#define TARGET_T0_FPS 24
#define TARGET_T1_W0 0x047901BD
#define TARGET_T1_W1 0x00041A54
#define TARGET_T1_FPS 24
#define TARGET_T2_W0 0x01C201C2
#define TARGET_T2_W1 0x00041900
#define TARGET_T2_FPS 25
#define TARGET_T3_W0 0x02DF01BD
#define TARGET_T3_W1 0x00041516
#define TARGET_T3_FPS 30
#define TARGET_T4_W0 0x031B01BD
#define TARGET_T4_W1 0x00040D2A
#define TARGET_T4_FPS 48
#define TARGET_T5_W0 0x01C201C2
#define TARGET_T5_W1 0x00040C80
#define TARGET_T5_FPS 50
#define TARGET_T6_W0 0x040B01BD
#define TARGET_T6_W1 0x00040A8A
#define TARGET_T6_FPS 60
#endif

.equ DONOR_TIMING,    TARGET_MODE_TIMING
.equ T2398_W0,         TARGET_T0_W0
.equ T2398_W1,         TARGET_T0_W1
.equ T24_W0,           TARGET_T1_W0
.equ T24_W1,           TARGET_T1_W1
.equ T25_W0,           TARGET_T2_W0
.equ T25_W1,           TARGET_T2_W1
.equ T30_W0,           TARGET_T3_W0
.equ T30_W1,           TARGET_T3_W1
@ 48/50/60 只有在目標真的有那些格率時才存在。OG6K 的感測器讀出是
@ 24.982 ms(445 x 4042 / 72 MHz),封頂 40.03 fps,所以它只有四個格率。
#ifdef TARGET_T4_W0
.equ T48_W0,           TARGET_T4_W0
.equ T48_W1,           TARGET_T4_W1
.equ T50_W0,           TARGET_T5_W0
.equ T50_W1,           TARGET_T5_W1
.equ T60_W0,           TARGET_T6_W0
.equ T60_W1,           TARGET_T6_W1
#endif
#ifdef TARGET_T7_W0
.equ T100_W0,          TARGET_T7_W0
.equ T100_W1,          TARGET_T7_W1
#endif

.macro LDA reg, value
#ifdef OG_V3
    OGLDA   \reg, \value
#else
    movw    \reg, #:lower16:\value
    movt    \reg, #:upper16:\value
#endif
.endm

.macro MATCH w0, w1, fps, next
    LDA     ip, \w0
    cmp     r2, ip
    bne     \next
    LDA     ip, \w1
    cmp     r3, ip
    moveq   r0, #\fps
    beq     done
.endm

.global entry
entry:
    /* 四個 registers 維持呼叫點的 8-byte stack alignment。 */
    push    {r4, r5, r6, lr}
    mov     r4, r0
#ifdef OG_CHAIN
    LDA     ip, OG_NEXT                 @ Loader v3: ORIGINAL, or the layer below
    ldr     ip, [ip]
#else
    LDA     ip, ORIGINAL
#endif
    blx     ip
    mov     r5, r0                      @ stock result / fail-open result

    cmp     r4, #TARGET_MODE
    bne     stock
    LDA     ip, FLAG
    ldr     ip, [ip]
    cmp     ip, #1
    bne     stock
    dmb     ish                         @ acquire timing published before FLAG/timing

    LDA     r6, DONOR_TIMING
    ldr     r2, [r6, #4]
    ldr     r3, [r6, #8]

    MATCH   T2398_W0, T2398_W1, TARGET_T0_FPS, try24
try24:
    MATCH   T24_W0,   T24_W1,   TARGET_T1_FPS, try25
try25:
    MATCH   T25_W0,   T25_W1,   TARGET_T2_FPS, try30
try30:
#ifdef TARGET_T4_W0
    MATCH   T30_W0,   T30_W1,   TARGET_T3_FPS, try48
try48:
    MATCH   T48_W0,   T48_W1,   TARGET_T4_FPS, try50
try50:
    MATCH   T50_W0,   T50_W1,   TARGET_T5_FPS, try60
try60:
#ifdef TARGET_T7_W0
    MATCH   T60_W0,   T60_W1,   TARGET_T6_FPS, try100
try100:
    MATCH   T100_W0,  T100_W1,  TARGET_T7_FPS, stock
#else
    MATCH   T60_W0,   T60_W1,   TARGET_T6_FPS, stock
#endif
#else
    @ 四格率的目標(OG6K):鏈在 T3 就結束,後面直接落到 stock。
    MATCH   T30_W0,   T30_W1,   TARGET_T3_FPS, stock
#endif

stock:
    mov     r0, r5
done:
    pop     {r4, r5, r6, pc}
