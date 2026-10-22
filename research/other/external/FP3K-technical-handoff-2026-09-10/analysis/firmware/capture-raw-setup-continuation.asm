c031c138  000051e1   cmp      r1, r0
c031c13c  00005113   cmpne    r1, #0
c031c140  2700000a   beq      #0xc031c1e4
c031c144  050000ea   b        #0xc031c160
c031c148  162af8fa   blx      #0xc01269a8
c031c14c  0700a0e1   mov      r0, r7
c031c150  9ef7ffeb   bl       #0xc0319fd0
c031c154  000050e3   cmp      r0, #0
c031c158  0000000a   beq      #0xc031c160
c031c15c  050000ea   b        #0xc031c178
c031c160  c225f8fa   blx      #0xc0125870
c031c164  44008de5   str      r0, [sp, #0x44]
c031c168  a827f8fa   blx      #0xc0126010
c031c16c  44109de5   ldr      r1, [sp, #0x44]
c031c170  000051e1   cmp      r1, r0
c031c174  f3ffff1a   bne      #0xc031c148
c031c178  301096e5   ldr      r1, [r6, #0x30]
c031c17c  0700a0e1   mov      r0, r7
c031c180  46f7ffeb   bl       #0xc0319ea0
c031c184  072af8fa   blx      #0xc01269a8
c031c188  a41700eb   bl       #0xc0322020
c031c18c  b01090e5   ldr      r1, [r0, #0xb0]
c031c190  20108de5   str      r1, [sp, #0x20]
c031c194  30009de5   ldr      r0, [sp, #0x30]
c031c198  08e4ffeb   bl       #0xc03151c0
c031c19c  000090e5   ldr      r0, [r0]
c031c1a0  1e4200eb   bl       #0xc032ca20
c031c1a4  d32d04e3   movw     r2, #0x4dd3
c031c1a8  622041e3   movt     r2, #0x1062
c031c1ac  fa1f80e2   add      r1, r0, #0x3e8
c031c1b0  912281e0   umull    r2, r1, r1, r2
c031c1b4  2123a0e1   lsr      r2, r1, #6
c031c1b8  20109de5   ldr      r1, [sp, #0x20]
c031c1bc  1c208de5   str      r2, [sp, #0x1c]
c031c1c0  020051e1   cmp      r1, r2
c031c1c4  0100002a   bhs      #0xc031c1d0
c031c1c8  1c108de2   add      r1, sp, #0x1c
c031c1cc  000000ea   b        #0xc031c1d4
c031c1d0  20108de2   add      r1, sp, #0x20
c031c1d4  001091e5   ldr      r1, [r1]
c031c1d8  20108de5   str      r1, [sp, #0x20]
c031c1dc  20009de5   ldr      r0, [sp, #0x20]
c031c1e0  fc5001eb   bl       #0xc03705d8
c031c1e4  6125f8fa   blx      #0xc0125770
c031c1e8  0080a0e1   mov      r8, r0
c031c1ec  7700a0e3   mov      r0, #0x77
c031c1f0  704100eb   bl       #0xc032c7b8
c031c1f4  900808e0   mul      r8, r0, r8
c031c1f8  3027f8fa   blx      #0xc0125ec0
c031c1fc  a09088e0   add      sb, r8, r0, lsr #1
c031c200  2e27f8fa   blx      #0xc0125ec0
c031c204  19f039e7   udiv     sb, sb, r0
c031c208  34908de5   str      sb, [sp, #0x34]
c031c20c  831700eb   bl       #0xc0322020
c031c210  b01090e5   ldr      r1, [r0, #0xb0]
c031c214  0121a0e1   lsl      r2, r1, #2
c031c218  021041e0   sub      r1, r1, r2
c031c21c  821281e0   add      r1, r1, r2, lsl #5
c031c220  8111a0e1   lsl      r1, r1, #3
c031c224  18108de5   str      r1, [sp, #0x18]
c031c228  30009de5   ldr      r0, [sp, #0x30]
c031c22c  e3e3ffeb   bl       #0xc03151c0
c031c230  000090e5   ldr      r0, [r0]
c031c234  f94100eb   bl       #0xc032ca20
c031c238  18109de5   ldr      r1, [sp, #0x18]
c031c23c  10008de5   str      r0, [sp, #0x10]
c031c240  000051e1   cmp      r1, r0
c031c244  0100002a   bhs      #0xc031c250
c031c248  10108de2   add      r1, sp, #0x10
c031c24c  000000ea   b        #0xc031c254
c031c250  18108de2   add      r1, sp, #0x18
c031c254  001091e5   ldr      r1, [r1]
c031c258  18108de5   str      r1, [sp, #0x18]
c031c25c  34009de5   ldr      r0, [sp, #0x34]
c031c260  18109de5   ldr      r1, [sp, #0x18]
c031c264  000051e1   cmp      r1, r0
c031c268  0a00003a   blo      #0xc031c298
c031c26c  18109de5   ldr      r1, [sp, #0x18]
c031c270  34009de5   ldr      r0, [sp, #0x34]
c031c274  d32d04e3   movw     r2, #0x4dd3
c031c278  622041e3   movt     r2, #0x1062
c031c27c  001041e0   sub      r1, r1, r0
c031c280  fa1f81e2   add      r1, r1, #0x3e8
c031c284  912281e0   umull    r2, r1, r1, r2
c031c288  2113a0e1   lsr      r1, r1, #6
c031c28c  010081e2   add      r0, r1, #1
c031c290  d05001eb   bl       #0xc03705d8
c031c294  00f020e3   nop      
c031c298  7700a0e3   mov      r0, #0x77
c031c29c  454100eb   bl       #0xc032c7b8
c031c2a0  34209de5   ldr      r2, [sp, #0x34]
c031c2a4  021040e0   sub      r1, r0, r2
c031c2a8  18209de5   ldr      r2, [sp, #0x18]
c031c2ac  020051e1   cmp      r1, r2
c031c2b0  1900002a   bhs      #0xc031c31c
c031c2b4  bb29f8fa   blx      #0xc01269a8
c031c2b8  581700eb   bl       #0xc0322020
c031c2bc  b01090e5   ldr      r1, [r0, #0xb0]
c031c2c0  18108de5   str      r1, [sp, #0x18]
c031c2c4  30009de5   ldr      r0, [sp, #0x30]
c031c2c8  bce3ffeb   bl       #0xc03151c0
c031c2cc  000090e5   ldr      r0, [r0]
c031c2d0  d24100eb   bl       #0xc032ca20
c031c2d4  d32d04e3   movw     r2, #0x4dd3
c031c2d8  622041e3   movt     r2, #0x1062
c031c2dc  fa1f80e2   add      r1, r0, #0x3e8
c031c2e0  912281e0   umull    r2, r1, r1, r2
c031c2e4  2113a0e1   lsr      r1, r1, #6
c031c2e8  24108de5   str      r1, [sp, #0x24]
c031c2ec  24209de5   ldr      r2, [sp, #0x24]
c031c2f0  18109de5   ldr      r1, [sp, #0x18]
c031c2f4  020051e1   cmp      r1, r2
c031c2f8  0200002a   bhs      #0xc031c308
c031c2fc  24108de2   add      r1, sp, #0x24
c031c300  010000ea   b        #0xc031c30c
c031c304  00f020e3   nop      
c031c308  18108de2   add      r1, sp, #0x18
c031c30c  001091e5   ldr      r1, [r1]
c031c310  18108de5   str      r1, [sp, #0x18]
c031c314  18009de5   ldr      r0, [sp, #0x18]
c031c318  ae5001eb   bl       #0xc03705d8
c031c31c  d00b0be3   movw     r0, #0xbbd0
c031c320  07034ce3   movt     r0, #0xc307
c031c324  59dbf3eb   bl       #0xc0013090
c031c328  000050e3   cmp      r0, #0
c031c32c  0500000a   beq      #0xc031c348
c031c330  b00b0be3   movw     r0, #0xbbb0
c031c334  07034ce3   movt     r0, #0xc307
c031c338  8c1600eb   bl       #0xc0321d70
c031c33c  d00b0be3   movw     r0, #0xbbd0
c031c340  07034ce3   movt     r0, #0xc307
c031c344  a6dbf3eb   bl       #0xc00131e4
c031c348  b00b0be3   movw     r0, #0xbbb0
c031c34c  07034ce3   movt     r0, #0xc307
c031c350  cc1600eb   bl       #0xc0321e88
c031c354  0b00a0e1   mov      r0, fp
c031c358  000800eb   bl       #0xc031e360
c031c35c  0010d0e5   ldrb     r1, [r0]
c031c360  000051e3   cmp      r1, #0
c031c364  8c00000a   beq      #0xc031c59c
c031c368  f4008de2   add      r0, sp, #0xf4
c031c36c  1420a0e3   mov      r2, #0x14
c031c370  0010a0e3   mov      r1, #0
c031c374  37e3f3eb   bl       #0xc0015058
c031c378  d4510cfa   blx      #0xc0630ad0
c031c37c  6400a0e3   mov      r0, #0x64
c031c380  cc540cfa   blx      #0xc06316b8
c031c384  0040a0e1   mov      r4, r0
c031c388  000054e3   cmp      r4, #0
c031c38c  0300000a   beq      #0xc031c3a0
c031c390  ec0f06e3   movw     r0, #0x6fec
c031c394  0e1100e3   movw     r1, #0x10e
c031c398  b5004ce3   movt     r0, #0xc0b5
c031c39c  57d3f3eb   bl       #0xc0011100
c031c3a0  00f020e3   nop      
c031c3a4  201096e5   ldr      r1, [r6, #0x20]
c031c3a8  0211cde5   strb     r1, [sp, #0x102]
c031c3ac  28009de5   ldr      r0, [sp, #0x28]
c031c3b0  78f7ffeb   bl       #0xc031a198
c031c3b4  7000efe6   uxtb     r0, r0
c031c3b8  ba510cfa   blx      #0xc0630aa8
c031c3bc  501b0be3   movw     r1, #0xbb50
c031c3c0  31104ce3   movt     r1, #0xc031
c031c3c4  04118de5   str      r1, [sp, #0x104]
c031c3c8  0b00a0e1   mov      r0, fp
c031c3cc  e30700eb   bl       #0xc031e360
c031c3d0  141090e5   ldr      r1, [r0, #0x14]
c031c3d4  020051e3   cmp      r1, #2
c031c3d8  2c00001a   bne      #0xc031c490
c031c3dc  e0008de2   add      r0, sp, #0xe0
c031c3e0  1420a0e3   mov      r2, #0x14
c031c3e4  0010a0e3   mov      r1, #0
c031c3e8  1ae3f3eb   bl       #0xc0015058
c031c3ec  0010a0e3   mov      r1, #0
c031c3f0  e0108de5   str      r1, [sp, #0xe0]
c031c3f4  e0108de2   add      r1, sp, #0xe0
c031c3f8  0200a0e3   mov      r0, #2
c031c3fc  315f0cfa   blx      #0xc06340c8
c031c400  0110a0e3   mov      r1, #1
c031c404  e0108de5   str      r1, [sp, #0xe0]
c031c408  e0108de2   add      r1, sp, #0xe0
c031c40c  0200a0e3   mov      r0, #2
c031c410  2c5f0cfa   blx      #0xc06340c8
c031c414  481095e5   ldr      r1, [r5, #0x48]
c031c418  010b51e3   cmp      r1, #0x400
c031c41c  4c109505   ldreq    r1, [r5, #0x4c]
c031c420  010b5103   cmpeq    r1, #0x400
c031c424  0d00000a   beq      #0xc031c460
c031c428  50009de5   ldr      r0, [sp, #0x50]
c031c42c  b40fcde1   strh     r0, [sp, #0xf4]
c031c430  001095e5   ldr      r1, [r5]
c031c434  50209de5   ldr      r2, [sp, #0x50]
c031c438  021081e0   add      r1, r1, r2
c031c43c  b61fcde1   strh     r1, [sp, #0xf6]
c031c440  54009de5   ldr      r0, [sp, #0x54]
c031c444  b80fcde1   strh     r0, [sp, #0xf8]
c031c448  041095e5   ldr      r1, [r5, #4]
c031c44c  54209de5   ldr      r2, [sp, #0x54]
c031c450  021081e0   add      r1, r1, r2
c031c454  ba1fcde1   strh     r1, [sp, #0xfa]
c031c458  0210a0e3   mov      r1, #2
c031c45c  0011cde5   strb     r1, [sp, #0x100]
c031c460  b41fdde1   ldrh     r1, [sp, #0xf4]
c031c464  e4108de5   str      r1, [sp, #0xe4]
c031c468  b61fdde1   ldrh     r1, [sp, #0xf6]
c031c46c  e8108de5   str      r1, [sp, #0xe8]
c031c470  b81fdde1   ldrh     r1, [sp, #0xf8]
c031c474  ec108de5   str      r1, [sp, #0xec]
c031c478  ba1fdde1   ldrh     r1, [sp, #0xfa]
c031c47c  f0108de5   str      r1, [sp, #0xf0]
c031c480  e0108de2   add      r1, sp, #0xe0
c031c484  0200a0e3   mov      r0, #2
c031c488  0e5f0cfa   blx      #0xc06340c8
c031c48c  200000ea   b        #0xc031c514
c031c490  cc008de2   add      r0, sp, #0xcc
c031c494  1420a0e3   mov      r2, #0x14
c031c498  0010a0e3   mov      r1, #0
c031c49c  ede2f3eb   bl       #0xc0015058
c031c4a0  0010a0e3   mov      r1, #0
c031c4a4  cc108de5   str      r1, [sp, #0xcc]
c031c4a8  cc108de2   add      r1, sp, #0xcc
c031c4ac  0100a0e3   mov      r0, #1
c031c4b0  045f0cfa   blx      #0xc06340c8
c031c4b4  0110a0e3   mov      r1, #1
c031c4b8  cc108de5   str      r1, [sp, #0xcc]
c031c4bc  cc108de2   add      r1, sp, #0xcc
c031c4c0  0100a0e3   mov      r0, #1
c031c4c4  ff5e0cfa   blx      #0xc06340c8
c031c4c8  481095e5   ldr      r1, [r5, #0x48]
c031c4cc  010b51e3   cmp      r1, #0x400
c031c4d0  4c109505   ldreq    r1, [r5, #0x4c]
c031c4d4  010b5103   cmpeq    r1, #0x400
c031c4d8  0d00000a   beq      #0xc031c514
c031c4dc  50009de5   ldr      r0, [sp, #0x50]
c031c4e0  b40fcde1   strh     r0, [sp, #0xf4]
c031c4e4  001095e5   ldr      r1, [r5]
c031c4e8  50209de5   ldr      r2, [sp, #0x50]
c031c4ec  021081e0   add      r1, r1, r2
c031c4f0  b61fcde1   strh     r1, [sp, #0xf6]
c031c4f4  54009de5   ldr      r0, [sp, #0x54]
c031c4f8  b80fcde1   strh     r0, [sp, #0xf8]
c031c4fc  041095e5   ldr      r1, [r5, #4]
c031c500  54209de5   ldr      r2, [sp, #0x54]
c031c504  021081e0   add      r1, r1, r2
c031c508  ba1fcde1   strh     r1, [sp, #0xfa]
c031c50c  0110a0e3   mov      r1, #1
c031c510  0011cde5   strb     r1, [sp, #0x100]
c031c514  f4008de2   add      r0, sp, #0xf4
c031c518  ec530cfa   blx      #0xc06314d0
c031c51c  0040a0e1   mov      r4, r0
c031c520  000054e3   cmp      r4, #0
c031c524  0300000a   beq      #0xc031c538
c031c528  ec0f06e3   movw     r0, #0x6fec
c031c52c  371100e3   movw     r1, #0x137
c031c530  b5004ce3   movt     r0, #0xc0b5
c031c534  f1d2f3eb   bl       #0xc0011100
c031c538  00f020e3   nop      
c031c53c  0b00a0e1   mov      r0, fp
c031c540  860700eb   bl       #0xc031e360
c031c544  040090e5   ldr      r0, [r0, #4]
c031c548  d6650cfa   blx      #0xc0635ca8
c031c54c  380096e5   ldr      r0, [r6, #0x38]
c031c550  3a540cfa   blx      #0xc0631640
c031c554  0040a0e1   mov      r4, r0
c031c558  000054e3   cmp      r4, #0
c031c55c  0300000a   beq      #0xc031c570
c031c560  ec0f06e3   movw     r0, #0x6fec
c031c564  3a1100e3   movw     r1, #0x13a
c031c568  b5004ce3   movt     r0, #0xc0b5
c031c56c  e3d2f3eb   bl       #0xc0011100
c031c570  00f020e3   nop      
c031c574  11f6f3eb   bl       #0xc0019dc0
c031c578  ac2f06e3   movw     r2, #0x6fac
c031c57c  b5204ce3   movt     r2, #0xc0b5
c031c580  04208de5   str      r2, [sp, #4]
c031c584  382096e5   ldr      r2, [r6, #0x38]
c031c588  0130a0e3   mov      r3, #1
c031c58c  4010a0e3   mov      r1, #0x40
c031c590  00208de5   str      r2, [sp]
c031c594  0020a0e3   mov      r2, #0
c031c598  acf7f3eb   bl       #0xc001a450
c031c59c  0b00a0e1   mov      r0, fp
c031c5a0  6e0700eb   bl       #0xc031e360
c031c5a4  0110d0e5   ldrb     r1, [r0, #1]
c031c5a8  000051e3   cmp      r1, #0
c031c5ac  9b00000a   beq      #0xc031c820
c031c5b0  b8008de2   add      r0, sp, #0xb8
c031c5b4  1420a0e3   mov      r2, #0x14
c031c5b8  0010a0e3   mov      r1, #0
c031c5bc  a5e2f3eb   bl       #0xc0015058
c031c5c0  b8530cfa   blx      #0xc06314a8
c031c5c4  0000a0e3   mov      r0, #0
c031c5c8  4e560cfa   blx      #0xc0631f08
c031c5cc  0040a0e1   mov      r4, r0
c031c5d0  000054e3   cmp      r4, #0
c031c5d4  0300000a   beq      #0xc031c5e8
c031c5d8  ec0f06e3   movw     r0, #0x6fec
c031c5dc  411100e3   movw     r1, #0x141
c031c5e0  b5004ce3   movt     r0, #0xc0b5
c031c5e4  c5d2f3eb   bl       #0xc0011100
c031c5e8  00f020e3   nop      
c031c5ec  201096e5   ldr      r1, [r6, #0x20]
c031c5f0  c610cde5   strb     r1, [sp, #0xc6]
c031c5f4  28009de5   ldr      r0, [sp, #0x28]
c031c5f8  e6f6ffeb   bl       #0xc031a198
c031c5fc  7000efe6   uxtb     r0, r0
c031c600  50530cfa   blx      #0xc0631348
c031c604  f81b0be3   movw     r1, #0xbbf8
c031c608  31104ce3   movt     r1, #0xc031
c031c60c  c8108de5   str      r1, [sp, #0xc8]
c031c610  0b00a0e1   mov      r0, fp
c031c614  510700eb   bl       #0xc031e360
c031c618  181090e5   ldr      r1, [r0, #0x18]
c031c61c  020051e3   cmp      r1, #2
c031c620  2c00001a   bne      #0xc031c6d8
c031c624  a4008de2   add      r0, sp, #0xa4
c031c628  1420a0e3   mov      r2, #0x14
c031c62c  0010a0e3   mov      r1, #0
c031c630  88e2f3eb   bl       #0xc0015058
c031c634  0010a0e3   mov      r1, #0
c031c638  a4108de5   str      r1, [sp, #0xa4]
c031c63c  a4108de2   add      r1, sp, #0xa4
c031c640  0200a0e3   mov      r0, #2
c031c644  9f5e0cfa   blx      #0xc06340c8
c031c648  0110a0e3   mov      r1, #1
c031c64c  a4108de5   str      r1, [sp, #0xa4]
c031c650  a4108de2   add      r1, sp, #0xa4
c031c654  0200a0e3   mov      r0, #2
c031c658  9a5e0cfa   blx      #0xc06340c8
c031c65c  481095e5   ldr      r1, [r5, #0x48]
c031c660  010b51e3   cmp      r1, #0x400
c031c664  4c109505   ldreq    r1, [r5, #0x4c]
c031c668  010b5103   cmpeq    r1, #0x400
c031c66c  0d00000a   beq      #0xc031c6a8
c031c670  50009de5   ldr      r0, [sp, #0x50]
c031c674  b80bcde1   strh     r0, [sp, #0xb8]
c031c678  001095e5   ldr      r1, [r5]
c031c67c  50209de5   ldr      r2, [sp, #0x50]
c031c680  021081e0   add      r1, r1, r2
c031c684  ba1bcde1   strh     r1, [sp, #0xba]
c031c688  54009de5   ldr      r0, [sp, #0x54]
c031c68c  bc0bcde1   strh     r0, [sp, #0xbc]
c031c690  041095e5   ldr      r1, [r5, #4]
c031c694  54209de5   ldr      r2, [sp, #0x54]
c031c698  021081e0   add      r1, r1, r2
c031c69c  be1bcde1   strh     r1, [sp, #0xbe]
c031c6a0  0210a0e3   mov      r1, #2
c031c6a4  c410cde5   strb     r1, [sp, #0xc4]
c031c6a8  b81bdde1   ldrh     r1, [sp, #0xb8]
c031c6ac  a8108de5   str      r1, [sp, #0xa8]
c031c6b0  ba1bdde1   ldrh     r1, [sp, #0xba]
c031c6b4  ac108de5   str      r1, [sp, #0xac]
c031c6b8  bc1bdde1   ldrh     r1, [sp, #0xbc]
c031c6bc  b0108de5   str      r1, [sp, #0xb0]
c031c6c0  be1bdde1   ldrh     r1, [sp, #0xbe]
c031c6c4  b4108de5   str      r1, [sp, #0xb4]
c031c6c8  a4108de2   add      r1, sp, #0xa4
c031c6cc  0200a0e3   mov      r0, #2
c031c6d0  7c5e0cfa   blx      #0xc06340c8
c031c6d4  220000ea   b        #0xc031c764
c031c6d8  90008de2   add      r0, sp, #0x90
c031c6dc  1420a0e3   mov      r2, #0x14
c031c6e0  0010a0e3   mov      r1, #0
c031c6e4  5be2f3eb   bl       #0xc0015058
c031c6e8  0010a0e3   mov      r1, #0
c031c6ec  90108de5   str      r1, [sp, #0x90]
c031c6f0  90108de2   add      r1, sp, #0x90
c031c6f4  0300a0e3   mov      r0, #3
c031c6f8  725e0cfa   blx      #0xc06340c8
c031c6fc  0110a0e3   mov      r1, #1
c031c700  90108de5   str      r1, [sp, #0x90]
c031c704  90108de2   add      r1, sp, #0x90
c031c708  0300a0e3   mov      r0, #3
c031c70c  6d5e0cfa   blx      #0xc06340c8
c031c710  481095e5   ldr      r1, [r5, #0x48]
c031c714  010b51e3   cmp      r1, #0x400
c031c718  4c109505   ldreq    r1, [r5, #0x4c]
c031c71c  010b5103   cmpeq    r1, #0x400
c031c720  0f00000a   beq      #0xc031c764
c031c724  0100a0e3   mov      r0, #1
c031c728  3e520cfa   blx      #0xc0631028
c031c72c  50009de5   ldr      r0, [sp, #0x50]
c031c730  b80bcde1   strh     r0, [sp, #0xb8]
c031c734  001095e5   ldr      r1, [r5]
c031c738  50209de5   ldr      r2, [sp, #0x50]
c031c73c  021081e0   add      r1, r1, r2
c031c740  ba1bcde1   strh     r1, [sp, #0xba]
c031c744  54009de5   ldr      r0, [sp, #0x54]
c031c748  bc0bcde1   strh     r0, [sp, #0xbc]
c031c74c  041095e5   ldr      r1, [r5, #4]
c031c750  54209de5   ldr      r2, [sp, #0x54]
c031c754  021081e0   add      r1, r1, r2
c031c758  be1bcde1   strh     r1, [sp, #0xbe]
c031c75c  0110a0e3   mov      r1, #1
c031c760  c410cde5   strb     r1, [sp, #0xc4]
c031c764  b8008de2   add      r0, sp, #0xb8
c031c768  72550cfa   blx      #0xc0631d38
c031c76c  0040a0e1   mov      r4, r0
c031c770  000054e3   cmp      r4, #0
c031c774  0300000a   beq      #0xc031c788
c031c778  ec0f06e3   movw     r0, #0x6fec
c031c77c  6a1100e3   movw     r1, #0x16a
c031c780  b5004ce3   movt     r0, #0xc0b5
c031c784  5dd2f3eb   bl       #0xc0011100
c031c788  00f020e3   nop      
c031c78c  0b00a0e1   mov      r0, fp
c031c790  f20600eb   bl       #0xc031e360
c031c794  080090e5   ldr      r0, [r0, #8]
c031c798  4c650cfa   blx      #0xc0635cd0
c031c79c  380096e5   ldr      r0, [r6, #0x38]
c031c7a0  2c560cfa   blx      #0xc0632058
c031c7a4  0040a0e1   mov      r4, r0
c031c7a8  000054e3   cmp      r4, #0
c031c7ac  0300000a   beq      #0xc031c7c0
c031c7b0  ec0f06e3   movw     r0, #0x6fec
c031c7b4  6d1100e3   movw     r1, #0x16d
c031c7b8  b5004ce3   movt     r0, #0xc0b5
c031c7bc  4fd2f3eb   bl       #0xc0011100
c031c7c0  00f020e3   nop      
c031c7c4  7df5f3eb   bl       #0xc0019dc0
c031c7c8  bc2f06e3   movw     r2, #0x6fbc
c031c7cc  b5204ce3   movt     r2, #0xc0b5
c031c7d0  04208de5   str      r2, [sp, #4]
c031c7d4  382096e5   ldr      r2, [r6, #0x38]
c031c7d8  0130a0e3   mov      r3, #1
c031c7dc  4010a0e3   mov      r1, #0x40
c031c7e0  00208de5   str      r2, [sp]
c031c7e4  0020a0e3   mov      r2, #0
c031c7e8  18f7f3eb   bl       #0xc001a450
c031c7ec  000095e5   ldr      r0, [r5]
c031c7f0  38008de5   str      r0, [sp, #0x38]
c031c7f4  c410dde5   ldrb     r1, [sp, #0xc4]
c031c7f8  000051e3   cmp      r1, #0
c031c7fc  0400001a   bne      #0xc031c814
c031c800  88008de2   add      r0, sp, #0x88
c031c804  7710a0e3   mov      r1, #0x77
c031c808  144000eb   bl       #0xc032c860
c031c80c  88009de5   ldr      r0, [sp, #0x88]
c031c810  38008de5   str      r0, [sp, #0x38]
c031c814  201096e5   ldr      r1, [r6, #0x20]
c031c818  38009de5   ldr      r0, [sp, #0x38]
c031c81c  d3520cfa   blx      #0xc0631370
c031c820  0b00a0e1   mov      r0, fp
c031c824  cd0600eb   bl       #0xc031e360
c031c828  0210d0e5   ldrb     r1, [r0, #2]
c031c82c  000051e3   cmp      r1, #0
c031c830  6400000a   beq      #0xc031c9c8
c031c834  74008de2   add      r0, sp, #0x74
c031c838  1420a0e3   mov      r2, #0x14
c031c83c  0010a0e3   mov      r1, #0
