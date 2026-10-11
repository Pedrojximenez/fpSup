c038b180  0000a0e3   mov      r0, #0
c038b184  1400c4e5   strb     r0, [r4, #0x14]
c038b188  0000a0e3   mov      r0, #0
c038b18c  1500c4e5   strb     r0, [r4, #0x15]
c038b190  0000a0e3   mov      r0, #0
c038b194  1600c4e5   strb     r0, [r4, #0x16]
c038b198  b8040fe3   movw     r0, #0xf4b8
c038b19c  f1024ce3   movt     r0, #0xc2f1
c038b1a0  5320f2eb   bl       #0xc00132f4
c038b1a4  600d0de3   movw     r0, #0xdd60
c038b1a8  58034ce3   movt     r0, #0xc358
c038b1ac  0c20f2eb   bl       #0xc00131e4
c038b1b0  0400a0e1   mov      r0, r4
c038b1b4  1080bde8   pop      {r4, pc}
c038b1b8  04e02de5   str      lr, [sp, #-4]!
c038b1bc  680d0de3   movw     r0, #0xdd68
c038b1c0  58034ce3   movt     r0, #0xc358
c038b1c4  b11ff2eb   bl       #0xc0013090
c038b1c8  000050e3   cmp      r0, #0
c038b1cc  0900000a   beq      #0xc038b1f8
c038b1d0  800c0de3   movw     r0, #0xdc80
c038b1d4  58034ce3   movt     r0, #0xc358
c038b1d8  1e0000eb   bl       #0xc038b258
c038b1dc  c4040fe3   movw     r0, #0xf4c4
c038b1e0  f1024ce3   movt     r0, #0xc2f1
c038b1e4  4220f2eb   bl       #0xc00132f4
c038b1e8  680d0de3   movw     r0, #0xdd68
c038b1ec  58034ce3   movt     r0, #0xc358
c038b1f0  fb1ff2eb   bl       #0xc00131e4
c038b1f4  00f020e3   nop      
c038b1f8  800c0de3   movw     r0, #0xdc80
c038b1fc  58034ce3   movt     r0, #0xc358
c038b200  04f09de4   pop      {pc}
c038b204  00f020e3   nop      
c038b208  04e02de5   str      lr, [sp, #-4]!
c038b20c  700d0de3   movw     r0, #0xdd70
c038b210  58034ce3   movt     r0, #0xc358
c038b214  9d1ff2eb   bl       #0xc0013090
c038b218  000050e3   cmp      r0, #0
c038b21c  0900000a   beq      #0xc038b248
c038b220  a40c0de3   movw     r0, #0xdca4
c038b224  58034ce3   movt     r0, #0xc358
c038b228  ee1400eb   bl       #0xc03905e8
c038b22c  d0040fe3   movw     r0, #0xf4d0
c038b230  f1024ce3   movt     r0, #0xc2f1
c038b234  2e20f2eb   bl       #0xc00132f4
c038b238  700d0de3   movw     r0, #0xdd70
c038b23c  58034ce3   movt     r0, #0xc358
c038b240  e71ff2eb   bl       #0xc00131e4
c038b244  00f020e3   nop      
c038b248  a40c0de3   movw     r0, #0xdca4
c038b24c  58034ce3   movt     r0, #0xc358
c038b250  04f09de4   pop      {pc}
c038b254  00f020e3   nop      
c038b258  10402de9   push     {r4, lr}
c038b25c  0040a0e1   mov      r4, r0
c038b260  0400a0e1   mov      r0, r4
c038b264  0f10a0e3   mov      r1, #0xf
c038b268  7e7900eb   bl       #0xc03a9868
c038b26c  60120ce3   movw     r1, #0xc260
c038b270  b9104ce3   movt     r1, #0xc0b9
c038b274  101084e5   str      r1, [r4, #0x10]
c038b278  0211a0e3   mov      r1, #0x80000000
c038b27c  141084e5   str      r1, [r4, #0x14]
c038b280  0010a0e3   mov      r1, #0
c038b284  1810c4e5   strb     r1, [r4, #0x18]
c038b288  0010e0e3   mvn      r1, #0
c038b28c  1c1084e5   str      r1, [r4, #0x1c]
c038b290  0010a0e3   mov      r1, #0
c038b294  2010c4e5   strb     r1, [r4, #0x20]
c038b298  0410a0e1   mov      r1, r4
c038b29c  0100a0e1   mov      r0, r1
c038b2a0  1080bde8   pop      {r4, pc}
c038b2a4  00f020e3   nop      
c038b2a8  30402de9   push     {r4, r5, lr}
c038b2ac  0040a0e1   mov      r4, r0
c038b2b0  0150a0e1   mov      r5, r1
c038b2b4  0400a0e1   mov      r0, r4
c038b2b8  0010a0e3   mov      r1, #0
c038b2bc  897900eb   bl       #0xc03a98e8
c038b2c0  010015e3   tst      r5, #1
c038b2c4  0300000a   beq      #0xc038b2d8
c038b2c8  0400a0e1   mov      r0, r4
c038b2cc  2410a0e3   mov      r1, #0x24
c038b2d0  7120f2eb   bl       #0xc001349c
c038b2d4  00f020e3   nop      
c038b2d8  3080bde8   pop      {r4, r5, pc}
c038b2dc  00f020e3   nop      
c038b2e0  70402de9   push     {r4, r5, r6, lr}
c038b2e4  0040a0e1   mov      r4, r0
c038b2e8  0150a0e1   mov      r5, r1
c038b2ec  0260a0e1   mov      r6, r2
c038b2f0  000094e5   ldr      r0, [r4]
c038b2f4  0110a0e3   mov      r1, #1
c038b2f8  f47700eb   bl       #0xc03a92d0
c038b2fc  1905feeb   bl       #0xc030c768
c038b300  ca05feeb   bl       #0xc030ca30
c038b304  020050e3   cmp      r0, #2
c038b308  0200000a   beq      #0xc038b318
c038b30c  0c3094e5   ldr      r3, [r4, #0xc]
c038b310  0b0000ea   b        #0xc038b344
c038b314  00f020e3   nop      
c038b318  0400a0e1   mov      r0, r4
c038b31c  370500eb   bl       #0xc038c800
c038b320  000050e3   cmp      r0, #0
c038b324  0100000a   beq      #0xc038b330
c038b328  0c3094e5   ldr      r3, [r4, #0xc]
c038b32c  040000ea   b        #0xc038b344
c038b330  0610a0e1   mov      r1, r6
c038b334  0500a0e1   mov      r0, r5
c038b338  0f20a0e3   mov      r2, #0xf
c038b33c  d72f00eb   bl       #0xc03972a0
c038b340  0030a0e1   mov      r3, r0
c038b344  0300a0e1   mov      r0, r3
c038b348  7080bde8   pop      {r4, r5, r6, pc}
c038b34c  00f020e3   nop      
c038b350  f0412de9   push     {r4, r5, r6, r7, r8, lr}
c038b354  10d04de2   sub      sp, sp, #0x10
c038b358  0040a0e1   mov      r4, r0
c038b35c  0160a0e1   mov      r6, r1
c038b360  0250a0e1   mov      r5, r2
c038b364  000094e5   ldr      r0, [r4]
c038b368  0110a0e3   mov      r1, #1
c038b36c  df7700eb   bl       #0xc03a92f0
c038b370  923af2eb   bl       #0xc0019dc0
c038b374  0080a0e3   mov      r8, #0
c038b378  08c0a0e1   mov      ip, r8
c038b37c  023000e3   movw     r3, #2
c038b380  0870a0e1   mov      r7, r8
c038b384  863041e3   movt     r3, #0x1086
c038b388  88118de8   stm      sp, {r3, r7, r8, ip}
c038b38c  0130a0e3   mov      r3, #1
c038b390  0410a0e3   mov      r1, #4
c038b394  0820a0e1   mov      r2, r8
c038b398  2a3bf2eb   bl       #0xc001a048
c038b39c  040094e5   ldr      r0, [r4, #4]
c038b3a0  0110a0e3   mov      r1, #1
c038b3a4  b34600eb   bl       #0xc039ce78
c038b3a8  000050e3   cmp      r0, #0
c038b3ac  0100001a   bne      #0xc038b3b8
c038b3b0  0c3094e5   ldr      r3, [r4, #0xc]
c038b3b4  0f0000ea   b        #0xc038b3f8
c038b3b8  040094e5   ldr      r0, [r4, #4]
c038b3bc  0020a0e3   mov      r2, #0
c038b3c0  0210a0e1   mov      r1, r2
c038b3c4  213b00eb   bl       #0xc039a050
c038b3c8  b0010ce3   movw     r0, #0xc1b0
c038b3cc  b9004ce3   movt     r0, #0xc0b9
c038b3d0  007090e5   ldr      r7, [r0]
c038b3d4  080094e5   ldr      r0, [r4, #8]
c038b3d8  226e00eb   bl       #0xc03a6c68
c038b3dc  0030a0e3   mov      r3, #0
c038b3e0  0010a0e1   mov      r1, r0
c038b3e4  88008de8   stm      sp, {r3, r7}
c038b3e8  0c2094e5   ldr      r2, [r4, #0xc]
c038b3ec  0500a0e1   mov      r0, r5
c038b3f0  b22d00eb   bl       #0xc0396ac0
c038b3f4  0c3094e5   ldr      r3, [r4, #0xc]
c038b3f8  0300a0e1   mov      r0, r3
c038b3fc  10d08de2   add      sp, sp, #0x10
c038b400  f081bde8   pop      {r4, r5, r6, r7, r8, pc}
c038b404  00f020e3   nop      
c038b408  f0402de9   push     {r4, r5, r6, r7, lr}
c038b40c  0040a0e1   mov      r4, r0
c038b410  0160a0e1   mov      r6, r1
c038b414  0270a0e1   mov      r7, r2
c038b418  0f50a0e3   mov      r5, #0xf
c038b41c  040094e5   ldr      r0, [r4, #4]
c038b420  0010a0e3   mov      r1, #0
c038b424  c33d00eb   bl       #0xc039ab38
c038b428  000050e3   cmp      r0, #0
c038b42c  0300000a   beq      #0xc038b440
c038b430  0130a0e3   mov      r3, #1
c038b434  1830c4e5   strb     r3, [r4, #0x18]
c038b438  040000ea   b        #0xc038b450
c038b43c  00f020e3   nop      
c038b440  000094e5   ldr      r0, [r4]
c038b444  0210a0e3   mov      r1, #2
c038b448  a07700eb   bl       #0xc03a92d0
c038b44c  00f020e3   nop      
c038b450  0530a0e1   mov      r3, r5
c038b454  0300a0e1   mov      r0, r3
c038b458  f080bde8   pop      {r4, r5, r6, r7, pc}
c038b45c  00f020e3   nop      
c038b460  70402de9   push     {r4, r5, r6, lr}
c038b464  0040a0e1   mov      r4, r0
c038b468  0150a0e1   mov      r5, r1
c038b46c  0260a0e1   mov      r6, r2
c038b470  000094e5   ldr      r0, [r4]
c038b474  0210a0e3   mov      r1, #2
c038b478  9c7700eb   bl       #0xc03a92f0
c038b47c  0c3094e5   ldr      r3, [r4, #0xc]
c038b480  0300a0e1   mov      r0, r3
c038b484  7080bde8   pop      {r4, r5, r6, pc}
c038b488  70402de9   push     {r4, r5, r6, lr}
c038b48c  0040a0e1   mov      r4, r0
c038b490  0150a0e1   mov      r5, r1
c038b494  0260a0e1   mov      r6, r2
c038b498  183095e5   ldr      r3, [r5, #0x18]
c038b49c  000094e5   ldr      r0, [r4]
c038b4a0  020053e3   cmp      r3, #2
c038b4a4  0110a003   moveq    r1, #1
c038b4a8  0010a013   movne    r1, #0
c038b4ac  ab7700eb   bl       #0xc03a9360
c038b4b0  0400a0e1   mov      r0, r4
c038b4b4  d10400eb   bl       #0xc038c800
c038b4b8  000050e3   cmp      r0, #0
c038b4bc  0100000a   beq      #0xc038b4c8
c038b4c0  0c3094e5   ldr      r3, [r4, #0xc]
c038b4c4  050000ea   b        #0xc038b4e0
c038b4c8  0c3094e5   ldr      r3, [r4, #0xc]
c038b4cc  0620a0e3   mov      r2, #6
c038b4d0  0500a0e1   mov      r0, r5
c038b4d4  0610a0e1   mov      r1, r6
c038b4d8  da2f00eb   bl       #0xc0397448
c038b4dc  0030a0e1   mov      r3, r0
c038b4e0  0300a0e1   mov      r0, r3
c038b4e4  7080bde8   pop      {r4, r5, r6, pc}
c038b4e8  f0452de9   push     {r4, r5, r6, r7, r8, sl, lr}
c038b4ec  a0d04de2   sub      sp, sp, #0xa0
c038b4f0  0040a0e1   mov      r4, r0
c038b4f4  0150a0e1   mov      r5, r1
c038b4f8  0260a0e1   mov      r6, r2
c038b4fc  183095e5   ldr      r3, [r5, #0x18]
c038b500  000094e5   ldr      r0, [r4]
c038b504  020053e3   cmp      r3, #2
c038b508  0110a003   moveq    r1, #1
c038b50c  0010a013   movne    r1, #0
c038b510  9e7700eb   bl       #0xc03a9390
c038b514  040094e5   ldr      r0, [r4, #4]
c038b518  0210a0e3   mov      r1, #2
c038b51c  554600eb   bl       #0xc039ce78
c038b520  000050e3   cmp      r0, #0
c038b524  0100001a   bne      #0xc038b530
c038b528  0c3094e5   ldr      r3, [r4, #0xc]
c038b52c  330000ea   b        #0xc038b600
c038b530  000094e5   ldr      r0, [r4]
c038b534  757700eb   bl       #0xc03a9310
c038b538  000050e3   cmp      r0, #0
c038b53c  1d00000a   beq      #0xc038b5b8
c038b540  0a7900eb   bl       #0xc03a9970
c038b544  3d7f00eb   bl       #0xc03ab240
c038b548  d831d0e5   ldrb     r3, [r0, #0x1d8]
c038b54c  000053e3   cmp      r3, #0
c038b550  1400001a   bne      #0xc038b5a8
c038b554  040094e5   ldr      r0, [r4, #4]
c038b558  0020a0e3   mov      r2, #0
c038b55c  0210a0e1   mov      r1, r2
c038b560  ba3a00eb   bl       #0xc039a050
c038b564  db30f2eb   bl       #0xc00178d8
c038b568  5631f2eb   bl       #0xc0017ac8
c038b56c  c03080e2   add      r3, r0, #0xc0
c038b570  08c08de2   add      ip, sp, #8
c038b574  567f80e2   add      r7, r0, #0x158
c038b578  04a093e4   ldr      sl, [r3], #4
c038b57c  030057e1   cmp      r7, r3
c038b580  04a08ce4   str      sl, [ip], #4
c038b584  fbffff1a   bne      #0xc038b578
c038b588  0030a0e3   mov      r3, #0
c038b58c  08308de5   str      r3, [sp, #8]
c038b590  d030f2eb   bl       #0xc00178d8
c038b594  08108de2   add      r1, sp, #8
c038b598  e031f2eb   bl       #0xc0017d20
c038b59c  040094e5   ldr      r0, [r4, #4]
c038b5a0  0210a0e3   mov      r1, #2
c038b5a4  814000eb   bl       #0xc039b7b0
c038b5a8  040094e5   ldr      r0, [r4, #4]
c038b5ac  214600eb   bl       #0xc039ce38
c038b5b0  0c3094e5   ldr      r3, [r4, #0xc]
c038b5b4  110000ea   b        #0xc038b600
c038b5b8  040094e5   ldr      r0, [r4, #4]
c038b5bc  0020a0e3   mov      r2, #0
c038b5c0  0210a0e1   mov      r1, r2
c038b5c4  a13a00eb   bl       #0xc039a050
c038b5c8  b4010ce3   movw     r0, #0xc1b4
c038b5cc  b9004ce3   movt     r0, #0xc0b9
c038b5d0  007090e5   ldr      r7, [r0]
c038b5d4  080094e5   ldr      r0, [r4, #8]
c038b5d8  a26d00eb   bl       #0xc03a6c68
c038b5dc  0030a0e3   mov      r3, #0
c038b5e0  88008de8   stm      sp, {r3, r7}
c038b5e4  0c2094e5   ldr      r2, [r4, #0xc]
c038b5e8  0010a0e1   mov      r1, r0
c038b5ec  0600a0e1   mov      r0, r6
c038b5f0  322d00eb   bl       #0xc0396ac0
c038b5f4  040094e5   ldr      r0, [r4, #4]
c038b5f8  0e4600eb   bl       #0xc039ce38
c038b5fc  0c3094e5   ldr      r3, [r4, #0xc]
c038b600  0300a0e1   mov      r0, r3
c038b604  a0d08de2   add      sp, sp, #0xa0
c038b608  f085bde8   pop      {r4, r5, r6, r7, r8, sl, pc}
c038b60c  00f020e3   nop      
c038b610  70402de9   push     {r4, r5, r6, lr}
c038b614  0060a0e1   mov      r6, r0
c038b618  0140a0e1   mov      r4, r1
c038b61c  0250a0e1   mov      r5, r2
c038b620  003100eb   bl       #0xc0397a28
c038b624  000050e3   cmp      r0, #0
c038b628  0000000a   beq      #0xc038b630
c038b62c  e73000eb   bl       #0xc03979d0
c038b630  0510a0e1   mov      r1, r5
c038b634  0400a0e1   mov      r0, r4
c038b638  0f30a0e3   mov      r3, #0xf
c038b63c  0620a0e3   mov      r2, #6
c038b640  e82f00eb   bl       #0xc03975e8
c038b644  0030a0e1   mov      r3, r0
c038b648  0300a0e1   mov      r0, r3
c038b64c  7080bde8   pop      {r4, r5, r6, pc}
c038b650  70402de9   push     {r4, r5, r6, lr}
c038b654  0040a0e1   mov      r4, r0
c038b658  0150a0e1   mov      r5, r1
c038b65c  0260a0e1   mov      r6, r2
c038b660  0500a0e1   mov      r0, r5
c038b664  0110a0e3   mov      r1, #1
c038b668  383000eb   bl       #0xc0397750
c038b66c  0c3094e5   ldr      r3, [r4, #0xc]
c038b670  0300a0e1   mov      r0, r3
c038b674  7080bde8   pop      {r4, r5, r6, pc}
c038b678  30002de9   push     {r4, r5}
c038b67c  00c0a0e1   mov      ip, r0
c038b680  0140a0e1   mov      r4, r1
c038b684  0250a0e1   mov      r5, r2
c038b688  0c309ce5   ldr      r3, [ip, #0xc]
c038b68c  0300a0e1   mov      r0, r3
c038b690  3000bde8   pop      {r4, r5}
c038b694  1eff2fe1   bx       lr
c038b698  30002de9   push     {r4, r5}
c038b69c  00c0a0e1   mov      ip, r0
c038b6a0  0140a0e1   mov      r4, r1
c038b6a4  0250a0e1   mov      r5, r2
c038b6a8  0c309ce5   ldr      r3, [ip, #0xc]
c038b6ac  0300a0e1   mov      r0, r3
c038b6b0  3000bde8   pop      {r4, r5}
c038b6b4  1eff2fe1   bx       lr
c038b6b8  30002de9   push     {r4, r5}
c038b6bc  00c0a0e1   mov      ip, r0
c038b6c0  0140a0e1   mov      r4, r1
c038b6c4  0250a0e1   mov      r5, r2
c038b6c8  0c309ce5   ldr      r3, [ip, #0xc]
c038b6cc  0300a0e1   mov      r0, r3
c038b6d0  3000bde8   pop      {r4, r5}
c038b6d4  1eff2fe1   bx       lr
c038b6d8  70402de9   push     {r4, r5, r6, lr}
c038b6dc  0040a0e1   mov      r4, r0
c038b6e0  0150a0e1   mov      r5, r1
c038b6e4  0260a0e1   mov      r6, r2
c038b6e8  800d0de3   movw     r0, #0xdd80
c038b6ec  58034ce3   movt     r0, #0xc358
c038b6f0  661ef2eb   bl       #0xc0013090
c038b6f4  000050e3   cmp      r0, #0
c038b6f8  0600000a   beq      #0xc038b718
c038b6fc  880d0de3   movw     r0, #0xdd88
c038b700  58034ce3   movt     r0, #0xc358
c038b704  5b0400eb   bl       #0xc038c878
c038b708  800d0de3   movw     r0, #0xdd80
c038b70c  58034ce3   movt     r0, #0xc358
c038b710  b31ef2eb   bl       #0xc00131e4
c038b714  00f020e3   nop      
c038b718  880d0de3   movw     r0, #0xdd88
c038b71c  58034ce3   movt     r0, #0xc358
c038b720  84edffeb   bl       #0xc0386d38
c038b724  0c3094e5   ldr      r3, [r4, #0xc]
c038b728  0300a0e1   mov      r0, r3
c038b72c  7080bde8   pop      {r4, r5, r6, pc}
c038b730  30002de9   push     {r4, r5}
c038b734  00c0a0e1   mov      ip, r0
c038b738  0140a0e1   mov      r4, r1
c038b73c  0250a0e1   mov      r5, r2
c038b740  0c309ce5   ldr      r3, [ip, #0xc]
c038b744  0300a0e1   mov      r0, r3
c038b748  3000bde8   pop      {r4, r5}
c038b74c  1eff2fe1   bx       lr
c038b750  30002de9   push     {r4, r5}
c038b754  00c0a0e1   mov      ip, r0
c038b758  0140a0e1   mov      r4, r1
c038b75c  0250a0e1   mov      r5, r2
c038b760  0c309ce5   ldr      r3, [ip, #0xc]
c038b764  0300a0e1   mov      r0, r3
c038b768  3000bde8   pop      {r4, r5}
c038b76c  1eff2fe1   bx       lr
c038b770  30002de9   push     {r4, r5}
c038b774  00c0a0e1   mov      ip, r0
c038b778  0140a0e1   mov      r4, r1
c038b77c  0250a0e1   mov      r5, r2
c038b780  0c309ce5   ldr      r3, [ip, #0xc]
c038b784  0300a0e1   mov      r0, r3
c038b788  3000bde8   pop      {r4, r5}
c038b78c  1eff2fe1   bx       lr
c038b790  70402de9   push     {r4, r5, r6, lr}
c038b794  10d04de2   sub      sp, sp, #0x10
c038b798  0040a0e1   mov      r4, r0
c038b79c  0150a0e1   mov      r5, r1
c038b7a0  0260a0e1   mov      r6, r2
c038b7a4  8539f2eb   bl       #0xc0019dc0
c038b7a8  00c0a0e3   mov      ip, #0
c038b7ac  0cc08de5   str      ip, [sp, #0xc]
c038b7b0  0c10a0e1   mov      r1, ip
c038b7b4  02108de9   stmib    sp, {r1, ip}
c038b7b8  01c100e3   movw     ip, #0x101
c038b7bc  0030a0e3   mov      r3, #0
c038b7c0  11c041e3   movt     ip, #0x1011
c038b7c4  0320a0e1   mov      r2, r3
c038b7c8  0410a0e3   mov      r1, #4
c038b7cc  00c08de5   str      ip, [sp]
c038b7d0  1c3af2eb   bl       #0xc001a048
c038b7d4  6431d5e5   ldrb     r3, [r5, #0x164]
c038b7d8  000053e3   cmp      r3, #0
c038b7dc  0300001a   bne      #0xc038b7f0
c038b7e0  040094e5   ldr      r0, [r4, #4]
c038b7e4  0020a0e3   mov      r2, #0
c038b7e8  0210a0e1   mov      r1, r2
c038b7ec  173a00eb   bl       #0xc039a050
c038b7f0  0400a0e1   mov      r0, r4
c038b7f4  010400eb   bl       #0xc038c800
c038b7f8  000050e3   cmp      r0, #0
c038b7fc  0100000a   beq      #0xc038b808
c038b800  0c3094e5   ldr      r3, [r4, #0xc]
c038b804  0f0000ea   b        #0xc038b848
c038b808  143094e5   ldr      r3, [r4, #0x14]
c038b80c  020153e3   cmp      r3, #0x80000000
c038b810  0400001a   bne      #0xc038b828
c038b814  000094e5   ldr      r0, [r4]
c038b818  0310a0e3   mov      r1, #3
c038b81c  ab7600eb   bl       #0xc03a92d0
c038b820  0c3094e5   ldr      r3, [r4, #0xc]
c038b824  070000ea   b        #0xc038b848
c038b828  b8010ce3   movw     r0, #0xc1b8
c038b82c  b9004ce3   movt     r0, #0xc0b9
c038b830  406800eb   bl       #0xc03a5938
c038b834  0620a0e1   mov      r2, r6
c038b838  0010e0e3   mvn      r1, #0
c038b83c  0400a0e1   mov      r0, r4
c038b840  de0200eb   bl       #0xc038c3c0
c038b844  0030a0e1   mov      r3, r0
c038b848  0300a0e1   mov      r0, r3
c038b84c  10d08de2   add      sp, sp, #0x10
c038b850  7080bde8   pop      {r4, r5, r6, pc}
c038b854  00f020e3   nop      
c038b858  f0442de9   push     {r4, r5, r6, r7, sl, lr}
c038b85c  0040a0e1   mov      r4, r0
c038b860  0170a0e1   mov      r7, r1
c038b864  02a0a0e1   mov      sl, r2
c038b868  407800eb   bl       #0xc03a9970
c038b86c  0010a0e1   mov      r1, r0
c038b870  0150a0e1   mov      r5, r1
c038b874  0500a0e1   mov      r0, r5
c038b878  787e00eb   bl       #0xc03ab260
c038b87c  0010a0e1   mov      r1, r0
c038b880  bc6191e5   ldr      r6, [r1, #0x1bc]
c038b884  0500a0e1   mov      r0, r5
c038b888  847800eb   bl       #0xc03a9aa0
c038b88c  0500a0e1   mov      r0, r5
c038b890  6a7e00eb   bl       #0xc03ab240
c038b894  bc3190e5   ldr      r3, [r0, #0x1bc]
c038b898  030056e1   cmp      r6, r3
c038b89c  1500000a   beq      #0xc038b8f8
c038b8a0  000094e5   ldr      r0, [r4]
c038b8a4  0110a0e3   mov      r1, #1
c038b8a8  807600eb   bl       #0xc03a92b0
c038b8ac  000050e3   cmp      r0, #0
c038b8b0  1000001a   bne      #0xc038b8f8
c038b8b4  000094e5   ldr      r0, [r4]
c038b8b8  947600eb   bl       #0xc03a9310
c038b8bc  000050e3   cmp      r0, #0
c038b8c0  0c00001a   bne      #0xc038b8f8
c038b8c4  676800eb   bl       #0xc03a5a68
c038b8c8  146900eb   bl       #0xc03a5d20
c038b8cc  000050e3   cmp      r0, #0
c038b8d0  0800001a   bne      #0xc038b8f8
c038b8d4  040094e5   ldr      r0, [r4, #4]
c038b8d8  403a00eb   bl       #0xc039a1e0
c038b8dc  000050e3   cmp      r0, #0
c038b8e0  0400001a   bne      #0xc038b8f8
c038b8e4  040094e5   ldr      r0, [r4, #4]
c038b8e8  0210a0e3   mov      r1, #2
c038b8ec  0020a0e3   mov      r2, #0
c038b8f0  503a00eb   bl       #0xc039a238
c038b8f4  00f020e3   nop      
c038b8f8  0c3094e5   ldr      r3, [r4, #0xc]
c038b8fc  0300a0e1   mov      r0, r3
c038b900  f084bde8   pop      {r4, r5, r6, r7, sl, pc}
c038b904  00f020e3   nop      
c038b908  70402de9   push     {r4, r5, r6, lr}
c038b90c  5bdf4de2   sub      sp, sp, #0x16c
c038b910  0040a0e1   mov      r4, r0
c038b914  0150a0e1   mov      r5, r1
c038b918  0260a0e1   mov      r6, r2
c038b91c  0d00a0e1   mov      r0, sp
c038b920  5b2fa0e3   mov      r2, #0x16c
c038b924  0010a0e3   mov      r1, #0
c038b928  ca25f2eb   bl       #0xc0015058
c038b92c  0400a0e1   mov      r0, r4
c038b930  a00300eb   bl       #0xc038c7b8
c038b934  0030a0e1   mov      r3, r0
c038b938  9c308de5   str      r3, [sp, #0x9c]
c038b93c  1cc094e5   ldr      ip, [r4, #0x1c]
c038b940  9c309de5   ldr      r3, [sp, #0x9c]
c038b944  0c0053e1   cmp      r3, ip
c038b948  0600000a   beq      #0xc038b968
c038b94c  0d30a0e1   mov      r3, sp
c038b950  0120a0e3   mov      r2, #1
c038b954  1210a0e3   mov      r1, #0x12
c038b958  0000a0e3   mov      r0, #0
c038b95c  472d00eb   bl       #0xc0396e80
c038b960  9c309de5   ldr      r3, [sp, #0x9c]
c038b964  1c3084e5   str      r3, [r4, #0x1c]
c038b968  f03095e5   ldr      r3, [r5, #0xf0]
c038b96c  030053e3   cmp      r3, #3
c038b970  0000001a   bne      #0xc038b978
c038b974  153000eb   bl       #0xc03979d0
c038b978  0c3094e5   ldr      r3, [r4, #0xc]
c038b97c  0300a0e1   mov      r0, r3
c038b980  5bdf8de2   add      sp, sp, #0x16c
c038b984  7080bde8   pop      {r4, r5, r6, pc}
c038b988  f0452de9   push     {r4, r5, r6, r7, r8, sl, lr}
c038b98c  83df4de2   sub      sp, sp, #0x20c
c038b990  0040a0e1   mov      r4, r0
c038b994  0150a0e1   mov      r5, r1
c038b998  0270a0e1   mov      r7, r2
c038b99c  ba30d5e5   ldrb     r3, [r5, #0xba]
c038b9a0  000053e3   cmp      r3, #0
c038b9a4  1800000a   beq      #0xc038ba0c
c038b9a8  040094e5   ldr      r0, [r4, #4]
c038b9ac  1c10d5e5   ldrb     r1, [r5, #0x1c]
c038b9b0  563c00eb   bl       #0xc039ab10
c038b9b4  c72ff2eb   bl       #0xc00178d8
c038b9b8  4230f2eb   bl       #0xc0017ac8
c038b9bc  c03080e2   add      r3, r0, #0xc0
c038b9c0  08c08de2   add      ip, sp, #8
c038b9c4  566f80e2   add      r6, r0, #0x158
c038b9c8  04a093e4   ldr      sl, [r3], #4
c038b9cc  030056e1   cmp      r6, r3
c038b9d0  04a08ce4   str      sl, [ip], #4
c038b9d4  fbffff1a   bne      #0xc038b9c8
c038b9d8  1cc0d5e5   ldrb     ip, [r5, #0x1c]
c038b9dc  0230a0e3   mov      r3, #2
c038b9e0  00005ce3   cmp      ip, #0
c038b9e4  0000000a   beq      #0xc038b9ec
c038b9e8  0130a0e3   mov      r3, #1
c038b9ec  08308de5   str      r3, [sp, #8]
c038b9f0  281085e2   add      r1, r5, #0x28
c038b9f4  0c008de2   add      r0, sp, #0xc
c038b9f8  9020a0e3   mov      r2, #0x90
c038b9fc  c225f2eb   bl       #0xc001510c
c038ba00  b42ff2eb   bl       #0xc00178d8
c038ba04  08108de2   add      r1, sp, #8
c038ba08  c430f2eb   bl       #0xc0017d20
c038ba0c  0c6094e5   ldr      r6, [r4, #0xc]
c038ba10  b830d5e5   ldrb     r3, [r5, #0xb8]
c038ba14  000053e3   cmp      r3, #0
c038ba18  0200001a   bne      #0xc038ba28
c038ba1c  0630a0e1   mov      r3, r6
c038ba20  360000ea   b        #0xc038bb00
c038ba24  00f020e3   nop      
c038ba28  040094e5   ldr      r0, [r4, #4]
c038ba2c  0020a0e3   mov      r2, #0
c038ba30  0210a0e1   mov      r1, r2
c038ba34  853900eb   bl       #0xc039a050
c038ba38  040094e5   ldr      r0, [r4, #4]
c038ba3c  fd3a00eb   bl       #0xc039a638
c038ba40  000050e3   cmp      r0, #0
c038ba44  0300000a   beq      #0xc038ba58
c038ba48  aa2f00eb   bl       #0xc03978f8
c038ba4c  040094e5   ldr      r0, [r4, #4]
c038ba50  0010a0e3   mov      r1, #0
c038ba54  ff3a00eb   bl       #0xc039a658
c038ba58  a0008de2   add      r0, sp, #0xa0
c038ba5c  5b2fa0e3   mov      r2, #0x16c
c038ba60  0010a0e3   mov      r1, #0
c038ba64  7b25f2eb   bl       #0xc0015058
c038ba68  040094e5   ldr      r0, [r4, #4]
c038ba6c  2d3c00eb   bl       #0xc039ab28
c038ba70  0030a0e1   mov      r3, r0
c038ba74  a830cde5   strb     r3, [sp, #0xa8]
c038ba78  c4f3ffeb   bl       #0xc0388990
c038ba7c  0010a0e3   mov      r1, #0
c038ba80  507700eb   bl       #0xc03a97c8
c038ba84  0030a0e1   mov      r3, r0
c038ba88  08328de5   str      r3, [sp, #0x208]
c038ba8c  a0308de2   add      r3, sp, #0xa0
c038ba90  0010a0e3   mov      r1, #0
c038ba94  0120a0e3   mov      r2, #1
c038ba98  0100a0e1   mov      r0, r1
c038ba9c  f72c00eb   bl       #0xc0396e80
c038baa0  c0010ce3   movw     r0, #0xc1c0
c038baa4  b9004ce3   movt     r0, #0xc0b9
c038baa8  00a090e5   ldr      sl, [r0]
c038baac  080094e5   ldr      r0, [r4, #8]
c038bab0  6c6c00eb   bl       #0xc03a6c68
c038bab4  0030a0e3   mov      r3, #0
c038bab8  08048de8   stm      sp, {r3, sl}
c038babc  0c2094e5   ldr      r2, [r4, #0xc]
c038bac0  0010a0e1   mov      r1, r0
c038bac4  0700a0e1   mov      r0, r7
c038bac8  fc2b00eb   bl       #0xc0396ac0
c038bacc  000094e5   ldr      r0, [r4]
c038bad0  0210a0e3   mov      r1, #2
c038bad4  f57500eb   bl       #0xc03a92b0
c038bad8  000050e3   cmp      r0, #0
c038badc  0600000a   beq      #0xc038bafc
c038bae0  040094e5   ldr      r0, [r4, #4]
c038bae4  0010a0e3   mov      r1, #0
c038bae8  123c00eb   bl       #0xc039ab38
c038baec  000050e3   cmp      r0, #0
c038baf0  0100000a   beq      #0xc038bafc
c038baf4  0130a0e3   mov      r3, #1
c038baf8  1830c4e5   strb     r3, [r4, #0x18]
c038bafc  0630a0e1   mov      r3, r6
c038bb00  0300a0e1   mov      r0, r3
c038bb04  83df8de2   add      sp, sp, #0x20c
c038bb08  f085bde8   pop      {r4, r5, r6, r7, r8, sl, pc}
c038bb0c  00f020e3   nop      
c038bb10  30002de9   push     {r4, r5}
c038bb14  00c0a0e1   mov      ip, r0
c038bb18  0140a0e1   mov      r4, r1
c038bb1c  0250a0e1   mov      r5, r2
c038bb20  0c309ce5   ldr      r3, [ip, #0xc]
c038bb24  0300a0e1   mov      r0, r3
c038bb28  3000bde8   pop      {r4, r5}
c038bb2c  1eff2fe1   bx       lr
c038bb30  f0482de9   push     {r4, r5, r6, r7, fp, lr}
c038bb34  10d04de2   sub      sp, sp, #0x10
c038bb38  0040a0e1   mov      r4, r0
c038bb3c  0150a0e1   mov      r5, r1
c038bb40  0270a0e1   mov      r7, r2
c038bb44  0c6094e5   ldr      r6, [r4, #0xc]
c038bb48  9c38f2eb   bl       #0xc0019dc0
c038bb4c  0030a0e3   mov      r3, #0
c038bb50  03c0a0e1   mov      ip, r3
c038bb54  011400e3   movw     r1, #0x401
c038bb58  0320a0e1   mov      r2, r3
c038bb5c  111041e3   movt     r1, #0x1011
c038bb60  0e108de8   stm      sp, {r1, r2, r3, ip}
c038bb64  0410a0e3   mov      r1, #4
c038bb68  3639f2eb   bl       #0xc001a048
c038bb6c  d430d5e5   ldrb     r3, [r5, #0xd4]
c038bb70  000053e3   cmp      r3, #0
c038bb74  1800000a   beq      #0xc038bbdc
c038bb78  143094e5   ldr      r3, [r4, #0x14]
c038bb7c  020153e3   cmp      r3, #0x80000000
c038bb80  0c00001a   bne      #0xc038bbb8
c038bb84  000094e5   ldr      r0, [r4]
c038bb88  0310a0e3   mov      r1, #3
c038bb8c  cf7500eb   bl       #0xc03a92d0
c038bb90  080094e5   ldr      r0, [r4, #8]
c038bb94  336c00eb   bl       #0xc03a6c68
c038bb98  0c1094e5   ldr      r1, [r4, #0xc]
c038bb9c  0020a0e1   mov      r2, r0
c038bba0  040094e5   ldr      r0, [r4, #4]
c038bba4  c83085e2   add      r3, r5, #0xc8
c038bba8  1e3d00eb   bl       #0xc039b028
c038bbac  0630a0e1   mov      r3, r6
c038bbb0  230000ea   b        #0xc038bc44
c038bbb4  00f020e3   nop      
c038bbb8  c4010ce3   movw     r0, #0xc1c4
c038bbbc  b9004ce3   movt     r0, #0xc0b9
c038bbc0  5c6700eb   bl       #0xc03a5938
c038bbc4  0720a0e1   mov      r2, r7
c038bbc8  0010e0e3   mvn      r1, #0
c038bbcc  0400a0e1   mov      r0, r4
c038bbd0  fa0100eb   bl       #0xc038c3c0
c038bbd4  0030a0e1   mov      r3, r0
c038bbd8  0360a0e1   mov      r6, r3
c038bbdc  080094e5   ldr      r0, [r4, #8]
c038bbe0  206c00eb   bl       #0xc03a6c68
c038bbe4  0c1094e5   ldr      r1, [r4, #0xc]
c038bbe8  0020a0e1   mov      r2, r0
c038bbec  040094e5   ldr      r0, [r4, #4]
c038bbf0  c83085e2   add      r3, r5, #0xc8
c038bbf4  0b3d00eb   bl       #0xc039b028
c038bbf8  cc30d5e5   ldrb     r3, [r5, #0xcc]
c038bbfc  000053e3   cmp      r3, #0
c038bc00  cb30d505   ldrbeq   r3, [r5, #0xcb]
c038bc04  00005303   cmpeq    r3, #0
c038bc08  0c00000a   beq      #0xc038bc40
c038bc0c  040094e5   ldr      r0, [r4, #4]
c038bc10  0020a0e3   mov      r2, #0
c038bc14  0210a0e1   mov      r1, r2
c038bc18  0c3900eb   bl       #0xc039a050
c038bc1c  c1f9ffeb   bl       #0xc038a328
c038bc20  00b0a0e1   mov      fp, r0
c038bc24  080094e5   ldr      r0, [r4, #8]
c038bc28  0e6c00eb   bl       #0xc03a6c68
c038bc2c  0010a0e1   mov      r1, r0
c038bc30  040094e5   ldr      r0, [r4, #4]
c038bc34  0030a0e3   mov      r3, #0
c038bc38  0b20a0e1   mov      r2, fp
c038bc3c  194200eb   bl       #0xc039c4a8
c038bc40  0630a0e1   mov      r3, r6
c038bc44  0300a0e1   mov      r0, r3
c038bc48  10d08de2   add      sp, sp, #0x10
c038bc4c  f088bde8   pop      {r4, r5, r6, r7, fp, pc}
c038bc50  f0492de9   push     {r4, r5, r6, r7, r8, fp, lr}
c038bc54  10d04de2   sub      sp, sp, #0x10
c038bc58  0070a0e1   mov      r7, r0
c038bc5c  0140a0e1   mov      r4, r1
c038bc60  02b0a0e1   mov      fp, r2
c038bc64  0c5097e5   ldr      r5, [r7, #0xc]
c038bc68  6ca1ffeb   bl       #0xc0374220
c038bc6c  e81094e5   ldr      r1, [r4, #0xe8]
c038bc70  d2a5ffeb   bl       #0xc03753c0
c038bc74  0030a0e1   mov      r3, r0
c038bc78  0360a0e1   mov      r6, r3
c038bc7c  000056e3   cmp      r6, #0
c038bc80  1200000a   beq      #0xc038bcd0
c038bc84  4d38f2eb   bl       #0xc0019dc0
c038bc88  68c096e5   ldr      ip, [r6, #0x68]
c038bc8c  048101e3   movw     r8, #0x1104
c038bc90  0cc08de5   str      ip, [sp, #0xc]
c038bc94  06c098e7   ldr      ip, [r8, r6]
c038bc98  08c08de5   str      ip, [sp, #8]
c038bc9c  e8c094e5   ldr      ip, [r4, #0xe8]
c038bca0  00e000e3   movw     lr, #0
c038bca4  04c08de5   str      ip, [sp, #4]
c038bca8  0cc094e5   ldr      ip, [r4, #0xc]
c038bcac  0020a0e3   mov      r2, #0
c038bcb0  0130a0e3   mov      r3, #1
c038bcb4  44e444e3   movt     lr, #0x4444
c038bcb8  0410a0e3   mov      r1, #4
c038bcbc  0ec08ce1   orr      ip, ip, lr
c038bcc0  00c08de5   str      ip, [sp]
c038bcc4  df38f2eb   bl       #0xc001a048
c038bcc8  0e0000ea   b        #0xc038bd08
c038bccc  00f020e3   nop      
c038bcd0  3a38f2eb   bl       #0xc0019dc0
c038bcd4  00c0a0e3   mov      ip, #0
c038bcd8  0cc08de5   str      ip, [sp, #0xc]
c038bcdc  08c08de5   str      ip, [sp, #8]
c038bce0  0cc094e5   ldr      ip, [r4, #0xc]
c038bce4  0020a0e3   mov      r2, #0
c038bce8  0130a0e3   mov      r3, #1
c038bcec  0410a0e3   mov      r1, #4
c038bcf0  04c08de5   str      ip, [sp, #4]
c038bcf4  44c404e3   movw     ip, #0x4444
c038bcf8  44c444e3   movt     ip, #0x4444
c038bcfc  00c08de5   str      ip, [sp]
c038bd00  d038f2eb   bl       #0xc001a048
c038bd04  00f020e3   nop      
c038bd08  0c3094e5   ldr      r3, [r4, #0xc]
c038bd0c  050053e3   cmp      r3, #5
c038bd10  0600001a   bne      #0xc038bd30
c038bd14  0b20a0e1   mov      r2, fp
c038bd18  0410a0e1   mov      r1, r4
c038bd1c  0700a0e1   mov      r0, r7
c038bd20  1c0000eb   bl       #0xc038bd98
c038bd24  0030a0e1   mov      r3, r0
c038bd28  0350a0e1   mov      r5, r3
c038bd2c  0c0000ea   b        #0xc038bd64
c038bd30  0c3094e5   ldr      r3, [r4, #0xc]
c038bd34  090053e3   cmp      r3, #9
c038bd38  08005313   cmpne    r3, #8
c038bd3c  0700001a   bne      #0xc038bd60
c038bd40  0b20a0e1   mov      r2, fp
c038bd44  0410a0e1   mov      r1, r4
c038bd48  0700a0e1   mov      r0, r7
c038bd4c  c10000eb   bl       #0xc038c058
c038bd50  0030a0e1   mov      r3, r0
c038bd54  0350a0e1   mov      r5, r3
c038bd58  010000ea   b        #0xc038bd64
c038bd5c  00f020e3   nop      
c038bd60  00f020e3   nop      
c038bd64  0530a0e1   mov      r3, r5
c038bd68  0300a0e1   mov      r0, r3
c038bd6c  10d08de2   add      sp, sp, #0x10
c038bd70  f089bde8   pop      {r4, r5, r6, r7, r8, fp, pc}
c038bd74  00f020e3   nop      
c038bd78  00c0a0e1   mov      ip, r0
c038bd7c  0010a0e3   mov      r1, #0
c038bd80  1810cce5   strb     r1, [ip, #0x18]
c038bd84  0010e0e3   mvn      r1, #0
c038bd88  1c108ce5   str      r1, [ip, #0x1c]
c038bd8c  0010a0e3   mov      r1, #0
c038bd90  2010cce5   strb     r1, [ip, #0x20]
c038bd94  1eff2fe1   bx       lr
c038bd98  f0492de9   push     {r4, r5, r6, r7, r8, fp, lr}
c038bd9c  14d04de2   sub      sp, sp, #0x14
c038bda0  0040a0e1   mov      r4, r0
c038bda4  0160a0e1   mov      r6, r1
c038bda8  02b0a0e1   mov      fp, r2
c038bdac  1ba1ffeb   bl       #0xc0374220
c038bdb0  e81096e5   ldr      r1, [r6, #0xe8]
c038bdb4  81a5ffeb   bl       #0xc03753c0
c038bdb8  0030a0e1   mov      r3, r0
c038bdbc  0350a0e1   mov      r5, r3
c038bdc0  0c7094e5   ldr      r7, [r4, #0xc]
c038bdc4  000055e3   cmp      r5, #0
c038bdc8  1c00001a   bne      #0xc038be40
c038bdcc  fb37f2eb   bl       #0xc0019dc0
c038bdd0  e8c096e5   ldr      ip, [r6, #0xe8]
c038bdd4  ff1300e3   movw     r1, #0x3ff
c038bdd8  111041e3   movt     r1, #0x1011
c038bddc  62108de8   stm      sp, {r1, r5, r6, ip}
c038bde0  0330a0e3   mov      r3, #3
c038bde4  0410a0e3   mov      r1, #4
c038bde8  0020a0e3   mov      r2, #0
c038bdec  9538f2eb   bl       #0xc001a048
c038bdf0  000094e5   ldr      r0, [r4]
c038bdf4  0210a0e3   mov      r1, #2
c038bdf8  3c7500eb   bl       #0xc03a92f0
c038bdfc  000094e5   ldr      r0, [r4]
c038be00  0310a0e3   mov      r1, #3
c038be04  397500eb   bl       #0xc03a92f0
c038be08  143094e5   ldr      r3, [r4, #0x14]
c038be0c  020153e3   cmp      r3, #0x80000000
c038be10  0800000a   beq      #0xc038be38
c038be14  cc010ce3   movw     r0, #0xc1cc
c038be18  b9004ce3   movt     r0, #0xc0b9
c038be1c  c56600eb   bl       #0xc03a5938
c038be20  0b20a0e1   mov      r2, fp
c038be24  0010e0e3   mvn      r1, #0
c038be28  0400a0e1   mov      r0, r4
c038be2c  630100eb   bl       #0xc038c3c0
c038be30  0030a0e1   mov      r3, r0
c038be34  840000ea   b        #0xc038c04c
c038be38  0730a0e1   mov      r3, r7
c038be3c  820000ea   b        #0xc038c04c
c038be40  000055e3   cmp      r5, #0
c038be44  0b00000a   beq      #0xc038be78
c038be48  143094e5   ldr      r3, [r4, #0x14]
c038be4c  020153e3   cmp      r3, #0x80000000
c038be50  0800001a   bne      #0xc038be78
c038be54  0400a0e1   mov      r0, r4
c038be58  680200eb   bl       #0xc038c800
c038be5c  000050e3   cmp      r0, #0
c038be60  0400001a   bne      #0xc038be78
c038be64  eb2700eb   bl       #0xc0395e18
c038be68  0210a0e3   mov      r1, #2
c038be6c  632800eb   bl       #0xc0396000
c038be70  0030a0e3   mov      r3, #0
c038be74  143084e5   str      r3, [r4, #0x14]
c038be78  e43096e5   ldr      r3, [r6, #0xe4]
c038be7c  000053e3   cmp      r3, #0
c038be80  3800000a   beq      #0xc038bf68
c038be84  cd37f2eb   bl       #0xc0019dc0
c038be88  00c0a0e3   mov      ip, #0
c038be8c  0cc08de5   str      ip, [sp, #0xc]
c038be90  0c10a0e1   mov      r1, ip
c038be94  02108de9   stmib    sp, {r1, ip}
c038be98  03c300e3   movw     ip, #0x303
c038be9c  0030a0e3   mov      r3, #0
c038bea0  11c041e3   movt     ip, #0x1011
c038bea4  0320a0e1   mov      r2, r3
c038bea8  0410a0e3   mov      r1, #4
c038beac  00c08de5   str      ip, [sp]
c038beb0  6438f2eb   bl       #0xc001a048
c038beb4  000094e5   ldr      r0, [r4]
c038beb8  0210a0e3   mov      r1, #2
c038bebc  0b7500eb   bl       #0xc03a92f0
c038bec0  000094e5   ldr      r0, [r4]
c038bec4  0310a0e3   mov      r1, #3
c038bec8  087500eb   bl       #0xc03a92f0
c038becc  1dadffeb   bl       #0xc0377348
c038bed0  fc8001e3   movw     r8, #0x10fc
c038bed4  051098e7   ldr      r1, [r8, r5]
c038bed8  14aeffeb   bl       #0xc0377730
c038bedc  118c85e2   add      r8, r5, #0x1100
c038bee0  008098e5   ldr      r8, [r8]
c038bee4  10808de5   str      r8, [sp, #0x10]
c038bee8  cca0ffeb   bl       #0xc0374220
c038beec  fc8001e3   movw     r8, #0x10fc
c038bef0  051098e7   ldr      r1, [r8, r5]
c038bef4  4da4ffeb   bl       #0xc0375030
c038bef8  e43096e5   ldr      r3, [r6, #0xe4]
c038befc  040053e3   cmp      r3, #4
c038bf00  0200000a   beq      #0xc038bf10
c038bf04  7fc7ffeb   bl       #0xc037dd08
c038bf08  f4c7ffeb   bl       #0xc037dee0
c038bf0c  00f020e3   nop      
c038bf10  143094e5   ldr      r3, [r4, #0x14]
c038bf14  020153e3   cmp      r3, #0x80000000
c038bf18  1000000a   beq      #0xc038bf60
c038bf1c  e43096e5   ldr      r3, [r6, #0xe4]
c038bf20  040053e3   cmp      r3, #4
c038bf24  0300000a   beq      #0xc038bf38
c038bf28  d4010ce3   movw     r0, #0xc1d4
c038bf2c  b9004ce3   movt     r0, #0xc0b9
c038bf30  806600eb   bl       #0xc03a5938
c038bf34  030000ea   b        #0xc038bf48
c038bf38  dc010ce3   movw     r0, #0xc1dc
c038bf3c  b9004ce3   movt     r0, #0xc0b9
c038bf40  7c6600eb   bl       #0xc03a5938
c038bf44  00f020e3   nop      
c038bf48  10109de5   ldr      r1, [sp, #0x10]
c038bf4c  0400a0e1   mov      r0, r4
c038bf50  0b20a0e1   mov      r2, fp
c038bf54  190100eb   bl       #0xc038c3c0
c038bf58  0030a0e1   mov      r3, r0
c038bf5c  3a0000ea   b        #0xc038c04c
c038bf60  0730a0e1   mov      r3, r7
c038bf64  380000ea   b        #0xc038c04c
c038bf68  1830d4e5   ldrb     r3, [r4, #0x18]
c038bf6c  000053e3   cmp      r3, #0
c038bf70  1100000a   beq      #0xc038bfbc
c038bf74  800d0de3   movw     r0, #0xdd80
c038bf78  58034ce3   movt     r0, #0xc358
c038bf7c  431cf2eb   bl       #0xc0013090
c038bf80  000050e3   cmp      r0, #0
c038bf84  0500000a   beq      #0xc038bfa0
c038bf88  880d0de3   movw     r0, #0xdd88
c038bf8c  58034ce3   movt     r0, #0xc358
c038bf90  380200eb   bl       #0xc038c878
c038bf94  800d0de3   movw     r0, #0xdd80
c038bf98  58034ce3   movt     r0, #0xc358
c038bf9c  901cf2eb   bl       #0xc00131e4
c038bfa0  301001e3   movw     r1, #0x1030
c038bfa4  880d0de3   movw     r0, #0xdd88
c038bfa8  051081e0   add      r1, r1, r5
c038bfac  58034ce3   movt     r0, #0xc358
c038bfb0  d0e9ffeb   bl       #0xc03866f8
c038bfb4  0030a0e3   mov      r3, #0
c038bfb8  1830c4e5   strb     r3, [r4, #0x18]
c038bfbc  4df8ffeb   bl       #0xc038a0f8
c038bfc0  0c3090e5   ldr      r3, [r0, #0xc]
c038bfc4  4c3185e5   str      r3, [r5, #0x14c]
c038bfc8  0510a0e1   mov      r1, r5
c038bfcc  0400a0e1   mov      r0, r4
c038bfd0  880100eb   bl       #0xc038c5f8
c038bfd4  4bc7ffeb   bl       #0xc037dd08
c038bfd8  003090e5   ldr      r3, [r0]
c038bfdc  fc8001e3   movw     r8, #0x10fc
c038bfe0  051098e7   ldr      r1, [r8, r5]
c038bfe4  103083e2   add      r3, r3, #0x10
c038bfe8  003093e5   ldr      r3, [r3]
c038bfec  0120a0e3   mov      r2, #1
c038bff0  33ff2fe1   blx      r3
c038bff4  000094e5   ldr      r0, [r4]
c038bff8  0310a0e3   mov      r1, #3
c038bffc  ab7400eb   bl       #0xc03a92b0
c038c000  000050e3   cmp      r0, #0
c038c004  0f00000a   beq      #0xc038c048
c038c008  e4010ce3   movw     r0, #0xc1e4
c038c00c  b9004ce3   movt     r0, #0xc0b9
c038c010  486600eb   bl       #0xc03a5938
c038c014  110c85e2   add      r0, r5, #0x1100
c038c018  001090e5   ldr      r1, [r0]
c038c01c  0b20a0e1   mov      r2, fp
c038c020  0400a0e1   mov      r0, r4
c038c024  e50000eb   bl       #0xc038c3c0
c038c028  0030a0e1   mov      r3, r0
c038c02c  0370a0e1   mov      r7, r3
c038c030  000094e5   ldr      r0, [r4]
c038c034  0210a0e3   mov      r1, #2
c038c038  ac7400eb   bl       #0xc03a92f0
c038c03c  000094e5   ldr      r0, [r4]
c038c040  0310a0e3   mov      r1, #3
c038c044  a97400eb   bl       #0xc03a92f0
c038c048  0730a0e1   mov      r3, r7
c038c04c  0300a0e1   mov      r0, r3
c038c050  14d08de2   add      sp, sp, #0x14
c038c054  f089bde8   pop      {r4, r5, r6, r7, r8, fp, pc}
c038c058  f0492de9   push     {r4, r5, r6, r7, r8, fp, lr}
c038c05c  20d04de2   sub      sp, sp, #0x20
c038c060  0040a0e1   mov      r4, r0
c038c064  0170a0e1   mov      r7, r1
c038c068  1c208de5   str      r2, [sp, #0x1c]
c038c06c  0c5094e5   ldr      r5, [r4, #0xc]
c038c070  6aa0ffeb   bl       #0xc0374220
c038c074  e81097e5   ldr      r1, [r7, #0xe8]
c038c078  d0a4ffeb   bl       #0xc03753c0
c038c07c  0030a0e1   mov      r3, r0
c038c080  0360a0e1   mov      r6, r3
c038c084  000056e3   cmp      r6, #0
c038c088  0200000a   beq      #0xc038c098
c038c08c  e43097e5   ldr      r3, [r7, #0xe4]
c038c090  000053e3   cmp      r3, #0
c038c094  3b00000a   beq      #0xc038c188
c038c098  aaacffeb   bl       #0xc0377348
c038c09c  5fadffeb   bl       #0xc0377620
c038c0a0  18c7ffeb   bl       #0xc037dd08
c038c0a4  8dc7ffeb   bl       #0xc037dee0
c038c0a8  4437f2eb   bl       #0xc0019dc0
c038c0ac  00c0a0e3   mov      ip, #0
c038c0b0  0cc08de5   str      ip, [sp, #0xc]
c038c0b4  08c08de5   str      ip, [sp, #8]
c038c0b8  e8e097e5   ldr      lr, [r7, #0xe8]
c038c0bc  08c300e3   movw     ip, #0x308
c038c0c0  11c041e3   movt     ip, #0x1011
c038c0c4  00508de8   stm      sp, {ip, lr}
c038c0c8  0330a0e3   mov      r3, #3
c038c0cc  0410a0e3   mov      r1, #4
c038c0d0  0020a0e3   mov      r2, #0
c038c0d4  db37f2eb   bl       #0xc001a048
c038c0d8  1c3400eb   bl       #0xc0399150
c038c0dc  000050e3   cmp      r0, #0
c038c0e0  1a00000a   beq      #0xc038c150
c038c0e4  000056e3   cmp      r6, #0
c038c0e8  0a00000a   beq      #0xc038c118
c038c0ec  f0010ce3   movw     r0, #0xc1f0
c038c0f0  b9004ce3   movt     r0, #0xc0b9
c038c0f4  0f6600eb   bl       #0xc03a5938
c038c0f8  1c209de5   ldr      r2, [sp, #0x1c]
c038c0fc  110c86e2   add      r0, r6, #0x1100
c038c100  001090e5   ldr      r1, [r0]
c038c104  0400a0e1   mov      r0, r4
c038c108  ac0000eb   bl       #0xc038c3c0
c038c10c  0030a0e1   mov      r3, r0
c038c110  0350a0e1   mov      r5, r3
c038c114  050000ea   b        #0xc038c130
c038c118  1c209de5   ldr      r2, [sp, #0x1c]
c038c11c  0400a0e1   mov      r0, r4
c038c120  0010e0e3   mvn      r1, #0
c038c124  a50000eb   bl       #0xc038c3c0
c038c128  0030a0e1   mov      r3, r0
c038c12c  0350a0e1   mov      r5, r3
c038c130  000094e5   ldr      r0, [r4]
c038c134  0210a0e3   mov      r1, #2
c038c138  6c7400eb   bl       #0xc03a92f0
c038c13c  000094e5   ldr      r0, [r4]
c038c140  0310a0e3   mov      r1, #3
c038c144  697400eb   bl       #0xc03a92f0
c038c148  0e0000ea   b        #0xc038c188
c038c14c  00f020e3   nop      
c038c150  1a37f2eb   bl       #0xc0019dc0
c038c154  00c0a0e3   mov      ip, #0
c038c158  0cc08de5   str      ip, [sp, #0xc]
c038c15c  08c08de5   str      ip, [sp, #8]
c038c160  e8c097e5   ldr      ip, [r7, #0xe8]
c038c164  0020a0e3   mov      r2, #0
c038c168  0330a0e3   mov      r3, #3
c038c16c  0410a0e3   mov      r1, #4
c038c170  04c08de5   str      ip, [sp, #4]
c038c174  1ac300e3   movw     ip, #0x31a
c038c178  11c041e3   movt     ip, #0x1011
c038c17c  00c08de5   str      ip, [sp]
c038c180  b037f2eb   bl       #0xc001a048
c038c184  00f020e3   nop      
c038c188  000056e3   cmp      r6, #0
c038c18c  0100001a   bne      #0xc038c198
c038c190  00b0e0e3   mvn      fp, #0
c038c194  010000ea   b        #0xc038c1a0
c038c198  113c86e2   add      r3, r6, #0x1100
c038c19c  00b093e5   ldr      fp, [r3]
c038c1a0  000056e3   cmp      r6, #0
c038c1a4  0100001a   bne      #0xc038c1b0
c038c1a8  110000ea   b        #0xc038c1f4
c038c1ac  00f020e3   nop      
c038c1b0  0c3097e5   ldr      r3, [r7, #0xc]
c038c1b4  080053e3   cmp      r3, #8
c038c1b8  0400001a   bne      #0xc038c1d0
c038c1bc  d1c6ffeb   bl       #0xc037dd08
c038c1c0  0010e0e3   mvn      r1, #0
c038c1c4  5dc7ffeb   bl       #0xc037df40
c038c1c8  090000ea   b        #0xc038c1f4
c038c1cc  00f020e3   nop      
c038c1d0  0c3097e5   ldr      r3, [r7, #0xc]
c038c1d4  090053e3   cmp      r3, #9
c038c1d8  0400001a   bne      #0xc038c1f0
c038c1dc  c9c6ffeb   bl       #0xc037dd08
c038c1e0  fc8001e3   movw     r8, #0x10fc
c038c1e4  061098e7   ldr      r1, [r8, r6]
c038c1e8  54c7ffeb   bl       #0xc037df40
c038c1ec  000000ea   b        #0xc038c1f4
c038c1f0  00f020e3   nop      
c038c1f4  000056e3   cmp      r6, #0
c038c1f8  0a00000a   beq      #0xc038c228
c038c1fc  0c3097e5   ldr      r3, [r7, #0xc]
c038c200  090053e3   cmp      r3, #9
c038c204  0700001a   bne      #0xc038c228
c038c208  4eacffeb   bl       #0xc0377348
c038c20c  fc8001e3   movw     r8, #0x10fc
c038c210  061098e7   ldr      r1, [r8, r6]
c038c214  45adffeb   bl       #0xc0377730
c038c218  00a0ffeb   bl       #0xc0374220
c038c21c  fc8001e3   movw     r8, #0x10fc
c038c220  061098e7   ldr      r1, [r8, r6]
c038c224  81a3ffeb   bl       #0xc0375030
c038c228  4e01feeb   bl       #0xc030c768
c038c22c  ff01feeb   bl       #0xc030ca30
c038c230  0030a0e1   mov      r3, r0
c038c234  14308de5   str      r3, [sp, #0x14]
c038c238  14309de5   ldr      r3, [sp, #0x14]
c038c23c  020053e3   cmp      r3, #2
c038c240  03005313   cmpne    r3, #3
c038c244  0d00001a   bne      #0xc038c280
c038c248  dc36f2eb   bl       #0xc0019dc0
c038c24c  00c0a0e3   mov      ip, #0
c038c250  0cc08de5   str      ip, [sp, #0xc]
c038c254  0c10a0e1   mov      r1, ip
c038c258  02108de9   stmib    sp, {r1, ip}
c038c25c  21c300e3   movw     ip, #0x321
c038c260  11c041e3   movt     ip, #0x1011
c038c264  0020a0e3   mov      r2, #0
c038c268  0130a0e3   mov      r3, #1
c038c26c  0410a0e3   mov      r1, #4
c038c270  00c08de5   str      ip, [sp]
c038c274  7337f2eb   bl       #0xc001a048
c038c278  0c3094e5   ldr      r3, [r4, #0xc]
c038c27c  4c0000ea   b        #0xc038c3b4
c038c280  0b10a0e1   mov      r1, fp
c038c284  0100a0e3   mov      r0, #1
c038c288  be3200eb   bl       #0xc0398d88
c038c28c  0030a0e1   mov      r3, r0
c038c290  1330cde5   strb     r3, [sp, #0x13]
c038c294  080094e5   ldr      r0, [r4, #8]
c038c298  726a00eb   bl       #0xc03a6c68
c038c29c  030050e3   cmp      r0, #3
c038c2a0  0300000a   beq      #0xc038c2b4
c038c2a4  080094e5   ldr      r0, [r4, #8]
c038c2a8  6c6900eb   bl       #0xc03a6860
c038c2ac  010050e3   cmp      r0, #1
c038c2b0  1200000a   beq      #0xc038c300
c038c2b4  040094e5   ldr      r0, [r4, #4]
c038c2b8  0020a0e3   mov      r2, #0
c038c2bc  0210a0e1   mov      r1, r2
c038c2c0  623700eb   bl       #0xc039a050
c038c2c4  080094e5   ldr      r0, [r4, #8]
c038c2c8  ec810ce3   movw     r8, #0xc1ec
c038c2cc  b9804ce3   movt     r8, #0xc0b9
c038c2d0  008098e5   ldr      r8, [r8]
c038c2d4  7b6800eb   bl       #0xc03a64c8
c038c2d8  0030a0e3   mov      r3, #0
c038c2dc  08018de8   stm      sp, {r3, r8}
c038c2e0  0c2094e5   ldr      r2, [r4, #0xc]
c038c2e4  0010a0e1   mov      r1, r0
c038c2e8  1c009de5   ldr      r0, [sp, #0x1c]
c038c2ec  f32900eb   bl       #0xc0396ac0
c038c2f0  0030a0e1   mov      r3, r0
c038c2f4  0350a0e1   mov      r5, r3
c038c2f8  130000ea   b        #0xc038c34c
c038c2fc  00f020e3   nop      
c038c300  c69fffeb   bl       #0xc0374220
c038c304  7da5ffeb   bl       #0xc0375900
c038c308  000050e3   cmp      r0, #0
c038c30c  0d00001a   bne      #0xc038c348
c038c310  000094e5   ldr      r0, [r4]
c038c314  0110a0e3   mov      r1, #1
c038c318  e47300eb   bl       #0xc03a92b0
c038c31c  000050e3   cmp      r0, #0
c038c320  0300001a   bne      #0xc038c334
c038c324  000094e5   ldr      r0, [r4]
c038c328  f87300eb   bl       #0xc03a9310
c038c32c  000050e3   cmp      r0, #0
c038c330  0200000a   beq      #0xc038c340
c038c334  0350a0e3   mov      r5, #3
c038c338  030000ea   b        #0xc038c34c
c038c33c  00f020e3   nop      
c038c340  0150a0e3   mov      r5, #1
c038c344  000000ea   b        #0xc038c34c
c038c348  00f020e3   nop      
c038c34c  1330dde5   ldrb     r3, [sp, #0x13]
c038c350  000053e3   cmp      r3, #0
c038c354  1500000a   beq      #0xc038c3b0
c038c358  800d0de3   movw     r0, #0xdd80
c038c35c  58034ce3   movt     r0, #0xc358
c038c360  4a1bf2eb   bl       #0xc0013090
c038c364  000050e3   cmp      r0, #0
c038c368  0600000a   beq      #0xc038c388
c038c36c  880d0de3   movw     r0, #0xdd88
c038c370  58034ce3   movt     r0, #0xc358
c038c374  3f0100eb   bl       #0xc038c878
c038c378  800d0de3   movw     r0, #0xdd80
c038c37c  58034ce3   movt     r0, #0xc358
c038c380  971bf2eb   bl       #0xc00131e4
c038c384  00f020e3   nop      
c038c388  880d0de3   movw     r0, #0xdd88
c038c38c  58034ce3   movt     r0, #0xc358
c038c390  72e9ffeb   bl       #0xc0386960
c038c394  0030a0e3   mov      r3, #0
c038c398  0120a0e3   mov      r2, #1
c038c39c  1310a0e3   mov      r1, #0x13
c038c3a0  0300a0e1   mov      r0, r3
c038c3a4  b52a00eb   bl       #0xc0396e80
c038c3a8  0530a0e1   mov      r3, r5
c038c3ac  000000ea   b        #0xc038c3b4
c038c3b0  0c3094e5   ldr      r3, [r4, #0xc]
c038c3b4  0300a0e1   mov      r0, r3
c038c3b8  20d08de2   add      sp, sp, #0x20
c038c3bc  f089bde8   pop      {r4, r5, r6, r7, r8, fp, pc}
c038c3c0  f0492de9   push     {r4, r5, r6, r7, r8, fp, lr}
c038c3c4  14d04de2   sub      sp, sp, #0x14
c038c3c8  0040a0e1   mov      r4, r0
c038c3cc  0c108de5   str      r1, [sp, #0xc]
c038c3d0  10208de5   str      r2, [sp, #0x10]
c038c3d4  7936f2eb   bl       #0xc0019dc0
c038c3d8  00c20ce3   movw     ip, #0xc200
c038c3dc  b9c04ce3   movt     ip, #0xc0b9
c038c3e0  0430a0e3   mov      r3, #4
c038c3e4  0020a0e3   mov      r2, #0
c038c3e8  0310a0e1   mov      r1, r3
c038c3ec  00c08de5   str      ip, [sp]
c038c3f0  a437f2eb   bl       #0xc001a288
c038c3f4  fc310ce3   movw     r3, #0xc1fc
c038c3f8  b9304ce3   movt     r3, #0xc0b9
c038c3fc  005093e5   ldr      r5, [r3]
c038c400  0510a0e1   mov      r1, r5
c038c404  0000a0e3   mov      r0, #0
c038c408  4407f5eb   bl       #0xc00ce120
c038c40c  cdabffeb   bl       #0xc0377348
c038c410  0030a0e1   mov      r3, r0
c038c414  7870d3e5   ldrb     r7, [r3, #0x78]
c038c418  2030d4e5   ldrb     r3, [r4, #0x20]
c038c41c  000053e3   cmp      r3, #0
c038c420  2a00001a   bne      #0xc038c4d0
c038c424  c7abffeb   bl       #0xc0377348
c038c428  7cacffeb   bl       #0xc0377620
c038c42c  b1bbf9eb   bl       #0xc01fb2f8
c038c430  9cbdf9eb   bl       #0xc01fbaa8
c038c434  0030a0e3   mov      r3, #0
c038c438  0120a0e3   mov      r2, #1
c038c43c  1110a0e3   mov      r1, #0x11
c038c440  0300a0e1   mov      r0, r3
c038c444  8d2a00eb   bl       #0xc0396e80
c038c448  722600eb   bl       #0xc0395e18
c038c44c  0211a0e3   mov      r1, #0x80000000
c038c450  602700eb   bl       #0xc03961d8
c038c454  8feaf9eb   bl       #0xc0206e98
c038c458  0aebf9eb   bl       #0xc0207088
c038c45c  e030d0e5   ldrb     r3, [r0, #0xe0]
c038c460  000053e3   cmp      r3, #0
c038c464  0300000a   beq      #0xc038c478
c038c468  a2bbf9eb   bl       #0xc01fb2f8
c038c46c  25bcf9eb   bl       #0xc01fb508
c038c470  020000ea   b        #0xc038c480
c038c474  00f020e3   nop      
c038c478  9ebbf9eb   bl       #0xc01fb2f8
c038c47c  25bdf9eb   bl       #0xc01fb918
c038c480  323300eb   bl       #0xc0399150
c038c484  000050e3   cmp      r0, #0
c038c488  0000000a   beq      #0xc038c490
c038c48c  0070a0e3   mov      r7, #0
c038c490  0000a0e3   mov      r0, #0
c038c494  333300eb   bl       #0xc0399168
c038c498  143094e5   ldr      r3, [r4, #0x14]
c038c49c  020153e3   cmp      r3, #0x80000000
c038c4a0  0400000a   beq      #0xc038c4b8
c038c4a4  000057e3   cmp      r7, #0
c038c4a8  0200001a   bne      #0xc038c4b8
c038c4ac  0010e0e3   mvn      r1, #0
c038c4b0  0500a0e3   mov      r0, #5
c038c4b4  f77e00eb   bl       #0xc03ac098
c038c4b8  0231a0e3   mov      r3, #0x80000000
c038c4bc  143084e5   str      r3, [r4, #0x14]
c038c4c0  52ceffeb   bl       #0xc037fe10
c038c4c4  0dcfffeb   bl       #0xc0380100
c038c4c8  0030a0e1   mov      r3, r0
c038c4cc  005093e5   ldr      r5, [r3]
c038c4d0  0510a0e1   mov      r1, r5
c038c4d4  0000a0e3   mov      r0, #0
c038c4d8  1007f5eb   bl       #0xc00ce120
c038c4dc  0c109de5   ldr      r1, [sp, #0xc]
c038c4e0  0100a0e3   mov      r0, #1
c038c4e4  273200eb   bl       #0xc0398d88
c038c4e8  0030a0e1   mov      r3, r0
c038c4ec  03b0a0e1   mov      fp, r3
c038c4f0  2030d4e5   ldrb     r3, [r4, #0x20]
c038c4f4  000053e3   cmp      r3, #0
c038c4f8  0400001a   bne      #0xc038c510
c038c4fc  040094e5   ldr      r0, [r4, #4]
c038c500  0020a0e3   mov      r2, #0
c038c504  0210a0e1   mov      r1, r2
c038c508  d03600eb   bl       #0xc039a050
c038c50c  00f020e3   nop      
c038c510  0c6094e5   ldr      r6, [r4, #0xc]
c038c514  9300feeb   bl       #0xc030c768
c038c518  4401feeb   bl       #0xc030ca30
c038c51c  020050e3   cmp      r0, #2
c038c520  0c00000a   beq      #0xc038c558
c038c524  080094e5   ldr      r0, [r4, #8]
c038c528  f8810ce3   movw     r8, #0xc1f8
c038c52c  b9804ce3   movt     r8, #0xc0b9
c038c530  008098e5   ldr      r8, [r8]
c038c534  e36700eb   bl       #0xc03a64c8
c038c538  0030a0e3   mov      r3, #0
c038c53c  08018de8   stm      sp, {r3, r8}
c038c540  0c2094e5   ldr      r2, [r4, #0xc]
c038c544  0010a0e1   mov      r1, r0
c038c548  10009de5   ldr      r0, [sp, #0x10]
c038c54c  5b2900eb   bl       #0xc0396ac0
c038c550  0030a0e1   mov      r3, r0
c038c554  0360a0e1   mov      r6, r3
c038c558  00005be3   cmp      fp, #0
c038c55c  1f00000a   beq      #0xc038c5e0
c038c560  1636f2eb   bl       #0xc0019dc0
c038c564  0cc20ce3   movw     ip, #0xc20c
c038c568  b9c04ce3   movt     ip, #0xc0b9
c038c56c  40108de8   stm      sp, {r6, ip}
c038c570  0430a0e3   mov      r3, #4
c038c574  0310a0e1   mov      r1, r3
c038c578  0020a0e3   mov      r2, #0
c038c57c  b337f2eb   bl       #0xc001a450
c038c580  5cbbf9eb   bl       #0xc01fb2f8
c038c584  0010a0e3   mov      r1, #0
c038c588  2cbcf9eb   bl       #0xc01fb640
c038c58c  800d0de3   movw     r0, #0xdd80
c038c590  58034ce3   movt     r0, #0xc358
c038c594  bd1af2eb   bl       #0xc0013090
c038c598  000050e3   cmp      r0, #0
c038c59c  0500000a   beq      #0xc038c5b8
c038c5a0  880d0de3   movw     r0, #0xdd88
c038c5a4  58034ce3   movt     r0, #0xc358
c038c5a8  b20000eb   bl       #0xc038c878
c038c5ac  800d0de3   movw     r0, #0xdd80
c038c5b0  58034ce3   movt     r0, #0xc358
c038c5b4  0a1bf2eb   bl       #0xc00131e4
c038c5b8  880d0de3   movw     r0, #0xdd88
c038c5bc  58034ce3   movt     r0, #0xc358
c038c5c0  e6e8ffeb   bl       #0xc0386960
c038c5c4  0030a0e3   mov      r3, #0
c038c5c8  0120a0e3   mov      r2, #1
c038c5cc  1310a0e3   mov      r1, #0x13
c038c5d0  0300a0e1   mov      r0, r3
c038c5d4  292a00eb   bl       #0xc0396e80
c038c5d8  0630a0e1   mov      r3, r6
c038c5dc  020000ea   b        #0xc038c5ec
c038c5e0  0130a0e3   mov      r3, #1
c038c5e4  2030c4e5   strb     r3, [r4, #0x20]
c038c5e8  0c3094e5   ldr      r3, [r4, #0xc]
c038c5ec  0300a0e1   mov      r0, r3
c038c5f0  14d08de2   add      sp, sp, #0x14
c038c5f4  f089bde8   pop      {r4, r5, r6, r7, r8, fp, pc}
c038c5f8  f0492de9   push     {r4, r5, r6, r7, r8, fp, lr}
c038c5fc  2cd04de2   sub      sp, sp, #0x2c
c038c600  00b0a0e1   mov      fp, r0
c038c604  0150a0e1   mov      r5, r1
c038c608  ec35f2eb   bl       #0xc0019dc0
c038c60c  0030a0e3   mov      r3, #0
c038c610  0310a0e1   mov      r1, r3
c038c614  0340a0e1   mov      r4, r3
c038c618  1a008de9   stmib    sp, {r1, r3, r4}
c038c61c  043300e3   movw     r3, #0x304
c038c620  113041e3   movt     r3, #0x1011
c038c624  00308de5   str      r3, [sp]
c038c628  0130a0e3   mov      r3, #1
c038c62c  0410a0e3   mov      r1, #4
c038c630  0020a0e3   mov      r2, #0
c038c634  8336f2eb   bl       #0xc001a048
c038c638  aef6ffeb   bl       #0xc038a0f8
c038c63c  eff6ffeb   bl       #0xc038a200
c038c640  0020a0e1   mov      r2, r0
c038c644  0240a0e1   mov      r4, r2
c038c648  aaf6ffeb   bl       #0xc038a0f8
c038c64c  eff6ffeb   bl       #0xc038a210
c038c650  0020a0e1   mov      r2, r0
c038c654  0260a0e1   mov      r6, r2
c038c658  702196e5   ldr      r2, [r6, #0x170]
c038c65c  0c2082e2   add      r2, r2, #0xc
c038c660  002092e5   ldr      r2, [r2]
c038c664  0600a0e1   mov      r0, r6
c038c668  0410a0e1   mov      r1, r4
c038c66c  32ff2fe1   blx      r2
c038c670  0020a0e1   mov      r2, r0
c038c674  0270a0e1   mov      r7, r2
c038c678  d035f2eb   bl       #0xc0019dc0
c038c67c  00c0a0e3   mov      ip, #0
c038c680  0ce0a0e1   mov      lr, ip
c038c684  053300e3   movw     r3, #0x305
c038c688  0c80a0e1   mov      r8, ip
c038c68c  113041e3   movt     r3, #0x1011
c038c690  08518de8   stm      sp, {r3, r8, ip, lr}
c038c694  0130a0e3   mov      r3, #1
c038c698  0410a0e3   mov      r1, #4
c038c69c  0c20a0e1   mov      r2, ip
c038c6a0  6836f2eb   bl       #0xc001a048
c038c6a4  002094e5   ldr      r2, [r4]
c038c6a8  1c2082e2   add      r2, r2, #0x1c
c038c6ac  002092e5   ldr      r2, [r2]
c038c6b0  14008de2   add      r0, sp, #0x14
c038c6b4  0410a0e1   mov      r1, r4
c038c6b8  32ff2fe1   blx      r2
c038c6bc  d421cde1   ldrd     r2, r3, [sp, #0x14]
c038c6c0  10308de5   str      r3, [sp, #0x10]
c038c6c4  2700feeb   bl       #0xc030c768
c038c6c8  4c1095e5   ldr      r1, [r5, #0x4c]
c038c6cc  3b01feeb   bl       #0xc030cbc0
c038c6d0  10209de5   ldr      r2, [sp, #0x10]
c038c6d4  000082e5   str      r0, [r2]
c038c6d8  442cf3eb   bl       #0xc00577f0
c038c6dc  00c0a0e1   mov      ip, r0
c038c6e0  000057e3   cmp      r7, #0
c038c6e4  0220a0e3   mov      r2, #2
c038c6e8  0000000a   beq      #0xc038c6f0
c038c6ec  0320a0e3   mov      r2, #3
c038c6f0  0430a0e1   mov      r3, r4
c038c6f4  0210a0e1   mov      r1, r2
c038c6f8  0c00a0e1   mov      r0, ip
c038c6fc  0320a0e3   mov      r2, #3
c038c700  ba24f3eb   bl       #0xc00559f0
c038c704  ad35f2eb   bl       #0xc0019dc0
c038c708  00c0a0e3   mov      ip, #0
c038c70c  0ce0a0e1   mov      lr, ip
c038c710  063300e3   movw     r3, #0x306
c038c714  0c80a0e1   mov      r8, ip
c038c718  113041e3   movt     r3, #0x1011
c038c71c  08518de8   stm      sp, {r3, r8, ip, lr}
c038c720  0130a0e3   mov      r3, #1
c038c724  0410a0e3   mov      r1, #4
c038c728  0c20a0e1   mov      r2, ip
c038c72c  4536f2eb   bl       #0xc001a048
c038c730  18c20ce3   movw     ip, #0xc218
c038c734  b9c04ce3   movt     ip, #0xc0b9
c038c738  1c208de2   add      r2, sp, #0x1c
c038c73c  0b00bce8   ldm      ip!, {r0, r1, r3}
c038c740  0b00a2e8   stm      r2!, {r0, r1, r3}
c038c744  00309ce5   ldr      r3, [ip]
c038c748  003082e5   str      r3, [r2]
c038c74c  69f6ffeb   bl       #0xc038a0f8
c038c750  f0f6ffeb   bl       #0xc038a318
c038c754  0020a0e1   mov      r2, r0
c038c758  1c208de5   str      r2, [sp, #0x1c]
c038c75c  4c0095e5   ldr      r0, [r5, #0x4c]
c038c760  4c1195e5   ldr      r1, [r5, #0x14c]
c038c764  5311f2eb   bl       #0xc0010cb8
c038c768  0020a0e1   mov      r2, r0
c038c76c  20208de5   str      r2, [sp, #0x20]
c038c770  4c2195e5   ldr      r2, [r5, #0x14c]
c038c774  24208de5   str      r2, [sp, #0x24]
c038c778  1c008de2   add      r0, sp, #0x1c
c038c77c  03bdf5fa   blx      #0xc00fbb90
c038c780  8e35f2eb   bl       #0xc0019dc0
c038c784  00c0a0e3   mov      ip, #0
c038c788  0ce0a0e1   mov      lr, ip
c038c78c  073300e3   movw     r3, #0x307
c038c790  0c80a0e1   mov      r8, ip
c038c794  113041e3   movt     r3, #0x1011
c038c798  08518de8   stm      sp, {r3, r8, ip, lr}
c038c79c  0130a0e3   mov      r3, #1
c038c7a0  0410a0e3   mov      r1, #4
c038c7a4  0c20a0e1   mov      r2, ip
c038c7a8  2636f2eb   bl       #0xc001a048
c038c7ac  2cd08de2   add      sp, sp, #0x2c
c038c7b0  f089bde8   pop      {r4, r5, r6, r7, r8, fp, pc}
c038c7b4  00f020e3   nop      
c038c7b8  30402de9   push     {r4, r5, lr}
c038c7bc  0040a0e1   mov      r4, r0
c038c7c0  e0aaffeb   bl       #0xc0377348
c038c7c4  0050a0e1   mov      r5, r0
c038c7c8  687400eb   bl       #0xc03a9970
c038c7cc  9b7a00eb   bl       #0xc03ab240
c038c7d0  140090e5   ldr      r0, [r0, #0x14]
c038c7d4  7f3afdeb   bl       #0xc02db1d8
c038c7d8  981095e5   ldr      r1, [r5, #0x98]
c038c7dc  101a02ee   vmov     s4, r1
c038c7e0  422bb8ee   vcvt.f64.u32 d2, s4
c038c7e4  001b82ee   vdiv.f64 d1, d2, d0
c038c7e8  003bb6ee   vmov.f64 d3, #5.000000e-01
c038c7ec  031b31ee   vadd.f64 d1, d1, d3
c038c7f0  c14bbcee   vcvt.u32.f64 s8, d1
c038c7f4  101a14ee   vmov     r1, s8
c038c7f8  0100a0e1   mov      r0, r1
c038c7fc  3080bde8   pop      {r4, r5, pc}
c038c800  30402de9   push     {r4, r5, lr}
c038c804  0040a0e1   mov      r4, r0
c038c808  2010d4e5   ldrb     r1, [r4, #0x20]
c038c80c  0150a0e3   mov      r5, #1
c038c810  000051e3   cmp      r1, #0
c038c814  0400001a   bne      #0xc038c82c
c038c818  caaaffeb   bl       #0xc0377348
c038c81c  7810d0e5   ldrb     r1, [r0, #0x78]
c038c820  000051e3   cmp      r1, #0
c038c824  0000001a   bne      #0xc038c82c
c038c828  0050a0e3   mov      r5, #0
c038c82c  0510a0e1   mov      r1, r5
c038c830  0100a0e1   mov      r0, r1
c038c834  3080bde8   pop      {r4, r5, pc}
c038c838  30002de9   push     {r4, r5}
c038c83c  00c0a0e1   mov      ip, r0
c038c840  0140a0e1   mov      r4, r1
c038c844  0250a0e1   mov      r5, r2
c038c848  0c309ce5   ldr      r3, [ip, #0xc]
c038c84c  0300a0e1   mov      r0, r3
c038c850  3000bde8   pop      {r4, r5}
c038c854  1eff2fe1   bx       lr
c038c858  04402de5   str      r4, [sp, #-4]!
c038c85c  0040a0e1   mov      r4, r0
c038c860  01c0a0e1   mov      ip, r1
c038c864  0c20a0e1   mov      r2, ip
c038c868  0200a0e1   mov      r0, r2
c038c86c  04409de4   pop      {r4}
c038c870  1eff2fe1   bx       lr
c038c874  00f020e3   nop      
c038c878  10402de9   push     {r4, lr}
c038c87c  1cd04de2   sub      sp, sp, #0x1c
c038c880  0040a0e1   mov      r4, r0
c038c884  b01f0be3   movw     r1, #0xbfb0
c038c888  b9104ce3   movt     r1, #0xc0b9
c038c88c  0400a0e1   mov      r0, r4
c038c890  022ca0e3   mov      r2, #0x200
c038c894  1c22f2eb   bl       #0xc001510c
c038c898  0010a0e3   mov      r1, #0
c038c89c  3c20a0e3   mov      r2, #0x3c
c038c8a0  810f84e2   add      r0, r4, #0x204
c038c8a4  0012c4e5   strb     r1, [r4, #0x200]
c038c8a8  ea21f2eb   bl       #0xc0015058
c038c8ac  0020a0e3   mov      r2, #0
c038c8b0  04008de2   add      r0, sp, #4
c038c8b4  0210a0e1   mov      r1, r2
c038c8b8  9e64fdeb   bl       #0xc02e5b38
c038c8bc  0020a0e3   mov      r2, #0
c038c8c0  0230a0e1   mov      r3, r2
c038c8c4  0010a0e1   mov      r1, r0
c038c8c8  810f84e2   add      r0, r4, #0x204
c038c8cc  00208de5   str      r2, [sp]
c038c8d0  ce64fdeb   bl       #0xc02e5c10
c038c8d4  0410a0e1   mov      r1, r4
c038c8d8  0100a0e1   mov      r0, r1
c038c8dc  1cd08de2   add      sp, sp, #0x1c
c038c8e0  1080bde8   pop      {r4, pc}
c038c8e4  00f020e3   nop      
c038c8e8  30402de9   push     {r4, r5, lr}
c038c8ec  0050a0e1   mov      r5, r0
c038c8f0  1e7400eb   bl       #0xc03a9970
c038c8f4  0010a0e1   mov      r1, r0
c038c8f8  0140a0e1   mov      r4, r1
c038c8fc  0400a0e1   mov      r0, r4
c038c900  4e7a00eb   bl       #0xc03ab240
c038c904  d911d0e5   ldrb     r1, [r0, #0x1d9]
c038c908  000051e3   cmp      r1, #0
c038c90c  0200000a   beq      #0xc038c91c
c038c910  041095e5   ldr      r1, [r5, #4]
c038c914  0120a0e3   mov      r2, #1
c038c918  2d20c1e5   strb     r2, [r1, #0x2d]
c038c91c  0110a0e3   mov      r1, #1
c038c920  0100a0e1   mov      r0, r1
c038c924  3080bde8   pop      {r4, r5, pc}
c038c928  70402de9   push     {r4, r5, r6, lr}
c038c92c  0050a0e1   mov      r5, r0
c038c930  0160a0e1   mov      r6, r1
c038c934  0d7400eb   bl       #0xc03a9970
c038c938  0020a0e1   mov      r2, r0
c038c93c  0240a0e1   mov      r4, r2
c038c940  0400a0e1   mov      r0, r4
c038c944  3d7a00eb   bl       #0xc03ab240
c038c948  d921d0e5   ldrb     r2, [r0, #0x1d9]
c038c94c  000052e3   cmp      r2, #0
c038c950  0020d615   ldrbne   r2, [r6]
c038c954  00005213   cmpne    r2, #0
c038c958  0200000a   beq      #0xc038c968
c038c95c  042095e5   ldr      r2, [r5, #4]
c038c960  0130a0e3   mov      r3, #1
c038c964  2d30c2e5   strb     r3, [r2, #0x2d]
c038c968  0120a0e3   mov      r2, #1
c038c96c  0200a0e1   mov      r0, r2
c038c970  7080bde8   pop      {r4, r5, r6, pc}
c038c974  00f020e3   nop      
c038c978  10412de9   push     {r4, r8, lr}
c038c97c  c84f0de3   movw     r4, #0xdfc8
c038c980  58434ce3   movt     r4, #0xc358
c038c984  5c0084e2   add      r0, r4, #0x5c
c038c988  c019f2eb   bl       #0xc0013090
c038c98c  000050e3   cmp      r0, #0
c038c990  0600000a   beq      #0xc038c9b0
c038c994  080084e2   add      r0, r4, #8
c038c998  540600eb   bl       #0xc038e2f0
c038c99c  dc040fe3   movw     r0, #0xf4dc
c038c9a0  f1024ce3   movt     r0, #0xc2f1
c038c9a4  521af2eb   bl       #0xc00132f4
c038c9a8  5c0084e2   add      r0, r4, #0x5c
c038c9ac  0c1af2eb   bl       #0xc00131e4
c038c9b0  640084e2   add      r0, r4, #0x64
c038c9b4  b519f2eb   bl       #0xc0013090
