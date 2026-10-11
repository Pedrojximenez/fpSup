c0206e98  10402de9   push     {r4, lr}
c0206e9c  5c4608e3   movw     r4, #0x865c
c0206ea0  1f434ce3   movt     r4, #0xc31f
c0206ea4  340600e3   movw     r0, #0x634
c0206ea8  040080e0   add      r0, r0, r4
c0206eac  7730f8eb   bl       #0xc0013090
c0206eb0  000050e3   cmp      r0, #0
c0206eb4  0700000a   beq      #0xc0206ed8
c0206eb8  0400a0e1   mov      r0, r4
c0206ebc  b5ffffeb   bl       #0xc0206d98
c0206ec0  540207e3   movw     r0, #0x7254
c0206ec4  f1024ce3   movt     r0, #0xc2f1
c0206ec8  0931f8eb   bl       #0xc00132f4
c0206ecc  340600e3   movw     r0, #0x634
c0206ed0  040080e0   add      r0, r0, r4
c0206ed4  c230f8eb   bl       #0xc00131e4
c0206ed8  0400a0e1   mov      r0, r4
c0206edc  1080bde8   pop      {r4, pc}
