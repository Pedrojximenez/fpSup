/* accel_fast.S — 把 MMA8452Q 從低功耗 6.25Hz 切到 100Hz 高解析模式。
 *
 * 背景:實測加速計只有 6.3Hz 更新(陀螺儀是 2014Hz),對 gyroflow 的地平線校正太鈍。
 * 韌體的 IMUDevInterface_MMA8452Q__v3(iface, mode) @0xC050CCA0 是模式設定器:
 *   mode 0 → CTRL_REG1 0x1C/0x1D = DR 100Hz + LNOISE,CTRL_REG2 0x02(無 auto-sleep)
 *   mode 1/2 → CTRL_REG1 0xF4/0xF5 = DR 6.25Hz + auto-sleep  ← 現在是這個
 * 借用它而不是自己戳 I2C:它內部會取同一把 I2C 鎖,不會跟韌體自己的取樣撞。
 *
 * 進入:worker `call`(r0=STATE)。STATE+0x70 = mode(0=100Hz, 1/2=低功耗)。
 * 介面物件是 singleton 0xC3777914(由 FUN_c050d028 建構)。
 */
.syntax unified
.arm
.global _start
_start:
    push {r4, lr}
    mov  r4, r0
    movw r0, #0x7914
    movt r0, #0xC377          @ iface singleton
    ldr  r1, [r4, #0x70]      @ mode
    movw r2, #0xCCA0
    movt r2, #0xC050          @ IMUDevInterface_MMA8452Q__v3
    blx  r2
    pop  {r4, pc}
