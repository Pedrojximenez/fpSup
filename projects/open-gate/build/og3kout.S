.syntax unified
.arm
.text
#include "og_pic.inc"
/* ============================================================================
 * og3kout — 主輸出描述子:照抄拍照模式的 3:2 幾何
 * ============================================================================
 * C0437E98 是 `return *(obj + idx*8)`,idx < 4,原指令 push {r4,r5,lr}。
 *
 * 實測兩個 LiveViewState 物件(相距 0x24),各有兩個有效插槽:
 *
 *              idx0 主預覽              idx2 次要
 *   STILL      1620x1080  (3:2)        320x213  (3:2)   ← 原生就是對的
 *   CINE       1620x 911  (16:9)       320x180  (16:9)
 *
 * 除了高度以外的九個字(格式 4、配置上限、視訊旗標 1,1)兩者完全相同,
 * 而且 320x213 正好是 320x2/3 —— 拍照模式就是我們要的那組 3:2 組態。
 *
 * 不改原廠描述子(共用的活緩衝)。第一次命中時整份複製到私有緩衝、只改兩個
 * 高度欄位,之後恆回傳同一份不可變副本。
 *
 * 守衛:旗標必須立起、idx 必須是 0 或 2、原廠描述子必須確為預期的 16:9 尺寸。
 * 任何一項不符就原封不動走原路,並把該筆記進拒絕環,方便找出還留著的 16:9。
 *
 *   0xC0732000  idx0:+00 已建置  +04..+2F 模板
 *   0xC0732030  idx2:+00 已建置  +04..+2F 模板
 *   0xC0732060  命中數
 *   0xC0732070  拒絕環:+00 筆數,之後每筆 12 bytes {idx, W, H},最多 6 筆
 * ========================================================================== */
.equ TPL0, OGA(0xC0732000)
.equ TPL2, OGA(0xC0732030)
.equ HITS, OGA(0xC0732060)
.equ REJ,  OGA(0xC0732070)
.equ FLAG,   OGA(0xC0731C08)
#ifdef TARGET_MATCH
.equ PICKOK, TARGET_MATCH   @ fmttable 寫:1 = picker 同意走 3:2
#endif
.equ PBFLAG, OGA(0xC0731C0C)
.equ BACK, 0xC0437E9C
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
    push    {r2, r3, r4, r5, ip, lr}
    /* 2026-09-13:守衛從「FLAG」擴成「FLAG 或 PBFLAG」。
     * 回放我們的片子時 FLAG 是 0(OG3K 不一定被選中),但顯示輸出一樣需要
     * 3:2 的描述子 —— 否則畫面正確卻被壓進 16:9 的視窗(截圖 SS__0427:
     * 內容清晰但垂直壓扁)。PBFLAG 由 og3kname 從真實片源尺寸 3008x2000 設,
     * 已由 og3kpbsel 的 40 命中 / 36 放行證明它確實跟著片子走。 */
    LDA     ip, FLAG
    ldr     ip, [ip]
    cmp     ip, #0
#ifdef TARGET_MATCH
    /* 2026-09-27:條件從「FLAG」收緊成「FLAG && PICKOK」。
     * FLAG==0 就跳過第二次載入,旗標仍是第一次 cmp 的結果(EQ);
     * FLAG!=0 才看 PICKOK,旗標換成它的結果。所以下面原本那幾條
     * 一個字都不用改。 */
    beq     pickdone
    LDA     ip, PICKOK
    ldr     ip, [ip]
    cmp     ip, #0
pickdone:
#endif
    bne     armed
    LDA     ip, PBFLAG
    ldr     ip, [ip]
    cmp     ip, #0
    beq     logonly                  @ 兩個旗標都沒立:只記錄,不改任何東西
armed:
    cmp     r1, #0
    beq     case0
    cmp     r1, #2
    beq     case2
    b       restore
case0:
    LDA     ip, TPL0
    ldr     r2, [ip]
    cmp     r2, #0
    bne     give
    movw    r4, #1620                @ 預期的原廠 16:9 尺寸
    movw    r5, #911
    movw    r3, #1080                @ 換成拍照模式的高
    b       build
case2:
    LDA     ip, TPL2
    ldr     r2, [ip]
    cmp     r2, #0
    bne     give
    movw    r4, #320
    movw    r5, #180
    movw    r3, #213
build:
    ldr     r2, [r0, r1, lsl #3]     @ 原廠描述子
    LDA     lr, 0xC0000000
    cmp     r2, lr
    blo     reject
    LDA     lr, 0xC4000000
    cmp     r2, lr
    bhs     reject
    ldr     lr, [r2]
    cmp     lr, r4
    bne     reject
    ldr     lr, [r2, #4]
    cmp     lr, r5
    bne     reject
    mov     r4, r3                   @ 守衛過了,r4/r5 改作他用
    mov     r5, r2
    mov     r2, #0
copy:
    ldr     r3, [r5, r2]             @ 整份 44 bytes 複製
    add     lr, ip, r2
    str     r3, [lr, #4]
    add     r2, r2, #4
    cmp     r2, #44
    blo     copy
    str     r4, [ip, #0x08]          @ 只改 +04 與 +14 的高度
    str     r4, [ip, #0x18]
    mov     r4, #1
    str     r4, [ip]
give:
    LDA     r2, HITS
    ldr     r3, [r2]
    add     r3, r3, #1
    str     r3, [r2]
    add     r0, ip, #4
    pop     {r2, r3, r4, r5, ip, lr}
    bx      lr

/* 2026-09-13:FLAG = 0 時也走一遍拒絕環,只記錄不改。
 * 目的是量出**回放**實際使用的描述子 —— 回放不看 FLAG(OG3K 可能根本沒被
 * 選中),所以原本的 `beq restore` 讓這個 hook 在回放期間完全沒有紀錄:
 * 實測 命中 0 / 拒絕 0,查不出回放用什麼幾何。
 * 只借用既有的去重環,不新增 hook 點。 */
logonly:
    ldr     r2, [r0, r1, lsl #3]
    LDA     lr, 0xC0000000
    cmp     r2, lr
    blo     restore
    LDA     lr, 0xC4000000
    cmp     r2, lr
    bhs     restore
    b       reject

/* 記下沒被處理到的描述子,去重,最多 6 筆。r2 仍是描述子指標。 */
reject:
    LDA     ip, REJ
    ldr     r3, [ip]
    mov     r4, #0
rscan:
    cmp     r4, r3
    beq     radd
    add     lr, ip, r4, lsl #2
    add     lr, lr, r4, lsl #3       @ ip + r4*12
    ldr     r5, [lr, #4]
    cmp     r5, r1
    bne     rnext
    ldr     r5, [lr, #8]
    ldr     lr, [r2]
    cmp     r5, lr
    beq     restore                  @ 這筆記過了
rnext:
    add     r4, r4, #1
    b       rscan
radd:
    cmp     r3, #6
    bhs     restore
    add     lr, ip, r3, lsl #2
    add     lr, lr, r3, lsl #3
    str     r1, [lr, #4]             @ idx
    ldr     r4, [r2]
    str     r4, [lr, #8]             @ W
    ldr     r4, [r2, #4]
    str     r4, [lr, #12]            @ H
    add     r3, r3, #1
    str     r3, [ip]
restore:
    pop     {r2, r3, r4, r5, ip, lr}
out:
#ifdef OG_CHAIN
    OG_PASS                     @ Loader v3: the layer below, or og_replay
.global og_replay
og_replay:
#endif
    push    {r4, r5, lr}             @ displaced
    LDA     ip, BACK
    bx      ip
