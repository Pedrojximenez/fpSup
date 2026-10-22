c03e5648  30402de9   push     {r4, r5, lr}
c03e564c  0040a0e1   mov      r4, r0
c03e5650  0150a0e1   mov      r5, r1
c03e5654  022400e3   movw     r2, #0x402
c03e5658  0510a0e1   mov      r1, r5
c03e565c  040084e2   add      r0, r4, #4
c03e5660  5202feeb   bl       #0xc0365fb0
c03e5664  000050e3   cmp      r0, #0
c03e5668  0200001a   bne      #0xc03e5678
c03e566c  0510a0e1   mov      r1, r5
c03e5670  040084e2   add      r0, r4, #4
c03e5674  1b10feeb   bl       #0xc03696e8
c03e5678  003094e5   ldr      r3, [r4]
c03e567c  060093e8   ldm      r3, {r1, r2}
c03e5680  040084e2   add      r0, r4, #4
c03e5684  9702feeb   bl       #0xc03660e8
c03e5688  040084e2   add      r0, r4, #4
c03e568c  6302feeb   bl       #0xc0366020
c03e5690  3080bde8   pop      {r4, r5, pc}
c03e5694  00f020e3   nop      
