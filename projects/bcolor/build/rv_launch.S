.syntax unified
.arm
.text
.global entry
/* ============================================================================
 * rv_launch — rawview 開機 launcher(destination 0:在 staging 原地執行,裝好後返回)
 * ============================================================================
 *
 * 照 gyro gsup_launch.S 的形狀(SUP_BUILD_RULES):自己配置、自己複製、自己裝 hook,
 * 不讀也不發布 0xC3757A7C,不呼叫其他 sup。任何檢查不過就什麼都不裝、直接返回。
 *
 *   1. 兩個 hook 點與 mode 表第 35 筆必須是 5.02 原廠值
 *   2. USER heap 配置 ALLOC bytes,4 KiB 對齊成 T0
 *   3. 124 張 tone 表(build/rv_tables.py 同一公式):表 k < 62 在 T0 + k·0x1000,其餘在 T0 + (k + 4)·0x1000
 *   4. T0 + 0x3E004:11 格插槽 → ISO 100 表;T0 + 0x3E060:mode 表副本,OFF 那筆指向插槽
 *   5. T0 + 0x3E200:常駐程式(rv_resident.S),填參數;flag = 0 → 行為與原廠相同
 *      T0 + 0x40800:色彩矩陣表(root+0x08)副本,OFF 那筆換成 fp 校色矩陣(RC1/RC2 用;build/rv_color.py)
 *   6. 五個 8-byte veneer 取自 CAVE_BUMP → D/I cache → 寫 bl 與 getter patch → 再 D/I cache
 *      增益:site A/B;選單:三個 GUI→enum 呼叫點共用一個 veneer、enum→GUI 一個、setter 一個;
 *      getter C06C07C0 的表位址改成常駐區的 17 筆表、筆數 16 → 17(第 17 列 = RAW)。
 *      RAW 列調整:右側上下框(SA/GA)兩個換算呼叫點、AEL 飽和度(矩陣程度)四個換算呼叫點 → stub_ef/en/sa/sn。
 *
 * builder 以 -D 傳入:RES_LEN、TDATA_OFF(blob 內表格資料的位置)、STUB_GS/DG/MA/MB/MC(常駐內偏移)。
 * blob(本檔尾端)= 常駐程式 | 表格資料(LT[257] u32 | LOGW s32 | REC[124] × 6 s32 | B s32 | THR[30] u32 | SAMP[32][146] u16)
 * ========================================================================== */

.equ H_GET,        0xC001D740       /* (desc, class, size, 0) */
.equ H_ADDR,       0xC001D7F0       /* (desc) -> address */
.equ ALLOC,        0x82000          /* 0..0x3E000 表 0–61、0x3E000..0x42000 插槽／常駐／矩陣、0x42000.. 表 62–123、0x80000 LOG 暫存 */
.equ OFF_LOG,      0x80000          /* LOG[2048] s32:開機時算,產完表就不用 */
.equ F_DCACHE,     0xC000E91C
.equ F_ICACHE,     0xC000EABC
.equ CAVE_BUMP,    0xC072E060
.equ CAVE_ARENA_END, 0xC072EFB4
.equ VENEER_LDR,   0xE51FF004       /* ldr pc, [pc, #-4] */

.equ SITE_A,       0xC0313244
.equ ORIG_A,       0xE595200C
.equ SITE_B,       0xC032F728
.equ ORIG_B,       0xE59C6000
.equ MODE_TAB,     0xC0B3D670       /* {mode, base} × 0x24 */
.equ GUI_TAB,      0xC2E412BC       /* 色彩模式 {enum, gui} × 16 */
.equ GET_MOVW,     0xC06C07CC
.equ GET_MOVT,     0xC06C07D0
.equ GET_COUNT,    0xC06C07D8
.equ SITE_MA1,     0xC0568950       /* COLOR 鍵 */
.equ SITE_MA2,     0xC056D028       /* 選單 */
.equ SITE_MA3,     0xC05818B8       /* QS */
.equ SITE_MB,      0xC0595734       /* CM_COLFIX 通知 */
.equ SITE_MC,      0xC0075CF4       /* setter cmp sl,r6 */
.equ P_GUI,        0x98
.equ NVEN,         19               /* 0–4 ARM、5 Thumb(H1)、6 ARM(LV_ColorMode)、7–10 ARM(ef/en/sa/sn)、11 ARM(mj)、12–15 ARM(zc/zs/znc/zns)、16 Thumb(ai)、17 ARM(sv)、18 ARM(pq) */
.equ SITE_PQ,      0xC02B8E64       /* 畫質管理器指令:bl FUN_c02b97a8 → stub_pq(回放時換回原廠) */
.equ ORIG_PQ,      0xEB00024F
.equ SITE_SV,      0xC0088C60       /* 關機存檔 v2:bl FUN_c0088660 → stub_sv(RAW 存成 0x10–0x17) */
.equ ORIG_SV,      0xEBFFFE7E
.equ BANK_COLOR,   0xC31B33E8       /* 工作設定 bank A +0x12C:色彩模式 */
.equ F_ITEM,       0xC0057AE8       /* () → 選單設定管理;shell `menu SetColorMode` 同一條 */
.equ F_SETCOLOR,   0xC005C958       /* (item, 值, 1):寫色彩模式並通知 PQ/LV/選單 */
.equ CBM_STATE,    0xC3766498       /* COLOR 鍵選單結構;+0x84 = 已初始化(清 0 → 下次開啟重建) */
.equ P_FLAG,       0x04
.equ P_PEND,       0x94
.equ P_VAR,        0x1A4
.equ P_SAT,        0x1B0
.equ P_SATF,       0x1B4
.equ P_CON,        0x1C4
.equ P_CONF,       0x1C8
.equ AI_SITE,      0xC05E2200       /* Thumb:bl FUN_c05d6bb8(關鍵影格圖名設到節點) */
.equ SITE_ZC_AJ,   0xC056D548       /* 對比 AJ bl C06C0EC0 */
.equ SITE_ZC_FIX,  0xC056D3E8       /* 對比 FIX */
.equ SITE_ZS_AJ,   0xC056D5A0       /* 清晰 AJ bl C06C0F90 */
.equ SITE_ZS_FIX,  0xC056D440       /* 清晰 FIX */
.equ SITE_ZNC_FIX, 0xC059581C       /* v83 bl C06C0F10 */
.equ SITE_ZNC_AJ,  0xC0595974       /* v88 */
.equ SITE_ZNS_FIX, 0xC0595854       /* v84 bl C06C0FE0 */
.equ SITE_ZNS_AJ,  0xC05959AC       /* v89 */
.equ SITE_MJ,      0xC05689A8       /* COLOR 鍵選單預覽 bl C06C07E8 */
.equ SITE_EN_FIX,  0xC05957B0       /* v82 bl C06C0D70(CM_COLFIX_Effect) */
.equ SITE_EF,      0xC0568A3C       /* 上下框回呼 bl C06C0D20 */
.equ SITE_EN,      0xC0595908       /* v87 bl C06C0D70 */
.equ SITE_SA_AJ,   0xC056D5F8       /* 飽和度 AJ bl C06C1060 */
.equ SITE_SA_FIX,  0xC056D498       /* 飽和度 FIX bl C06C1060 */
.equ SITE_SN_FIX,  0xC059588C       /* v85 bl C06C10B0 */
.equ SITE_SN_AJ,   0xC05959E4       /* v90 bl C06C10B0 */
.equ SITE_ML,      0xC059DA1C       /* LV_ColorMode enum→GUI */
.equ H1_SITE,      0xC05E5BEC       /* Thumb:adds r0,r0,r1; str r0,[r5,#4] */
.equ THUMB_VENEER, 0xF000F8DF       /* ldr.w pc, [pc, #0] */
.equ CURVE_ENTRIES, 0xC0971114

.equ OFF_SLOTS,    0x3E004          /* ≡ 4 mod 8(CURVE_ENTRIES ≡ 4 mod 8) */
.equ OFF_MODE,     0x3E060
.equ OFF_RES,      0x3E200
.equ OFF_MAT,      0x40800          /* 常駐(含 RAW 圖示、DNG CM 表)之後 */
.equ CBM_VT_V25,   0xC0D119FC       /* ColorButtonMenu vtable:v25 開啟 */
.equ CBM_VT_V26,   0xC0D11A00       /*                        v26 關閉 */
.equ DNG_CM1_MOVW, 0xC02C4BE4       /* FUN_c02c4a50 OFF 分支:movw/movt r2 = OFF CM1 常數 */
.equ DNG_CM1_MOVT, 0xC02C4BE8
.equ DNG_CM2_MOVW, 0xC02C4C98       /* 同上,CM2 */
.equ DNG_CM2_MOVT, 0xC02C4C9C
.equ ROOT_P08,     0xC2F1A06C       /* 色彩矩陣表 {指標, 筆數} */
.equ MAT_TAB,      0xC0B39CC8
.equ MAT_OFF_REC,  0xC0B39FF8       /* 第 34 筆 = OFF(0x24) */
.equ MAT_LEN,      35 * 0x18
.equ P_MAT,        0x1A8
.equ NTAB,         31
.equ NREC,         124              /* 4 組 × 31(曲線 SA/GA × 對比 0/1;rv_tables.SETS) */
.equ RECW,         6                /* REC 每筆 {K, A, GRP, M, C, XK} */
.equ NLT,          257              /* LT[j] = log2(1 + j/256) Q16 */
.equ REC_OFF,      NLT * 4 + 4      /* 表格資料內:LT | LOGW | REC… */
.equ NS,           146              /* 每張表的取樣點(−8..+6.5 檔,每 0.1) */
.equ NSP,          146
.equ SAMP_OFF,     NREC * RECW * 4 + 4 + NTHR * 4   /* REC 之後:B、THR,再來取樣表(GA 31 + SA 共用 1 組) */
.equ NTHR,         30

.macro LDA reg, value
    movw    \reg, #:lower16:\value
    movt    \reg, #:upper16:\value
.endm

/* 原廠字不符 → 9f(什麼都不裝) */
.macro GUARD addr, word
    LDA     r0, \addr
    ldr     r1, [r0]
    LDA     r2, \word
    cmp     r1, r2
    bne     9f
.endm

/* site 寫成 bl <veneer n>;r5 = veneer 起點。(dest − site − 8) asr 2 */
.macro ARM site, n
    LDA     r1, \site
    add     r2, r5, #(\n) * 8
    sub     r0, r2, r1
    sub     r0, r0, #8
    asr     r0, r0, #2
    bic     r0, r0, #0xFF000000
    orr     r0, r0, #0xEB000000
    str     r0, [r1]
.endm

/* Thumb B.W site → veneer(r5 + vofs)。off = veneer − (site + 4)
 * hw1 = 0xF000 | S<<10 | off[21:12]
 * hw2 = 0x9000 | J1<<13 | J2<<11 | off[11:1],J1 = ~I1 ^ S,J2 = ~I2 ^ S(I1 = off[23],I2 = off[22])(r0–r4、ip 破壞) */
.macro THUMB_BW site, vofs, bl=0
    LDA     r1, \site
    add     r0, r5, #\vofs
    sub     r0, r0, r1
    sub     r0, r0, #4              @ r0 = off
    lsr     r2, r0, #31             @ S
    lsr     r3, r0, #12
    LDA     ip, 0x3FF
    and     r3, r3, ip
    orr     r3, r3, r2, lsl #10
    orr     r3, r3, #0xF000         @ hw1
    lsr     ip, r0, #23
    and     ip, ip, #1              @ I1
    eor     ip, ip, #1
    eor     ip, ip, r2              @ J1
    lsr     r4, r0, #22
    and     r4, r4, #1              @ I2
    eor     r4, r4, #1
    eor     r4, r4, r2              @ J2
    lsr     r0, r0, #1
    LDA     r2, 0x7FF
    and     r0, r0, r2              @ imm11
    orr     r0, r0, ip, lsl #13
    orr     r0, r0, r4, lsl #11
    orr     r0, r0, #0x9000         @ hw2(B.W)
.if \bl
    orr     r0, r0, #0x4000         @ BL:hw2 = 0xD000 | …
.endif
    orr     r0, r3, r0, lsl #16     @ 小端:hw1 在低位
    str     r0, [r1]
.endm

/* r3 = 值 → 寫 movw/movt r2 到兩個位址(r0–r2 破壞) */
.macro MOVWT_R2 site_w, site_t
    LDA     r1, \site_w
    mov     r0, r3, lsl #16
    lsr     r0, r0, #16             @ lo16
    and     r2, r0, #0xF000
    bic     r0, r0, #0xF000
    orr     r0, r0, r2, lsl #4      @ imm4 → bits 19:16
    LDA     r2, 0xE3002000          @ movw r2, #imm
    orr     r0, r0, r2
    str     r0, [r1]
    LDA     r1, \site_t
    lsr     r0, r3, #16             @ hi16
    and     r2, r0, #0xF000
    bic     r0, r0, #0xF000
    orr     r0, r0, r2, lsl #4
    LDA     r2, 0xE3402000          @ movt r2, #imm
    orr     r0, r0, r2
    str     r0, [r1]
.endm

/* veneer n → 常駐 + off;r9 = 常駐,r5 = veneer 起點,r2 = VENEER_LDR */
.macro VEN n, off
    LDA     r0, \off
    add     r0, r9, r0
    str     r2, [r5, #(\n) * 8]
    str     r0, [r5, #(\n) * 8 + 4]
.endm

entry:
    push    {r4-r11, ip, lr}        @ 十個:stack 保持 8-byte 對齊
    sub     sp, sp, #16             @ allocator descriptor(不釋放)

    /* 1. 原廠值檢查 */
    GUARD   SITE_A, ORIG_A
    GUARD   SITE_B, ORIG_B
    GUARD   GET_MOVW, 0xE30122BC
    GUARD   GET_MOVT, 0xE34C22E4
    GUARD   GET_COUNT, 0xE3A02010
    GUARD   SITE_MA1, 0xEB055F70
    GUARD   SITE_MA2, 0xEB054DBA
    GUARD   SITE_MA3, 0xEB04FB96
    GUARD   SITE_MB, 0xEB04AC0B
    GUARD   SITE_MC, 0xE15A0006
    ldr     r3, page_rel1           @ 頁面表:{位址, 原廠字, 新字}…,0 結尾
13: add     r3, pc, r3
14: ldr     r0, [r3], #12
    cmp     r0, #0
    beq     15f
    ldr     r1, [r0]
    ldr     r2, [r3, #-8]
    cmp     r1, r2
    bne     9f
    b       14b
15:
    GUARD   H1_SITE, 0x60681840
    GUARD   SITE_ML, 0xEB048B51
    GUARD   AI_SITE, 0xFCDAF7F4
    GUARD   SITE_SV, ORIG_SV
    GUARD   SITE_PQ, ORIG_PQ
    GUARD   SITE_EF, 0xEB0560B7
    GUARD   SITE_MJ, 0xEB055F8E
    GUARD   SITE_EN_FIX, 0xEB04AD6E
    GUARD   DNG_CM1_MOVW, 0xE30F2D74
    GUARD   CBM_VT_V25, 0xC05687E0
    GUARD   SITE_ZC_AJ, 0xEB054E5C
    GUARD   SITE_ZC_FIX, 0xEB054EB4
    GUARD   SITE_ZS_AJ, 0xEB054E7A
    GUARD   SITE_ZS_FIX, 0xEB054ED2
    GUARD   SITE_ZNC_FIX, 0xEB04ADBB
    GUARD   SITE_ZNC_AJ, 0xEB04AD65
    GUARD   SITE_ZNS_FIX, 0xEB04ADE1
    GUARD   SITE_ZNS_AJ, 0xEB04AD8B
    GUARD   CBM_VT_V26, 0xC0568888
    GUARD   DNG_CM1_MOVT, 0xE34C2096
    GUARD   DNG_CM2_MOVW, 0xE30F2CE4
    GUARD   DNG_CM2_MOVT, 0xE34C2096
    GUARD   SITE_EN, 0xEB04AD18
    GUARD   SITE_SA_AJ, 0xEB054E98
    GUARD   SITE_SA_FIX, 0xEB054EF0
    GUARD   SITE_SN_FIX, 0xEB04AE07
    GUARD   SITE_SN_AJ, 0xEB04ADB1
    GUARD   ROOT_P08, MAT_TAB
    GUARD   ROOT_P08 + 4, 35
    LDA     r0, MAT_OFF_REC         @ OFF 那筆必須是原廠單位矩陣
    ldr     r1, mat_rel1
22: add     r1, pc, r1              @ r1 = mat_stock
    mov     r2, #6
19: ldr     r3, [r0], #4
    ldr     ip, [r1], #4
    cmp     r3, ip
    bne     9f
    subs    r2, r2, #1
    bne     19b
    LDA     r0, MODE_TAB + 0x118
    ldr     r1, [r0]
    cmp     r1, #0x24
    bne     9f
    ldr     r1, [r0, #4]
    cmp     r1, #82
    bne     9f

    /* 2. 配置 */
    mov     r0, sp
    mov     r1, #0                  @ USER
    LDA     r2, ALLOC
    mov     r3, #0
    LDA     ip, H_GET
    blx     ip
    mov     r0, sp
    LDA     ip, H_ADDR
    blx     ip
    movs    r4, r0
    beq     9f                      @ 被拒:什麼都不裝
    LDA     r1, 0xFFF
    add     r4, r4, r1
    bic     r4, r4, r1              @ r4 = T0

    /* 3a. LOG[i] = log2(i/1918) Q16 → T0 + OFF_LOG(rv_tables.log_q16 逐位元相同)
     *     n = 31 − clz(i),f = (i << (20 − n)) − 2^20,j = f >> 12,r = f & 0xFFF
     *     LOG = (n << 16) + LT[j] + ((LT[j+1] − LT[j])·r >> 12) − LOGW;LOG[0] = −32 << 16 */
    ldr     r7, blob_rel1
11: add     r7, pc, r7              @ r7 = blob(adr 距離不夠,用 PC 相對常數)
    LDA     r0, TDATA_OFF
    add     r7, r7, r0              @ r7 = LT[]
    ldr     r9, [r7, #NLT * 4]      @ r9 = LOGW
    LDA     r0, OFF_LOG
    add     r5, r4, r0              @ r5 = LOG[]
    LDA     r0, 0xFFE00000
    str     r0, [r5]
    mov     r11, #1
40: clz     r1, r11
    sub     r2, r1, #11
    lsl     r3, r11, r2             @ i << (20 − n)
    sub     r3, r3, #0x100000       @ f
    lsr     r0, r3, #12
    add     r0, r7, r0, lsl #2
    ldr     r2, [r0]                @ LT[j]
    ldr     r0, [r0, #4]            @ LT[j+1]
    sub     r0, r0, r2
    lsl     r3, r3, #20
    lsr     r3, r3, #20             @ r
    mul     r0, r0, r3
    add     r2, r2, r0, lsr #12
    rsb     r1, r1, #31             @ n
    add     r2, r2, r1, lsl #16
    sub     r2, r2, r9
    str     r2, [r5, r11, lsl #2]
    add     r11, r11, #1
    cmp     r11, #2048
    blo     40b

    /* 3. 124 張表(rv_tables.py):v = max(取樣曲線, 直線),index 0 = 0
     *    x = (LOG·K >> 16) + A(Q16);x < 0 → 0
     *    GRP ≥ 0:t = x·10;j = t >> 16、f = t & 0xFFFF;j ≥ NS − 1 → SAMP[NS−1];否則 SAMP[j] + ((SAMP[j+1] − SAMP[j])·f >> 16)
     *    x < XK:直線 C + (M·x >> 24);夾到 0..B */
    LDA     r0, REC_OFF
    add     r6, r7, r0              @ r6 = REC[124]
    LDA     r0, NREC * RECW * 4
    ldr     r7, [r6, r0]            @ r7 = B
    mov     r8, #0                  @ k
    mov     r9, r4                  @ 目的
1:  mov     r0, #RECW * 4
    mla     lr, r8, r0, r6          @ lr = REC[k]
    ldr     r3, [lr, #4]            @ A
    ldr     r1, [lr, #8]            @ GRP
    mov     r10, #0
    cmp     r1, #0
    blt     30f
    LDA     r10, SAMP_OFF
    add     r10, r6, r10
    LDA     r0, NSP * 2
    mla     r10, r1, r0, r10        @ r10 = SAMP[GRP]
30: mov     r11, #0                 @ i
2:  ldr     r0, [r5, r11, lsl #2]
    ldr     r1, [lr]                @ K
    smull   ip, r2, r0, r1          @ r2:ip = LOG·K
    lsr     ip, ip, #16
    orr     r0, ip, r2, lsl #16     @ LOG·K >> 16
    adds    r0, r0, r3              @ x
    movmi   r1, #0
    bmi     32f                     @ index 0:純黑
    mov     r1, #0x80000000         @ v = −∞
    cmp     r10, #0
    beq     31f
    add     r2, r0, r0, lsl #2
    lsl     r2, r2, #1              @ t = x·10
    lsr     ip, r2, #16             @ j
    LDA     r1, NS - 1
    cmp     ip, r1
    movhs   ip, r1
    movhs   r2, #0                  @ j 夾到最後一點、f = 0
    add     ip, r10, ip, lsl #1
    ldrh    r1, [ip]                @ y[j]
    ldrh    ip, [ip, #2]            @ y[j+1]
    sub     ip, ip, r1
    lsl     r2, r2, #16
    lsr     r2, r2, #16             @ f
    mul     ip, ip, r2
    add     r1, r1, ip, asr #16     @ v
31: ldr     r2, [lr, #20]           @ XK
    cmp     r0, r2
    bge     32f
    ldr     r2, [lr, #12]           @ M
    smull   ip, r2, r2, r0
    lsr     ip, ip, #24
    orr     ip, ip, r2, lsl #8      @ M·x >> 24
    ldr     r2, [lr, #16]           @ C
    add     ip, ip, r2
    cmp     ip, r1
    movgt   r1, ip
32: cmp     r1, #0
    movlt   r1, #0
    cmp     r1, r7
    movgt   r1, r7
    strh    r1, [r9], #2
    add     r11, r11, #1
    cmp     r11, #2048
    blo     2b
    add     r8, r8, #1
    cmp     r8, #62
    addeq   r9, r9, #0x4000         @ 表 62 起跳過插槽／常駐／矩陣區
    cmp     r8, #NREC
    blo     1b

    /* 4. 插槽:11 × {0, ISO 100 表} */
    LDA     r0, OFF_SLOTS
    add     r10, r4, r0             @ r10 = slots
    mov     r0, r10
    mov     r1, #0
    mov     r2, #11
3:  str     r1, [r0], #4
    str     r4, [r0], #4
    subs    r2, r2, #1
    bne     3b

    /*    mode 表副本,第 35 筆 base = N = ((slots − CURVE_ENTRIES) asr 3) + 5 */
    LDA     r0, OFF_MODE
    add     r11, r4, r0             @ r11 = mode_copy
    LDA     r1, MODE_TAB
    mov     r0, r11
    mov     r2, #0x24 * 2
4:  ldr     r3, [r1], #4
    str     r3, [r0], #4
    subs    r2, r2, #1
    bne     4b
    LDA     r1, CURVE_ENTRIES
    sub     r1, r10, r1
    asr     r1, r1, #3
    add     r1, r1, #5
    str     r1, [r11, #0x11C]

    /* 5. 常駐程式與參數 */
    LDA     r0, OFF_RES
    add     r9, r4, r0              @ r9 = 常駐
    ldr     r1, blob_rel2
12: add     r1, pc, r1              @ r1 = blob
    mov     r0, r9
    LDA     r2, RES_LEN
5:  ldr     r3, [r1], #4
    str     r3, [r0], #4
    subs    r2, r2, #4
    bne     5b
    str     r4, [r9, #0x10]         @ tab_base
    str     r10, [r9, #0x14]        @ slots
    str     r11, [r9, #0x18]        @ mode_copy
    LDA     r1, NREC * RECW * 4 + 4
    add     r1, r6, r1              @ THR[]
    add     r0, r9, #0x1C
    mov     r2, #NTHR
6:  ldr     r3, [r1], #4
    str     r3, [r0], #4
    subs    r2, r2, #1
    bne     6b

    /*    色彩模式 {enum, gui}:原廠 16 筆 + {0xC, 16} */
    LDA     r1, GUI_TAB
    add     r0, r9, #P_GUI
    mov     r2, #32
7:  ldr     r3, [r1], #4
    str     r3, [r0], #4
    subs    r2, r2, #1
    bne     7b
    mov     r3, #0xC
    mov     r2, #16
8:  str     r3, [r0], #4
    str     r2, [r0], #4
    add     r2, r2, #1
    cmp     r2, #17
    blo     8b

    /*    色彩矩陣表副本(OFF 那筆換成校色矩陣) */
    LDA     r0, OFF_MAT
    add     r0, r4, r0              @ r0 = 副本
    str     r0, [r9, #P_MAT]
    LDA     r1, MAT_TAB
    LDA     r2, MAT_LEN
20: ldr     r3, [r1], #4
    str     r3, [r0], #4
    subs    r2, r2, #4
    bne     20b
    LDA     r1, MAT_OFF_REC - MAT_TAB
    ldr     r0, [r9, #P_MAT]
    add     r0, r0, r1
    ldr     r1, mat_rel2
23: add     r1, pc, r1              @ r1 = mat_new
    mov     r2, #6
21: ldr     r3, [r1], #4
    str     r3, [r0], #4
    subs    r2, r2, #1
    bne     21b

    /* 6. veneer(五個,取自 cave 的 bump 配置器) */
    LDA     r7, CAVE_BUMP
    ldr     r5, [r7]                @ r5 = veneer 起點
    add     r1, r5, #NVEN * 8
    LDA     r2, CAVE_ARENA_END
    cmp     r1, r2
    bhi     9f                      @ cave 滿了:不裝(記憶體留著,重開機釋放)
    str     r1, [r7]
    LDA     r2, VENEER_LDR
    VEN     0, STUB_GS
    VEN     1, STUB_DG
    VEN     2, STUB_MA
    VEN     3, STUB_MB
    VEN     4, STUB_MC
    LDA     r0, STUB_FV              @ veneer 5:Thumb,ldr.w pc 跳 ARM stub(bit0 = 0)
    add     r0, r9, r0
    LDA     r1, THUMB_VENEER
    str     r1, [r5, #40]
    str     r0, [r5, #44]
    LDA     r2, VENEER_LDR
    VEN     6, STUB_ML
    VEN     7, STUB_EF
    VEN     8, STUB_EN
    VEN     9, STUB_SA
    VEN     10, STUB_SN
    VEN     11, STUB_MJ
    VEN     12, STUB_ZC
    VEN     13, STUB_ZS
    VEN     14, STUB_ZNC
    VEN     15, STUB_ZNS
    LDA     r0, STUB_AI              @ veneer 16:Thumb,ldr.w pc 跳 ARM stub_ai
    add     r0, r9, r0
    LDA     r1, THUMB_VENEER
    str     r1, [r5, #128]
    str     r0, [r5, #132]
    LDA     r2, VENEER_LDR
    VEN     17, STUB_SV
    VEN     18, STUB_PQ

    LDA     ip, F_DCACHE            @ 表(DMA 讀)、常駐程式、veneer
    blx     ip
    LDA     ip, F_ICACHE
    blx     ip

    /* getter:表位址 = 常駐 + P_GUI(movw/movt r2),筆數 17 */
    add     r3, r9, #P_GUI
    MOVWT_R2 GET_MOVW, GET_MOVT
    /* ColorButtonMenu 開/關 → stub_mo/stub_mx(記錄選單開著;SA/GA 字形的條件) */
    LDA     r0, STUB_MO
    add     r0, r9, r0
    LDA     r1, CBM_VT_V25
    str     r0, [r1]
    LDA     r0, STUB_MX
    add     r0, r9, r0
    LDA     r1, CBM_VT_V26
    str     r0, [r1]
    /* DNG writer:OFF 常數位址 → 常駐 cm_buf(CM1)、cm_buf + 72(CM2) */
    LDA     r3, CMBUF
    add     r3, r9, r3
    MOVWT_R2 DNG_CM1_MOVW, DNG_CM1_MOVT
    add     r3, r3, #72
    MOVWT_R2 DNG_CM2_MOVW, DNG_CM2_MOVT
    LDA     r1, GET_COUNT
    LDA     r0, 0xE3A02011          @ mov r2, #17
    str     r0, [r1]

    ARM     SITE_A, 0
    ARM     SITE_B, 1
    ARM     SITE_MA1, 2
    ARM     SITE_MA2, 2
    ARM     SITE_MA3, 2
    ARM     SITE_MB, 3
    ARM     SITE_MC, 4
    ARM     SITE_ML, 6
    ARM     SITE_EF, 7
    ARM     SITE_EN, 8
    ARM     SITE_SA_AJ, 9
    ARM     SITE_SA_FIX, 9
    ARM     SITE_SN_FIX, 10
    ARM     SITE_SN_AJ, 10
    ARM     SITE_MJ, 11
    ARM     SITE_EN_FIX, 8
    ARM     SITE_ZC_AJ, 12
    ARM     SITE_ZC_FIX, 12
    ARM     SITE_ZS_AJ, 13
    ARM     SITE_ZS_FIX, 13
    ARM     SITE_ZNC_FIX, 14
    ARM     SITE_ZNC_AJ, 14
    ARM     SITE_ZNS_FIX, 15
    ARM     SITE_ZNS_AJ, 15

    /* ColorButtonMenu 頁面(開啟時才解析,開機時改即可) */
    ldr     r3, page_rel2
16: add     r3, pc, r3
17: ldr     r1, [r3], #12
    cmp     r1, #0
    beq     18f
    ldr     r0, [r3, #-4]
    str     r0, [r1]
    b       17b
18:

    THUMB_BW H1_SITE, 40             @ H1 → veneer 5
    THUMB_BW AI_SITE, 128, 1         @ 關鍵影格圖名 BL → veneer 16(stub_ai)
    ARM     SITE_SV, 17             @ 關機存檔 → stub_sv
    ARM     SITE_PQ, 18             @ 畫質指令 → stub_pq

    LDA     ip, F_DCACHE
    blx     ip
    LDA     ip, F_ICACHE
    blx     ip

    /* 7. 開機還原 RAW:上次關機時 stub_sv 把色彩存成 0x10 | lat | con << 1 | sat << 2。
     *    所有 hook 都裝好之後才做:經 setter 寫 0xC(與 shell `menu SetColorMode 12` 同一條,通知 PQ/LV/選單),
     *    pend = 17 讓 stub_mc 把它當成選了 RAW 列;flag 另外直接設(setter 沒通知時也生效)。 */
    LDA     r0, BANK_COLOR
    ldr     r1, [r0]
    sub     r1, r1, #0x10
    cmp     r1, #7
    bhi     9f
    and     r0, r1, #1
    str     r0, [r9, #P_VAR]
    lsr     r0, r1, #1
    and     r0, r0, #1
    str     r0, [r9, #P_CON]
    str     r0, [r9, #P_CONF]
    lsr     r0, r1, #2
    str     r0, [r9, #P_SAT]
    str     r0, [r9, #P_SATF]
    mov     r0, #17
    str     r0, [r9, #P_PEND]
    LDA     ip, F_ITEM
    blx     ip
    mov     r1, #0xC
    mov     r2, #1
    LDA     ip, F_SETCOLOR
    blx     ip
    mov     r0, #1
    str     r0, [r9, #P_FLAG]
    LDA     r0, CBM_STATE
    mov     r1, #0
    strb    r1, [r0, #0x84]

9:  add     sp, sp, #16
    mov     r0, #0
    pop     {r4-r11, ip, pc}

    .align  2
page_rel1:  .word page_tab - (13b + 8)
page_rel2:  .word page_tab - (16b + 8)
#include "rv_page.inc"
mat_rel1:   .word mat_stock - (22b + 8)
mat_rel2:   .word mat_new - (23b + 8)
#include "rv_mat.inc"
blob_rel1:  .word blob - (11b + 8)
blob_rel2:  .word blob - (12b + 8)
blob:
    /* build_bcolor.py 在這裡接上:常駐程式 | 表格資料 */
