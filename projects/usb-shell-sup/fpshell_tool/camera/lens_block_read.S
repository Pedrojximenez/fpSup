.syntax unified
.arm
.global _start
/* lens_block_read v2: r0=STATE, STATE+0x70=block id
 * 結果 @0xC072F700: +0 id  +4 ok  +8 len  +0xC nzcount  +0x10 起=資料
 * nzcount = 回傳資料中「非 0x00 且非 0xFF」的位元組數 → 一眼判斷有沒有真內容 */
_start:
    push {r4-r10, lr}
    mov  r4, r0
    ldr  r5, [r4, #0x70]
    movw r6, #0xF700
    movt r6, #0xC072
    movw r0, #0x4368
    movt r0, #0xC0B9
    mov  r1, #0xC
    mul  r1, r5, r1
    add  r0, r0, r1
    ldr  r7, [r0]                @ len
    str  r5, [r6, #0x00]
    mov  r0, #0
    str  r0, [r6, #0x04]
    str  r7, [r6, #0x08]
    str  r0, [r6, #0x0C]
    movw r0, #0x54A0
    movt r0, #0xC035
    blx  r0
    mov  r1, r5
    add  r2, r6, #0x10
    movw r3, #0x5DE0
    movt r3, #0xC035
    blx  r3
    str  r0, [r6, #0x04]         @ ok
    /* 統計非 0/非 FF 位元組 */
    add  r8, r6, #0x10
    mov  r9, #0
    mov  r10, #0
.cnt:
    cmp  r10, r7
    bge  .done
    ldrb r0, [r8, r10]
    cmp  r0, #0
    beq  .nx
    cmp  r0, #0xFF
    beq  .nx
    add  r9, r9, #1
.nx:
    add  r10, r10, #1
    b    .cnt
.done:
    str  r9, [r6, #0x0C]
    pop  {r4-r10, pc}
