.syntax unified
.arm
.text
.global sl_journal_ready

/* Sensor Lab's fail-closed guard immediately before a USER-resident hook is
 * armed.  r0 = packed {site, stock_word} pairs; r1 = 1..64 pairs;
 * r2 = 1..512 journal entries allowed by this exact VBIN.  Return r0 = 1 if
 * the shared stage2 callback is in BOTH power-off lists and every pair has
 * exactly one journal record containing the factory word, while the current
 * site is still factory; otherwise return 0.  The table is also the builder's
 * single source for 4-byte stock-word VBIN sections and the arming loop.
 *
 * Call once before the first core hook, and again before the first late UI
 * hook.  This function registers nothing and writes no firmware word.
 * Stage2's pass-1 writes are protected separately by its lh_setup gate.
 * Power cuts and a callback which never executes remain outside this proof.
 */
.equ POFF_MGR,       0xC0023A98
.equ ORDINARY_OFF,   0x0C
.equ FORCED_OFF,     0x34
.equ LIST_SLOTS,     10
.equ MAX_SITES,      64      @ a range check only (2026-10-05: 33 with imx410_binfilt)
.equ MAX_RECORDS,    512
.equ MAX_ENTRY_BYTES, 0x10000
.equ MAX_JOURNAL_SPAN, 0x20000

.macro SL_LDA reg, value
    movw \reg, #:lower16:\value
    movt \reg, #:upper16:\value
.endm

sl_journal_ready:
    push    {r3-r11, lr}               @ 10 registers: aligned firmware call
    mov     r4, r0                      @ descriptor table
    mov     r5, r1                      @ descriptor count
    mov     r6, r2                      @ journal entry limit
    cmp     r4, #0
    beq     .Lfail
    tst     r4, #3
    bne     .Lfail
    cmp     r5, #1
    blo     .Lfail
    cmp     r5, #MAX_SITES
    bhi     .Lfail
    cmp     r6, #1
    blo     .Lfail
    cmp     r6, #MAX_RECORDS
    bhi     .Lfail

    SL_LDA  r3, POFF_MGR
    blx     r3
    movs    r7, r0                      @ XC_PowerOffMgr
    beq     .Lfail
    tst     r7, #3
    bne     .Lfail

    /* Find a stage2-shaped object present in both fixed ten-slot lists.
     * Compare pointers before dereferencing an object, so native objects
     * registered in only one list are never examined.  A second candidate
     * is ambiguous and is rejected. */
    mov     r8, #0                      @ candidate object
    add     r9, r7, #ORDINARY_OFF
    mov     r10, #LIST_SLOTS
.Lordinary:
    ldr     r0, [r9], #4
    cmp     r0, #0
    beq     .Lnext_ordinary
    add     r1, r7, #FORCED_OFF
    mov     r2, #LIST_SLOTS
.Lforced:
    ldr     r3, [r1], #4
    cmp     r0, r3
    beq     .Lcommon
    subs    r2, r2, #1
    bne     .Lforced
    b       .Lnext_ordinary

.Lcommon:
    tst     r0, #3
    bne     .Lfail
    SL_LDA  r3, 0x40000000
    cmp     r0, r3
    blo     .Lfail
    SL_LDA  r3, 0xF0000000
    cmp     r0, r3
    bhs     .Lfail
    ldr     r1, [r0]
    sub     r3, r0, #8
    cmp     r1, r3
    bne     .Lnext_ordinary
    ldr     r1, [r0, #4]
    add     r3, r0, #12
    cmp     r1, r3
    bne     .Lnext_ordinary
    ldr     r1, [r0, #8]               @ journal after copied callback
    tst     r1, #3
    bne     .Lnext_ordinary
    sub     r3, r1, r0
    cmp     r3, #12
    bls     .Lnext_ordinary
    cmp     r3, #0x400                 @ callback is far smaller than 1 KiB
    bhi     .Lnext_ordinary

    /* Exact first four words of stage2.S:lh_unhook.  The remaining routine
     * is owned by the coherent shared loader build; this signature prevents
     * an unrelated native object with the same three-word header from being
     * mistaken for its journal. */
    ldr     r1, [r0, #12]
    SL_LDA  r3, 0xE92D4070
    cmp     r1, r3
    bne     .Lnext_ordinary
    ldr     r1, [r0, #16]
    SL_LDA  r3, 0xE1A0600D
    cmp     r1, r3
    bne     .Lnext_ordinary
    ldr     r1, [r0, #20]
    SL_LDA  r3, 0xE3CDD007
    cmp     r1, r3
    bne     .Lnext_ordinary
    ldr     r1, [r0, #24]
    SL_LDA  r3, 0xE5904008
    cmp     r1, r3
    bne     .Lnext_ordinary
    cmp     r8, #0
    bne     .Lfail                      @ ambiguous callback owner
    mov     r8, r0
.Lnext_ordinary:
    subs    r10, r10, #1
    bne     .Lordinary
    cmp     r8, #0
    beq     .Lfail

    ldr     r9, [r8, #8]               @ current journal record
    mov     r7, r6                      @ records remaining
    mov     r10, #0                     @ seen descriptor bits
    cmp     r5, #MAX_SITES
    mvneq   r11, #0
    beq     .Ljournal
    mov     r11, #1
    lsl     r11, r11, r5
    sub     r11, r11, #1               @ exact required bits

.Ljournal:
    ldr     r0, [r9]                   @ journal entry address, 0 = end
    cmp     r0, #0
    beq     .Lcomplete
    cmp     r7, #0
    beq     .Lfail
    sub     r7, r7, #1
    tst     r0, #3
    bne     .Lfail
    SL_LDA  r3, 0x40000000
    cmp     r0, r3
    blo     .Lfail
    ldr     r1, [r9, #4]               @ padded section length
    cmp     r1, #0
    beq     .Lfail
    tst     r1, #3
    bne     .Lfail
    cmp     r1, #MAX_ENTRY_BYTES
    bhi     .Lfail
    add     r3, r0, r1
    cmp     r3, r0
    bls     .Lfail                      @ wraparound
    mov     r2, #0                      @ descriptor index
    mov     r3, r4                      @ descriptor cursor
.Lpair:
    cmp     r2, r5
    bhs     .Lnext_record
    ldr     r6, [r3]                   @ site
    cmp     r6, r0
    blo     .Lnext_pair
    sub     r6, r6, r0                  @ site offset in record
    cmp     r6, r1
    bhs     .Lnext_pair
    add     ip, r6, #4
    cmp     ip, r1
    bhi     .Lfail                      @ a word must fit entirely
    ldr     ip, [r3, #4]               @ expected factory word
    add     r6, r9, r6
    ldr     r6, [r6, #8]               @ stage2's saved word
    cmp     r6, ip
    bne     .Lfail
    ldr     r6, [r3]
    ldr     r6, [r6]                   @ current site, before arming
    cmp     r6, ip
    bne     .Lfail
    mov     r6, #1
    lsl     r6, r6, r2
    tst     r10, r6
    bne     .Lfail                      @ duplicate coverage is ambiguous
    orr     r10, r10, r6
.Lnext_pair:
    add     r3, r3, #8
    add     r2, r2, #1
    b       .Lpair

.Lnext_record:
    add     r9, r9, r1
    add     r9, r9, #8
    sub     r3, r9, r8
    cmp     r3, #MAX_JOURNAL_SPAN
    bhi     .Lfail
    b       .Ljournal

.Lcomplete:
    cmp     r10, r11
    moveq   r0, #1
    movne   r0, #0
    pop     {r3-r11, pc}
.Lfail:
    mov     r0, #0
    pop     {r3-r11, pc}
