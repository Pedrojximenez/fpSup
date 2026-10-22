c03146e0  0540a0e1   mov      r4, r5
c03146e4  10408de5   str      r4, [sp, #0x10]
c03146e8  14408de5   str      r4, [sp, #0x14]
c03146ec  18408de5   str      r4, [sp, #0x18]
c03146f0  1c408de5   str      r4, [sp, #0x1c]
c03146f4  10008de2   add      r0, sp, #0x10
c03146f8  a07f0cfa   blx      #0xc0634580
c03146fc  0100a0e3   mov      r0, #1
c0314700  30d08de2   add      sp, sp, #0x30
c0314704  f08dbde8   pop      {r4, r5, r6, r7, r8, sl, fp, pc}
c0314708  f04c2de9   push     {r4, r5, r6, r7, sl, fp, lr}
c031470c  04d04de2   sub      sp, sp, #4
c0314710  0060a0e1   mov      r6, r0
c0314714  c0460ae3   movw     r4, #0xa6c0
c0314718  0170a0e1   mov      r7, r1
c031471c  4ca606e3   movw     sl, #0x664c
c0314720  43434ce3   movt     r4, #0xc343
c0314724  b5a04ce3   movt     sl, #0xc0b5
c0314728  76e4ffeb   bl       #0xc030d908
c031472c  00b0a0e1   mov      fp, r0
c0314730  0b00a0e1   mov      r0, fp
c0314734  a5e4ffeb   bl       #0xc030d9d0
c0314738  040050e3   cmp      r0, #4
c031473c  0300001a   bne      #0xc0314750
c0314740  001096e5   ldr      r1, [r6]
c0314744  0b00a0e1   mov      r0, fp
c0314748  d2e5ffeb   bl       #0xc030de98
c031474c  00f020e3   nop      
c0314750  007086e5   str      r7, [r6]
c0314754  513400eb   bl       #0xc03218a0
c0314758  581603e3   movw     r1, #0x3658
c031475c  31104ce3   movt     r1, #0xc031
c0314760  8a3400eb   bl       #0xc0321990
c0314764  0000a0e3   mov      r0, #0
c0314768  000084e5   str      r0, [r4]
c031476c  0000a0e3   mov      r0, #0
c0314770  040084e5   str      r0, [r4, #4]
c0314774  b7850cfa   blx      #0xc0635e58
c0314778  0040a0e1   mov      r4, r0
c031477c  000054e3   cmp      r4, #0
c0314780  0200000a   beq      #0xc0314790
c0314784  0a00a0e1   mov      r0, sl
c0314788  a61fa0e3   mov      r1, #0x298
c031478c  5bf2f3eb   bl       #0xc0011100
c0314790  00f020e3   nop      
c0314794  c3850cfa   blx      #0xc0635ea8
c0314798  0040a0e1   mov      r4, r0
c031479c  000054e3   cmp      r4, #0
c03147a0  0200000a   beq      #0xc03147b0
c03147a4  9a1200e3   movw     r1, #0x29a
c03147a8  0a00a0e1   mov      r0, sl
c03147ac  53f2f3eb   bl       #0xc0011100
c03147b0  00f020e3   nop      
c03147b4  0000a0e3   mov      r0, #0
c03147b8  48890cfa   blx      #0xc0636ce0
c03147bc  0040a0e1   mov      r4, r0
c03147c0  000054e3   cmp      r4, #0
c03147c4  0300000a   beq      #0xc03147d8
c03147c8  0a00a0e1   mov      r0, sl
c03147cc  a71fa0e3   mov      r1, #0x29c
c03147d0  4af2f3eb   bl       #0xc0011100
c03147d4  00f020e3   nop      
c03147d8  00f020e3   nop      
c03147dc  0000a0e3   mov      r0, #0
c03147e0  44890cfa   blx      #0xc0636cf8
c03147e4  0040a0e1   mov      r4, r0
c03147e8  000054e3   cmp      r4, #0
c03147ec  0300000a   beq      #0xc0314800
c03147f0  9e1200e3   movw     r1, #0x29e
c03147f4  0a00a0e1   mov      r0, sl
c03147f8  40f2f3eb   bl       #0xc0011100
c03147fc  00f020e3   nop      
c0314800  00f020e3   nop      
c0314804  0000a0e3   mov      r0, #0
c0314808  8e3900eb   bl       #0xc0322e48
c031480c  0050a0e1   mov      r5, r0
c0314810  0500a0e1   mov      r0, r5
c0314814  b73200eb   bl       #0xc03212f8
c0314818  0010a0e1   mov      r1, r0
c031481c  0500a0e1   mov      r0, r5
c0314820  b83200eb   bl       #0xc0321308
c0314824  001096e5   ldr      r1, [r6]
c0314828  0500a0e1   mov      r0, r5
c031482c  ab3200eb   bl       #0xc03212e0
c0314830  001096e5   ldr      r1, [r6]
c0314834  0500a0e1   mov      r0, r5
c0314838  943200eb   bl       #0xc0321290
c031483c  f13400eb   bl       #0xc0321c08
c0314840  3a3500eb   bl       #0xc0321d30
c0314844  d02095e5   ldr      r2, [r5, #0xd0]
c0314848  582082e2   add      r2, r2, #0x58
c031484c  002092e5   ldr      r2, [r2]
c0314850  0500a0e1   mov      r0, r5
c0314854  0710a0e1   mov      r1, r7
c0314858  32ff2fe1   blx      r2
c031485c  0700a0e1   mov      r0, r7
c0314860  de43f8fa   blx      #0xc01257e0
c0314864  0100a0e3   mov      r0, #1
c0314868  3c47f8fa   blx      #0xc0126560
c031486c  0040a0e1   mov      r4, r0
c0314870  000054e3   cmp      r4, #0
c0314874  0300000a   beq      #0xc0314888
c0314878  b21200e3   movw     r1, #0x2b2
c031487c  0a00a0e1   mov      r0, sl
c0314880  1ef2f3eb   bl       #0xc0011100
c0314884  00f020e3   nop      
c0314888  00f020e3   nop      
c031488c  001096e5   ldr      r1, [r6]
c0314890  0030a0e3   mov      r3, #0
c0314894  0320a0e1   mov      r2, r3
c0314898  0500a0e1   mov      r0, r5
c031489c  833000eb   bl       #0xc0320ab0
c03148a0  000050e3   cmp      r0, #0
c03148a4  0100001a   bne      #0xc03148b0
c03148a8  0000a0e3   mov      r0, #0
c03148ac  3d0000ea   b        #0xc03149a8
c03148b0  20e6ffeb   bl       #0xc030e138
c03148b4  0010a0e3   mov      r1, #0
c03148b8  00108de5   str      r1, [sp]
c03148bc  0030a0e3   mov      r3, #0
c03148c0  0710a0e1   mov      r1, r7
c03148c4  0320a0e1   mov      r2, r3
c03148c8  74e6ffeb   bl       #0xc030e2a0
c03148cc  19e6ffeb   bl       #0xc030e138
c03148d0  0010a0e3   mov      r1, #0
c03148d4  00108de5   str      r1, [sp]
c03148d8  0030a0e3   mov      r3, #0
c03148dc  0710a0e1   mov      r1, r7
c03148e0  0320a0e1   mov      r2, r3
c03148e4  6bebffeb   bl       #0xc030f698
c03148e8  580b01e3   movw     r0, #0x1b58
c03148ec  20034ce3   movt     r0, #0xc320
c03148f0  e6f9f3eb   bl       #0xc0013090
c03148f4  000050e3   cmp      r0, #0
c03148f8  0600000a   beq      #0xc0314918
c03148fc  140b01e3   movw     r0, #0x1b14
c0314900  20034ce3   movt     r0, #0xc320
c0314904  cff2ffeb   bl       #0xc0311448
c0314908  580b01e3   movw     r0, #0x1b58
c031490c  20034ce3   movt     r0, #0xc320
c0314910  33faf3eb   bl       #0xc00131e4
c0314914  00f020e3   nop      
c0314918  140b01e3   movw     r0, #0x1b14
c031491c  20034ce3   movt     r0, #0xc320
c0314920  0710a0e1   mov      r1, r7
c0314924  0020a0e3   mov      r2, #0
c0314928  faf8ffeb   bl       #0xc0312d18
c031492c  d02095e5   ldr      r2, [r5, #0xd0]
c0314930  001096e5   ldr      r1, [r6]
c0314934  202082e2   add      r2, r2, #0x20
c0314938  002092e5   ldr      r2, [r2]
c031493c  0500a0e1   mov      r0, r5
c0314940  32ff2fe1   blx      r2
c0314944  000050e3   cmp      r0, #0
c0314948  0200001a   bne      #0xc0314958
c031494c  0000a0e3   mov      r0, #0
c0314950  140000ea   b        #0xc03149a8
c0314954  00f020e3   nop      
c0314958  001096e5   ldr      r1, [r6]
c031495c  0500a0e1   mov      r0, r5
c0314960  a82d00eb   bl       #0xc0320008
c0314964  000050e3   cmp      r0, #0
c0314968  0200001a   bne      #0xc0314978
c031496c  0000a0e3   mov      r0, #0
c0314970  0c0000ea   b        #0xc03149a8
c0314974  00f020e3   nop      
c0314978  d02095e5   ldr      r2, [r5, #0xd0]
c031497c  0030a0e3   mov      r3, #0
c0314980  0500a0e1   mov      r0, r5
c0314984  78c092e5   ldr      ip, [r2, #0x78]
c0314988  0310a0e1   mov      r1, r3
c031498c  0320a0e1   mov      r2, r3
c0314990  3cff2fe1   blx      ip
c0314994  b345f8fa   blx      #0xc0126068
c0314998  ba45f8fa   blx      #0xc0126088
c031499c  c145f8fa   blx      #0xc01260a8
c03149a0  ce45f8fa   blx      #0xc01260e0
c03149a4  0100a0e3   mov      r0, #1
c03149a8  04d08de2   add      sp, sp, #4
c03149ac  f08cbde8   pop      {r4, r5, r6, r7, sl, fp, pc}
c03149b0  f04b2de9   push     {r4, r5, r6, r7, r8, sb, fp, lr}
c03149b4  2cd04de2   sub      sp, sp, #0x2c
c03149b8  28008de5   str      r0, [sp, #0x28]
c03149bc  0000a0e3   mov      r0, #0
c03149c0  203900eb   bl       #0xc0322e48
c03149c4  0050a0e1   mov      r5, r0
c03149c8  0500a0e1   mov      r0, r5
c03149cc  5b2f00eb   bl       #0xc0320740
c03149d0  000050e3   cmp      r0, #0
c03149d4  0100001a   bne      #0xc03149e0
c03149d8  0000a0e3   mov      r0, #0
c03149dc  ee0100ea   b        #0xc031519c
c03149e0  d01095e5   ldr      r1, [r5, #0xd0]
c03149e4  1c1081e2   add      r1, r1, #0x1c
c03149e8  001091e5   ldr      r1, [r1]
c03149ec  0500a0e1   mov      r0, r5
c03149f0  31ff2fe1   blx      r1
c03149f4  000050e3   cmp      r0, #0
c03149f8  0200001a   bne      #0xc0314a08
c03149fc  0000a0e3   mov      r0, #0
c0314a00  e50100ea   b        #0xc031519c
c0314a04  00f020e3   nop      
c0314a08  28009de5   ldr      r0, [sp, #0x28]
c0314a0c  bffaffeb   bl       #0xc0313510
c0314a10  b81500eb   bl       #0xc031a0f8
c0314a14  10008de5   str      r0, [sp, #0x10]
c0314a18  0000a0e3   mov      r0, #0
c0314a1c  0500cde5   strb     r0, [sp, #5]
c0314a20  10009de5   ldr      r0, [sp, #0x10]
c0314a24  d11500eb   bl       #0xc031a170
c0314a28  000050e3   cmp      r0, #0
c0314a2c  0200001a   bne      #0xc0314a3c
c0314a30  c62300eb   bl       #0xc031d950
c0314a34  d32300eb   bl       #0xc031d988
c0314a38  0500cde5   strb     r0, [sp, #5]
c0314a3c  bde5ffeb   bl       #0xc030e138
c0314a40  28209de5   ldr      r2, [sp, #0x28]
c0314a44  0010a0e3   mov      r1, #0
c0314a48  00108de5   str      r1, [sp]
c0314a4c  001092e5   ldr      r1, [r2]
c0314a50  0030a0e3   mov      r3, #0
c0314a54  0120a0e3   mov      r2, #1
c0314a58  10e6ffeb   bl       #0xc030e2a0
c0314a5c  b5e5ffeb   bl       #0xc030e138
c0314a60  28209de5   ldr      r2, [sp, #0x28]
c0314a64  0010a0e3   mov      r1, #0
c0314a68  00108de5   str      r1, [sp]
c0314a6c  001092e5   ldr      r1, [r2]
c0314a70  0030a0e3   mov      r3, #0
c0314a74  0120a0e3   mov      r2, #1
c0314a78  06ebffeb   bl       #0xc030f698
c0314a7c  580b01e3   movw     r0, #0x1b58
c0314a80  20034ce3   movt     r0, #0xc320
c0314a84  81f9f3eb   bl       #0xc0013090
c0314a88  000050e3   cmp      r0, #0
c0314a8c  0500000a   beq      #0xc0314aa8
c0314a90  140b01e3   movw     r0, #0x1b14
c0314a94  20034ce3   movt     r0, #0xc320
c0314a98  6af2ffeb   bl       #0xc0311448
c0314a9c  580b01e3   movw     r0, #0x1b58
c0314aa0  20034ce3   movt     r0, #0xc320
c0314aa4  cef9f3eb   bl       #0xc00131e4
c0314aa8  28009de5   ldr      r0, [sp, #0x28]
c0314aac  0120a0e3   mov      r2, #1
c0314ab0  001090e5   ldr      r1, [r0]
c0314ab4  140b01e3   movw     r0, #0x1b14
c0314ab8  20034ce3   movt     r0, #0xc320
c0314abc  95f8ffeb   bl       #0xc0312d18
c0314ac0  0000a0e3   mov      r0, #0
c0314ac4  0600cde5   strb     r0, [sp, #6]
c0314ac8  10009de5   ldr      r0, [sp, #0x10]
c0314acc  a71500eb   bl       #0xc031a170
c0314ad0  000050e3   cmp      r0, #0
c0314ad4  0100001a   bne      #0xc0314ae0
c0314ad8  0100a0e3   mov      r0, #1
c0314adc  0600cde5   strb     r0, [sp, #6]
c0314ae0  461800eb   bl       #0xc031ac00
c0314ae4  0610dde5   ldrb     r1, [sp, #6]
c0314ae8  2c1a00eb   bl       #0xc031b3a0
c0314aec  e13300eb   bl       #0xc0321a78
c0314af0  2a3400eb   bl       #0xc0321ba0
c0314af4  10009de5   ldr      r0, [sp, #0x10]
c0314af8  9c1500eb   bl       #0xc031a170
c0314afc  000050e3   cmp      r0, #0
