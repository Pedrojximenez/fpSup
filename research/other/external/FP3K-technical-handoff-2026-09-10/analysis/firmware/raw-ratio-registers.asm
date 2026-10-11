c0633e60  2de9f00c   push.w   {r4, r5, r6, r7, sl, fp}
c0633e64  8446       mov      ip, r0
c0633e66  40f20402   movw     r2, #4
c0633e6a  0c46       mov      r4, r1
c0633e6c  c3f20f02   movt     r2, #0x300f
c0633e70  2378       ldrb     r3, [r4]
c0633e72  03f00107   and      r7, r3, #1
c0633e76  1368       ldr      r3, [r2]
c0633e78  23f48073   bic      r3, r3, #0x100
c0633e7c  43ea0723   orr.w    r3, r3, r7, lsl #8
c0633e80  1360       str      r3, [r2]
c0633e82  bcf1010f   cmp.w    ip, #1
c0633e86  42d1       bne      #0xc0633f0e
c0633e88  6388       ldrh     r3, [r4, #2]
c0633e8a  c3f30903   ubfx     r3, r3, #0, #0xa
c0633e8e  b3f5007f   cmp.w    r3, #0x200
c0633e92  08dd       ble      #0xc0633ea6
c0633e94  6588       ldrh     r5, [r4, #2]
c0633e96  c5f30905   ubfx     r5, r5, #0, #0xa
c0633e9a  05ebd575   add.w    r5, r5, r5, lsr #31
c0633e9e  6d10       asrs     r5, r5, #1
c0633ea0  c5f50073   rsb.w    r3, r5, #0x200
c0633ea4  09e0       b        #0xc0633eba
c0633ea6  6588       ldrh     r5, [r4, #2]
c0633ea8  c5f30905   ubfx     r5, r5, #0, #0xa
c0633eac  c5f58065   rsb.w    r5, r5, #0x400
c0633eb0  05ebd575   add.w    r5, r5, r5, lsr #31
c0633eb4  6d10       asrs     r5, r5, #1
c0633eb6  c5f50073   rsb.w    r3, r5, #0x200
c0633eba  a588       ldrh     r5, [r4, #4]
c0633ebc  c5f30905   ubfx     r5, r5, #0, #0xa
c0633ec0  b5f5007f   cmp.w    r5, #0x200
c0633ec4  08dd       ble      #0xc0633ed8
c0633ec6  a688       ldrh     r6, [r4, #4]
c0633ec8  c6f30906   ubfx     r6, r6, #0, #0xa
c0633ecc  06ebd676   add.w    r6, r6, r6, lsr #31
c0633ed0  7610       asrs     r6, r6, #1
c0633ed2  c6f50075   rsb.w    r5, r6, #0x200
c0633ed6  09e0       b        #0xc0633eec
c0633ed8  a688       ldrh     r6, [r4, #4]
c0633eda  c6f30906   ubfx     r6, r6, #0, #0xa
c0633ede  c6f58066   rsb.w    r6, r6, #0x400
c0633ee2  06ebd676   add.w    r6, r6, r6, lsr #31
c0633ee6  7610       asrs     r6, r6, #1
c0633ee8  c6f50075   rsb.w    r5, r6, #0x200
c0633eec  4ff0010a   mov.w    sl, #1
c0633ef0  c2f8fca8   str.w    sl, [r2, #0x8fc]
c0633ef4  b4f802b0   ldrh.w   fp, [r4, #2]
c0633ef8  cbea034a   pkhbt    sl, fp, r3, lsl #0x10
c0633efc  c2f804a9   str.w    sl, [r2, #0x904]
c0633f00  b4f804b0   ldrh.w   fp, [r4, #4]
c0633f04  cbea054a   pkhbt    sl, fp, r5, lsl #0x10
c0633f08  c2f808a9   str.w    sl, [r2, #0x908]
c0633f0c  02e0       b        #0xc0633f14
c0633f0e  0023       movs     r3, #0
c0633f10  c2f8fc38   str.w    r3, [r2, #0x8fc]
c0633f14  0026       movs     r6, #0
c0633f16  3046       mov      r0, r6
c0633f18  bde8f00c   pop.w    {r4, r5, r6, r7, sl, fp}
c0633f1c  7047       bx       lr
c0633f1e  00bf       nop      
c0633f20  2de9f00c   push.w   {r4, r5, r6, r7, sl, fp}
c0633f24  8446       mov      ip, r0
c0633f26  42f20402   movw     r2, #0x2004
c0633f2a  0c46       mov      r4, r1
c0633f2c  c3f20f02   movt     r2, #0x300f
c0633f30  2378       ldrb     r3, [r4]
c0633f32  03f00107   and      r7, r3, #1
c0633f36  1368       ldr      r3, [r2]
c0633f38  23f48073   bic      r3, r3, #0x100
c0633f3c  43ea0723   orr.w    r3, r3, r7, lsl #8
c0633f40  1360       str      r3, [r2]
c0633f42  bcf1010f   cmp.w    ip, #1
c0633f46  42d1       bne      #0xc0633fce
c0633f48  6388       ldrh     r3, [r4, #2]
c0633f4a  c3f30903   ubfx     r3, r3, #0, #0xa
c0633f4e  b3f5007f   cmp.w    r3, #0x200
c0633f52  08dd       ble      #0xc0633f66
c0633f54  6588       ldrh     r5, [r4, #2]
c0633f56  c5f30905   ubfx     r5, r5, #0, #0xa
c0633f5a  05ebd575   add.w    r5, r5, r5, lsr #31
c0633f5e  6d10       asrs     r5, r5, #1
c0633f60  c5f50073   rsb.w    r3, r5, #0x200
c0633f64  09e0       b        #0xc0633f7a
c0633f66  6588       ldrh     r5, [r4, #2]
c0633f68  c5f30905   ubfx     r5, r5, #0, #0xa
c0633f6c  c5f58065   rsb.w    r5, r5, #0x400
c0633f70  05ebd575   add.w    r5, r5, r5, lsr #31
c0633f74  6d10       asrs     r5, r5, #1
c0633f76  c5f50073   rsb.w    r3, r5, #0x200
c0633f7a  a588       ldrh     r5, [r4, #4]
c0633f7c  c5f30905   ubfx     r5, r5, #0, #0xa
c0633f80  b5f5007f   cmp.w    r5, #0x200
c0633f84  08dd       ble      #0xc0633f98
c0633f86  a688       ldrh     r6, [r4, #4]
c0633f88  c6f30906   ubfx     r6, r6, #0, #0xa
c0633f8c  06ebd676   add.w    r6, r6, r6, lsr #31
c0633f90  7610       asrs     r6, r6, #1
c0633f92  c6f50075   rsb.w    r5, r6, #0x200
c0633f96  09e0       b        #0xc0633fac
c0633f98  a688       ldrh     r6, [r4, #4]
c0633f9a  c6f30906   ubfx     r6, r6, #0, #0xa
c0633f9e  c6f58066   rsb.w    r6, r6, #0x400
c0633fa2  06ebd676   add.w    r6, r6, r6, lsr #31
c0633fa6  7610       asrs     r6, r6, #1
c0633fa8  c6f50075   rsb.w    r5, r6, #0x200
c0633fac  4ff0010a   mov.w    sl, #1
c0633fb0  c2f8fca8   str.w    sl, [r2, #0x8fc]
c0633fb4  b4f802b0   ldrh.w   fp, [r4, #2]
c0633fb8  cbea034a   pkhbt    sl, fp, r3, lsl #0x10
c0633fbc  c2f804a9   str.w    sl, [r2, #0x904]
c0633fc0  b4f804b0   ldrh.w   fp, [r4, #4]
c0633fc4  cbea054a   pkhbt    sl, fp, r5, lsl #0x10
c0633fc8  c2f808a9   str.w    sl, [r2, #0x908]
c0633fcc  02e0       b        #0xc0633fd4
c0633fce  0023       movs     r3, #0
c0633fd0  c2f8fc38   str.w    r3, [r2, #0x8fc]
c0633fd4  0026       movs     r6, #0
c0633fd6  3046       mov      r0, r6
c0633fd8  bde8f00c   pop.w    {r4, r5, r6, r7, sl, fp}
c0633fdc  7047       bx       lr
c0633fde  00bf       nop      
