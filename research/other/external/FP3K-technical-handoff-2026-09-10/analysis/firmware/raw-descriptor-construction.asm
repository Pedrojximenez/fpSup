c0438018  70402de9   push     {r4, r5, r6, lr}
c043801c  0040a0e1   mov      r4, r0
c0438020  0150a0e1   mov      r5, r1
c0438024  0260a0e1   mov      r6, r2
c0438028  4c3200e3   movw     r3, #0x24c
c043802c  bd304ce3   movt     r3, #0xc0bd
c0438030  bc3084e5   str      r3, [r4, #0xbc]
c0438034  0520a0e1   mov      r2, r5
c0438038  0410a0e1   mov      r1, r4
c043803c  0400a0e1   mov      r0, r4
c0438040  680000eb   bl       #0xc04381e8
c0438044  043095e5   ldr      r3, [r5, #4]
c0438048  643093e5   ldr      r3, [r3, #0x64]
c043804c  483084e5   str      r3, [r4, #0x48]
c0438050  043095e5   ldr      r3, [r5, #4]
c0438054  d43093e5   ldr      r3, [r3, #0xd4]
c0438058  4c3084e5   str      r3, [r4, #0x4c]
c043805c  043095e5   ldr      r3, [r5, #4]
c0438060  5c3093e5   ldr      r3, [r3, #0x5c]
c0438064  503084e5   str      r3, [r4, #0x50]
c0438068  043095e5   ldr      r3, [r5, #4]
c043806c  c83093e5   ldr      r3, [r3, #0xc8]
c0438070  543084e5   str      r3, [r4, #0x54]
c0438074  00f020e3   nop      
c0438078  0520a0e1   mov      r2, r5
c043807c  581084e2   add      r1, r4, #0x58
c0438080  0400a0e1   mov      r0, r4
c0438084  770000eb   bl       #0xc0438268
c0438088  043095e5   ldr      r3, [r5, #4]
c043808c  603093e5   ldr      r3, [r3, #0x60]
c0438090  a03084e5   str      r3, [r4, #0xa0]
c0438094  043095e5   ldr      r3, [r5, #4]
c0438098  d03093e5   ldr      r3, [r3, #0xd0]
c043809c  a43084e5   str      r3, [r4, #0xa4]
c04380a0  043095e5   ldr      r3, [r5, #4]
c04380a4  583093e5   ldr      r3, [r3, #0x58]
c04380a8  a83084e5   str      r3, [r4, #0xa8]
c04380ac  043095e5   ldr      r3, [r5, #4]
c04380b0  c43093e5   ldr      r3, [r3, #0xc4]
c04380b4  ac3084e5   str      r3, [r4, #0xac]
c04380b8  00f020e3   nop      
c04380bc  003096e5   ldr      r3, [r6]
c04380c0  04c096e5   ldr      ip, [r6, #4]
c04380c4  b03084e5   str      r3, [r4, #0xb0]
c04380c8  b4c084e5   str      ip, [r4, #0xb4]
c04380cc  003095e5   ldr      r3, [r5]
c04380d0  b83084e5   str      r3, [r4, #0xb8]
c04380d4  0430a0e1   mov      r3, r4
c04380d8  0300a0e1   mov      r0, r3
c04380dc  7080bde8   pop      {r4, r5, r6, pc}
c04380e0  30402de9   push     {r4, r5, lr}
c04380e4  0040a0e1   mov      r4, r0
c04380e8  0150a0e1   mov      r5, r1
c04380ec  030055e3   cmp      r5, #3
c04380f0  0200001a   bne      #0xc0438100
c04380f4  242094e5   ldr      r2, [r4, #0x24]
c04380f8  040000ea   b        #0xc0438110
c04380fc  00f020e3   nop      
c0438100  0510a0e1   mov      r1, r5
c0438104  0400a0e1   mov      r0, r4
c0438108  62ffffeb   bl       #0xc0437e98
c043810c  0020a0e1   mov      r2, r0
c0438110  0200a0e1   mov      r0, r2
c0438114  3080bde8   pop      {r4, r5, pc}
c0438118  30402de9   push     {r4, r5, lr}
c043811c  0050a0e1   mov      r5, r0
c0438120  0140a0e1   mov      r4, r1
c0438124  030054e3   cmp      r4, #3
c0438128  0200001a   bne      #0xc0438138
c043812c  0120a0e3   mov      r2, #1
c0438130  040000ea   b        #0xc0438148
c0438134  00f020e3   nop      
c0438138  0410a0e1   mov      r1, r4
c043813c  0500a0e1   mov      r0, r5
c0438140  64ffffeb   bl       #0xc0437ed8
c0438144  0020a0e1   mov      r2, r0
c0438148  0200a0e1   mov      r0, r2
c043814c  3080bde8   pop      {r4, r5, pc}
c0438150  30402de9   push     {r4, r5, lr}
c0438154  0040a0e1   mov      r4, r0
c0438158  0150a0e1   mov      r5, r1
c043815c  020055e3   cmp      r5, #2
c0438160  0200001a   bne      #0xc0438170
c0438164  242094e5   ldr      r2, [r4, #0x24]
c0438168  040000ea   b        #0xc0438180
c043816c  00f020e3   nop      
c0438170  0510a0e1   mov      r1, r5
c0438174  0400a0e1   mov      r0, r4
c0438178  68ffffeb   bl       #0xc0437f20
c043817c  0020a0e1   mov      r2, r0
c0438180  0200a0e1   mov      r0, r2
c0438184  3080bde8   pop      {r4, r5, pc}
c0438188  30402de9   push     {r4, r5, lr}
c043818c  0050a0e1   mov      r5, r0
c0438190  0140a0e1   mov      r4, r1
c0438194  020054e3   cmp      r4, #2
c0438198  0200001a   bne      #0xc04381a8
c043819c  0120a0e3   mov      r2, #1
c04381a0  040000ea   b        #0xc04381b8
c04381a4  00f020e3   nop      
c04381a8  0410a0e1   mov      r1, r4
c04381ac  0500a0e1   mov      r0, r5
c04381b0  70ffffeb   bl       #0xc0437f78
c04381b4  0020a0e1   mov      r2, r0
c04381b8  0200a0e1   mov      r0, r2
c04381bc  3080bde8   pop      {r4, r5, pc}
c04381c0  30402de9   push     {r4, r5, lr}
c04381c4  0040a0e1   mov      r4, r0
c04381c8  0150a0e1   mov      r5, r1
c04381cc  010015e3   tst      r5, #1
c04381d0  0200000a   beq      #0xc04381e0
c04381d4  0400a0e1   mov      r0, r4
c04381d8  c010a0e3   mov      r1, #0xc0
c04381dc  ae6cefeb   bl       #0xc001349c
c04381e0  3080bde8   pop      {r4, r5, pc}
c04381e4  00f020e3   nop      
