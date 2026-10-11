c03255f8  30402de9   push     {r4, r5, lr}
c03255fc  88450be3   movw     r4, #0xb588
c0325600  0050a0e1   mov      r5, r0
c0325604  43434ce3   movt     r4, #0xc343
c0325608  dc0084e2   add      r0, r4, #0xdc
c032560c  9fb6f3eb   bl       #0xc0013090
c0325610  000050e3   cmp      r0, #0
c0325614  0700000a   beq      #0xc0325638
c0325618  0510a0e1   mov      r1, r5
c032561c  0400a0e1   mov      r0, r4
c0325620  e2ffffeb   bl       #0xc03255b0
c0325624  98070ee3   movw     r0, #0xe798
c0325628  f1024ce3   movt     r0, #0xc2f1
c032562c  30b7f3eb   bl       #0xc00132f4
c0325630  dc0084e2   add      r0, r4, #0xdc
c0325634  eab6f3eb   bl       #0xc00131e4
c0325638  0400a0e1   mov      r0, r4
c032563c  3080bde8   pop      {r4, r5, pc}
