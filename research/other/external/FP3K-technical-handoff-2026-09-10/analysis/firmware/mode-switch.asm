c0321330  f0492de9   push     {r4, r5, r6, r7, r8, fp, lr}
c0321334  0070a0e1   mov      r7, r0
c0321338  0160a0e1   mov      r6, r1
c032133c  02b0a0e1   mov      fp, r2
c0321340  8c3209e3   movw     r3, #0x928c
c0321344  b5304ce3   movt     r3, #0xc0b5
c0321348  d040c3e1   ldrd     r4, r5, [r3]
c032134c  d03096e5   ldr      r3, [r6, #0xd0]
c0321350  683083e2   add      r3, r3, #0x68
c0321354  003093e5   ldr      r3, [r3]
c0321358  0600a0e1   mov      r0, r6
c032135c  0b10a0e1   mov      r1, fp
c0321360  33ff2fe1   blx      r3
c0321364  0030a0e1   mov      r3, r0
c0321368  0340a0e1   mov      r4, r3
c032136c  d03096e5   ldr      r3, [r6, #0xd0]
c0321370  6c3083e2   add      r3, r3, #0x6c
c0321374  003093e5   ldr      r3, [r3]
c0321378  0600a0e1   mov      r0, r6
c032137c  0410a0e1   mov      r1, r4
c0321380  33ff2fe1   blx      r3
c0321384  0030a0e1   mov      r3, r0
c0321388  0350a0e1   mov      r5, r3
c032138c  f040c7e1   strd     r4, r5, [r7]
c0321390  f089bde8   pop      {r4, r5, r6, r7, r8, fp, pc}
c0321394  00f020e3   nop      
c0321398  f00c2de9   push     {r4, r5, r6, r7, sl, fp}
c032139c  0070a0e1   mov      r7, r0
c03213a0  0140a0e1   mov      r4, r1
c03213a4  02c0a0e1   mov      ip, r2
c03213a8  0350a0e1   mov      r5, r3
c03213ac  18609de5   ldr      r6, [sp, #0x18]
c03213b0  00005ce3   cmp      ip, #0
c03213b4  0000001a   bne      #0xc03213bc
c03213b8  01c0a0e3   mov      ip, #1
c03213bc  00a094e5   ldr      sl, [r4]
c03213c0  0c005ae1   cmp      sl, ip
c03213c4  0500009a   bls      #0xc03213e0
c03213c8  00b094e5   ldr      fp, [r4]
c03213cc  1bfc3ae7   udiv     sl, fp, ip
c03213d0  9cba6ae0   mls      sl, ip, sl, fp
c03213d4  00a085e5   str      sl, [r5]
c03213d8  020000ea   b        #0xc03213e8
c03213dc  00f020e3   nop      
c03213e0  00a094e5   ldr      sl, [r4]
c03213e4  00a085e5   str      sl, [r5]
c03213e8  00a094e5   ldr      sl, [r4]
c03213ec  0c005ae1   cmp      sl, ip
c03213f0  0c00009a   bls      #0xc0321428
c03213f4  00a094e5   ldr      sl, [r4]
c03213f8  1afc3ae7   udiv     sl, sl, ip
c03213fc  00a086e5   str      sl, [r6]
c0321400  00b094e5   ldr      fp, [r4]
c0321404  1bfc3ae7   udiv     sl, fp, ip
c0321408  9cba6ae0   mls      sl, ip, sl, fp
c032140c  00005ae3   cmp      sl, #0
c0321410  0600001a   bne      #0xc0321430
c0321414  00a096e5   ldr      sl, [r6]
c0321418  01a04ae2   sub      sl, sl, #1
c032141c  00a086e5   str      sl, [r6]
c0321420  00c085e5   str      ip, [r5]
c0321424  010000ea   b        #0xc0321430
c0321428  00a0a0e3   mov      sl, #0
c032142c  00a086e5   str      sl, [r6]
c0321430  f00cbde8   pop      {r4, r5, r6, r7, sl, fp}
c0321434  1eff2fe1   bx       lr
c0321438  30402de9   push     {r4, r5, lr}
c032143c  6cd04de2   sub      sp, sp, #0x6c
c0321440  0050a0e1   mov      r5, r0
c0321444  0140a0e1   mov      r4, r1
c0321448  0d00a0e1   mov      r0, sp
c032144c  6c20a0e3   mov      r2, #0x6c
c0321450  0010a0e3   mov      r1, #0
c0321454  ffcef3eb   bl       #0xc0015058
c0321458  0020d4e5   ldrb     r2, [r4]
c032145c  00208de5   str      r2, [sp]
c0321460  042094e5   ldr      r2, [r4, #4]
c0321464  10208de5   str      r2, [sp, #0x10]
c0321468  082094e5   ldr      r2, [r4, #8]
c032146c  04208de5   str      r2, [sp, #4]
c0321470  0c2094e5   ldr      r2, [r4, #0xc]
c0321474  08208de5   str      r2, [sp, #8]
c0321478  102094e5   ldr      r2, [r4, #0x10]
c032147c  0c208de5   str      r2, [sp, #0xc]
c0321480  142094e5   ldr      r2, [r4, #0x14]
c0321484  40208de5   str      r2, [sp, #0x40]
c0321488  0d00a0e1   mov      r0, sp
c032148c  3313f8fa   blx      #0xc0126160
c0321490  6cd08de2   add      sp, sp, #0x6c
c0321494  3080bde8   pop      {r4, r5, pc}
c0321498  30402de9   push     {r4, r5, lr}
c032149c  405601e3   movw     r5, #0x1640
c03214a0  0040a0e1   mov      r4, r0
c03214a4  32504ce3   movt     r5, #0xc032
c03214a8  0400a0e1   mov      r0, r4
c03214ac  2820a0e3   mov      r2, #0x28
c03214b0  0010a0e3   mov      r1, #0
c03214b4  e7cef3eb   bl       #0xc0015058
c03214b8  0500a0e1   mov      r0, r5
c03214bc  4d15f8fa   blx      #0xc01269f8
c03214c0  0410a0e1   mov      r1, r4
c03214c4  0100a0e1   mov      r0, r1
c03214c8  3080bde8   pop      {r4, r5, pc}
c03214cc  00f020e3   nop      
c03214d0  10402de9   push     {r4, lr}
c03214d4  74440be3   movw     r4, #0xb474
c03214d8  43434ce3   movt     r4, #0xc343
c03214dc  280084e2   add      r0, r4, #0x28
c03214e0  eac6f3eb   bl       #0xc0013090
c03214e4  000050e3   cmp      r0, #0
c03214e8  0400000a   beq      #0xc0321500
c03214ec  0400a0e1   mov      r0, r4
c03214f0  e8ffffeb   bl       #0xc0321498
c03214f4  280084e2   add      r0, r4, #0x28
c03214f8  39c7f3eb   bl       #0xc00131e4
c03214fc  00f020e3   nop      
c0321500  0400a0e1   mov      r0, r4
c0321504  1080bde8   pop      {r4, pc}
c0321508  f0402de9   push     {r4, r5, r6, r7, lr}
c032150c  08d04de2   sub      sp, sp, #8
c0321510  0050a0e1   mov      r5, r0
c0321514  0160a0e1   mov      r6, r1
c0321518  0d00a0e1   mov      r0, sp
c032151c  efedf3eb   bl       #0xc001cce0
c0321520  0520a0e1   mov      r2, r5
c0321524  283082e2   add      r3, r2, #0x28
c0321528  0b0000ea   b        #0xc032155c
c032152c  00f020e3   nop      
c0321530  0270a0e1   mov      r7, r2
c0321534  00c097e5   ldr      ip, [r7]
c0321538  06005ce1   cmp      ip, r6
c032153c  0500001a   bne      #0xc0321558
c0321540  0d00a0e1   mov      r0, sp
c0321544  0210a0e3   mov      r1, #2
c0321548  f2edf3eb   bl       #0xc001cd18
c032154c  0020a0e3   mov      r2, #0
c0321550  170000ea   b        #0xc03215b4
c0321554  00f020e3   nop      
c0321558  042082e2   add      r2, r2, #4
c032155c  030052e1   cmp      r2, r3
c0321560  f2ffff1a   bne      #0xc0321530
c0321564  0520a0e1   mov      r2, r5
c0321568  283082e2   add      r3, r2, #0x28
c032156c  0a0000ea   b        #0xc032159c
c0321570  0240a0e1   mov      r4, r2
c0321574  00c094e5   ldr      ip, [r4]
c0321578  00005ce3   cmp      ip, #0
c032157c  0500001a   bne      #0xc0321598
c0321580  006084e5   str      r6, [r4]
c0321584  0d00a0e1   mov      r0, sp
c0321588  0210a0e3   mov      r1, #2
c032158c  e1edf3eb   bl       #0xc001cd18
c0321590  0120a0e3   mov      r2, #1
c0321594  060000ea   b        #0xc03215b4
c0321598  042082e2   add      r2, r2, #4
c032159c  030052e1   cmp      r2, r3
c03215a0  f2ffff1a   bne      #0xc0321570
c03215a4  0d00a0e1   mov      r0, sp
c03215a8  0210a0e3   mov      r1, #2
c03215ac  d9edf3eb   bl       #0xc001cd18
c03215b0  0020a0e3   mov      r2, #0
c03215b4  0200a0e1   mov      r0, r2
c03215b8  08d08de2   add      sp, sp, #8
c03215bc  f080bde8   pop      {r4, r5, r6, r7, pc}
c03215c0  70402de9   push     {r4, r5, r6, lr}
c03215c4  08d04de2   sub      sp, sp, #8
c03215c8  0050a0e1   mov      r5, r0
c03215cc  0160a0e1   mov      r6, r1
c03215d0  0d00a0e1   mov      r0, sp
c03215d4  c1edf3eb   bl       #0xc001cce0
c03215d8  0520a0e1   mov      r2, r5
c03215dc  283082e2   add      r3, r2, #0x28
c03215e0  0d0000ea   b        #0xc032161c
c03215e4  00f020e3   nop      
c03215e8  0240a0e1   mov      r4, r2
c03215ec  00c094e5   ldr      ip, [r4]
c03215f0  06005ce1   cmp      ip, r6
c03215f4  0700001a   bne      #0xc0321618
c03215f8  0020a0e3   mov      r2, #0
c03215fc  002084e5   str      r2, [r4]
c0321600  0d00a0e1   mov      r0, sp
c0321604  0210a0e3   mov      r1, #2
c0321608  c2edf3eb   bl       #0xc001cd18
c032160c  0120a0e3   mov      r2, #1
c0321610  070000ea   b        #0xc0321634
c0321614  00f020e3   nop      
c0321618  042082e2   add      r2, r2, #4
c032161c  030052e1   cmp      r2, r3
c0321620  f0ffff1a   bne      #0xc03215e8
c0321624  0d00a0e1   mov      r0, sp
c0321628  0210a0e3   mov      r1, #2
c032162c  b9edf3eb   bl       #0xc001cd18
c0321630  0020a0e3   mov      r2, #0
c0321634  0200a0e1   mov      r0, r2
c0321638  08d08de2   add      sp, sp, #8
c032163c  7080bde8   pop      {r4, r5, r6, pc}
c0321640  70402de9   push     {r4, r5, r6, lr}
c0321644  a1ffffeb   bl       #0xc03214d0
c0321648  0050a0e1   mov      r5, r0
c032164c  286080e2   add      r6, r0, #0x28
c0321650  070000ea   b        #0xc0321674
c0321654  00f020e3   nop      
c0321658  0540a0e1   mov      r4, r5
c032165c  000094e5   ldr      r0, [r4]
c0321660  000050e3   cmp      r0, #0
c0321664  0100000a   beq      #0xc0321670
c0321668  000094e5   ldr      r0, [r4]
c032166c  30ff2fe1   blx      r0
c0321670  045085e2   add      r5, r5, #4
c0321674  060055e1   cmp      r5, r6
c0321678  f6ffff1a   bne      #0xc0321658
c032167c  7080bde8   pop      {r4, r5, r6, pc}
c0321680  30402de9   push     {r4, r5, lr}
c0321684  285801e3   movw     r5, #0x1828
c0321688  0040a0e1   mov      r4, r0
c032168c  32504ce3   movt     r5, #0xc032
c0321690  0400a0e1   mov      r0, r4
c0321694  2820a0e3   mov      r2, #0x28
c0321698  0010a0e3   mov      r1, #0
c032169c  6dcef3eb   bl       #0xc0015058
c03216a0  0500a0e1   mov      r0, r5
c03216a4  e714f8fa   blx      #0xc0126a48
c03216a8  0410a0e1   mov      r1, r4
c03216ac  0100a0e1   mov      r0, r1
c03216b0  3080bde8   pop      {r4, r5, pc}
c03216b4  00f020e3   nop      
c03216b8  10402de9   push     {r4, lr}
c03216bc  a4440be3   movw     r4, #0xb4a4
c03216c0  43434ce3   movt     r4, #0xc343
c03216c4  280084e2   add      r0, r4, #0x28
c03216c8  70c6f3eb   bl       #0xc0013090
c03216cc  000050e3   cmp      r0, #0
c03216d0  0400000a   beq      #0xc03216e8
c03216d4  0400a0e1   mov      r0, r4
c03216d8  e8ffffeb   bl       #0xc0321680
c03216dc  280084e2   add      r0, r4, #0x28
c03216e0  bfc6f3eb   bl       #0xc00131e4
c03216e4  00f020e3   nop      
c03216e8  0400a0e1   mov      r0, r4
c03216ec  1080bde8   pop      {r4, pc}
c03216f0  f0402de9   push     {r4, r5, r6, r7, lr}
c03216f4  08d04de2   sub      sp, sp, #8
c03216f8  0050a0e1   mov      r5, r0
c03216fc  0160a0e1   mov      r6, r1
c0321700  0d00a0e1   mov      r0, sp
c0321704  75edf3eb   bl       #0xc001cce0
c0321708  0520a0e1   mov      r2, r5
c032170c  283082e2   add      r3, r2, #0x28
c0321710  0b0000ea   b        #0xc0321744
c0321714  00f020e3   nop      
c0321718  0270a0e1   mov      r7, r2
c032171c  00c097e5   ldr      ip, [r7]
c0321720  06005ce1   cmp      ip, r6
c0321724  0500001a   bne      #0xc0321740
c0321728  0d00a0e1   mov      r0, sp
c032172c  0210a0e3   mov      r1, #2
c0321730  78edf3eb   bl       #0xc001cd18
c0321734  0020a0e3   mov      r2, #0
c0321738  170000ea   b        #0xc032179c
c032173c  00f020e3   nop      
c0321740  042082e2   add      r2, r2, #4
c0321744  030052e1   cmp      r2, r3
c0321748  f2ffff1a   bne      #0xc0321718
c032174c  0520a0e1   mov      r2, r5
c0321750  283082e2   add      r3, r2, #0x28
c0321754  0a0000ea   b        #0xc0321784
c0321758  0240a0e1   mov      r4, r2
c032175c  00c094e5   ldr      ip, [r4]
c0321760  00005ce3   cmp      ip, #0
c0321764  0500001a   bne      #0xc0321780
c0321768  006084e5   str      r6, [r4]
c032176c  0d00a0e1   mov      r0, sp
c0321770  0210a0e3   mov      r1, #2
c0321774  67edf3eb   bl       #0xc001cd18
c0321778  0120a0e3   mov      r2, #1
c032177c  060000ea   b        #0xc032179c
c0321780  042082e2   add      r2, r2, #4
c0321784  030052e1   cmp      r2, r3
c0321788  f2ffff1a   bne      #0xc0321758
c032178c  0d00a0e1   mov      r0, sp
c0321790  0210a0e3   mov      r1, #2
c0321794  5fedf3eb   bl       #0xc001cd18
c0321798  0020a0e3   mov      r2, #0
c032179c  0200a0e1   mov      r0, r2
c03217a0  08d08de2   add      sp, sp, #8
c03217a4  f080bde8   pop      {r4, r5, r6, r7, pc}
c03217a8  70402de9   push     {r4, r5, r6, lr}
c03217ac  08d04de2   sub      sp, sp, #8
c03217b0  0050a0e1   mov      r5, r0
c03217b4  0160a0e1   mov      r6, r1
c03217b8  0d00a0e1   mov      r0, sp
c03217bc  47edf3eb   bl       #0xc001cce0
c03217c0  0520a0e1   mov      r2, r5
c03217c4  283082e2   add      r3, r2, #0x28
c03217c8  0d0000ea   b        #0xc0321804
c03217cc  00f020e3   nop      
c03217d0  0240a0e1   mov      r4, r2
c03217d4  00c094e5   ldr      ip, [r4]
c03217d8  06005ce1   cmp      ip, r6
c03217dc  0700001a   bne      #0xc0321800
c03217e0  0020a0e3   mov      r2, #0
c03217e4  002084e5   str      r2, [r4]
c03217e8  0d00a0e1   mov      r0, sp
c03217ec  0210a0e3   mov      r1, #2
c03217f0  48edf3eb   bl       #0xc001cd18
c03217f4  0120a0e3   mov      r2, #1
c03217f8  070000ea   b        #0xc032181c
c03217fc  00f020e3   nop      
c0321800  042082e2   add      r2, r2, #4
c0321804  030052e1   cmp      r2, r3
c0321808  f0ffff1a   bne      #0xc03217d0
c032180c  0d00a0e1   mov      r0, sp
c0321810  0210a0e3   mov      r1, #2
c0321814  3fedf3eb   bl       #0xc001cd18
c0321818  0020a0e3   mov      r2, #0
c032181c  0200a0e1   mov      r0, r2
c0321820  08d08de2   add      sp, sp, #8
c0321824  7080bde8   pop      {r4, r5, r6, pc}
c0321828  70402de9   push     {r4, r5, r6, lr}
c032182c  a1ffffeb   bl       #0xc03216b8
c0321830  0050a0e1   mov      r5, r0
c0321834  286080e2   add      r6, r0, #0x28
c0321838  070000ea   b        #0xc032185c
c032183c  00f020e3   nop      
c0321840  0540a0e1   mov      r4, r5
c0321844  000094e5   ldr      r0, [r4]
c0321848  000050e3   cmp      r0, #0
c032184c  0100000a   beq      #0xc0321858
c0321850  000094e5   ldr      r0, [r4]
c0321854  30ff2fe1   blx      r0
c0321858  045085e2   add      r5, r5, #4
c032185c  060055e1   cmp      r5, r6
c0321860  f6ffff1a   bne      #0xc0321840
c0321864  7080bde8   pop      {r4, r5, r6, pc}
c0321868  30402de9   push     {r4, r5, lr}
c032186c  105a01e3   movw     r5, #0x1a10
c0321870  0040a0e1   mov      r4, r0
c0321874  32504ce3   movt     r5, #0xc032
c0321878  0400a0e1   mov      r0, r4
c032187c  2820a0e3   mov      r2, #0x28
c0321880  0010a0e3   mov      r1, #0
c0321884  f3cdf3eb   bl       #0xc0015058
c0321888  0500a0e1   mov      r0, r5
c032188c  6914f8fa   blx      #0xc0126a38
c0321890  0410a0e1   mov      r1, r4
c0321894  0100a0e1   mov      r0, r1
c0321898  3080bde8   pop      {r4, r5, pc}
c032189c  00f020e3   nop      
c03218a0  10402de9   push     {r4, lr}
c03218a4  d4440be3   movw     r4, #0xb4d4
c03218a8  43434ce3   movt     r4, #0xc343
c03218ac  280084e2   add      r0, r4, #0x28
c03218b0  f6c5f3eb   bl       #0xc0013090
c03218b4  000050e3   cmp      r0, #0
c03218b8  0400000a   beq      #0xc03218d0
c03218bc  0400a0e1   mov      r0, r4
c03218c0  e8ffffeb   bl       #0xc0321868
c03218c4  280084e2   add      r0, r4, #0x28
c03218c8  45c6f3eb   bl       #0xc00131e4
c03218cc  00f020e3   nop      
c03218d0  0400a0e1   mov      r0, r4
c03218d4  1080bde8   pop      {r4, pc}
c03218d8  f0402de9   push     {r4, r5, r6, r7, lr}
c03218dc  08d04de2   sub      sp, sp, #8
c03218e0  0050a0e1   mov      r5, r0
c03218e4  0160a0e1   mov      r6, r1
c03218e8  0d00a0e1   mov      r0, sp
c03218ec  fbecf3eb   bl       #0xc001cce0
c03218f0  0520a0e1   mov      r2, r5
c03218f4  283082e2   add      r3, r2, #0x28
c03218f8  0b0000ea   b        #0xc032192c
c03218fc  00f020e3   nop      
c0321900  0270a0e1   mov      r7, r2
c0321904  00c097e5   ldr      ip, [r7]
c0321908  06005ce1   cmp      ip, r6
c032190c  0500001a   bne      #0xc0321928
c0321910  0d00a0e1   mov      r0, sp
c0321914  0210a0e3   mov      r1, #2
c0321918  feecf3eb   bl       #0xc001cd18
c032191c  0020a0e3   mov      r2, #0
c0321920  170000ea   b        #0xc0321984
c0321924  00f020e3   nop      
c0321928  042082e2   add      r2, r2, #4
c032192c  030052e1   cmp      r2, r3
