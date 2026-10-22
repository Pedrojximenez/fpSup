c0321028  70402de9   push     {r4, r5, r6, lr}
c032102c  0040a0e1   mov      r4, r0
c0321030  0160a0e1   mov      r6, r1
c0321034  770056e3   cmp      r6, #0x77
c0321038  0600001a   bne      #0xc0321058
c032103c  041094e5   ldr      r1, [r4, #4]
c0321040  0400a0e1   mov      r0, r4
c0321044  bbfeffeb   bl       #0xc0320b38
c0321048  0020a0e1   mov      r2, r0
c032104c  0250a0e1   mov      r5, r2
c0321050  050000ea   b        #0xc032106c
c0321054  00f020e3   nop      
c0321058  0610a0e1   mov      r1, r6
c032105c  0400a0e1   mov      r0, r4
c0321060  b4feffeb   bl       #0xc0320b38
c0321064  0020a0e1   mov      r2, r0
c0321068  0250a0e1   mov      r5, r2
c032106c  002094e5   ldr      r2, [r4]
c0321070  6430a0e3   mov      r3, #0x64
c0321074  950303e0   mul      r3, r5, r3
c0321078  082092e5   ldr      r2, [r2, #8]
c032107c  022083e0   add      r2, r3, r2
c0321080  0200a0e1   mov      r0, r2
c0321084  7080bde8   pop      {r4, r5, r6, pc}
