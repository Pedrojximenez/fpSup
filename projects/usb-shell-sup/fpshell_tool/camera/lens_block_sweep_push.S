/* lens_block_sweep_push.S — 逐區塊讀鏡頭,**每讀完一個就推一幀**,整趟只要一個 BATCHPUSH。
 *
 * 為什麼是「每塊一幀」而不是「整批一次」:
 *   daemon 的 BATCHPUSH 對每一幀給 5 秒逾時。若整批掃完才推,71 個區塊要 21 秒,
 *   第一幀根本等不到 → 必然逾時(實測踩過)。每塊推一幀的話每幀只等約 0.3 秒。
 * 這樣 mem read 歸零,而 BATCHPUSH 只要 1 個(密集下 BATCHPUSH 會弄死端點,越少越好)。
 *
 * 進入:BATCHPUSH 的 `call 0xC072F600`(r0=STATE)
 *   STATE+0x60 = 起始 block id
 *   STATE+0x70 = 幀數(BATCHPUSH 的 nframes,同時就是要掃幾個區塊)
 *   STATE+0x78 = framesize(固定 0x848 = 2120 = 16 表頭 + 最大區塊 2101 + 對齊)
 *
 * 每幀 @0x4072F780(CPU 0xC072F780 的 uncached 別名,直接寫別名免清 cache):
 *   +0x00 id   +0x04 ok   +0x08 len   +0x0C nz   +0x10 資料
 */
.syntax unified
.arm
.text
.global _start
_start:
    push {r4-r11, lr}
    mov  r4, r0
    ldr  r8, [r4, #0x60]        @ 起始 id
    ldr  r7, [r4, #0x70]        @ 幀數 = 區塊數
    ldr  r6, [r4, #0x78]        @ framesize
    ldr  r5, .Lbuf              @ 固定緩衝區
.blk:
    cmp  r7, #0
    beq  .done
    movw r0, #0x436C            @ ROM 表 0xC0B94364 + id*0xC:{addr, len, flag}
    movt r0, #0xC0B9
    mov  r1, #0xC
    mul  r1, r8, r1
    ldr  r2, [r0, r1]           @ flag
    movw r0, #0x4368
    movt r0, #0xC0B9
    ldr  r3, [r0, r1]           @ len
    str  r8, [r5]
    mov  r0, #0
    str  r0, [r5, #4]           @ ok = 0
    str  r3, [r5, #8]           @ len
    str  r0, [r5, #0xC]         @ nz = 0
    cmp  r2, #1
    beq  .push                  @ flag==1 → 韌體拒讀,只送表頭
    movw r0, #0x54A0            @ ctx = FUN_c03554a0()
    movt r0, #0xC035
    blx  r0
    mov  r1, r8
    add  r2, r5, #0x10
    movw r3, #0x5DE0            @ FUN_c0355de0(ctx,id,dst) — 自帶 PreCommunicationSequence 鎖
    movt r3, #0xC035
    blx  r3
    str  r0, [r5, #4]           @ ok
    ldr  r3, [r5, #8]
    add  r10, r5, #0x10
    mov  r9, #0
    mov  r11, #0
.cnt:                           @ 非 0/非 FF 的位元組數 → 一眼看出有無真內容
    cmp  r11, r3
    bge  .cdone
    ldrb r0, [r10, r11]
    cmp  r0, #0
    beq  .cnx
    cmp  r0, #0xFF
    beq  .cnx
    add  r9, r9, #1
.cnx:
    add  r11, r11, #1
    b    .cnt
.cdone:
    str  r9, [r5, #0xC]
.push:
    movw r0, #0x3274            @ CTX4_TBL
    movt r0, #0xC31E
    ldr  r11, [r0]
    str  r5, [r11]              @ bufptr
    mov  r0, #0
    str  r0, [r11, #4]
    str  r6, [r11, #8]          @ size = framesize
    movw r0, #0x0813
    str  r0, [r11, #0xc]
    dsb
    mov  r0, #9
    movw r12, #0x6B81           @ FN_STARTX
    movt r12, #0xC01E
    blx  r12
    mov  r0, #4
    movw r1, #50000
    movw r12, #0x4E81           @ FN_WAIT — 擋到 host 收完這一幀才做下一個區塊
    movt r12, #0xC01E
    blx  r12
    add  r8, r8, #1
    subs r7, r7, #1
    b    .blk
.done:
    mov  r0, #0
    pop  {r4-r11, pc}
.align 2
.Lbuf: .word 0x4072F780
