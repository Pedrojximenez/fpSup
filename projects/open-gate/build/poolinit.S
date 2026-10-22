.syntax unified
.arm
.text
#include "og_pic.inc"
/* ============================================================================
 * poolinit —— 把 CinemaDNG 的描述子池從原廠的 96 格換成 TARGET_POOLDEPTH 格。
 *
 * 2026-09-21:240 fps 停在 150-200 格,不是吞吐不足(236 MB/s 需求 vs 實測
 * >=317),是**寫入端的延遲尖峰**。A001_171 有一筆寫了 126 ms、前面空了 183 ms,
 * 那段時間累積 48 格請求,池子從 82 掉到 15。一次停頓吃掉約 67 個描述子,
 * 而 MPoolFixed<4380U,96U> 只有 96 —— 撐得過一次,撐不過第二次。
 *
 * 從 RAW(NonCacheBuffer id 10,MOVIE_REC_DNG 模式下 708 MB)配一塊,照原廠
 * 建構子 FUN_c03809A8 的版面蓋出自由串列,再換掉 0xC2F1F3D8 的指標。
 * v2/v4 的兩對界線常數由 plan 靜態寫好(它們是相對物件基底的位移)。
 *
 *     obj+0x0000 vptr   +0x0004/0x0008 哨兵   +0x112C 剩餘數
 *     obj+0x1130 起,每塊 0x1128;node+0 next、+4 prev、+8 guard 0xFAFAFEFE
 *     配置回傳的是 node+0x0C
 *
 * ★ 由 og3kcanvas 的錄影分支呼叫(旗標守衛在那邊),也就是韌體自己的任務脈絡。
 *   2026-09-21 用 callfn 從 shell 呼叫配置器當場死鎖,那是脈絡問題不是函式問題。
 * ========================================================================== */

.equ POOLFLAG, OGA(0xC0731C18)      @ 一次性旗標(本檔自己設,呼叫端只負責檢查)
.equ POOLPTR,  0xC2F1F3D8
.equ POOLVPTR, 0xC0B99474
.equ POOLSTR,  0x1128
.equ POOLHDR,  0x1130
.equ POOLCNT,  0x112C
.equ POOLSLOT, OGA(0xC0731C1C)
.equ HEAPNEW,  0xC001CF78
.equ HEAPGET,  0xC001CFD8
.equ MEMSET,   0xC0015058
.equ POOLN,    TARGET_POOLDEPTH
.equ POOLSZ,   (0x1130 + TARGET_POOLDEPTH * 0x1128)

.macro LDA reg, value
#ifdef OG_V3
    OGLDA   \reg, \value
#else
    movw    \reg, #:lower16:\value
    movt    \reg, #:upper16:\value
#endif
.endm

.global entry
entry:
    LDA     r0, POOLFLAG
    mov     r3, #1
    str     r3, [r0]                    @ 先設:配置失敗也不重試

    push    {r4, r5, r6, r7, lr}
    mov     r0, #10                     @ RAW
    LDA     ip, HEAPNEW
    blx     ip
    LDA     r1, POOLSLOT
    LDA     r2, POOLSZ
    mov     r3, #0x400                  @ 對齊
    push    {r0}                        @ 第五個參數走堆疊
    mov     ip, #0
    push    {ip}
    LDA     ip, HEAPGET
    blx     ip
    add     sp, sp, #8
    LDA     r6, POOLSLOT
    ldr     r6, [r6]
    cmp     r6, #0
    beq     pool_abort

    mov     r0, r6
    mov     r1, #0
    LDA     r2, POOLSZ
    LDA     ip, MEMSET
    blx     ip

    movw    r7, #POOLSTR
    movw    r2, #POOLHDR
    add     r2, r2, r6                  @ node0
    str     r2, [r6, #4]                @ sentinel.next = node0
    movw    r0, #(POOLN - 1)
    mul     r3, r0, r7
    add     r3, r3, r2
    str     r3, [r6, #8]                @ sentinel.prev = node[N-1]
    movw    r3, #POOLCNT
    movw    r0, #POOLN
    str     r0, [r6, r3]                @ 剩餘數 = N
    add     r1, r6, #4                  @ sentinel 位址
    mov     r3, r1                      @ prev = sentinel
    mov     ip, #1
    movw    r0, #0xFEFE
    movt    r0, #0xFAFA
pool_loop:
    str     r3, [r2, #4]                @ cur->prev
    str     r0, [r2, #8]                @ guard
    cmp     ip, #POOLN
    beq     pool_tail
    mov     r3, r2
    add     r2, r2, r7
    str     r2, [r3]                    @ prev->next = cur
    add     ip, ip, #1
    b       pool_loop
pool_tail:
    str     r1, [r2]                    @ last->next = sentinel
    LDA     r3, POOLVPTR
    str     r3, [r6]
    LDA     r0, POOLPTR
    str     r6, [r0]
pool_abort:
    pop     {r4, r5, r6, r7, lr}
    bx      lr
