/* OpenGate-specific runtime repair for the native SIGMA fp UI.
 *
 * This payload deliberately contains no capture geometry.  It registers a
 * private NBR pack and extends only the parsed MV_Resolution/QS records while
 * SIGMA's own NBU interpreter is consuming them.  Stock records and stock
 * image resources stay immutable.
 *
 * The generated ui_records/ui_edits tables are appended by
 * build_og3k_ui_candidate.py before assembly.
 */
.syntax unified
.arm
.text
#include "og_pic.inc"

.equ BASE,          OGA(0xC0732C84)
.equ STATE,         OGA(0xC0732700)
/* UI_DIAG only: two 16-word capture slots right after the 72-byte state.
 * Slot A = first target hit of this boot, slot B = first target hit whose
 * source record lies in the Quick Set MV_Resolution range. */
.equ DIAG,          OGA(0xC0732748)
/* ui_layout state, reset every load (48 bytes):
 *   +0 snapshot taken   +4 releases   +8 last layout released   +12 unused
 *   +16.. three {layout, tree built before our hooks (0 = none / no longer)} */
.equ REQ,           OGA(0xC07327C8)
.equ RCACHE,        0xC37B7254          /* UicResourceCache singleton */
.equ RCACHE_V3,     0xC0566498          /* UicResourceCache::v3 (ARM): release cached layout */
.equ RCACHE_NAMES,  0xC37B7288          /* its three QS layout names (QS_STILL/QS_CINE/QS_STILLlike) */
.equ LAYOUT_FIND,   0xC05E04E8          /* (ctx, name) -> layout object or 0 (Thumb) */
/* UI_DIAG only: ui_layout log.  +0..+8 the three snapshot trees (never
 * cleared), +12 entries written, +16.. seven 16-byte entries, one per load of
 * a recorded QS layout: {layout, its tree now, recorded tree before this call,
 * flags}.  flags = refcount of the tree now (low 16) | 1<<16 cache holds another
 * layout | 1<<17 it is the current screen | 1<<18 it is the held screen |
 * 1<<19 cache busy | 1<<20 this call released it. */
.equ LLOG,          OGA(0xC0732800)
.equ UI_PACK,       OGP(0xC0793060)
.equ UI_PACK_BYTES, OG3K_UI_PACK_BYTES

.macro addr reg,value
#ifdef OG_V3
    OGLDA   \reg, \value
#else
    movw    \reg, #:lower16:\value
    movt    \reg, #:upper16:\value
#endif
.endm

.macro call target
    addr    ip, \target
    blx     ip
.endm

/* OG_V3: the label's address from where this runs (og_pic.inc). */
.macro self reg,label
#ifdef OG_V3
    ldr     \reg, 90f
92: add     \reg, pc, \reg
    b       91f
90: .word \label - (92b + 8)
91:
#else
    ldr     \reg, 90f
    b       91f
90: .word BASE + (\label - ui_payload)
91:
#endif
.endm

.global ui_payload
ui_payload:

/* C05E84D8 is Thumb.  Replay its first four bytes in ui_load_original. */
.align 2
.thumb
.global ui_load
.thumb_func
ui_load:
    bx      pc
    nop
.arm
    push    {r4-r8, lr}
    mov     r4, r0
    mov     r5, r1
    self    ip, ui_load_original
    orr     ip, ip, #1                 @ idempotently select Thumb state
    blx     ip
    mov     r6, r0
    cmp     r6, #0
    bne     ui_load_done
    addr    r0, 0xC0D22400             @ stock NBR base
    cmp     r5, r0
    bne     ui_load_done
    mov     r0, r4
    bl      ensure_ui_pack
ui_load_done:
    mov     r0, r6
    pop     {r4-r8, pc}

/* If the stock NBR was parsed before AutoRun, the NBU hook calls this with the
 * same live resource context.  Registration is once per context. */
ensure_ui_pack:
    push    {r4-r6, lr}
    mov     r4, r0
    addr    r5, STATE
    ldr     r1, [r5, #0]               @ last resource context
    cmp     r1, r4
    bne     ensure_ui_new
    ldr     r0, [r5, #4]               @ 0 new, 1 ready, 2 loading, 3 failed
    cmp     r0, #0
    bne     ensure_ui_result
ensure_ui_new:
    str     r4, [r5, #0]
    mov     r0, #2
    str     r0, [r5, #4]
    mov     r0, r4
    addr    r1, UI_PACK
    movw    r2, #:lower16:UI_PACK_BYTES
    mov     r3, #0
    self    ip, ui_load_original
    orr     ip, ip, #1                 @ symbol may already carry Thumb bit
    blx     ip
    str     r0, [r5, #8]
    cmp     r0, #0
    moveq   r0, #1
    movne   r0, #3
    str     r0, [r5, #4]
ensure_ui_result:
    cmp     r0, #1
    moveq   r0, #1
    movne   r0, #0
    pop     {r4-r6, pc}

.align 2
.thumb
.thumb_func
ui_load_original:
    push    {lr}
    sub     sp, #24
    movw    ip, #0x84dd
    movt    ip, #0xc05e
    bx      ip

/* C05D90F0 (Thumb) loads one layout.  Quick Set layouts are held an extra
 * reference by UicResourceCache (+4) and are never re-parsed while it holds
 * them, so a QS opened before our hooks were armed stays stock for the whole
 * power cycle (notes/OG_BOOT_RESTORE_STABILITY_REVIEW_2026-09-23.md §7.8-7.12).
 *
 * The first layout load after arming comes before any post-arm re-parse, so
 * that is where the trees the cache's QS layouts already have are recorded:
 * those were built without our hooks.  (Recording what the cache holds is not
 * enough: with QS left open across the load, the cache only takes QS_CINE in
 * the 0x2601 'leaving QS' event, after the switch's first load.)
 *
 * When a recorded layout is about to be loaded again with that same tree, is
 * held only by the cache (refcount 1) and is neither the current nor the held
 * screen, the cache releases it with its own v3 -- the release a CINE/STILL
 * round trip performs -- and the stock load re-parses it through ui_record.
 * A layout seen loading with no tree (rebuilt after arming), or with another
 * tree, is forgotten.  Runs in the GUI task inside the screen switch, like the
 * stock release.  A normal boot records nothing and never acts. */
.align 2
.thumb
.global ui_layout
.thumb_func
ui_layout:
    bx      pc
    nop
.arm
    push    {r0, r4-r9, lr}
#ifdef UI_NESTED
    self    r1, ui_aliases
    ldr     r1, [r1]                    @ not armed until the strings exist
    cmp     r1, #0
    beq     ui_layout_go
#endif
    mov     r4, r0                      @ layout about to be loaded
    addr    r5, REQ
    ldr     r1, [r5]
    cmp     r1, #0
    bne     ui_layout_check
    mov     r1, #1
    str     r1, [r5]
    ldr     r7, [r4, #4]                @ resource context
    addr    r8, RCACHE_NAMES
    add     r9, r5, #16
    mov     r6, #3
ui_layout_snap:
    ldr     r1, [r8], #4                @ QS layout name
    cmp     r1, #0
    beq     ui_layout_snap_next
    mov     r0, r7
    addr    ip, LAYOUT_FIND
    orr     ip, ip, #1
    blx     ip
    cmp     r0, #0
    ldrne   r1, [r0, #0xC]              @ its tree, if already built
    moveq   r1, #0
    str     r0, [r9]
    str     r1, [r9, #4]
#ifdef UI_DIAG
    addr    ip, LLOG
    rsb     r0, r6, #3
    str     r1, [ip, r0, lsl #2]        @ permanent copy of the snapshot tree
#endif
ui_layout_snap_next:
    add     r9, r9, #8
    subs    r6, r6, #1
    bne     ui_layout_snap
ui_layout_check:
    add     r9, r5, #16
    mov     r6, #3
ui_layout_find:
    ldr     r1, [r9]
    cmp     r1, r4
    beq     ui_layout_found
    add     r9, r9, #8
    subs    r6, r6, #1
    bne     ui_layout_find
    b       ui_layout_go
ui_layout_found:
#ifdef UI_DIAG
    bl      ui_layout_log
#endif
    ldr     r2, [r9, #4]                @ tree built before our hooks
    cmp     r2, #0
    beq     ui_layout_go
    ldr     r3, [r4, #0xC]
    cmp     r3, r2
    movne   r0, #0
    strne   r0, [r9, #4]                @ rebuilt or unloaded since: forget it
    bne     ui_layout_go
    addr    r2, RCACHE
    ldr     r0, [r2, #4]
    cmp     r0, r4                      @ cache holds it
    bne     ui_layout_go
    ldrb    r0, [r2, #0x28]
    cmp     r0, #0                      @ cache not busy
    bne     ui_layout_go
    ldr     r0, [r3, #0xC]
    cmp     r0, #1                      @ only the cache's reference is left
    bne     ui_layout_go
    ldr     r7, [r4, #4]
    ldr     r0, [r7, #0x84C]
    cmp     r0, r4                      @ not the current screen
    beq     ui_layout_go
    ldr     r0, [r7, #0x848]
    cmp     r0, r4                      @ not the held screen
    beq     ui_layout_go
    mov     r0, #0
    str     r0, [r9, #4]                @ one shot per layout
    ldr     r0, [r5, #4]
    add     r0, r0, #1
    str     r0, [r5, #4]
    str     r4, [r5, #8]
#ifdef UI_DIAG
    bl      ui_layout_log_fired
#endif
    mov     r0, r2
    addr    ip, RCACHE_V3
    blx     ip                          @ stock release of the cached layout
ui_layout_go:
    pop     {r0, r4-r9, lr}
    self    ip, ui_layout_original
    orr     ip, ip, #1
    bx      ip                          @ tail: stock load, same r0 and lr

#ifdef UI_DIAG
/* r4 = layout, r9 = its record.  Preserves every register but ip. */
ui_layout_log:
    push    {r0-r3, r5, lr}
    addr    r5, LLOG
    ldr     r0, [r5, #12]
    cmp     r0, #7
    bhs     ui_layout_log_done
    add     r1, r0, #1
    str     r1, [r5, #12]
    add     r5, r5, #16
    add     r5, r5, r0, lsl #4          @ entry
    str     r4, [r5]
    ldr     r1, [r4, #0xC]
    str     r1, [r5, #4]
    ldr     r2, [r9, #4]
    str     r2, [r5, #8]
    mov     r3, #0
    cmp     r1, #0
    ldrne   r3, [r1, #0xC]              @ refcount of the tree now
    ubfx    r3, r3, #0, #16
    addr    r0, RCACHE
    ldr     r1, [r0, #4]
    cmp     r1, r4
    orrne   r3, r3, #0x10000
    ldrb    r1, [r0, #0x28]
    cmp     r1, #0
    orrne   r3, r3, #0x80000
    ldr     r0, [r4, #4]
    ldr     r1, [r0, #0x84C]
    cmp     r1, r4
    orreq   r3, r3, #0x20000
    ldr     r1, [r0, #0x848]
    cmp     r1, r4
    orreq   r3, r3, #0x40000
    str     r3, [r5, #12]
ui_layout_log_done:
    pop     {r0-r3, r5, pc}

/* Mark the newest entry as the one that released its layout. */
ui_layout_log_fired:
    push    {r0, r1, lr}
    addr    ip, LLOG
    ldr     r0, [ip, #12]
    cmp     r0, #0
    beq     1f
    cmp     r0, #7
    movhi   r0, #7
    add     ip, ip, r0, lsl #4          @ 16 + (n-1)*16
    ldr     r1, [ip, #12]
    orr     r1, r1, #0x100000
    str     r1, [ip, #12]
1:  pop     {r0, r1, pc}
#endif

.align 2
.thumb
.thumb_func
ui_layout_original:
    push.w  {r4-r7, r10, r11, lr}
    movw    ip, #0x90f5
    movt    ip, #0xc05d
    bx      ip

#ifndef UI_NESTED
/* Synthetic string offsets FFFFFFF2..FFFFFFF6 are accepted only for the stock
 * NBU pool, or for a pool made by the shared convention (fpSup/uishare): a copy
 * of the stock pool with private strings appended by other sups, announced by
 * a 16-byte header right before it ("FSPL", version 1).  Such a pool keeps
 * every stock offset, and its length stays below FFFFFFF2, so the aliases mean
 * the same.  No global string lookup behavior is changed. */
.equ FSPL_MAGIC,    0x4C505346
.align 2
.thumb
.global ui_string
.thumb_func
ui_string:
    bx      pc
    nop
.arm
    cmp     r1, #0xfffffff2
    blo     ui_string_stock
    cmp     r1, #0xfffffff6
    bhi     ui_string_stock
    ldr     ip, [r0, #20]
    push    {r2, lr}
    addr    r2, 0xC18C0474             @ stock NBU string pool
    cmp     ip, r2
    beq     ui_string_pool_ok
    tst     ip, #3                     @ a shared pool is word aligned
    bne     ui_string_pool_other
    cmp     ip, #16
    bls     ui_string_pool_other
    ldr     r2, [ip, #-16]
    addr    lr, FSPL_MAGIC
    cmp     r2, lr
    bne     ui_string_pool_other
    ldr     r2, [ip, #-12]
    cmp     r2, #1                     @ uishare header version
    bne     ui_string_pool_other
ui_string_pool_ok:
    pop     {r2, lr}
    b       ui_string_alias
ui_string_pool_other:
    pop     {r2, lr}
    b       ui_string_stock
ui_string_alias:
    add     r1, r1, #14                @ F2..F6 -> table indices 0..4
    self    ip, ui_aliases
    ldr     r0, [ip, r1, lsl #2]
    bx      lr
ui_string_stock:
    self    ip, ui_string_original
    orr     ip, ip, #1                 @ symbol may already carry Thumb bit
    bx      ip

.align 2
.thumb
.thumb_func
ui_string_original:
    cmp.w   r1, #-1
    movw    ip, #0x5b5d
    movt    ip, #0xc05e
    bx      ip
#endif

/* UI_NESTED (fpSup/uishare/NESTED_HOOKS.md, 2026-10-04): there is no string
 * hook here.  OpenGate's five labels are strings in its FPUI block; at boot
 * ui_apply puts them in OpenGate's own layer of the nested string hooks and
 * writes the offsets they were given into ui_aliases (STRBASE).  Until then
 * ui_aliases[0] is 0 and nothing here is armed: ui_record leaves every record
 * stock and ui_layout takes no snapshot, so "armed" means "the strings exist"
 * and a Quick Set layout built before that is still found and re-parsed. */
/* C05E6400: parse one NBU record.  Only exact source addresses with exact
 * FNV-1a fingerprints enter the temporary-copy path. */
.align 2
.thumb
.global ui_record
.thumb_func
ui_record:
    bx      pc
    nop
.arm
    push    {r4-r11, lr}
    sub     sp, sp, #4                  @ retain 8-byte stack alignment
    mov     r4, r0
    ldr     r5, [r4, #36]
    addr    r6, 0xC18C0460             @ stock NBU base
    cmp     r5, r6
    bne     ui_record_stock

    ldr     r7, [r4, #4]
    add     r8, r5, r7                  @ exact source record address
    addr    r0, STATE
    ldr     r1, [r0, #12]
    add     r1, r1, #1
    str     r1, [r0, #12]              @ all post-AutoRun stock NBU records
    str     r8, [r0, #20]

    ldr     r0, [r4, #8]
    bl      ensure_ui_pack
    cmp     r0, #1
    bne     ui_record_stock
#ifdef UI_NESTED
    self    r0, ui_aliases
    ldr     r0, [r0]                    @ 0 until ui_apply hands out the strings
    cmp     r0, #0
    beq     ui_record_stock
#endif

    self    r9, ui_records
    mov     r10, #0
    movw    r11, #:lower16:UI_RECORD_COUNT
ui_record_find:
    cmp     r10, r11
    bhs     ui_record_stock
    add     r0, r10, r11
    lsr     r0, r0, #1
    add     r1, r0, r0, lsl #1
    add     r1, r9, r1, lsl #2         @ table row is 12 bytes
    ldr     r2, [r1]
    cmp     r8, r2
    beq     ui_record_found
    addhi   r10, r0, #1
    movlo   r11, r0
    b       ui_record_find

ui_record_found:
    mov     r11, r0                     @ preserve matched table index
    mov     r9, r1
    ldr     r10, [r9, #4]
    ubfx    r10, r10, #0, #10          @ original record length
    mov     r0, r8
    mov     r1, r10
    addr    r2, 0x811c9dc5
    addr    r3, 0x01000193
ui_record_hash:
    ldrb    ip, [r0], #1
    eor     r2, r2, ip
    mul     r2, r3, r2
    subs    r1, r1, #1
    bne     ui_record_hash
    ldr     r0, [r9, #8]
    cmp     r2, r0
    bne     ui_record_stock

    addr    r0, STATE
    ldr     r1, [r0, #16]
    add     r1, r1, #1
    str     r1, [r0, #16]              @ exact copy paths entered
    add     r0, r0, #24                 @ one bit per sorted record-table row
    lsr     r2, r11, #3
    ldrb    r3, [r0, r2]
    and     r1, r11, #7
    mov     ip, #1
    orr     r3, r3, ip, lsl r1
    strb    r3, [r0, r2]               @ persistent unique-hit bitmap
#ifdef UI_DIAG
    bl      ui_diag                    @ record who is parsing this record
#endif

    sub     sp, sp, #512               @ largest generated record < 512 bytes
    ldr     r6, [r9, #4]
    ubfx    r6, r6, #10, #3            @ operation kind
    cmp     r6, #4
    beq     ui_literal_delta
    cmp     r6, #2
    bhs     ui_replace_word
    cmp     r6, #1
    beq     ui_layout_copy

    /* Kind 0: insert big-endian float 2.0 into a controlValue record. */
    mov     r11, #32
    mov     r0, r8
    mov     r1, sp
    mov     r2, r11
ui_copy_prefix:
    ldrb    r3, [r0], #1
    strb    r3, [r1], #1
    subs    r2, r2, #1
    bne     ui_copy_prefix
    mov     r2, #0x40
    strb    r2, [r1], #1
    mov     r2, #0
    strb    r2, [r1], #1
    strb    r2, [r1], #1
    strb    r2, [r1], #1
    mov     r6, #4
ui_copy_tail:
    sub     r2, r10, r11
    cmp     r2, #0
    beq     ui_copy_done
ui_copy_tail_loop:
    ldrb    r3, [r0], #1
    strb    r3, [r1], #1
    subs    r2, r2, #1
    bne     ui_copy_tail_loop
ui_copy_done:
    add     r0, r10, r6
    rev     r0, r0
    str     r0, [sp, #4]               @ total record size
    mov     r0, #0x1a
    strb    r0, [sp, #31]              @ property mask includes max-value
    b       ui_copy_parse

/* Kind 2: timeline endpoint.  Kind 3: independent collapsed summary text. */
ui_replace_word:
    mov     r0, r8
    mov     r1, sp
    mov     r2, r10
1:
    ldrb    r3, [r0], #1
    strb    r3, [r1], #1
    subs    r2, r2, #1
    bne     1b
    mov     r1, #32
#ifdef UI_NESTED
    self    r0, ui_aliases
    ldr     r0, [r0, #16]             @ the summary's offset (ui_aliases[4])
#else
    mvn     r0, #9                    @ FFFFFFF6 = OG3K summary alias
#endif
    cmp     r6, #3
    beq     2f
    mov     r1, #36
    ldr     r0, [r9, #4]
    ubfx    r0, r0, #13, #7          @ new timeline endpoint
2:
    rev     r0, r0
    str     r0, [sp, r1]
    b       ui_copy_parse

/* Kind 1: append the first (UHD) key to every companion property at the new
 * endpoint, replacing only the selected image property's name. */
ui_layout_copy:
    mov     r0, r8
    mov     r1, sp
    mov     r2, #28
1:
    ldrb    r3, [r0], #1
    strb    r3, [r1], #1
    subs    r2, r2, #1
    bne     1b
    ldr     r11, [sp, #12]
    rev     r11, r11                  @ property count
    mov     r6, #1
ui_layout_property:
    ldr     ip, [r9, #4]
    ubfx    r2, ip, #13, #7           @ new state time
    mov     r3, #0
    ubfx    ip, ip, #20, #4           @ aliased property index + 1
    cmp     ip, r6
    bne     2f
    ldr     r3, [r9, #4]
    lsr     r3, r3, #24
#ifdef UI_NESTED
    sub     r3, r3, #0xF2             @ alias F2/F3/F4 -> ui_aliases[0..2]
    self    ip, ui_aliases
    ldr     r3, [ip, r3, lsl #2]
#else
    sub     r3, r3, #256              @ FFFFFFF2/3/4
#endif
2:
    bl      ui_clone_property
    add     r6, r6, #1
    subs    r11, r11, #1
    bne     ui_layout_property
    sub     r2, r1, sp
    rev     r2, r2
    str     r2, [sp, #4]
    b       ui_copy_parse

/* Kind 4: apply a bounded immutable edit recipe. */
ui_literal_delta:
    mov     r0, r8
    mov     r1, sp
    self    r2, ui_edits
    ldr     r3, [r9, #4]
    add     r2, r2, r3, lsr #13
    mov     r3, r10
    bl      ui_apply_delta
    b       ui_copy_parse

ui_apply_delta:
    push    {r4-r8, lr}
    mov     r4, r0
    add     r5, r0, r3
    mov     r6, r2
ui_delta_next:
    ldrh    r7, [r6], #2
    movw    r2, #65535
    cmp     r7, r2
    beq     ui_delta_tail
    ldrh    r8, [r6], #2
    ldrh    ip, [r6], #2
    add     r3, r4, r7
    sub     r3, r3, r0
    cmp     r3, #0
    beq     2f
1:
    ldrb    r2, [r0], #1
    strb    r2, [r1], #1
    subs    r3, r3, #1
    bne     1b
2:
    add     r0, r0, r8
    cmp     ip, #0
    beq     2f
1:
    ldrb    r2, [r6], #1
    strb    r2, [r1], #1
    subs    ip, ip, #1
    bne     1b
2:
    add     r6, r6, #1
    bic     r6, r6, #1
    b       ui_delta_next
ui_delta_tail:
    sub     r3, r5, r0
    cmp     r3, #0
    beq     2f
1:
    ldrb    r2, [r0], #1
    strb    r2, [r1], #1
    subs    r3, r3, #1
    bne     1b
2:
    pop     {r4-r8, pc}

/* r0/r1 source/destination cursors, r2 new time, r3 optional alias. */
ui_clone_property:
    push    {r4-r8, lr}
    mov     r4, r2
    mov     r5, r3
    ldr     r6, [r0]
    rev     r6, r6
    add     r7, r0, #20
    mov     r8, r1
    mov     r2, #20
1:
    ldrb    r3, [r0], #1
    strb    r3, [r1], #1
    subs    r2, r2, #1
    bne     1b
    add     r2, r6, #1
    strb    r2, [r8, #3]               @ count is < 256 in guarded sources
    add     r2, r6, r6, lsl #2
    lsl     r2, r2, #1                 @ count * 10
1:
    ldrb    r3, [r0], #1
    strb    r3, [r1], #1
    subs    r2, r2, #1
    bne     1b
    mov     r8, r1
    mov     r2, #10
1:
    ldrb    r3, [r7], #1               @ clone first/UHD key
    strb    r3, [r1], #1
    subs    r2, r2, #1
    bne     1b
    mov     r2, #0
    strb    r2, [r8, #2]
    strb    r2, [r8, #3]
    strb    r2, [r8, #4]
    strb    r4, [r8, #5]               @ big-endian time <= 255
    cmp     r5, #0
    beq     2f
#ifdef UI_NESTED
    lsr     r2, r5, #24                @ the whole offset, big-endian
    strb    r2, [r8, #6]
    lsr     r2, r5, #16
    strb    r2, [r8, #7]
    lsr     r2, r5, #8
    strb    r2, [r8, #8]
#else
    mov     r2, #255
    strb    r2, [r8, #6]
    strb    r2, [r8, #7]
    strb    r2, [r8, #8]
#endif
    strb    r5, [r8, #9]
2:
    pop     {r4-r8, pc}

ui_copy_parse:
    sub     r0, sp, r7                 @ reader still sees base + position
    str     r0, [r4, #36]
    mov     r0, r4
    self    ip, ui_record_original
    orr     ip, ip, #1                 @ symbol may already carry Thumb bit
    blx     ip
    str     r5, [r4, #36]
    add     r1, r7, r10                @ skip original source record
    str     r1, [r4, #4]
    add     sp, sp, #512
    b       ui_record_return

ui_record_stock:
    mov     r0, r4
    self    ip, ui_record_original
    orr     ip, ip, #1                 @ symbol may already carry Thumb bit
    blx     ip
ui_record_return:
    add     sp, sp, #4
    pop     {r4-r11, pc}

.align 2
.thumb
.thumb_func
ui_record_original:
    push.w  {r4-r11, lr}
    movw    ip, #0x6405
    movt    ip, #0xc05e
    bx      ip

#ifdef UI_DIAG
/* Capture the caller chain of an exact target hit.  Called from ui_record
 * with its frame intact: push {r4-r11,lr} + 4 bytes of alignment, so at
 * ui_diag's own push (5 words) the stock caller's LR is at sp+20+36 and the
 * caller's stack starts at sp+20+40.  Slot layout (16 words):
 *   +0 1 when filled  +4 source record  +8 parse object (r0 of C05E6400)
 *   +12 return address into the caller of C05E6400
 *   +16..+60 twelve words of the caller's stack (more return addresses)
 * Every register is preserved; nothing else is written. */
.align 2
.arm
ui_diag:
    push    {r0-r3, lr}
    addr    r0, DIAG
    ldr     r1, [r0]
    cmp     r1, #0
    bne     1f
    mov     r1, r0
    bl      ui_diag_fill               @ slot A: first hit of any target
1:
    addr    r1, 0xC2280000
    cmp     r8, r1
    blo     ui_diag_done
    addr    r1, 0xC2340000
    cmp     r8, r1
    bhs     ui_diag_done
    add     r1, r0, #64
    ldr     r2, [r1]
    cmp     r2, #0
    bne     ui_diag_done
    bl      ui_diag_fill               @ slot B: first Quick Set resolution hit
ui_diag_done:
    pop     {r0-r3, pc}

ui_diag_fill:                           @ r1 = slot; sp = ui_diag's frame
    mov     r2, #1
    str     r2, [r1]
    str     r8, [r1, #4]
    str     r4, [r1, #8]
    ldr     r2, [sp, #56]
    str     r2, [r1, #12]
    .irp    i, 0,1,2,3,4,5,6,7,8,9,10,11
    ldr     r2, [sp, #60 + \i * 4]
    str     r2, [r1, #16 + \i * 4]
    .endr
    bx      lr
#endif

.align 2
.arm
.global ui_aliases
ui_aliases:
#ifdef UI_NESTED
    .word 0, 0, 0, 0, 0                         @ offsets, written by ui_apply (STRBASE)
#else
    .word BASE + (ui_name_qs - ui_payload)      @ FFFFFFF2
    .word BASE + (ui_name_set - ui_payload)     @ FFFFFFF3
    .word BASE + (ui_name_font - ui_payload)    @ FFFFFFF4
    .word BASE + (ui_name_unused - ui_payload)  @ FFFFFFF5, deliberately unused
    .word BASE + (ui_summary - ui_payload)      @ FFFFFFF6

ui_name_qs:     .asciz "OG3K_QS"
ui_name_set:    .asciz "OG3K_SET"
ui_name_font:   .asciz "OG3K_FONT"
ui_name_unused: .asciz "OG3K_UNUSED"
/* 收合摘要顯示的文字。2026-09-15:原本寫死 "OG3K",OG2K 的 build 也會
 * 顯示 OG3K。上面那幾個 OG3K_* 是**內部資源名**,不顯示,不需要改。
 * 由 build_og3k_ui_candidate.py 以 -DUI_SUMMARY_TEXT 傳入。 */
#ifndef UI_SUMMARY_TEXT
#define UI_SUMMARY_TEXT "OG3K"
#endif
ui_summary:     .asciz UI_SUMMARY_TEXT
#endif
.align 2

/* build_og3k_ui_candidate.py appends UI_RECORD_COUNT, ui_records and ui_edits. */
