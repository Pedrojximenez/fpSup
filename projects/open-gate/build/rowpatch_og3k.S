.syntax unified
.arm
.text

/*
 * Proven 3032x2012 canvas patch used by the live USB experiment.
 *
 * Hook: 0xC043A19C, reached after FUN_C0439D18 builds the 65-word
 * FieldAngle row and before downstream geometry is derived from it.
 *
 * ABI:
 *   r4 = FieldAngle object
 *   r4+0x5C = geometry row
 *   r5 = selector
 *
 * The displaced instruction is `mov r0,r4`.  The hook site uses BL and this
 * routine returns through LR after replaying that instruction.
 */

.equ LOG, 0xC0732600
.equ FLAG, 0xC0731C08
.equ ROW, 0x5C

.macro LDA reg, value
    movw    \reg, #:lower16:\value
    movt    \reg, #:upper16:\value
.endm

.macro PUT off, val
    movw    r3, #\val
    movw    r0, #\off
    str     r3, [r1, r0]
.endm

.global entry
entry:
    push    {r0, r1, r2, r3, ip, lr}

    LDA     ip, FLAG                    @ OG3K 沒被選中就完全不動手
    ldr     r3, [ip]
    cmp     r3, #0
    beq     out

    add     r1, r4, #ROW
    LDA     ip, LOG

    /* Affect only the shipping FHD CinemaDNG row. */
    ldr     r3, [r1]
    movw    r0, #1936
    cmp     r3, r0
    bne     out
    ldr     r3, [r1, #4]
    movw    r0, #1090
    cmp     r3, r0
    bne     out

    /* Preserve the first pre-overwrite producer fields for diagnosis. */
    ldr     r0, [ip]
    cmp     r0, #0
    bne     patch
    str     r5, [ip, #4]
    movw    r0, #0x0D8
    ldr     r3, [r1, r0]
    str     r3, [ip, #8]
    movw    r0, #0x0E0
    ldr     r3, [r1, r0]
    str     r3, [ip, #12]

patch:
/* ============================================================================
 * 2026-09-12 事故與退回 —— 動這個檔案之前務必讀完。
 * ============================================================================
 * 為了修錄影時的 live view,我把預覽相關欄位加進來,其中把
 *     +0xD8 / +0xE0  從 3032/2012 改成 0
 * 依據是對方文件說 +D8/+E0 只是「預覽柵格的覆寫,0 表示不覆寫」。
 *
 * 那是錯的,而且我們自己的舊註解就寫著 +0xD8 是 **producer-side** 的寬高對。
 * 關掉它之後 producer 改去讀 +0x0C/+0x10(我設成預覽的 2024x1341),於是:
 *   A001_015 起  只有左上約 1936 寬的區域有畫面,其餘是未初始化記憶體
 *   A001_047 起  連 strip 本身都縮成 3032x1341(檔案 6,179,328 而非 9,229,824)
 * 共毀掉數十段素材。
 *
 * 教訓:**這個塊的欄位不是預覽專用的。** 在沒有實際錄一段並檢查 DNG 之前,
 * 不要在這裡加任何預覽相關的寫入 —— live view 的外觀問題永遠不值得拿錄影
 * 資料去換。要改預覽,改別處(profile 表、顯示層 hook),不要改 canvas。
 *
 * 以下十個 PUT 是 A001_001..014 全部驗證正常的組合,不要再動。
 * ========================================================================== */
    PUT     0x000, 3032       /* base */
    PUT     0x004, 2012
    PUT     0x024, 3008       /* active; yields crop origin (12,6) */
    PUT     0x02C, 2000
    /* 試驗(2026-09-12,依 SS__0411 的量測):
     * 錄影時 producer 只寫 1936x1090,消費端讀 3032x2012 ——
     *   水平放大 3032/1936 = 1.566(量到 1.560,差 0.4%)
     *   垂直影像只佔 1090/2012 = 0.542(量到 0.563),上下是未寫入記憶體
     * 只改 producer 那一對讓兩邊一致。+0xD8/+0xE0 一個字都不動。 */
    PUT     0x00C, 3032       /* producer 產出寬 */
    PUT     0x010, 2012       /* producer 產出高 */
    PUT     0x020, 3000       /* 可見窗口 = DNG 裁切,所見即所錄 */
    PUT     0x028, 2000

    PUT     0x0D8, 3032       /* producer-side width/height pair */
    PUT     0x0E0, 2012
    PUT     0x0DC, 3032       /* size-getter override */
    PUT     0x0E4, 2012
    PUT     0x0F4, 3032       /* input */
    PUT     0x0F8, 2012

    ldr     r3, [ip]
    add     r3, r3, #1
    str     r3, [ip]

out:
    pop     {r0, r1, r2, r3, ip, lr}
    mov     r0, r4
    bx      lr
