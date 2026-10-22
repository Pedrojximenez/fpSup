c0320b38  f0002de9   push     {r4, r5, r6, r7}
c0320b3c  00c0a0e1   mov      ip, r0
c0320b40  0150a0e1   mov      r5, r1
c0320b44  0030a0e3   mov      r3, #0
c0320b48  00209ce5   ldr      r2, [ip]
c0320b4c  0c4092e5   ldr      r4, [r2, #0xc]
c0320b50  0020a0e3   mov      r2, #0
c0320b54  0a0000ea   b        #0xc0320b84
c0320b58  00609ce5   ldr      r6, [ip]
c0320b5c  086096e5   ldr      r6, [r6, #8]
c0320b60  6470a0e3   mov      r7, #0x64
c0320b64  926726e0   mla      r6, r2, r7, r6
c0320b68  006096e5   ldr      r6, [r6]
c0320b6c  060055e1   cmp      r5, r6
c0320b70  0200001a   bne      #0xc0320b80
c0320b74  0230a0e1   mov      r3, r2
c0320b78  030000ea   b        #0xc0320b8c
c0320b7c  00f020e3   nop      
c0320b80  012082e2   add      r2, r2, #1
c0320b84  040052e1   cmp      r2, r4
c0320b88  f2ffff3a   blo      #0xc0320b58
c0320b8c  00f020e3   nop      
c0320b90  0300a0e1   mov      r0, r3
c0320b94  f000bde8   pop      {r4, r5, r6, r7}
c0320b98  1eff2fe1   bx       lr
c0320b9c  00f020e3   nop      
c0320ba0  f0002de9   push     {r4, r5, r6, r7}
c0320ba4  00c0a0e1   mov      ip, r0
c0320ba8  0150a0e1   mov      r5, r1
c0320bac  0030a0e3   mov      r3, #0
c0320bb0  00209ce5   ldr      r2, [ip]
c0320bb4  044092e5   ldr      r4, [r2, #4]
c0320bb8  0020a0e3   mov      r2, #0
c0320bbc  080000ea   b        #0xc0320be4
