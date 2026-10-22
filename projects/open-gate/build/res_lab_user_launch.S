.syntax unified
.arm
.text
.global entry

/* Run-in-place Sensor Lab core installer.  The builder appends descriptor
 * tables and one packed USER image; only 8-byte veneers use CAVE_BUMP.
 * All writable firmware sites are carried as factory words in the VBIN, so
 * stage2 records them before this entry runs.  A failed check arms nothing.
 *
 * Builder definitions: BLOCK_BYTES, CORE_BYTES, IMAGE_OFF, RELOCS_OFF,
 * RELOC_COUNT, GATE_PAIRS_OFF, GATE_COUNT, ARMS_OFF, HOOK_COUNT,
 * POINTERS_OFF, POINTER_COUNT, JOURNAL_GATE_OFF, JOURNAL_MAX, RESTORE_OFF.
 */
.equ H_GET,          0xC001D740
.equ H_ADDR,         0xC001D7F0
.equ F_DCACHE,       0xC000E91C
.equ F_ICACHE,       0xC000EABC
.equ CAVE_BUMP,      0xC072E060
.equ CAVE_ARENA,     0xC072E064
.equ CAVE_END,       0xC072EFB4
.equ VENEER_LDR,     0xE51FF004
.equ VENEER_BYTES,   (HOOK_COUNT * 8)

.macro LDA reg, value
    movw    \reg, #:lower16:\value
    movt    \reg, #:upper16:\value
.endm

entry:
.Lentry:
    push    {r3-r11, lr}              @ ten words: AAPCS alignment
    sub     sp, sp, #16               @ allocator descriptor, never freed
    mov     r0, sp
    mov     r1, #0                    @ USER class
    LDA     r2, BLOCK_BYTES
    mov     r3, #0
    LDA     ip, H_GET
    blx     ip
    mov     r0, sp
    LDA     ip, H_ADDR
    blx     ip
    movs    r5, r0                    @ USER base
    beq     out
    tst     r5, #7
    bne     out
    adr     r4, .Lentry              @ run-in-place staging base

    LDA     r0, IMAGE_OFF
    add     r0, r4, r0
    mov     r1, r5
    LDA     r2, CORE_BYTES
1:  ldr     r3, [r0], #4
    str     r3, [r1], #4
    subs    r2, r2, #4
    bne     1b
    LDA     r2, BLOCK_BYTES
    add     r2, r5, r2
    mov     r3, #0
2:  cmp     r1, r2
    strlo   r3, [r1], #4
    blo     2b

    /* Internal absolute words and ARM MOVW/MOVT pairs.  Branches between
     * packed spans were resolved while building and need no runtime work. */
    LDA     r6, RELOCS_OFF
    add     r6, r4, r6
    LDA     r7, RELOC_COUNT
3:  cmp     r7, #0
    beq     4f
    ldr     r0, [r6], #4             @ top 2 bits = kind
    ldr     r9, [r6], #4             @ target USER offset
    mov     r8, r0, lsl #2
    mov     r8, r8, lsr #2          @ source USER offset
    add     r8, r5, r8
    add     r9, r5, r9
    mov     r0, r0, lsr #30
    cmp     r0, #1                  @ ABS32
    streq   r9, [r8]
    beq     5f
    cmp     r0, #2                  @ ARM_MOV32, adjacent instructions
    bne     out
    mov     r0, r8
    mov     r1, r9
    bl      patch_mov
    add     r0, r8, #4
    mov     r1, r9, lsr #16
    bl      patch_mov
5:  subs    r7, r7, #1
    b       3b
4:
    bl      publish                 @ executable USER payload and gate

    /* Gate includes every core hook and every external MOVW/MOVT site.
     * It checks the stage2 callback on both power-off lists and the exact
     * factory words preserved by its bounded journal. */
    LDA     r0, GATE_PAIRS_OFF
    add     r0, r4, r0
    LDA     r1, GATE_COUNT
    LDA     r2, JOURNAL_MAX
    LDA     ip, JOURNAL_GATE_OFF
    add     ip, r5, ip
    blx     ip
    cmp     r0, #1
    bne     out

    /* Reserve every near veneer before changing any firmware instruction. */
    LDA     r0, CAVE_BUMP
    ldr     r8, [r0]
    tst     r8, #3
    bne     out
    LDA     r1, CAVE_ARENA
    cmp     r8, r1
    blo     out
    LDA     r1, VENEER_BYTES
    adds    r9, r8, r1
    bcs     out
    LDA     r1, CAVE_END
    cmp     r9, r1
    bhi     out

    /* Publish all veneer targets while every site is still stock. */
    LDA     r6, ARMS_OFF
    add     r6, r4, r6
    mov     r7, #HOOK_COUNT
    mov     r10, r8
    LDA     r11, VENEER_LDR
6:  ldr     r0, [r6], #4             @ target offset; bit 31 marks BL
    bic     r0, r0, #0x80000000
    add     r0, r5, r0
    str     r11, [r10], #4
    str     r0, [r10], #4
    subs    r7, r7, #1
    bne     6b
    LDA     r0, CAVE_BUMP
    str     r9, [r0]
    bl      publish

    /* The conversion functions' three pointer pairs must follow the new
     * tables.  Their six sites are already validated and journalled. */
    LDA     r6, POINTERS_OFF
    add     r6, r4, r6
    mov     r7, #POINTER_COUNT
7:  ldr     r8, [r6], #4             @ low instruction site
    ldr     r9, [r6], #4             @ high instruction site
    ldr     r1, [r6], #4             @ target offset
    add     r1, r5, r1
    mov     r0, r8
    bl      patch_mov
    mov     r0, r9
    mov     r1, r1, lsr #16
    bl      patch_mov
    subs    r7, r7, #1
    bne     7b
    bl      publish

    /* Dependency order from imx410_plan._stages(): picker is last.  No
     * failure path remains after the first patch. */
    LDA     r6, GATE_PAIRS_OFF
    add     r6, r4, r6
    LDA     r7, ARMS_OFF
    add     r7, r4, r7
    LDA     r0, CAVE_BUMP
    ldr     r10, [r0]
    sub     r10, r10, #VENEER_BYTES
    mov     r11, #HOOK_COUNT
8:  ldr     r0, [r6], #8             @ site, skip stock word
    ldr     r2, [r7], #4
    mov     r3, #0xEA000000         @ B
    tst     r2, #0x80000000
    orrne   r3, r3, #0x01000000     @ BL
    mov     r1, r10                 @ corresponding veneer
    bl      encode_branch
    add     r10, r10, #8
    subs    r11, r11, #1
    bne     8b
    bl      publish

    /* Restore the user's prior resolution only after the selector is live. */
    LDA     r0, RESTORE_OFF
    add     r0, r5, r0
    mov     ip, r0
    blx     ip
out:
    add     sp, sp, #16
    mov     r0, #0
    pop     {r3-r11, pc}

/* Patch immediate16 of an existing MOVW or MOVT at r0 using r1's low half. */
patch_mov:
    ldr     r2, [r0]
    LDA     r3, 0xFFF0F000
    and     r2, r2, r3
    movw    ip, #0x0FFF
    and     ip, ip, r1
    orr     r2, r2, ip
    mov     r3, r1, lsr #12
    and     r3, r3, #0xF
    orr     r2, r2, r3, lsl #16
    str     r2, [r0]
    bx      lr

/* r0=site, r1=veneer, r3=B/BL top byte.  The builder proves range/alignment. */
encode_branch:
    sub     ip, r1, r0
    sub     ip, ip, #8
    asr     ip, ip, #2
    bic     ip, ip, #0xFF000000
    orr     ip, ip, r3
    str     ip, [r0]
    bx      lr

publish:
    push    {r4, lr}
    LDA     ip, F_DCACHE
    blx     ip
    LDA     ip, F_ICACHE
    blx     ip
    pop     {r4, pc}
