c031a0f8  10402de9   push     {r4, lr}
c031a0fc  8c470ae3   movw     r4, #0xa78c
c031a100  43434ce3   movt     r4, #0xc343
c031a104  650f84e2   add      r0, r4, #0x194
c031a108  e0e3f3eb   bl       #0xc0013090
c031a10c  000050e3   cmp      r0, #0
c031a110  0400000a   beq      #0xc031a128
c031a114  0400a0e1   mov      r0, r4
c031a118  baffffeb   bl       #0xc031a008
c031a11c  650f84e2   add      r0, r4, #0x194
c031a120  2fe4f3eb   bl       #0xc00131e4
c031a124  00f020e3   nop      
c031a128  0400a0e1   mov      r0, r4
c031a12c  1080bde8   pop      {r4, pc}
c031a130  04402de5   str      r4, [sp, #-4]!
c031a134  00c0a0e1   mov      ip, r0
c031a138  0140a0e1   mov      r4, r1
c031a13c  00408ce5   str      r4, [ip]
c031a140  04409de4   pop      {r4}
c031a144  1eff2fe1   bx       lr
c031a148  00c0a0e1   mov      ip, r0
c031a14c  00109ce5   ldr      r1, [ip]
c031a150  0100a0e1   mov      r0, r1
c031a154  1eff2fe1   bx       lr
c031a158  04402de5   str      r4, [sp, #-4]!
c031a15c  00c0a0e1   mov      ip, r0
c031a160  0140a0e1   mov      r4, r1
c031a164  04408ce5   str      r4, [ip, #4]
c031a168  04409de4   pop      {r4}
c031a16c  1eff2fe1   bx       lr
c031a170  00c0a0e1   mov      ip, r0
c031a174  04109ce5   ldr      r1, [ip, #4]
c031a178  0100a0e1   mov      r0, r1
c031a17c  1eff2fe1   bx       lr
c031a180  04402de5   str      r4, [sp, #-4]!
c031a184  00c0a0e1   mov      ip, r0
c031a188  0140a0e1   mov      r4, r1
c031a18c  08408ce5   str      r4, [ip, #8]
c031a190  04409de4   pop      {r4}
c031a194  1eff2fe1   bx       lr
c031a198  00c0a0e1   mov      ip, r0
c031a19c  08109ce5   ldr      r1, [ip, #8]
c031a1a0  0100a0e1   mov      r0, r1
c031a1a4  1eff2fe1   bx       lr
c031a1a8  04402de5   str      r4, [sp, #-4]!
c031a1ac  00c0a0e1   mov      ip, r0
c031a1b0  0140a0e1   mov      r4, r1
c031a1b4  0c408ce5   str      r4, [ip, #0xc]
c031a1b8  04409de4   pop      {r4}
c031a1bc  1eff2fe1   bx       lr
c031a1c0  00c0a0e1   mov      ip, r0
c031a1c4  0c109ce5   ldr      r1, [ip, #0xc]
c031a1c8  0100a0e1   mov      r0, r1
c031a1cc  1eff2fe1   bx       lr
c031a1d0  04402de5   str      r4, [sp, #-4]!
c031a1d4  00c0a0e1   mov      ip, r0
c031a1d8  0140a0e1   mov      r4, r1
c031a1dc  10408ce5   str      r4, [ip, #0x10]
c031a1e0  04409de4   pop      {r4}
c031a1e4  1eff2fe1   bx       lr
c031a1e8  00c0a0e1   mov      ip, r0
c031a1ec  10109ce5   ldr      r1, [ip, #0x10]
c031a1f0  0100a0e1   mov      r0, r1
c031a1f4  1eff2fe1   bx       lr
c031a1f8  f04f2de9   push     {r4, r5, r6, r7, r8, sb, sl, fp, lr}
c031a1fc  08d04de2   sub      sp, sp, #8
c031a200  00c0a0e1   mov      ip, r0
c031a204  0140a0e1   mov      r4, r1
c031a208  0250a0e1   mov      r5, r2
c031a20c  0360a0e1   mov      r6, r3
c031a210  2c709de5   ldr      r7, [sp, #0x2c]
c031a214  30a0dde5   ldrb     sl, [sp, #0x30]
c031a218  34b09de5   ldr      fp, [sp, #0x34]
c031a21c  38e19ce5   ldr      lr, [ip, #0x138]
c031a220  14908ce2   add      sb, ip, #0x14
c031a224  0e4189e7   str      r4, [sb, lr, lsl #2]
c031a228  38e19ce5   ldr      lr, [ip, #0x138]
c031a22c  3c908ce2   add      sb, ip, #0x3c
c031a230  0e5189e7   str      r5, [sb, lr, lsl #2]
c031a234  38e19ce5   ldr      lr, [ip, #0x138]
c031a238  64908ce2   add      sb, ip, #0x64
c031a23c  0e6189e7   str      r6, [sb, lr, lsl #2]
c031a240  38e19ce5   ldr      lr, [ip, #0x138]
c031a244  8c908ce2   add      sb, ip, #0x8c
c031a248  0e7189e7   str      r7, [sb, lr, lsl #2]
c031a24c  38819ce5   ldr      r8, [ip, #0x138]
c031a250  08808ce0   add      r8, ip, r8
c031a254  b4a0c8e5   strb     sl, [r8, #0xb4]
c031a258  38e19ce5   ldr      lr, [ip, #0x138]
c031a25c  10909ce5   ldr      sb, [ip, #0x10]
c031a260  e8808ce2   add      r8, ip, #0xe8
c031a264  0e9188e7   str      sb, [r8, lr, lsl #2]
c031a268  38e19ce5   ldr      lr, [ip, #0x138]
c031a26c  119e8ce2   add      sb, ip, #0x110
c031a270  0eb189e7   str      fp, [sb, lr, lsl #2]
c031a274  38e19ce5   ldr      lr, [ip, #0x138]
c031a278  01e08ee2   add      lr, lr, #1
c031a27c  38e18ce5   str      lr, [ip, #0x138]
c031a280  38e19ce5   ldr      lr, [ip, #0x138]
c031a284  0a005ee3   cmp      lr, #0xa
c031a288  0100001a   bne      #0xc031a294
c031a28c  00e0a0e3   mov      lr, #0
c031a290  38e18ce5   str      lr, [ip, #0x138]
c031a294  08d08de2   add      sp, sp, #8
c031a298  f08fbde8   pop      {r4, r5, r6, r7, r8, sb, sl, fp, pc}
c031a29c  00f020e3   nop      
c031a2a0  f04f2de9   push     {r4, r5, r6, r7, r8, sb, sl, fp, lr}
c031a2a4  18d04de2   sub      sp, sp, #0x18
c031a2a8  0060a0e1   mov      r6, r0
c031a2ac  01b0a0e1   mov      fp, r1
c031a2b0  00208de5   str      r2, [sp]
c031a2b4  04308de5   str      r3, [sp, #4]
c031a2b8  38c196e5   ldr      ip, [r6, #0x138]
c031a2bc  00005ce3   cmp      ip, #0
c031a2c0  0200001a   bne      #0xc031a2d0
c031a2c4  0950a0e3   mov      r5, #9
c031a2c8  020000ea   b        #0xc031a2d8
c031a2cc  00f020e3   nop      
c031a2d0  38c196e5   ldr      ip, [r6, #0x138]
c031a2d4  01504ce2   sub      r5, ip, #1
c031a2d8  584e06e3   movw     r4, #0x6e58
c031a2dc  b5404ce3   movt     r4, #0xc0b5
c031a2e0  08c08de2   add      ip, sp, #8
c031a2e4  0b00b4e8   ldm      r4!, {r0, r1, r3}
c031a2e8  0b00ace8   stm      ip!, {r0, r1, r3}
c031a2ec  004094e5   ldr      r4, [r4]
c031a2f0  00408ce5   str      r4, [ip]
c031a2f4  08008de2   add      r0, sp, #8
c031a2f8  8e4d00eb   bl       #0xc032d938
c031a2fc  08c09de5   ldr      ip, [sp, #8]
c031a300  0c704be0   sub      r7, fp, ip
c031a304  00039de8   ldm      sp, {r8, sb}
c031a308  09c048e0   sub      ip, r8, sb
c031a30c  cc4fa0e1   asr      r4, ip, #0x1f
c031a310  24cf8ce0   add      ip, ip, r4, lsr #30
c031a314  4ca1a0e1   asr      sl, ip, #2
c031a318  0ac547e0   sub      ip, r7, sl, lsl #10
c031a31c  01476ce2   rsb      r4, ip, #0x40000
c031a320  0000a0e3   mov      r0, #0
c031a324  c72200eb   bl       #0xc0322e48
c031a328  d0c090e5   ldr      ip, [r0, #0xd0]
c031a32c  94c08ce2   add      ip, ip, #0x94
c031a330  00c09ce5   ldr      ip, [ip]
c031a334  3cff2fe1   blx      ip
c031a338  00c0a0e1   mov      ip, r0
c031a33c  0c4084e0   add      r4, r4, ip
c031a340  05c1a0e1   lsl      ip, r5, #2
c031a344  c0e086e2   add      lr, r6, #0xc0
c031a348  0c408ee7   str      r4, [lr, ip]
c031a34c  18d08de2   add      sp, sp, #0x18
c031a350  f08fbde8   pop      {r4, r5, r6, r7, r8, sb, sl, fp, pc}
c031a354  00f020e3   nop      
c031a358  f04c2de9   push     {r4, r5, r6, r7, sl, fp, lr}
c031a35c  0040a0e1   mov      r4, r0
c031a360  01b0a0e1   mov      fp, r1
c031a364  0050e0e3   mvn      r5, #0
c031a368  0070a0e3   mov      r7, #0
c031a36c  080000ea   b        #0xc031a394
c031a370  e83084e2   add      r3, r4, #0xe8
c031a374  072193e7   ldr      r2, [r3, r7, lsl #2]
c031a378  02005be1   cmp      fp, r2
c031a37c  0300001a   bne      #0xc031a390
c031a380  0721a0e1   lsl      r2, r7, #2
c031a384  143084e2   add      r3, r4, #0x14
c031a388  025093e7   ldr      r5, [r3, r2]
c031a38c  020000ea   b        #0xc031a39c
c031a390  017087e2   add      r7, r7, #1
c031a394  0a0057e3   cmp      r7, #0xa
c031a398  f4ffff3a   blo      #0xc031a370
c031a39c  010075e3   cmn      r5, #1
c031a3a0  2d00001a   bne      #0xc031a45c
c031a3a4  0400a0e1   mov      r0, r4
c031a3a8  8effffeb   bl       #0xc031a1e8
c031a3ac  00005be1   cmp      fp, r0
c031a3b0  0f00009a   bls      #0xc031a3f4
c031a3b4  00a0a0e3   mov      sl, #0
c031a3b8  0060a0e3   mov      r6, #0
c031a3bc  0a0000ea   b        #0xc031a3ec
c031a3c0  e83084e2   add      r3, r4, #0xe8
c031a3c4  062193e7   ldr      r2, [r3, r6, lsl #2]
c031a3c8  02005ae1   cmp      sl, r2
c031a3cc  0500002a   bhs      #0xc031a3e8
c031a3d0  0621a0e1   lsl      r2, r6, #2
c031a3d4  e83084e2   add      r3, r4, #0xe8
c031a3d8  02a093e7   ldr      sl, [r3, r2]
c031a3dc  0621a0e1   lsl      r2, r6, #2
c031a3e0  143084e2   add      r3, r4, #0x14
c031a3e4  025093e7   ldr      r5, [r3, r2]
c031a3e8  016086e2   add      r6, r6, #1
c031a3ec  0a0056e3   cmp      r6, #0xa
c031a3f0  f2ffff3a   blo      #0xc031a3c0
c031a3f4  0400a0e1   mov      r0, r4
c031a3f8  7affffeb   bl       #0xc031a1e8
c031a3fc  0a0050e3   cmp      r0, #0xa
c031a400  1500003a   blo      #0xc031a45c
c031a404  0400a0e1   mov      r0, r4
c031a408  76ffffeb   bl       #0xc031a1e8
c031a40c  0a2040e2   sub      r2, r0, #0xa
c031a410  02005be1   cmp      fp, r2
c031a414  1000008a   bhi      #0xc031a45c
c031a418  0030e0e3   mvn      r3, #0
c031a41c  0020a0e3   mov      r2, #0
c031a420  0b0000ea   b        #0xc031a454
c031a424  00f020e3   nop      
c031a428  e8e084e2   add      lr, r4, #0xe8
c031a42c  02c19ee7   ldr      ip, [lr, r2, lsl #2]
c031a430  0c0053e1   cmp      r3, ip
c031a434  0500009a   bls      #0xc031a450
c031a438  02c1a0e1   lsl      ip, r2, #2
c031a43c  e8e084e2   add      lr, r4, #0xe8
c031a440  0c309ee7   ldr      r3, [lr, ip]
c031a444  02c1a0e1   lsl      ip, r2, #2
c031a448  14e084e2   add      lr, r4, #0x14
c031a44c  0c509ee7   ldr      r5, [lr, ip]
c031a450  012082e2   add      r2, r2, #1
c031a454  0a0052e3   cmp      r2, #0xa
c031a458  f2ffff3a   blo      #0xc031a428
c031a45c  05c0a0e1   mov      ip, r5
c031a460  0c00a0e1   mov      r0, ip
c031a464  f08cbde8   pop      {r4, r5, r6, r7, sl, fp, pc}
c031a468  f04c2de9   push     {r4, r5, r6, r7, sl, fp, lr}
c031a46c  0040a0e1   mov      r4, r0
c031a470  01b0a0e1   mov      fp, r1
c031a474  0050e0e3   mvn      r5, #0
c031a478  0070a0e3   mov      r7, #0
c031a47c  080000ea   b        #0xc031a4a4
c031a480  e83084e2   add      r3, r4, #0xe8
c031a484  072193e7   ldr      r2, [r3, r7, lsl #2]
c031a488  02005be1   cmp      fp, r2
c031a48c  0300001a   bne      #0xc031a4a0
c031a490  0721a0e1   lsl      r2, r7, #2
c031a494  3c3084e2   add      r3, r4, #0x3c
c031a498  025093e7   ldr      r5, [r3, r2]
c031a49c  020000ea   b        #0xc031a4ac
c031a4a0  017087e2   add      r7, r7, #1
c031a4a4  0a0057e3   cmp      r7, #0xa
c031a4a8  f4ffff3a   blo      #0xc031a480
c031a4ac  010075e3   cmn      r5, #1
c031a4b0  2d00001a   bne      #0xc031a56c
c031a4b4  0400a0e1   mov      r0, r4
c031a4b8  4affffeb   bl       #0xc031a1e8
c031a4bc  00005be1   cmp      fp, r0
c031a4c0  0f00009a   bls      #0xc031a504
c031a4c4  00a0a0e3   mov      sl, #0
c031a4c8  0060a0e3   mov      r6, #0
c031a4cc  0a0000ea   b        #0xc031a4fc
c031a4d0  e83084e2   add      r3, r4, #0xe8
c031a4d4  062193e7   ldr      r2, [r3, r6, lsl #2]
c031a4d8  02005ae1   cmp      sl, r2
c031a4dc  0500002a   bhs      #0xc031a4f8
c031a4e0  0621a0e1   lsl      r2, r6, #2
c031a4e4  e83084e2   add      r3, r4, #0xe8
c031a4e8  02a093e7   ldr      sl, [r3, r2]
c031a4ec  0621a0e1   lsl      r2, r6, #2
c031a4f0  3c3084e2   add      r3, r4, #0x3c
c031a4f4  025093e7   ldr      r5, [r3, r2]
c031a4f8  016086e2   add      r6, r6, #1
c031a4fc  0a0056e3   cmp      r6, #0xa
c031a500  f2ffff3a   blo      #0xc031a4d0
c031a504  0400a0e1   mov      r0, r4
c031a508  36ffffeb   bl       #0xc031a1e8
c031a50c  0a0050e3   cmp      r0, #0xa
c031a510  1500003a   blo      #0xc031a56c
c031a514  0400a0e1   mov      r0, r4
c031a518  32ffffeb   bl       #0xc031a1e8
c031a51c  0a2040e2   sub      r2, r0, #0xa
c031a520  02005be1   cmp      fp, r2
c031a524  1000008a   bhi      #0xc031a56c
c031a528  0030e0e3   mvn      r3, #0
c031a52c  0020a0e3   mov      r2, #0
c031a530  0b0000ea   b        #0xc031a564
c031a534  00f020e3   nop      
c031a538  e8e084e2   add      lr, r4, #0xe8
c031a53c  02c19ee7   ldr      ip, [lr, r2, lsl #2]
c031a540  0c0053e1   cmp      r3, ip
c031a544  0500009a   bls      #0xc031a560
c031a548  02c1a0e1   lsl      ip, r2, #2
c031a54c  e8e084e2   add      lr, r4, #0xe8
c031a550  0c309ee7   ldr      r3, [lr, ip]
c031a554  02c1a0e1   lsl      ip, r2, #2
c031a558  3ce084e2   add      lr, r4, #0x3c
c031a55c  0c509ee7   ldr      r5, [lr, ip]
c031a560  012082e2   add      r2, r2, #1
c031a564  0a0052e3   cmp      r2, #0xa
c031a568  f2ffff3a   blo      #0xc031a538
c031a56c  05c0a0e1   mov      ip, r5
c031a570  0c00a0e1   mov      r0, ip
c031a574  f08cbde8   pop      {r4, r5, r6, r7, sl, fp, pc}
c031a578  f04c2de9   push     {r4, r5, r6, r7, sl, fp, lr}
c031a57c  0040a0e1   mov      r4, r0
c031a580  01b0a0e1   mov      fp, r1
c031a584  0050e0e3   mvn      r5, #0
c031a588  0070a0e3   mov      r7, #0
c031a58c  080000ea   b        #0xc031a5b4
c031a590  e83084e2   add      r3, r4, #0xe8
c031a594  072193e7   ldr      r2, [r3, r7, lsl #2]
c031a598  02005be1   cmp      fp, r2
c031a59c  0300001a   bne      #0xc031a5b0
c031a5a0  0721a0e1   lsl      r2, r7, #2
c031a5a4  643084e2   add      r3, r4, #0x64
