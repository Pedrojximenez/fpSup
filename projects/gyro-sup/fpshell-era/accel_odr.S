/* accel_odr.S — 直接寫 MMA8452Q CTRL_REG1(0x2A) 設定 ODR,用來測「韌體輪詢是不是真天花板」。
 *
 * 背景:切到韌體 mode 0(ODR 100Hz)後實測只有 46.5Hz,懷疑瓶頸已從感測器換成
 * 韌體讀快取的頻率(~50Hz)。若真是如此,把 ODR 再拉高不會有變化 —— 這支就是拿來證實的。
 *
 * DR bits[5:3]: 000=800 001=400 010=200 011=100 100=50 101=12.5 110=6.25 111=1.56
 * CTRL_REG1 = ASLP_RATE[7:6] | DR[5:3] | LNOISE[2] | F_READ[1] | ACTIVE[0]
 *   0x05=800Hz  0x0D=400Hz  0x15=200Hz  0x1D=100Hz(韌體 mode 0)   ← 皆含 LNOISE+ACTIVE
 * MMA8452Q 要改 DR 必須先進 standby,所以寫兩次:先 val&0xFE(standby),再 val(active)。
 *
 * 取鎖方式完全照抄 IMUDevInterface_MMA8452Q__v3:FUN_c0010298(guard, *iface) 進、
 * FUN_c00102d0(guard, 2) 出 —— 不繞過鎖,才不會跟韌體自己的取樣撞。
 *
 * 進入:worker `call`(r0=STATE)。STATE+0x70 = 要寫進 CTRL_REG1 的值。
 * 堆疊配置:sp+0..7 = 呼叫用的第 5/6 引數  sp+16..23 = lock guard  sp+24 = 值
 */
.syntax unified
.arm
.global _start
_start:
    push {r4-r9, lr}
    sub  sp, sp, #32
    mov  r4, r0
    ldr  r8, [r4, #0x70]        @ CTRL_REG1 目標值
    movw r5, #0x7914
    movt r5, #0xC377            @ iface singleton 0xC3777914
    add  r0, sp, #16            @ guard
    ldr  r1, [r5]
    movw r12, #0x0298
    movt r12, #0xC001           @ FUN_c0010298 (取鎖)
    blx  r12
    ldr  r6, [r5, #8]           @ bus 物件 = *(iface+8)
    ldr  r0, [r6, #0x18]
    ldr  r7, [r0, #0xc]         @ I2C write fn = *(*(bus+0x18)+0xc)
    and  r9, r8, #0xFE          @ 先 standby(清 ACTIVE)才能改 DR
    strb r9, [sp, #24]
    mov  r0, #1
    str  r0, [sp]
    mov  r0, #0
    str  r0, [sp, #4]
    mov  r0, r6
    mov  r1, #0x2A
    mov  r2, #1
    add  r3, sp, #24
    blx  r7
    strb r8, [sp, #24]          @ 再寫回 active
    mov  r0, #1
    str  r0, [sp]
    mov  r0, #0
    str  r0, [sp, #4]
    mov  r0, r6
    mov  r1, #0x2A
    mov  r2, #1
    add  r3, sp, #24
    blx  r7
    add  r0, sp, #16
    mov  r1, #2
    movw r12, #0x02D0
    movt r12, #0xC001           @ FUN_c00102d0 (放鎖)
    blx  r12
    add  sp, sp, #32
    pop  {r4-r9, pc}
