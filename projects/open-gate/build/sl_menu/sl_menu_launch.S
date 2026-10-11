.syntax unified
.arm
.text
@ entry is at offset 0; not global, so every adr to it resolves here
/* ============================================================================
 * Sensor Lab: launcher for the private B2_5 page installer (sl_menu.c).
 * ============================================================================
 *
 * Built by sl_menu/build_sl_menu.py, which appends the compiled C (sl_menu.c
 * with fpSup/uishare/ui_pool.c, one translation unit, no relocations) at
 * `c_base`. Runs where the file landed (a destination-zero --late-boot-bin
 * section), the shape of fpSup/lossless/native/card.S without any hook:
 * ask the allocator for a USER block that is never freed (the UI borrows the
 * page, its strings and the variables' names for the whole boot), copy the
 * whole blob there, zero the rest, publish D/I, call the installer in the
 * resident copy, and return so the boot carries on. Any refusal: return with
 * nothing changed. In the relocated build, MARK lives in the core USER block;
 * the picker hook's cave veneer identifies that block, with a magic check.
 * ========================================================================== */

.equ H_GET,        0xC001D740    /* (desc, class, size, 0): gsup_launch.S    */
.equ H_ADDR,       0xC001D7F0    /* (desc) -> address                         */
.equ USER_CLASS,   0             /* NOT class 10: that is the frames' pool    */
.equ F_DCACHE,     0xC000E91C
.equ F_ICACHE,     0xC000EABC
.equ MARK_MAGIC,   0x534D4C53    /* "SLMS"                                    */
.equ CORE_MAGIC,   0x534C434F    /* "SLCO"                                    */
.equ PICKER_SITE,  0xC043CCF8
.equ CAVE_BEGIN,   0xC072E064
.equ CAVE_END,     0xC072EFB4
.equ ARM_VENEER,   0xE51FF004

/* Passed in by the builder: BLOB_LEN, BLOCK_BYTES, STATE_OFF, AREA_OFF,
 * AREA_BYTES, OFF_INSTALL / OFF_UI (from c_base, Thumb bit set), MARK and the
 * struct sl_menu offsets OFF_NBR / OFF_NBRLEN / OFF_READER. */

.macro LDA reg, value
    movw    \reg, #:lower16:\value
    movt    \reg, #:upper16:\value
.endm

entry:
    push    {r3, r4, r5, r6, r7, r8, r9, r10, r11, lr}   @ ten: 8-aligned
    sub     sp, sp, #16                 @ the allocator descriptor
#ifdef CORE_DYNAMIC
    /* Derive USER base from the already armed picker branch.  Validate the
     * veneer and packed core identity before allocating or touching UI state. */
    LDA     r0, PICKER_SITE
    ldr     r1, [r0]
    LDA     r2, 0xFF000000
    and     r3, r1, r2
    LDA     r2, 0xEA000000
    cmp     r3, r2
    bne     out
    lsl     r1, r1, #8
    asr     r1, r1, #6
    add     r1, r1, r0
    add     r1, r1, #8
    LDA     r2, CAVE_BEGIN
    cmp     r1, r2
    blo     out
    LDA     r2, CAVE_END - 8
    cmp     r1, r2
    bhi     out
    tst     r1, #3
    bne     out
    ldr     r3, [r1]
    LDA     r2, ARM_VENEER
    cmp     r3, r2
    bne     out
    ldr     r1, [r1, #4]
    tst     r1, #3
    bne     out
    LDA     r2, OFF_FMT_CODE
    subs    r10, r1, r2
    bcc     out
    tst     r10, #7
    bne     out
    LDA     r2, 0x40000000
    cmp     r10, r2
    blo     out
    LDA     r2, 0xF0000000
    cmp     r10, r2
    bhs     out
    LDA     r2, OFF_CORE_MAGIC
    ldr     r1, [r10, r2]
    LDA     r3, CORE_MAGIC
    cmp     r1, r3
    bne     out
    LDA     r2, OFF_MARK
    add     r11, r10, r2
#else
    mov     r10, #0
    LDA     r11, MARK
#endif
    mov     r0, sp
    mov     r1, #USER_CLASS
    LDA     r2, BLOCK_BYTES
    mov     r3, #0
    LDA     ip, H_GET
    blx     ip
    mov     r0, sp
    LDA     ip, H_ADDR
    blx     ip
    movs    r5, r0                      @ r5 = the resident base
    beq     out                         @ refused: stand down, camera is stock
    tst     r5, #7
    bne     out

    /* copy the whole blob -- this code included -- to the block */
    adr     r6, entry
    mov     r7, r5
    LDA     r8, BLOB_LEN
1:  ldr     ip, [r6], #4
    str     ip, [r7], #4
    subs    r8, r8, #4
    bne     1b
    /* zero the rest: the installer's state and its area */
    LDA     r8, BLOCK_BYTES
    add     r8, r5, r8
    mov     ip, #0
2:  cmp     r7, r8
    strlo   ip, [r7], #4
    blo     2b

    LDA     r6, STATE_OFF
    add     r6, r5, r6                  @ r6 = struct sl_menu
    str     r10, [r6, #OFF_CORE_BASE]
    mov     r0, r11
    LDA     r1, MARK_MAGIC
    str     r1, [r0]
    str     r5, [r0, #4]
    str     r6, [r0, #8]

    LDA     ip, F_DCACHE
    blx     ip
    LDA     ip, F_ICACHE
    blx     ip

    /* sl_menu_install(state, area, area_bytes), in the resident copy */
    mov     r0, r6
    LDA     r1, AREA_OFF
    add     r1, r5, r1
    LDA     r2, AREA_BYTES
    adr     r4, entry
    adr     ip, c_base
    sub     ip, ip, r4                  @ c_base's offset in the blob
    add     ip, r5, ip
    LDA     r4, OFF_INSTALL
    add     ip, ip, r4
    blx     ip
    mov     r1, r11
    str     r0, [r1, #12]               @ the result, for mem get
    cmp     r0, #1
    bne     out
    /* for sl_excl.S: the private NBR and the reader it is registered with */
    ldr     r2, [r6, #OFF_NBR]
    str     r2, [r1, #0x10]
    ldr     r2, [r6, #OFF_NBRLEN]
    str     r2, [r1, #0x14]
    ldr     r2, [r6, #OFF_READER]
    str     r2, [r1, #0x18]
    ldr     r2, [r6, #OFF_EXCLRATE]
    str     r2, [r1, #0x34]
    ldr     r2, [r6, #OFF_EXCLBIT]
    str     r2, [r1, #0x38]
    /* for sl_excl.S ROLE 7: sl_menu_ui in the resident copy (Thumb bit set) */
    adr     r2, entry
    adr     ip, c_base
    sub     ip, ip, r2                  @ c_base's offset in the blob
    add     ip, r5, ip
    LDA     r2, OFF_UI
    add     r3, ip, r2
    str     r3, [r1, #0x50]
    /* and sl_menu_live, for the frame-rate / bit-depth setter wrappers (ROLE 12-14) */
    LDA     r2, OFF_LIVE
    add     r3, ip, r2
    str     r3, [r1, #0x54]

#ifdef CORE_DYNAMIC
    /* Every SLX site was declared as a stock-word VBIN section, so stage2
     * journals it before this entry.  The resident installer checks all ten
     * declarations and both power-off callback lists, then reserves/writes
     * veneers, publishes them and finally arms the sites. */
    mov     r0, r10
    adr     r1, hook_table
    LDA     r2, OFF_JOURNAL_GATE
    LDA     r3, JOURNAL_MAX
    adr     r4, entry
    adr     ip, c_base
    sub     ip, ip, r4
    add     ip, r5, ip
    LDA     r4, OFF_ARM
    add     ip, ip, r4
    blx     ip
    cmp     r0, #1
    bne     hook_refused
    /* ROLE7 can run on the UI thread as soon as its site is armed.  If NBR
     * registration has already refused, it must not expose B2_5 here. */
    ldr     r0, [r11, #0x1C]            @ M_NBR: 3 = refused
    cmp     r0, #3
    beq     hook_refused
    /* The parser hook is active now; expose the private page last. */
    ldr     r0, [r6, #12]              @ struct sl_menu.entry
    ldr     r1, [r6, #16]              @ struct sl_menu.page
    LDA     r2, 0xC18C0460            @ NBU base
    sub     r1, r1, r2
    str     r1, [r0, #8]
    LDA     ip, F_DCACHE
    blx     ip
    ldr     r0, [r11, #0x1C]
    cmp     r0, #3
    beq     hook_refused
    b       out
hook_refused:
    /* The private page remains hidden or is restored to stock.  Registered
     * variables and resident memory are harmless with result != installed. */
    ldr     r0, [r6, #12]               @ struct sl_menu.entry
    cmp     r0, #0
    LDA     r1, 0x19C130               @ factory B2_5 page offset
    strne   r1, [r0, #8]
    mov     r0, #12                    @ SL_MENU_HOOK
    str     r0, [r6]
    str     r0, [r11, #12]
    LDA     ip, F_DCACHE
    blx     ip
#endif

out:
    add     sp, sp, #16
    pop     {r3, r4, r5, r6, r7, r8, r9, r10, r11, pc}

#ifdef CORE_DYNAMIC
    .align 2
hook_table:
    .word HOOK0_SITE, HOOK0_STOCK, HOOK0_OFFSET, HOOK0_KIND
    .word HOOK1_SITE, HOOK1_STOCK, HOOK1_OFFSET, HOOK1_KIND
    .word HOOK2_SITE, HOOK2_STOCK, HOOK2_OFFSET, HOOK2_KIND
    .word HOOK3_SITE, HOOK3_STOCK, HOOK3_OFFSET, HOOK3_KIND
    .word HOOK4_SITE, HOOK4_STOCK, HOOK4_OFFSET, HOOK4_KIND
    .word HOOK5_SITE, HOOK5_STOCK, HOOK5_OFFSET, HOOK5_KIND
    .word HOOK6_SITE, HOOK6_STOCK, HOOK6_OFFSET, HOOK6_KIND
    .word HOOK7_SITE, HOOK7_STOCK, HOOK7_OFFSET, HOOK7_KIND
    .word HOOK8_SITE, HOOK8_STOCK, HOOK8_OFFSET, HOOK8_KIND
    .word HOOK9_SITE, HOOK9_STOCK, HOOK9_OFFSET, HOOK9_KIND
#endif

    .align  3
c_base:
    /* the compiled C is appended here by build_sl_menu.py */
