.syntax unified
.arm
.global _start
/* push_addr: r0=STATE。從任意位址推 N 幀出去。
 *   STATE+0x60 = 來源位址(bus 視角,CPU 位址減 0x80000000)
 *   STATE+0x70 = N (BATCHPUSH 的 nframes)
 *   STATE+0x78 = framesize
 * 用 +0x60 帶來源是因為 BATCHPUSH 會覆寫 +0x74。
 * 每幀 arm ctx4 → StartTransfer(9) → wait(4),與 host 的 bulk-IN 同步。*/
_start:
    push {r4-r9, lr}
    mov  r4, r0
    ldr  r7, [r4, #0x70]
    ldr  r8, [r4, #0x60]
    ldr  r6, [r4, #0x78]
.ploop:
    movw r0, #0x3274
    movt r0, #0xC31E
    ldr  r5, [r0]
    str  r8, [r5]
    mov  r0, #0
    str  r0, [r5, #4]
    str  r6, [r5, #8]
    movw r0, #0x0813
    str  r0, [r5, #0xc]
    dsb
    mov  r0, #9
    movw r12, #0x6B81
    movt r12, #0xC01E
    blx  r12
    mov  r0, #4
    movw r1, #50000
    movw r12, #0x4E81
    movt r12, #0xC01E
    blx  r12
    add  r8, r8, r6              @ 下一幀往後移一個 framesize
    subs r7, r7, #1
    bne  .ploop
    mov  r0, #0
    pop  {r4-r9, pc}
