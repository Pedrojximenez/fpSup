c03fa0e0  f04c2de9   push     {r4, r5, r6, r7, sl, fp, lr}
c03fa0e4  49df4de2   sub      sp, sp, #0x124
c03fa0e8  0050a0e1   mov      r5, r0
c03fa0ec  08108de5   str      r1, [sp, #8]
c03fa0f0  02b0a0e1   mov      fp, r2
c03fa0f4  08109be5   ldr      r1, [fp, #8]
c03fa0f8  ff20a0e3   mov      r2, #0xff
c03fa0fc  24008de2   add      r0, sp, #0x24
c03fa100  fc66f0eb   bl       #0xc0013cf8
c03fa104  5c120ae3   movw     r1, #0xa25c
c03fa108  bb104ce3   movt     r1, #0xc0bb
c03fa10c  24008de2   add      r0, sp, #0x24
c03fa110  0affffeb   bl       #0xc03f9d40
c03fa114  0030a0e1   mov      r3, r0
c03fa118  00308de5   str      r3, [sp]
c03fa11c  5c120ae3   movw     r1, #0xa25c
c03fa120  bb104ce3   movt     r1, #0xc0bb
c03fa124  0000a0e3   mov      r0, #0
c03fa128  04ffffeb   bl       #0xc03f9d40
c03fa12c  0030a0e1   mov      r3, r0
c03fa130  0360a0e1   mov      r6, r3
c03fa134  5c120ae3   movw     r1, #0xa25c
c03fa138  bb104ce3   movt     r1, #0xc0bb
c03fa13c  0000a0e3   mov      r0, #0
c03fa140  fefeffeb   bl       #0xc03f9d40
c03fa144  0030a0e1   mov      r3, r0
c03fa148  0370a0e1   mov      r7, r3
c03fa14c  00109de5   ldr      r1, [sp]
c03fa150  0120a0e3   mov      r2, #1
c03fa154  0500a0e1   mov      r0, r5
c03fa158  1effffeb   bl       #0xc03f9dd8
c03fa15c  0030a0e1   mov      r3, r0
c03fa160  03a0a0e1   mov      sl, r3
c03fa164  00005ae3   cmp      sl, #0
c03fa168  0200001a   bne      #0xc03fa178
c03fa16c  0030a0e3   mov      r3, #0
c03fa170  490000ea   b        #0xc03fa29c
c03fa174  00f020e3   nop      
c03fa178  000056e3   cmp      r6, #0
c03fa17c  d030d611   ldrsbne  r3, [r6]
c03fa180  00005313   cmpne    r3, #0
c03fa184  0900001a   bne      #0xc03fa1b0
c03fa188  000057e3   cmp      r7, #0
c03fa18c  d030d711   ldrsbne  r3, [r7]
c03fa190  00005313   cmpne    r3, #0
c03fa194  0500001a   bne      #0xc03fa1b0
c03fa198  003095e5   ldr      r3, [r5]
c03fa19c  64020ae3   movw     r0, #0xa264
c03fa1a0  bb004ce3   movt     r0, #0xc0bb
c03fa1a4  33ff2fe1   blx      r3
c03fa1a8  0130a0e3   mov      r3, #1
c03fa1ac  3a0000ea   b        #0xc03fa29c
c03fa1b0  0040a0e3   mov      r4, #0
c03fa1b4  000056e3   cmp      r6, #0
c03fa1b8  d030d611   ldrsbne  r3, [r6]
c03fa1bc  00005313   cmpne    r3, #0
c03fa1c0  0c00000a   beq      #0xc03fa1f8
c03fa1c4  0610a0e1   mov      r1, r6
c03fa1c8  0500a0e1   mov      r0, r5
c03fa1cc  0120a0e3   mov      r2, #1
c03fa1d0  00ffffeb   bl       #0xc03f9dd8
c03fa1d4  0030a0e1   mov      r3, r0
c03fa1d8  04308de5   str      r3, [sp, #4]
c03fa1dc  04009de5   ldr      r0, [sp, #4]
c03fa1e0  0a10a0e1   mov      r1, sl
c03fa1e4  d35af0eb   bl       #0xc0010d38
c03fa1e8  0030a0e1   mov      r3, r0
c03fa1ec  014083e2   add      r4, r3, #1
c03fa1f0  0a0000ea   b        #0xc03fa220
c03fa1f4  00f020e3   nop      
c03fa1f8  000057e3   cmp      r7, #0
c03fa1fc  d030d711   ldrsbne  r3, [r7]
c03fa200  00005313   cmpne    r3, #0
c03fa204  0500000a   beq      #0xc03fa220
c03fa208  0710a0e1   mov      r1, r7
c03fa20c  0500a0e1   mov      r0, r5
c03fa210  0120a0e3   mov      r2, #1
c03fa214  09ffffeb   bl       #0xc03f9e40
c03fa218  0030a0e1   mov      r3, r0
c03fa21c  0340a0e1   mov      r4, r3
c03fa220  000054e3   cmp      r4, #0
c03fa224  1700000a   beq      #0xc03fa288
c03fa228  1ca08de5   str      sl, [sp, #0x1c]
c03fa22c  20408de5   str      r4, [sp, #0x20]
c03fa230  082901eb   bl       #0xc0444658
c03fa234  0010a0e3   mov      r1, #0
c03fa238  162901eb   bl       #0xc0444698
c03fa23c  0030a0e1   mov      r3, r0
c03fa240  1cc08de2   add      ip, sp, #0x1c
c03fa244  0cc08de5   str      ip, [sp, #0xc]
c03fa248  0310a0e1   mov      r1, r3
c03fa24c  10008de2   add      r0, sp, #0x10
c03fa250  0eaffdeb   bl       #0xc0365e90
c03fa254  00f020e3   nop      
c03fa258  04109be5   ldr      r1, [fp, #4]
c03fa25c  0c008de2   add      r0, sp, #0xc
c03fa260  f8acffeb   bl       #0xc03e5648
c03fa264  003095e5   ldr      r3, [r5]
c03fa268  54020ae3   movw     r0, #0xa254
c03fa26c  bb004ce3   movt     r0, #0xc0bb
c03fa270  33ff2fe1   blx      r3
c03fa274  10008de2   add      r0, sp, #0x10
c03fa278  0210a0e3   mov      r1, #2
c03fa27c  13affdeb   bl       #0xc0365ed0
c03fa280  0130a0e3   mov      r3, #1
c03fa284  040000ea   b        #0xc03fa29c
c03fa288  003095e5   ldr      r3, [r5]
c03fa28c  5e020ae3   movw     r0, #0xa25e
c03fa290  bb004ce3   movt     r0, #0xc0bb
c03fa294  33ff2fe1   blx      r3
c03fa298  0030a0e3   mov      r3, #0
c03fa29c  0300a0e1   mov      r0, r3
c03fa2a0  49df8de2   add      sp, sp, #0x124
c03fa2a4  f08cbde8   pop      {r4, r5, r6, r7, sl, fp, pc}
