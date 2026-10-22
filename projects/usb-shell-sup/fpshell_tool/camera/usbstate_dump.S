.syntax unified
.arm
.text
/* 在切換到 CDC 模式之後,把 USB 控制器狀態 dump 到卡上。
 *
 * 為什麼要這樣做:CDC 模式下 vendor 通道消失,沒有任何方式跟相機說話,
 * 所以不能互動式探索。這個常式掛在陀螺 hook(~90 Hz,跟 USB 無關),
 * 在被啟用後倒數,時間到就自己寫檔 —— 那時 host 早就切走了。
 *
 * 流程:vendor 模式下注入並啟用 → shl usb cdc → 等倒數結束 → 拔電池讀卡。
 *
 * 抓什麼:
 *   +0x000  64 B  MMIO/暫存器快照(DALEPENA 等,不能直接餵給檔案 API 所以先複製)
 *   +0x040  4 KB  0xC31E3000 USB 控制器結構(worker 用的那幾個位址都在裡面)
 *   +0x1040 512 B 0xC3079340 vendor 描述元暫存區
 *   +0x1240 512 B 0xC307A0C0 MSC/CDC 描述元暫存區
 *
 * 狀態放 bufmem 池尾,避開 shell 自己的 4 KB 指令緩衝(0x44F6ADC0..0x44F6BDC0)。
 */

.equ CHAIN,      0xC01EC6F9
.equ ACTIVE,     0xC072F480      /* 主機寫 1 開始倒數 */
.equ ST,         0x44F6BE00      /* 狀態 */
.equ SNAP,       0x44F6BF00      /* 快照緩衝起點 */
.equ PATHBUF,    0x44F6BE80
.equ FILEOBJ,    0x44F6BEC0
.equ DELAY_TICKS, 1800           /* ~90 Hz x 20 秒 */

.equ USB_STRUCT, 0xC31E3000
.equ DALEPENA,   0x2100C720
.equ VEND_STAGE, 0xC3079340
.equ MSC_STAGE,  0xC307A0C0

.macro la reg, value
    movw    \reg, #:lower16:\value
    movt    \reg, #:upper16:\value
.endm

.global hook_entry
hook_entry:
    push    {r3-r11, lr}             /* 十個 —— 8-byte 對齊 */
    la      ip, CHAIN
    blx     ip
    mov     r11, r0

    la      r10, ST
    ldr     r0, [r10]
    la      r1, 0x44554D50           /* 'DUMP' */
    cmp     r0, r1
    beq     1f
    str     r1, [r10]
    mov     r0, #0
    str     r0, [r10, #4]            /* tick */
    str     r0, [r10, #8]            /* done */
    str     r0, [r10, #12]           /* open ret */
    str     r0, [r10, #16]           /* write ret */
1:
    la      r0, ACTIVE
    ldr     r0, [r0]
    cmp     r0, #0
    beq     out
    ldr     r0, [r10, #8]
    cmp     r0, #0
    bne     out                      /* 只做一次 */
    ldr     r0, [r10, #4]
    add     r0, r0, #1
    str     r0, [r10, #4]
    movw    r1, #DELAY_TICKS
    cmp     r0, r1
    blo     out

    mov     r0, #1
    str     r0, [r10, #8]            /* 標記已做,避免重入 */

    /* ---- 快照 MMIO(檔案 API 不見得能從 MMIO 取 DMA,先複製) ---- */
    la      r4, SNAP
    la      r0, DALEPENA
    ldr     r1, [r0]
    str     r1, [r4]
    ldr     r1, [r0, #4]
    str     r1, [r4, #4]
    ldr     r1, [r0, #8]
    str     r1, [r4, #8]
    la      r0, 0x2100C700
    ldr     r1, [r0]
    str     r1, [r4, #12]
    ldr     r1, [r0, #4]
    str     r1, [r4, #16]
    mov     r0, #0
    str     r0, [r4, #20]
    str     r0, [r4, #24]
    str     r0, [r4, #28]

    /* ---- 路徑 ---- */
    adr     r0, s_path
    la      r1, PATHBUF
2:  ldrb    r2, [r0], #1
    strb    r2, [r1], #1
    cmp     r2, #0
    bne     2b

    /* ---- 開檔 ---- */
    la      ip, 0xC0444658
    blx     ip
    mov     r1, #0
    la      ip, 0xC0444698
    blx     ip
    mov     r1, r0
    la      r0, FILEOBJ
    la      ip, 0xC0365E90
    blx     ip
    la      r0, FILEOBJ
    la      r1, PATHBUF
    mov     r2, #7                   /* 7 可覆寫 */
    la      ip, 0xC0365FB0
    blx     ip
    str     r0, [r10, #12]
    cmp     r0, #0
    beq     out

    /* ---- 四段寫入 ---- */
    la      r0, SNAP
    mov     r1, #0x40
    bl      wr
    la      r0, USB_STRUCT
    movw    r1, #0x1000
    bl      wr
    la      r0, VEND_STAGE
    movw    r1, #0x200
    bl      wr
    la      r0, MSC_STAGE
    movw    r1, #0x200
    bl      wr

    la      r0, FILEOBJ
    la      ip, 0xC0366020           /* close */
    blx     ip
    la      r0, FILEOBJ
    mov     r1, #2
    la      ip, 0xC0365ED0
    blx     ip
out:
    mov     r0, r11
    pop     {r3-r11, pc}

/* r0 = 來源, r1 = 長度 */
wr:
    push    {r4-r6, lr}
    mov     r4, r0
    mov     r5, r1
    la      r0, FILEOBJ
    mov     r1, r4
    mov     r2, r5
    la      ip, 0xC03660E8
    blx     ip
    la      r6, ST
    str     r0, [r6, #16]
    pop     {r4-r6, pc}

.align 2
s_path: .asciz "\\USBDUMP.BIN"
.align 2
