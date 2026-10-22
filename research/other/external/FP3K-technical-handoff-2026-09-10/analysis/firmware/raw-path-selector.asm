c0325228  f0002de9   push     {r4, r5, r6, r7}
c032522c  0050a0e1   mov      r5, r0
c0325230  0140a0e1   mov      r4, r1
c0325234  02c0a0e1   mov      ip, r2
c0325238  003094e5   ldr      r3, [r4]
c032523c  000053e3   cmp      r3, #0
c0325240  04309405   ldreq    r3, [r4, #4]
c0325244  00005303   cmpeq    r3, #0
c0325248  1600001a   bne      #0xc03252a8
c032524c  0130a0e3   mov      r3, #1
c0325250  04308ce5   str      r3, [ip, #4]
c0325254  0030a0e3   mov      r3, #0
c0325258  14308ce5   str      r3, [ip, #0x14]
c032525c  0130a0e3   mov      r3, #1
c0325260  08308ce5   str      r3, [ip, #8]
c0325264  0130a0e3   mov      r3, #1
c0325268  18308ce5   str      r3, [ip, #0x18]
c032526c  0030a0e3   mov      r3, #0
c0325270  2030cce5   strb     r3, [ip, #0x20]
c0325274  243094e5   ldr      r3, [r4, #0x24]
c0325278  286094e5   ldr      r6, [r4, #0x28]
c032527c  34308ce5   str      r3, [ip, #0x34]
c0325280  38608ce5   str      r6, [ip, #0x38]
c0325284  2c3094e5   ldr      r3, [r4, #0x2c]
c0325288  306094e5   ldr      r6, [r4, #0x30]
c032528c  24308ce5   str      r3, [ip, #0x24]
c0325290  28608ce5   str      r6, [ip, #0x28]
c0325294  0030a0e3   mov      r3, #0
c0325298  4430cce5   strb     r3, [ip, #0x44]
c032529c  0030a0e3   mov      r3, #0
c03252a0  48308ce5   str      r3, [ip, #0x48]
c03252a4  bf0000ea   b        #0xc03255a8
c03252a8  086094e5   ldr      r6, [r4, #8]
c03252ac  247094e5   ldr      r7, [r4, #0x24]
c03252b0  0030a0e3   mov      r3, #0
c03252b4  070056e1   cmp      r6, r7
c03252b8  0300001a   bne      #0xc03252cc
c03252bc  287094e5   ldr      r7, [r4, #0x28]
c03252c0  0c6094e5   ldr      r6, [r4, #0xc]
c03252c4  070056e1   cmp      r6, r7
c03252c8  0130a003   moveq    r3, #1
c03252cc  000053e3   cmp      r3, #0
c03252d0  4600000a   beq      #0xc03253f0
c03252d4  083094e5   ldr      r3, [r4, #8]
c03252d8  010b53e3   cmp      r3, #0x400
c03252dc  0c309405   ldreq    r3, [r4, #0xc]
c03252e0  010b5303   cmpeq    r3, #0x400
c03252e4  2700001a   bne      #0xc0325388
c03252e8  183094e5   ldr      r3, [r4, #0x18]
c03252ec  040053e3   cmp      r3, #4
c03252f0  0a00001a   bne      #0xc0325320
c03252f4  0130a0e3   mov      r3, #1
c03252f8  04308ce5   str      r3, [ip, #4]
c03252fc  0030a0e3   mov      r3, #0
c0325300  14308ce5   str      r3, [ip, #0x14]
c0325304  0130a0e3   mov      r3, #1
c0325308  08308ce5   str      r3, [ip, #8]
c032530c  0130a0e3   mov      r3, #1
c0325310  18308ce5   str      r3, [ip, #0x18]
c0325314  0130a0e3   mov      r3, #1
c0325318  0130cce5   strb     r3, [ip, #1]
c032531c  090000ea   b        #0xc0325348
c0325320  0130a0e3   mov      r3, #1
c0325324  04308ce5   str      r3, [ip, #4]
c0325328  0030a0e3   mov      r3, #0
c032532c  14308ce5   str      r3, [ip, #0x14]
c0325330  0130a0e3   mov      r3, #1
c0325334  0030cce5   strb     r3, [ip]
c0325338  0130a0e3   mov      r3, #1
c032533c  08308ce5   str      r3, [ip, #8]
c0325340  0130a0e3   mov      r3, #1
c0325344  18308ce5   str      r3, [ip, #0x18]
c0325348  0030a0e3   mov      r3, #0
c032534c  2030cce5   strb     r3, [ip, #0x20]
c0325350  243094e5   ldr      r3, [r4, #0x24]
c0325354  286094e5   ldr      r6, [r4, #0x28]
c0325358  34308ce5   str      r3, [ip, #0x34]
c032535c  38608ce5   str      r6, [ip, #0x38]
c0325360  2c3094e5   ldr      r3, [r4, #0x2c]
c0325364  306094e5   ldr      r6, [r4, #0x30]
c0325368  24308ce5   str      r3, [ip, #0x24]
c032536c  28608ce5   str      r6, [ip, #0x28]
c0325370  0030a0e3   mov      r3, #0
c0325374  4430cce5   strb     r3, [ip, #0x44]
c0325378  0030a0e3   mov      r3, #0
c032537c  48308ce5   str      r3, [ip, #0x48]
c0325380  880000ea   b        #0xc03255a8
c0325384  00f020e3   nop      
c0325388  0130a0e3   mov      r3, #1
c032538c  04308ce5   str      r3, [ip, #4]
c0325390  0030a0e3   mov      r3, #0
c0325394  14308ce5   str      r3, [ip, #0x14]
c0325398  0430a0e3   mov      r3, #4
c032539c  08308ce5   str      r3, [ip, #8]
c03253a0  0130a0e3   mov      r3, #1
c03253a4  18308ce5   str      r3, [ip, #0x18]
c03253a8  0130a0e3   mov      r3, #1
c03253ac  0130cce5   strb     r3, [ip, #1]
c03253b0  0030a0e3   mov      r3, #0
c03253b4  2030cce5   strb     r3, [ip, #0x20]
c03253b8  083094e5   ldr      r3, [r4, #8]
c03253bc  0c6094e5   ldr      r6, [r4, #0xc]
c03253c0  34308ce5   str      r3, [ip, #0x34]
c03253c4  38608ce5   str      r6, [ip, #0x38]
c03253c8  103094e5   ldr      r3, [r4, #0x10]
c03253cc  146094e5   ldr      r6, [r4, #0x14]
c03253d0  24308ce5   str      r3, [ip, #0x24]
c03253d4  28608ce5   str      r6, [ip, #0x28]
c03253d8  0030a0e3   mov      r3, #0
c03253dc  4430cce5   strb     r3, [ip, #0x44]
c03253e0  0030a0e3   mov      r3, #0
c03253e4  48308ce5   str      r3, [ip, #0x48]
c03253e8  6e0000ea   b        #0xc03255a8
c03253ec  00f020e3   nop      
c03253f0  083094e5   ldr      r3, [r4, #8]
c03253f4  010b53e3   cmp      r3, #0x400
c03253f8  0c309405   ldreq    r3, [r4, #0xc]
c03253fc  010b5303   cmpeq    r3, #0x400
c0325400  2800001a   bne      #0xc03254a8
c0325404  183094e5   ldr      r3, [r4, #0x18]
c0325408  040053e3   cmp      r3, #4
c032540c  0b00001a   bne      #0xc0325440
c0325410  0130a0e3   mov      r3, #1
c0325414  04308ce5   str      r3, [ip, #4]
c0325418  0030a0e3   mov      r3, #0
c032541c  14308ce5   str      r3, [ip, #0x14]
c0325420  0130a0e3   mov      r3, #1
c0325424  08308ce5   str      r3, [ip, #8]
c0325428  0130a0e3   mov      r3, #1
c032542c  18308ce5   str      r3, [ip, #0x18]
c0325430  0130a0e3   mov      r3, #1
c0325434  0130cce5   strb     r3, [ip, #1]
c0325438  0a0000ea   b        #0xc0325468
c032543c  00f020e3   nop      
c0325440  0130a0e3   mov      r3, #1
c0325444  04308ce5   str      r3, [ip, #4]
c0325448  0030a0e3   mov      r3, #0
c032544c  14308ce5   str      r3, [ip, #0x14]
c0325450  0130a0e3   mov      r3, #1
c0325454  0030cce5   strb     r3, [ip]
c0325458  0130a0e3   mov      r3, #1
c032545c  08308ce5   str      r3, [ip, #8]
c0325460  0130a0e3   mov      r3, #1
c0325464  18308ce5   str      r3, [ip, #0x18]
c0325468  0030a0e3   mov      r3, #0
c032546c  2030cce5   strb     r3, [ip, #0x20]
c0325470  243094e5   ldr      r3, [r4, #0x24]
c0325474  286094e5   ldr      r6, [r4, #0x28]
c0325478  34308ce5   str      r3, [ip, #0x34]
c032547c  38608ce5   str      r6, [ip, #0x38]
c0325480  2c3094e5   ldr      r3, [r4, #0x2c]
c0325484  306094e5   ldr      r6, [r4, #0x30]
c0325488  24308ce5   str      r3, [ip, #0x24]
c032548c  28608ce5   str      r6, [ip, #0x28]
c0325490  0030a0e3   mov      r3, #0
c0325494  4430cce5   strb     r3, [ip, #0x44]
c0325498  0030a0e3   mov      r3, #0
c032549c  48308ce5   str      r3, [ip, #0x48]
c03254a0  400000ea   b        #0xc03255a8
c03254a4  00f020e3   nop      
c03254a8  243094e5   ldr      r3, [r4, #0x24]
c03254ac  010b53e3   cmp      r3, #0x400
c03254b0  28309405   ldreq    r3, [r4, #0x28]
c03254b4  010b5303   cmpeq    r3, #0x400
c03254b8  1800001a   bne      #0xc0325520
c03254bc  0130a0e3   mov      r3, #1
c03254c0  04308ce5   str      r3, [ip, #4]
c03254c4  0030a0e3   mov      r3, #0
c03254c8  14308ce5   str      r3, [ip, #0x14]
c03254cc  0330a0e3   mov      r3, #3
c03254d0  08308ce5   str      r3, [ip, #8]
c03254d4  0130a0e3   mov      r3, #1
c03254d8  18308ce5   str      r3, [ip, #0x18]
c03254dc  0130a0e3   mov      r3, #1
c03254e0  0230cce5   strb     r3, [ip, #2]
c03254e4  0130a0e3   mov      r3, #1
c03254e8  2030cce5   strb     r3, [ip, #0x20]
c03254ec  083094e5   ldr      r3, [r4, #8]
c03254f0  0c6094e5   ldr      r6, [r4, #0xc]
c03254f4  34308ce5   str      r3, [ip, #0x34]
c03254f8  38608ce5   str      r6, [ip, #0x38]
c03254fc  2c3094e5   ldr      r3, [r4, #0x2c]
c0325500  306094e5   ldr      r6, [r4, #0x30]
c0325504  24308ce5   str      r3, [ip, #0x24]
c0325508  28608ce5   str      r6, [ip, #0x28]
c032550c  0030a0e3   mov      r3, #0
c0325510  4430cce5   strb     r3, [ip, #0x44]
c0325514  0130a0e3   mov      r3, #1
c0325518  48308ce5   str      r3, [ip, #0x48]
c032551c  210000ea   b        #0xc03255a8
c0325520  0430a0e3   mov      r3, #4
c0325524  04308ce5   str      r3, [ip, #4]
c0325528  0030a0e3   mov      r3, #0
c032552c  14308ce5   str      r3, [ip, #0x14]
c0325530  0430a0e3   mov      r3, #4
c0325534  08308ce5   str      r3, [ip, #8]
c0325538  0130a0e3   mov      r3, #1
c032553c  18308ce5   str      r3, [ip, #0x18]
c0325540  0130a0e3   mov      r3, #1
c0325544  0130cce5   strb     r3, [ip, #1]
c0325548  0030a0e3   mov      r3, #0
c032554c  2030cce5   strb     r3, [ip, #0x20]
c0325550  0030a0e3   mov      r3, #0
c0325554  2130cce5   strb     r3, [ip, #0x21]
c0325558  083094e5   ldr      r3, [r4, #8]
c032555c  0c6094e5   ldr      r6, [r4, #0xc]
c0325560  34308ce5   str      r3, [ip, #0x34]
c0325564  38608ce5   str      r6, [ip, #0x38]
c0325568  103094e5   ldr      r3, [r4, #0x10]
c032556c  146094e5   ldr      r6, [r4, #0x14]
c0325570  24308ce5   str      r3, [ip, #0x24]
c0325574  28608ce5   str      r6, [ip, #0x28]
c0325578  243094e5   ldr      r3, [r4, #0x24]
c032557c  286094e5   ldr      r6, [r4, #0x28]
c0325580  3c308ce5   str      r3, [ip, #0x3c]
c0325584  40608ce5   str      r6, [ip, #0x40]
c0325588  2c3094e5   ldr      r3, [r4, #0x2c]
c032558c  306094e5   ldr      r6, [r4, #0x30]
c0325590  2c308ce5   str      r3, [ip, #0x2c]
c0325594  30608ce5   str      r6, [ip, #0x30]
c0325598  0130a0e3   mov      r3, #1
c032559c  4430cce5   strb     r3, [ip, #0x44]
c03255a0  0030a0e3   mov      r3, #0
c03255a4  48308ce5   str      r3, [ip, #0x48]
c03255a8  f000bde8   pop      {r4, r5, r6, r7}
c03255ac  1eff2fe1   bx       lr
