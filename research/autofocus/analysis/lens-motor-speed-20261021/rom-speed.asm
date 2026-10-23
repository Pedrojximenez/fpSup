
; C0238A28..C0238B78 (end exclusive)
C0238A28: f04d2de9  push     {r4, r5, r6, r7, r8, sl, fp, lr}
C0238A2C: 0cd04de2  sub      sp, sp, #0xc
C0238A30: 0070a0e1  mov      r7, r0
C0238A34: 04108de5  str      r1, [sp, #4]
C0238A38: 08208de5  str      r2, [sp, #8]
C0238A3C: f6c501e3  movw     ip, #0x15f6
C0238A40: 29c34ce3  movt     ip, #0xc329
C0238A44: b030dce1  ldrh     r3, [ip]
C0238A48: 000053e3  cmp      r3, #0
C0238A4C: 3d00001a  bne      #0xc0238b48
C0238A50: 08309de5  ldr      r3, [sp, #8]
C0238A54: 010053e3  cmp      r3, #1
C0238A58: 0400001a  bne      #0xc0238a70
C0238A5C: 903501e3  movw     r3, #0x1590
C0238A60: 29334ce3  movt     r3, #0xc329
C0238A64: 004093e5  ldr      r4, [r3]
C0238A68: 030000ea  b        #0xc0238a7c
C0238A6C: 00f020e3  nop      
C0238A70: 6c3501e3  movw     r3, #0x156c
C0238A74: 29334ce3  movt     r3, #0xc329
C0238A78: 004093e5  ldr      r4, [r3]
C0238A7C: 77b201eb  bl       #0xc02a5460
C0238A80: 043090e5  ldr      r3, [r0, #4]
C0238A84: 403083e2  add      r3, r3, #0x40
C0238A88: 003093e5  ldr      r3, [r3]
C0238A8C: 33ff2fe1  blx      r3
C0238A90: 0030a0e1  mov      r3, r0
C0238A94: 0350a0e1  mov      r5, r3
C0238A98: aec8ffeb  bl       #0xc022ad58
C0238A9C: 17ccffeb  bl       #0xc022bb00
C0238AA0: f48102e3  movw     r8, #0x21f4
C0238AA4: 003098e7  ldr      r3, [r8, r0]
C0238AA8: 006093e5  ldr      r6, [r3]
C0238AAC: 010056e3  cmp      r6, #1
C0238AB0: 08005613  cmpne    r6, #8
C0238AB4: 09005613  cmpne    r6, #9
C0238AB8: 0300001a  bne      #0xc0238acc
C0238ABC: 0300a0e3  mov      r0, #3
C0238AC0: 009d04eb  bl       #0xc035fec8
C0238AC4: 0030a0e1  mov      r3, r0
C0238AC8: 0350a0e1  mov      r5, r3
C0238ACC: 7700a0e3  mov      r0, #0x77
C0238AD0: 1ecf03eb  bl       #0xc032c750
C0238AD4: 47a704eb  bl       #0xc03627f8
C0238AD8: 0030a0e1  mov      r3, r0
C0238ADC: 01a083e2  add      sl, r3, #1
C0238AE0: 04309de5  ldr      r3, [sp, #4]
C0238AE4: 03c1a0e1  lsl      ip, r3, #2
C0238AE8: 0c3043e0  sub      r3, r3, ip
C0238AEC: 8c3283e0  add      r3, r3, ip, lsl #5
C0238AF0: 0332a0e1  lsl      r3, r3, #4
C0238AF4: 00308de5  str      r3, [sp]
C0238AF8: 44b5fbfa  blx      #0xc0126010
C0238AFC: 013080e2  add      r3, r0, #1
C0238B00: 950303e0  mul      r3, r5, r3
C0238B04: 00c09de5  ldr      ip, [sp]
C0238B08: 9a0303e0  mul      r3, sl, r3
C0238B0C: 1cf31be7  sdiv     fp, ip, r3
C0238B10: 403097e5  ldr      r3, [r7, #0x40]
C0238B14: 0b20a0e1  mov      r2, fp
C0238B18: 183083e2  add      r3, r3, #0x18
C0238B1C: 003093e5  ldr      r3, [r3]
C0238B20: 0410a0e1  mov      r1, r4
C0238B24: 0700a0e1  mov      r0, r7
C0238B28: 33ff2fe1  blx      r3
C0238B2C: f6c501e3  movw     ip, #0x15f6
C0238B30: 29c34ce3  movt     ip, #0xc329
C0238B34: b030dce1  ldrh     r3, [ip]
C0238B38: 013083e2  add      r3, r3, #1
C0238B3C: b030cce1  strh     r3, [ip]
C0238B40: 010000ea  b        #0xc0238b4c
C0238B44: 00f020e3  nop      
C0238B48: 00f020e3  nop      
C0238B4C: 0cd08de2  add      sp, sp, #0xc
C0238B50: f08dbde8  pop      {r4, r5, r6, r7, r8, sl, fp, pc}
C0238B54: 00f020e3  nop      
C0238B58: 70402de9  push     {r4, r5, r6, lr}
C0238B5C: 0060a0e1  mov      r6, r0
C0238B60: 0140a0e1  mov      r4, r1
C0238B64: 0250a0e1  mov      r5, r2
C0238B68: 0510a0e1  mov      r1, r5
C0238B6C: 0400a0e1  mov      r0, r4
C0238B70: c49c04eb  bl       #0xc035fe88
C0238B74: 7080bde8  pop      {r4, r5, r6, pc}

; C033DE20..C033DEC8 (end exclusive)
C033DE20: 10402de9  push     {r4, lr}
C033DE24: 0040a0e1  mov      r4, r0
C033DE28: e6d8ffeb  bl       #0xc03341c8
C033DE2C: 1710a0e3  mov      r1, #0x17
C033DE30: 84f2ffeb  bl       #0xc033a848
C033DE34: 000050e3  cmp      r0, #0
C033DE38: 0200000a  beq      #0xc033de48
C033DE3C: 541094e5  ldr      r1, [r4, #0x54]
C033DE40: 401191e5  ldr      r1, [r1, #0x140]
C033DE44: 010000ea  b        #0xc033de50
C033DE48: 541094e5  ldr      r1, [r4, #0x54]
C033DE4C: 7c1091e5  ldr      r1, [r1, #0x7c]
C033DE50: 0100a0e1  mov      r0, r1
C033DE54: 1080bde8  pop      {r4, pc}
C033DE58: 10402de9  push     {r4, lr}
C033DE5C: 0040a0e1  mov      r4, r0
C033DE60: d8d8ffeb  bl       #0xc03341c8
C033DE64: 1710a0e3  mov      r1, #0x17
C033DE68: 76f2ffeb  bl       #0xc033a848
C033DE6C: 000050e3  cmp      r0, #0
C033DE70: 0200000a  beq      #0xc033de80
C033DE74: 541094e5  ldr      r1, [r4, #0x54]
C033DE78: 3c1191e5  ldr      r1, [r1, #0x13c]
C033DE7C: 010000ea  b        #0xc033de88
C033DE80: 541094e5  ldr      r1, [r4, #0x54]
C033DE84: 781091e5  ldr      r1, [r1, #0x78]
C033DE88: 0100a0e1  mov      r0, r1
C033DE8C: 1080bde8  pop      {r4, pc}
C033DE90: 10402de9  push     {r4, lr}
C033DE94: 0040a0e1  mov      r4, r0
C033DE98: cad8ffeb  bl       #0xc03341c8
C033DE9C: 1710a0e3  mov      r1, #0x17
C033DEA0: 68f2ffeb  bl       #0xc033a848
C033DEA4: 000050e3  cmp      r0, #0
C033DEA8: 0200000a  beq      #0xc033deb8
C033DEAC: 541094e5  ldr      r1, [r4, #0x54]
C033DEB0: 441191e5  ldr      r1, [r1, #0x144]
C033DEB4: 010000ea  b        #0xc033dec0
C033DEB8: 541094e5  ldr      r1, [r4, #0x54]
C033DEBC: 801091e5  ldr      r1, [r1, #0x80]
C033DEC0: 0100a0e1  mov      r0, r1
C033DEC4: 1080bde8  pop      {r4, pc}

; C033EC80..C033EE78 (end exclusive)
C033EC80: f0482de9  push     {r4, r5, r6, r7, fp, lr}
C033EC84: 14d04de2  sub      sp, sp, #0x14
C033EC88: 0050a0e1  mov      r5, r0
C033EC8C: 0170a0e1  mov      r7, r1
C033EC90: 10208de5  str      r2, [sp, #0x10]
C033EC94: 0360a0e1  mov      r6, r3
C033EC98: 486cf3eb  bl       #0xc0019dc0
C033EC9C: 0110a0e3  mov      r1, #1
C033ECA0: 0120a0e1  mov      r2, r1
C033ECA4: 0130a0e1  mov      r3, r1
C033ECA8: 0e008de9  stmib    sp, {r1, r2, r3}
C033ECAC: 0510a0e3  mov      r1, #5
C033ECB0: 0130a0e3  mov      r3, #1
C033ECB4: 00108de5  str      r1, [sp]
C033ECB8: 0212a0e3  mov      r1, #0x20000000
C033ECBC: 0020a0e3  mov      r2, #0
C033ECC0: 046df3eb  bl       #0xc001a0d8
C033ECC4: 000056e3  cmp      r6, #0
C033ECC8: 0c00000a  beq      #0xc033ed00
C033ECCC: 7700a0e3  mov      r0, #0x77
C033ECD0: b8b6ffeb  bl       #0xc032c7b8
C033ECD4: 00c0a0e1  mov      ip, r0
C033ECD8: 0cb0a0e1  mov      fp, ip
C033ECDC: 58c095e5  ldr      ip, [r5, #0x58]
C033ECE0: 0b20a0e1  mov      r2, fp
C033ECE4: 24309ce5  ldr      r3, [ip, #0x24]
C033ECE8: 0610a0e1  mov      r1, r6
C033ECEC: 0500a0e1  mov      r0, r5
C033ECF0: 280000eb  bl       #0xc033ed98
C033ECF4: 00c0a0e1  mov      ip, r0
C033ECF8: 0c40a0e1  mov      r4, ip
C033ECFC: 0d0000ea  b        #0xc033ed38
C033ED00: 727100eb  bl       #0xc035b2d0
C033ED04: 57c1d0e5  ldrb     ip, [r0, #0x157]
C033ED08: 00005ce3  cmp      ip, #0
C033ED0C: 0500000a  beq      #0xc033ed28
C033ED10: 0500a0e1  mov      r0, r5
C033ED14: 5dfcffeb  bl       #0xc033de90
C033ED18: 00c0a0e1  mov      ip, r0
C033ED1C: 0c40a0e1  mov      r4, ip
C033ED20: 040000ea  b        #0xc033ed38
C033ED24: 00f020e3  nop      
C033ED28: 0500a0e1  mov      r0, r5
C033ED2C: 3bfcffeb  bl       #0xc033de20
C033ED30: 00c0a0e1  mov      ip, r0
C033ED34: 0c40a0e1  mov      r4, ip
C033ED38: 206cf3eb  bl       #0xc0019dc0
C033ED3C: 0710a0e1  mov      r1, r7
C033ED40: 04c0a0e1  mov      ip, r4
C033ED44: 42108de9  stmib    sp, {r1, r6, ip}
C033ED48: 4ce702e3  movw     lr, #0x274c
C033ED4C: 0020a0e3  mov      r2, #0
C033ED50: 0430a0e3  mov      r3, #4
C033ED54: 011ca0e3  mov      r1, #0x100
C033ED58: 00e08de5  str      lr, [sp]
C033ED5C: 256df3eb  bl       #0xc001a1f8
C033ED60: 5a7100eb  bl       #0xc035b2d0
C033ED64: 857200eb  bl       #0xc035b780
C033ED68: 00c0a0e3  mov      ip, #0
C033ED6C: 10309de5  ldr      r3, [sp, #0x10]
C033ED70: 0500a0e1  mov      r0, r5
C033ED74: 0420a0e1  mov      r2, r4
C033ED78: 0710a0e1  mov      r1, r7
C033ED7C: 00c08de5  str      ip, [sp]
C033ED80: b20000eb  bl       #0xc033f050
C033ED84: 00c0a0e1  mov      ip, r0
C033ED88: 0c00a0e1  mov      r0, ip
C033ED8C: 14d08de2  add      sp, sp, #0x14
C033ED90: f088bde8  pop      {r4, r5, r6, r7, fp, pc}
C033ED94: 00f020e3  nop      
C033ED98: f04b2de9  push     {r4, r5, r6, r7, r8, sb, fp, lr}
C033ED9C: 20d04de2  sub      sp, sp, #0x20
C033EDA0: 0060a0e1  mov      r6, r0
C033EDA4: 10108de5  str      r1, [sp, #0x10]
C033EDA8: 0270a0e1  mov      r7, r2
C033EDAC: 14308de5  str      r3, [sp, #0x14]
C033EDB0: 000057e3  cmp      r7, #0
C033EDB4: 0400001a  bne      #0xc033edcc
C033EDB8: a4000fe3  movw     r0, #0xf0a4
C033EDBC: 2e1200e3  movw     r1, #0x22e
C033EDC0: b8004ce3  movt     r0, #0xc0b8
C033EDC4: cd48f3eb  bl       #0xc0011100
C033EDC8: 00f020e3  nop      
C033EDCC: 14c09de5  ldr      ip, [sp, #0x14]
C033EDD0: 10e09de5  ldr      lr, [sp, #0x10]
C033EDD4: 9ebc8ce0  umull    fp, ip, lr, ip
C033EDD8: 0c50a0e1  mov      r5, ip
C033EDDC: 0b40a0e1  mov      r4, fp
C033EDE0: fa0fa0e3  mov      r0, #0x3e8
C033EDE4: 94b08ce0  umull    fp, ip, r4, r0
C033EDE8: 95c02ce0  mla      ip, r5, r0, ip
C033EDEC: 9b8089e0  umull    r8, sb, fp, r0
C033EDF0: 0030a0e3  mov      r3, #0
C033EDF4: 9c9021e0  mla      r1, ip, r0, sb
C033EDF8: 07c147e0  sub      ip, r7, r7, lsl #2
C033EDFC: 87c38ce0  add      ip, ip, r7, lsl #7
C033EE00: 8c21a0e1  lsl      r2, ip, #3
C033EE04: 0800a0e1  mov      r0, r8
C033EE08: fc5af3eb  bl       #0xc0015a00
C033EE0C: 00c0a0e1  mov      ip, r0
C033EE10: 08c08de5  str      ip, [sp, #8]
C033EE14: 0600a0e1  mov      r0, r6
C033EE18: 0efcffeb  bl       #0xc033de58
C033EE1C: 00008de5  str      r0, [sp]
C033EE20: 0600a0e1  mov      r0, r6
C033EE24: fdfbffeb  bl       #0xc033de20
C033EE28: 08c09de5  ldr      ip, [sp, #8]
C033EE2C: 00b09de5  ldr      fp, [sp]
C033EE30: 04008de5  str      r0, [sp, #4]
C033EE34: 0b005ce1  cmp      ip, fp
C033EE38: 0200002a  bhs      #0xc033ee48
C033EE3C: 0dc0a0e1  mov      ip, sp
C033EE40: 010000ea  b        #0xc033ee4c
C033EE44: 00f020e3  nop      
C033EE48: 08c08de2  add      ip, sp, #8
C033EE4C: 00e09ce5  ldr      lr, [ip]
C033EE50: 04b09de5  ldr      fp, [sp, #4]
C033EE54: 0e005be1  cmp      fp, lr
C033EE58: 0000002a  bhs      #0xc033ee60
C033EE5C: 04c08de2  add      ip, sp, #4
C033EE60: 00c09ce5  ldr      ip, [ip]
C033EE64: 08c08de5  str      ip, [sp, #8]
C033EE68: 08c09de5  ldr      ip, [sp, #8]
C033EE6C: 0c00a0e1  mov      r0, ip
C033EE70: 20d08de2  add      sp, sp, #0x20
C033EE74: f08bbde8  pop      {r4, r5, r6, r7, r8, sb, fp, pc}

; C033EF90..C033F050 (end exclusive)
C033EF90: f0482de9  push     {r4, r5, r6, r7, fp, lr}
C033EF94: 10d04de2  sub      sp, sp, #0x10
C033EF98: 0040a0e1  mov      r4, r0
C033EF9C: 0170a0e1  mov      r7, r1
C033EFA0: 02b0a0e1  mov      fp, r2
C033EFA4: 7700a0e3  mov      r0, #0x77
C033EFA8: 02b6ffeb  bl       #0xc032c7b8
C033EFAC: 0030a0e1  mov      r3, r0
C033EFB0: 0350a0e1  mov      r5, r3
C033EFB4: 583094e5  ldr      r3, [r4, #0x58]
C033EFB8: 0520a0e1  mov      r2, r5
C033EFBC: 243093e5  ldr      r3, [r3, #0x24]
C033EFC0: 0b10a0e1  mov      r1, fp
C033EFC4: 0400a0e1  mov      r0, r4
C033EFC8: 72ffffeb  bl       #0xc033ed98
C033EFCC: 0030a0e1  mov      r3, r0
C033EFD0: 0360a0e1  mov      r6, r3
C033EFD4: 796bf3eb  bl       #0xc0019dc0
C033EFD8: 06e0a0e1  mov      lr, r6
C033EFDC: 4d1702e3  movw     r1, #0x274d
C033EFE0: 82488de8  stm      sp, {r1, r7, fp, lr}
C033EFE4: 0430a0e3  mov      r3, #4
C033EFE8: 011ca0e3  mov      r1, #0x100
C033EFEC: 0020a0e3  mov      r2, #0
C033EFF0: 806cf3eb  bl       #0xc001a1f8
C033EFF4: 716bf3eb  bl       #0xc0019dc0
C033EFF8: 0030a0e3  mov      r3, #0
C033EFFC: 03c0a0e1  mov      ip, r3
C033F000: 0520a0e1  mov      r2, r5
C033F004: 4e1702e3  movw     r1, #0x274e
C033F008: 0e108de8  stm      sp, {r1, r2, r3, ip}
C033F00C: 0430a0e3  mov      r3, #4
C033F010: 011ca0e3  mov      r1, #0x100
C033F014: 0020a0e3  mov      r2, #0
C033F018: 766cf3eb  bl       #0xc001a1f8
C033F01C: ab7000eb  bl       #0xc035b2d0
C033F020: d67100eb  bl       #0xc035b780
C033F024: 0130a0e3  mov      r3, #1
C033F028: 00308de5  str      r3, [sp]
C033F02C: 0620a0e1  mov      r2, r6
C033F030: 0710a0e1  mov      r1, r7
C033F034: 0400a0e1  mov      r0, r4
C033F038: 0030a0e3  mov      r3, #0
C033F03C: 030000eb  bl       #0xc033f050
C033F040: 0030a0e1  mov      r3, r0
C033F044: 0300a0e1  mov      r0, r3
C033F048: 10d08de2  add      sp, sp, #0x10
C033F04C: f088bde8  pop      {r4, r5, r6, r7, fp, pc}

; C0357E58..C0357F30 (end exclusive)
C0357E58: f04c2de9  push     {r4, r5, r6, r7, sl, fp, lr}
C0357E5C: 08d04de2  sub      sp, sp, #8
C0357E60: 0040a0e1  mov      r4, r0
C0357E64: 01a0a0e1  mov      sl, r1
C0357E68: 0250a0e1  mov      r5, r2
C0357E6C: 0360a0e1  mov      r6, r3
C0357E70: 24b09de5  ldr      fp, [sp, #0x24]
C0357E74: 000055e3  cmp      r5, #0
C0357E78: 040000aa  bge      #0xc0357e90
C0357E7C: 0b0204e3  movw     r0, #0x420b
C0357E80: 261600e3  movw     r1, #0x626
C0357E84: b9004ce3  movt     r0, #0xc0b9
C0357E88: 9ce4f2eb  bl       #0xc0011100
C0357E8C: 00f020e3  nop      
C0357E90: 00f020e3  nop      
C0357E94: 0400a0e1  mov      r0, r4
C0357E98: 90f5ffeb  bl       #0xc03554e0
C0357E9C: 00a0cde5  strb     sl, [sp]
C0357EA0: 55c4e7e7  ubfx     ip, r5, #8, #8
C0357EA4: 01c0cde5  strb     ip, [sp, #1]
C0357EA8: 05c0a0e1  mov      ip, r5
C0357EAC: 02c0cde5  strb     ip, [sp, #2]
C0357EB0: 56c4e7e7  ubfx     ip, r6, #8, #8
C0357EB4: 03c0cde5  strb     ip, [sp, #3]
C0357EB8: 06c0a0e1  mov      ip, r6
C0357EBC: 04c0cde5  strb     ip, [sp, #4]
C0357EC0: 05b0cde5  strb     fp, [sp, #5]
C0357EC4: bf70ffeb  bl       #0xc03341c8
C0357EC8: 1710a0e3  mov      r1, #0x17
C0357ECC: 5d8affeb  bl       #0xc033a848
C0357ED0: 000050e3  cmp      r0, #0
C0357ED4: 0100000a  beq      #0xc0357ee0
C0357ED8: 56c8e7e7  ubfx     ip, r6, #0x10, #8
C0357EDC: 000000ea  b        #0xc0357ee4
C0357EE0: 00c0a0e3  mov      ip, #0
C0357EE4: 06c0cde5  strb     ip, [sp, #6]
C0357EE8: 00c0a0e3  mov      ip, #0
C0357EEC: 07c0cde5  strb     ip, [sp, #7]
C0357EF0: ec0094e5  ldr      r0, [r4, #0xec]
C0357EF4: 0710a0e3  mov      r1, #7
C0357EF8: 0d20a0e1  mov      r2, sp
C0357EFC: 4b0800eb  bl       #0xc035a030
C0357F00: ec0094e5  ldr      r0, [r4, #0xec]
C0357F04: 1010a0e3  mov      r1, #0x10
C0357F08: b20800eb  bl       #0xc035a1d8
C0357F0C: 00c0a0e1  mov      ip, r0
C0357F10: 0c70a0e1  mov      r7, ip
C0357F14: 0400a0e1  mov      r0, r4
C0357F18: a0f5ffeb  bl       #0xc03555a0
C0357F1C: 07c0a0e1  mov      ip, r7
C0357F20: 0c00a0e1  mov      r0, ip
C0357F24: 08d08de2  add      sp, sp, #8
C0357F28: f08cbde8  pop      {r4, r5, r6, r7, sl, fp, pc}
C0357F2C: 00f020e3  nop      
