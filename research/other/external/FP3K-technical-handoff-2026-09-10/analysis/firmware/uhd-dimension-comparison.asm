c02c0388  80850fe3   movw     r8, #0xf580
c02c038c  96804ce3   movt     r8, #0xc096
c02c0390  000398e8   ldm      r8, {r8, sb}
c02c0394  10808de5   str      r8, [sp, #0x10]
c02c0398  14908de5   str      sb, [sp, #0x14]
c02c039c  88850fe3   movw     r8, #0xf588
c02c03a0  96804ce3   movt     r8, #0xc096
c02c03a4  000398e8   ldm      r8, {r8, sb}
c02c03a8  08808de5   str      r8, [sp, #8]
c02c03ac  0c908de5   str      sb, [sp, #0xc]
c02c03b0  10309de5   ldr      r3, [sp, #0x10]
c02c03b4  34c194e5   ldr      ip, [r4, #0x134]
c02c03b8  0020a0e3   mov      r2, #0
c02c03bc  03005ce1   cmp      ip, r3
c02c03c0  0300001a   bne      #0xc02c03d4
c02c03c4  38c194e5   ldr      ip, [r4, #0x138]
c02c03c8  14309de5   ldr      r3, [sp, #0x14]
c02c03cc  03005ce1   cmp      ip, r3
c02c03d0  0120a003   moveq    r2, #1
c02c03d4  000052e3   cmp      r2, #0
c02c03d8  0a00001a   bne      #0xc02c0408
c02c03dc  08309de5   ldr      r3, [sp, #8]
c02c03e0  34c194e5   ldr      ip, [r4, #0x134]
c02c03e4  0020a0e3   mov      r2, #0
c02c03e8  03005ce1   cmp      ip, r3
c02c03ec  0300001a   bne      #0xc02c0400
c02c03f0  38c194e5   ldr      ip, [r4, #0x138]
c02c03f4  0c309de5   ldr      r3, [sp, #0xc]
c02c03f8  03005ce1   cmp      ip, r3
c02c03fc  0120a003   moveq    r2, #1
c02c0400  000052e3   cmp      r2, #0
c02c0404  0100000a   beq      #0xc02c0410
c02c0408  1c0000ea   b        #0xc02c0480
c02c040c  00f020e3   nop      
c02c0410  002194e5   ldr      r2, [r4, #0x100]
c02c0414  0a0b52e3   cmp      r2, #0x2800
c02c0418  020000da   ble      #0xc02c0428
c02c041c  1e60a0e3   mov      r6, #0x1e
c02c0420  0f0000ea   b        #0xc02c0464
c02c0424  00f020e3   nop      
c02c0428  002194e5   ldr      r2, [r4, #0x100]
c02c042c  050b52e3   cmp      r2, #0x1400
c02c0430  020000aa   bge      #0xc02c0440
c02c0434  6460a0e3   mov      r6, #0x64
c02c0438  090000ea   b        #0xc02c0464
c02c043c  00f020e3   nop      
c02c0440  002194e5   ldr      r2, [r4, #0x100]
c02c0444  1e30a0e3   mov      r3, #0x1e
c02c0448  0a1ba0e3   mov      r1, #0x2800
c02c044c  050ba0e3   mov      r0, #0x1400
c02c0450  00208de5   str      r2, [sp]
c02c0454  6420a0e3   mov      r2, #0x64
c02c0458  704108eb   bl       #0xc04d0a20
c02c045c  0020a0e1   mov      r2, r0
c02c0460  0260a0e1   mov      r6, r2
c02c0464  28209de5   ldr      r2, [sp, #0x28]
c02c0468  960202e0   mul      r2, r6, r2
c02c046c  1f3508e3   movw     r3, #0x851f
c02c0470  eb3145e3   movt     r3, #0x51eb
c02c0474  923382e0   umull    r3, r2, r2, r3
c02c0478  a222a0e1   lsr      r2, r2, #5
c02c047c  28208de5   str      r2, [sp, #0x28]
