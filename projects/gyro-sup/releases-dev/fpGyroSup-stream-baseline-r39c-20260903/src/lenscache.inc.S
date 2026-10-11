/* Idle lens cache + early JSON helpers for profilegen.S (r39b).
 *
 * Included into every PGEN build: pg_build consults the cache in all of them,
 * while only the native-lifecycle boundary watch drives the poll and the
 * early write.  Everything here runs in the writer task. */

/* r39b: the writer's 5 ms poll also keeps the lens cache warm while idle and
 * writes a take's JSON as soon as the take is established.  Both preserve
 * r4-r8; pg_build saves what it uses. */
pg_lens_fp_take:                        /* r0 = dst; copy LENS_REGION, r0 = any nonzero */
    push    {r4, r5, lr}
    ldr_addr r1, LENS_REGION
    mov     r2, #LC_FP_LEN
    mov     r3, #0
1:  ldrb    r4, [r1], #1
    strb    r4, [r0], #1
    orr     r3, r3, r4
    subs    r2, r2, #1
    bne     1b
    cmp     r3, #0
    movne   r0, #1
    moveq   r0, #0
    pop     {r4, r5, pc}

pg_lens_fp_equal:                       /* r0 = cached copy -> r0 = 1 if LENS_REGION still equals it */
    push    {r4, r5, lr}
    ldr_addr r1, LENS_REGION
    mov     r2, #LC_FP_LEN
2:  ldrb    r3, [r0], #1
    ldrb    r4, [r1], #1
    cmp     r3, r4
    bne     3f
    subs    r2, r2, #1
    bne     2b
    mov     r0, #1
    pop     {r4, r5, pc}
3:  mov     r0, #0
    pop     {r4, r5, pc}

pg_post_owner:                          /* r0 = 1 if this task may build/write a JSON now */
    ldr     r0, [r10, #S_POST_BUSY]
    cmp     r0, #1
    moveq   r0, #1
    bxeq    lr
    movw    r0, #:lower16:PG_LCACHE
    movt    r0, #:upper16:PG_LCACHE
    add     r0, r10, r0
    ldr     r0, [r0, #LC_EARLY]
    cmp     r0, #1
    moveq   r0, #1
    movne   r0, #0
    bx      lr

pg_lens_cache_poll:
    push    {r4, r5, r6, r7, r8, lr}
    movw    r4, #:lower16:PG_LCACHE
    movt    r4, #:upper16:PG_LCACHE
    add     r4, r10, r4                 @ cache block
    sub     r6, r4, #0x1000             @ PG_LENS: focal at +0, name at +0x80
    ldr     r0, [r4, #LC_MAGIC]
    ldr_addr r1, LC_MAGIC_V
    cmp     r0, r1
    beq     1f
    mov     r0, #0                      @ first sight of this pool: clear the cache block
    str     r0, [r4, #LC_OK]
    str     r0, [r4, #LC_BACKOFF]
    str     r0, [r4, #LC_JSON_GEN]
    str     r0, [r4, #LC_EARLY]
    str     r0, [r4, #LC_JSON_RES]
    str     r0, [r4, #LC_JSON_SEQ]
    str     r0, [r4, #LC_JSON_SKIP]
    str     r1, [r4, #LC_MAGIC]
1:  ldr     r0, [r10, #S_ACTIVE]
    cmp     r0, #1
    beq     9f                          @ recording: the bus belongs to the camera
    ldr     r0, [r10, #S_FILE]
    cmp     r0, #0
    bne     9f
    ldr     r0, [r10, #S_POST_BUSY]
    cmp     r0, #0
    bne     9f
    ldr     r0, [r10, #O_LC_STATE]
    cmp     r0, #1
    cmpne   r0, #4
    cmpne   r0, #6
    beq     9f                          @ a take is being published
    ldr_addr r0, XMP_FOBJ_PTR
    ldr     r0, [r0]
    cmp     r0, #0
    bne     9f
    ldr_addr r0, MOV_ACTIVE_PTR
    ldrb    r0, [r0]
    cmp     r0, #0
    bne     9f
    ldr     r0, [r4, #LC_OK]
    cmp     r0, #0
    beq     2f
    add     r0, r4, #LC_FP
    bl      pg_lens_fp_equal
    cmp     r0, #0
    bne     9f                          @ cached, and still the mounted lens
2:  ldr     r0, [r4, #LC_BACKOFF]
    cmp     r0, #0
    subne   r0, r0, #1
    strne   r0, [r4, #LC_BACKOFF]
    bne     9f
    mov     r0, #LC_RETRY_POLLS
    str     r0, [r4, #LC_BACKOFF]
    mov     r0, #0
    str     r0, [r4, #LC_OK]
    add     r0, r4, #LC_FP
    bl      pg_lens_fp_take
    cmp     r0, #0
    beq     9f                          @ no lens correction region: nothing mounted
    ldr_addr ip, F_LENS_CTX
    blx     ip
    mov     r5, r0
    mov     r1, #B_FOCAL
    mov     r2, r6
    ldr_addr ip, F_LENS_READ
    blx     ip
    cmp     r0, #0
    beq     9f
    ldrb    r0, [r6]
    ldrb    r1, [r6, #1]
    orr     r0, r1, r0, lsl #8
    cmp     r0, #10
    blo     9f
    mov     r0, r5
    mov     r1, #B_NAME
    add     r2, r6, #0x80
    ldr_addr ip, F_LENS_READ
    blx     ip
    cmp     r0, #0
    beq     9f
    add     r0, r4, #LC_FP
    bl      pg_lens_fp_equal
    cmp     r0, #0
    beq     9f                          @ the lens changed under the reads
    mov     r0, #1
    str     r0, [r4, #LC_OK]
9:  pop     {r4, r5, r6, r7, r8, pc}

/* r0 = queue job -> r0 = 1 when that job's clip is the take whose JSON the
 * early write already produced (J_PATH equals O_PATH and the write succeeded). */
pg_json_early_done:
    push    {r4, r5, lr}
    movw    r4, #:lower16:PG_LCACHE
    movt    r4, #:upper16:PG_LCACHE
    add     r4, r10, r4
    ldr     r1, [r4, #LC_JSON_RES]
    cmp     r1, #0
    beq     8f
    add     r1, r0, #J_PATH
    add     r2, r10, #O_PATH
    mov     r3, #20
7:  ldrb    r5, [r1], #1
    ldrb    ip, [r2], #1
    cmp     r5, ip
    bne     8f
    subs    r3, r3, #1
    bne     7b
    ldr     r0, [r4, #LC_JSON_SKIP]
    add     r0, r0, #1
    str     r0, [r4, #LC_JSON_SKIP]
    mov     r0, #1
    pop     {r4, r5, pc}
8:  mov     r0, #0
    pop     {r4, r5, pc}

pg_json_early:
    push    {r4, r5, r6, r7, r8, lr}
    movw    r4, #:lower16:PG_LCACHE
    movt    r4, #:upper16:PG_LCACHE
    add     r4, r10, r4
    ldr     r0, [r10, #S_ACTIVE]
    cmp     r0, #1
    bne     9f
    ldr     r0, [r10, #O_LC_STATE]
    cmp     r0, #4                      @ first DNG confirmed: the folder exists
    bne     9f
    ldr     r0, [r10, #S_FILE]
    cmp     r0, #2                      @ the gcsv is open
    bne     9f
    ldr     r0, [r10, #S_MODE_RUN]
    cmp     r0, #0                      @ the mode sampled at the first block
    beq     9f
    ldr     r0, [r10, #S_POST_BUSY]
    cmp     r0, #0
    bne     9f
    ldr     r0, [r4, #LC_JSON_GEN]
    ldr     r1, [r10, #O_LC_ATTACH]
    cmp     r0, r1
    beq     9f                          @ this take's JSON is already written
    ldr     r0, [r4, #LC_OK]
    cmp     r0, #0
    beq     9f
    add     r0, r4, #LC_FP
    bl      pg_lens_fp_equal
    cmp     r0, #0
    beq     9f                          @ cache is for another lens: the stop path will do it
    ldr     r0, [r10, #O_LC_ATTACH]
    str     r0, [r4, #LC_JSON_GEN]
    ldr     r0, [r10, #S_MODE_RUN]
    str     r0, [r10, #O_POST_MODE]
    mov     r0, #0
    str     r0, [r10, #O_POST_W]        @ pg_setting_dims fills these
    str     r0, [r10, #O_POST_H]
    ldr     r0, [r10, #O_LC_VOLUME]
    str     r0, [r10, #O_POST_VOLUME]
    mov     r0, #1
    str     r0, [r4, #LC_EARLY]
    bl      pg_build
    str     r0, [r4, #LC_JSON_RES]
    mov     r0, #0
    str     r0, [r4, #LC_EARLY]
    ldr     r0, [r10, #S_NEXTSEQ]
    str     r0, [r4, #LC_JSON_SEQ]
9:  pop     {r4, r5, r6, r7, r8, pc}

