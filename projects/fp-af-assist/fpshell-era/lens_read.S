/* lens_read.S — CmdRead(ctx, addr, len, dest, 0). ctx/addr/len from scratch (configurable). */
.syntax unified
.arm
.text
.global _start
_start:
    push  {r4-r11, lr}
    ldr   r4, .Lscr
    ldr   r0, [r4, #0]       @ ctx (lens_mgr: 0xC347CB14 runtime / 0xC347D098 mount)
    ldr   r1, [r4, #4]       @ addr
    ldr   r2, [r4, #8]       @ len
    ldr   r3, .Ldest
    mov   r5, #0
    push  {r5}               @ flag=0
    ldr   ip, .Lcmdread
    blx   ip
    add   sp, sp, #4
    str   r0, [r4, #12]      @ ret
    pop   {r4-r11, lr}
    bx    lr
.align 2
.Lscr:     .word 0xC072FF00
.Ldest:    .word 0xC072FA00
.Lcmdread: .word 0xC0355BE0
