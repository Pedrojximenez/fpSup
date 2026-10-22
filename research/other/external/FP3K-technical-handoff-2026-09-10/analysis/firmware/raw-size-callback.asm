c03d9630  30402de9   push     {r4, r5, lr}
c03d9634  0040a0e1   mov      r4, r0
c03d9638  200094e5   ldr      r0, [r4, #0x20]
c03d963c  090000eb   bl       #0xc03d9668
c03d9640  041094e5   ldr      r1, [r4, #4]
c03d9644  0020a0e1   mov      r2, r0
c03d9648  000094e5   ldr      r0, [r4]
c03d964c  f744f7fa   blx      #0xc01aaa30
c03d9650  0010a0e1   mov      r1, r0
c03d9654  0150a0e1   mov      r5, r1
c03d9658  0510a0e1   mov      r1, r5
c03d965c  0100a0e1   mov      r0, r1
c03d9660  3080bde8   pop      {r4, r5, pc}
c03d9664  00f020e3   nop      
c03d9668  00412de9   push     {r8, lr}
c03d966c  022000e3   movw     r2, #2
c03d9670  00c0a0e1   mov      ip, r0
c03d9674  043000e3   movw     r3, #4
c03d9678  012040e3   movt     r2, #1
c03d967c  023040e3   movt     r3, #2
c03d9680  01185ce2   subs     r1, ip, #0x10000
c03d9684  0700002a   bhs      #0xc03d96a8
c03d9688  011891e2   adds     r1, r1, #0x10000
c03d968c  070051e3   cmp      r1, #7
c03d9690  4200008a   bhi      #0xc03d97a0
c03d9694  04808fe2   add      r8, pc, #4
c03d9698  0180d8e7   ldrb     r8, [r8, r1]
c03d969c  08f18fe0   add      pc, pc, r8, lsl #2
c03d96a0  17191b1d   vldrne.16 s2, [fp, #-0x2e]
c03d96a4  1f212325   strhs    r2, [r3, #-0x11f]!
c03d96a8  011851e2   subs     r1, r1, #0x10000
c03d96ac  0700002a   bhs      #0xc03d96d0
c03d96b0  011891e2   adds     r1, r1, #0x10000
c03d96b4  070051e3   cmp      r1, #7
c03d96b8  3800008a   bhi      #0xc03d97a0
c03d96bc  04808fe2   add      r8, pc, #4
c03d96c0  0180d8e7   ldrb     r8, [r8, r1]
c03d96c4  08f18fe0   add      pc, pc, r8, lsl #2
c03d96c8  1d351f21   tsths    pc, sp, lsl r5
c03d96cc  23252729   stmdbhs  r7!, {r0, r1, r5, r8, sl, sp}
c03d96d0  001051e2   subs     r1, r1, #0
c03d96d4  2700000a   beq      #0xc03d9778
c03d96d8  041051e2   subs     r1, r1, #4
c03d96dc  2f00003a   blo      #0xc03d97a0
c03d96e0  2600000a   beq      #0xc03d9780
c03d96e4  021051e2   subs     r1, r1, #2
c03d96e8  2600003a   blo      #0xc03d9788
c03d96ec  2700000a   beq      #0xc03d9790
c03d96f0  010051e3   cmp      r1, #1
c03d96f4  2700000a   beq      #0xc03d9798
c03d96f8  280000ea   b        #0xc03d97a0
c03d96fc  00f020e3   nop      
c03d9700  0010a0e3   mov      r1, #0
c03d9704  2b0000ea   b        #0xc03d97b8
c03d9708  0110a0e3   mov      r1, #1
c03d970c  290000ea   b        #0xc03d97b8
c03d9710  0210a0e3   mov      r1, #2
c03d9714  270000ea   b        #0xc03d97b8
c03d9718  0310a0e3   mov      r1, #3
c03d971c  250000ea   b        #0xc03d97b8
c03d9720  0410a0e3   mov      r1, #4
c03d9724  230000ea   b        #0xc03d97b8
c03d9728  0510a0e3   mov      r1, #5
c03d972c  210000ea   b        #0xc03d97b8
c03d9730  0610a0e3   mov      r1, #6
c03d9734  1f0000ea   b        #0xc03d97b8
c03d9738  0710a0e3   mov      r1, #7
c03d973c  1d0000ea   b        #0xc03d97b8
c03d9740  160000ea   b        #0xc03d97a0
c03d9744  00f020e3   nop      
c03d9748  0210a0e1   mov      r1, r2
c03d974c  190000ea   b        #0xc03d97b8
c03d9750  011082e2   add      r1, r2, #1
c03d9754  170000ea   b        #0xc03d97b8
c03d9758  021082e2   add      r1, r2, #2
c03d975c  150000ea   b        #0xc03d97b8
c03d9760  031082e2   add      r1, r2, #3
c03d9764  130000ea   b        #0xc03d97b8
c03d9768  041082e2   add      r1, r2, #4
c03d976c  110000ea   b        #0xc03d97b8
c03d9770  051082e2   add      r1, r2, #5
c03d9774  0f0000ea   b        #0xc03d97b8
c03d9778  080000ea   b        #0xc03d97a0
c03d977c  00f020e3   nop      
c03d9780  0310a0e1   mov      r1, r3
c03d9784  0b0000ea   b        #0xc03d97b8
c03d9788  011083e2   add      r1, r3, #1
c03d978c  090000ea   b        #0xc03d97b8
c03d9790  021083e2   add      r1, r3, #2
c03d9794  070000ea   b        #0xc03d97b8
c03d9798  031083e2   add      r1, r3, #3
c03d979c  050000ea   b        #0xc03d97b8
c03d97a0  580a0be3   movw     r0, #0xba58
c03d97a4  ba004ce3   movt     r0, #0xc0ba
c03d97a8  4210a0e3   mov      r1, #0x42
c03d97ac  53def0eb   bl       #0xc0011100
c03d97b0  feffffea   b        #0xc03d97b0
c03d97b4  00f020e3   nop      
c03d97b8  0100a0e1   mov      r0, r1
c03d97bc  0081bde8   pop      {r8, pc}
c03d97c0  04e02de5   str      lr, [sp, #-4]!
c03d97c4  6b12f7fa   blx      #0xc019e178
