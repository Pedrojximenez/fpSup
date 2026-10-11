c0630e90  2de9f00d   push.w   {r4, r5, r6, r7, r8, sl, fp}
c0630e94  0446       mov      r4, r0
c0630e96  42f20c22   movw     r2, #0x220c
c0630e9a  8c46       mov      ip, r1
c0630e9c  c3f21802   movt     r2, #0x3018
c0630ea0  0023       movs     r3, #0
c0630ea2  6546       mov      r5, ip
c0630ea4  042d       cmp      r5, #4
c0630ea6  50d8       bhi      #0xc0630f4a
c0630ea8  0ff20408   addw     r8, pc, #4
c0630eac  d8e805f0   tbb      [r8, r5]
c0630eb0  0312       asrs     r3, r0, #8
c0630eb2  222f       cmp      r7, #0x22
c0630eb4  3f00       movs     r7, r7
c0630eb6  1568       ldr      r5, [r2]
c0630eb8  25f00705   bic      r5, r5, #7
c0630ebc  1560       str      r5, [r2]
c0630ebe  c4eb8405   rsb      r5, r4, r4, lsl #2
c0630ec2  c5f35c05   ubfx     r5, r5, #1, #0x1d
c0630ec6  ad08       lsrs     r5, r5, #2
c0630ec8  9560       str      r5, [r2, #8]
c0630eca  1568       ldr      r5, [r2]
c0630ecc  25f48075   bic      r5, r5, #0x100
c0630ed0  1560       str      r5, [r2]
c0630ed2  46e0       b        #0xc0630f62
c0630ed4  1568       ldr      r5, [r2]
c0630ed6  0126       movs     r6, #1
c0630ed8  66f30205   bfi      r5, r6, #0, #3
c0630edc  1560       str      r5, [r2]
c0630ede  c4ebc405   rsb      r5, r4, r4, lsl #3
c0630ee2  c5f39c05   ubfx     r5, r5, #2, #0x1d
c0630ee6  ad08       lsrs     r5, r5, #2
c0630ee8  9560       str      r5, [r2, #8]
c0630eea  1568       ldr      r5, [r2]
c0630eec  25f48075   bic      r5, r5, #0x100
c0630ef0  1560       str      r5, [r2]
c0630ef2  36e0       b        #0xc0630f62
c0630ef4  1568       ldr      r5, [r2]
c0630ef6  0426       movs     r6, #4
c0630ef8  66f30205   bfi      r5, r6, #0, #3
c0630efc  1560       str      r5, [r2]
c0630efe  c4f35a05   ubfx     r5, r4, #1, #0x1b
c0630f02  9560       str      r5, [r2, #8]
c0630f04  1568       ldr      r5, [r2]
c0630f06  25f48075   bic      r5, r5, #0x100
c0630f0a  1560       str      r5, [r2]
c0630f0c  29e0       b        #0xc0630f62
c0630f0e  1568       ldr      r5, [r2]
c0630f10  0226       movs     r6, #2
c0630f12  66f30205   bfi      r5, r6, #0, #3
c0630f16  1560       str      r5, [r2]
c0630f18  04eb8405   add.w    r5, r4, r4, lsl #2
c0630f1c  c5f39c05   ubfx     r5, r5, #2, #0x1d
c0630f20  ad08       lsrs     r5, r5, #2
c0630f22  9560       str      r5, [r2, #8]
c0630f24  1568       ldr      r5, [r2]
c0630f26  25f48075   bic      r5, r5, #0x100
c0630f2a  1560       str      r5, [r2]
c0630f2c  19e0       b        #0xc0630f62
c0630f2e  1568       ldr      r5, [r2]
c0630f30  0326       movs     r6, #3
c0630f32  66f30205   bfi      r5, r6, #0, #3
c0630f36  1560       str      r5, [r2]
c0630f38  24f06045   bic      r5, r4, #0xe0000000
c0630f3c  ad08       lsrs     r5, r5, #2
c0630f3e  9560       str      r5, [r2, #8]
c0630f40  1568       ldr      r5, [r2]
c0630f42  45f48075   orr      r5, r5, #0x100
c0630f46  1560       str      r5, [r2]
c0630f48  0be0       b        #0xc0630f62
c0630f4a  1568       ldr      r5, [r2]
c0630f4c  25f00705   bic      r5, r5, #7
c0630f50  1560       str      r5, [r2]
c0630f52  04eb4406   add.w    r6, r4, r4, lsl #1
c0630f56  f608       lsrs     r6, r6, #3
c0630f58  9660       str      r6, [r2, #8]
c0630f5a  1568       ldr      r5, [r2]
c0630f5c  25f48075   bic      r5, r5, #0x100
c0630f60  1560       str      r5, [r2]
c0630f62  0025       movs     r5, #0
c0630f64  4ff47e77   mov.w    r7, #0x3f8
c0630f68  0026       movs     r6, #0
c0630f6a  9568       ldr      r5, [r2, #8]
c0630f6c  07eb050a   add.w    sl, r7, r5
c0630f70  aaf1010a   sub.w    sl, sl, #1
c0630f74  bafbf7f6   udiv     r6, sl, r7
c0630f78  06eb050a   add.w    sl, r6, r5
c0630f7c  aaf1010a   sub.w    sl, sl, #1
c0630f80  bafbf6f3   udiv     r3, sl, r6
c0630f84  03f1070a   add.w    sl, r3, #7
c0630f88  2af00703   bic      r3, sl, #7
c0630f8c  d360       str      r3, [r2, #0xc]
c0630f8e  4ff0000b   mov.w    fp, #0
c0630f92  c2f810b0   str.w    fp, [r2, #0x10]
c0630f96  bde8f00d   pop.w    {r4, r5, r6, r7, r8, sl, fp}
c0630f9a  7047       bx       lr
c0630f9c  00bf       nop      
c0630f9e  00bf       nop      
