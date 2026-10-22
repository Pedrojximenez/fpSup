c031d950  10402de9   push     {r4, lr}
c031d954  74490ae3   movw     r4, #0xa974
c031d958  43434ce3   movt     r4, #0xc343
c031d95c  200084e2   add      r0, r4, #0x20
c031d960  cad5f3eb   bl       #0xc0013090
c031d964  000050e3   cmp      r0, #0
c031d968  0400000a   beq      #0xc031d980
c031d96c  0400a0e1   mov      r0, r4
c031d970  ecffffeb   bl       #0xc031d928
c031d974  200084e2   add      r0, r4, #0x20
c031d978  19d6f3eb   bl       #0xc00131e4
c031d97c  00f020e3   nop      
c031d980  0400a0e1   mov      r0, r4
c031d984  1080bde8   pop      {r4, pc}
c031d988  f04d2de9   push     {r4, r5, r6, r7, r8, sl, fp, lr}
c031d98c  94d04de2   sub      sp, sp, #0x94
c031d990  0050a0e1   mov      r5, r0
c031d994  fd6204eb   bl       #0xc0436590
c031d998  08108de2   add      r1, sp, #8
c031d99c  d16504eb   bl       #0xc04370e8
c031d9a0  08109de5   ldr      r1, [sp, #8]
c031d9a4  0160a0e1   mov      r6, r1
c031d9a8  08109de5   ldr      r1, [sp, #8]
c031d9ac  587081e2   add      r7, r1, #0x58
c031d9b0  5c008de2   add      r0, sp, #0x5c
c031d9b4  3820a0e3   mov      r2, #0x38
c031d9b8  0010a0e3   mov      r1, #0
c031d9bc  a5ddf3eb   bl       #0xc0015058
c031d9c0  10008de2   add      r0, sp, #0x10
c031d9c4  4c20a0e3   mov      r2, #0x4c
c031d9c8  0010a0e3   mov      r1, #0
c031d9cc  a1ddf3eb   bl       #0xc0015058
c031d9d0  001096e5   ldr      r1, [r6]
c031d9d4  5c108de5   str      r1, [sp, #0x5c]
c031d9d8  041096e5   ldr      r1, [r6, #4]
c031d9dc  60108de5   str      r1, [sp, #0x60]
c031d9e0  481096e5   ldr      r1, [r6, #0x48]
c031d9e4  443107e3   movw     r3, #0x7144
c031d9e8  b5304ce3   movt     r3, #0xc0b5
c031d9ec  002093e5   ldr      r2, [r3]
c031d9f0  020051e1   cmp      r1, r2
c031d9f4  0300002a   bhs      #0xc031da08
c031d9f8  441107e3   movw     r1, #0x7144
c031d9fc  b5104ce3   movt     r1, #0xc0b5
c031da00  010000ea   b        #0xc031da0c
c031da04  00f020e3   nop      
c031da08  481086e2   add      r1, r6, #0x48
c031da0c  001091e5   ldr      r1, [r1]
c031da10  64108de5   str      r1, [sp, #0x64]
c031da14  4c1096e5   ldr      r1, [r6, #0x4c]
c031da18  443107e3   movw     r3, #0x7144
c031da1c  b5304ce3   movt     r3, #0xc0b5
c031da20  002093e5   ldr      r2, [r3]
c031da24  020051e1   cmp      r1, r2
c031da28  0200002a   bhs      #0xc031da38
c031da2c  441107e3   movw     r1, #0x7144
c031da30  b5104ce3   movt     r1, #0xc0b5
c031da34  000000ea   b        #0xc031da3c
c031da38  4c1086e2   add      r1, r6, #0x4c
c031da3c  001091e5   ldr      r1, [r1]
c031da40  68108de5   str      r1, [sp, #0x68]
c031da44  500086e2   add      r0, r6, #0x50
c031da48  f044fceb   bl       #0xc022ee10
c031da4c  0010a0e1   mov      r1, r0
c031da50  6c108de5   str      r1, [sp, #0x6c]
c031da54  540086e2   add      r0, r6, #0x54
c031da58  0c45fceb   bl       #0xc022ee90
c031da5c  0010a0e1   mov      r1, r0
c031da60  70108de5   str      r1, [sp, #0x70]
c031da64  201096e5   ldr      r1, [r6, #0x20]
c031da68  74108de5   str      r1, [sp, #0x74]
c031da6c  001097e5   ldr      r1, [r7]
c031da70  78108de5   str      r1, [sp, #0x78]
c031da74  041097e5   ldr      r1, [r7, #4]
c031da78  7c108de5   str      r1, [sp, #0x7c]
c031da7c  481097e5   ldr      r1, [r7, #0x48]
c031da80  443107e3   movw     r3, #0x7144
c031da84  b5304ce3   movt     r3, #0xc0b5
c031da88  002093e5   ldr      r2, [r3]
c031da8c  020051e1   cmp      r1, r2
c031da90  0200002a   bhs      #0xc031daa0
c031da94  441107e3   movw     r1, #0x7144
c031da98  b5104ce3   movt     r1, #0xc0b5
c031da9c  000000ea   b        #0xc031daa4
c031daa0  481087e2   add      r1, r7, #0x48
c031daa4  001091e5   ldr      r1, [r1]
c031daa8  80108de5   str      r1, [sp, #0x80]
c031daac  4c1097e5   ldr      r1, [r7, #0x4c]
c031dab0  443107e3   movw     r3, #0x7144
c031dab4  b5304ce3   movt     r3, #0xc0b5
c031dab8  002093e5   ldr      r2, [r3]
c031dabc  020051e1   cmp      r1, r2
c031dac0  0200002a   bhs      #0xc031dad0
c031dac4  441107e3   movw     r1, #0x7144
c031dac8  b5104ce3   movt     r1, #0xc0b5
c031dacc  000000ea   b        #0xc031dad4
c031dad0  4c1087e2   add      r1, r7, #0x4c
c031dad4  001091e5   ldr      r1, [r1]
c031dad8  84108de5   str      r1, [sp, #0x84]
c031dadc  500087e2   add      r0, r7, #0x50
c031dae0  ca44fceb   bl       #0xc022ee10
c031dae4  0010a0e1   mov      r1, r0
c031dae8  88108de5   str      r1, [sp, #0x88]
c031daec  540087e2   add      r0, r7, #0x54
c031daf0  e644fceb   bl       #0xc022ee90
c031daf4  0010a0e1   mov      r1, r0
c031daf8  8c108de5   str      r1, [sp, #0x8c]
c031dafc  201097e5   ldr      r1, [r7, #0x20]
c031db00  90108de5   str      r1, [sp, #0x90]
c031db04  0010a0e3   mov      r1, #0
c031db08  5410cde5   strb     r1, [sp, #0x54]
c031db0c  0110a0e3   mov      r1, #1
c031db10  14108de5   str      r1, [sp, #0x14]
c031db14  0110a0e3   mov      r1, #1
c031db18  18108de5   str      r1, [sp, #0x18]
c031db1c  0110a0e3   mov      r1, #1
c031db20  1c108de5   str      r1, [sp, #0x1c]
c031db24  0110a0e3   mov      r1, #1
c031db28  20108de5   str      r1, [sp, #0x20]
c031db2c  0010a0e3   mov      r1, #0
c031db30  24108de5   str      r1, [sp, #0x24]
c031db34  0110a0e3   mov      r1, #1
c031db38  28108de5   str      r1, [sp, #0x28]
c031db3c  0210a0e3   mov      r1, #2
c031db40  2c108de5   str      r1, [sp, #0x2c]
c031db44  0010a0e3   mov      r1, #0
c031db48  1010cde5   strb     r1, [sp, #0x10]
c031db4c  0010a0e3   mov      r1, #0
c031db50  1110cde5   strb     r1, [sp, #0x11]
c031db54  0010a0e3   mov      r1, #0
c031db58  1210cde5   strb     r1, [sp, #0x12]
c031db5c  0010a0e3   mov      r1, #0
c031db60  3010cde5   strb     r1, [sp, #0x30]
c031db64  0010a0e3   mov      r1, #0
c031db68  3110cde5   strb     r1, [sp, #0x31]
c031db6c  0110a0e3   mov      r1, #1
c031db70  34108de5   str      r1, [sp, #0x34]
c031db74  0110a0e3   mov      r1, #1
c031db78  38108de5   str      r1, [sp, #0x38]
c031db7c  0110a0e3   mov      r1, #1
c031db80  3c108de5   str      r1, [sp, #0x3c]
c031db84  0110a0e3   mov      r1, #1
c031db88  40108de5   str      r1, [sp, #0x40]
c031db8c  011ba0e3   mov      r1, #0x400
c031db90  44108de5   str      r1, [sp, #0x44]
c031db94  011ba0e3   mov      r1, #0x400
c031db98  48108de5   str      r1, [sp, #0x48]
c031db9c  011ba0e3   mov      r1, #0x400
c031dba0  4c108de5   str      r1, [sp, #0x4c]
c031dba4  011ba0e3   mov      r1, #0x400
c031dba8  50108de5   str      r1, [sp, #0x50]
c031dbac  0000a0e3   mov      r0, #0
c031dbb0  a41400eb   bl       #0xc0322e48
c031dbb4  0010a0e1   mov      r1, r0
c031dbb8  01a0a0e1   mov      sl, r1
c031dbbc  d0109ae5   ldr      r1, [sl, #0xd0]
c031dbc0  10208de2   add      r2, sp, #0x10
c031dbc4  9c3091e5   ldr      r3, [r1, #0x9c]
c031dbc8  5c108de2   add      r1, sp, #0x5c
c031dbcc  0a00a0e1   mov      r0, sl
c031dbd0  33ff2fe1   blx      r3
c031dbd4  3000dde5   ldrb     r0, [sp, #0x30]
c031dbd8  54580cfa   blx      #0xc0633d30
c031dbdc  3100dde5   ldrb     r0, [sp, #0x31]
c031dbe0  6a580cfa   blx      #0xc0633d90
c031dbe4  58209de5   ldr      r2, [sp, #0x58]
c031dbe8  3c108de2   add      r1, sp, #0x3c
c031dbec  06008de8   stm      sp, {r1, r2}
c031dbf0  34308de2   add      r3, sp, #0x34
c031dbf4  4c208de2   add      r2, sp, #0x4c
c031dbf8  44108de2   add      r1, sp, #0x44
c031dbfc  0a00a0e1   mov      r0, sl
c031dc00  ba0b00eb   bl       #0xc0320af0
c031dc04  1010dde5   ldrb     r1, [sp, #0x10]
c031dc08  0010c5e5   strb     r1, [r5]
c031dc0c  1110dde5   ldrb     r1, [sp, #0x11]
c031dc10  0110c5e5   strb     r1, [r5, #1]
c031dc14  1210dde5   ldrb     r1, [sp, #0x12]
c031dc18  0210c5e5   strb     r1, [r5, #2]
c031dc1c  14109de5   ldr      r1, [sp, #0x14]
c031dc20  041085e5   str      r1, [r5, #4]
c031dc24  18109de5   ldr      r1, [sp, #0x18]
c031dc28  081085e5   str      r1, [r5, #8]
c031dc2c  24109de5   ldr      r1, [sp, #0x24]
c031dc30  141085e5   str      r1, [r5, #0x14]
c031dc34  28109de5   ldr      r1, [sp, #0x28]
c031dc38  181085e5   str      r1, [r5, #0x18]
c031dc3c  2c109de5   ldr      r1, [sp, #0x2c]
c031dc40  1c1085e5   str      r1, [r5, #0x1c]
c031dc44  040095e5   ldr      r0, [r5, #4]
c031dc48  16600cfa   blx      #0xc0635ca8
c031dc4c  080095e5   ldr      r0, [r5, #8]
c031dc50  1e600cfa   blx      #0xc0635cd0
c031dc54  5410dde5   ldrb     r1, [sp, #0x54]
c031dc58  000051e3   cmp      r1, #0
c031dc5c  0700000a   beq      #0xc031dc80
c031dc60  0110a0e3   mov      r1, #1
c031dc64  0020a0e3   mov      r2, #0
c031dc68  0100a0e1   mov      r0, r1
c031dc6c  23600cfa   blx      #0xc0635d00
c031dc70  0010a0e3   mov      r1, #0
c031dc74  0100a0e1   mov      r0, r1
c031dc78  505a0cfa   blx      #0xc06345c0
c031dc7c  070000ea   b        #0xc031dca0
c031dc80  0020a0e3   mov      r2, #0
c031dc84  0210a0e1   mov      r1, r2
c031dc88  0100a0e3   mov      r0, #1
c031dc8c  1b600cfa   blx      #0xc0635d00
c031dc90  0010a0e3   mov      r1, #0
c031dc94  0100a0e1   mov      r0, r1
c031dc98  485a0cfa   blx      #0xc06345c0
c031dc9c  00f020e3   nop      
c031dca0  18bfffeb   bl       #0xc030d908
c031dca4  0010a0e1   mov      r1, r0
c031dca8  0140a0e1   mov      r4, r1
c031dcac  0400a0e1   mov      r0, r4
c031dcb0  2abfffeb   bl       #0xc030d960
c031dcb4  000050e3   cmp      r0, #0
c031dcb8  a001000a   beq      #0xc031e340
c031dcbc  0400a0e1   mov      r0, r4
c031dcc0  2abfffeb   bl       #0xc030d970
c031dcc4  080010e3   tst      r0, #8
c031dcc8  9c01000a   beq      #0xc031e340
c031dccc  0400a0e1   mov      r0, r4
c031dcd0  22bfffeb   bl       #0xc030d960
