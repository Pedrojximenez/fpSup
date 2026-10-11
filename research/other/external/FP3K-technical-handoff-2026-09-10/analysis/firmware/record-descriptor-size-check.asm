c0379f98  a0e8ffeb   bl       #0xc0374220
c0379f9c  0010a0e1   mov      r1, r0
c0379fa0  0120a0e1   mov      r2, r1
c0379fa4  0710a0e1   mov      r1, r7
c0379fa8  0200a0e1   mov      r0, r2
c0379fac  03edffeb   bl       #0xc03753c0
c0379fb0  0010a0e1   mov      r1, r0
c0379fb4  0150a0e1   mov      r5, r1
c0379fb8  000055e3   cmp      r5, #0
c0379fbc  8100000a   beq      #0xc037a1c8
c0379fc0  a40084e2   add      r0, r4, #0xa4
c0379fc4  e981fdeb   bl       #0xc02da770
c0379fc8  0010a0e1   mov      r1, r0
c0379fcc  28108de5   str      r1, [sp, #0x28]
c0379fd0  100085e2   add      r0, r5, #0x10
c0379fd4  e581fdeb   bl       #0xc02da770
c0379fd8  0010a0e1   mov      r1, r0
c0379fdc  28809de5   ldr      r8, [sp, #0x28]
c0379fe0  010058e1   cmp      r8, r1
c0379fe4  7700000a   beq      #0xc037a1c8
c0379fe8  de49feeb   bl       #0xc030c768
c0379fec  0010a0e1   mov      r1, r0
c0379ff0  0100a0e1   mov      r0, r1
c0379ff4  0010a0e3   mov      r1, #0
c0379ff8  fc4bfeeb   bl       #0xc030cff0
c0379ffc  0110a0e3   mov      r1, #1
c037a000  7810c4e5   strb     r1, [r4, #0x78]
c037a004  fc8001e3   movw     r8, #0x10fc
c037a008  058088e0   add      r8, r8, r5
c037a00c  001098e5   ldr      r1, [r8]
c037a010  0b00a0e1   mov      r0, fp
c037a014  05ecffeb   bl       #0xc0375030
c037a018  590100ea   b        #0xc037a584
