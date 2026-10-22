c0374220  04e02de5   str      lr, [sp, #-4]!
c0374224  d80000e3   movw     r0, #0xd8
c0374228  52034ce3   movt     r0, #0xc352
c037422c  977bf2eb   bl       #0xc0013090
c0374230  000050e3   cmp      r0, #0
c0374234  0800000a   beq      #0xc037425c
c0374238  440f0fe3   movw     r0, #0xff44
c037423c  51034ce3   movt     r0, #0xc351
c0374240  e2ffffeb   bl       #0xc03741d0
c0374244  7c030fe3   movw     r0, #0xf37c
c0374248  f1024ce3   movt     r0, #0xc2f1
c037424c  287cf2eb   bl       #0xc00132f4
c0374250  d80000e3   movw     r0, #0xd8
c0374254  52034ce3   movt     r0, #0xc352
c0374258  e17bf2eb   bl       #0xc00131e4
c037425c  440f0fe3   movw     r0, #0xff44
c0374260  51034ce3   movt     r0, #0xc351
c0374264  04f09de4   pop      {pc}
c0374268  f0492de9   push     {r4, r5, r6, r7, r8, fp, lr}
c037426c  44d04de2   sub      sp, sp, #0x44
c0374270  0050a0e1   mov      r5, r0
c0374274  0170a0e1   mov      r7, r1
c0374278  2c208de5   str      r2, [sp, #0x2c]
c037427c  0030e0e3   mvn      r3, #0
c0374280  883185e5   str      r3, [r5, #0x188]
c0374284  904809e3   movw     r4, #0x9890
c0374288  b9404ce3   movt     r4, #0xc0b9
c037428c  cb96f2eb   bl       #0xc0019dc0
c0374290  0030a0e1   mov      r3, r0
c0374294  00408de5   str      r4, [sp]
c0374298  0300a0e1   mov      r0, r3
c037429c  0030a0e3   mov      r3, #0
c03742a0  0410a0e3   mov      r1, #4
c03742a4  0020a0e3   mov      r2, #0
c03742a8  f697f2eb   bl       #0xc001a288
c03742ac  9031d5e5   ldrb     r3, [r5, #0x190]
c03742b0  000053e3   cmp      r3, #0
c03742b4  0100000a   beq      #0xc03742c0
c03742b8  883195e5   ldr      r3, [r5, #0x188]
c03742bc  360200ea   b        #0xc0374b9c
c03742c0  010057e3   cmp      r7, #1
c03742c4  6030a003   moveq    r3, #0x60
c03742c8  3f30a013   movne    r3, #0x3f
c03742cc  0340a0e1   mov      r4, r3
c03742d0  010057e3   cmp      r7, #1
c03742d4  0130a003   moveq    r3, #1
c03742d8  0630a013   movne    r3, #6
c03742dc  0360a0e1   mov      r6, r3
c03742e0  b6fdffeb   bl       #0xc03739c0
c03742e4  0030a0e1   mov      r3, r0
c03742e8  60c064e2   rsb      ip, r4, #0x60
c03742ec  0cc086e0   add      ip, r6, ip
c03742f0  0c0053e1   cmp      r3, ip
c03742f4  1100008a   bhi      #0xc0374340
c03742f8  090057e3   cmp      r7, #9
c03742fc  0330a013   movne    r3, #3
c0374300  0130a003   moveq    r3, #1
c0374304  0340a0e1   mov      r4, r3
c0374308  8c6809e3   movw     r6, #0x988c
c037430c  b9604ce3   movt     r6, #0xc0b9
c0374310  aa96f2eb   bl       #0xc0019dc0
c0374314  0030a0e1   mov      r3, r0
c0374318  03c0a0e1   mov      ip, r3
c037431c  00608de5   str      r6, [sp]
c0374320  0430a0e1   mov      r3, r4
c0374324  0c00a0e1   mov      r0, ip
c0374328  0410a0e3   mov      r1, #4
c037432c  0020a0e3   mov      r2, #0
c0374330  d497f2eb   bl       #0xc001a288
c0374334  883195e5   ldr      r3, [r5, #0x188]
c0374338  170200ea   b        #0xc0374b9c
c037433c  00f020e3   nop      
c0374340  0710a0e1   mov      r1, r7
c0374344  0500a0e1   mov      r0, r5
c0374348  160200eb   bl       #0xc0374ba8
c037434c  0030a0e1   mov      r3, r0
c0374350  000053e3   cmp      r3, #0
c0374354  0f00000a   beq      #0xc0374398
c0374358  fcb000eb   bl       #0xc03a0750
c037435c  0030a0e1   mov      r3, r0
c0374360  0300a0e1   mov      r0, r3
c0374364  83b300eb   bl       #0xc03a1178
c0374368  0030a0e1   mov      r3, r0
c037436c  040053e3   cmp      r3, #4
c0374370  0800001a   bne      #0xc0374398
c0374374  db8df3eb   bl       #0xc0057ae8
c0374378  0030a0e1   mov      r3, r0
c037437c  0300a0e1   mov      r0, r3
c0374380  ee8ff3eb   bl       #0xc0058340
c0374384  0030a0e1   mov      r3, r0
c0374388  010053e3   cmp      r3, #1
c037438c  0100001a   bne      #0xc0374398
c0374390  883195e5   ldr      r3, [r5, #0x188]
c0374394  000200ea   b        #0xc0374b9c
c0374398  1c3101e3   movw     r3, #0x111c
c037439c  0300a0e1   mov      r0, r3
c03743a0  363000eb   bl       #0xc0380480
c03743a4  0030a0e1   mov      r3, r0
c03743a8  0340a0e1   mov      r4, r3
c03743ac  000054e3   cmp      r4, #0
c03743b0  0400000a   beq      #0xc03743c8
c03743b4  0400a0e1   mov      r0, r4
c03743b8  8cfdffeb   bl       #0xc03739f0
c03743bc  0430a0e1   mov      r3, r4
c03743c0  0430a0e1   mov      r3, r4
c03743c4  000000ea   b        #0xc03743cc
c03743c8  0030a0e3   mov      r3, #0
c03743cc  04308de5   str      r3, [sp, #4]
c03743d0  2c409de5   ldr      r4, [sp, #0x2c]
c03743d4  000054e3   cmp      r4, #0
c03743d8  0500001a   bne      #0xc03743f4
c03743dc  ad4afaeb   bl       #0xc0206e98
c03743e0  0030a0e1   mov      r3, r0
c03743e4  0300a0e1   mov      r0, r3
c03743e8  264bfaeb   bl       #0xc0207088
c03743ec  0030a0e1   mov      r3, r0
c03743f0  0340a0e1   mov      r4, r3
c03743f4  04309de5   ldr      r3, [sp, #4]
c03743f8  00c0a0e3   mov      ip, #0
c03743fc  048101e3   movw     r8, #0x1104
c0374400  038088e0   add      r8, r8, r3
c0374404  00c088e5   str      ip, [r8]
c0374408  04309de5   ldr      r3, [sp, #4]
c037440c  01c0a0e3   mov      ip, #1
c0374410  00c0c3e5   strb     ip, [r3]
c0374414  04309de5   ldr      r3, [sp, #4]
c0374418  047083e5   str      r7, [r3, #4]
c037441c  04309de5   ldr      r3, [sp, #4]
c0374420  00c0a0e3   mov      ip, #0
c0374424  bbc7c3e5   strb     ip, [r3, #0x7bb]
c0374428  04609de5   ldr      r6, [sp, #4]
c037442c  894003eb   bl       #0xc0444658
c0374430  0030a0e1   mov      r3, r0
c0374434  0300a0e1   mov      r0, r3
c0374438  0110a0e3   mov      r1, #1
c037443c  954003eb   bl       #0xc0444698
c0374440  0030a0e1   mov      r3, r0
c0374444  743186e5   str      r3, [r6, #0x174]
c0374448  04309de5   ldr      r3, [sp, #4]
c037444c  043093e5   ldr      r3, [r3, #4]
c0374450  010053e3   cmp      r3, #1
c0374454  3300001a   bne      #0xc0374528
c0374458  44d500eb   bl       #0xc03a9970
c037445c  0030a0e1   mov      r3, r0
c0374460  0300a0e1   mov      r0, r3
c0374464  75db00eb   bl       #0xc03ab240
c0374468  0030a0e1   mov      r3, r0
c037446c  0c3093e5   ldr      r3, [r3, #0xc]
c0374470  000053e3   cmp      r3, #0
c0374474  0300000a   beq      #0xc0374488
c0374478  ac0809e3   movw     r0, #0x98ac
c037447c  b9004ce3   movt     r0, #0xc0b9
c0374480  011ca0e3   mov      r1, #0x100
c0374484  1d73f2eb   bl       #0xc0011100
c0374488  00f020e3   nop      
c037448c  dbb5f2eb   bl       #0xc0021c00
c0374490  0030a0e1   mov      r3, r0
c0374494  0300a0e1   mov      r0, r3
c0374498  e8b5f2eb   bl       #0xc0021c40
c037449c  0030a0e1   mov      r3, r0
c03744a0  0320a0e1   mov      r2, r3
c03744a4  08008de2   add      r0, sp, #8
c03744a8  0330a0e3   mov      r3, #3
c03744ac  0210a0e3   mov      r1, #2
c03744b0  220b03eb   bl       #0xc0437140
c03744b4  08309de5   ldr      r3, [sp, #8]
c03744b8  0310a0e1   mov      r1, r3
c03744bc  04309de5   ldr      r3, [sp, #4]
c03744c0  100083e2   add      r0, r3, #0x10
c03744c4  abc5fdeb   bl       #0xc02e5b78
c03744c8  04609de5   ldr      r6, [sp, #4]
c03744cc  cbb5f2eb   bl       #0xc0021c00
c03744d0  0030a0e1   mov      r3, r0
c03744d4  0300a0e1   mov      r0, r3
c03744d8  d8b5f2eb   bl       #0xc0021c40
c03744dc  0030a0e1   mov      r3, r0
c03744e0  0320a0e1   mov      r2, r3
c03744e4  0330a0e3   mov      r3, #3
c03744e8  0010a0e3   mov      r1, #0
c03744ec  0200a0e3   mov      r0, #2
c03744f0  e00a03eb   bl       #0xc0437078
c03744f4  0030a0e1   mov      r3, r0
c03744f8  603086e5   str      r3, [r6, #0x60]
c03744fc  08309de5   ldr      r3, [sp, #8]
c0374500  04c09de5   ldr      ip, [sp, #4]
c0374504  b83093e5   ldr      r3, [r3, #0xb8]
c0374508  64308ce5   str      r3, [ip, #0x64]
c037450c  04309de5   ldr      r3, [sp, #4]
c0374510  55cba0e3   mov      ip, #0x15400
c0374514  28c183e5   str      ip, [r3, #0x128]
c0374518  08008de2   add      r0, sp, #8
c037451c  0210a0e3   mov      r1, #2
c0374520  22eafaeb   bl       #0xc022edb0
c0374524  eb0000ea   b        #0xc03748d8
c0374528  04309de5   ldr      r3, [sp, #4]
c037452c  043093e5   ldr      r3, [r3, #4]
c0374530  060053e3   cmp      r3, #6
c0374534  0100001a   bne      #0xc0374540
c0374538  e60000ea   b        #0xc03748d8
c037453c  00f020e3   nop      
c0374540  04309de5   ldr      r3, [sp, #4]
c0374544  043093e5   ldr      r3, [r3, #4]
c0374548  090053e3   cmp      r3, #9
c037454c  5b00001a   bne      #0xc03746c0
c0374550  aab5f2eb   bl       #0xc0021c00
c0374554  0030a0e1   mov      r3, r0
c0374558  0300a0e1   mov      r0, r3
c037455c  b7b5f2eb   bl       #0xc0021c40
c0374560  0030a0e1   mov      r3, r0
c0374564  0320a0e1   mov      r2, r3
c0374568  14008de2   add      r0, sp, #0x14
c037456c  0330a0e3   mov      r3, #3
c0374570  0410a0e3   mov      r1, #4
c0374574  f10a03eb   bl       #0xc0437140
c0374578  14309de5   ldr      r3, [sp, #0x14]
c037457c  0310a0e1   mov      r1, r3
c0374580  04309de5   ldr      r3, [sp, #4]
c0374584  100083e2   add      r0, r3, #0x10
c0374588  7ac5fdeb   bl       #0xc02e5b78
c037458c  04609de5   ldr      r6, [sp, #4]
c0374590  9ab5f2eb   bl       #0xc0021c00
c0374594  0030a0e1   mov      r3, r0
c0374598  0300a0e1   mov      r0, r3
c037459c  a7b5f2eb   bl       #0xc0021c40
c03745a0  0030a0e1   mov      r3, r0
c03745a4  0320a0e1   mov      r2, r3
c03745a8  0330a0e3   mov      r3, #3
c03745ac  0010a0e3   mov      r1, #0
c03745b0  0400a0e3   mov      r0, #4
c03745b4  af0a03eb   bl       #0xc0437078
c03745b8  0030a0e1   mov      r3, r0
c03745bc  603086e5   str      r3, [r6, #0x60]
c03745c0  14309de5   ldr      r3, [sp, #0x14]
c03745c4  04c09de5   ldr      ip, [sp, #4]
c03745c8  b83093e5   ldr      r3, [r3, #0xb8]
c03745cc  64308ce5   str      r3, [ip, #0x64]
c03745d0  04309de5   ldr      r3, [sp, #4]
c03745d4  1cc094e5   ldr      ip, [r4, #0x1c]
c03745d8  206094e5   ldr      r6, [r4, #0x20]
c03745dc  58c083e5   str      ip, [r3, #0x58]
c03745e0  5c6083e5   str      r6, [r3, #0x5c]
c03745e4  0410a0e1   mov      r1, r4
c03745e8  0c008de2   add      r0, sp, #0xc
c03745ec  e7c00ceb   bl       #0xc06a4990
c03745f0  0c309de5   ldr      r3, [sp, #0xc]
c03745f4  00c0a0e3   mov      ip, #0
c03745f8  0cc08de5   str      ip, [sp, #0xc]
c03745fc  04c09de5   ldr      ip, [sp, #4]
c0374600  38318ce5   str      r3, [ip, #0x138]
c0374604  0c008de2   add      r0, sp, #0xc
c0374608  0210a0e3   mov      r1, #2
c037460c  252f00eb   bl       #0xc03802a8
c0374610  04309de5   ldr      r3, [sp, #4]
c0374614  01c0a0e3   mov      ip, #1
c0374618  c0c183e5   str      ip, [r3, #0x1c0]
c037461c  04309de5   ldr      r3, [sp, #4]
c0374620  00c0a0e3   mov      ip, #0
c0374624  c4c183e5   str      ip, [r3, #0x1c4]
c0374628  1a4afaeb   bl       #0xc0206e98
c037462c  0030a0e1   mov      r3, r0
c0374630  0300a0e1   mov      r0, r3
c0374634  934afaeb   bl       #0xc0207088
c0374638  0030a0e1   mov      r3, r0
c037463c  04c09de5   ldr      ip, [sp, #4]
c0374640  cc3293e5   ldr      r3, [r3, #0x2cc]
c0374644  c83f8ce5   str      r3, [ip, #0xfc8]
c0374648  240d08e3   movw     r0, #0x8d24
c037464c  58034ce3   movt     r0, #0xc358
c0374650  8e7af2eb   bl       #0xc0013090
c0374654  0030a0e1   mov      r3, r0
c0374658  000053e3   cmp      r3, #0
c037465c  0500000a   beq      #0xc0374678
c0374660  000d08e3   movw     r0, #0x8d00
c0374664  58034ce3   movt     r0, #0xc358
c0374668  22d000eb   bl       #0xc03a86f8
c037466c  240d08e3   movw     r0, #0x8d24
c0374670  58034ce3   movt     r0, #0xc358
c0374674  da7af2eb   bl       #0xc00131e4
c0374678  003d08e3   movw     r3, #0x8d00
c037467c  58334ce3   movt     r3, #0xc358
c0374680  10108de2   add      r1, sp, #0x10
c0374684  0300a0e1   mov      r0, r3
c0374688  0620a0e3   mov      r2, #6
c037468c  57d000eb   bl       #0xc03a87f0
c0374690  10108de2   add      r1, sp, #0x10
c0374694  04309de5   ldr      r3, [sp, #4]
c0374698  520f83e2   add      r0, r3, #0x148
c037469c  bd2e00eb   bl       #0xc0380198
c03746a0  10008de2   add      r0, sp, #0x10
c03746a4  0210a0e3   mov      r1, #2
c03746a8  2a2f00eb   bl       #0xc0380358
c03746ac  14008de2   add      r0, sp, #0x14
c03746b0  0210a0e3   mov      r1, #2
c03746b4  bde9faeb   bl       #0xc022edb0
c03746b8  860000ea   b        #0xc03748d8
c03746bc  00f020e3   nop      
c03746c0  0130a0e3   mov      r3, #1
c03746c4  48c094e5   ldr      ip, [r4, #0x48]
c03746c8  01005ce3   cmp      ip, #1
c03746cc  0b00000a   beq      #0xc0374700
c03746d0  04c09de5   ldr      ip, [sp, #4]
c03746d4  04c09ce5   ldr      ip, [ip, #4]
c03746d8  08005ce3   cmp      ip, #8
c03746dc  0700000a   beq      #0xc0374700
c03746e0  04c09de5   ldr      ip, [sp, #4]
c03746e4  04c09ce5   ldr      ip, [ip, #4]
c03746e8  0b005ce3   cmp      ip, #0xb
c03746ec  0300000a   beq      #0xc0374700
c03746f0  04c09de5   ldr      ip, [sp, #4]
c03746f4  04c09ce5   ldr      ip, [ip, #4]
c03746f8  0c005ce3   cmp      ip, #0xc
c03746fc  0030a013   movne    r3, #0
c0374700  013023e2   eor      r3, r3, #1
c0374704  7330efe6   uxtb     r3, r3
c0374708  03b0a0e1   mov      fp, r3
c037470c  00005be3   cmp      fp, #0
c0374710  0a00000a   beq      #0xc0374740
c0374714  0500a0e1   mov      r0, r5
c0374718  b20300eb   bl       #0xc03755e8
c037471c  0030a0e1   mov      r3, r0
c0374720  000053e3   cmp      r3, #0
c0374724  0500001a   bne      #0xc0374740
c0374728  886195e5   ldr      r6, [r5, #0x188]
c037472c  04008de2   add      r0, sp, #4
c0374730  0210a0e3   mov      r1, #2
c0374734  f32e00eb   bl       #0xc0380308
c0374738  0630a0e1   mov      r3, r6
c037473c  160100ea   b        #0xc0374b9c
c0374740  2eb5f2eb   bl       #0xc0021c00
c0374744  0030a0e1   mov      r3, r0
c0374748  0300a0e1   mov      r0, r3
c037474c  3bb5f2eb   bl       #0xc0021c40
c0374750  0030a0e1   mov      r3, r0
c0374754  0320a0e1   mov      r2, r3
c0374758  20008de2   add      r0, sp, #0x20
c037475c  0330a0e3   mov      r3, #3
c0374760  0310a0e3   mov      r1, #3
c0374764  750a03eb   bl       #0xc0437140
c0374768  20309de5   ldr      r3, [sp, #0x20]
c037476c  0310a0e1   mov      r1, r3
c0374770  04309de5   ldr      r3, [sp, #4]
c0374774  100083e2   add      r0, r3, #0x10
c0374778  fec4fdeb   bl       #0xc02e5b78
c037477c  04609de5   ldr      r6, [sp, #4]
c0374780  1eb5f2eb   bl       #0xc0021c00
c0374784  0030a0e1   mov      r3, r0
c0374788  0300a0e1   mov      r0, r3
c037478c  2bb5f2eb   bl       #0xc0021c40
c0374790  0030a0e1   mov      r3, r0
c0374794  0320a0e1   mov      r2, r3
c0374798  0330a0e3   mov      r3, #3
c037479c  0010a0e3   mov      r1, #0
c03747a0  0300a0e3   mov      r0, #3
c03747a4  330a03eb   bl       #0xc0437078
c03747a8  0030a0e1   mov      r3, r0
c03747ac  603086e5   str      r3, [r6, #0x60]
c03747b0  20309de5   ldr      r3, [sp, #0x20]
c03747b4  04c09de5   ldr      ip, [sp, #4]
c03747b8  b83093e5   ldr      r3, [r3, #0xb8]
c03747bc  64308ce5   str      r3, [ip, #0x64]
c03747c0  04309de5   ldr      r3, [sp, #4]
c03747c4  1cc094e5   ldr      ip, [r4, #0x1c]
c03747c8  206094e5   ldr      r6, [r4, #0x20]
c03747cc  58c083e5   str      ip, [r3, #0x58]
c03747d0  5c6083e5   str      r6, [r3, #0x5c]
c03747d4  30c08de2   add      ip, sp, #0x30
c03747d8  986809e3   movw     r6, #0x9898
c03747dc  b9604ce3   movt     r6, #0xc0b9
c03747e0  0b00b6e8   ldm      r6!, {r0, r1, r3}
c03747e4  0b00ace8   stm      ip!, {r0, r1, r3}
c03747e8  030096e8   ldm      r6, {r0, r1}
c03747ec  03008ce8   stm      ip, {r0, r1}
c03747f0  924d00eb   bl       #0xc0387e40
c03747f4  0030a0e1   mov      r3, r0
c03747f8  0300a0e1   mov      r0, r3
c03747fc  994e00eb   bl       #0xc0388268
c0374800  0030a0e1   mov      r3, r0
c0374804  3830cde5   strb     r3, [sp, #0x38]
c0374808  8c4d00eb   bl       #0xc0387e40
c037480c  0030a0e1   mov      r3, r0
c0374810  0300a0e1   mov      r0, r3
c0374814  334f00eb   bl       #0xc03884e8
c0374818  0030a0e1   mov      r3, r0
c037481c  40308de5   str      r3, [sp, #0x40]
c0374820  04309de5   ldr      r3, [sp, #4]
c0374824  5ecf83e2   add      ip, r3, #0x178
c0374828  30608de2   add      r6, sp, #0x30
c037482c  0b00b6e8   ldm      r6!, {r0, r1, r3}
c0374830  0b00ace8   stm      ip!, {r0, r1, r3}
c0374834  030096e8   ldm      r6, {r0, r1}
c0374838  03008ce8   stm      ip, {r0, r1}
c037483c  0410a0e1   mov      r1, r4
c0374840  18008de2   add      r0, sp, #0x18
c0374844  51c00ceb   bl       #0xc06a4990
c0374848  18309de5   ldr      r3, [sp, #0x18]
c037484c  00c0a0e3   mov      ip, #0
c0374850  18c08de5   str      ip, [sp, #0x18]
c0374854  04c09de5   ldr      ip, [sp, #4]
c0374858  38318ce5   str      r3, [ip, #0x138]
c037485c  18008de2   add      r0, sp, #0x18
c0374860  0210a0e3   mov      r1, #2
c0374864  8f2e00eb   bl       #0xc03802a8
c0374868  240d08e3   movw     r0, #0x8d24
c037486c  58034ce3   movt     r0, #0xc358
c0374870  067af2eb   bl       #0xc0013090
c0374874  0030a0e1   mov      r3, r0
c0374878  000053e3   cmp      r3, #0
c037487c  0500000a   beq      #0xc0374898
c0374880  000d08e3   movw     r0, #0x8d00
c0374884  58034ce3   movt     r0, #0xc358
c0374888  9acf00eb   bl       #0xc03a86f8
c037488c  240d08e3   movw     r0, #0x8d24
c0374890  58034ce3   movt     r0, #0xc358
c0374894  527af2eb   bl       #0xc00131e4
c0374898  003d08e3   movw     r3, #0x8d00
c037489c  58334ce3   movt     r3, #0xc358
c03748a0  1c108de2   add      r1, sp, #0x1c
c03748a4  0300a0e1   mov      r0, r3
c03748a8  0620a0e3   mov      r2, #6
c03748ac  cfcf00eb   bl       #0xc03a87f0
c03748b0  1c108de2   add      r1, sp, #0x1c
c03748b4  04309de5   ldr      r3, [sp, #4]
c03748b8  520f83e2   add      r0, r3, #0x148
c03748bc  352e00eb   bl       #0xc0380198
c03748c0  1c008de2   add      r0, sp, #0x1c
c03748c4  0210a0e3   mov      r1, #2
c03748c8  a22e00eb   bl       #0xc0380358
c03748cc  20008de2   add      r0, sp, #0x20
c03748d0  0210a0e3   mov      r1, #2
c03748d4  35e9faeb   bl       #0xc022edb0
c03748d8  04309de5   ldr      r3, [sp, #4]
c03748dc  28c094e5   ldr      ip, [r4, #0x28]
c03748e0  50c083e5   str      ip, [r3, #0x50]
c03748e4  04309de5   ldr      r3, [sp, #4]
c03748e8  48c094e5   ldr      ip, [r4, #0x48]
c03748ec  08c083e5   str      ip, [r3, #8]
c03748f0  04309de5   ldr      r3, [sp, #4]
c03748f4  30c094e5   ldr      ip, [r4, #0x30]
c03748f8  0cc083e5   str      ip, [r3, #0xc]
c03748fc  04309de5   ldr      r3, [sp, #4]
c0374900  adc0d4e5   ldrb     ip, [r4, #0xad]
c0374904  608001e3   movw     r8, #0x1060
c0374908  038088e0   add      r8, r8, r3
c037490c  00c0c8e5   strb     ip, [r8]
c0374910  04309de5   ldr      r3, [sp, #4]
c0374914  b0c094e5   ldr      ip, [r4, #0xb0]
c0374918  648001e3   movw     r8, #0x1064
c037491c  038088e0   add      r8, r8, r3
c0374920  00c088e5   str      ip, [r8]
c0374924  04309de5   ldr      r3, [sp, #4]
c0374928  a0c094e5   ldr      ip, [r4, #0xa0]
c037492c  f88001e3   movw     r8, #0x10f8
c0374930  038088e0   add      r8, r8, r3
c0374934  00c088e5   str      ip, [r8]
c0374938  04309de5   ldr      r3, [sp, #4]
c037493c  00c0e0e3   mvn      ip, #0
c0374940  188101e3   movw     r8, #0x1118
c0374944  038088e0   add      r8, r8, r3
c0374948  00c088e5   str      ip, [r8]
c037494c  04309de5   ldr      r3, [sp, #4]
c0374950  01c0a0e3   mov      ip, #1
c0374954  c4cfc3e5   strb     ip, [r3, #0xfc4]
c0374958  0710a0e1   mov      r1, r7
c037495c  0500a0e1   mov      r0, r5
c0374960  900000eb   bl       #0xc0374ba8
c0374964  0030a0e1   mov      r3, r0
c0374968  000053e3   cmp      r3, #0
c037496c  7c00000a   beq      #0xc0374b64
c0374970  76af00eb   bl       #0xc03a0750
c0374974  0030a0e1   mov      r3, r0
c0374978  0300a0e1   mov      r0, r3
c037497c  fdb100eb   bl       #0xc03a1178
c0374980  0030a0e1   mov      r3, r0
c0374984  040053e3   cmp      r3, #4
c0374988  7500000a   beq      #0xc0374b64
c037498c  0060a0e3   mov      r6, #0
c0374990  0730a0e1   mov      r3, r7
c0374994  013053e2   subs     r3, r3, #1
c0374998  1a00000a   beq      #0xc0374a08
c037499c  083053e2   subs     r3, r3, #8
c03749a0  2a00001a   bne      #0xc0374a50
c03749a4  04309de5   ldr      r3, [sp, #4]
c03749a8  38c193e5   ldr      ip, [r3, #0x138]
c03749ac  08309ce5   ldr      r3, [ip, #8]
c03749b0  143083e2   add      r3, r3, #0x14
c03749b4  003093e5   ldr      r3, [r3]
c03749b8  0c00a0e1   mov      r0, ip
c03749bc  33ff2fe1   blx      r3
c03749c0  0030a0e1   mov      r3, r0
c03749c4  03c0a0e1   mov      ip, r3
c03749c8  04e09de5   ldr      lr, [sp, #4]
c03749cc  04309de5   ldr      r3, [sp, #4]
c03749d0  283193e5   ldr      r3, [r3, #0x128]
c03749d4  0c3083e0   add      r3, r3, ip
c03749d8  fc3f8ee5   str      r3, [lr, #0xffc]
c03749dc  0fbf00eb   bl       #0xc03a4620
c03749e0  0030a0e1   mov      r3, r0
c03749e4  04c09de5   ldr      ip, [sp, #4]
c03749e8  fc1f9ce5   ldr      r1, [ip, #0xffc]
c03749ec  0300a0e1   mov      r0, r3
c03749f0  42bf00eb   bl       #0xc03a4700
c03749f4  0030a0e1   mov      r3, r0
c03749f8  000053e3   cmp      r3, #0
c03749fc  0160a003   moveq    r6, #1
c0374a00  0060a013   movne    r6, #0
c0374a04  430000ea   b        #0xc0374b18
c0374a08  04bf00eb   bl       #0xc03a4620
c0374a0c  0030a0e1   mov      r3, r0
c0374a10  04c09de5   ldr      ip, [sp, #4]
c0374a14  10108ce2   add      r1, ip, #0x10
c0374a18  0300a0e1   mov      r0, r3
c0374a1c  37c000eb   bl       #0xc03a4b00
c0374a20  0030a0e1   mov      r3, r0
c0374a24  28308de5   str      r3, [sp, #0x28]
c0374a28  fcbe00eb   bl       #0xc03a4620
c0374a2c  0030a0e1   mov      r3, r0
c0374a30  28109de5   ldr      r1, [sp, #0x28]
c0374a34  0300a0e1   mov      r0, r3
c0374a38  08bf00eb   bl       #0xc03a4660
c0374a3c  0030a0e1   mov      r3, r0
c0374a40  013023e2   eor      r3, r3, #1
c0374a44  7330efe6   uxtb     r3, r3
c0374a48  0360a0e1   mov      r6, r3
c0374a4c  310000ea   b        #0xc0374b18
c0374a50  04309de5   ldr      r3, [sp, #4]
c0374a54  383193e5   ldr      r3, [r3, #0x138]
c0374a58  000053e3   cmp      r3, #0
c0374a5c  0f00000a   beq      #0xc0374aa0
c0374a60  04309de5   ldr      r3, [sp, #4]
c0374a64  38c193e5   ldr      ip, [r3, #0x138]
c0374a68  08309ce5   ldr      r3, [ip, #8]
c0374a6c  143083e2   add      r3, r3, #0x14
c0374a70  003093e5   ldr      r3, [r3]
c0374a74  0c00a0e1   mov      r0, ip
c0374a78  33ff2fe1   blx      r3
c0374a7c  0030a0e1   mov      r3, r0
c0374a80  03c0a0e1   mov      ip, r3
c0374a84  04e09de5   ldr      lr, [sp, #4]
c0374a88  04309de5   ldr      r3, [sp, #4]
c0374a8c  283193e5   ldr      r3, [r3, #0x128]
c0374a90  0c3083e0   add      r3, r3, ip
c0374a94  fc3f8ee5   str      r3, [lr, #0xffc]
c0374a98  130000ea   b        #0xc0374aec
c0374a9c  00f020e3   nop      
c0374aa0  0410a0e1   mov      r1, r4
c0374aa4  24008de2   add      r0, sp, #0x24
c0374aa8  b8bf0ceb   bl       #0xc06a4990
c0374aac  24c09de5   ldr      ip, [sp, #0x24]
c0374ab0  08309ce5   ldr      r3, [ip, #8]
c0374ab4  143083e2   add      r3, r3, #0x14
