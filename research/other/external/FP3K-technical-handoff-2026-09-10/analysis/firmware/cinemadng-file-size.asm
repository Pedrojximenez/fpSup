c03a5300  004095e5   ldr      r4, [r5]
c03a5304  000054e3   cmp      r4, #0
c03a5308  0700000a   beq      #0xc03a532c
c03a530c  00c094e5   ldr      ip, [r4]
c03a5310  0b30a0e1   mov      r3, fp
c03a5314  0a20a0e1   mov      r2, sl
c03a5318  0cc08ce2   add      ip, ip, #0xc
c03a531c  00c09ce5   ldr      ip, [ip]
c03a5320  0710a0e1   mov      r1, r7
c03a5324  0400a0e1   mov      r0, r4
c03a5328  3cff2fe1   blx      ip
c03a532c  045085e2   add      r5, r5, #4
c03a5330  00c09de5   ldr      ip, [sp]
c03a5334  0c0055e1   cmp      r5, ip
c03a5338  f0ffff1a   bne      #0xc03a5300
c03a533c  04d08de2   add      sp, sp, #4
c03a5340  f08fbde8   pop      {r4, r5, r6, r7, r8, sb, sl, fp, pc}
c03a5344  00f020e3   nop      
c03a5348  f04b2de9   push     {r4, r5, r6, r7, r8, sb, fp, lr}
c03a534c  b4d04de2   sub      sp, sp, #0xb4
c03a5350  00b0a0e1   mov      fp, r0
c03a5354  0140a0e1   mov      r4, r1
c03a5358  14208de5   str      r2, [sp, #0x14]
c03a535c  97d2f1eb   bl       #0xc0019dc0
c03a5360  00c0a0e3   mov      ip, #0
c03a5364  0cc08de5   str      ip, [sp, #0xc]
c03a5368  0c10a0e1   mov      r1, ip
c03a536c  02108de9   stmib    sp, {r1, ip}
c03a5370  03c000e3   movw     ip, #3
c03a5374  0030a0e3   mov      r3, #0
c03a5378  bbcb4be3   movt     ip, #0xbbbb
c03a537c  0320a0e1   mov      r2, r3
c03a5380  0215a0e3   mov      r1, #0x800000
c03a5384  00c08de5   str      ip, [sp]
c03a5388  2ed3f1eb   bl       #0xc001a048
c03a538c  10209be5   ldr      r2, [fp, #0x10]
c03a5390  301001e3   movw     r1, #0x1030
c03a5394  041081e0   add      r1, r1, r4
c03a5398  20008de2   add      r0, sp, #0x20
c03a539c  0130a0e3   mov      r3, #1
c03a53a0  0a70ffeb   bl       #0xc03813d0
c03a53a4  0050a0e3   mov      r5, #0
c03a53a8  14009de5   ldr      r0, [sp, #0x14]
c03a53ac  143090e5   ldr      r3, [r0, #0x14]
c03a53b0  483083e2   add      r3, r3, #0x48
c03a53b4  003093e5   ldr      r3, [r3]
c03a53b8  33ff2fe1   blx      r3
c03a53bc  3c3090e5   ldr      r3, [r0, #0x3c]
c03a53c0  10308de5   str      r3, [sp, #0x10]
c03a53c4  10309de5   ldr      r3, [sp, #0x10]
c03a53c8  000053e3   cmp      r3, #0
c03a53cc  0900000a   beq      #0xc03a53f8
c03a53d0  4c6194e5   ldr      r6, [r4, #0x14c]
c03a53d4  14009de5   ldr      r0, [sp, #0x14]
c03a53d8  143090e5   ldr      r3, [r0, #0x14]
c03a53dc  0620a0e1   mov      r2, r6
c03a53e0  54c093e5   ldr      ip, [r3, #0x54]
c03a53e4  023ca0e3   mov      r3, #0x200
c03a53e8  20108de2   add      r1, sp, #0x20
c03a53ec  3cff2fe1   blx      ip
c03a53f0  4c3194e5   ldr      r3, [r4, #0x14c]
c03a53f4  035085e0   add      r5, r5, r3
c03a53f8  14009de5   ldr      r0, [sp, #0x14]
c03a53fc  143090e5   ldr      r3, [r0, #0x14]
c03a5400  483083e2   add      r3, r3, #0x48
c03a5404  003093e5   ldr      r3, [r3]
c03a5408  33ff2fe1   blx      r3
c03a540c  d7d4fceb   bl       #0xc02da770
c03a5410  0030a0e1   mov      r3, r0
c03a5414  0360a0e1   mov      r6, r3
c03a5418  ff3100e3   movw     r3, #0x1ff
c03a541c  033086e0   add      r3, r6, r3
c03a5420  1f30c8e7   bfc      r3, #0, #9
c03a5424  035085e0   add      r5, r5, r3
c03a5428  0500a0e1   mov      r0, r5
c03a542c  5d0100eb   bl       #0xc03a59a8
c03a5430  62d2f1eb   bl       #0xc0019dc0
c03a5434  0030a0e3   mov      r3, #0
c03a5438  03c0a0e1   mov      ip, r3
c03a543c  041000e3   movw     r1, #4
c03a5440  0320a0e1   mov      r2, r3
c03a5444  991949e3   movt     r1, #0x9999
c03a5448  0e108de8   stm      sp, {r1, r2, r3, ip}
c03a544c  0215a0e3   mov      r1, #0x800000
c03a5450  fcd2f1eb   bl       #0xc001a048
c03a5454  0c30dbe5   ldrb     r3, [fp, #0xc]
c03a5458  000053e3   cmp      r3, #0
c03a545c  0900000a   beq      #0xc03a5488
c03a5460  0c30a0e3   mov      r3, #0xc
c03a5464  048101e3   movw     r8, #0x1104
c03a5468  043088e7   str      r3, [r8, r4]
c03a546c  fc8001e3   movw     r8, #0x10fc
c03a5470  041098e7   ldr      r1, [r8, r4]
c03a5474  0320a0e3   mov      r2, #3
c03a5478  0030a0e3   mov      r3, #0
c03a547c  0b00a0e1   mov      r0, fp
c03a5480  92ffffeb   bl       #0xc03a52d0
c03a5484  00f020e3   nop      
c03a5488  0410a0e1   mov      r1, r4
c03a548c  20008de2   add      r0, sp, #0x20
c03a5490  52d60beb   bl       #0xc069ade0
c03a5494  0060a0e1   mov      r6, r0
c03a5498  0170a0e1   mov      r7, r1
c03a549c  0d30dbe5   ldrb     r3, [fp, #0xd]
c03a54a0  000053e3   cmp      r3, #0
c03a54a4  1200001a   bne      #0xc03a54f4
c03a54a8  073096e1   orrs     r3, r6, r7
c03a54ac  0100000a   beq      #0xc03a54b8
c03a54b0  0030a0e3   mov      r3, #0
c03a54b4  000000ea   b        #0xc03a54bc
c03a54b8  0030e0e3   mvn      r3, #0
c03a54bc  0310a0e1   mov      r1, r3
c03a54c0  0400a0e1   mov      r0, r4
c03a54c4  410000eb   bl       #0xc03a55d0
c03a54c8  0130a0e3   mov      r3, #1
c03a54cc  18308de5   str      r3, [sp, #0x18]
c03a54d0  0030a0e3   mov      r3, #0
c03a54d4  000055e3   cmp      r5, #0
c03a54d8  1c308de5   str      r3, [sp, #0x1c]
c03a54dc  0200009a   bls      #0xc03a54ec
c03a54e0  0030a0e3   mov      r3, #0
c03a54e4  18508de5   str      r5, [sp, #0x18]
c03a54e8  1c308de5   str      r3, [sp, #0x1c]
c03a54ec  18609de5   ldr      r6, [sp, #0x18]
c03a54f0  1c709de5   ldr      r7, [sp, #0x1c]
c03a54f4  073096e1   orrs     r3, r6, r7
c03a54f8  1600001a   bne      #0xc03a5558
c03a54fc  0d30a0e3   mov      r3, #0xd
c03a5500  048101e3   movw     r8, #0x1104
c03a5504  043088e7   str      r3, [r8, r4]
c03a5508  fc8001e3   movw     r8, #0x10fc
c03a550c  041098e7   ldr      r1, [r8, r4]
c03a5510  0420a0e3   mov      r2, #4
c03a5514  0130a0e3   mov      r3, #1
c03a5518  0b00a0e1   mov      r0, fp
c03a551c  6bffffeb   bl       #0xc03a52d0
c03a5520  26d2f1eb   bl       #0xc0019dc0
c03a5524  0020a0e3   mov      r2, #0
c03a5528  0230a0e1   mov      r3, r2
c03a552c  0210a0e1   mov      r1, r2
c03a5530  0e008de9   stmib    sp, {r1, r2, r3}
c03a5534  fc8001e3   movw     r8, #0x10fc
c03a5538  04c098e7   ldr      ip, [r8, r4]
c03a553c  0330a0e3   mov      r3, #3
c03a5540  0215a0e3   mov      r1, #0x800000
c03a5544  00c08de5   str      ip, [sp]
c03a5548  bed2f1eb   bl       #0xc001a048
c03a554c  0050a0e3   mov      r5, #0
c03a5550  0c0000ea   b        #0xc03a5588
c03a5554  00f020e3   nop      
c03a5558  0c30dbe5   ldrb     r3, [fp, #0xc]
c03a555c  000053e3   cmp      r3, #0
c03a5560  0800001a   bne      #0xc03a5588
c03a5564  0d30a0e3   mov      r3, #0xd
c03a5568  048101e3   movw     r8, #0x1104
c03a556c  043088e7   str      r3, [r8, r4]
c03a5570  fc8001e3   movw     r8, #0x10fc
c03a5574  041098e7   ldr      r1, [r8, r4]
c03a5578  0420a0e3   mov      r2, #4
c03a557c  0030a0e3   mov      r3, #0
c03a5580  0b00a0e1   mov      r0, fp
c03a5584  51ffffeb   bl       #0xc03a52d0
c03a5588  0cd2f1eb   bl       #0xc0019dc0
c03a558c  0c508de5   str      r5, [sp, #0xc]
c03a5590  68c094e5   ldr      ip, [r4, #0x68]
c03a5594  fc8001e3   movw     r8, #0x10fc
c03a5598  0020a0e3   mov      r2, #0
c03a559c  08c08de5   str      ip, [sp, #8]
c03a55a0  04c098e7   ldr      ip, [r8, r4]
c03a55a4  0130a0e3   mov      r3, #1
c03a55a8  0215a0e3   mov      r1, #0x800000
c03a55ac  04c08de5   str      ip, [sp, #4]
c03a55b0  05c000e3   movw     ip, #5
c03a55b4  99c949e3   movt     ip, #0x9999
c03a55b8  00c08de5   str      ip, [sp]
c03a55bc  a1d2f1eb   bl       #0xc001a048
c03a55c0  0530a0e1   mov      r3, r5
c03a55c4  0300a0e1   mov      r0, r3
c03a55c8  b4d08de2   add      sp, sp, #0xb4
c03a55cc  f08bbde8   pop      {r4, r5, r6, r7, r8, sb, fp, pc}
c03a55d0  f0412de9   push     {r4, r5, r6, r7, r8, lr}
c03a55d4  10d04de2   sub      sp, sp, #0x10
c03a55d8  0060a0e1   mov      r6, r0
c03a55dc  0170a0e1   mov      r7, r1
c03a55e0  000100eb   bl       #0xc03a59e8
c03a55e4  f5d1f1eb   bl       #0xc0019dc0
c03a55e8  0050a0e3   mov      r5, #0
c03a55ec  0580a0e1   mov      r8, r5
c03a55f0  303000e3   movw     r3, #0x30
c03a55f4  0540a0e1   mov      r4, r5
c03a55f8  993949e3   movt     r3, #0x9999
c03a55fc  38018de8   stm      sp, {r3, r4, r5, r8}
c03a5600  0530a0e1   mov      r3, r5
c03a5604  0215a0e3   mov      r1, #0x800000
c03a5608  0320a0e1   mov      r2, r3
