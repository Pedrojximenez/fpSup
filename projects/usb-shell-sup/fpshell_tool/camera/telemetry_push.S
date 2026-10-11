/* telemetry_push.S — 相機主動推送遙測記錄(hook-push),取代儀表板的 host 輪詢。
 *
 * 為什麼:舊儀表板每 20-30ms 輪詢一次,每輪 10 幾筆 shell 交易 → 約 400 筆/秒,
 * 把 USB 端點打到 stall。改成相機端 arm ctx4 TRB + StartTransfer,host 只做 bulk-IN:
 * 一次 call 推 N 筆,零 per-sample 命令。
 *
 * 進入:worker `call`(blx, r0=STATE)。STATE+0x70=N, STATE+0x78=framesize(=0x60)。
 * 記錄寫在 0x4072F400 = CPU 0xC072F400 的 **uncached 別名** —— 直接寫別名就不必
 * 清 cache,DMA 讀到的一定是新值。
 *
 * 記錄格式(欄位配置預留到 96 bytes;phase 1 只推前 0x20 bytes,framesize 由 STATE+0x78 給。
 * 之後補 phase-2 欄位時只要把 framesize 調大,前 0x20 的配置不變 → host 不用改解析):
 *   +0x00 u32 magic 'FPT1' 0x31545046      +0x20 u32 af_drive      [phase2]
 *   +0x04 u32 seq                          +0x24 u32 af_area       [phase2]
 *   +0x08 i16 gyro X,Y,Z,pad               +0x28 u32 af_route      [phase2]
 *   +0x10 i16 accel X,Y,Z,pad              +0x2C u32 af_con_hi     [phase2]
 *   +0x18 u32 gyro ring cursor(去重用)     +0x30 u32 af_con_lo     [phase2]
 *   +0x1C u32 flags  bit0=IMU 有效          +0x34 u32 af_peak_now   [phase2]
 *                                          +0x38 i16 aat x,y,w,h   [phase2]
 *                                          +0x40 i16 aat_conf,face_mode
 *                                          +0x44 i16 face x,y,w,h  [phase2]
 *                                          +0x4C u32 gain_state    [phase2]
 *                                          +0x50 u32 iso           [phase2]
 *                                          +0x54 u32 analog_gain   [phase2]
 *                                          +0x58 u32 hcg           [phase2]
 * 注意:gyro 2500Hz 但推送速率由 host bulk-IN 決定,可能重複取樣 —— host 用 +0x18
 * 的 ring cursor 去重即可。
 */
.syntax unified
.arm
.text
.global _start
_start:
    push {r4-r11, lr}
    mov  r4, r0
    ldr  r7, [r4, #0x70]        @ N
    ldr  r6, [r4, #0x78]        @ framesize
    ldr  r8, .Lrec              @ 記錄 base(uncached 別名)
    mov  r9, #0                 @ seq
    ldr  r0, .Lmagic
    str  r0, [r8]
    mov  r0, #3
    str  r0, [r8, #0x1C]        @ flags: bit0=IMU bit1=AF/框/曝光 皆有效
.tloop:
    str  r9, [r8, #4]           @ seq
    ldr  r1, .Laccel            @ MMA8452Q 快取
    ldrsh r2, [r1]
    ldrsh r3, [r1, #2]
    ldrsh r0, [r1, #4]
    strh  r2, [r8, #0x10]
    strh  r3, [r8, #0x12]
    strh  r0, [r8, #0x14]
    ldr  r1, .Lgmbox            @ 0xC31E3FCC → P → ring
    ldr  r1, [r1]
    ldr  r2, [r1, #0x60]
    ldr  r3, [r2]               @ cursor = latest_sample_start + 4
    str  r3, [r8, #0x18]
    sub  r3, r3, #4
    ldrsh r0, [r3]              @ gyro X
    ldrsh r1, [r3, #2]          @ gyro Y
    ldrsh r2, [r3, #6]          @ gyro Z (X,Y,pad,Z)
    strh  r0, [r8, #0x08]
    strh  r1, [r8, #0x0A]
    strh  r2, [r8, #0x0C]
    @ ---- phase 2:AF / 追蹤框 / 人臉 / 曝光(同一趟 gather,不增加任何 USB 命令) ----
    movw r0, #0x65A0
    movt r0, #0xC320
    ldr  r1, [r0]
    str  r1, [r8, #0x20]      @ af_drive
    movw r0, #0x46A4
    movt r0, #0xC320
    ldr  r1, [r0]
    str  r1, [r8, #0x24]      @ af_area
    movw r0, #0x15B0
    movt r0, #0xC329
    ldr  r1, [r0]
    str  r1, [r8, #0x28]      @ af_route
    movw r0, #0x85E8
    movt r0, #0xC329
    ldr  r1, [r0]
    str  r1, [r8, #0x2C]      @ af_con_hi
    movw r0, #0x86B4
    movt r0, #0xC329
    ldr  r1, [r0]
    str  r1, [r8, #0x30]      @ af_con_lo
    movw r0, #0x15C4
    movt r0, #0xC329
    ldr  r1, [r0]
    str  r1, [r8, #0x34]      @ af_peak_now
    movw r0, #0xA6AC
    movt r0, #0xC343
    ldr  r1, [r0]
    str  r1, [r8, #0x4C]      @ gain_state
    movw r0, #0xA6B8
    movt r0, #0xC343
    ldr  r1, [r0]
    str  r1, [r8, #0x50]      @ iso
    movw r0, #0xA6CC
    movt r0, #0xC343
    ldr  r1, [r0]
    str  r1, [r8, #0x54]      @ analog_gain
    movw r0, #0xA6D4
    movt r0, #0xC343
    ldrb r1, [r0]
    str  r1, [r8, #0x58]      @ hcg (byte → u32)
    movw r0, #0x3E00          @ 追蹤框 0xC3033E00 {i16 x,y,w,h}
    movt r0, #0xC303
    ldrsh r1, [r0]
    ldrsh r2, [r0, #2]
    ldrsh r3, [r0, #4]
    strh  r1, [r8, #0x38]
    strh  r2, [r8, #0x3A]
    strh  r3, [r8, #0x3C]
    ldrsh r1, [r0, #6]
    ldrsh r2, [r0, #0x26]     @ 信心值 @0xC3033E26
    strh  r1, [r8, #0x3E]
    strh  r2, [r8, #0x40]
    movw r0, #0xCE6C          @ 人臉 mode 0xC37CCA9C+0x3D0
    movt r0, #0xC37C
    ldr  r1, [r0]
    strh r1, [r8, #0x42]
    movw r0, #0xCE7C          @ 人臉框 0xC37CCA9C+0x3E0
    movt r0, #0xC37C
    ldrsh r1, [r0]
    ldrsh r2, [r0, #2]
    ldrsh r3, [r0, #4]
    strh  r1, [r8, #0x44]
    strh  r2, [r8, #0x46]
    strh  r3, [r8, #0x48]
    ldrsh r1, [r0, #6]
    strh  r1, [r8, #0x4A]
    dsb
    movw r0, #0x3274            @ CTX4_TBL
    movt r0, #0xC31E
    ldr  r5, [r0]               @ TRB(bus alias)
    str  r8, [r5]               @ bufptr = 記錄
    mov  r0, #0
    str  r0, [r5, #4]           @ BPTRH
    str  r6, [r5, #8]           @ size
    movw r0, #0x0813            @ HWO|LST|IOC
    str  r0, [r5, #0xc]
    dsb
    mov  r0, #9                 @ EP84
    movw r12, #0x6B81           @ FN_STARTX
    movt r12, #0xC01E
    blx  r12
    mov  r0, #4
    movw r1, #50000             @ TMO
    movw r12, #0x4E81           @ FN_WAIT
    movt r12, #0xC01E
    blx  r12
    add  r9, r9, #1
    subs r7, r7, #1
    bne  .tloop
    mov  r0, #0
    pop  {r4-r11, pc}
.align 2
.Lrec:    .word 0x4072F400
.Laccel:  .word 0xC377790C
.Lgmbox:  .word 0xC31E3FCC
.Lmagic:  .word 0x31545046
