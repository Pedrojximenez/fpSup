@ perf_core.S -- the sys-perf sup (Loader v3): one block holding the modules
@ neonblit / dirtyclean / filldma (and lz4fast when it exists), the fill
@ dispatcher, the switches and the installer.  build.py generates gen.inc
@ (module bodies, gate stubs, claim and write tables) and assembles this file.
@
@ Body offset 0 = file offset 32 (after the FSB1 header).  Everything is
@ position independent; firmware routines are reached through literals.
@
@ entry(r0 = block, r1 = svc, r2 = path) -> 0 KEEP / 1 RELEASE
@   1. claim every firmware word (EXCL, stock bytes from the reference image)
@      -- any failure: RELEASE, nothing written
@   2. cave_alloc the veneers (BL range of C0528xxx) -- failure: RELEASE
@   3. module control init, veneers, publish
@   4. phase 1 writes (data pointers, dirtyclean copy/clear sites), publish
@   5. phase 2 writes (dirtyclean clean site), publish
@ Power-off write-back is the loader's journal (the claims): nothing here.
@ There is no uninstall: hooks stay until power-off (LOADER_V3 §4).

        .syntax unified
        .arm
        .text

        .equ SVC_CLAIM,     8
        .equ SVC_CAVE,      20
        .equ SVC_PUBLISH,   24
        .equ SVC_LOG,       28
        .equ SL_EXCL,       2
        .equ FW_FILL,       0xC0721480      @ stock layer fill (ARM)
        .equ FW_FLUSH,      0xC000E91C

        .macro PCADDR reg, sym              @ reg = run-time address of sym
        ldr     \reg, 91f
90:     add     \reg, pc, \reg
        b       92f
91:     .word   \sym - (90b + 8)
92:
        .endm

@ ------------------------------------------------------------------ control
@ Fixed offsets from the body (host tool perfctl.py reads these).
pf_body:
        .word   0x46524550                  @ +00 'PERF'
        .word   4                           @ +04 layout version (2: +54..+5C module offsets; 3: +40 alphalut; 4: +44 waveform; 0 = module left out)
pf_master:
        .word   PF_MASTER_INIT              @ +08 0 = every hook behaves stock
pf_nb:
        .word   PF_NB_INIT                  @ +0C neonblit spans + CPU fill
pf_lz:
        .word   PF_LZ_INIT                  @ +10 lz4fast (0 when not built in)
pf_state:
        .word   0                           @ +14 0 never ran, 1 installed, else 0x100+why
pf_veneers:
        .word   0                           @ +18 cave address of the veneers
pf_n_fill:
        .word   0                           @ +1C dispatcher calls
pf_n_dma:
        .word   0                           @ +20 filled by filldma
pf_n_neon:
        .word   0                           @ +24 handed to nb_layer_fill
pf_n_stock:
        .word   0                           @ +28 handed to stock C0721480
pf_mods:
        .word   dc_mod - pf_body            @ +2C dirtyclean control block (its dc_ctl)
        .word   fd_mod - pf_body            @ +30 filldma header (fd_enable at +8)
        .word   nb_mod - pf_body            @ +34 neonblit code
        .word   LZ_MOD_OFF                  @ +38 lz4fast (0 = absent)
        .word   PF_BUILD_ID                 @ +3C low 32 bits of the build hash
pf_mods3:
        .word   AL_MOD_OFF                  @ +40 alphalut al_ctl (enable at +8); layout 3
        .word   WF_MOD_OFF                  @ +44 waveform wf_ctl (enable at +4); layout 4
        .space  12                          @ +48..+53 reserved (was the log buffer; the log
                                            @ line is now built on the stack -- svc->log copies it)
pf_mods2:
        .word   IR_MOD_OFF                  @ +54 inputredraw ir_base (enable at +8)
        .word   IC_MOD_OFF                  @ +58 iconcache ic_ctl (enable at +4)
        .word   PL_MOD_OFF                  @ +5C pagelru pl_ctl (enable at +4)

@ ------------------------------------------------------------------ dispatcher
@ The layer vtables' fill slot (0xC2E38E7C, 0xC2EF62A0).  Same arguments as
@ C0721480: r0 = layer, r1 = value.  Order: filldma (it declines with r0 != 0
@ having touched nothing) -> neonblit (it forwards non-16bpp to stock) -> stock.
        .global pf_layer_fill
pf_layer_fill:
        push    {r4-r6, lr}
        mov     r4, r0
        mov     r5, r1
        mov     r6, sp
        bic     sp, sp, #7
        adr     ip, pf_body
        ldr     r0, [ip, #0x1C]
        add     r0, r0, #1
        str     r0, [ip, #0x1C]
        ldr     r0, [ip, #0x08]             @ master
        cmp     r0, #0
        beq     3f
        mov     r0, r4
        mov     r1, r5
        bl      fd_layer_fill               @ checks its own fd_enable
        cmp     r0, #0
        bne     1f
        adr     ip, pf_body
        ldr     r0, [ip, #0x20]
        add     r0, r0, #1
        str     r0, [ip, #0x20]
        mov     sp, r6
        pop     {r4-r6, pc}
1:      adr     ip, pf_body
        ldr     r0, [ip, #0x0C]             @ neonblit switch
        cmp     r0, #0
        beq     3f
        ldr     r0, [ip, #0x24]
        add     r0, r0, #1
        str     r0, [ip, #0x24]
        mov     r0, r4
        mov     r1, r5
        mov     sp, r6
        pop     {r4-r6, lr}
        b       nb_layer_fill
3:      adr     ip, pf_body
        ldr     r0, [ip, #0x28]
        add     r0, r0, #1
        str     r0, [ip, #0x28]
        mov     r0, r4
        mov     r1, r5
        mov     sp, r6
        pop     {r4-r6, lr}
        ldr     pc, =FW_FILL

@ ------------------------------------------------------------------ dirtyclean gate
@ Replaces bl C000E91C at C0528954 (through a veneer).  Master off: the
@ stock whole-cache flush.  dirtyclean's clear/copy marks keep accumulating
@ meanwhile; that only makes its first round after master-on clean whole
@ buffers (conservative, never wrong).  r0-r3/ip are free: C000E91C clobbers them.
        .global pf_dc_gate
pf_dc_gate:
        adr     ip, pf_body
        ldr     r0, [ip, #0x08]
        cmp     r0, #0
        bne     dc_clean
        ldr     pc, =FW_FLUSH
        .ltorg

@ ------------------------------------------------------------------ entry
        .global pf_entry
pf_entry:
        push    {r4-r11, lr}
        mov     r11, sp
        bic     sp, sp, #7
        mov     r5, r1                      @ svc

        @ 1. claims
        PCADDR  r6, pf_claims
        ldr     r7, [r6], #4
1:      cmp     r7, #0
        beq     2f
        sub     sp, sp, #8
        ldr     r0, [r6, #8]                @ kind
        str     r0, [sp]
        mov     r0, r5
        ldr     r1, [r6]                    @ addr
        ldr     r2, [r6, #4]                @ len
        add     r3, r6, #12                 @ stock bytes follow
        ldr     ip, [r5, #SVC_CLAIM]
        blx     ip
        add     sp, sp, #8
        cmp     r0, #0
        movne   r0, #1                      @ why 1: a claim failed
        bne     fail
        ldr     r0, [r6, #4]
        add     r6, r6, #12
        add     r6, r6, r0
        sub     r7, r7, #1
        b       1b

        @ 2. veneers (8 bytes each), within BL range of every bl site
2:      mov     r0, r5
        mov     r1, #N_VENEERS * 8
        ldr     ip, [r5, #SVC_CAVE]
        blx     ip
        movs    r8, r0
        moveq   r0, #2                      @ why 2: no cave
        beq     fail
        ldr     r1, =0xC0528000
        subs    r1, r8, r1
        rsbmi   r1, r1, #0
        cmp     r1, #0x01000000             @ well inside +-32 MiB
        movhs   r0, #3                      @ why 3: cave out of BL range
        bhs     fail
        PCADDR  ip, pf_body
        str     r8, [ip, #0x18]

        @ 3. module control init (our own block), veneers, publish
        PCADDR  r0, dc_mod
        mov     r1, #DC_EN_INIT
        str     r1, [r0, #0x04]             @ C_EN
        mov     r1, #0
        str     r1, [r0, #0x08]             @ C_CLEAR
        mov     r1, #0xF
        str     r1, [r0, #0x0C]             @ C_COPY: first round per slot cleans whole
        PCADDR  r0, fd_mod
        mov     r1, #FD_EN_INIT
        str     r1, [r0, #0x08]             @ fd_enable
#if HAS_IR
        PCADDR  r0, ir_mod
        mov     r1, #IR_EN_INIT
        str     r1, [r0, #0x08]             @ ir_enable (the module ships 1)
#endif
#if HAS_PL
        PCADDR  r0, pl_mod
        mov     r1, #PL_EN_INIT
        str     r1, [r0, #0x04]             @ pagelru enable
#endif
#if HAS_IC
        PCADDR  r0, ic_mod
        PCADDR  r1, pf_end                  @ arena = block BSS after the file
        add     r1, r1, #7
        bic     r1, r1, #7
        str     r1, [r0, #0x08]             @ ARENA (absolute)
        ldr     r1, =IC_ARENA
        str     r1, [r0, #0x0C]             @ ARENA_SZ
        mov     r1, #IC_EN_INIT
        str     r1, [r0, #0x04]             @ EN last
#endif
#if HAS_AL
        PCADDR  r0, al_mod
        mov     r1, #AL_EN_INIT
        str     r1, [r0, #0x08]             @ alphalut enable (the module ships 1)
#endif
#if HAS_WF
        PCADDR  r0, wf_mod
        mov     r1, #WF_EN_INIT
        str     r1, [r0, #0x04]             @ waveform enable (the module ships 1)
#endif
        PCADDR  r6, pf_writes
        ldr     r7, [r6], #4
        mov     r9, #0                      @ veneer index
3:      cmp     r7, #0
        beq     4f
        ldr     r0, [r6, #4]                @ type
        cmp     r0, #0
        beq     31f
        PCADDR  r1, pf_body
        ldr     r2, [r6, #12]               @ target, body-relative
        add     r1, r1, r2
        add     r2, r8, r9, lsl #3
        cmp     r0, #3
        ldrne   r3, =0xE51FF004             @ ARM: ldr pc, [pc, #-4]
        ldreq   r3, =0xF000F8DF             @ Thumb: ldr.w pc, [pc, #0]
        str     r3, [r2]
        str     r1, [r2, #4]
        add     r9, r9, #1
31:     add     r6, r6, #16
        sub     r7, r7, #1
        b       3b
4:      mov     r0, r5
        ldr     ip, [r5, #SVC_PUBLISH]
        blx     ip

        @ 4./5. firmware words, phase by phase, each phase published
        mov     r10, #1
5:      PCADDR  r6, pf_writes
        ldr     r7, [r6], #4
        mov     r9, #0
6:      cmp     r7, #0
        beq     8f
        ldr     r0, [r6]                    @ addr
        ldr     r1, [r6, #4]                @ type
        ldr     r2, [r6, #8]                @ phase
        cmp     r1, #0
        addne   r3, r8, r9, lsl #3          @ branch rows: this row's veneer
        addne   r9, r9, #1
        cmp     r2, r10
        bne     7f
        cmp     r1, #2
        beq     62f
        cmp     r1, #3
        beq     63f
        cmp     r1, #1
        beq     61f
        PCADDR  r1, pf_body                 @ data: body + target
        ldr     r2, [r6, #12]
        add     r1, r1, r2
        str     r1, [r0]
        b       7f
61:     sub     r1, r3, r0                  @ bl veneer
        sub     r1, r1, #8
        lsr     r1, r1, #2
        bic     r1, r1, #0xFF000000
        orr     r1, r1, #0xEB000000
        str     r1, [r0]
        b       7f
62:     mov     r1, r3                      @ Thumb blx -> ARM veneer (two halfwords)
        mov     r2, #1
        bl      thumb_branch
        b       7f
63:     mov     r1, r3                      @ Thumb b.w -> Thumb veneer (one word)
        mov     r2, #0
        bl      thumb_branch
7:      add     r6, r6, #16
        sub     r7, r7, #1
        b       6b
8:      mov     r0, r5
        ldr     ip, [r5, #SVC_PUBLISH]
        blx     ip
        add     r10, r10, #1
        cmp     r10, #3
        blt     5b

        PCADDR  ip, pf_body
        mov     r0, #1
        str     r0, [ip, #0x14]
        PCADDR  r0, pf_body
        bl      log_ctl
        mov     r0, #0                      @ KEEP
        mov     sp, r11
        pop     {r4-r11, pc}

fail:   PCADDR  ip, pf_body
        add     r0, r0, #0x100
        str     r0, [ip, #0x14]
        mov     r0, #1                      @ RELEASE
        mov     sp, r11
        pop     {r4-r11, pc}

@ thumb_branch(r0 = site, r1 = veneer, r2 = 1 blx / 0 b.w).  Clobbers r0-r3, ip.
@ blx (T2): imm = veneer - Align(site+4, 4), halfwords stored one at a time
@ (the site may be only 2-aligned).  b.w (T4): imm = veneer - (site+4), one
@ aligned word.  hw1 = F000|S<<10|imm[21:12]; hw2 = J1<<13|J2<<11|low, with
@ J = NOT(I) XOR S; blx: C000|imm[11:2]<<1, b.w: 9000|imm[11:1].
thumb_branch:
        push    {r4-r6, lr}
        add     r3, r0, #4
        cmp     r2, #0
        bicne   r3, r3, #3
        sub     r3, r1, r3                  @ imm32
        lsr     r4, r3, #24
        and     r4, r4, #1                  @ S
        lsr     r5, r3, #23
        and     r5, r5, #1                  @ I1
        eor     r5, r5, #1
        eor     r5, r5, r4                  @ J1
        lsr     r6, r3, #22
        and     r6, r6, #1                  @ I2
        eor     r6, r6, #1
        eor     r6, r6, r4                  @ J2
        ubfx    ip, r3, #12, #10            @ imm10(H)
        orr     ip, ip, r4, lsl #10
        orr     ip, ip, #0xF000             @ hw1
        lsl     r5, r5, #13
        orr     r5, r5, r6, lsl #11
        cmp     r2, #0
        ubfxne  r6, r3, #2, #10             @ blx: imm10L
        lslne   r6, r6, #1
        orrne   r6, r6, #0xC000
        ubfxeq  r6, r3, #1, #11             @ b.w: imm11
        orreq   r6, r6, #0x9000
        orr     r5, r5, r6                  @ hw2
        cmp     r2, #0
        strhne  r5, [r0, #2]
        strhne  ip, [r0]
        orreq   ip, ip, r5, lsl #16
        streq   ip, [r0]
        pop     {r4-r6, pc}

@ "PERF ctl XXXXXXXX" -> svc->log.  r0 = address to print, r5 = svc.
log_ctl:
        push    {r4, lr}
        sub     sp, sp, #24                 @ line buffer; svc->log copies it (sloader logrec)
        mov     r1, sp
        ldr     r2, =0x46524550             @ "PERF"
        str     r2, [r1]
        ldr     r2, =0x6C746320             @ " ctl"
        str     r2, [r1, #4]
        mov     r2, #0x20
        strb    r2, [r1, #8]
        add     r1, r1, #9
        mov     r3, #28
1:      lsr     r2, r0, r3
        and     r2, r2, #0xF
        cmp     r2, #10
        addlo   r2, r2, #0x30
        addhs   r2, r2, #0x37
        strb    r2, [r1], #1
        subs    r3, r3, #4
        bpl     1b
        mov     r2, #0
        strb    r2, [r1]
        mov     r0, r5
        mov     r1, sp
        ldr     ip, [r5, #SVC_LOG]
        blx     ip
        add     sp, sp, #24
        pop     {r4, pc}
        .ltorg

#include GEN_INC
