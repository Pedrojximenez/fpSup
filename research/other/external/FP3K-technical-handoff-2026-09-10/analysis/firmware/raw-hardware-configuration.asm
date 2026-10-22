c032d9a0  f04f2de9   push     {r4, r5, r6, r7, r8, sb, sl, fp, lr}
c032d9a4  3cd04de2   sub      sp, sp, #0x3c
c032d9a8  0050a0e1   mov      r5, r0
c032d9ac  01a0a0e1   mov      sl, r1
c032d9b0  02b0a0e1   mov      fp, r2
c032d9b4  0360a0e1   mov      r6, r3
c032d9b8  18860de3   movw     r8, #0xd618
c032d9bc  b8804ce3   movt     r8, #0xc0b8
c032d9c0  005098e8   ldm      r8, {ip, lr}
c032d9c4  34c08de5   str      ip, [sp, #0x34]
c032d9c8  38e08de5   str      lr, [sp, #0x38]
c032d9cc  08008de2   add      r0, sp, #8
c032d9d0  2c20a0e3   mov      r2, #0x2c
c032d9d4  0010a0e3   mov      r1, #0
c032d9d8  9e9df3eb   bl       #0xc0015058
c032d9dc  64409de5   ldr      r4, [sp, #0x64]
c032d9e0  147195e5   ldr      r7, [r5, #0x114]
c032d9e4  84c164e0   rsb      ip, r4, r4, lsl #3
c032d9e8  8cc187e0   add      ip, r7, ip, lsl #3
c032d9ec  06c0dce5   ldrb     ip, [ip, #6]
c032d9f0  09c0cde5   strb     ip, [sp, #9]
c032d9f4  147195e5   ldr      r7, [r5, #0x114]
c032d9f8  84c164e0   rsb      ip, r4, r4, lsl #3
c032d9fc  8cc187e0   add      ip, r7, ip, lsl #3
c032da00  07c0dce5   ldrb     ip, [ip, #7]
c032da04  0cc08de5   str      ip, [sp, #0xc]
c032da08  147195e5   ldr      r7, [r5, #0x114]
c032da0c  84c164e0   rsb      ip, r4, r4, lsl #3
c032da10  8cc187e0   add      ip, r7, ip, lsl #3
c032da14  b8c0dce1   ldrh     ip, [ip, #8]
c032da18  b0c1cde1   strh     ip, [sp, #0x10]
c032da1c  147195e5   ldr      r7, [r5, #0x114]
c032da20  84c164e0   rsb      ip, r4, r4, lsl #3
c032da24  8cc187e0   add      ip, r7, ip, lsl #3
c032da28  bac0dce1   ldrh     ip, [ip, #0xa]
c032da2c  b2c1cde1   strh     ip, [sp, #0x12]
c032da30  147195e5   ldr      r7, [r5, #0x114]
c032da34  84c164e0   rsb      ip, r4, r4, lsl #3
c032da38  8cc187e0   add      ip, r7, ip, lsl #3
c032da3c  bcc0dce1   ldrh     ip, [ip, #0xc]
c032da40  b4c1cde1   strh     ip, [sp, #0x14]
c032da44  147195e5   ldr      r7, [r5, #0x114]
c032da48  84c164e0   rsb      ip, r4, r4, lsl #3
c032da4c  8cc187e0   add      ip, r7, ip, lsl #3
c032da50  bec0dce1   ldrh     ip, [ip, #0xe]
c032da54  b6c1cde1   strh     ip, [sp, #0x16]
c032da58  147195e5   ldr      r7, [r5, #0x114]
c032da5c  84c164e0   rsb      ip, r4, r4, lsl #3
c032da60  8cc187e0   add      ip, r7, ip, lsl #3
c032da64  b0c1dce1   ldrh     ip, [ip, #0x10]
c032da68  b8c1cde1   strh     ip, [sp, #0x18]
c032da6c  147195e5   ldr      r7, [r5, #0x114]
c032da70  84c164e0   rsb      ip, r4, r4, lsl #3
c032da74  8cc187e0   add      ip, r7, ip, lsl #3
c032da78  b2c1dce1   ldrh     ip, [ip, #0x12]
c032da7c  bac1cde1   strh     ip, [sp, #0x1a]
c032da80  147195e5   ldr      r7, [r5, #0x114]
c032da84  84c164e0   rsb      ip, r4, r4, lsl #3
c032da88  8cc187e0   add      ip, r7, ip, lsl #3
c032da8c  b4c1dce1   ldrh     ip, [ip, #0x14]
c032da90  bcc1cde1   strh     ip, [sp, #0x1c]
c032da94  147195e5   ldr      r7, [r5, #0x114]
c032da98  84c164e0   rsb      ip, r4, r4, lsl #3
c032da9c  8cc187e0   add      ip, r7, ip, lsl #3
c032daa0  b6c1dce1   ldrh     ip, [ip, #0x16]
c032daa4  bec1cde1   strh     ip, [sp, #0x1e]
c032daa8  147195e5   ldr      r7, [r5, #0x114]
c032daac  84c164e0   rsb      ip, r4, r4, lsl #3
c032dab0  8cc187e0   add      ip, r7, ip, lsl #3
c032dab4  b8c1dce1   ldrh     ip, [ip, #0x18]
c032dab8  b0c2cde1   strh     ip, [sp, #0x20]
c032dabc  147195e5   ldr      r7, [r5, #0x114]
c032dac0  84c164e0   rsb      ip, r4, r4, lsl #3
c032dac4  8cc187e0   add      ip, r7, ip, lsl #3
c032dac8  1bc0dce5   ldrb     ip, [ip, #0x1b]
c032dacc  23c0cde5   strb     ip, [sp, #0x23]
c032dad0  147195e5   ldr      r7, [r5, #0x114]
c032dad4  84c164e0   rsb      ip, r4, r4, lsl #3
c032dad8  8cc187e0   add      ip, r7, ip, lsl #3
c032dadc  1cc0dce5   ldrb     ip, [ip, #0x1c]
c032dae0  24c0cde5   strb     ip, [sp, #0x24]
c032dae4  147195e5   ldr      r7, [r5, #0x114]
c032dae8  84c164e0   rsb      ip, r4, r4, lsl #3
c032daec  8cc187e0   add      ip, r7, ip, lsl #3
c032daf0  1dc0dce5   ldrb     ip, [ip, #0x1d]
c032daf4  25c0cde5   strb     ip, [sp, #0x25]
c032daf8  147195e5   ldr      r7, [r5, #0x114]
c032dafc  84c164e0   rsb      ip, r4, r4, lsl #3
c032db00  8cc187e0   add      ip, r7, ip, lsl #3
c032db04  1ec0dce5   ldrb     ip, [ip, #0x1e]
c032db08  26c0cde5   strb     ip, [sp, #0x26]
c032db0c  147195e5   ldr      r7, [r5, #0x114]
c032db10  84c164e0   rsb      ip, r4, r4, lsl #3
c032db14  8cc187e0   add      ip, r7, ip, lsl #3
c032db18  1fc0dce5   ldrb     ip, [ip, #0x1f]
c032db1c  27c0cde5   strb     ip, [sp, #0x27]
c032db20  147195e5   ldr      r7, [r5, #0x114]
c032db24  84c164e0   rsb      ip, r4, r4, lsl #3
c032db28  8cc187e0   add      ip, r7, ip, lsl #3
c032db2c  20c0dce5   ldrb     ip, [ip, #0x20]
c032db30  28c0cde5   strb     ip, [sp, #0x28]
c032db34  147195e5   ldr      r7, [r5, #0x114]
c032db38  84c164e0   rsb      ip, r4, r4, lsl #3
c032db3c  8cc187e0   add      ip, r7, ip, lsl #3
c032db40  21c0dce5   ldrb     ip, [ip, #0x21]
c032db44  29c0cde5   strb     ip, [sp, #0x29]
c032db48  147195e5   ldr      r7, [r5, #0x114]
c032db4c  84c164e0   rsb      ip, r4, r4, lsl #3
c032db50  8cc187e0   add      ip, r7, ip, lsl #3
c032db54  22c0dce5   ldrb     ip, [ip, #0x22]
c032db58  2ac0cde5   strb     ip, [sp, #0x2a]
c032db5c  147195e5   ldr      r7, [r5, #0x114]
c032db60  84c164e0   rsb      ip, r4, r4, lsl #3
c032db64  8cc187e0   add      ip, r7, ip, lsl #3
c032db68  23c0dce5   ldrb     ip, [ip, #0x23]
c032db6c  2bc0cde5   strb     ip, [sp, #0x2b]
c032db70  147195e5   ldr      r7, [r5, #0x114]
c032db74  84c164e0   rsb      ip, r4, r4, lsl #3
c032db78  8cc187e0   add      ip, r7, ip, lsl #3
c032db7c  24c0dce5   ldrb     ip, [ip, #0x24]
c032db80  2cc0cde5   strb     ip, [sp, #0x2c]
c032db84  147195e5   ldr      r7, [r5, #0x114]
c032db88  84c164e0   rsb      ip, r4, r4, lsl #3
c032db8c  8cc187e0   add      ip, r7, ip, lsl #3
c032db90  25c0dce5   ldrb     ip, [ip, #0x25]
c032db94  2dc0cde5   strb     ip, [sp, #0x2d]
c032db98  147195e5   ldr      r7, [r5, #0x114]
c032db9c  84c164e0   rsb      ip, r4, r4, lsl #3
c032dba0  8cc187e0   add      ip, r7, ip, lsl #3
c032dba4  26c0dce5   ldrb     ip, [ip, #0x26]
c032dba8  2ec0cde5   strb     ip, [sp, #0x2e]
c032dbac  147195e5   ldr      r7, [r5, #0x114]
c032dbb0  84c164e0   rsb      ip, r4, r4, lsl #3
c032dbb4  8cc187e0   add      ip, r7, ip, lsl #3
c032dbb8  27c0dce5   ldrb     ip, [ip, #0x27]
c032dbbc  2fc0cde5   strb     ip, [sp, #0x2f]
c032dbc0  147195e5   ldr      r7, [r5, #0x114]
c032dbc4  84c164e0   rsb      ip, r4, r4, lsl #3
c032dbc8  8cc187e0   add      ip, r7, ip, lsl #3
c032dbcc  29c0dce5   ldrb     ip, [ip, #0x29]
c032dbd0  31c0cde5   strb     ip, [sp, #0x31]
c032dbd4  147195e5   ldr      r7, [r5, #0x114]
c032dbd8  84c164e0   rsb      ip, r4, r4, lsl #3
c032dbdc  8cc187e0   add      ip, r7, ip, lsl #3
c032dbe0  2ac0dce5   ldrb     ip, [ip, #0x2a]
c032dbe4  32c0cde5   strb     ip, [sp, #0x32]
c032dbe8  147195e5   ldr      r7, [r5, #0x114]
c032dbec  84c164e0   rsb      ip, r4, r4, lsl #3
c032dbf0  8cc187e0   add      ip, r7, ip, lsl #3
c032dbf4  2bc0dce5   ldrb     ip, [ip, #0x2b]
c032dbf8  33c0cde5   strb     ip, [sp, #0x33]
c032dbfc  01cba0e3   mov      ip, #0x400
c032dc00  04c08de5   str      ip, [sp, #4]
c032dc04  0170a0e3   mov      r7, #1
c032dc08  14e195e5   ldr      lr, [r5, #0x114]
c032dc0c  84c164e0   rsb      ip, r4, r4, lsl #3
c032dc10  8cc18ee0   add      ip, lr, ip, lsl #3
c032dc14  2dc0dce5   ldrb     ip, [ip, #0x2d]
c032dc18  34c0cde5   strb     ip, [sp, #0x34]
c032dc1c  00e09ae5   ldr      lr, [sl]
c032dc20  04c09de5   ldr      ip, [sp, #4]
c032dc24  0e005ce1   cmp      ip, lr
c032dc28  0200002a   bhs      #0xc032dc38
c032dc2c  0ac0a0e1   mov      ip, sl
c032dc30  010000ea   b        #0xc032dc3c
c032dc34  00f020e3   nop      
c032dc38  04c08de2   add      ip, sp, #4
c032dc3c  00c09ce5   ldr      ip, [ip]
c032dc40  b6c3cde1   strh     ip, [sp, #0x36]
c032dc44  04e09ae5   ldr      lr, [sl, #4]
c032dc48  04c09de5   ldr      ip, [sp, #4]
c032dc4c  0e005ce1   cmp      ip, lr
c032dc50  0200002a   bhs      #0xc032dc60
c032dc54  04c08ae2   add      ip, sl, #4
c032dc58  010000ea   b        #0xc032dc64
c032dc5c  00f020e3   nop      
c032dc60  04c08de2   add      ip, sp, #4
c032dc64  00c09ce5   ldr      ip, [ip]
c032dc68  b8c3cde1   strh     ip, [sp, #0x38]
c032dc6c  04e09de5   ldr      lr, [sp, #4]
c032dc70  b6c3dde1   ldrh     ip, [sp, #0x36]
c032dc74  0e005ce1   cmp      ip, lr
c032dc78  b8c3dd01   ldrheq   ip, [sp, #0x38]
c032dc7c  0e005c01   cmpeq    ip, lr
c032dc80  0000001a   bne      #0xc032dc88
c032dc84  0070a0e3   mov      r7, #0
c032dc88  34108de2   add      r1, sp, #0x34
c032dc8c  0700a0e1   mov      r0, r7
c032dc90  52200cfa   blx      #0xc0635de0
c032dc94  01c0a0e3   mov      ip, #1
c032dc98  01c0cde5   strb     ip, [sp, #1]
c032dc9c  14e195e5   ldr      lr, [r5, #0x114]
c032dca0  84c164e0   rsb      ip, r4, r4, lsl #3
c032dca4  8cc18ee0   add      ip, lr, ip, lsl #3
c032dca8  2dc0dce5   ldrb     ip, [ip, #0x2d]
c032dcac  34c0cde5   strb     ip, [sp, #0x34]
c032dcb0  00e09be5   ldr      lr, [fp]
c032dcb4  04c09de5   ldr      ip, [sp, #4]
c032dcb8  0e005ce1   cmp      ip, lr
c032dcbc  0100002a   bhs      #0xc032dcc8
c032dcc0  0bc0a0e1   mov      ip, fp
c032dcc4  000000ea   b        #0xc032dccc
c032dcc8  04c08de2   add      ip, sp, #4
c032dccc  00c09ce5   ldr      ip, [ip]
c032dcd0  b6c3cde1   strh     ip, [sp, #0x36]
c032dcd4  04e09be5   ldr      lr, [fp, #4]
c032dcd8  04c09de5   ldr      ip, [sp, #4]
c032dcdc  0e005ce1   cmp      ip, lr
c032dce0  0200002a   bhs      #0xc032dcf0
c032dce4  04c08be2   add      ip, fp, #4
c032dce8  010000ea   b        #0xc032dcf4
c032dcec  00f020e3   nop      
c032dcf0  04c08de2   add      ip, sp, #4
c032dcf4  00c09ce5   ldr      ip, [ip]
c032dcf8  b8c3cde1   strh     ip, [sp, #0x38]
c032dcfc  04e09de5   ldr      lr, [sp, #4]
c032dd00  b6c3dde1   ldrh     ip, [sp, #0x36]
c032dd04  0e005ce1   cmp      ip, lr
c032dd08  b8c3dd01   ldrheq   ip, [sp, #0x38]
c032dd0c  0e005c01   cmpeq    ip, lr
c032dd10  0100001a   bne      #0xc032dd1c
c032dd14  00c0a0e3   mov      ip, #0
c032dd18  01c0cde5   strb     ip, [sp, #1]
c032dd1c  0100dde5   ldrb     r0, [sp, #1]
c032dd20  34108de2   add      r1, sp, #0x34
c032dd24  33200cfa   blx      #0xc0635df8
c032dd28  01c0a0e3   mov      ip, #1
c032dd2c  02c0cde5   strb     ip, [sp, #2]
c032dd30  04c096e5   ldr      ip, [r6, #4]
c032dd34  03005ce3   cmp      ip, #3
c032dd38  0200001a   bne      #0xc032dd48
c032dd3c  02c0a0e3   mov      ip, #2
c032dd40  08c0cde5   strb     ip, [sp, #8]
c032dd44  010000ea   b        #0xc032dd50
c032dd48  00c0a0e3   mov      ip, #0
c032dd4c  08c0cde5   strb     ip, [sp, #8]
c032dd50  00c096e5   ldr      ip, [r6]
c032dd54  05005ce3   cmp      ip, #5
c032dd58  0200001a   bne      #0xc032dd68
c032dd5c  02c0a0e3   mov      ip, #2
c032dd60  22c0cde5   strb     ip, [sp, #0x22]
c032dd64  070000ea   b        #0xc032dd88
c032dd68  00c096e5   ldr      ip, [r6]
c032dd6c  03005ce3   cmp      ip, #3
c032dd70  0200001a   bne      #0xc032dd80
c032dd74  01c0a0e3   mov      ip, #1
c032dd78  22c0cde5   strb     ip, [sp, #0x22]
c032dd7c  010000ea   b        #0xc032dd88
c032dd80  00c0a0e3   mov      ip, #0
c032dd84  22c0cde5   strb     ip, [sp, #0x22]
c032dd88  000057e3   cmp      r7, #0
c032dd8c  22c0dd15   ldrbne   ip, [sp, #0x22]
c032dd90  00005c13   cmpne    ip, #0
c032dd94  0600000a   beq      #0xc032ddb4
c032dd98  f4170cfa   blx      #0xc0633d70
c032dd9c  000050e3   cmp      r0, #0
c032dda0  0300001a   bne      #0xc032ddb4
c032dda4  22c0dde5   ldrb     ip, [sp, #0x22]
c032dda8  30c0cde5   strb     ip, [sp, #0x30]
c032ddac  00c0a0e3   mov      ip, #0
c032ddb0  22c0cde5   strb     ip, [sp, #0x22]
c032ddb4  99d0ffeb   bl       #0xc0322020
c032ddb8  fcc0d0e5   ldrb     ip, [r0, #0xfc]
c032ddbc  00005ce3   cmp      ip, #0
c032ddc0  00c09615   ldrne    ip, [r6]
c032ddc4  01005c13   cmpne    ip, #1
c032ddc8  0600000a   beq      #0xc032dde8
c032ddcc  04c096e5   ldr      ip, [r6, #4]
c032ddd0  01005ce3   cmp      ip, #1
c032ddd4  0300001a   bne      #0xc032dde8
c032ddd8  22c0dde5   ldrb     ip, [sp, #0x22]
c032dddc  30c0cde5   strb     ip, [sp, #0x30]
c032dde0  00c0a0e3   mov      ip, #0
c032dde4  22c0cde5   strb     ip, [sp, #0x22]
c032dde8  0200dde5   ldrb     r0, [sp, #2]
c032ddec  08108de2   add      r1, sp, #8
c032ddf0  ee1f0cfa   blx      #0xc0635db0
c032ddf4  01c0a0e3   mov      ip, #1
c032ddf8  03c0cde5   strb     ip, [sp, #3]
c032ddfc  60809de5   ldr      r8, [sp, #0x60]
c032de00  04c098e5   ldr      ip, [r8, #4]
c032de04  03005ce3   cmp      ip, #3
c032de08  0200001a   bne      #0xc032de18
c032de0c  02c0a0e3   mov      ip, #2
c032de10  08c0cde5   strb     ip, [sp, #8]
c032de14  010000ea   b        #0xc032de20
c032de18  00c0a0e3   mov      ip, #0
c032de1c  08c0cde5   strb     ip, [sp, #8]
c032de20  60809de5   ldr      r8, [sp, #0x60]
c032de24  00c098e5   ldr      ip, [r8]
c032de28  05005ce3   cmp      ip, #5
c032de2c  0300001a   bne      #0xc032de40
c032de30  02c0a0e3   mov      ip, #2
c032de34  22c0cde5   strb     ip, [sp, #0x22]
c032de38  0a0000ea   b        #0xc032de68
c032de3c  00f020e3   nop      
c032de40  60809de5   ldr      r8, [sp, #0x60]
c032de44  00c098e5   ldr      ip, [r8]
c032de48  03005ce3   cmp      ip, #3
c032de4c  0300001a   bne      #0xc032de60
c032de50  01c0a0e3   mov      ip, #1
c032de54  22c0cde5   strb     ip, [sp, #0x22]
c032de58  020000ea   b        #0xc032de68
c032de5c  00f020e3   nop      
c032de60  00c0a0e3   mov      ip, #0
c032de64  22c0cde5   strb     ip, [sp, #0x22]
c032de68  0300dde5   ldrb     r0, [sp, #3]
c032de6c  08108de2   add      r1, sp, #8
c032de70  d41f0cfa   blx      #0xc0635dc8
c032de74  01c0a0e3   mov      ip, #1
c032de78  0c00a0e1   mov      r0, ip
c032de7c  3cd08de2   add      sp, sp, #0x3c
c032de80  f08fbde8   pop      {r4, r5, r6, r7, r8, sb, sl, fp, pc}
c032de84  00f020e3   nop      
c032de88  f04c2de9   push     {r4, r5, r6, r7, sl, fp, lr}
c032de8c  0040a0e1   mov      r4, r0
c032de90  0150a0e1   mov      r5, r1
c032de94  02b0a0e1   mov      fp, r2
c032de98  0360a0e1   mov      r6, r3
c032de9c  0600a0e1   mov      r0, r6
c032dea0  0010a0e3   mov      r1, #0
c032dea4  0f0000eb   bl       #0xc032dee8
c032dea8  00c0a0e1   mov      ip, r0
c032deac  0c70a0e1   mov      r7, ip
c032deb0  0600a0e1   mov      r0, r6
c032deb4  0110a0e3   mov      r1, #1
c032deb8  0a0000eb   bl       #0xc032dee8
c032debc  00c0a0e1   mov      ip, r0
c032dec0  0ca0a0e1   mov      sl, ip
c032dec4  00c094e5   ldr      ip, [r4]
c032dec8  1cf73ce7   udiv     ip, ip, r7
c032decc  00c084e5   str      ip, [r4]
c032ded0  00c095e5   ldr      ip, [r5]
c032ded4  1cfa3ce7   udiv     ip, ip, sl
c032ded8  00c085e5   str      ip, [r5]
c032dedc  00f020e3   nop      
c032dee0  f08cbde8   pop      {r4, r5, r6, r7, sl, fp, pc}
c032dee4  00f020e3   nop      
c032dee8  f0402de9   push     {r4, r5, r6, r7, lr}
c032deec  28d04de2   sub      sp, sp, #0x28
c032def0  0060a0e1   mov      r6, r0
c032def4  0150a0e1   mov      r5, r1
c032def8  0040a0e3   mov      r4, #0
c032defc  0000a0e3   mov      r0, #0
c032df00  d0d3ffeb   bl       #0xc0322e48
c032df04  0610a0e1   mov      r1, r6
c032df08  fcc9ffeb   bl       #0xc0320700
c032df0c  0020a0e1   mov      r2, r0
c032df10  0d30a0e1   mov      r3, sp
c032df14  28c082e2   add      ip, r2, #0x28
