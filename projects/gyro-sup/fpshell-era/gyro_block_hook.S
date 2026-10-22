.syntax unified
.arm
.text
/* 陀螺分塊記錄:hook 填滿固定大小的記憶區塊,滿了才寫 SD。
 *
 * 這是使用者指定的架構。陀螺與加速計各自有獨立的區塊與獨立的檔案。
 *
 * ★ 這個版本存在的目的是「量出一個數字」:寫 SD 會不會阻塞陀螺執行緒太久。
 *   陀螺 ring 只有 600 樣本 = 240 ms 的餘裕,超過就被硬體蓋掉、樣本靜默遺失。
 *   平時 20 KB 寫入是幾毫秒,但錄影時卡片被 CinemaDNG 灌滿,我們的寫入排在
 *   DNG 幀後面要等多久沒人量過。所以每次寫入都記錄耗時與最大值:
 *     max < 240 ms → 這個設計成立,不需要背景任務
 *     接近或超過   → 才需要雙緩衝 + writer task
 *   不為了還沒證實的風險先加複雜度。
 *
 * ★ hook 點是空的。shell 的 AutoRun 確實會寫 0xC00D0794,但那只是開機跳板 ——
 *   它在那裡建立 worker 任務後就把原指令還原了(現場讀到 0xFA046FD7 = 原本的
 *   BLX 0xC01EC6F9)。所以串接對象就是原始指令的目標,shell 版與 AutoRun 版相同。
 *   (先前我看 AutoRun 的靜態內容,以為 shell worker 掛在那裡 —— 讀現場才發現不是。)
 *
 * 狀態與緩衝全部放 bufmem 池(0x44F6ADC0,配置大小不影響回傳位址)。
 * 0xC072Fxxx 那個視窗真正空著的只有 512 bytes,我已經在那裡撞車三次。
 */

.equ CHAIN,      0xC01EC6F9      /* 原始指令的目標(Thumb);shell 與 AutoRun 相同 */
.equ RING_PTR,   0xC31E3FCC
.equ RING_SIZE,  0x12C4
.equ FN_TICK,    0xC002B6E0      /* TickTimer,微秒 */
.equ ACCEL_CACHE,0xC377790C      /* i16 X, Y, Z,韌體已做軸重映 */

/* bufmem 池主機寫不進去(實測),所以唯一需要主機控制的旗標放在可寫視窗,
 * 其餘計數器與緩衝都在池裡、由相機端自己初始化。pushread 讀池沒有限制。 */
.equ ACTIVE,     0xC072F480      /* 主機寫 1 開始 / 0 停止 */
/* ★ 必須避開 0x44F6ADC0..0x44F6BDC0 —— 那 4 KB 是 USB shell worker 自己的指令
 * 緩衝(讀出來是 ASCII "FPSH"),每送一個指令就被覆寫一次。我一度把 STATE 放在
 * 那裡,計數器永遠是 0,還以為是程式沒執行。實測 0x44F6BDC0 之後跑過多個指令
 * 都存活。 */
.equ POOL,       0x44F6BE00
.equ OPENED,     0x44F6ADC4
.equ GBYTES,     0x44F6ADC8      /* 目前區塊內的位元組 */
.equ ABYTES,     0x44F6ADCC
.equ BLOCKS,     0x44F6ADD0      /* 已寫出的陀螺區塊數 */
.equ MAXUS,      0x44F6ADD4      /* ★ 寫入耗時最大值(微秒) */
.equ LASTUS,     0x44F6ADD8
.equ OVERFLOW,   0x44F6ADDC      /* 區塊來不及寫、被迫丟棄的次數 */
.equ HEAD,       0x44F6ADE0
.equ GOPEN,      0x44F6ADE4
.equ AOPEN,      0x44F6ADE8
.equ GTOTAL,     0x44F6ADEC
.equ ATOTAL,     0x44F6ADF0
.equ CALLS,      0x44F6ADF4      /* hook 進入次數,判斷還活著 */

/* 全部塞進 shell AutoRun 已經配好的那 4 KB(0x44F6ADC0 起) —— 不去執行期重新
 * 配置。位址早就從 AutoRun 知道了,再推導一次只是多引入一個沒驗過的機制。
 * 區塊小一點反而更好:寫得更頻繁 = 更嚴苛的測試,而要量的數字(單次寫入耗時)一樣。 */
.equ PATH_G,     0x44F6BE40      /* 32 */
.equ PATH_A,     0x44F6BE60      /* 32 */
.equ FOBJ_G,     0x44F6BE80      /* 256 */
.equ FOBJ_A,     0x44F6BF80      /* 256 */
.equ GBLOCK,     0x44F6C080
.equ GCAP,       5120            /* 640 樣本 = 0.256 s。必須 >= ring 大小(0x12C4=4804),
                                  * 否則繞回時一整圈的 span 本來就塞不進區塊。 */
.equ ABLOCK,     0x44F6D500
.equ ACAP,       256

.macro la reg, value
    movw    \reg, #:lower16:\value
    movt    \reg, #:upper16:\value
.endm

.global hook_entry
hook_entry:
    /* 十個暫存器 —— 讓對外呼叫時堆疊維持 8-byte 對齊。stage5 在同一個位置留了
     * 這句註解,我第一版推了九個(36 bytes,破壞對齊)就凍結了。AAPCS 要求公開
     * 介面 8-byte 對齊,用到 LDRD/STRD 或 VFP 的韌體函式會直接炸。 */
    push    {r3-r11, lr}
    la      ip, CHAIN
    blx     ip
    mov     r11, r0                  @ 保住被串接者的回傳值

    la      r10, POOL
    /* 自我初始化。池裡是上一輪留下的資料,OPENED 幾乎不可能剛好是 0 —— 沒有這段
     * 檢查,第一次 hook 就會拿垃圾當檔案物件去 close,當場掛掉。不能指望主機先清:
     * worker 的 mem set 寫不到池裡。 */
    ldr     r0, [r10, #0x38]
    movw    r1, #0x4831
    movt    r1, #0x4247              @ 'GBH1'
    cmp     r0, r1
    beq     1f
    mov     r2, #0
2:  str     r1, [r10, #0x38]
    mov     r0, #0
3:  str     r0, [r10, r2]
    add     r2, r2, #4
    cmp     r2, #0x38
    blo     3b
    str     r1, [r10, #0x38]
1:
    ldr     r0, [r10, #0x34]         @ CALLS
    add     r0, r0, #1
    str     r0, [r10, #0x34]

    la      r0, ACTIVE
    ldr     r0, [r0]
    cmp     r0, #0
    beq     maybe_close

    ldr     r0, [r10, #4]            @ OPENED
    cmp     r0, #0
    bne     drain
    bl      open_files
    b       out

/* ---------- 開檔 + 對齊 ring 起點 ---------- */
open_files:
    push    {r4-r6, lr}
    /* 路徑內嵌在程式碼裡,開檔時複製進池 —— 主機寫不進池,所以不能從外面塞 */
    adr     r0, s_path_g
    la      r1, PATH_G
    bl      copy_str
    adr     r0, s_path_a
    la      r1, PATH_A
    bl      copy_str
    /* 計數器歸零(除了 ACTIVE,它不在池裡) */
    la      r4, POOL
    mov     r5, #0
    mov     r6, #4
1:  str     r5, [r4, r6]
    add     r6, r6, #4
    cmp     r6, #0x38
    blo     1b
    la      r0, PATH_G
    la      r1, FOBJ_G
    bl      open_one
    la      r10, POOL
    str     r0, [r10, #0x24]         @ GOPEN
    la      r0, PATH_A
    la      r1, FOBJ_A
    bl      open_one
    la      r10, POOL
    str     r0, [r10, #0x28]         @ AOPEN
    la      r0, RING_PTR
    ldr     r0, [r0]
    ldr     r0, [r0, #0x60]
    ldr     r1, [r0]
    str     r1, [r10, #0x20]         @ HEAD:不收錄影前的歷史
    mov     r0, #0
    str     r0, [r10, #8]
    str     r0, [r10, #0xC]
    mov     r0, #1
    str     r0, [r10, #4]            @ OPENED
    pop     {r4-r6, pc}

/* r0 = 來源(NUL 結尾), r1 = 目的 */
copy_str:
    ldrb    r2, [r0], #1
    strb    r2, [r1], #1
    cmp     r2, #0
    bne     copy_str
    bx      lr

.align 2
s_path_g: .asciz "\\GBLK.BIN"
.align 2
s_path_a: .asciz "\\ABLK.BIN"
.align 2

/* ---------- 每次 hook:把 ring 新增的部分搬進區塊 ---------- */
drain:
    la      r0, RING_PTR
    ldr     r0, [r0]
    ldr     r9, [r0, #0x60]          @ ring struct
    ldr     r8, [r9]                 @ 目前 head
    ldr     r7, [r10, #0x20]         @ 上次 head
    cmp     r8, r7
    beq     do_accel

    /* head 是**絕對指標**,不是 ring 內的偏移量(實測 0x2E0075E4,ring 在
     * 0x2E00644C)。stage5 一直是這樣用的 —— 我沒細讀就自己重寫,把它當偏移量,
     * 算出來的長度過大被上限擋掉,OVERFLOW 就是這樣來的。 */
    cmp     r8, r7
    bhi     one_span
    /* 繞回:先 [r7, ring_end) 再 [ring+4, r8) */
    mov     r0, r7
    movw    r1, #RING_SIZE
    add     r1, r9, r1
    sub     r1, r1, r7
    bl      block_append
    add     r0, r9, #4
    sub     r1, r8, r0
    bl      block_append
    b       span_done
one_span:
    mov     r0, r7
    sub     r1, r8, r7
    bl      block_append
span_done:
    str     r8, [r10, #0x20]

do_accel:
    /* 一次 hook 一組加速度三元組,約 50 Hz —— 感測器本身就只有 ~47 Hz */
    ldr     r0, [r10, #0xC]          @ ABYTES
    movw    r1, #ACAP
    cmp     r0, r1
    bhs     acc_full
    la      r1, ABLOCK
    add     r1, r1, r0
    la      r2, ACCEL_CACHE
    ldrsh   r3, [r2]
    strh    r3, [r1]
    ldrsh   r3, [r2, #2]
    strh    r3, [r1, #2]
    ldrsh   r3, [r2, #4]
    strh    r3, [r1, #4]
    mov     r3, #0
    strh    r3, [r1, #6]
    add     r0, r0, #8
    str     r0, [r10, #0xC]
acc_full:

    /* 區塊滿了才寫 —— 這裡就是被量測的那一下 */
    ldr     r0, [r10, #8]
    movw    r1, #GCAP
    cmp     r0, r1
    blo     check_accel
    la      r0, GBLOCK
    la      r1, FOBJ_G
    ldr     r2, [r10, #8]
    bl      timed_write
    mov     r0, #0
    la      r10, POOL
    str     r0, [r10, #8]
    ldr     r0, [r10, #0x10]
    add     r0, r0, #1
    str     r0, [r10, #0x10]         @ BLOCKS

check_accel:
    ldr     r0, [r10, #0xC]
    movw    r1, #ACAP
    cmp     r0, r1
    blo     out
    la      r0, ABLOCK
    la      r1, FOBJ_A
    ldr     r2, [r10, #0xC]
    bl      timed_write
    mov     r0, #0
    la      r10, POOL
    str     r0, [r10, #0xC]
out:
    mov     r0, r11
    pop     {r3-r11, pc}

maybe_close:
    ldr     r0, [r10, #4]
    cmp     r0, #0
    beq     out
    /* 停止:把剩下的寫完再關 */
    ldr     r2, [r10, #8]
    cmp     r2, #0
    beq     1f
    la      r0, GBLOCK
    la      r1, FOBJ_G
    bl      timed_write
1:  la      r10, POOL
    ldr     r2, [r10, #0xC]
    cmp     r2, #0
    beq     2f
    la      r0, ABLOCK
    la      r1, FOBJ_A
    bl      timed_write
2:  la      r0, FOBJ_G
    bl      close_one
    la      r0, FOBJ_A
    bl      close_one
    la      r10, POOL
    mov     r0, #0
    str     r0, [r10, #4]
    str     r0, [r10, #8]
    str     r0, [r10, #0xC]
    b       out

/* r0 = 來源, r1 = 位元組數。追加進陀螺區塊;塞不下就記一次 overflow 並丟棄。 */
/* 放不下就先把現有區塊寫出去,再放 —— 原本是「放不下就丟棄」,結果區塊會卡在
 * 剛好不夠的位置(實測 2252/2560),寫出條件永遠達不到,OVERFLOW 一路漲。
 * OVERFLOW 現在只在「單一 span 比整個區塊還大」時才會發生,那是真的異常。 */
block_append:
    push    {r4-r7, lr}
    cmp     r1, #0
    beq     9f
    mov     r7, r1
    la      r4, POOL
    ldr     r5, [r4, #8]             @ GBYTES
    add     r6, r5, r7
    movw    r2, #GCAP
    cmp     r6, r2
    bls     1f
    cmp     r5, #0
    beq     0f
    push    {r0, r1}
    la      r0, GBLOCK
    la      r1, FOBJ_G
    mov     r2, r5
    bl      timed_write
    la      r4, POOL
    mov     r2, #0
    str     r2, [r4, #8]
    ldr     r2, [r4, #0x10]
    add     r2, r2, #1
    str     r2, [r4, #0x10]          @ BLOCKS
    pop     {r0, r1}
0:  la      r4, POOL
    mov     r5, #0
    mov     r6, r7
    movw    r2, #GCAP
    cmp     r6, r2
    bhi     8f
1:  la      r2, GBLOCK
    add     r2, r2, r5
    mov     r1, r7
2:  ldrb    r3, [r0], #1
    strb    r3, [r2], #1
    subs    r1, r1, #1
    bne     2b
    str     r6, [r4, #8]
    b       9f
8:  ldr     r2, [r4, #0x1C]
    add     r2, r2, #1
    str     r2, [r4, #0x1C]          @ OVERFLOW:單一 span 大於整個區塊
9:  pop     {r4-r7, pc}

/* r0 = 資料, r1 = 檔案物件, r2 = 長度。寫入 + flush,兩者一起計時。
 *
 * ★ 必須含 flush。0xC03660E8 只是進緩衝,真正的 SD I/O 在 0xC0366020。
 *   實測:串流任務回報寫了 2016 bytes,但因為卡住時沒走到 close,檔案根本
 *   不在卡上。只計時 write 會量到接近零,然後得出「沒有延遲問題」的錯誤結論。
 *   flush 同時也讓凍結後卡上真的有東西可以解剖。 */
timed_write:
    push    {r4-r8, lr}
    mov     r4, r0
    mov     r5, r1
    mov     r6, r2
    la      ip, FN_TICK
    blx     ip
    mov     r7, r0
    mov     r0, r5
    mov     r1, r4
    mov     r2, r6
    la      ip, 0xC03660E8
    blx     ip
    mov     r8, r0
    /* ★ 這裡原本呼叫 0xC0366020,我以為它是 flush。它不是 —— 反組譯後看到它在
     * vtable 呼叫之後 `str #0, [r4]`,把物件的 handle 清成 0,那是 **close**。
     * 每個區塊呼叫一次等於第一個區塊寫完就關檔,第二次寫入打到空 handle 直接卡死。
     * 兩次相機當機都是 BLOCKS=1 之後,完全吻合。
     * 所以只計時 write;close 留在 ACTIVE=0 的收尾路徑。 */
    la      ip, FN_TICK
    blx     ip
    sub     r0, r0, r7               @ 耗時,微秒
    la      r4, POOL
    str     r0, [r4, #0x18]          @ LASTUS
    ldr     r1, [r4, #0x14]
    cmp     r0, r1
    strhi   r0, [r4, #0x14]          @ MAXUS
    ldr     r1, [r4, #0x2C]
    add     r1, r1, r6
    str     r1, [r4, #0x2C]          @ GTOTAL(兩個檔共用計數,先夠用)
    pop     {r4-r8, pc}

/* r0 = 路徑, r1 = 檔案物件 -> r0 = open 的回傳(非 0 才是成功) */
open_one:
    push    {r4-r6, lr}
    mov     r4, r0
    mov     r5, r1
    la      ip, 0xC0444658
    blx     ip
    mov     r1, #0
    la      ip, 0xC0444698
    blx     ip
    mov     r1, r0
    mov     r0, r5
    la      ip, 0xC0365E90
    blx     ip
    mov     r0, r5
    mov     r1, r4
    mov     r2, #7                   @ 7 可覆寫;0x402 檔案已存在就失敗
    la      ip, 0xC0365FB0
    blx     ip
    pop     {r4-r6, pc}

close_one:
    push    {r4, lr}
    mov     r4, r0
    la      ip, 0xC0366020
    blx     ip
    mov     r0, r4
    mov     r1, #2
    la      ip, 0xC0365ED0
    blx     ip
    pop     {r4, pc}
