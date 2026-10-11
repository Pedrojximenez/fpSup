.syntax unified
.arm
.text
/* Stream the gyro ring straight to a card file from a background task.
 *
 * The point is to prove the mechanism the small-buffer design needs -- a file held
 * open while a separate task appends to it repeatedly -- without needing recording,
 * and without an intermediate buffer at all. The ring IS the buffer: it holds 600
 * samples (240 ms at 2500 Hz), so polling every 100 ms cannot lose anything, and
 * each poll writes only the span that appeared since the last one. Ten writes a
 * second is a harsher test than the once-a-second the real design will do.
 *
 * CTL: [0]=run flag, host writes 1 to start and 0 to stop
 *      [4]=task state (0 idle, 1 running, 2 finished)  [8]=bytes written
 *      [12]=write calls  [16]=poll iterations  [20]=open ret  [24]=wraps
 *      [28]=create id    [32]=start ret
 * PATH at CTL+0x40, written by the host before starting.
 */
/* 位址依 SHELL_MEMORY_MAP.md 配置。原本 CTL 放在 0xC072F600 —— 那是 push_addr
 * 常式的位址,清空 CTL 就把推送常式抹掉,BATCHPUSH 接著去執行垃圾,相機凍結。
 * 常式與狀態永遠分開配置。 */
/* 狀態與緩衝放 bufmem 池(0x44F6ADC0 起),不跟 0xC072Fxxx 的常式擠 ——
 * 那個視窗真正空著的只有兩段共 512 bytes,而我已經在那裡撞車三次,
 * 其中兩次要拔電池。詳見 SHELL_MEMORY_MAP.md。 */
.equ POOL,      0x44F6ADC0
.equ CTL,       0x44F6ADC0
.equ PATHBUF,   0x44F6AE00
.equ FILEOBJ,   0x44F6AE40
.equ RING_PTR,  0xC31E3FCC
.equ RING_SIZE, 0x12C4
.equ FN_CRETSK, 0xC0016A58
.equ FN_STATSK, 0xC0016BC0
.equ FN_SLEEP,  0xC01F89C4
.equ WORKER_PRI, 0x1C

.macro la reg, value
    movw    \reg, #:lower16:\value
    movt    \reg, #:upper16:\value
.endm

.global cave_entry
cave_entry:
    push    {r4, lr}
    la      r4, CTL
    sub     sp, sp, #32
    mov     r0, #0
    str     r0, [sp, #0]
    mov     r0, #0x41
    str     r0, [sp, #4]
    adr     r0, stream_task
    str     r0, [sp, #8]
    mov     r0, #WORKER_PRI
    str     r0, [sp, #12]
    movw    r0, #0x2000              /* 唯一驗證過的值,不要動 */
    str     r0, [sp, #16]
    movw    r0, #0x5947              @ "GY"
    movt    r0, #0x5453              @ "ST" -> "GYST"
    str     r0, [sp, #20]
    movw    r0, #0x0052              @ "R\0"
    str     r0, [sp, #24]
    mov     r0, #0
    str     r0, [sp, #28]
    mov     r0, sp
    la      ip, FN_CRETSK
    blx     ip
    add     sp, sp, #32
    str     r0, [r4, #28]
    cmp     r0, #0
    ble     1f
    mov     r1, #0
    la      ip, FN_STATSK
    blx     ip
    str     r0, [r4, #32]
1:  mov     r0, #0
    pop     {r4, pc}

/* ---- the task ---- */
stream_task:
    push    {r4-r11, lr}
    la      r4, CTL
    mov     r0, #1
    str     r0, [r4, #4]

    /* open once */
    mov     r0, #1
    str     r0, [r4, #40]
    la      ip, 0xC0444658
    blx     ip
    mov     r1, #0
    la      ip, 0xC0444698
    blx     ip
    mov     r1, r0
    la      r0, CTL
    mov     r2, #2
    str     r2, [r0, #40]
    la      r0, FILEOBJ
    la      ip, 0xC0365E90
    blx     ip
    la      r0, CTL
    mov     r2, #3
    str     r2, [r0, #40]
    la      r0, FILEOBJ
    la      r1, PATHBUF
    mov     r2, #7                   @ 7 overwrites; 0x402 would fail on a rerun
    la      ip, 0xC0365FB0
    blx     ip
    str     r0, [r4, #20]
    mov     r2, #4
    str     r2, [r4, #40]
    cmp     r0, #0
    beq     9f

    /* r5 = ring base, r6 = last head */
    la      r0, RING_PTR
    ldr     r0, [r0]
    ldr     r5, [r0, #0x60]
    ldr     r6, [r5]

poll_loop:
    mov     r0, #5
    str     r0, [r4, #40]
    ldr     r0, [r4]
    cmp     r0, #0
    beq     8f
    ldr     r0, [r4, #16]
    add     r0, r0, #1
    str     r0, [r4, #16]

    ldr     r7, [r5]                 @ current head
    cmp     r7, r6
    beq     5f
    bhi     3f
    /* wrapped: write [r6, end) then [0, r7) */
    ldr     r0, [r4, #24]
    add     r0, r0, #1
    str     r0, [r4, #24]
    add     r0, r5, #4
    add     r0, r0, r6
    movw    r1, #RING_SIZE
    sub     r1, r1, r6
    bl      wr_span
    add     r0, r5, #4
    mov     r1, r7
    bl      wr_span
    b       4f
3:  add     r0, r5, #4
    add     r0, r0, r6
    sub     r1, r7, r6
    bl      wr_span
4:  mov     r6, r7
5:
    mov     r0, #6
    str     r0, [r4, #40]
    mov     r0, #100
    la      ip, FN_SLEEP
    blx     ip
    b       poll_loop

8:  la      r0, FILEOBJ
    la      ip, 0xC0366020
    blx     ip
9:  la      r0, FILEOBJ
    mov     r1, #2
    la      ip, 0xC0365ED0
    blx     ip
    la      r4, CTL
    mov     r0, #2
    str     r0, [r4, #4]
10: mov     r0, #1000                @ park; the task is not deleted, only idled
    la      ip, FN_SLEEP
    blx     ip
    b       10b

/* r0 = source, r1 = byte count */
wr_span:
    push    {r4-r6, lr}
    cmp     r1, #0
    beq     1f
    mov     r5, r1
    mov     r4, r0
    la      r6, CTL
    mov     r0, #7
    str     r0, [r6, #40]            @ 進入寫入呼叫
    str     r4, [r6, #44]            @ 來源位址
    str     r5, [r6, #48]            @ 長度
    la      r0, FILEOBJ
    mov     r2, r5
    mov     r1, r4
    la      ip, 0xC03660E8
    blx     ip
    la      r6, CTL
    mov     r1, #8
    str     r1, [r6, #40]            @ 寫入呼叫已返回
    str     r0, [r6, #36]            @ last write return (24 is the wrap counter)
    ldr     r0, [r6, #8]
    add     r0, r0, r5
    str     r0, [r6, #8]
    ldr     r0, [r6, #12]
    add     r0, r0, #1
    str     r0, [r6, #12]
1:  pop     {r4-r6, pc}
