.syntax unified
.arm
.text
#include "og_pic.inc"
/* ============================================================================
 * og3krecipe — 七個軸 -> 一張配方。**靜態格式表就是被這個取代的。**
 * ============================================================================
 *
 * OG3K/OG2K/OG6K/HSW 各自把「哪個 donor、什麼時序、多大的畫布」寫死成一張
 * 八到十列的表。全功能版的這些值取決於七個活變數,窮舉組合會爆,所以改成
 * 當場算:讀 AXIS,算出 RECIPE,fmttable / og3kcanvas / og3kfps 都讀 RECIPE。
 *
 * 規格在 build/imx410_block.py 的 expected_recipe() —— 那份 Python 產生的字
 * 與這裡產生的字必須**逐字相同**,test_imx410_recipe.py 對著跑。
 *
 * 呼叫時機:fmttable 命中自家標籤時先呼叫這裡。它自己比對 AXIS 快照,
 * 沒變就立刻返回(約 12 條指令),所以放在熱路徑上也無所謂。不需要 hook
 * 七個 setter,也就沒有「setter 漏掉一個就用到舊值」這種失效模式。
 *
 * 相機上刻意不做的事:
 *   浮點      —— 引擎格率的 float bits 由主機先算好放進 RATE 表。
 *   除法解時序 —— 全 70 個模式只用到 6 種 hmax,所以 6 x 11 的預算表就夠了。
 *                 這顆核心的 **ARM 模式**有沒有 udiv 沒有確認過(只在 Thumb
 *                 碼裡見過,0xC0630F74),繞開它比賭它安全。
 *   64 位元   —— 最大的中間值是 6064 x 1024 = 6,209,536,遠在 32 位元內。
 *
 * 幾何那三個除法躲不掉(RWZM 是任意數字),用下面的 udivs 軟除法。
 *
 * 表基底不寫死:從 imager 物件拿,這樣萬一表被搬走也跟得上。
 *     [0xC343B588]      -> 描述子(實機讀到 0xC2F1E654)
 *     描述子 +0x08      -> metadata 基底(實機 0xC0B59DC0)
 *     描述子 +0x0C      -> 筆數(實機 70)
 * metadata 一筆 0x64 bytes:+0x00 mode id  +0x04/+0x08 光柵  +0x3C 位深列舉
 *                          +0x50 Y scale  +0x5C vblank
 * timing 一筆 0x20:+0x00 mode id  +0x04 hmax|tail<<16  +0x08 vmax|x<<16
 * ========================================================================== */

#ifndef AXIS
.equ AXIS,    OGA(0xC0733000)        /* 九個字,選單寫 */
#endif
#ifndef RECIPE
.equ RECIPE,  OGA(0xC0733040)        /* 二十個字,本檔寫 */
#endif
#ifndef RATETAB
.equ RATETAB, OGA(0xC0733100)        /* 11 x 12 bytes */
#endif
#ifndef TMGTAB
.equ TMGTAB,  OGA(0xC0733200)        /* 6 x 11 x 4 bytes */
#endif
#ifndef CTMPL
.equ CTMPL,   OGA(0xC0733280)        /* 畫布模板,21 筆 + 表尾 */
#endif
#ifndef CANVAS
.equ CANVAS,  OGA(0xC0733300)        /* +0x00 對數,之後 (位移, 值) 陣列 */
#endif
#ifndef ASPTAB
.equ ASPTAB,  OGA(0xC07332C0)        /* 5 個 enum 的定點比例 x1024 */
#endif
/* >60 fps 的判斷寫成整數:fps > 60 <=> 週期數 < 72e6/60 = 1,200,000 */
.equ OVER60_CYCLES, 1200000
.equ IMAGER,  0xC343B588        /* [這裡] = 模式表描述子 */

.equ N_RATE,  11
.equ META_STRIDE, 0x64
.equ TMG_STRIDE,  0x20

/* RECIPE 的字索引(與 imx410_block.py 的 R_* 一致) */
.equ R_VALID, 9*4
.equ R_MODE,  10*4
.equ R_IDX,   11*4
.equ R_TW0,   12*4
.equ R_TW1,   13*4
.equ R_RECW,  14*4
.equ R_RECH,  15*4
.equ R_ACTW,  16*4
.equ R_ACTH,  17*4
.equ R_NOM,   18*4
.equ R_EFPS,  19*4
.equ R_ASPECT, 20*4
.equ R_SAVE0,  21*4
.equ R_SAVE1,  22*4
/* 這四個連續,畫布模板的來源代碼 9..12 直接對過來。 */
.equ R_HBIN_E, 23*4
.equ R_VBIN_E, 24*4
.equ R_ZH,     25*4
.equ R_ZV,     26*4
.equ RWZM_UNITY, 1024           /* 韌體把 RWZM 下夾在這個值(DAT_c0b56538) */

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
    push    {r3, r4-r11, lr}      @ 偶數個 —— 維持 8-byte 對齊

/* ---- 1. AXIS 沒變就直接回 ------------------------------------------------
 * 用快照比對而不是世代計數器:選單那側只要把值寫進 AXIS 就好,不必記得
 * 通知我們。少一個「忘了通知」的失效模式。 */
    LDA     r0, AXIS
    LDA     r1, RECIPE
    mov     r2, #0
1:  ldr     r3, [r0, r2]
    ldr     r4, [r1, r2]
    cmp     r3, r4
    bne     recompute
    add     r2, r2, #4
    cmp     r2, #36                 @ 9 個字
    blo     1b
    pop     {r3, r4-r11, pc}

recompute:
    /* ★ 先把**上一個 donor** 的時序還原成原廠值。
     * imx410_fmt 每次命中都會改 donor 的時序記錄,而 donor 是變動的 ——
     * 不還原的話,配方借過 mode 106 之後切回原廠 FHD30 就拿到我們的時序。
     * og3k_plan 那邊 donor 固定,所以它用寫死的常數;這裡查 STOCKTMG。 */
    ldr     r3, [r1, #R_VALID]
    cmp     r3, #0
    beq     no_restore
    ldr     r3, [r1, #R_IDX]
    cmp     r3, #70
    bhs     no_restore                  @ 索引不合理 -> 不動,故障安全
    ldr     r5, [r1, #R_SAVE0]
    ldr     r6, [r1, #R_SAVE1]
    cmp     r5, #0
    beq     no_restore                  @ 沒存過 -> 沒動過
    LDA     r2, IMAGER
    ldr     r2, [r2]
    ldr     r2, [r2]                    @ 時序表基底
    add     r2, r2, r3, lsl #5
    str     r5, [r2, #4]
    str     r6, [r2, #8]
no_restore:

    /* 快照更新,結果欄先全部清零 —— valid=0 就是「沒有 mode 對應」,
     * 這是故障安全值:fmttable 會走 FHD fallback,不會拿到半套配方。 */
    mov     r2, #0
2:  ldr     r3, [r0, r2]
    str     r3, [r1, r2]
    add     r2, r2, #4
    cmp     r2, #36
    blo     2b
    mov     r3, #0
3:  str     r3, [r1, r2]
    add     r2, r2, #4
    cmp     r2, #80                 @ 20 個字
    blo     3b

/* ---- 2. 幾何 -------------------------------------------------------------
 * rec_w = ((raster_w / hbin) * 1024 / rwzm_h) 向下對齊到 step
 * rec_h = ((raster_h / vbin) * 1024 / rwzm_v) 向下取偶
 * step 由位深決定:10/14-bit 要 16、12-bit 要 8、8-bit 要 4,但統一取 16 ——
 * 16 同時滿足四個深度,換位深不必重算幾何(見 IMX410_FULL_DESIGN §3)。 */
    ldr     r5, [r0, #16]           @ hbin | vbin<<16
    ldr     r6, [r0, #8]            @ raster_w
    and     r7, r5, #0xFF
    mov     r8, r6
    mov     r0, r8
    mov     r1, r7
    bl      udivs                   @ r0 = raster_w / hbin
    lsl     r0, r0, #10             @ x 1024
    LDA     r1, AXIS
    ldr     r1, [r1, #20]           @ rwzm_h (A_ZH)
    bl      udivs
    bic     r0, r0, #15             @ 對齊 16
    LDA     r1, RECIPE
    str     r0, [r1, #R_RECW]
    mov     r9, r0                  @ 留著算裁切

    LDA     r0, AXIS
    ldr     r6, [r0, #12]           @ raster_h
    lsr     r7, r5, #16             @ vbin
    mov     r0, r6
    mov     r1, r7
    bl      udivs
    lsl     r0, r0, #10
    LDA     r1, AXIS
    ldr     r1, [r1, #24]           @ rwzm_v (A_ZV)
    bl      udivs
    bic     r0, r0, #1              @ 取偶
    LDA     r1, RECIPE
    str     r0, [r1, #R_RECH]
    mov     r10, r0

    /* CRCT 的列舉與 RWZM 的值也要進畫布 —— 沒有它們,hbin/vbin 與 RWZM
     * 兩個軸只會把宣告的幾何縮小,卻不真的程式化硬體。列舉是 (x-1)>>1:
     * hbin 1/3/5 -> 0/1/2,vbin 1/3 -> 0/1(FUN_c022ee10 / FUN_c022ee90)。 */
    and     r0, r5, #0xFF           @ hbin
    sub     r0, r0, #1
    lsr     r0, r0, #1
    str     r0, [r1, #R_HBIN_E]
    lsr     r0, r5, #16             @ vbin
    sub     r0, r0, #1
    lsr     r0, r0, #1
    str     r0, [r1, #R_VBIN_E]
    LDA     r0, AXIS
    ldr     r2, [r0, #20]           @ rwzm_h
    str     r2, [r1, #R_ZH]
    ldr     r2, [r0, #24]           @ rwzm_v
    str     r2, [r1, #R_ZV]

/* ---- 3. 裁切 —— AXIS 給 0 就用原廠留邊慣例(16 寬 / 10 高)------------- */
    LDA     r0, AXIS
    ldr     r2, [r0, #28]           @ crop:w | h<<16 (A_CROP)
    mov     r3, r2, lsr #16
    uxth    r2, r2
    cmp     r2, #0
    cmpne   r3, #0
    bne     4f
    sub     r2, r9, #16
    bic     r2, r2, #15
    sub     r3, r10, #10
    bic     r3, r3, #1
4:  LDA     r1, RECIPE
    str     r2, [r1, #R_ACTW]
    str     r3, [r1, #R_ACTH]

/* ---- 4. 格率常數:RATETAB[ridx] = (週期數, 標稱, 引擎 float bits) ------ */
    LDA     r0, AXIS
    ldr     r4, [r0, #4]            @ rate 索引
    cmp     r4, #N_RATE
    bhs     done                    @ 索引壞掉 -> valid 留 0
    add     r2, r4, r4, lsl #1      @ x3
    LDA     r3, RATETAB
    add     r3, r3, r2, lsl #2      @ x4 -> x12
    ldr     r11, [r3]               @ r11 = 週期數,整個掃描都要用
    ldr     r2, [r3, #4]
    str     r2, [r1, #R_NOM]
    ldr     r2, [r3, #8]
    str     r2, [r1, #R_EFPS]

/* ---- 5. 掃 metadata 挑 donor --------------------------------------------
 * 通過條件:光柵相符、位深相符、(有指定就)mode 相符、消隱餘裕夠。
 * 排名壓成一個可比較的字,取最小:
 *     bit31 不是 quiet   bit30 不是 native   bit9..18 (1023-hmax)   bit0..8 mid
 * 與 imx410_block.py 的 key 逐位元相同。 */
    LDA     r0, IMAGER
    ldr     r0, [r0]                @ 描述子
    ldr     r5, [r0, #8]            @ metadata 基底
    ldr     r6, [r0, #12]           @ 筆數
    mov     r7, #0                  @ 索引
    mvn     r8, #0                  @ 目前最好的排名 = 0xFFFFFFFF
    mov     r12, #0                 @ 目前最好的 metadata 列位址

scan:
    cmp     r7, r6
    bhs     picked
    mov     r0, #META_STRIDE
    mla     r2, r7, r0, r5          @ r2 = 這一列

    LDA     r3, AXIS
    ldr     r0, [r2, #4]            @ 光柵寬
    ldr     r1, [r3, #8]
    cmp     r0, r1
    bne     next
    ldr     r0, [r2, #8]            @ 光柵高
    ldr     r1, [r3, #12]
    cmp     r0, r1
    bne     next

    /* 位深:metadata +0x3C 的列舉 0=RAW12 1=RAW14 2=RAW16 3=RAW12 4=RAW8。
     * AXIS 的 bit 是 14 就要 enum 1,其餘要 enum 0 或 3。 */
    ldr     r0, [r2, #0x3C]
    ldr     r1, [r3]                @ bit
    cmp     r1, #14
    beq     want14
    cmp     r0, #0
    cmpne   r0, #3
    bne     next
    b       depthok
want14:
    cmp     r0, #1
    bne     next
depthok:

    /* 指定了 mode 就只收那一個 */
    ldr     r0, [r3, #32]           @ mode_force
    cmp     r0, #0
    beq     nomforce
    ldr     r1, [r2]                @ 這一列的 mode id
    cmp     r0, r1
    bne     next
nomforce:

    /* 時序列:與 metadata 同一個索引。hmax 必須是六種之一,
     * 不是的話預算表查不到,直接跳過。 */
    ldr     r0, [r2]                @ mode id
    LDA     r1, IMAGER
    ldr     r1, [r1]
    ldr     r1, [r1]                @ timing 基底
    add     r1, r1, r7, lsl #5      @ x 0x20
    ldr     r4, [r1, #4]            @ hmax | tail<<16
    uxth    r4, r4                  @ r4 = hmax
    bl      hmax_index              @ r0 = 0..5,或 -1
    cmp     r0, #0
    blt     next
    mov     r9, r0                  @ 留著查表

    /* 消隱餘裕:cycles/hmax - rows >= vblank
     * 改寫成不必除法的形式:cycles >= (rows + vblank) * hmax */
    ldr     r0, [r2, #8]            @ 光柵高
    ldr     r1, [r2, #0x5C]         @ vblank
    add     r0, r0, r1
    mul     r0, r0, r4
    cmp     r11, r0
    blo     next

    /* 排名 */
    ldr     r0, [r2]                @ mode id
    ubfx    r0, r0, #0, #9          @ mode id 取低 9 位(最大 221,防禦用)
    movw    r1, #1023
    sub     r1, r1, r4
    orr     r0, r0, r1, lsl #9
    /* native:原廠時序的週期數 == 目標週期數 */
    LDA     r1, IMAGER
    ldr     r1, [r1]
    ldr     r1, [r1]
    add     r1, r1, r7, lsl #5
    ldr     r3, [r1, #4]
    lsr     r3, r3, #16             @ tail
    ldr     r1, [r1, #8]
    uxth    r1, r1                  @ vmax
    sub     r1, r1, #1
    mla     r1, r1, r4, r3          @ hmax*(vmax-1)+tail
    cmp     r1, r11
    orrne   r0, r0, #(1 << 30)
    /* quiet:位深不是 14 且 hmax >= 445 */
    LDA     r1, AXIS
    ldr     r1, [r1]
    cmp     r1, #14
    beq     notquiet
    movw    r1, #445
    cmp     r4, r1
    bhs     quietok
notquiet:
    orr     r0, r0, #(1 << 31)
quietok:
    cmp     r0, r8
    bhs     next
    mov     r8, r0                  @ 新的最好
    mov     r12, r2
    LDA     r1, RECIPE
    str     r7, [r1, #R_IDX]
    mov     r0, r9
    str     r0, [r1, #R_TW0]        @ 暫存 hmax 索引,下面換成真正的值
next:
    add     r7, r7, #1
    b       scan

picked:
    cmp     r12, #0
    beq     done                    @ 沒有 mode -> valid 留 0 -> FHD fallback

/* ---- 6. 時序:預算表 TMGTAB[hmax_idx * 11 + ridx] = vmax | tail<<16 ---- */
    LDA     r1, RECIPE
    ldr     r9, [r1, #R_TW0]        @ hmax 索引
    LDA     r0, AXIS
    ldr     r4, [r0, #4]            @ ridx
    mov     r2, #N_RATE
    mla     r2, r9, r2, r4
    LDA     r3, TMGTAB
    ldr     r2, [r3, r2, lsl #2]
    cmp     r2, #0
    beq     fail                    @ 這個 (hmax, 格率) 解不出來

    ldr     r0, [r12]               @ mode id
    str     r0, [r1, #R_MODE]
    /* 這一列自己的 timing 記錄,拿 hmax 與 x_start */
    ldr     r3, [r1, #R_IDX]
    LDA     r0, IMAGER
    ldr     r0, [r0]
    ldr     r0, [r0]
    add     r0, r0, r3, lsl #5
    ldr     r4, [r0, #4]
    ldr     r5, [r0, #8]
    /* 存下這個 donor 的**原廠**時序。現在讀到的一定是原廠值 —— og3krecipe
     * 跑在 imx410_fmt 寫入之前,而換配方時上面已經先把舊的還原掉了。
     * ★ 必須在這裡存:r0 再過幾條就被 orr 的結果蓋掉了。 */
    str     r4, [r1, #R_SAVE0]
    str     r5, [r1, #R_SAVE1]
    uxth    r4, r4                  @ hmax
    lsr     r5, r5, #16             @ x_start

    lsr     r6, r2, #16             @ tail
    uxth    r2, r2                  @ vmax
    orr     r0, r4, r6, lsl #16
    str     r0, [r1, #R_TW0]
    orr     r0, r2, r5, lsl #16
    str     r0, [r1, #R_TW1]
    mov     r0, #1
    str     r0, [r1, #R_VALID]
    bl      aspect_pick
    bl      canvas_emit
    pop     {r3, r4-r11, pc}

fail:
    LDA     r1, RECIPE
    mov     r0, #0
    str     r0, [r1, #R_TW0]
    str     r0, [r1, #R_IDX]
done:
    /* 沒解出來就把畫布對數歸零。留著上一組配方的陣列 = 用舊幾何錄新設定,
     * 那比什麼都不寫更糟。 */
    LDA     r0, CANVAS
    mov     r1, #0
    str     r1, [r0]
    pop     {r3, r4-r11, pc}

/* ---- 長寬比 enum ---------------------------------------------------------
 * 顯示比例 = **錄下的像素** act_w : act_h(2026-10-04 使用者:「壓扁才是他真實的
 * 樣子」—— LV 與錄影中都顯示像素原本的形狀,跟打開 DNG 一樣)。
 *
 * 以前乘 mode 的 geometry scale(+0x4C/+0x50)和 RWZM,換算成「感測器上的形狀」:
 * mode 12(3x6)的 2000x662 會被還原成 3:2(HSW 寫死 2 的理由)。但 mode 10
 * (metadata 1x1)就照像素顯示 3:1 —— 兩個同樣是扁像素的 mode 顯示規則不一樣,
 * 而且待機與錄影的預覽也對不上。現在一律照像素。
 *
 * 比較用定點:r = act_w * 1024 / act_h,再和 ASPTAB 的五個常數比絕對差。
 * **不可以比 |w*y - h*x|** —— 那個量會被 y 縮放。溢位:6064 x 1024 = 6.2M。 */
aspect_pick:
    push    {r4-r8, lr}
    LDA     r7, RECIPE
    ldr     r4, [r7, #R_ACTW]
    ldr     r5, [r7, #R_ACTH]
    lsl     r0, r4, #10
    mov     r1, r5
    bl      udivs                   @ r0 = 定點顯示比(像素)
    mov     r4, r0
ap_noz:
    LDA     r5, ASPTAB
    mov     r6, #0                  @ 索引
    mvn     r8, #0                  @ 目前最小誤差
    mov     r1, #3                  @ 目前最好的 enum,預設 16:9
ap_loop:
    ldr     r0, [r5, r6, lsl #2]
    subs    r0, r4, r0
    rsblt   r0, r0, #0              @ 絕對值
    cmp     r0, r8
    movlo   r8, r0
    addlo   r1, r6, #1              @ enum = 索引 + 1
    add     r6, r6, #1
    cmp     r6, #5
    blo     ap_loop
    str     r1, [r7, #R_ASPECT]
    pop     {r4-r8, pc}

/* ---- 畫布 (位移, 值) 陣列 ------------------------------------------------
 * 走 CTMPL,一筆一個字:位移 16 位元 | 來源 8 位元 | 閘門 8 位元,0xFFFFFFFF
 * 是表尾。閘門 1 = 只有 >60 fps 才寫。
 *
 * 這一段取代 og3kcanvas.S 那 32 個 PUT(x3 字)+ 2 個 PUTW(x4 字)= 104 個字
 * 把常數編進指令的做法。值變成資料,幾何才可能是動態的。
 *
 * 來源代碼:0 rec_w  1 rec_h  2 act_w  3 act_h —— 這四個在 RECIPE 裡剛好連續
 * (R_RECW..R_ACTH),所以直接 RECIPE + R_RECW + src*4。
 *          4 預覽平面碼  5 RAW 平面碼  6 常數 1  7 常數 0  8 常數 2.0f */
canvas_emit:
    push    {r4-r8, lr}
    LDA     r7, RECIPE
    LDA     r5, CTMPL
    LDA     r6, CANVAS
    add     r6, r6, #4
    mov     r8, #0                  @ 對數

    /* r4 = 閘門位元圖,bit N = 閘門 N 成立。
     *   bit0 一律成立(CG_ALWAYS)
     *   bit1 = >60 fps(CG_OVER60)
     *   bit4 = RWZM 非 unity(CG_ZOOM)
     * 這樣 ce_loop 用一次 tst 就能分派任意閘門,不必每加一個就多一條分支。
     * ★ 加 bit4 之前 CG_ZOOM 是**安裝時**決定的,於是「執行期改了 RWZM,
     *   RECIPE 完全正確地跟著變而硬體不動」—— 2026-09-28 的假通過。 */
    mov     r4, #1                  @ bit0:CG_ALWAYS

    /* >60 fps?週期數 < 1,200,000 就是。 */
    LDA     r0, AXIS
    ldr     r0, [r0, #4]            @ rate 索引
    add     r1, r0, r0, lsl #1
    LDA     r2, RATETAB
    ldr     r1, [r2, r1, lsl #2]    @ 週期數
    LDA     r0, OVER60_CYCLES
    cmp     r1, r0
    orrlo   r4, r4, #(1 << 1)       @ bit1:CG_OVER60

    /* RWZM 非 unity?R_ZH / R_ZV 任一個 != 1024 就算。 */
    ldr     r0, [r7, #R_ZH]
    ldr     r1, [r7, #R_ZV]
    cmp     r0, #RWZM_UNITY
    cmpeq   r1, #RWZM_UNITY
    orrne   r4, r4, #(1 << 4)       @ bit4:CG_ZOOM

ce_loop:
    ldr     r0, [r5], #4
    cmn     r0, #1
    beq     ce_done                 @ 0xFFFFFFFF = 表尾
    lsr     r1, r0, #24             @ 閘門編號
    mov     r2, #1
    lsl     r2, r2, r1
    tst     r4, r2
    beq     ce_loop                 @ 閘門不成立 -> 跳過(不認識的閘門也跳過)
ce_take:
    ubfx    r2, r0, #16, #8         @ 來源
    uxth    r0, r0                  @ 位移
    cmp     r2, #9
    blo     ce_notbin
    /* 9..12 -> RECIPE 的 R_HBIN_E..R_ZV(四個字連續) */
    sub     r2, r2, #9
    add     r1, r7, #R_HBIN_E
    ldr     r1, [r1, r2, lsl #2]
    b       ce_store
ce_notbin:
    cmp     r2, #4
    bhs     ce_special
    add     r1, r7, #R_RECW
    ldr     r1, [r1, r2, lsl #2]    @ rec_w / rec_h / act_w / act_h
    b       ce_store
ce_special:
    cmp     r2, #6
    bhs     ce_const
    /* 平面格式碼:依位深查 plane_tab,一筆兩個半字 (預覽, RAW) */
    LDA     r1, AXIS
    ldr     r1, [r1]                @ bit
    adr     r3, plane_tab
ce_pl:
    ldrh    ip, [r3]
    cmp     ip, #0
    beq     ce_pl_dflt
    cmp     ip, r1
    beq     ce_pl_hit
    add     r3, r3, #6
    b       ce_pl
ce_pl_dflt:
    sub     r3, r3, #6              @ 表尾之前那一筆 = 12-bit
ce_pl_hit:
    sub     r2, r2, #4              @ 0 = 預覽,1 = RAW
    add     r3, r3, #2
    add     r3, r3, r2, lsl #1      @ ARM 的 ldrh 不吃縮放暫存器位移
    ldrh    r1, [r3]
    b       ce_store
ce_const:
    sub     r2, r2, #6
    adr     r3, const_tab
    ldr     r1, [r3, r2, lsl #2]
ce_store:
    str     r0, [r6], #4
    str     r1, [r6], #4
    add     r8, r8, #1
    b       ce_loop
ce_done:
    LDA     r0, CANVAS
    str     r8, [r0]
    pop     {r4-r8, pc}

.align 2
/* (位深, 預覽平面碼, RAW 平面碼),0 結尾。12-bit 放最後一筆當預設。 */
plane_tab:
    .short  8, 10, 10
    .short  10, 10, 9
    .short  14, 7, 8       /* RAW 平面 8 = 16 bpp 容器,見 §4.3 */
    .short  12, 7, 7
    .short  0, 0, 0
.align 2
const_tab:
    .word   1, 0, 0x40000000

/* ---- hmax -> 0..5,查不到回 -1 ------------------------------------------ */
hmax_index:
    push    {r1, r2, r3, lr}      @ 偶數個
    adr     r1, hmax_set
    mov     r0, #0
5:  ldr     r2, [r1, r0, lsl #2]
    cmp     r2, r4
    beq     6f
    add     r0, r0, #1
    cmp     r0, #6
    blo     5b
    mvn     r0, #0
6:  pop     {r1, r2, r3, pc}

.align 2
hmax_set:
    .word   330, 360, 395, 445, 450, 911

/* ---- 軟除法 r0 / r1 -> r0 ------------------------------------------------
 * 這顆核心的 ARM 模式有沒有 udiv 沒有確認過,所以自己做。只在重算時跑
 * 四次,快慢無所謂。 */
udivs:
    push    {r1, r2, r3, lr}      @ 偶數個。**不可以放 r0** —— 回傳值在 r0
    cmp     r1, #0
    beq     8f                      @ 除以 0 -> 回 0,故障安全
    mov     r2, #0                  @ 商
    mov     r3, #1                  @ 目前的位
7:  cmp     r1, r0
    bhs     9f
    tst     r1, #0x80000000         @ 再左移就溢位了,停
    bne     9f
    lsl     r1, r1, #1
    lsl     r3, r3, #1
    b       7b
9:  cmp     r0, r1
    subhs   r0, r0, r1
    addhs   r2, r2, r3
    lsrs    r3, r3, #1
    lsr     r1, r1, #1
    bne     9b
    mov     r0, r2
    pop     {r1, r2, r3, pc}
8:  mov     r0, #0
    pop     {r1, r2, r3, pc}
