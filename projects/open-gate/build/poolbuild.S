.syntax unified
.arm
.text
/* ============================================================================
 * poolbuild —— 在一塊新配置的記憶體上就地蓋出一個 MPoolFixed<4380U, N>。
 *
 * 原廠的建構子 FUN_c03809A8 把塊數寫死成 0x60 = 96,而 96 個描述子正是
 * 240 fps 爆發長度的天花板(§53:req_cnt=94 = 96 − 保留 2)。這支payload
 * 做的事與原廠建構子逐字相同,只是塊數由 r1 給。
 *
 *   obj+0x0000  vptr          = 0xC0B99474
 *   obj+0x0004  sentinel.next -> node0            (FUN_c03806E8 的自環被覆蓋)
 *   obj+0x0008  sentinel.prev -> node[N-1]
 *   obj+0x112C  free count    = N                 (MPoolFixed::v3 回傳的就是它)
 *   obj+0x1130  node0,步長 0x1128 = 4380 + 12
 *       node+0x00 next   node+0x04 prev   node+0x08 guard 0xFAFAFEFE
 *       配置回傳的是 node+0x0C(MPoolFixed::v2 的 `param_2 - 0xc`)
 *
 * vptr 不在這裡寫 —— 由主機在 memset 之後寫,這樣萬一這支跑一半失敗,
 * 物件不會長得像一個「可用但串列是壞的」池子。
 *
 * 進入:r0 = 物件基底   r1 = N        離開:r0 = N
 * 不呼叫任何韌體函式,不碰中斷,可以在相機閒置時安全執行。
 * ========================================================================== */

.global entry
entry:
    push    {r4, r5, r6, r7, lr}
    mov     r4, r0                      @ obj
    mov     r5, r1                      @ N
    movw    r7, #0x1128                 @ stride
    movw    r6, #0x1130
    add     r6, r6, r4                  @ node0

    str     r6, [r4, #4]                @ sentinel.next = node0

    sub     r0, r5, #1
    mul     r2, r0, r7
    add     r2, r2, r6
    str     r2, [r4, #8]                @ sentinel.prev = node[N-1]

    add     r1, r4, #4                  @ sentinel 位址
    movw    r3, #0x112C
    str     r5, [r4, r3]                @ free count = N

    mov     r0, r6                      @ cur  = node0
    mov     r2, r1                      @ prev = sentinel
    mov     r3, #1                      @ i    = 1
    movw    ip, #0xFEFE
    movt    ip, #0xFAFA                 @ guard 0xFAFAFEFE
1:
    str     r2, [r0, #4]                @ cur->prev
    str     ip, [r0, #8]                @ cur->guard
    cmp     r3, r5
    beq     2f
    mov     r2, r0                      @ prev = cur
    add     r0, r0, r7                  @ cur  = cur + stride
    str     r0, [r2]                    @ prev->next = cur
    add     r3, r3, #1
    b       1b
2:
    str     r1, [r0]                    @ last->next = sentinel
    mov     r0, r5
    pop     {r4, r5, r6, r7, pc}
