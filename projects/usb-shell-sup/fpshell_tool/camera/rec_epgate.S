.syntax unified
.arm
.text
/* 錄影期間關閉 vendor 端點,錄完自動恢復。
 *
 * 問題:USB shell 的 worker 在開機時做一次 `DALEPENA |= 0x600`(啟用 EP84-IN/EP05-OUT),
 * 之後**永遠不關**。它的 admission gate 只在 bring-up 時檢查一次錄影旗標
 * (`ag_admitted` 被 STATE+0x3C 的一次性旗標擋住),所以錄影開始時端點還開著。
 * 韌體自己的 gadget(PTP)會管理這個暫存器,我們的不會 —— 差別就在這。
 *
 * 而先前的 "pre-disarm hook" 依賴 record-start 呼叫 FUN_c01e62a8(0),但實測
 * record-start 根本不呼叫它,所以那道保護從沒生效。這裡改由我們自己的 hook
 * (~90 Hz)主動輪詢,不依賴任何韌體呼叫。
 *
 * 只清我們自己設的那兩個位元,不動別人的。恢復時做 3 次去彈跳,避免在 record-start
 * 的旗標抖動中反覆切換。
 *
 * 狀態(cave 區,主機可讀寫,不碰 bufmem 池):
 *   +0  magic  +4 我們是否已關閉(1=關閉中)  +8 去彈跳計數
 *   +12 切換次數  +16 最後讀到的 REC_FLAG  +20 hook 進入次數
 */

.equ CHAIN,       0xC01EC6F9      /* 被取代的原指令 BLX 目標 */
.equ REC_FLAG,    0xC347E08F
.equ DALEPENA,    0x2100C720      /* DWC3 硬體暫存器 */
.equ DALEPENA_SH, 0xC31E398C      /* 韌體 shadow */
.equ EP_BITS,     0x600           /* EP84-IN(4) + EP05-OUT(5) */
.equ ST,          0xC072F4A0

.macro la reg, value
    movw    \reg, #:lower16:\value
    movt    \reg, #:upper16:\value
.endm

.global hook_entry
hook_entry:
    push    {r3-r11, lr}             /* 十個 —— 維持 8-byte 對齊 */
    la      ip, CHAIN
    blx     ip
    mov     r11, r0

    la      r10, ST
    /* 自我初始化:池/cave 的殘留值不可信 */
    ldr     r0, [r10]
    la      r1, 0x45504731           /* 'EPG1' */
    cmp     r0, r1
    beq     1f
    str     r1, [r10]
    mov     r0, #0
    str     r0, [r10, #4]
    str     r0, [r10, #8]
    str     r0, [r10, #12]
    str     r0, [r10, #16]
    str     r0, [r10, #20]
1:
    ldr     r0, [r10, #20]
    add     r0, r0, #1
    str     r0, [r10, #20]

    la      r0, REC_FLAG
    ldrb    r0, [r0]
    str     r0, [r10, #16]
    cmp     r0, #0
    beq     not_recording

    /* ---- 錄影中:若尚未關閉,立刻關 ---- */
    mov     r0, #0
    str     r0, [r10, #8]            /* 去彈跳計數歸零 */
    ldr     r0, [r10, #4]
    cmp     r0, #0
    bne     done                     /* 已經關了 */
    la      r0, DALEPENA
    ldr     r1, [r0]
    la      r2, EP_BITS
    bic     r1, r1, r2
    str     r1, [r0]
    la      r0, DALEPENA_SH
    ldr     r1, [r0]
    la      r2, EP_BITS
    bic     r1, r1, r2
    str     r1, [r0]
    mov     r0, #1
    str     r0, [r10, #4]
    ldr     r0, [r10, #12]
    add     r0, r0, #1
    str     r0, [r10, #12]
    b       done

not_recording:
    ldr     r0, [r10, #4]
    cmp     r0, #0
    beq     done                     /* 本來就沒關 */
    /* 去彈跳:連續 3 次讀到 clear 才恢復,避免 record-start 抖動 */
    ldr     r0, [r10, #8]
    add     r0, r0, #1
    str     r0, [r10, #8]
    cmp     r0, #3
    blo     done
    la      r0, DALEPENA
    ldr     r1, [r0]
    la      r2, EP_BITS
    orr     r1, r1, r2
    str     r1, [r0]
    la      r0, DALEPENA_SH
    ldr     r1, [r0]
    la      r2, EP_BITS
    orr     r1, r1, r2
    str     r1, [r0]
    mov     r0, #0
    str     r0, [r10, #4]
    str     r0, [r10, #8]
    ldr     r0, [r10, #12]
    add     r0, r0, #1
    str     r0, [r10, #12]
done:
    mov     r0, r11
    pop     {r3-r11, pc}
