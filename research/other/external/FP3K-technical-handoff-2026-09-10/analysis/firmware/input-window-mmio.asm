c0635ed8  2de9f049   push.w   {r4, r5, r6, r7, r8, fp, lr}
c0635edc  83b0       sub      sp, #0xc
c0635ede  0446       mov      r4, r0
c0635ee0  2068       ldr      r0, [r4]
c0635ee2  eff64df0   bl       #0xc0124f80
c0635ee6  a188       ldrh     r1, [r4, #4]
c0635ee8  4af6ab23   movw     r3, #0xaaab
c0635eec  c2f6aa23   movt     r3, #0x2aaa
c0635ef0  53fb01f6   smmul    r6, r3, r1
c0635ef4  ca17       asrs     r2, r1, #0x1f
c0635ef6  7610       asrs     r6, r6, #1
c0635ef8  b61a       subs     r6, r6, r2
c0635efa  a288       ldrh     r2, [r4, #4]
c0635efc  4af6ab21   movw     r1, #0xaaab
c0635f00  c2f6aa21   movt     r1, #0x2aaa
c0635f04  51fb02f1   smmul    r1, r1, r2
c0635f08  4910       asrs     r1, r1, #1
c0635f0a  0c23       movs     r3, #0xc
c0635f0c  a1ebe271   sub.w    r1, r1, r2, asr #31
c0635f10  5943       muls     r1, r3, r1
c0635f12  a2eb010b   sub.w    fp, r2, r1
c0635f16  e188       ldrh     r1, [r4, #6]
c0635f18  a1eb0b02   sub.w    r2, r1, fp
c0635f1c  4af6ab21   movw     r1, #0xaaab
c0635f20  caf6aa21   movt     r1, #0xaaaa
c0635f24  a2fb0115   umull    r1, r5, r2, r1
c0635f28  ed08       lsrs     r5, r5, #3
c0635f2a  e188       ldrh     r1, [r4, #6]
c0635f2c  4af6ab22   movw     r2, #0xaaab
c0635f30  caf6aa22   movt     r2, #0xaaaa
c0635f34  a1eb0b03   sub.w    r3, r1, fp
c0635f38  a3fb0221   umull    r2, r1, r3, r2
c0635f3c  c908       lsrs     r1, r1, #3
c0635f3e  0c22       movs     r2, #0xc
c0635f40  5143       muls     r1, r2, r1
c0635f42  5f1a       subs     r7, r3, r1
c0635f44  1fb1       cbz      r7, #0xc0635f4e
c0635f46  0135       adds     r5, #1
c0635f48  c7f10c01   rsb.w    r1, r7, #0xc
c0635f4c  0f46       mov      r7, r1
c0635f4e  2189       ldrh     r1, [r4, #8]
c0635f50  0191       str      r1, [sp, #4]
c0635f52  6189       ldrh     r1, [r4, #0xa]
c0635f54  0091       str      r1, [sp]
c0635f56  40f20c08   movw     r8, #0xc
c0635f5a  45ea0641   orr.w    r1, r5, r6, lsl #16
c0635f5e  c3f21008   movt     r8, #0x3010
c0635f62  c8f80010   str.w    r1, [r8]
c0635f66  9de80801   ldm.w    sp, {r3, r8}
c0635f6a  53ea0841   orrs.w   r1, r3, r8, lsl #16
c0635f6e  40f22408   movw     r8, #0x24
c0635f72  c3f21008   movt     r8, #0x3010
c0635f76  c8f80010   str.w    r1, [r8]
c0635f7a  40f20c08   movw     r8, #0xc
c0635f7e  c3f21008   movt     r8, #0x3010
c0635f82  d8f80010   ldr.w    r1, [r8]
c0635f86  41f28408   movw     r8, #0x1084
c0635f8a  c3f20f08   movt     r8, #0x300f
c0635f8e  c1f30c01   ubfx     r1, r1, #0, #0xd
c0635f92  0131       adds     r1, #1
c0635f94  c8f80010   str.w    r1, [r8]
c0635f98  2046       mov      r0, r4
c0635f9a  eef6fdf7   bl       #0xc0124f98
c0635f9e  41f2c008   movw     r8, #0x10c0
c0635fa2  c3f20f08   movt     r8, #0x300f
c0635fa6  d8f80010   ldr.w    r1, [r8]
c0635faa  21f47021   bic      r1, r1, #0xf0000
c0635fae  41ea0b41   orr.w    r1, r1, fp, lsl #16
c0635fb2  c8f80010   str.w    r1, [r8]
c0635fb6  40f21008   movw     r8, #0x10
c0635fba  c3f20f08   movt     r8, #0x300f
c0635fbe  c8f80c72   str.w    r7, [r8, #0x20c]
c0635fc2  0021       movs     r1, #0
c0635fc4  0846       mov      r0, r1
c0635fc6  eff68ff0   bl       #0xc01250e8
c0635fca  b0f5e75f   cmp.w    r0, #0x1ce0
c0635fce  11d9       bls      #0xc0635ff4
c0635fd0  40f21008   movw     r8, #0x10
c0635fd4  0121       movs     r1, #1
c0635fd6  c3f20f08   movt     r8, #0x300f
c0635fda  c8f80010   str.w    r1, [r8]
c0635fde  40f21008   movw     r8, #0x10
c0635fe2  c3f20f08   movt     r8, #0x300f
c0635fe6  d8f83c1c   ldr.w    r1, [r8, #0xc3c]
c0635fea  41f01001   orr      r1, r1, #0x10
c0635fee  c8f83c1c   str.w    r1, [r8, #0xc3c]
c0635ff2  10e0       b        #0xc0636016
c0635ff4  40f21008   movw     r8, #0x10
c0635ff8  0021       movs     r1, #0
c0635ffa  c3f20f08   movt     r8, #0x300f
c0635ffe  c8f80010   str.w    r1, [r8]
c0636002  40f21008   movw     r8, #0x10
c0636006  c3f20f08   movt     r8, #0x300f
c063600a  d8f83c1c   ldr.w    r1, [r8, #0xc3c]
c063600e  21f01001   bic      r1, r1, #0x10
c0636012  c8f83c1c   str.w    r1, [r8, #0xc3c]
c0636016  0020       movs     r0, #0
c0636018  faf792fa   bl       #0xc0630540
c063601c  0020       movs     r0, #0
c063601e  faf7a7fa   bl       #0xc0630570
c0636022  0020       movs     r0, #0
c0636024  faf768fd   bl       #0xc0630af8
c0636028  0020       movs     r0, #0
c063602a  faf77dfd   bl       #0xc0630b28
c063602e  0020       movs     r0, #0
c0636030  faf7caff   bl       #0xc0630fc8
c0636034  0020       movs     r0, #0
c0636036  faf7dfff   bl       #0xc0630ff8
c063603a  0021       movs     r1, #0
c063603c  0846       mov      r0, r1
c063603e  03b0       add      sp, #0xc
c0636040  bde8f089   pop.w    {r4, r5, r6, r7, r8, fp, pc}
c0636044  00bf       nop      
c0636046  00bf       nop      
