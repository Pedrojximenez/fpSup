c040c4d8  f0442de9   push     {r4, r5, r6, r7, sl, lr}
c040c4dc  0060a0e1   mov      r6, r0
c040c4e0  0170a0e1   mov      r7, r1
c040c4e4  02a0a0e1   mov      sl, r2
c040c4e8  0050a0e3   mov      r5, #0
c040c4ec  0040a0e3   mov      r4, #0
c040c4f0  000057e3   cmp      r7, #0
c040c4f4  080000da   ble      #0xc040c51c
c040c4f8  00009ae5   ldr      r0, [sl]
c040c4fc  0020a0e3   mov      r2, #0
c040c500  0210a0e1   mov      r1, r2
c040c504  e3a4f7eb   bl       #0xc01f5898
c040c508  0030a0e1   mov      r3, r0
c040c50c  0340a0e1   mov      r4, r3
c040c510  0400a0e1   mov      r0, r4
c040c514  955400eb   bl       #0xc0421770
c040c518  0150a0e3   mov      r5, #1
c040c51c  000055e3   cmp      r5, #0
c040c520  0600000a   beq      #0xc040c540
c040c524  003096e5   ldr      r3, [r6]
c040c528  800203e3   movw     r0, #0x3280
c040c52c  bc004ce3   movt     r0, #0xc0bc
c040c530  0410a0e1   mov      r1, r4
c040c534  33ff2fe1   blx      r3
c040c538  040000ea   b        #0xc040c550
c040c53c  00f020e3   nop      
c040c540  003096e5   ldr      r3, [r6]
c040c544  7c0203e3   movw     r0, #0x327c
c040c548  bc004ce3   movt     r0, #0xc0bc
c040c54c  33ff2fe1   blx      r3
c040c550  f084bde8   pop      {r4, r5, r6, r7, sl, pc}
c040c554  00f020e3   nop      
