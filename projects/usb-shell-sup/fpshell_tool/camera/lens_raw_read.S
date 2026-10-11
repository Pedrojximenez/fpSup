.syntax unified
.arm
.global _start
/* lens_raw_read: r0=STATE
 *   STATE+0x70 = lens address
 *   STATE+0x74 = length (<=0xA000)
 * 直接呼叫 CmdRead(ctx, addr, len, dst, 0) @0xC0355BE0 — 自帶 PreCommunicationSequence 鎖
 * 結果 @0xC072F700: +0 addr  +4 ok  +8 len  +0xC nzcount  +0x10 起=資料 */
_start:
    push {r4-r10, lr}
    mov  r4, r0
    ldr  r5, [r4, #0x70]         @ addr
    ldr  r7, [r4, #0x74]         @ len
    movw r6, #0xF700
    movt r6, #0xC072
    str  r5, [r6, #0x00]
    mov  r0, #0
    str  r0, [r6, #0x04]
    str  r7, [r6, #0x08]
    str  r0, [r6, #0x0C]
    movw r0, #0x54A0
    movt r0, #0xC035
    blx  r0                      @ r0 = ctx
    mov  r1, r5                  @ addr
    mov  r2, r7                  @ len
    add  r3, r6, #0x10           @ dst
    mov  r8, #0
    mov  r9, #0
    push {r8, r9}                @ param_5 = 0 @[sp]; 推兩字維持 8-byte 對齊
    movw r10, #0x5BE0
    movt r10, #0xC035
    blx  r10
    add  sp, sp, #8
    str  r0, [r6, #0x04]
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
