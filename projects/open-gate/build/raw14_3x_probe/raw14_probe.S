@ RAW14 ÷3 bounded probe —— 相機端負載
@
@ 設計見 PROBE_DESIGN.md。位址由 raw14_probe.py 以 --defsym 傳入。
@ 探針不配置記憶體、不產生檔案、不呼叫任何寫入 API。
@
@ 單一掛鉤。原本設計有 HOOK_WRITER 和 HOOK_FRAME 兩個,2026-09-16 合併:
@ 錄影的每一格 CinemaDNG 都是對 F_WRITE 的一次 ≥1 MB 寫入,而它的
@ r1 就是緩衝區指標 —— 閘門和畫格偵測是同一個事件。

        .syntax unified
        .arm

.ifndef STATE
        .err            @ STATE 未定義
.endif
.ifndef F_WRITE
        .err            @ F_WRITE 未綁定 —— 見 PROBE_DESIGN.md §5
.endif
.ifndef F_WRITE_BODY
        .err            @ F_WRITE_BODY 未綁定
.endif
.ifndef TICK_US
        .err            @ TICK_US 未綁定
.endif

        .equ MAGIC,      0x52313450        @ 'R14P'
        .equ RZ_LO,      0x5A5AA5A5
        .equ RZ_HI,      0xA5A55A5A

        @ 一格 CinemaDNG 最小 1 MB。OG2K 12-bit 是 4.06 MB,RAW14 16-bit 容器
        @ 是 5.42 MB。fpSup/gyro/phase_probe.S 用同一個門檻分辨 DNG 寫入。
        .equ DNG_MIN,    0x00100000

        .equ S_IDLE,     0
        .equ S_ARMED,    1
        .equ S_SEEN,     2
        .equ S_ABORT,    3
        .equ S_CLEAN,    4

        .equ A_NONE,     0
        .equ A_HOST,     1
        .equ A_DEADLINE, 2
        .equ A_REDZONE,  3

        .equ O_MAGIC,    0x00
        .equ O_STATE,    0x04
        .equ O_FRAMES,   0x08
        .equ O_TARM,     0x0C
        .equ O_TSEEN,    0x10
        .equ O_DESC,     0x14             @ [0]=file obj [1]=buffer [2]=length
        .equ O_DIGEST,   0x34
        .equ O_ABORT,    0x38
        .equ O_GATE,     0x3C
        .equ O_RZHI,     0x40
        .equ O_DEADLINE, 0x44             @ 相機端惰性期限(µs,0 = 不設)

        .macro LDA reg, val
        movw \reg, #((\val) & 0xFFFF)
        movt \reg, #(((\val) >> 16) & 0xFFFF)
        .endm

@ ---------------------------------------------------------------- writer gate
@ 掛在 F_WRITE 的**第一道指令**,所以進來時 prologue 還沒跑、堆疊未動、
@ lr 還是呼叫端的 —— 要抑制寫入只需要 `bx lr`,不必拆別人的框架。
@
@ r0 = file object   r1 = buffer   r2 = length
@ 回傳:0 = 失敗,非 0 = 成功(兩個呼叫端都只看 0/非 0,已確認)
@
@ 閘門與畫格擷取狀態脫鉤:從 arm 關到 cleanup,SEEN 和 ABORT 下仍然關著。
@ 否則一次錄影的第 2..N 格就會落到卡上。fail-closed:主機失聯時寧可完全
@ 不產生檔案,也不要產生非預期的檔案。
        .global wr_gate
wr_gate:
        cmp     r2, #DNG_MIN
        blo     wr_pass                   @ 小寫入一律放行,連狀態都不查

        push    {r0-r4, lr}               @ 6 regs = 24 bytes,8-byte 對齊
        LDA     r4, STATE
        ldr     r3, [r4, #O_MAGIC]
        LDA     r12, MAGIC
        cmp     r3, r12
        bne     wr_unhook                 @ 狀態區不是我們的 → 原廠行為
        ldr     r3, [r4, #O_STATE]
        cmp     r3, #S_IDLE
        beq     wr_unhook
        cmp     r3, #S_CLEAN
        beq     wr_unhook

        cmp     r3, #S_ARMED
        bne     wr_gated                  @ SEEN / ABORT:只關閘,不再擷取
        bl      deadline_check
        ldr     r3, [r4, #O_STATE]
        cmp     r3, #S_ARMED
        bne     wr_gated                  @ 期限剛到:關閘,但不擷取

        ldr     r3, [r4, #O_FRAMES]
        cmp     r3, #0
        bne     wr_gated                  @ 只記錄第一格
        mov     r3, #1
        str     r3, [r4, #O_FRAMES]

        bl      tick_now
        str     r0, [r4, #O_TSEEN]

        ldr     r0, [sp]                  @ file object
        str     r0, [r4, #O_DESC]
        ldr     r1, [sp, #4]              @ buffer
        str     r1, [r4, #(O_DESC + 4)]
        ldr     r0, [sp, #8]              @ length
        str     r0, [r4, #(O_DESC + 8)]

        bl      digest_head               @ r1 = buffer -> r0 = 摘要
        str     r0, [r4, #O_DIGEST]

        mov     r3, #S_SEEN               @ 擷取到就停止擷取(閘門不動)
        str     r3, [r4, #O_STATE]

wr_gated:
        ldr     r3, [r4, #O_GATE]
        add     r3, r3, #1
        str     r3, [r4, #O_GATE]
        pop     {r0-r4, lr}
        mov     r0, #1                    @ 非 0 = 成功
        bx      lr                        @ 真正的寫入從未發生

wr_unhook:
        pop     {r0-r4, lr}
wr_pass:
        stmfd   sp!, {r4, r5, r6, r7, lr} @ F_WRITE 被位移的那道指令 E92D40F0
        LDA     r12, F_WRITE_BODY
        bx      r12

@ --------------------------------------------------------------- digest head
@ r1 = 緩衝區 -> r0 = 前 256 bytes 的摘要。只讀,不寫。
digest_head:
        push    {r1-r5, lr}
        mov     r2, #0
        mov     r3, #0
dg_loop:
        ldr     r5, [r1, r2]
        eor     r3, r3, r5
        ror     r3, r3, #7
        add     r2, r2, #4
        cmp     r2, #256
        blt     dg_loop
        mov     r0, r3
        pop     {r1-r5, pc}

@ ------------------------------------------------------------ deadline (lazy)
@ 只在掛鉤進入時檢查。相機端的備援;主看門狗在主機。
@ 它只把 ARMED 推到 ABORT —— **絕不開閘**。
deadline_check:
        push    {r1-r5, lr}
        LDA     r1, STATE
        ldr     r2, [r1, #O_DEADLINE]
        cmp     r2, #0
        beq     dl_out                    @ 0 = 不設期限
        bl      tick_now
        subs    r0, r0, r2
        blt     dl_out
        mov     r0, #S_ABORT
        str     r0, [r1, #O_STATE]
        mov     r0, #A_DEADLINE
        str     r0, [r1, #O_ABORT]
dl_out:
        pop     {r1-r5, pc}

@ TICK_US 是**函式**不是位址:0xC002B6E0 回傳微秒數。
@ fpSup/gyro/phase_probe.S 在四個地方這樣用,所以從掛鉤裡呼叫它是已驗證的。
tick_now:                                 @ -> r0 = µs
        push    {r1-r4, r12, lr}
        LDA     r12, TICK_US
        blx     r12
        pop     {r1-r4, r12, pc}

@ ------------------------------------------------------------------- redzone
@ cleanup 由主機驅動;這一段只做檢查。撤掛鉤是主機寫回原指令。
        .global rz_check
rz_check:
        LDA     r1, STATE
        ldr     r2, [r1, #-4]
        LDA     r3, RZ_LO
        cmp     r2, r3
        bne     rz_bad
        ldr     r2, [r1, #O_RZHI]
        LDA     r3, RZ_HI
        cmp     r2, r3
        bne     rz_bad
        mov     r0, #A_NONE
        bx      lr
rz_bad:
        mov     r0, #A_REDZONE
        str     r0, [r1, #O_ABORT]
        mov     r0, #S_ABORT
        str     r0, [r1, #O_STATE]
        mov     r0, #A_REDZONE
        bx      lr
