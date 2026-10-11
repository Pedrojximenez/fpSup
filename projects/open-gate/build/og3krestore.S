.syntax unified
.arm
.text
#include "og_pic.inc"
/* ============================================================================
 * og3krestore —— 開機時把使用者上次選的 OG 解析度還原回去。每次載入只跑一次。
 * ============================================================================
 * 2026-09-23 起由 loader 的 VSHL entry 呼叫(build_autorun.py --vshl-entry),
 * 不再在 AutoRun 末端借 echo 槽。差別:
 *   - 只有 fpSup.BIN 開檔、magic、配置都成功,stage2 放完所有 firmware-address
 *     sections 並 publish D/I cache 之後才會走到這裡。舊的 echo 呼叫不看 loader
 *     成敗,載入失敗時會跳進沒寫過的 cave。
 *   - 仍在同一個 task:loader 本身就是 AutoRun 借 echo handler 叫起來的,
 *     跑在 shell dispatcher 的工作裡 —— 與 `menu SetMovRecSize` 同一個情境。
 *     時間點比舊位置早,中間只差 AutoRun 末端的 display osd/text 幾行。
 *   - debug 版有 USB worker 時由 entries.S trampoline 依序叫:worker 先、這裡後。
 * 此換位**尚未上機驗證**。見 notes/OG_BOOT_RESTORE_STABILITY_REVIEW_2026-09-23.md。
 *
 * 2026-09-21 在舊位置實機驗證過:AutoRun 末端 `menu SetMovRecSize 4`,重開機後
 * RecSize=4、FLAG=1、og3ksel 次數=1,錄一段 file-size=4,143,104(OG2K 12-bit)、
 * req=fin=48。
 *
 * 為什麼不直接在 AutoRun 寫死那一行:AutoRun 是線性腳本,沒有條件分支。
 * 無條件寫死會害「上次用 FHD」的使用者每次開機被改成 OG。判斷必須在程式碼裡。
 *
 * 步驟,任何一步不成立就跳過本次還原,不重試、不 rollback:
 *   0. 本次載入第二次以上進來 → 什麼都不做(結果字保留第一次的)。
 *   1. 向原廠 getter 問**真實的**錄影格式,鎖存進 FMTLATCH。無論後面是否還原
 *      都要做:FMTLATCH 開機值是 UNKNOWN(0xFFFFFFFF),在這之前 og3ksel
 *      一律當成「非 CinemaDNG、不生效」,不會走進 §38 的 MOV 凍結。
 *   2. 讀 OGSAVE(跨電源循環,由 og3ksel 寫)。不是 1 → 跳過。
 *   3. 格式不是 CinemaDNG → 跳過。
 *   4. 錄影忙碌 → 跳過。三個訊號沿用 gyro logger(同韌體 Ver.5.02 實測):
 *        MovieRecording  selector 0xC347D1D4 == 0x21 讀 0xC3476609,否則 0xC347E08F
 *        XMP 檔案物件    0xC358E140 非 0 = CinemaDNG clip 已開檔(失敗的 open
 *                        也可能留下非 0 —— 那就保守跳過)
 *        MOV active      0xC35A952C 非 0 = MOV 仍在寫,到 ImageSave 為止
 *      這**不是**與 REC 的互斥:最後一次檢查到 setter 之間仍可能有新 REC。
 *      只是把「已知在錄/在寫」的狀態排除掉。這三個值在開機這一刻的讀數尚未
 *      上機確認 —— 若任何一個開機時就殘留非 0,還原會永遠被跳過,看結果碼。
 *   5. 呼叫真正的解析度 setter 設回 enum 4。FLAG / GTAB / donor 時序全部由
 *      og3ksel 自己發布,這裡不複製那段邏輯。之後把 FLAG 讀回記下 ——
 *      FLAG=1 只代表 og3ksel 發布了,不代表整條管線已切換完成。
 *   6. FLAG=1 時讓 live view 重讀顯示 profile。setter 與 og3ksel 只改了 profile 表
 *      (可見高 1125 → 1334),但 MovSigProcess 只在「停止→啟動」時才把表複製並
 *      輸出給引擎(FUN_c0428ab8:param_1[2]==0 才走 FUN_c0437668 + FUN_c0429910)。
 *      開機時它早已用 1125 跑起來,所以畫面停在 16:9,要等半按換成 sensor mode
 *      不同的兄弟 profile 才會重啟。這裡照 setChangeSensorMode(c022df68)的順序,
 *      只是不改 sensor mode:CamSch1 狀態切 6 → stop → start → 狀態還原。
 *      MovSigProcess 沒在跑就不碰(stop 此時是 no-op,但 start 會主動把它啟動);
 *      它之後自己啟動時自然會讀到 1334。
 *      2026-09-24 實機(從 shell task 呼叫同一段):可見區 1125 → 1334,畫面變 3:2,
 *      無閃爍,之後半按與 QS 正常。同一狀態下 QS 的 LvRestart
 *      (FUN_c04a9078(LVRSTCK()))、單獨呼叫其守衛、靜置 5 分鐘都沒有效果。
 *
 * RLOG:+0x00 次數  +0x04 看到的 OGSAVE  +0x08 看到的格式
 *       +0x0C 結果碼(下表,0 = 沒跑到)  +0x10 還原後讀回的 FLAG
 *       +0x14 LV 重讀:0 沒試  1 已停止再啟動  2 FLAG 不是 1  3 MovSigProcess 沒在跑
 *       +0x18 重讀時看到的 CamSch1 狀態(實測待機為 1)
 * ========================================================================== */

.equ FMTLATCH,  OGA(0xC0731C20)      /* 0 = CinemaDNG;開機值 UNKNOWN,由這裡寫成真值 */
.equ RLOG,      OGA(0xC0731C24)      /* 見上方 RLOG 說明 */
.equ FLAG,      OGA(0xC0731C08)      /* og3ksel 發布的「OG 生效」 */
.equ OGSAVE,    0xC30754CC      /* XC_CommonSaveData +0x290,跨電源循環 */
#ifndef OG_ENUM
#define OG_ENUM 4
#endif

/* 結果碼,寫在 RLOG+0x0C */
.equ R_RESTORED,  1             /* 呼叫了 setter */
.equ R_NOPREF,    2             /* OGSAVE != 1 */
.equ R_FORMAT,    3             /* 不是 CinemaDNG */
.equ R_MOVREC,    4             /* MovieRecording 非 0 */
.equ R_XMPFILE,   5             /* CinemaDNG clip 檔案物件存在 */
.equ R_MOVWRITE,  6             /* MOV 仍在寫 */

/* 錄影忙碌訊號,與 gyro-sup logger.S / lifecycle.inc.S 同一組位址 */
.equ MOV_SELECTOR, 0xC347D1D4   /* 0xC347D1C0 + 0x14,0x21 時 MovieRecording 在另一個物件 */
.equ MOVREC_DEFAULT, 0xC347E08F /* 0xC347DF38 + 0x157 */
.equ MOVREC_SEL21,   0xC3476609 /* 0xC34765CC + 0x3D */
.equ XMP_FOBJ_PTR, 0xC358E140
.equ MOV_ACTIVE,   0xC35A952C

/* LV 重讀結果,寫在 RLOG+0x14 */
.equ L_RELOADED,  1
.equ L_NOFLAG,    2
.equ L_NOTRUN,    3             /* MovSigProcess 沒在跑:不碰 */

/* 照 setChangeSensorMode(c022df68)的停止/啟動,不改 sensor mode */
.equ CAMSCH1,     0xC0207188    /* () -> 相機排程物件 */
.equ CS_GET,      0xC0207440    /* (cs) -> *(cs+4) 狀態 */
.equ CS_SET,      0xC02073B8    /* (cs, v):cs[1]=v、cs[0]=0 */
.equ LV_HOLDER,   0xC0423C48    /* () -> 持有 MovSigProcess 指標的物件(0xC375BA2C) */
.equ LV_STOP,     0xC0423D28    /* (holder) -> FUN_c0428da0 */
.equ LV_START,    0xC0423C88    /* (holder) -> FUN_c0428ab8:停止時才重建並輸出 */

/* 原廠進入點。三個都是 SetMovRecSize / SetMovRecFormat 的 shell 處理器
 * 自己在用的,呼叫慣例照抄那裡(見 0xC03FDAB0 / 0xC03FD960)。 */
.equ GET_OBJ,   0xC0057AE8      /* 無參數,回傳設定物件 */
.equ GET_FMT,   0xC005BE90      /* r0 = obj,回傳目前的錄影格式 */
.equ SET_RES,   0xC005C020      /* r0 = obj, r1 = enum, r2 = 1 */

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
    push    {r4, r5, r6, lr}

    /* 0. 每次載入只做一次。state() 在 entry 之前把 RLOG 歸零。 */
    LDA     r6, RLOG
    ldr     r4, [r6]
    add     r4, r4, #1
    str     r4, [r6]                    @ 跑過幾次
    cmp     r4, #1
    bne     out                         @ 重複進來:不動結果字

    /* 1. 問真實格式並鎖存 —— 取代開機時的 UNKNOWN */
    LDA     r4, GET_OBJ
    blx     r4
    LDA     r4, GET_FMT
    blx     r4
    mov     r5, r0                      @ r5 = 目前的錄影格式
    LDA     r4, FMTLATCH
    str     r5, [r4]
    str     r5, [r6, #8]
    dmb     ish

    /* 2. 讀跨電源循環的那個位元 */
    LDA     r4, OGSAVE
    ldr     r4, [r4]
    str     r4, [r6, #4]
    mov     r0, #R_NOPREF
#ifdef OG_SAVE_ENUM
    cmp     r4, #OG_ENUM                @ v3: OGSAVE = the chosen OG's enum (og3ksel)
#else
    cmp     r4, #1
#endif
    bne     done

    /* 3. 只有在格式是 CinemaDNG 時才還原 —— 否則正好踩進 §38 那條凍結 */
    mov     r0, #R_FORMAT
    cmp     r5, #0
    bne     done

    /* 4. 錄影忙碌就跳過。盡量貼近 setter 再檢查,縮小(但不能消除)窗口。 */
    /* 注意:不能照 logger.S 寫 `movwne r3, #0xE08F` 共用高半 ——
     * MOVW 會把高 16 位清成 0,讀到的是 0x0000E08F。兩個位址都完整載入。 */
    LDA     r3, MOV_SELECTOR
    ldr     r2, [r3]
    cmp     r2, #0x21
    LDA     r3, MOVREC_DEFAULT          @ movw/movt 不動旗標
    bne     1f
    LDA     r3, MOVREC_SEL21
1:  ldrb    r2, [r3]
    mov     r0, #R_MOVREC
    cmp     r2, #0
    bne     done

    LDA     r3, XMP_FOBJ_PTR
    ldr     r2, [r3]
    mov     r0, #R_XMPFILE
    cmp     r2, #0
    bne     done

    LDA     r3, MOV_ACTIVE
    ldrb    r2, [r3]
    mov     r0, #R_MOVWRITE
    cmp     r2, #0
    bne     done

    /* 5. 走真 setter;og3ksel 看到的 FMTLATCH 已是步驟 1 的真值 */
    LDA     r4, GET_OBJ
    blx     r4
    mov     r1, #OG_ENUM
    mov     r2, #1
    LDA     r4, SET_RES
    blx     r4
    LDA     r4, FLAG
    ldr     r4, [r4]
    str     r4, [r6, #0x10]             @ 讀回:og3ksel 有沒有發布

    /* 6. OG 真的生效才讓 LV 重讀顯示 profile,畫面換成 3:2 */
    mov     r5, #L_NOFLAG
    cmp     r4, #1
    bne     lvdone
    bl      lvreload
    mov     r5, r0
lvdone:
    str     r5, [r6, #0x14]
    mov     r0, #R_RESTORED

done:
    str     r0, [r6, #0x0C]
    dmb     ish
out:
    mov     r0, #0
    pop     {r4, r5, r6, pc}

/* ---------------------------------------------------------------------------
 * lvreload:MovSigProcess 在跑才停止再啟動。回傳 L_RELOADED 或 L_NOTRUN;
 * 看到的 CamSch1 狀態寫在 RLOG+0x18。
 * ------------------------------------------------------------------------- */
lvreload:
    push    {r4, r5, r6, lr}
    LDA     ip, LV_HOLDER
    blx     ip
    mov     r6, r0                      @ holder
    ldr     r1, [r0]                    @ MovSigProcess 物件
    cmp     r1, #0                      @ 還沒建立:當成沒在跑
    ldrne   r1, [r1, #4]                @ stop 自己用的「有在跑」判斷
    cmp     r1, #0
    moveq   r0, #L_NOTRUN
    beq     9f
    LDA     ip, CAMSCH1
    blx     ip
    mov     r4, r0                      @ cs
    LDA     ip, CS_GET
    blx     ip
    mov     r5, r0                      @ 原本的狀態
    LDA     ip, RLOG
    str     r5, [ip, #0x18]
    cmp     r5, #6
    beq     1f
    mov     r0, r4
    mov     r1, #6
    LDA     ip, CS_SET
    blx     ip
1:  mov     r0, r6
    LDA     ip, LV_STOP
    blx     ip
    mov     r0, r6
    LDA     ip, LV_START
    blx     ip
    cmp     r5, #6
    beq     2f
    mov     r0, r4
    mov     r1, r5
    LDA     ip, CS_SET
    blx     ip
2:  mov     r0, #L_RELOADED
9:  pop     {r4, r5, r6, pc}

