.syntax unified
.arm
.text
#include "og_pic.inc"
/* ============================================================================
 * og3kcanvas — 0xC043A19C 一個 hook,兩個 case。都只改畫布的 RAM 複本。
 * ============================================================================
 *
 * case A:錄影(r5 == 83)
 *   記錄尺寸 3032x2012 → **3024x2010**,遵守 fp 自己的邊界慣例。
 *   原廠三個影片錄影 profile 全是「裁切 +16 寬 / +10 高」而且寬度 16 對齊:
 *       p171 3856x2170 / 3840x2160    p173 1936x1090 / 1920x1080
 *   p83 是照片 profile,用感測器視窗 3032x2012(+24/+12,3032 只有 8 對齊)。
 *   2026-09-13 已解檔驗證:A001_036 標頭 3024x2010、裁切 3008x2000 @ (8,5)、
 *   StripByteCounts 9,117,360 = 3024x2010x1.5,整幅影像清晰無剪切。
 *
 * case B:回放(畫布 +0x80 的 bit16 = 壓縮位元流類,且 PBFLAG == 1)
 *   把柵格設成**與片子記錄尺寸完全相同**的 3024x2010。
 *
 *   理由:原廠回放 profile 的柵格**正好等於該格式片子的記錄寬高** ——
 *       p53 (FHD 回放) 柵格 1936x1090 = FHD 片子的 1936x1090
 *       p51 (UHD 回放) 柵格 3856x2170 = UHD 片子的 3856x2170
 *   所以柵格就是「來源列距」。我們的片子沒有對應的 profile,退回值是
 *   p51(3856)或 p53(1936),兩者都與 3024 不符 → 花屏。
 *
 *   ⚠️ 2026-09-13 我試過這個 hook 並結論「沒反應」,但當時填的是 2024x1341
 *   (照 p43 抄的),**不是片子的實際寬度**。那個實驗的值填錯了,
 *   結論不成立,已收回。這一版填的是與檔案完全相同的尺寸。
 *
 *   柵格 = 視窗時縮放比應為 unity,所以 +0x60/+0xD0/+0x64/+0xD4 一併設 1024。
 *
 * Hook:0xC043A19C(BL,位移指令 mov r0,r4)。r5 = profile id,r4+0x5C = 畫布。
 * LOG(0xC0732A00):+0 錄影命中  +4 回放命中  +8 最後 profile id
 * ========================================================================== */

.equ ROW,    0x5C
.equ LOG,    OGA(0xC0732A00)
.equ FLAG,   OGA(0xC0731C08)
.equ PBFLAG, OGA(0xC0731C0C)
/* 目標參數。armasm.assemble(src, defines=[...]) 會把它們當 -D 傳給 clang,
 * 而檔名是 .S(大寫)所以前處理器有跑。沒有定義時就是 OG3K 的值,
 * 這樣既有的 OG3K 建置逐位元組不變。 */
#ifndef TARGET_PROF
#define TARGET_PROF 83          /* 已驗證的 donor;p221 見 og3k_plan 的回退說明 */
#define TARGET_W    3024
#define TARGET_H    2010
#define TARGET_AW   3008
#define TARGET_AH   2000
#endif

.equ PROF,   TARGET_PROF
.equ W,      TARGET_W
.equ H,      TARGET_H
.equ AW,     TARGET_AW
.equ AH,     TARGET_AH
.equ POOLINIT, OGA(0xC0730500)      @ poolinit.S 的入口
.equ POOLFLAG, OGA(0xC0731C18)      @ 池深一次性旗標(0 = 還沒換過)
.equ POOLPTR,  0xC2F1F3D8      @ MPoolFixed<4380U,96U> 的物件指標
.equ POOLVPTR, 0xC0B99474      @ 它的 vtable
.equ POOLSTR,  0x1128          @ 每塊 4380 + 12
.equ POOLHDR,  0x1130          @ 表頭長度 = node0 的位移
.equ POOLCNT,  0x112C          @ 剩餘數欄位
#ifdef TARGET_POOLDEPTH
.equ POOLN,    TARGET_POOLDEPTH
.equ POOLSZ,   (0x1130 + TARGET_POOLDEPTH * 0x1128)
#endif
.equ HEAPNEW,  0xC001CF78      @ FUN_c001CF78(id) -> heap 物件
.equ HEAPGET,  0xC001CFD8      @ FUN_c001CFD8(heap, &slot, size, align, tag)
.equ MEMSET,   0xC0015058      @ FUN_c0015058(dst, val, len)
.equ POOLSLOT, OGA(0xC0731C1C)      @ HEAPGET 的三字輸出槽
.equ BITLATCH, OGA(0xC0731C14)       @ fmttable 命中 OG3K 時鎖存的 eRawBitType
#ifdef TARGET_ENGFPS
.equ FPSLATCH, TARGET_ENGFPS    @ fmttable 鎖存的引擎格率(float bits)
#endif
.equ BD10,   3
.equ BD8,    4

.macro LDA reg, value
#ifdef OG_V3
    OGLDA   \reg, \value
#else
    movw    \reg, #:lower16:\value
    movt    \reg, #:upper16:\value
#endif
.endm

.macro PUT off, val
    movw    r3, #\val
    movw    r0, #\off
    str     r3, [r1, r0]
.endm

/* 32-bit 常數版。PUT 用 movw 只能帶 16 位元,而 +0x0FC/+0x100 是浮點 2.0f
 * (0x40000000)。check() 對 PUTW 與 PUT 一視同仁。 */
.macro PUTW off, val
    movw    r3, #:lower16:\val
    movt    r3, #:upper16:\val
    movw    r0, #\off
    str     r3, [r1, r0]
.endm

/* 與 PUT 完全相同,但名字不同 —— og3k_plan.check() 的 PUT 白名單是
 * 「一個位移一個值」的平表,表達不了「同一個位移依位元深度三選一」。
 * 平面格式碼改用 PFMT,由 check() 另一條規則對著 CANVAS_PLANE 驗。 */
.macro PFMT off, val
    movw    r3, #\val
    movw    r0, #\off
    str     r3, [r1, r0]
.endm

.global entry
entry:
    push    {r0, r1, r2, r3, ip, lr}
    add     r1, r4, #ROW
    LDA     ip, LOG
    str     r5, [ip, #8]

    cmp     r5, #PROF
    bne     playback
    /* 2026-09-15:donor 從 p83 換成 **p221**。
     * p83 是 S 尺寸 12-bit 照片的拍攝 profile(照片拍攝表 0xC0BE5D70 引用),
     * 所以借它必須靠 FLAG 守衛,而 FLAG 只是選單狀態 —— 選了 OG3K 再去
     * 拍照旗標仍然立著。那個缺口在 p221 下**不存在**:全映像掃過所有
     * {1|5|6, profile, mode, key_ptr} 表項,沒有任何一張表引用 p221,
     * 而它與 p83 的分支欄位逐格相同(+0x1C/+0x3C/+0x44/+0x7C/+0xA4/
     * +0xB4/+0xCC/+0xD8/+0xE0/+0xF0/+0xF4/+0xF8)。
     * FLAG 守衛保留 —— 零成本,而且萬一 p221 其實走得到就還有一層。 */
    LDA     r0, FLAG
    ldr     r3, [r0]
    cmp     r3, #0
    bne     record
    b       out

playback:

    /* --- case B:影片回放類 + 正在顯示我們的片子 -------------------------- */
    movw    r0, #0x80
    ldr     r3, [r1, r0]
    tst     r3, #0x10000
    beq     out
    LDA     r0, PBFLAG
    ldr     r3, [r0]
    cmp     r3, #1
    bne     out

    ldr     r3, [ip, #4]
    add     r3, r3, #1
    str     r3, [ip, #4]

    PUT     0x1C, 2                     @ 3:2 標記
    PUT     0x0C, W                     @ 柵格 = 片子的記錄尺寸
    PUT     0x10, H
    PUT     0xD8, W                     @ 消費端覆寫,與柵格一致
    PUT     0xE0, H
    PUT     0x20, AW                    @ 可見 = 裁切尺寸
    PUT     0x28, AH
    PUT     0xF4, W                     @ 視窗 = 柵格 → 縮放 unity
    PUT     0xF8, H
    /* 2026-09-13 試過拿掉這四筆:**幾何被放大了,而且過曝完全沒改善**。
     * 所以縮放比只管幾何,不是顯像增益的來源 —— 那個否定是乾淨的。還原。 */
    PUT     0x60, 1024
    PUT     0xD0, 1024
    PUT     0x64, 1024
    PUT     0xD4, 1024
    b       out

record:
#ifdef TARGET_POOLDEPTH
    LDA     r0, POOLFLAG                @ 一次性:池深替換(poolinit.S)
    ldr     r3, [r0]
    cmp     r3, #0
    bne     pool_done
    push    {r1, lr}
    LDA     ip, POOLINIT
    blx     ip
    pop     {r1, lr}
pool_done:
    LDA     ip, LOG                     @ 上面的呼叫毀掉了 ip(hook 用它指 LOG)
#endif
    ldr     r3, [ip]
    add     r3, r3, #1
    str     r3, [ip]
    /* 2026-09-20:把畫布指標記下來,這樣可以用 shell 直接讀**真正的**畫布
     * 內容。先前從 profile 的欄位表推論 +0xA4/+0xB0,結果 +0xB0 寫了沒用
     * —— 因為 FUN_c0435e38 要 +0xA4 是 0x18/0x2B,而靜態表說它是 0。
     * 與其再猜,不如把執行期的畫布整份讀出來比對。 */
#ifdef TARGET_CANVAS_PTR_LOG
    /* 畫布緩衝是重複使用的:錄影結束後即時取景(pid 5)會把同一塊覆寫掉,
     * 所以事後從指標讀回來的是取景那份,不是錄影當下的值(2026-09-20 踩到)。
     * 關鍵欄位必須**當場**抄進 cave。
     *     LOG+0x14 畫布位址   +0x18 類別碼 +0xA4   +0x1C 張數旗標 +0xB0
     *     LOG+0x20 +0xC0      +0x24 +0xFC
     * FUN_c0435e38 要 +0xA4 是 0x18/0x2B 才會走到「8 張 vs 6 張」那條。 */
    str     r1, [ip, #0x14]             @ LOG+0x14 = 畫布位址
    movw    r0, #0xA4
    ldr     r3, [r1, r0]
    str     r3, [ip, #0x18]
    movw    r0, #0xB0
    ldr     r3, [r1, r0]
    str     r3, [ip, #0x1C]
    movw    r0, #0xC0
    ldr     r3, [r1, r0]
    str     r3, [ip, #0x20]
    movw    r0, #0xFC
    ldr     r3, [r1, r0]
    str     r3, [ip, #0x24]
#endif
    /* 記下呼叫端要求的尺寸,看能不能用它當守衛(比 FLAG 可靠) */
    ldr     r3, [r4, #0x08]
    str     r3, [ip, #0x0C]
    ldr     r3, [r4, #0x0C]
    str     r3, [ip, #0x10]
    PUT     0x00, W                     @ 記錄矩陣寬
    PUT     0x04, H                     @ 記錄矩陣高
#ifdef TARGET_WRITE_ACTIVE
    /* p221 原廠的 active 就是 3008x2000,不必寫;p13(OG2K 的 donor)
     * 的 active 是 0x0,必須補,否則 DNG 沒有 DefaultCropSize。
     * 裁切原點由 (記錄 − active)/2 導出 —— 2016-2000=16 → 8,
     * 1344-1334=10 → 5,正好是 fp 自己的 +16 寬 / +10 高邊界慣例。 */
    PUT     0x24, AW
    PUT     0x2C, AH
#endif
#ifdef TARGET_WRITE_PREVIEW
    /* 預覽柵格與可見區。2026-09-15 實機量到:OG2K 錄影時 live view
     * 水平被放大 1.050x(待機 vs 錄影截圖,水平 0.952x、垂直 1.000x)。
     * 1.050 = 2016 / 1920 —— 正是 donor 的感測器視窗與預覽柵格之比。
     *
     * 成因:預覽 RWZM(+0x60/+0xD0)決定 producer 輸出多寬,柵格決定收多寬。
     *     p83  RWZM 1536/1024 = 1.5  → 3032/1.5 = 2021 ≈ 柵格 2024  一致
     *     p13  RWZM 1023/1024 ≈ 1.0  → 2016/1.0 = 2016 ≠ 柵格 1920  差 1.05
     * 差的那 96 欄被裁掉,就是看到的放大。
     *
     * 所以柵格要跟著記錄矩陣走,可見區跟著 DNG 裁切走。 */
    PUT     0x0C, W
    PUT     0x10, H
    PUT     0x20, AW
    PUT     0x28, AH
#endif
#ifdef TARGET_WRITE_PRODUCER
    /* p13 原廠的生產者對是 1920x1280,跟我們的記錄矩陣不符。
     * 2026-09-12 的事故正是生產者對與記錄矩陣不一致 ——
     * 錄出來只有左上一塊有畫面。p221 原廠是 0x0,所以 OG3K 不需要寫。 */
    PUT     0xD8, W
    PUT     0xE0, H
#endif
/* ★ 2026-09-20 實機證明的一組。>60 fps 時 p13 會讓錄影凍結,而原廠 120p
 * 的 profile 不會 —— 先把原廠 FHD120 那一格指到 mode 12(借它的 profile),
 * 錄 119.88 不凍結(A001_118:620 幀 / 5 秒);再把下面這七欄寫進 p13,
 * 用我們自己的 profile 也不凍結(A001_120:1173 幀 / 9 秒 = 約 120 fps,
 * 2016x672 8-bit)。見 notes §37-§39。
 *
 * 這七欄是「原廠影片 profile 有、p13 沒有、而且不是幾何/RWZM」的全部差異。
 * 最小集合尚未二分出來,所以**每一欄各自一個開關**,由 og3k_plan 的
 * OG_HIRATE 環境變數挑選(預設七欄全開 = 已驗證的那一組):
 *     OG_HIRATE=all              七欄全寫(預設,等同先前的行為)
 *     OG_HIRATE=90,DC,E4         只寫這三欄
 *     OG_HIRATE=none             一欄都不寫(回到 >60 fps 會凍結的狀態)
 * 二分時一次砍一半,判讀仍然只看「會不會凍結」。
 * ★ 這七個 #ifdef 必須保持**平行**、不可巢狀 —— og3k_plan.check() 的
 *   前處理器模擬對巢狀的 #ifdef 會算錯。 */
#ifdef TARGET_HIRATE_90
    PUT     0x90, 1                     @ 三個原廠影片 profile 都是 1
#endif
#ifdef TARGET_HIRATE_B0
    PUT     0xB0, 1                     @ 原廠 120p = 1,60p = 0
#endif
#ifdef TARGET_HIRATE_C0
    PUT     0xC0, 0                     @ 原廠影片 = 0,兩個 donor = 1
#endif
#ifdef TARGET_HIRATE_DC
    PUT     0xDC, W                     @ producer 第二組寬(原廠填自己的記錄寬)
#endif
#ifdef TARGET_HIRATE_E4
    PUT     0xE4, H                     @ producer 第二組高
#endif
#ifdef TARGET_HIRATE_FC
    PUTW    0xFC, 0x40000000            @ 2.0f;只有 p13 是 3.0f
#endif
#ifdef TARGET_HIRATE_100
    PUTW    0x100, 0x40000000
#endif
#ifdef TARGET_BUFCLASS
    /* ★ 2026-09-21:把畫布的**類別碼** +0x0A4 從 0 改成 0x29,唯一的目的是
     * 讓管線多配置一整類緩衝。原廠沒有任何錄影 profile 走這條 —— 因為原廠
     * 沒有任何模式超過 119.88 —— 但「原廠不做」不等於「做不到」。
     *
     *   FUN_c0435E38(canvas)  +0xA4 ∈ {0x18, 0x29} 時回 (+0xB0 == 1 ? 8 : 6)
     *                         否則回 0。我們的 +0xB0 已經是 1(§39 七欄之一),
     *                         所以會拿到 **8 張** —— 比任何原廠 profile 在這
     *                         條路上拿到的(那 16 個 0x29 的 profile 都是
     *                         +0xB0 = 0 -> 6 張)都多。
     *   FUN_c0435DF8(canvas)  同一組條件下回 顯示寬 x 顯示高 x 2,否則 0。
     *   FUN_c0435588          把每一對 (數量 x 大小) 加總 = 管線的配置預算。
     *
     * 代價(sizesim,顯示 1024x682):總配置 7,472,776 -> 18,646,664(+10.7 MB)。
     * 配置器實際服務過 p51 回放的 22.0 MB,所以在已知可行的範圍內。
     *
     * ★ 安全性:+0xA4 是**類別碼**,不是單純的數量旋鈕。全映像掃過所有把它
     * 當畫布欄位讀的函式,0 與 0x29 的行為只在上面那兩顆不同:
     *     FUN_c0434EF8  它的 case 表是 1,3,4,5,6,7,8,9,10,0xB..0xE,0x10..0x12,
     *                   0x1C,0x1F —— **0x29 與 0 一樣都不命中**,不設任何旗標
     *     FUN_c04357E0  +0xA4==1 -> 2;∈{9,10} -> 0;否則 3。兩者都是 3
     *     FUN_c0435978  只在 +0xF0 != 0 時讀,且只比 "!= 6"。兩者都成立
     * 另外 FUN_c06BEF38/90 的 "+0xa4" 是別的物件的 vtable 呼叫,不是畫布。
     *
     * 只寫錄影路徑。回放不碰。 */
    PUT     0xA4, TARGET_BUFCLASS
#endif
#ifdef TARGET_WRITE_WINDOW
    /* 感測器視窗。2026-09-20:HSW 是第一個 donor 原廠視窗與實際讀出不符的
     * 目標 —— p13 宣告 2016x1344,而 mode 12 只讀 **672** 行,差兩倍。
     *     OG3K  p83 視窗 3032x2012 = 它的光柵,本來就對
     *     OG2K  p13 視窗 2016x1344 = 它的光柵,剛好對
     *     HSW   p13 視窗 2016x1344 vs 光柵 2016x672   ← 對不上
     * 實機症狀:req_cnt 94 / fin_cnt 72,22 格請求永遠不會完成,
     * 錄影結束不了(需斷電)。消費端照 1344 行配置並等待,而資料只有 672。
     * 見 notes/HSW_240FPS_MODE12.md §20。 */
    PUT     0xF4, W
    PUT     0xF8, H
#endif
#ifdef TARGET_ENGFPS
    /* 畫布 +0x030 = 引擎格率。fmttable 命中時鎖存了「原廠在同一個 picker
     * slot 上宣告的格率」,這裡把它寫進畫布,FUN_c0434ef8 會複製到引擎組態
     * +0x10(DAT_c31df574 + ch*0x1B0)。
     *
     * 沒有它的話引擎對每一個格率都看到 p83 原廠的 **18.0**:
     *     FUN_c01caba0   `fps < 30` -> 硬體欄位除數 ÷33 而非 ÷100
     *                    (29.97 就分岔了:原廠 p175 宣告 30.0)
     *     FUN_c01cec08   「>99 fps」永遠假 -> OG3K100 拿不到 HFR 路徑
     *     FUN_c01cc868   引擎狀態存 (int)18
     *     FUN_c01d11e8   timeout = fps * 1000 -> 18000
     *
     * 鎖存為 0(還沒命中過)就不寫 —— 寫 0.0 比留著 18.0 更糟。
     * 值一定是正的(check() 驗 0 < fps <= 240):FUN_c04357e0 的 plane count
     * 只有在 +0x030 == -1.0 時才歸零,正值一律 3 張,與原廠相同。 */
    LDA     r2, FPSLATCH
    ldr     r2, [r2]
    cmp     r2, #0
    strne   r2, [r1, #0x30]
#endif
    /* 2026-09-14:預覽平面的像素格式碼。c04356b0(obj,0) 用 +0x0C(寬)與
     * +0x80(格式)算預覽平面;+0x84 是 RAW 平面的。
     *     p83(照片)  +0x80 = 10 = 8-bit    +0x84 = 7 = 12-bit
     *     p175(影片) +0x80 =  7 = 12-bit   +0x84 = 7 = 12-bit
     * 原廠影片的預覽平面是 12-bit,我們借的照片 profile 宣告成 8-bit。
     * 修好增益(gain_state 7)之後錄影預覽變綠且閃爍,而檔案的通道平衡、
     * 黑階、白平衡標籤都與原廠一致 —— 綠只在預覽那一層,像解碼錯誤。
     * 補成 7,讓預覽平面和原廠影片一樣。
     *
     * 2026-09-15:這兩欄必須跟著 CinemaDNG 品質走,不能寫死 12-bit。
     * DNG 的 BitsPerSample 是 FUN_c06a5290 用 FUN_c02da870(eRawBitType)
     * 算的,**不看 profile**;而平面格式碼決定資料怎麼打包。兩邊不一致
     * 就是「資料 12-bit、標籤寫 8/10」的毀檔。
     * 原廠三胞胎(p131/p151/p171、p135/p155/p175、p133/p153/p173)
     * 65 欄裡就只差這兩欄:
     *      8-bit   +0x80 = 10   +0x84 = 10
     *     10-bit   +0x80 = 10   +0x84 =  9
     *     12-bit   +0x80 =  7   +0x84 =  7
     * (bpp 對照 FUN_c04356b0:7 → 12-bit、9 → 10-bit、10 → 8-bit。)
     * p83 原廠是 +0x80 = 10、+0x84 = 7,所以 8/10-bit 其實只差 +0x84、
     * 12-bit 只差 +0x80;這裡三條路都把兩欄寫滿,不依賴 p83 的原廠值。
     * 見 notes/OG3K_8BIT_10BIT_FALLS_BACK_TO_UHD.md。 */
    LDA     r2, BITLATCH
    ldr     r2, [r2]
    cmp     r2, #BD8
    beq     bd8
    cmp     r2, #BD10
    beq     bd10
    PUT     0x80, 7                     @ 12-bit(CANVAS_REC 驗證的那一筆)
    PFMT    0x84, 7
    b       out
bd10:
    PFMT    0x80, 10
    PFMT    0x84, 9
    b       out
bd8:
    PFMT    0x80, 10
    PFMT    0x84, 10

out:
    pop     {r0, r1, r2, r3, ip, lr}
#ifdef OG_CHAIN
    OG_PASS                     @ Loader v3: the layer below, or og_replay
.global og_replay
og_replay:
#endif
    mov     r0, r4                      @ 位移指令
    bx      lr
