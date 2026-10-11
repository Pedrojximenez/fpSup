/* RETIRED 2026-09-28. Power-off restoration belongs to the shared loader, not
 * to a sup: stage2 registers one callback in both lists and journals every
 * firmware word a card changes, and a sup that arms a hook at run time declares
 * the site as a four-byte section holding the stock word instead of registering
 * a routine of its own (fpSup/HOOKS_AT_POWER_OFF.md). This object also spent one
 * of the ordinary list's ten slots, of which the firmware already fills eight.
 * Kept only as a record of the manager ABI it modelled; nothing installs it.
 * See notes/AF_LOADER_CONVENTION_FINDING_2026-09-28.md.
 */
.syntax unified
.arm
.text
/* Power-off restore object for the finite AF publication trial, fp 5.02.
 *
 * The loader's own journal (asm/stage2.S, LH_RESTORE) covers the words a
 * card's section table writes.  The AF callsite and the borrowed echo are
 * written at runtime over USB, so they are NOT in that journal, and the journal
 * has no runtime append API or published spare capacity.  This object is the
 * trial's own entry in the firmware's power-off manager, holding exactly the
 * words the trial borrows.
 *
 * Assemble at its final cave address:
 *   AF_POFF_BLOCK       the boot-scoped cave.claim() address of this object
 *   AF_POFF_SITE        AF publication callsite; ORIG its stock word; ARMED the
 *                       candidate branch word the trial writes there
 *   AF_POFF_ECHO        borrowed echo word; ORIG its stock value; A1..A3 the
 *                       other values the trial leaves there. This object's own
 *                       register entry is the fourth, added here.
 * Every allowed value is fixed at assembly time.  A word held by anyone else is
 * left alone and reported, never overwritten at power-off.
 *
 * Block layout, matching the loader's so the manager needs no vtable of ours:
 *   +0x00 vtbl     = BLOCK-8; the manager calls [vtbl+0xC], which is [BLOCK+4]
 *   +0x04 routine  = pg_restore
 *   +0x08 pairs    = the entry table
 *   +0x0C status   register outcome bits (see below)
 *   +0x10 runs     times the routine has run
 *   +0x14 masks    low 16 bits restored, high 16 bits foreign owner
 *   +0x18 code, then the table: { address, original, allowed[4] } x n, 0
 *
 * status: 1 ordinary registered, 2 forced registered, 4 manager null,
 *         8 ordinary list full, 16 forced list full, 32 already attempted.
 * Registration is attempted once; a refused ordinary list does not try forced.
 * The routine may run twice (both lists) -- writing an original word back twice
 * is harmless.  It performs no allocation, no wait, no USB and no lens command,
 * and it never touches the cave, the trial's USER allocation or the loader's
 * own journal.
 */
#ifndef AF_POFF_BLOCK
#error AF_POFF_BLOCK is required
#endif
#ifndef AF_POFF_SITE
#error AF_POFF_SITE is required
#endif
#ifndef AF_POFF_ECHO
#error AF_POFF_ECHO is required
#endif

.equ POFF_MGR,  0xC0023A98           /* () -> XC_PowerOffMgr                */
.equ POFF_ADD,  0xC0024118           /* (mgr, obj, forced) -> 1 registered   */
.equ F_DCACHE,  0xC000E91C
.equ F_ICACHE,  0xC000EABC
.equ BLOCK,     AF_POFF_BLOCK
.equ MAX_ENTRY, 8                    /* bound on the table walk              */

.macro LDA reg, value
    movw \reg, #:lower16:\value
    movt \reg, #:upper16:\value
.endm

/* Absolute addresses within this object are BLOCK plus an in-section label
 * difference: a constant at assembly time, so no ABS32 relocation is emitted
 * (armasm.py supports R_ARM_CALL and a pc-relative literal only). */
.equ A_RESTORE,  BLOCK + (pg_restore - block)
.equ A_PAIRS,    BLOCK + (pairs - block)
.equ A_REGISTER, BLOCK + (pg_register - block)

.global block
block:
    .word BLOCK - 8                  /* +0x00 vtbl                           */
    .word A_RESTORE                  /* +0x04 routine                        */
    .word A_PAIRS                    /* +0x08 pairs                          */
    .word 0                          /* +0x0C status                         */
    .word 0                          /* +0x10 runs                           */
    .word 0                          /* +0x14 masks                          */

/* --- registration, called once through the borrowed echo ------------------
 * Publishes nothing: the installer publishes this object's code and header
 * before branching here, and re-publishes after.  Returns status in r0. */
.global pg_register
pg_register:
    push {r4, r5, r6, lr}
    mov r6, sp
    bic sp, sp, #7
    LDA r4, BLOCK
    ldr r0, [r4, #0x0C]
    cmp r0, #0
    bne already                      /* one attempt per boot, never re-added */
    mov r5, #32
    str r5, [r4, #0x0C]              /* attempted, published before the call */
    LDA r3, POFF_MGR
    blx r3
    cmp r0, #0
    beq no_manager
    mov r5, r0
    mov r0, r5
    LDA r1, BLOCK
    mov r2, #0                       /* the ordinary list                    */
    LDA r3, POFF_ADD
    blx r3
    cmp r0, #0
    beq ordinary_full
    mov r0, #1
    str r0, [r4, #0x0C]              /* ordinary registered, forced pending  */
    mov r0, r5
    LDA r1, BLOCK
    mov r2, #1                       /* the forced list: the manager's fast
                                      * path runs it instead of the ordinary */
    LDA r3, POFF_ADD
    blx r3
    cmp r0, #0
    beq forced_full
    mov r0, #3
    b register_done

no_manager:
    mov r0, #(32 | 4)
    b register_done
ordinary_full:
    mov r0, #(32 | 8)
    b register_done
forced_full:
    mov r0, #(1 | 16)
    b register_done
already:
    mov sp, r6
    pop {r4, r5, r6, pc}
register_done:
    str r0, [r4, #0x0C]
    mov sp, r6
    pop {r4, r5, r6, pc}

/* --- the power-off routine: vtbl[+0xC](obj, reason) -----------------------
 * Walks the table; for each entry whose word is not already stock and whose
 * current value is one this trial is known to write, puts the original back.
 * Then one D-cache clean and one I-cache invalidate, because a restored word
 * is an instruction. Preserves the caller's sp and r4-r11. */
pg_restore:
    push {r4, r5, r6, r7, r8, r9, lr}
    mov r9, sp
    bic sp, sp, #7
    mov r8, r0                       /* the object                           */
    ldr r4, [r8, #8]                 /* the table                            */
    ldr r7, [r8, #0x14]              /* masks, accumulated across both lists */
    mov r5, #0                       /* entry index                          */
entry_loop:
    cmp r5, #MAX_ENTRY
    bhs walked
    ldr r1, [r4]
    cmp r1, #0
    beq walked
    ldr r2, [r1]                     /* the live word                        */
    ldr r3, [r4, #4]                 /* the original                         */
    cmp r2, r3
    beq next_entry                   /* already stock                        */
    add r6, r4, #8                   /* allowed[0]                           */
    mov r0, #4
allowed_loop:
    cmp r0, #0
    beq foreign
    ldr ip, [r6], #4
    sub r0, r0, #1
    cmp ip, #0
    beq foreign                      /* the list ended: not ours             */
    cmp ip, r2
    bne allowed_loop
    str r3, [r1]                     /* ours: put the original back          */
    mov r0, #1
    lsl r0, r0, r5
    orr r7, r7, r0
    b next_entry
foreign:
    mov r0, #0x10000
    lsl r0, r0, r5
    orr r7, r7, r0
next_entry:
    add r4, r4, #0x18
    add r5, r5, #1
    b entry_loop

walked:
    str r7, [r8, #0x14]
    ldr r0, [r8, #0x10]
    add r0, r0, #1
    str r0, [r8, #0x10]
    LDA r3, F_DCACHE
    blx r3
    LDA r3, F_ICACHE
    blx r3
    mov sp, r9
    pop {r4, r5, r6, r7, r8, r9, pc}

.balign 4
pairs:
    .word AF_POFF_SITE
    .word AF_POFF_SITE_ORIG
    .word AF_POFF_SITE_ARMED
    .word 0
    .word 0
    .word 0
    .word AF_POFF_ECHO
    .word AF_POFF_ECHO_ORIG
    .word AF_POFF_ECHO_A1
    .word AF_POFF_ECHO_A2
    .word AF_POFF_ECHO_A3
    .word A_REGISTER                 /* the installer reaches this object
                                      * through the same borrowed echo       */
    .word 0                          /* end of table                         */
.global block_end
block_end:
