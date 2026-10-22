.syntax unified
.arm
.text
/* ============================================================================
 * cfgobs — 觀測 XC_LiveViewConfiguratorW71c1__v3 的請求(param_2)。
 * ============================================================================
 * 目的:直接比對「S 尺寸照片檢視」與「OG3K 影片回放」各自帶什麼請求。
 *
 * 配置器用 *param_2 選分支:
 *     0,1,2 → 各自的 live 分支
 *     3,4   → FUN_c043bb20  照片(*param_2==4 → 拍攝表 0xC0BE5D70,否則檢視表 5CF0)
 *     5     → FUN_c043bc68  影片回放
 *                param_2+0x20 == 4 → 表 0xC0BE4508(+0x80 = 0x1000A,8-bit)
 *                            == 3 → 表 0xC0BE4548(0x10009,10-bit)
 *                            否則 → 表 0xC0BE4588(0x10007,12-bit)
 *
 * 實測回放拿到 p51 = 0x4508 的第 0 筆,也就是 8-bit 表,但檔案是 12-bit。
 * 這個 payload 就是去確認 param_2+0x20 到底是多少、以及照片那邊是多少。
 *
 * Hook:0xC043BE68(函式進入點,B,回放位移的 push 後跳回 0xC043BE6C)。
 * r0 = param_1(不動,後面 mov r6,r0 要用),r1 = param_2。
 *
 * LOG 佈局(0xC0732600):
 *   +0x00 總呼叫次數
 *   +0x04 已用格數
 *   +0x10 起,每格 64 bytes:param_1(**指標本身**), param_2[0..10]
 * 依 (param_2[0], param_2[8]) 去重,最多 7 格。
 *
 * 2026-09-13 v1 一進回放就凍結。v1 在新格子裡做 `ldr lr, [r0]` 去解參考
 * param_1 —— 但配置器的條件是 `(*param_2 - 3U < 3) || (*param_1 < 1)`,
 * **短路**:mode 3/4/5 時原廠根本不會讀 *param_1,那個指標在回放路徑上
 * 不保證有效。v2 只記指標的值,一個字都不解參考;r1 也先做範圍檢查。
 * ========================================================================== */

.equ LOG,   0xC0732600
.equ BACK,  0xC043BE6C
.equ SLOTS, 7

.macro LDA reg, value
    movw    \reg, #:lower16:\value
    movt    \reg, #:upper16:\value
.endm

.global entry
entry:
    push    {r1, r2, r3, r4, r5, r6, ip, lr}

    LDA     ip, LOG
    ldr     r2, [ip]
    add     r2, r2, #1
    str     r2, [ip]

    /* r1 必須像一個可讀的指標,而且 4 對齊。不像就什麼都不做。 */
    tst     r1, #3
    bne     out
    LDA     r2, 0xC0000000
    cmp     r1, r2
    blo     out
    LDA     r2, 0xC3900000
    cmp     r1, r2
    bhs     out

    ldr     r4, [ip, #4]                @ 已用格數
    add     r5, ip, #0x10               @ 第一格
    mov     r2, #0
    ldr     r3, [r1]                    @ mode
    ldr     r6, [r1, #0x20]             @ 表選擇欄位

dloop:
    cmp     r2, r4
    bge     newslot
    ldr     lr, [r5, #4]                @ 已記的 mode
    cmp     lr, r3
    bne     dnext
    ldr     lr, [r5, #0x24]             @ 已記的 param_2[8]
    cmp     lr, r6
    beq     out                         @ 這個組合記過了
dnext:
    add     r5, r5, #64
    add     r2, r2, #1
    b       dloop

newslot:
    cmp     r4, #SLOTS
    bge     out
    add     r4, r4, #1
    str     r4, [ip, #4]

    str     r0, [r5]                    @ param_1 的**指標值**,不解參考
    mov     r2, #0
cloop:
    ldr     lr, [r1, r2]
    add     r3, r5, #4
    str     lr, [r3, r2]
    add     r2, r2, #4
    cmp     r2, #44                     @ param_2[0..10]
    blt     cloop

out:
    pop     {r1, r2, r3, r4, r5, r6, ip, lr}
    push    {r4, r5, r6, lr}            @ 位移指令
    LDA     ip, BACK
    bx      ip
