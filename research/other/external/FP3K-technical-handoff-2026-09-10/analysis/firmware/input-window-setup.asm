c0320008  30402de9   push     {r4, r5, lr}
c032000c  0cd04de2   sub      sp, sp, #0xc
c0320010  0040a0e1   mov      r4, r0
c0320014  0150a0e1   mov      r5, r1
c0320018  b43109e3   movw     r3, #0x91b4
c032001c  b5304ce3   movt     r3, #0xc0b5
c0320020  0d20a0e1   mov      r2, sp
c0320024  0b0093e8   ldm      r3, {r0, r1, r3}
c0320028  0b0082e8   stm      r2, {r0, r1, r3}
c032002c  c82094e5   ldr      r2, [r4, #0xc8]
c0320030  012052e2   subs     r2, r2, #1
c0320034  0500003a   blo      #0xc0320050
c0320038  2200000a   beq      #0xc03200c8
c032003c  020052e3   cmp      r2, #2
c0320040  3c00003a   blo      #0xc0320138
c0320044  5900000a   beq      #0xc03201b0
c0320048  760000ea   b        #0xc0320228
c032004c  00f020e3   nop      
c0320050  0510a0e1   mov      r1, r5
c0320054  0400a0e1   mov      r0, r4
c0320058  d0ffffeb   bl       #0xc031ffa0
c032005c  0020a0e1   mov      r2, r0
c0320060  00208de5   str      r2, [sp]
c0320064  003094e5   ldr      r3, [r4]
c0320068  0c2094e5   ldr      r2, [r4, #0xc]
c032006c  003093e5   ldr      r3, [r3]
c0320070  822283e0   add      r2, r3, r2, lsl #5
c0320074  ba20d2e1   ldrh     r2, [r2, #0xa]
c0320078  b420cde1   strh     r2, [sp, #4]
c032007c  003094e5   ldr      r3, [r4]
c0320080  0c2094e5   ldr      r2, [r4, #0xc]
c0320084  003093e5   ldr      r3, [r3]
c0320088  822283e0   add      r2, r3, r2, lsl #5
c032008c  bc20d2e1   ldrh     r2, [r2, #0xc]
c0320090  b620cde1   strh     r2, [sp, #6]
c0320094  003094e5   ldr      r3, [r4]
c0320098  0c2094e5   ldr      r2, [r4, #0xc]
c032009c  003093e5   ldr      r3, [r3]
c03200a0  822283e0   add      r2, r3, r2, lsl #5
c03200a4  be20d2e1   ldrh     r2, [r2, #0xe]
c03200a8  b820cde1   strh     r2, [sp, #8]
c03200ac  003094e5   ldr      r3, [r4]
c03200b0  0c2094e5   ldr      r2, [r4, #0xc]
c03200b4  003093e5   ldr      r3, [r3]
c03200b8  822283e0   add      r2, r3, r2, lsl #5
c03200bc  b021d2e1   ldrh     r2, [r2, #0x10]
c03200c0  ba20cde1   strh     r2, [sp, #0xa]
c03200c4  580000ea   b        #0xc032022c
c03200c8  0510a0e1   mov      r1, r5
c03200cc  0400a0e1   mov      r0, r4
c03200d0  b2ffffeb   bl       #0xc031ffa0
c03200d4  0020a0e1   mov      r2, r0
c03200d8  00208de5   str      r2, [sp]
c03200dc  0020a0e3   mov      r2, #0
c03200e0  b420cde1   strh     r2, [sp, #4]
c03200e4  00c094e5   ldr      ip, [r4]
c03200e8  0c2094e5   ldr      r2, [r4, #0xc]
c03200ec  00c09ce5   ldr      ip, [ip]
c03200f0  82228ce0   add      r2, ip, r2, lsl #5
c03200f4  bc30d2e1   ldrh     r3, [r2, #0xc]
c03200f8  ba20d2e1   ldrh     r2, [r2, #0xa]
c03200fc  022053e0   subs     r2, r3, r2
c0320100  00206242   rsbmi    r2, r2, #0
c0320104  b620cde1   strh     r2, [sp, #6]
c0320108  0020a0e3   mov      r2, #0
c032010c  b820cde1   strh     r2, [sp, #8]
c0320110  00c094e5   ldr      ip, [r4]
c0320114  0c2094e5   ldr      r2, [r4, #0xc]
c0320118  00c09ce5   ldr      ip, [ip]
c032011c  82228ce0   add      r2, ip, r2, lsl #5
c0320120  b031d2e1   ldrh     r3, [r2, #0x10]
c0320124  be20d2e1   ldrh     r2, [r2, #0xe]
c0320128  022053e0   subs     r2, r3, r2
c032012c  00206242   rsbmi    r2, r2, #0
c0320130  ba20cde1   strh     r2, [sp, #0xa]
c0320134  3c0000ea   b        #0xc032022c
c0320138  0510a0e1   mov      r1, r5
c032013c  0400a0e1   mov      r0, r4
c0320140  96ffffeb   bl       #0xc031ffa0
c0320144  0020a0e1   mov      r2, r0
c0320148  00208de5   str      r2, [sp]
c032014c  0020a0e3   mov      r2, #0
c0320150  b420cde1   strh     r2, [sp, #4]
c0320154  00c094e5   ldr      ip, [r4]
c0320158  0c2094e5   ldr      r2, [r4, #0xc]
c032015c  00c09ce5   ldr      ip, [ip]
c0320160  82228ce0   add      r2, ip, r2, lsl #5
c0320164  bc30d2e1   ldrh     r3, [r2, #0xc]
c0320168  ba20d2e1   ldrh     r2, [r2, #0xa]
c032016c  022053e0   subs     r2, r3, r2
c0320170  00206242   rsbmi    r2, r2, #0
c0320174  b620cde1   strh     r2, [sp, #6]
c0320178  003094e5   ldr      r3, [r4]
c032017c  0c2094e5   ldr      r2, [r4, #0xc]
c0320180  003093e5   ldr      r3, [r3]
c0320184  822283e0   add      r2, r3, r2, lsl #5
c0320188  be20d2e1   ldrh     r2, [r2, #0xe]
c032018c  b820cde1   strh     r2, [sp, #8]
c0320190  003094e5   ldr      r3, [r4]
c0320194  0c2094e5   ldr      r2, [r4, #0xc]
c0320198  003093e5   ldr      r3, [r3]
c032019c  822283e0   add      r2, r3, r2, lsl #5
c03201a0  b021d2e1   ldrh     r2, [r2, #0x10]
c03201a4  ba20cde1   strh     r2, [sp, #0xa]
c03201a8  1f0000ea   b        #0xc032022c
c03201ac  00f020e3   nop      
c03201b0  0510a0e1   mov      r1, r5
c03201b4  0400a0e1   mov      r0, r4
c03201b8  78ffffeb   bl       #0xc031ffa0
c03201bc  0020a0e1   mov      r2, r0
c03201c0  00208de5   str      r2, [sp]
c03201c4  003094e5   ldr      r3, [r4]
c03201c8  0c2094e5   ldr      r2, [r4, #0xc]
c03201cc  003093e5   ldr      r3, [r3]
c03201d0  822283e0   add      r2, r3, r2, lsl #5
c03201d4  ba20d2e1   ldrh     r2, [r2, #0xa]
c03201d8  b420cde1   strh     r2, [sp, #4]
c03201dc  003094e5   ldr      r3, [r4]
c03201e0  0c2094e5   ldr      r2, [r4, #0xc]
c03201e4  003093e5   ldr      r3, [r3]
c03201e8  822283e0   add      r2, r3, r2, lsl #5
c03201ec  bc20d2e1   ldrh     r2, [r2, #0xc]
c03201f0  b620cde1   strh     r2, [sp, #6]
c03201f4  0020a0e3   mov      r2, #0
c03201f8  b820cde1   strh     r2, [sp, #8]
c03201fc  00c094e5   ldr      ip, [r4]
c0320200  0c2094e5   ldr      r2, [r4, #0xc]
c0320204  00c09ce5   ldr      ip, [ip]
c0320208  82228ce0   add      r2, ip, r2, lsl #5
c032020c  b031d2e1   ldrh     r3, [r2, #0x10]
c0320210  be20d2e1   ldrh     r2, [r2, #0xe]
c0320214  022053e0   subs     r2, r3, r2
c0320218  00206242   rsbmi    r2, r2, #0
c032021c  ba20cde1   strh     r2, [sp, #0xa]
c0320220  010000ea   b        #0xc032022c
c0320224  00f020e3   nop      
c0320228  00f020e3   nop      
c032022c  0d00a0e1   mov      r0, sp
c0320230  28570cfa   blx      #0xc0635ed8
c0320234  000050e3   cmp      r0, #0
c0320238  0200000a   beq      #0xc0320248
c032023c  0020a0e3   mov      r2, #0
c0320240  070000ea   b        #0xc0320264
c0320244  00f020e3   nop      
c0320248  0d00a0e1   mov      r0, sp
c032024c  7d570cfa   blx      #0xc0636048
c0320250  000050e3   cmp      r0, #0
c0320254  0100000a   beq      #0xc0320260
c0320258  0020a0e3   mov      r2, #0
c032025c  000000ea   b        #0xc0320264
c0320260  0120a0e3   mov      r2, #1
c0320264  0200a0e1   mov      r0, r2
c0320268  0cd08de2   add      sp, sp, #0xc
c032026c  3080bde8   pop      {r4, r5, pc}
