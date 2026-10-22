c0135d40  2de9f048   push.w   {r4, r5, r6, r7, fp, lr}
c0135d44  0546       mov      r5, r0
c0135d46  0f46       mov      r7, r1
c0135d48  1646       mov      r6, r2
c0135d4a  0124       movs     r4, #1
c0135d4c  16f4803f   tst.w    r6, #0x10000
c0135d50  07d0       beq      #0xc0135d62
c0135d52  3146       mov      r1, r6
c0135d54  2846       mov      r0, r5
c0135d56  00f02ff8   bl       #0xc0135db8
c0135d5a  0346       mov      r3, r0
c0135d5c  07fb03f4   mul      r4, r7, r3
c0135d60  25e0       b        #0xc0135dae
c0135d62  05b1       cbz      r5, #0xc0135d66
c0135d64  0fb9       cbnz     r7, #0xc0135d6a
c0135d66  0024       movs     r4, #0
c0135d68  21e0       b        #0xc0135dae
c0135d6a  4af6ab2c   movw     ip, #0xaaab
c0135d6e  05f10b03   add.w    r3, r5, #0xb
c0135d72  caf6aa2c   movt     ip, #0xaaaa
c0135d76  a3fb0cc3   umull    ip, r3, r3, ip
c0135d7a  db08       lsrs     r3, r3, #3
c0135d7c  c3eb8303   rsb      r3, r3, r3, lsl #2
c0135d80  9b00       lsls     r3, r3, #2
c0135d82  0333       adds     r3, #3
c0135d84  23f0030b   bic      fp, r3, #3
c0135d88  3146       mov      r1, r6
c0135d8a  2846       mov      r0, r5
c0135d8c  00f014f8   bl       #0xc0135db8
c0135d90  c31c       adds     r3, r0, #3
c0135d92  23f00303   bic      r3, r3, #3
c0135d96  a7f1010c   sub.w    ip, r7, #1
c0135d9a  0cfb03f4   mul      r4, ip, r3
c0135d9e  3146       mov      r1, r6
c0135da0  5846       mov      r0, fp
c0135da2  00f009f8   bl       #0xc0135db8
c0135da6  c31c       adds     r3, r0, #3
c0135da8  23f00303   bic      r3, r3, #3
c0135dac  e418       adds     r4, r4, r3
c0135dae  2346       mov      r3, r4
c0135db0  1846       mov      r0, r3
c0135db2  bde8f088   pop.w    {r4, r5, r6, r7, fp, pc}
c0135db6  00bf       nop      
c0135db8  2de97041   push.w   {r4, r5, r6, r8, lr}
c0135dbc  0546       mov      r5, r0
c0135dbe  0e46       mov      r6, r1
c0135dc0  0124       movs     r4, #1
c0135dc2  16f4803f   tst.w    r6, #0x10000
c0135dc6  0cd0       beq      #0xc0135de2
c0135dc8  40f20202   movw     r2, #2
c0135dcc  c0f20102   movt     r2, #1
c0135dd0  b21a       subs     r2, r6, r2
c0135dd2  c2f10a02   rsb.w    r2, r2, #0xa
c0135dd6  2846       mov      r0, r5
c0135dd8  0c21       movs     r1, #0xc
c0135dda  00f031f8   bl       #0xc0135e40
c0135dde  8400       lsls     r4, r0, #2
c0135de0  28e0       b        #0xc0135e34
c0135de2  16f4003f   tst.w    r6, #0x20000
c0135de6  0cd0       beq      #0xc0135e02
c0135de8  40f20402   movw     r2, #4
c0135dec  c0f20202   movt     r2, #2
c0135df0  b21a       subs     r2, r6, r2
c0135df2  c2f10802   rsb.w    r2, r2, #8
c0135df6  2846       mov      r0, r5
c0135df8  0a21       movs     r1, #0xa
c0135dfa  00f069f8   bl       #0xc0135ed0
c0135dfe  8400       lsls     r4, r0, #2
c0135e00  18e0       b        #0xc0135e34
c0135e02  3246       mov      r2, r6
c0135e04  042a       cmp      r2, #4
c0135e06  15d8       bhi      #0xc0135e34
c0135e08  0ff20408   addw     r8, pc, #4
c0135e0c  d8e802f0   tbb      [r8, r2]
c0135e10  0307       lsls     r3, r0, #0x1c
c0135e12  0b0d       lsrs     r3, r1, #0x14
c0135e14  1100       movs     r1, r2
c0135e16  05eb4502   add.w    r2, r5, r5, lsl #1
c0135e1a  5408       lsrs     r4, r2, #1
c0135e1c  0ae0       b        #0xc0135e34
c0135e1e  c5ebc502   rsb      r2, r5, r5, lsl #3
c0135e22  9408       lsrs     r4, r2, #2
c0135e24  06e0       b        #0xc0135e34
c0135e26  6c00       lsls     r4, r5, #1
c0135e28  04e0       b        #0xc0135e34
c0135e2a  05eb8502   add.w    r2, r5, r5, lsl #2
c0135e2e  9408       lsrs     r4, r2, #2
c0135e30  00e0       b        #0xc0135e34
c0135e32  2c46       mov      r4, r5
c0135e34  2246       mov      r2, r4
c0135e36  1046       mov      r0, r2
c0135e38  bde87081   pop.w    {r4, r5, r6, r8, pc}
c0135e3c  00bf       nop      
c0135e3e  00bf       nop      
