c0436500  0140a0e1   mov      r4, r1
c0436504  04409de4   pop      {r4}
c0436508  1eff2fe1   bx       lr
c043650c  00f020e3   nop      
c0436510  30402de9   push     {r4, r5, lr}
c0436514  0040a0e1   mov      r4, r0
c0436518  0150a0e1   mov      r5, r1
c043651c  010015e3   tst      r5, #1
c0436520  0200000a   beq      #0xc0436530
c0436524  0400a0e1   mov      r0, r4
c0436528  1410a0e3   mov      r1, #0x14
c043652c  da73efeb   bl       #0xc001349c
c0436530  3080bde8   pop      {r4, r5, pc}
c0436534  00f020e3   nop      
c0436538  f0042de9   push     {r4, r5, r6, r7, sl}
c043653c  0050a0e1   mov      r5, r0
c0436540  0160a0e1   mov      r6, r1
c0436544  0270a0e1   mov      r7, r2
c0436548  03a0a0e1   mov      sl, r3
c043654c  000056e3   cmp      r6, #0
c0436550  0b00000a   beq      #0xc0436584
c0436554  007085e5   str      r7, [r5]
c0436558  0640a0e1   mov      r4, r6
c043655c  04c085e2   add      ip, r5, #4
c0436560  0b00b4e8   ldm      r4!, {r0, r1, r3}
c0436564  0b00ace8   stm      ip!, {r0, r1, r3}
c0436568  0b00b4e8   ldm      r4!, {r0, r1, r3}
c043656c  0b00ace8   stm      ip!, {r0, r1, r3}
c0436570  0b00b4e8   ldm      r4!, {r0, r1, r3}
c0436574  0b00ace8   stm      ip!, {r0, r1, r3}
c0436578  030094e8   ldm      r4, {r0, r1}
c043657c  03008ce8   stm      ip, {r0, r1}
c0436580  30a085e5   str      sl, [r5, #0x30]
c0436584  f004bde8   pop      {r4, r5, r6, r7, sl}
c0436588  1eff2fe1   bx       lr
c043658c  00f020e3   nop      
c0436590  30402de9   push     {r4, r5, lr}
c0436594  40480de3   movw     r4, #0xd840
c0436598  75434ce3   movt     r4, #0xc375
c043659c  425f84e2   add      r5, r4, #0x108
c04365a0  470f84e2   add      r0, r4, #0x11c
c04365a4  b972efeb   bl       #0xc0013090
c04365a8  000050e3   cmp      r0, #0
c04365ac  0700000a   beq      #0xc04365d0
c04365b0  0500a0e1   mov      r0, r5
c04365b4  0bd6efeb   bl       #0xc002bde8
c04365b8  440100e3   movw     r0, #0x144
c04365bc  bd004ce3   movt     r0, #0xc0bd
c04365c0  180184e5   str      r0, [r4, #0x118]
c04365c4  470f84e2   add      r0, r4, #0x11c
c04365c8  0573efeb   bl       #0xc00131e4
c04365cc  00f020e3   nop      
c04365d0  490f84e2   add      r0, r4, #0x124
c04365d4  ad72efeb   bl       #0xc0013090
c04365d8  000050e3   cmp      r0, #0
c04365dc  0700000a   beq      #0xc0436600
c04365e0  0510a0e1   mov      r1, r5
c04365e4  0400a0e1   mov      r0, r4
c04365e8  060000eb   bl       #0xc0436608
c04365ec  280301e3   movw     r0, #0x1328
c04365f0  f2024ce3   movt     r0, #0xc2f2
c04365f4  3e73efeb   bl       #0xc00132f4
c04365f8  490f84e2   add      r0, r4, #0x124
c04365fc  f872efeb   bl       #0xc00131e4
c0436600  0400a0e1   mov      r0, r4
c0436604  3080bde8   pop      {r4, r5, pc}
c0436608  70412de9   push     {r4, r5, r6, r8, lr}
c043660c  0040a0e1   mov      r4, r0
c0436610  d06309e3   movw     r6, #0x93d0
c0436614  0150a0e1   mov      r5, r1
c0436618  43604ce3   movt     r6, #0xc043
c043661c  0300a0e3   mov      r0, #3
c0436620  220c00eb   bl       #0xc04396b0
c0436624  0020a0e1   mov      r2, r0
c0436628  002084e5   str      r2, [r4]
c043662c  9bffffeb   bl       #0xc04364a0
c0436630  0020a0e1   mov      r2, r0
c0436634  042084e5   str      r2, [r4, #4]
c0436638  080084e2   add      r0, r4, #8
c043663c  0320a0e3   mov      r2, #3
c0436640  0110a0e3   mov      r1, #1
c0436644  1bffffeb   bl       #0xc04362b8
c0436648  203b0fe3   movw     r3, #0xfb20
c043664c  bc304ce3   movt     r3, #0xc0bc
c0436650  002093e5   ldr      r2, [r3]
c0436654  0c2084e5   str      r2, [r4, #0xc]
c0436658  0020a0e3   mov      r2, #0
c043665c  102084e5   str      r2, [r4, #0x10]
c0436660  0020a0e3   mov      r2, #0
c0436664  142084e5   str      r2, [r4, #0x14]
c0436668  0630a0e1   mov      r3, r6
c043666c  180084e2   add      r0, r4, #0x18
c0436670  3420a0e3   mov      r2, #0x34
c0436674  0410a0e3   mov      r1, #4
c0436678  8bfbf6eb   bl       #0xc01f54ac
c043667c  10cb0fe3   movw     ip, #0xfb10
c0436680  bcc04ce3   movt     ip, #0xc0bc
c0436684  0c009ce8   ldm      ip, {r2, r3}
c0436688  e82084e5   str      r2, [r4, #0xe8]
c043668c  ec3084e5   str      r3, [r4, #0xec]
c0436690  18cb0fe3   movw     ip, #0xfb18
c0436694  bcc04ce3   movt     ip, #0xc0bc
c0436698  0c009ce8   ldm      ip, {r2, r3}
c043669c  f02084e5   str      r2, [r4, #0xf0]
c04366a0  f43084e5   str      r3, [r4, #0xf4]
c04366a4  0020a0e3   mov      r2, #0
c04366a8  f82084e5   str      r2, [r4, #0xf8]
c04366ac  0020a0e3   mov      r2, #0
c04366b0  fc2084e5   str      r2, [r4, #0xfc]
c04366b4  243b0fe3   movw     r3, #0xfb24
c04366b8  bc304ce3   movt     r3, #0xc0bc
c04366bc  002093e5   ldr      r2, [r3]
c04366c0  002184e5   str      r2, [r4, #0x100]
c04366c4  045184e5   str      r5, [r4, #0x104]
c04366c8  000094e5   ldr      r0, [r4]
c04366cc  082090e5   ldr      r2, [r0, #8]
c04366d0  041094e5   ldr      r1, [r4, #4]
c04366d4  142082e2   add      r2, r2, #0x14
c04366d8  002092e5   ldr      r2, [r2]
c04366dc  32ff2fe1   blx      r2
c04366e0  0020a0e1   mov      r2, r0
c04366e4  102084e5   str      r2, [r4, #0x10]
c04366e8  0400a0e1   mov      r0, r4
c04366ec  610300eb   bl       #0xc0437478
c04366f0  0420a0e1   mov      r2, r4
c04366f4  0200a0e1   mov      r0, r2
c04366f8  7081bde8   pop      {r4, r5, r6, r8, pc}
c04366fc  00f020e3   nop      
c0436700  30402de9   push     {r4, r5, lr}
c0436704  0040a0e1   mov      r4, r0
c0436708  0150a0e1   mov      r5, r1
c043670c  000054e3   cmp      r4, #0
c0436710  0e00000a   beq      #0xc0436750
c0436714  010c84e2   add      r0, r4, #0x100
c0436718  0210a0e3   mov      r1, #2
c043671c  290800eb   bl       #0xc04387c8
c0436720  0c0084e2   add      r0, r4, #0xc
c0436724  0210a0e3   mov      r1, #2
c0436728  88e1f7eb   bl       #0xc022ed50
c043672c  080084e2   add      r0, r4, #8
c0436730  0210a0e3   mov      r1, #2
c0436734  85e1f7eb   bl       #0xc022ed50
c0436738  010015e3   tst      r5, #1
c043673c  0300000a   beq      #0xc0436750
c0436740  0400a0e1   mov      r0, r4
c0436744  421fa0e3   mov      r1, #0x108
c0436748  5373efeb   bl       #0xc001349c
c043674c  00f020e3   nop      
c0436750  3080bde8   pop      {r4, r5, pc}
c0436754  00f020e3   nop      
c0436758  30402de9   push     {r4, r5, lr}
c043675c  0040a0e1   mov      r4, r0
c0436760  0150a0e1   mov      r5, r1
c0436764  040194e5   ldr      r0, [r4, #0x104]
c0436768  0510a0e1   mov      r1, r5
c043676c  b797faeb   bl       #0xc02dc650
c0436770  3080bde8   pop      {r4, r5, pc}
c0436774  00f020e3   nop      
c0436778  30402de9   push     {r4, r5, lr}
c043677c  0040a0e1   mov      r4, r0
c0436780  0150a0e1   mov      r5, r1
c0436784  040194e5   ldr      r0, [r4, #0x104]
c0436788  0510a0e1   mov      r1, r5
c043678c  6b4afbeb   bl       #0xc0309140
c0436790  3080bde8   pop      {r4, r5, pc}
c0436794  00f020e3   nop      
c0436798  30402de9   push     {r4, r5, lr}
c043679c  0040a0e1   mov      r4, r0
c04367a0  0150a0e1   mov      r5, r1
c04367a4  040194e5   ldr      r0, [r4, #0x104]
c04367a8  0510a0e1   mov      r1, r5
c04367ac  f30a00eb   bl       #0xc0439380
c04367b0  0020a0e1   mov      r2, r0
c04367b4  0200a0e1   mov      r0, r2
c04367b8  3080bde8   pop      {r4, r5, pc}
c04367bc  00f020e3   nop      
c04367c0  f04c2de9   push     {r4, r5, r6, r7, sl, fp, lr}
c04367c4  9cd04de2   sub      sp, sp, #0x9c
c04367c8  00a0a0e1   mov      sl, r0
c04367cc  0170a0e1   mov      r7, r1
c04367d0  02b0a0e1   mov      fp, r2
c04367d4  0360a0e1   mov      r6, r3
c04367d8  68008de2   add      r0, sp, #0x68
c04367dc  3420a0e3   mov      r2, #0x34
c04367e0  0010a0e3   mov      r1, #0
c04367e4  1b7aefeb   bl       #0xc0015058
c04367e8  0600a0e1   mov      r0, r6
c04367ec  950700eb   bl       #0xc0438648
c04367f0  000050e3   cmp      r0, #0
c04367f4  0300001a   bne      #0xc0436808
c04367f8  280b0fe3   movw     r0, #0xfb28
c04367fc  bc004ce3   movt     r0, #0xc0bc
c0436800  b010a0e3   mov      r1, #0xb0
c0436804  3d6aefeb   bl       #0xc0011100
c0436808  00f020e3   nop      
c043680c  0b20a0e1   mov      r2, fp
c0436810  0710a0e1   mov      r1, r7
c0436814  04008de2   add      r0, sp, #4
c0436818  160b00eb   bl       #0xc0439478
c043681c  f7acefeb   bl       #0xc0021c00
c0436820  06adefeb   bl       #0xc0021c40
c0436824  0c108de2   add      r1, sp, #0xc
c0436828  0020a0e1   mov      r2, r0
c043682c  0700a0e1   mov      r0, r7
c0436830  0030a0e3   mov      r3, #0
c0436834  d10000eb   bl       #0xc0436b80
c0436838  0300a0e3   mov      r0, #3
c043683c  9b0b00eb   bl       #0xc04396b0
c0436840  084090e5   ldr      r4, [r0, #8]
c0436844  1c4084e2   add      r4, r4, #0x1c
c0436848  004094e5   ldr      r4, [r4]
c043684c  04108de2   add      r1, sp, #4
c0436850  34ff2fe1   blx      r4
c0436854  00c0a0e1   mov      ip, r0
c0436858  0c50a0e1   mov      r5, ip
c043685c  20c095e5   ldr      ip, [r5, #0x20]
c0436860  10408ce2   add      r4, ip, #0x10
c0436864  18c08ce2   add      ip, ip, #0x18
c0436868  00c09ce5   ldr      ip, [ip]
c043686c  0500a0e1   mov      r0, r5
c0436870  0610a0e1   mov      r1, r6
c0436874  3cff2fe1   blx      ip
c0436878  00c094e5   ldr      ip, [r4]
c043687c  00008de5   str      r0, [sp]
c0436880  0500a0e1   mov      r0, r5
c0436884  0610a0e1   mov      r1, r6
c0436888  3cff2fe1   blx      ip
c043688c  00309de5   ldr      r3, [sp]
c0436890  0010a0e1   mov      r1, r0
c0436894  68008de2   add      r0, sp, #0x68
c0436898  0020a0e3   mov      r2, #0
c043689c  25ffffeb   bl       #0xc0436538
c04368a0  68408de2   add      r4, sp, #0x68
c04368a4  0ac0a0e1   mov      ip, sl
c04368a8  0b00b4e8   ldm      r4!, {r0, r1, r3}
c04368ac  0b00ace8   stm      ip!, {r0, r1, r3}
c04368b0  0b00b4e8   ldm      r4!, {r0, r1, r3}
c04368b4  0b00ace8   stm      ip!, {r0, r1, r3}
c04368b8  0b00b4e8   ldm      r4!, {r0, r1, r3}
c04368bc  0b00ace8   stm      ip!, {r0, r1, r3}
c04368c0  0b00b4e8   ldm      r4!, {r0, r1, r3}
c04368c4  0b00ace8   stm      ip!, {r0, r1, r3}
c04368c8  004094e5   ldr      r4, [r4]
c04368cc  00408ce5   str      r4, [ip]
c04368d0  9cd08de2   add      sp, sp, #0x9c
c04368d4  f08cbde8   pop      {r4, r5, r6, r7, sl, fp, pc}
c04368d8  10402de9   push     {r4, lr}
c04368dc  0040a0e1   mov      r4, r0
c04368e0  0400a0e1   mov      r0, r4
c04368e4  1030a0e3   mov      r3, #0x10
c04368e8  0020a0e3   mov      r2, #0
c04368ec  0210a0e3   mov      r1, #2
c04368f0  b2ffffeb   bl       #0xc04367c0
c04368f4  1080bde8   pop      {r4, pc}
c04368f8  f0442de9   push     {r4, r5, r6, r7, sl, lr}
c04368fc  04d04de2   sub      sp, sp, #4
c0436900  0040a0e1   mov      r4, r0
c0436904  0150a0e1   mov      r5, r1
c0436908  0260a0e1   mov      r6, r2
c043690c  0370a0e1   mov      r7, r3
c0436910  1ca09de5   ldr      sl, [sp, #0x1c]
c0436914  04c094e5   ldr      ip, [r4, #4]
c0436918  00508ce5   str      r5, [ip]
c043691c  04c094e5   ldr      ip, [r4, #4]
c0436920  04708ce5   str      r7, [ip, #4]
c0436924  04c094e5   ldr      ip, [r4, #4]
c0436928  60a08ce5   str      sl, [ip, #0x60]
c043692c  0400a0e1   mov      r0, r4
c0436930  280000eb   bl       #0xc04369d8
c0436934  0610a0e1   mov      r1, r6
c0436938  0400a0e1   mov      r0, r4
c043693c  150100eb   bl       #0xc0436d98
c0436940  0d10a0e1   mov      r1, sp
c0436944  0400a0e1   mov      r0, r4
c0436948  380300eb   bl       #0xc0437630
c043694c  0d10a0e1   mov      r1, sp
c0436950  080084e2   add      r0, r4, #8
c0436954  630700eb   bl       #0xc04386e8
c0436958  0d00a0e1   mov      r0, sp
c043695c  0210a0e3   mov      r1, #2
c0436960  fae0f7eb   bl       #0xc022ed50
c0436964  0400a0e1   mov      r0, r4
c0436968  340000eb   bl       #0xc0436a40
c043696c  04d08de2   add      sp, sp, #4
c0436970  f084bde8   pop      {r4, r5, r6, r7, sl, pc}
c0436974  00f020e3   nop      
c0436978  30402de9   push     {r4, r5, lr}
c043697c  04d04de2   sub      sp, sp, #4
c0436980  0040a0e1   mov      r4, r0
c0436984  0150a0e1   mov      r5, r1
c0436988  042094e5   ldr      r2, [r4, #4]
c043698c  045082e5   str      r5, [r2, #4]
c0436990  0400a0e1   mov      r0, r4
c0436994  0f0000eb   bl       #0xc04369d8
c0436998  0400a0e1   mov      r0, r4
c043699c  0010a0e3   mov      r1, #0
c04369a0  fc0000eb   bl       #0xc0436d98
c04369a4  0d10a0e1   mov      r1, sp
c04369a8  0400a0e1   mov      r0, r4
c04369ac  1f0300eb   bl       #0xc0437630
c04369b0  0d10a0e1   mov      r1, sp
c04369b4  080084e2   add      r0, r4, #8
c04369b8  4a0700eb   bl       #0xc04386e8
c04369bc  0d00a0e1   mov      r0, sp
c04369c0  0210a0e3   mov      r1, #2
c04369c4  e1e0f7eb   bl       #0xc022ed50
c04369c8  0400a0e1   mov      r0, r4
c04369cc  1b0000eb   bl       #0xc0436a40
c04369d0  04d08de2   add      sp, sp, #4
c04369d4  3080bde8   pop      {r4, r5, pc}
c04369d8  10402de9   push     {r4, lr}
c04369dc  0040a0e1   mov      r4, r0
c04369e0  86acefeb   bl       #0xc0021c00
c04369e4  95acefeb   bl       #0xc0021c40
c04369e8  041094e5   ldr      r1, [r4, #4]
c04369ec  0020a0e1   mov      r2, r0
c04369f0  603091e5   ldr      r3, [r1, #0x60]
c04369f4  080091e4   ldr      r0, [r1], #8
c04369f8  600000eb   bl       #0xc0436b80
c04369fc  000094e5   ldr      r0, [r4]
c0436a00  081090e5   ldr      r1, [r0, #8]
c0436a04  043094e5   ldr      r3, [r4, #4]
c0436a08  14c091e5   ldr      ip, [r1, #0x14]
c0436a0c  0310a0e1   mov      r1, r3
c0436a10  3cff2fe1   blx      ip
c0436a14  0010a0e1   mov      r1, r0
c0436a18  101084e5   str      r1, [r4, #0x10]
c0436a1c  000094e5   ldr      r0, [r4]
c0436a20  081090e5   ldr      r1, [r0, #8]
c0436a24  043094e5   ldr      r3, [r4, #4]
c0436a28  1cc091e5   ldr      ip, [r1, #0x1c]
c0436a2c  0310a0e1   mov      r1, r3
c0436a30  3cff2fe1   blx      ip
c0436a34  0010a0e1   mov      r1, r0
c0436a38  141084e5   str      r1, [r4, #0x14]
c0436a3c  1080bde8   pop      {r4, pc}
c0436a40  f04c2de9   push     {r4, r5, r6, r7, sl, fp, lr}
c0436a44  58d04de2   sub      sp, sp, #0x58
c0436a48  0050a0e1   mov      r5, r0
c0436a4c  6bacefeb   bl       #0xc0021c00
c0436a50  7aacefeb   bl       #0xc0021c40
c0436a54  0010a0e1   mov      r1, r0
c0436a58  8c4500e3   movw     r4, #0x58c
c0436a5c  014084e0   add      r4, r4, r1
c0436a60  041095e5   ldr      r1, [r5, #4]
c0436a64  087081e2   add      r7, r1, #8
c0436a68  402097e5   ldr      r2, [r7, #0x40]
c0436a6c  083094e5   ldr      r3, [r4, #8]
c0436a70  0010a0e3   mov      r1, #0
c0436a74  030052e1   cmp      r2, r3
c0436a78  0300001a   bne      #0xc0436a8c
c0436a7c  0c3094e5   ldr      r3, [r4, #0xc]
c0436a80  442097e5   ldr      r2, [r7, #0x44]
c0436a84  030052e1   cmp      r2, r3
c0436a88  0110a003   moveq    r1, #1
c0436a8c  011021e2   eor      r1, r1, #1
c0436a90  7110efe6   uxtb     r1, r1
c0436a94  01a0a0e1   mov      sl, r1
c0436a98  0060a0e3   mov      r6, #0
c0436a9c  40008de2   add      r0, sp, #0x40
c0436aa0  1820a0e3   mov      r2, #0x18
c0436aa4  0010a0e3   mov      r1, #0
c0436aa8  6a79efeb   bl       #0xc0015058
c0436aac  041095e5   ldr      r1, [r5, #4]
c0436ab0  001091e5   ldr      r1, [r1]
c0436ab4  000051e3   cmp      r1, #0
c0436ab8  04109515   ldrne    r1, [r5, #4]
c0436abc  00109115   ldrne    r1, [r1]
c0436ac0  01005113   cmpne    r1, #1
c0436ac4  0b00001a   bne      #0xc0436af8
c0436ac8  201097e5   ldr      r1, [r7, #0x20]
c0436acc  000051e3   cmp      r1, #0
c0436ad0  0800000a   beq      #0xc0436af8
c0436ad4  0500a0e1   mov      r0, r5
c0436ad8  600100eb   bl       #0xc0437060
c0436adc  00b0a0e1   mov      fp, r0
c0436ae0  2057fbeb   bl       #0xc030c768
c0436ae4  0b30a0e1   mov      r3, fp
c0436ae8  40208de2   add      r2, sp, #0x40
c0436aec  101084e2   add      r1, r4, #0x10
c0436af0  6658fbeb   bl       #0xc030cc90
c0436af4  0160a0e3   mov      r6, #1
c0436af8  00005ae3   cmp      sl, #0
c0436afc  00005603   cmpeq    r6, #0
c0436b00  1900000a   beq      #0xc0436b6c
c0436b04  7383efeb   bl       #0xc00178d8
c0436b08  ee83efeb   bl       #0xc0017ac8
c0436b0c  8e1f80e2   add      r1, r0, #0x238
c0436b10  0d20a0e1   mov      r2, sp
c0436b14  9e3f80e2   add      r3, r0, #0x278
c0436b18  04c091e4   ldr      ip, [r1], #4
c0436b1c  010053e1   cmp      r3, r1
c0436b20  04c082e4   str      ip, [r2], #4
c0436b24  fbffff1a   bne      #0xc0436b18
c0436b28  00005ae3   cmp      sl, #0
c0436b2c  0300000a   beq      #0xc0436b40
c0436b30  081094e5   ldr      r1, [r4, #8]
c0436b34  0c2094e5   ldr      r2, [r4, #0xc]
c0436b38  38108de5   str      r1, [sp, #0x38]
c0436b3c  3c208de5   str      r2, [sp, #0x3c]
c0436b40  000056e3   cmp      r6, #0
c0436b44  0500000a   beq      #0xc0436b60
c0436b48  40c08de2   add      ip, sp, #0x40
c0436b4c  08208de2   add      r2, sp, #8
c0436b50  0b00bce8   ldm      ip!, {r0, r1, r3}
c0436b54  0b00a2e8   stm      r2!, {r0, r1, r3}
c0436b58  0b009ce8   ldm      ip, {r0, r1, r3}
c0436b5c  0b0082e8   stm      r2, {r0, r1, r3}
c0436b60  5c83efeb   bl       #0xc00178d8
c0436b64  0d10a0e1   mov      r1, sp
c0436b68  0685efeb   bl       #0xc0017f88
c0436b6c  040195e5   ldr      r0, [r5, #0x104]
c0436b70  aad4efeb   bl       #0xc002be20
c0436b74  58d08de2   add      sp, sp, #0x58
c0436b78  f08cbde8   pop      {r4, r5, r6, r7, sl, fp, pc}
c0436b7c  00f020e3   nop      
c0436b80  f04c2de9   push     {r4, r5, r6, r7, sl, fp, lr}
c0436b84  58d04de2   sub      sp, sp, #0x58
c0436b88  0070a0e1   mov      r7, r0
c0436b8c  0140a0e1   mov      r4, r1
c0436b90  0250a0e1   mov      r5, r2
c0436b94  03a0a0e1   mov      sl, r3
c0436b98  00005ae3   cmp      sl, #0
c0436b9c  1f00000a   beq      #0xc0436c20
c0436ba0  0d00a0e1   mov      r0, sp
c0436ba4  5820a0e3   mov      r2, #0x58
c0436ba8  0010a0e3   mov      r1, #0
c0436bac  2979efeb   bl       #0xc0015058
c0436bb0  0dc0a0e1   mov      ip, sp
c0436bb4  0460a0e1   mov      r6, r4
c0436bb8  58b08ce2   add      fp, ip, #0x58
c0436bbc  04e09ce4   ldr      lr, [ip], #4
c0436bc0  0c005be1   cmp      fp, ip
c0436bc4  04e086e4   str      lr, [r6], #4
c0436bc8  fbffff1a   bne      #0xc0436bbc
c0436bcc  00c09ae5   ldr      ip, [sl]
c0436bd0  05005ce3   cmp      ip, #5
c0436bd4  0b00001a   bne      #0xc0436c08
c0436bd8  04608ae2   add      r6, sl, #4
c0436bdc  00c096e5   ldr      ip, [r6]
c0436be0  04b096e5   ldr      fp, [r6, #4]
c0436be4  00c084e5   str      ip, [r4]
c0436be8  04b084e5   str      fp, [r4, #4]
c0436bec  08c0d6e5   ldrb     ip, [r6, #8]
c0436bf0  0fc0c4e5   strb     ip, [r4, #0xf]
c0436bf4  0cc096e5   ldr      ip, [r6, #0xc]
c0436bf8  18c084e5   str      ip, [r4, #0x18]
c0436bfc  10c0d6e5   ldrb     ip, [r6, #0x10]
c0436c00  3ec0c4e5   strb     ip, [r4, #0x3e]
c0436c04  540000ea   b        #0xc0436d5c
c0436c08  5c0b0fe3   movw     r0, #0xfb5c
c0436c0c  071100e3   movw     r1, #0x107
c0436c10  bc004ce3   movt     r0, #0xc0bc
c0436c14  3969efeb   bl       #0xc0011100
c0436c18  00f020e3   nop      
c0436c1c  4e0000ea   b        #0xc0436d5c
c0436c20  b4c5d5e5   ldrb     ip, [r5, #0x5b4]
c0436c24  3cc0c4e5   strb     ip, [r4, #0x3c]
c0436c28  00c095e5   ldr      ip, [r5]
c0436c2c  046095e5   ldr      r6, [r5, #4]
c0436c30  00c084e5   str      ip, [r4]
c0436c34  046084e5   str      r6, [r4, #4]
c0436c38  14c095e5   ldr      ip, [r5, #0x14]
c0436c3c  08c084e5   str      ip, [r4, #8]
c0436c40  3dc3d5e5   ldrb     ip, [r5, #0x33d]
c0436c44  0cc0c4e5   strb     ip, [r4, #0xc]
c0436c48  34c395e5   ldr      ip, [r5, #0x334]
c0436c4c  01005ce3   cmp      ip, #1
c0436c50  00c0a013   movne    ip, #0
c0436c54  0fc0c4e5   strb     ip, [r4, #0xf]
c0436c58  1cc095e5   ldr      ip, [r5, #0x1c]
c0436c5c  206095e5   ldr      r6, [r5, #0x20]
c0436c60  10c084e5   str      ip, [r4, #0x10]
c0436c64  146084e5   str      r6, [r4, #0x14]
c0436c68  020057e3   cmp      r7, #2
c0436c6c  00c0a0e3   mov      ip, #0
c0436c70  0200001a   bne      #0xc0436c80
c0436c74  0c6095e5   ldr      r6, [r5, #0xc]
c0436c78  000056e3   cmp      r6, #0
c0436c7c  01c0a003   moveq    ip, #1
c0436c80  1cc0c4e5   strb     ip, [r4, #0x1c]
c0436c84  1cc0d4e5   ldrb     ip, [r4, #0x1c]
c0436c88  00005ce3   cmp      ip, #0
c0436c8c  0100000a   beq      #0xc0436c98
c0436c90  08c095e5   ldr      ip, [r5, #8]
c0436c94  000000ea   b        #0xc0436c9c
c0436c98  24c095e5   ldr      ip, [r5, #0x24]
c0436c9c  18c084e5   str      ip, [r4, #0x18]
c0436ca0  8cc595e5   ldr      ip, [r5, #0x58c]
c0436ca4  20c084e5   str      ip, [r4, #0x20]
c0436ca8  0a83efeb   bl       #0xc00178d8
c0436cac  8583efeb   bl       #0xc0017ac8
c0436cb0  04c290e5   ldr      ip, [r0, #0x204]
c0436cb4  01005ce3   cmp      ip, #1
c0436cb8  00c0a013   movne    ip, #0
c0436cbc  1ec0c4e5   strb     ip, [r4, #0x1e]
c0436cc0  9cc395e5   ldr      ip, [r5, #0x39c]
c0436cc4  01005ce3   cmp      ip, #1
c0436cc8  00c0a013   movne    ip, #0
c0436ccc  3fc0c4e5   strb     ip, [r4, #0x3f]
c0436cd0  acc0d5e5   ldrb     ip, [r5, #0xac]
c0436cd4  1dc0c4e5   strb     ip, [r4, #0x1d]
c0436cd8  000057e3   cmp      r7, #0
c0436cdc  01005713   cmpne    r7, #1
c0436ce0  0900001a   bne      #0xc0436d0c
c0436ce4  20c094e5   ldr      ip, [r4, #0x20]
c0436ce8  00005ce3   cmp      ip, #0
c0436cec  0600000a   beq      #0xc0436d0c
c0436cf0  9c6500e3   movw     r6, #0x59c
c0436cf4  056086e0   add      r6, r6, r5
c0436cf8  24c084e2   add      ip, r4, #0x24
c0436cfc  0b00b6e8   ldm      r6!, {r0, r1, r3}
c0436d00  0b00ace8   stm      ip!, {r0, r1, r3}
c0436d04  0b0096e8   ldm      r6, {r0, r1, r3}
c0436d08  0b008ce8   stm      ip, {r0, r1, r3}
c0436d0c  8461d5e5   ldrb     r6, [r5, #0x184]
c0436d10  01c0a0e3   mov      ip, #1
c0436d14  000056e3   cmp      r6, #0
c0436d18  0200001a   bne      #0xc0436d28
c0436d1c  806195e5   ldr      r6, [r5, #0x180]
c0436d20  000056e3   cmp      r6, #0
c0436d24  00c0a003   moveq    ip, #0
c0436d28  3dc0c4e5   strb     ip, [r4, #0x3d]
c0436d2c  acc3d5e5   ldrb     ip, [r5, #0x3ac]
c0436d30  3ec0c4e5   strb     ip, [r4, #0x3e]
c0436d34  94c595e5   ldr      ip, [r5, #0x594]
c0436d38  986595e5   ldr      r6, [r5, #0x598]
c0436d3c  40c084e5   str      ip, [r4, #0x40]
c0436d40  446084e5   str      r6, [r4, #0x44]
c0436d44  3b6e85e2   add      r6, r5, #0x3b0
c0436d48  48c084e2   add      ip, r4, #0x48
c0436d4c  0b0096e8   ldm      r6, {r0, r1, r3}
c0436d50  0b008ce8   stm      ip, {r0, r1, r3}
c0436d54  94c3d5e5   ldrb     ip, [r5, #0x394]
c0436d58  55c0c4e5   strb     ip, [r4, #0x55]
c0436d5c  f1b4faeb   bl       #0xc02e4128
c0436d60  f2b6faeb   bl       #0xc02e4930
c0436d64  00c0a0e1   mov      ip, r0
c0436d68  0dc0c4e5   strb     ip, [r4, #0xd]
c0436d6c  edb4faeb   bl       #0xc02e4128
c0436d70  feb6faeb   bl       #0xc02e4970
c0436d74  00c0a0e1   mov      ip, r0
c0436d78  0ec0c4e5   strb     ip, [r4, #0xe]
c0436d7c  e9b4faeb   bl       #0xc02e4128
c0436d80  32b7faeb   bl       #0xc02e4a50
c0436d84  00c0a0e1   mov      ip, r0
c0436d88  54c0c4e5   strb     ip, [r4, #0x54]
c0436d8c  58d08de2   add      sp, sp, #0x58
c0436d90  f08cbde8   pop      {r4, r5, r6, r7, sl, fp, pc}
c0436d94  00f020e3   nop      
c0436d98  f04c2de9   push     {r4, r5, r6, r7, sl, fp, lr}
c0436d9c  0050a0e1   mov      r5, r0
c0436da0  01b0a0e1   mov      fp, r1
c0436da4  0b60a0e1   mov      r6, fp
c0436da8  0040a0e3   mov      r4, #0
c0436dac  420000ea   b        #0xc0436ebc
c0436db0  140095e5   ldr      r0, [r5, #0x14]
c0436db4  202090e5   ldr      r2, [r0, #0x20]
c0436db8  0c2082e2   add      r2, r2, #0xc
c0436dbc  002092e5   ldr      r2, [r2]
c0436dc0  0410a0e1   mov      r1, r4
c0436dc4  32ff2fe1   blx      r2
c0436dc8  0020a0e1   mov      r2, r0
c0436dcc  0270a0e1   mov      r7, r2
c0436dd0  000057e3   cmp      r7, #0
c0436dd4  2f00000a   beq      #0xc0436e98
c0436dd8  140095e5   ldr      r0, [r5, #0x14]
c0436ddc  202090e5   ldr      r2, [r0, #0x20]
c0436de0  142082e2   add      r2, r2, #0x14
c0436de4  002092e5   ldr      r2, [r2]
c0436de8  0410a0e1   mov      r1, r4
c0436dec  32ff2fe1   blx      r2
c0436df0  0020a0e1   mov      r2, r0
c0436df4  02a0a0e1   mov      sl, r2
c0436df8  00005be3   cmp      fp, #0
c0436dfc  0900001a   bne      #0xc0436e28
c0436e00  18e085e2   add      lr, r5, #0x18
c0436e04  3420a0e3   mov      r2, #0x34
c0436e08  94e222e0   mla      r2, r4, r2, lr
c0436e0c  34c0a0e3   mov      ip, #0x34
c0436e10  94ec20e0   mla      r0, r4, ip, lr
c0436e14  002092e5   ldr      r2, [r2]
c0436e18  0710a0e1   mov      r1, r7
c0436e1c  0a30a0e1   mov      r3, sl
c0436e20  c4fdffeb   bl       #0xc0436538
c0436e24  230000ea   b        #0xc0436eb8
c0436e28  20005ae3   cmp      sl, #0x20
c0436e2c  0700001a   bne      #0xc0436e50
c0436e30  fc2095e5   ldr      r2, [r5, #0xfc]
c0436e34  34c0a0e3   mov      ip, #0x34
c0436e38  18e085e2   add      lr, r5, #0x18
c0436e3c  94ec20e0   mla      r0, r4, ip, lr
c0436e40  0710a0e1   mov      r1, r7
c0436e44  0a30a0e1   mov      r3, sl
c0436e48  bafdffeb   bl       #0xc0436538
c0436e4c  190000ea   b        #0xc0436eb8
c0436e50  0a30a0e1   mov      r3, sl
c0436e54  18e085e2   add      lr, r5, #0x18
c0436e58  34c0a0e3   mov      ip, #0x34
c0436e5c  94ec20e0   mla      r0, r4, ip, lr
c0436e60  0710a0e1   mov      r1, r7
c0436e64  0620a0e1   mov      r2, r6
c0436e68  b2fdffeb   bl       #0xc0436538
c0436e6c  18c085e2   add      ip, r5, #0x18
c0436e70  3420a0e3   mov      r2, #0x34
c0436e74  94c223e0   mla      r3, r4, r2, ip
c0436e78  242093e5   ldr      r2, [r3, #0x24]
c0436e7c  203093e5   ldr      r3, [r3, #0x20]
c0436e80  930201e0   mul      r1, r3, r2
c0436e84  0600a0e1   mov      r0, r6
c0436e88  8267efeb   bl       #0xc0010c98
c0436e8c  0020a0e1   mov      r2, r0
c0436e90  0260a0e1   mov      r6, r2
c0436e94  070000ea   b        #0xc0436eb8
c0436e98  183085e2   add      r3, r5, #0x18
c0436e9c  3420a0e3   mov      r2, #0x34
c0436ea0  901b0fe3   movw     r1, #0xfb90
c0436ea4  943220e0   mla      r0, r4, r2, r3
c0436ea8  0030a0e3   mov      r3, #0
c0436eac  bc104ce3   movt     r1, #0xc0bc
c0436eb0  0320a0e1   mov      r2, r3
c0436eb4  9ffdffeb   bl       #0xc0436538
c0436eb8  014084e2   add      r4, r4, #1
c0436ebc  040054e3   cmp      r4, #4
c0436ec0  baffff3a   blo      #0xc0436db0
c0436ec4  f08cbde8   pop      {r4, r5, r6, r7, sl, fp, pc}
c0436ec8  30402de9   push     {r4, r5, lr}
c0436ecc  0040a0e1   mov      r4, r0
c0436ed0  140094e5   ldr      r0, [r4, #0x14]
c0436ed4  201090e5   ldr      r1, [r0, #0x20]
c0436ed8  105094e5   ldr      r5, [r4, #0x10]
c0436edc  0c2091e5   ldr      r2, [r1, #0xc]
c0436ee0  0010a0e3   mov      r1, #0
c0436ee4  32ff2fe1   blx      r2
c0436ee8  101080e2   add      r1, r0, #0x10
c0436eec  0500a0e1   mov      r0, r5
c0436ef0  000300eb   bl       #0xc0437af8
c0436ef4  0010a0e1   mov      r1, r0
c0436ef8  0100a0e1   mov      r0, r1
c0436efc  3080bde8   pop      {r4, r5, pc}
c0436f00  04402de5   str      r4, [sp, #-4]!
c0436f04  00c0a0e1   mov      ip, r0
c0436f08  0140a0e1   mov      r4, r1
c0436f0c  3420a0e3   mov      r2, #0x34
c0436f10  94c223e0   mla      r3, r4, r2, ip
c0436f14  182083e2   add      r2, r3, #0x18
c0436f18  0200a0e1   mov      r0, r2
c0436f1c  04409de4   pop      {r4}
c0436f20  1eff2fe1   bx       lr
c0436f24  00f020e3   nop      
c0436f28  70002de9   push     {r4, r5, r6}
c0436f2c  00c0a0e1   mov      ip, r0
c0436f30  0140a0e1   mov      r4, r1
c0436f34  000054e3   cmp      r4, #0
c0436f38  0200001a   bne      #0xc0436f48
c0436f3c  18208ce2   add      r2, ip, #0x18
c0436f40  0e0000ea   b        #0xc0436f80
c0436f44  00f020e3   nop      
c0436f48  18208ce2   add      r2, ip, #0x18
c0436f4c  d05082e2   add      r5, r2, #0xd0
c0436f50  070000ea   b        #0xc0436f74
c0436f54  00f020e3   nop      
c0436f58  0230a0e1   mov      r3, r2
c0436f5c  306093e5   ldr      r6, [r3, #0x30]
c0436f60  040016e1   tst      r6, r4
c0436f64  0100000a   beq      #0xc0436f70
c0436f68  0320a0e1   mov      r2, r3
c0436f6c  030000ea   b        #0xc0436f80
c0436f70  342082e2   add      r2, r2, #0x34
c0436f74  050052e1   cmp      r2, r5
c0436f78  f6ffff1a   bne      #0xc0436f58
c0436f7c  18208ce2   add      r2, ip, #0x18
c0436f80  0200a0e1   mov      r0, r2
c0436f84  7000bde8   pop      {r4, r5, r6}
c0436f88  1eff2fe1   bx       lr
c0436f8c  00f020e3   nop      
c0436f90  30402de9   push     {r4, r5, lr}
c0436f94  00c0a0e1   mov      ip, r0
c0436f98  0140a0e1   mov      r4, r1
c0436f9c  0020a0e3   mov      r2, #0
c0436fa0  070000ea   b        #0xc0436fc4
c0436fa4  00f020e3   nop      
c0436fa8  3430a0e3   mov      r3, #0x34
c0436fac  18508ce2   add      r5, ip, #0x18
c0436fb0  925323e0   mla      r3, r2, r3, r5
c0436fb4  030054e1   cmp      r4, r3
c0436fb8  0000001a   bne      #0xc0436fc0
c0436fbc  070000ea   b        #0xc0436fe0
c0436fc0  012082e2   add      r2, r2, #1
c0436fc4  030052e3   cmp      r2, #3
c0436fc8  f6ffff3a   blo      #0xc0436fa8
c0436fcc  bc0b0fe3   movw     r0, #0xfbbc
c0436fd0  bc004ce3   movt     r0, #0xc0bc
c0436fd4  5b1fa0e3   mov      r1, #0x16c
c0436fd8  4868efeb   bl       #0xc0011100
c0436fdc  feffffea   b        #0xc0436fdc
c0436fe0  0200a0e1   mov      r0, r2
c0436fe4  3080bde8   pop      {r4, r5, pc}
c0436fe8  70402de9   push     {r4, r5, r6, lr}
c0436fec  0050a0e1   mov      r5, r0
c0436ff0  0040a0e3   mov      r4, #0
c0436ff4  160000ea   b        #0xc0437054
c0436ff8  140095e5   ldr      r0, [r5, #0x14]
c0436ffc  201090e5   ldr      r1, [r0, #0x20]
c0437000  0c2091e5   ldr      r2, [r1, #0xc]
c0437004  0410a0e1   mov      r1, r4
c0437008  32ff2fe1   blx      r2
c043700c  0010a0e1   mov      r1, r0
c0437010  0160a0e1   mov      r6, r1
c0437014  000056e3   cmp      r6, #0
c0437018  0c00000a   beq      #0xc0437050
c043701c  3410a0e3   mov      r1, #0x34
c0437020  182085e2   add      r2, r5, #0x18
c0437024  942121e0   mla      r1, r4, r1, r2
c0437028  06c0a0e1   mov      ip, r6
c043702c  042081e2   add      r2, r1, #4
c0437030  0b00bce8   ldm      ip!, {r0, r1, r3}
c0437034  0b00a2e8   stm      r2!, {r0, r1, r3}
c0437038  0b00bce8   ldm      ip!, {r0, r1, r3}
c043703c  0b00a2e8   stm      r2!, {r0, r1, r3}
c0437040  0b00bce8   ldm      ip!, {r0, r1, r3}
c0437044  0b00a2e8   stm      r2!, {r0, r1, r3}
c0437048  03009ce8   ldm      ip, {r0, r1}
c043704c  030082e8   stm      r2, {r0, r1}
c0437050  014084e2   add      r4, r4, #1
c0437054  040054e3   cmp      r4, #4
c0437058  e6ffff3a   blo      #0xc0436ff8
c043705c  7080bde8   pop      {r4, r5, r6, pc}
c0437060  00c0a0e1   mov      ip, r0
c0437064  10109ce5   ldr      r1, [ip, #0x10]
c0437068  081091e5   ldr      r1, [r1, #8]
c043706c  0100a0e1   mov      r0, r1
c0437070  1eff2fe1   bx       lr
c0437074  00f020e3   nop      
c0437078  f0442de9   push     {r4, r5, r6, r7, sl, lr}
c043707c  64d04de2   sub      sp, sp, #0x64
c0437080  0040a0e1   mov      r4, r0
c0437084  0150a0e1   mov      r5, r1
c0437088  0260a0e1   mov      r6, r2
c043708c  0370a0e1   mov      r7, r3
c0437090  0520a0e1   mov      r2, r5
c0437094  0410a0e1   mov      r1, r4
c0437098  0d00a0e1   mov      r0, sp
c043709c  f50800eb   bl       #0xc0439478
c04370a0  0620a0e1   mov      r2, r6
c04370a4  08108de2   add      r1, sp, #8
c04370a8  0400a0e1   mov      r0, r4
c04370ac  0030a0e3   mov      r3, #0
c04370b0  b2feffeb   bl       #0xc0436b80
c04370b4  0700a0e1   mov      r0, r7
c04370b8  7c0900eb   bl       #0xc04396b0
c04370bc  08c090e5   ldr      ip, [r0, #8]
c04370c0  14c08ce2   add      ip, ip, #0x14
c04370c4  00c09ce5   ldr      ip, [ip]
c04370c8  0d10a0e1   mov      r1, sp
c04370cc  3cff2fe1   blx      ip
c04370d0  00c0a0e1   mov      ip, r0
c04370d4  08c09ce5   ldr      ip, [ip, #8]
c04370d8  0c00a0e1   mov      r0, ip
c04370dc  64d08de2   add      sp, sp, #0x64
c04370e0  f084bde8   pop      {r4, r5, r6, r7, sl, pc}
c04370e4  00f020e3   nop      
c04370e8  70402de9   push     {r4, r5, r6, lr}
c04370ec  04d04de2   sub      sp, sp, #4
c04370f0  0040a0e1   mov      r4, r0
c04370f4  0150a0e1   mov      r5, r1
c04370f8  0400a0e1   mov      r0, r4
c04370fc  450100eb   bl       #0xc0437618
c0437100  0060a0e1   mov      r6, r0
c0437104  0400a0e1   mov      r0, r4
c0437108  2e0100eb   bl       #0xc04375c8
c043710c  0010a0e1   mov      r1, r0
c0437110  0620a0e1   mov      r2, r6
c0437114  0d00a0e1   mov      r0, sp
c0437118  7e0600eb   bl       #0xc0438b18
c043711c  0d10a0e1   mov      r1, sp
c0437120  0500a0e1   mov      r0, r5
c0437124  610500eb   bl       #0xc04386b0
c0437128  0d00a0e1   mov      r0, sp
c043712c  0210a0e3   mov      r1, #2
c0437130  bc0500eb   bl       #0xc0438828
c0437134  00f020e3   nop      
c0437138  04d08de2   add      sp, sp, #4
c043713c  7080bde8   pop      {r4, r5, r6, pc}
c0437140  f04c2de9   push     {r4, r5, r6, r7, sl, fp, lr}
c0437144  6cd04de2   sub      sp, sp, #0x6c
c0437148  0070a0e1   mov      r7, r0
c043714c  0140a0e1   mov      r4, r1
c0437150  02a0a0e1   mov      sl, r2
c0437154  0350a0e1   mov      r5, r3
c0437158  0410a0e1   mov      r1, r4
c043715c  08008de2   add      r0, sp, #8
c0437160  0020a0e3   mov      r2, #0
c0437164  c30800eb   bl       #0xc0439478
c0437168  0a20a0e1   mov      r2, sl
c043716c  10108de2   add      r1, sp, #0x10
c0437170  0400a0e1   mov      r0, r4
c0437174  0030a0e3   mov      r3, #0
c0437178  80feffeb   bl       #0xc0436b80
c043717c  0500a0e1   mov      r0, r5
c0437180  4a0900eb   bl       #0xc04396b0
c0437184  00c0a0e1   mov      ip, r0
c0437188  08009ce5   ldr      r0, [ip, #8]
c043718c  14b090e5   ldr      fp, [r0, #0x14]
c0437190  0c00a0e1   mov      r0, ip
c0437194  08108de2   add      r1, sp, #8
c0437198  3bff2fe1   blx      fp
c043719c  0060a0e1   mov      r6, r0
c04371a0  041096e5   ldr      r1, [r6, #4]
c04371a4  04008de2   add      r0, sp, #4
c04371a8  0520a0e1   mov      r2, r5
c04371ac  41fcffeb   bl       #0xc04362b8
c04371b0  04109de5   ldr      r1, [sp, #4]
c04371b4  0d00a0e1   mov      r0, sp
c04371b8  50208de2   add      r2, sp, #0x50
c04371bc  670600eb   bl       #0xc0438b60
c04371c0  0d10a0e1   mov      r1, sp
c04371c4  0700a0e1   mov      r0, r7
c04371c8  380500eb   bl       #0xc04386b0
c04371cc  0d00a0e1   mov      r0, sp
c04371d0  0210a0e3   mov      r1, #2
c04371d4  930500eb   bl       #0xc0438828
c04371d8  04008de2   add      r0, sp, #4
c04371dc  0210a0e3   mov      r1, #2
c04371e0  dadef7eb   bl       #0xc022ed50
c04371e4  00f020e3   nop      
c04371e8  6cd08de2   add      sp, sp, #0x6c
c04371ec  f08cbde8   pop      {r4, r5, r6, r7, sl, fp, pc}
c04371f0  30402de9   push     {r4, r5, lr}
c04371f4  10d04de2   sub      sp, sp, #0x10
c04371f8  0040a0e1   mov      r4, r0
c04371fc  101094e5   ldr      r1, [r4, #0x10]
c0437200  000051e3   cmp      r1, #0
c0437204  0300001a   bne      #0xc0437218
c0437208  1c0c0fe3   movw     r0, #0xfc1c
c043720c  bc004ce3   movt     r0, #0xc0bc
c0437210  651fa0e3   mov      r1, #0x194
c0437214  b967efeb   bl       #0xc0011100
c0437218  00f020e3   nop      
c043721c  101094e5   ldr      r1, [r4, #0x10]
c0437220  001091e5   ldr      r1, [r1]
c0437224  030051e3   cmp      r1, #3
c0437228  10109415   ldrne    r1, [r4, #0x10]
c043722c  00109115   ldrne    r1, [r1]
c0437230  04005113   cmpne    r1, #4
c0437234  1b00001a   bne      #0xc04372a8
c0437238  f81094e5   ldr      r1, [r4, #0xf8]
c043723c  000051e3   cmp      r1, #0
c0437240  1500001a   bne      #0xc043729c
c0437244  0400a0e1   mov      r0, r4
c0437248  1effffeb   bl       #0xc0436ec8
c043724c  0050a0e1   mov      r5, r0
c0437250  0500a0e3   mov      r0, #5
c0437254  4797efeb   bl       #0xc001cf78
c0437258  0010a0e3   mov      r1, #0
c043725c  00108de5   str      r1, [sp]
c0437260  0030a0e3   mov      r3, #0
c0437264  0510a0e1   mov      r1, r5
c0437268  0320a0e1   mov      r2, r3
c043726c  7197efeb   bl       #0xc001d038
c0437270  0010a0e1   mov      r1, r0
c0437274  f81084e5   str      r1, [r4, #0xf8]
c0437278  f81094e5   ldr      r1, [r4, #0xf8]
c043727c  000051e3   cmp      r1, #0
c0437280  0400001a   bne      #0xc0437298
c0437284  1c0c0fe3   movw     r0, #0xfc1c
c0437288  9a1100e3   movw     r1, #0x19a
c043728c  bc004ce3   movt     r0, #0xc0bc
c0437290  9a67efeb   bl       #0xc0011100
c0437294  00f020e3   nop      
c0437298  00f020e3   nop      
c043729c  f81094e5   ldr      r1, [r4, #0xf8]
c04372a0  360000ea   b        #0xc0437380
c04372a4  00f020e3   nop      
c04372a8  e81094e5   ldr      r1, [r4, #0xe8]
c04372ac  000051e3   cmp      r1, #0
c04372b0  2700001a   bne      #0xc0437354
c04372b4  0400a0e1   mov      r0, r4
c04372b8  02ffffeb   bl       #0xc0436ec8
c04372bc  0010a0e1   mov      r1, r0
c04372c0  ec1084e5   str      r1, [r4, #0xec]
c04372c4  0300a0e3   mov      r0, #3
c04372c8  2a97efeb   bl       #0xc001cf78
c04372cc  0010a0e3   mov      r1, #0
c04372d0  00108de5   str      r1, [sp]
c04372d4  ec1094e5   ldr      r1, [r4, #0xec]
c04372d8  0030a0e3   mov      r3, #0
c04372dc  0320a0e1   mov      r2, r3
c04372e0  5497efeb   bl       #0xc001d038
c04372e4  0010a0e1   mov      r1, r0
c04372e8  e81084e5   str      r1, [r4, #0xe8]
c04372ec  e81094e5   ldr      r1, [r4, #0xe8]
c04372f0  000051e3   cmp      r1, #0
c04372f4  2000001a   bne      #0xc043737c
c04372f8  101c0fe3   movw     r1, #0xfc10
c04372fc  bc104ce3   movt     r1, #0xc0bc
c0437300  04208de2   add      r2, sp, #4
c0437304  0b0091e8   ldm      r1, {r0, r1, r3}
c0437308  0b0082e8   stm      r2, {r0, r1, r3}
c043730c  0300a0e3   mov      r0, #3
c0437310  1897efeb   bl       #0xc001cf78
c0437314  0010a0e3   mov      r1, #0
c0437318  0120e0e3   mvn      r2, #1
c043731c  00108de5   str      r1, [sp]
c0437320  04108de2   add      r1, sp, #4
c0437324  0030a0e3   mov      r3, #0
c0437328  2a97efeb   bl       #0xc001cfd8
c043732c  08109de5   ldr      r1, [sp, #8]
c0437330  f02b0fe3   movw     r2, #0xfbf0
c0437334  bc204ce3   movt     r2, #0xc0bc
c0437338  00108de5   str      r1, [sp]
c043733c  ec3094e5   ldr      r3, [r4, #0xec]
c0437340  a51100e3   movw     r1, #0x1a5
c0437344  1c0c0fe3   movw     r0, #0xfc1c
c0437348  bc004ce3   movt     r0, #0xc0bc
c043734c  7767efeb   bl       #0xc0011130
c0437350  090000ea   b        #0xc043737c
c0437354  0400a0e1   mov      r0, r4
c0437358  dafeffeb   bl       #0xc0436ec8
c043735c  ec2094e5   ldr      r2, [r4, #0xec]
c0437360  000052e1   cmp      r2, r0
c0437364  0300002a   bhs      #0xc0437378
c0437368  1c0c0fe3   movw     r0, #0xfc1c
c043736c  bc004ce3   movt     r0, #0xc0bc
c0437370  6a1fa0e3   mov      r1, #0x1a8
c0437374  6167efeb   bl       #0xc0011100
c0437378  00f020e3   nop      
c043737c  e81094e5   ldr      r1, [r4, #0xe8]
c0437380  0100a0e1   mov      r0, r1
c0437384  10d08de2   add      sp, sp, #0x10
c0437388  3080bde8   pop      {r4, r5, pc}
c043738c  00f020e3   nop      
c0437390  10402de9   push     {r4, lr}
c0437394  0040a0e1   mov      r4, r0
c0437398  e81094e5   ldr      r1, [r4, #0xe8]
c043739c  000051e3   cmp      r1, #0
c04373a0  0500000a   beq      #0xc04373bc
c04373a4  0300a0e3   mov      r0, #3
c04373a8  f296efeb   bl       #0xc001cf78
c04373ac  e81094e5   ldr      r1, [r4, #0xe8]
c04373b0  c097efeb   bl       #0xc001d2b8
c04373b4  0010a0e3   mov      r1, #0
c04373b8  e81084e5   str      r1, [r4, #0xe8]
c04373bc  f81094e5   ldr      r1, [r4, #0xf8]
c04373c0  000051e3   cmp      r1, #0
c04373c4  0500000a   beq      #0xc04373e0
c04373c8  0500a0e3   mov      r0, #5
c04373cc  e996efeb   bl       #0xc001cf78
c04373d0  f81094e5   ldr      r1, [r4, #0xf8]
c04373d4  b797efeb   bl       #0xc001d2b8
c04373d8  0010a0e3   mov      r1, #0
c04373dc  f81084e5   str      r1, [r4, #0xf8]
c04373e0  1080bde8   pop      {r4, pc}
c04373e4  00f020e3   nop      
c04373e8  30402de9   push     {r4, r5, lr}
c04373ec  04d04de2   sub      sp, sp, #4
c04373f0  0040a0e1   mov      r4, r0
c04373f4  0150a0e1   mov      r5, r1
c04373f8  f02094e5   ldr      r2, [r4, #0xf0]
c04373fc  000052e3   cmp      r2, #0
c0437400  0c00001a   bne      #0xc0437438
c0437404  0500a0e1   mov      r0, r5
c0437408  b48cfaeb   bl       #0xc02da6e0
c043740c  0020a0e1   mov      r2, r0
c0437410  f42084e5   str      r2, [r4, #0xf4]
c0437414  0300a0e3   mov      r0, #3
c0437418  d696efeb   bl       #0xc001cf78
c043741c  0030a0e3   mov      r3, #0
c0437420  00308de5   str      r3, [sp]
c0437424  f41094e5   ldr      r1, [r4, #0xf4]
c0437428  0320a0e1   mov      r2, r3
c043742c  0197efeb   bl       #0xc001d038
c0437430  0020a0e1   mov      r2, r0
c0437434  f02084e5   str      r2, [r4, #0xf0]
c0437438  f02094e5   ldr      r2, [r4, #0xf0]
c043743c  0200a0e1   mov      r0, r2
c0437440  04d08de2   add      sp, sp, #4
c0437444  3080bde8   pop      {r4, r5, pc}
c0437448  10402de9   push     {r4, lr}
c043744c  0040a0e1   mov      r4, r0
c0437450  f01094e5   ldr      r1, [r4, #0xf0]
c0437454  000051e3   cmp      r1, #0
c0437458  0500000a   beq      #0xc0437474
c043745c  0300a0e3   mov      r0, #3
c0437460  c496efeb   bl       #0xc001cf78
c0437464  f01094e5   ldr      r1, [r4, #0xf0]
c0437468  9297efeb   bl       #0xc001d2b8
c043746c  0010a0e3   mov      r1, #0
c0437470  f01084e5   str      r1, [r4, #0xf0]
c0437474  1080bde8   pop      {r4, pc}
c0437478  30402de9   push     {r4, r5, lr}
c043747c  04d04de2   sub      sp, sp, #4
c0437480  0040a0e1   mov      r4, r0
c0437484  fc1094e5   ldr      r1, [r4, #0xfc]
c0437488  000051e3   cmp      r1, #0
c043748c  1800001a   bne      #0xc04374f4
c0437490  000094e5   ldr      r0, [r4]
c0437494  081090e5   ldr      r1, [r0, #8]
c0437498  241081e2   add      r1, r1, #0x24
c043749c  001091e5   ldr      r1, [r1]
c04374a0  31ff2fe1   blx      r1
c04374a4  0050a0e1   mov      r5, r0
c04374a8  0000a0e3   mov      r0, #0
c04374ac  b196efeb   bl       #0xc001cf78
c04374b0  0010a0e3   mov      r1, #0
c04374b4  00108de5   str      r1, [sp]
c04374b8  0030a0e3   mov      r3, #0
c04374bc  0510a0e1   mov      r1, r5
c04374c0  0320a0e1   mov      r2, r3
c04374c4  db96efeb   bl       #0xc001d038
c04374c8  0010a0e1   mov      r1, r0
c04374cc  fc1084e5   str      r1, [r4, #0xfc]
c04374d0  fc1094e5   ldr      r1, [r4, #0xfc]
c04374d4  000051e3   cmp      r1, #0
c04374d8  0400001a   bne      #0xc04374f0
c04374dc  500c0fe3   movw     r0, #0xfc50
c04374e0  bc004ce3   movt     r0, #0xc0bc
c04374e4  1d1ea0e3   mov      r1, #0x1d0
c04374e8  0467efeb   bl       #0xc0011100
c04374ec  00f020e3   nop      
c04374f0  00f020e3   nop      
c04374f4  fc1094e5   ldr      r1, [r4, #0xfc]
c04374f8  0100a0e1   mov      r0, r1
c04374fc  04d08de2   add      sp, sp, #4
c0437500  3080bde8   pop      {r4, r5, pc}
c0437504  00f020e3   nop      
c0437508  30402de9   push     {r4, r5, lr}
c043750c  08d04de2   sub      sp, sp, #8
c0437510  0040a0e1   mov      r4, r0
c0437514  001194e5   ldr      r1, [r4, #0x100]
c0437518  000051e3   cmp      r1, #0
c043751c  1f00001a   bne      #0xc04375a0
c0437520  010c84e2   add      r0, r4, #0x100
c0437524  0010a0e3   mov      r1, #0
c0437528  960400eb   bl       #0xc0438788
c043752c  04108de2   add      r1, sp, #4
c0437530  0400a0e1   mov      r0, r4
c0437534  ebfeffeb   bl       #0xc04370e8
c0437538  0c00a0e3   mov      r0, #0xc
c043753c  f10400eb   bl       #0xc0438908
c0437540  0050b0e1   movs     r5, r0
c0437544  0f00000a   beq      #0xc0437588
c0437548  04109de5   ldr      r1, [sp, #4]
c043754c  580081e2   add      r0, r1, #0x58
c0437550  868cfaeb   bl       #0xc02da770
c0437554  00008de5   str      r0, [sp]
c0437558  0010a0e1   mov      r1, r0
c043755c  0500a0e1   mov      r0, r5
c0437560  d80700eb   bl       #0xc04394c8
c0437564  801100e3   movw     r1, #0x180
c0437568  bd104ce3   movt     r1, #0xc0bd
c043756c  001085e5   str      r1, [r5]
c0437570  9c1100e3   movw     r1, #0x19c
c0437574  bd104ce3   movt     r1, #0xc0bd
c0437578  001085e5   str      r1, [r5]
c043757c  0510a0e1   mov      r1, r5
c0437580  010000ea   b        #0xc043758c
c0437584  00f020e3   nop      
c0437588  0010a0e3   mov      r1, #0
c043758c  010c84e2   add      r0, r4, #0x100
c0437590  7c0400eb   bl       #0xc0438788
c0437594  04008de2   add      r0, sp, #4
c0437598  0210a0e3   mov      r1, #2
c043759c  03def7eb   bl       #0xc022edb0
c04375a0  001194e5   ldr      r1, [r4, #0x100]
c04375a4  0100a0e1   mov      r0, r1
c04375a8  08d08de2   add      sp, sp, #8
c04375ac  3080bde8   pop      {r4, r5, pc}
c04375b0  10402de9   push     {r4, lr}
c04375b4  0040a0e1   mov      r4, r0
c04375b8  010c84e2   add      r0, r4, #0x100
c04375bc  0010a0e3   mov      r1, #0
c04375c0  700400eb   bl       #0xc0438788
c04375c4  1080bde8   pop      {r4, pc}
c04375c8  10402de9   push     {r4, lr}
c04375cc  0040a0e1   mov      r4, r0
c04375d0  081094e5   ldr      r1, [r4, #8]
c04375d4  000051e3   cmp      r1, #0
c04375d8  0400001a   bne      #0xc04375f0
c04375dc  840c0fe3   movw     r0, #0xfc84
c04375e0  eb1100e3   movw     r1, #0x1eb
c04375e4  bc004ce3   movt     r0, #0xc0bc
c04375e8  c466efeb   bl       #0xc0011100
c04375ec  00f020e3   nop      
c04375f0  00f020e3   nop      
c04375f4  081094e5   ldr      r1, [r4, #8]
c04375f8  0100a0e1   mov      r0, r1
c04375fc  1080bde8   pop      {r4, pc}
c0437600  00c0a0e1   mov      ip, r0
c0437604  04109ce5   ldr      r1, [ip, #4]
c0437608  281091e5   ldr      r1, [r1, #0x28]
c043760c  0100a0e1   mov      r0, r1
c0437610  1eff2fe1   bx       lr
c0437614  00f020e3   nop      
c0437618  00c0a0e1   mov      ip, r0
c043761c  04109ce5   ldr      r1, [ip, #4]
c0437620  481081e2   add      r1, r1, #0x48
c0437624  0100a0e1   mov      r0, r1
c0437628  1eff2fe1   bx       lr
c043762c  00f020e3   nop      
c0437630  30402de9   push     {r4, r5, lr}
c0437634  0040a0e1   mov      r4, r0
c0437638  0150a0e1   mov      r5, r1
c043763c  0400a0e1   mov      r0, r4
c0437640  0010a0e3   mov      r1, #0
c0437644  2dfeffeb   bl       #0xc0436f00
c0437648  101094e5   ldr      r1, [r4, #0x10]
c043764c  041091e5   ldr      r1, [r1, #4]
c0437650  042080e2   add      r2, r0, #4
c0437654  0500a0e1   mov      r0, r5
c0437658  0afbffeb   bl       #0xc0436288
c043765c  00f020e3   nop      
c0437660  3080bde8   pop      {r4, r5, pc}
c0437664  00f020e3   nop      
c0437668  30412de9   push     {r4, r5, r8, lr}
c043766c  08d04de2   sub      sp, sp, #8
c0437670  0040a0e1   mov      r4, r0
c0437674  0150a0e1   mov      r5, r1
c0437678  b82c0fe3   movw     r2, #0xfcb8
c043767c  bc204ce3   movt     r2, #0xc0bc
c0437680  001092e5   ldr      r1, [r2]
c0437684  04108de5   str      r1, [sp, #4]
c0437688  0c1084e2   add      r1, r4, #0xc
c043768c  04008de2   add      r0, sp, #4
c0437690  220400eb   bl       #0xc0438720
c0437694  0d10a0e1   mov      r1, sp
c0437698  0400a0e1   mov      r0, r4
c043769c  e3ffffeb   bl       #0xc0437630
c04376a0  0d10a0e1   mov      r1, sp
c04376a4  0c0084e2   add      r0, r4, #0xc
c04376a8  0e0400eb   bl       #0xc04386e8
c04376ac  0d00a0e1   mov      r0, sp
c04376b0  0210a0e3   mov      r1, #2
c04376b4  a5ddf7eb   bl       #0xc022ed50
c04376b8  04108de2   add      r1, sp, #4
c04376bc  0500a0e1   mov      r0, r5
c04376c0  ec0300eb   bl       #0xc0438678
c04376c4  04008de2   add      r0, sp, #4
c04376c8  0210a0e3   mov      r1, #2
c04376cc  9fddf7eb   bl       #0xc022ed50
c04376d0  00f020e3   nop      
c04376d4  08d08de2   add      sp, sp, #8
c04376d8  3081bde8   pop      {r4, r5, r8, pc}
c04376dc  00f020e3   nop      
c04376e0  00c0a0e1   mov      ip, r0
c04376e4  0c109ce5   ldr      r1, [ip, #0xc]
c04376e8  0100a0e1   mov      r0, r1
c04376ec  1eff2fe1   bx       lr
c04376f0  04402de5   str      r4, [sp, #-4]!
c04376f4  00c0a0e1   mov      ip, r0
c04376f8  18108ce2   add      r1, ip, #0x18
c04376fc  d03081e2   add      r3, r1, #0xd0
c0437700  070000ea   b        #0xc0437724
c0437704  00f020e3   nop      
c0437708  0120a0e1   mov      r2, r1
c043770c  304092e5   ldr      r4, [r2, #0x30]
c0437710  100014e3   tst      r4, #0x10
c0437714  0100000a   beq      #0xc0437720
c0437718  0110a0e3   mov      r1, #1
c043771c  030000ea   b        #0xc0437730
c0437720  341081e2   add      r1, r1, #0x34
c0437724  030051e1   cmp      r1, r3
c0437728  f6ffff1a   bne      #0xc0437708
c043772c  0010a0e3   mov      r1, #0
c0437730  0100a0e1   mov      r0, r1
c0437734  04409de4   pop      {r4}
c0437738  1eff2fe1   bx       lr
c043773c  00f020e3   nop      
c0437740  f04c2de9   push     {r4, r5, r6, r7, sl, fp, lr}
c0437744  48d04de2   sub      sp, sp, #0x48
c0437748  0060a0e1   mov      r6, r0
c043774c  0150a0e1   mov      r5, r1
c0437750  000055e3   cmp      r5, #0
c0437754  0100001a   bne      #0xc0437760
c0437758  da0000ea   b        #0xc0437ac8
c043775c  00f020e3   nop      
c0437760  d00d0fe3   movw     r0, #0xfdd0
c0437764  bc004ce3   movt     r0, #0xc0bc
c0437768  35ff2fe1   blx      r5
c043776c  0600a0e1   mov      r0, r6
c0437770  94ffffeb   bl       #0xc04375c8
c0437774  0040a0e1   mov      r4, r0
c0437778  32b1ffeb   bl       #0xc0423c48
c043777c  b1b1ffeb   bl       #0xc0423e48
c0437780  0070a0e1   mov      r7, r0
c0437784  0600a0e1   mov      r0, r6
c0437788  34feffeb   bl       #0xc0437060
c043778c  001094e5   ldr      r1, [r4]
c0437790  0020a0e1   mov      r2, r0
c0437794  dc0d0fe3   movw     r0, #0xfddc
c0437798  0730a0e1   mov      r3, r7
c043779c  bc004ce3   movt     r0, #0xc0bc
c04377a0  35ff2fe1   blx      r5
c04377a4  10108de2   add      r1, sp, #0x10
c04377a8  0600a0e1   mov      r0, r6
c04377ac  4dfeffeb   bl       #0xc04370e8
c04377b0  10209de5   ldr      r2, [sp, #0x10]
c04377b4  30008de2   add      r0, sp, #0x30
c04377b8  581082e2   add      r1, r2, #0x58
c04377bc  6b8cfaeb   bl       #0xc02da970
c04377c0  44209de5   ldr      r2, [sp, #0x44]
c04377c4  00208de5   str      r2, [sp]
c04377c8  30109de5   ldr      r1, [sp, #0x30]
c04377cc  34209de5   ldr      r2, [sp, #0x34]
c04377d0  40309de5   ldr      r3, [sp, #0x40]
c04377d4  f80c0fe3   movw     r0, #0xfcf8
c04377d8  bc004ce3   movt     r0, #0xc0bc
c04377dc  35ff2fe1   blx      r5
c04377e0  10109de5   ldr      r1, [sp, #0x10]
c04377e4  18008de2   add      r0, sp, #0x18
c04377e8  608cfaeb   bl       #0xc02da970
c04377ec  2c209de5   ldr      r2, [sp, #0x2c]
c04377f0  00208de5   str      r2, [sp]
c04377f4  18109de5   ldr      r1, [sp, #0x18]
c04377f8  1c209de5   ldr      r2, [sp, #0x1c]
c04377fc  28309de5   ldr      r3, [sp, #0x28]
c0437800  380d0fe3   movw     r0, #0xfd38
c0437804  bc004ce3   movt     r0, #0xc0bc
c0437808  35ff2fe1   blx      r5
c043780c  fc0d0fe3   movw     r0, #0xfdfc
c0437810  bc004ce3   movt     r0, #0xc0bc
c0437814  35ff2fe1   blx      r5
c0437818  042096e5   ldr      r2, [r6, #4]
c043781c  602092e5   ldr      r2, [r2, #0x60]
c0437820  000052e3   cmp      r2, #0
c0437824  1d00000a   beq      #0xc04378a0
c0437828  042096e5   ldr      r2, [r6, #4]
c043782c  602092e5   ldr      r2, [r2, #0x60]
c0437830  002092e5   ldr      r2, [r2]
c0437834  050052e3   cmp      r2, #5
c0437838  1800001a   bne      #0xc04378a0
c043783c  042096e5   ldr      r2, [r6, #4]
c0437840  602092e5   ldr      r2, [r2, #0x60]
c0437844  044082e2   add      r4, r2, #4
c0437848  1020d4e5   ldrb     r2, [r4, #0x10]
c043784c  000052e3   cmp      r2, #0
c0437850  0200000a   beq      #0xc0437860
c0437854  2c7e0fe3   movw     r7, #0xfe2c
c0437858  bc704ce3   movt     r7, #0xc0bc
c043785c  010000ea   b        #0xc0437868
c0437860  d47c0fe3   movw     r7, #0xfcd4
c0437864  bc704ce3   movt     r7, #0xc0bc
c0437868  0c0094e5   ldr      r0, [r4, #0xc]
c043786c  ff8bfaeb   bl       #0xc02da870
c0437870  00708de5   str      r7, [sp]
c0437874  042094e5   ldr      r2, [r4, #4]
c0437878  001094e5   ldr      r1, [r4]
c043787c  0030a0e1   mov      r3, r0
c0437880  080e0fe3   movw     r0, #0xfe08
c0437884  bc004ce3   movt     r0, #0xc0bc
c0437888  35ff2fe1   blx      r5
c043788c  10008de2   add      r0, sp, #0x10
c0437890  0210a0e3   mov      r1, #2
c0437894  45ddf7eb   bl       #0xc022edb0
c0437898  8a0000ea   b        #0xc0437ac8
c043789c  00f020e3   nop      
c04378a0  042096e5   ldr      r2, [r6, #4]
c04378a4  084082e2   add      r4, r2, #8
c04378a8  3c20d4e5   ldrb     r2, [r4, #0x3c]
c04378ac  000052e3   cmp      r2, #0
c04378b0  0200000a   beq      #0xc04378c0
c04378b4  540d0fe3   movw     r0, #0xfd54
c04378b8  bc004ce3   movt     r0, #0xc0bc
c04378bc  35ff2fe1   blx      r5
c04378c0  043096e5   ldr      r3, [r6, #4]
c04378c4  060093e8   ldm      r3, {r1, r2}
c04378c8  680d0fe3   movw     r0, #0xfd68
c04378cc  bc004ce3   movt     r0, #0xc0bc
c04378d0  35ff2fe1   blx      r5
c04378d4  180094e5   ldr      r0, [r4, #0x18]
c04378d8  e48bfaeb   bl       #0xc02da870
c04378dc  042094e5   ldr      r2, [r4, #4]
c04378e0  001094e5   ldr      r1, [r4]
c04378e4  0030a0e1   mov      r3, r0
c04378e8  800d0fe3   movw     r0, #0xfd80
c04378ec  bc004ce3   movt     r0, #0xc0bc
c04378f0  35ff2fe1   blx      r5
c04378f4  180094e5   ldr      r0, [r4, #0x18]
c04378f8  dc8bfaeb   bl       #0xc02da870
c04378fc  142094e5   ldr      r2, [r4, #0x14]
c0437900  101094e5   ldr      r1, [r4, #0x10]
c0437904  0030a0e1   mov      r3, r0
c0437908  180d0fe3   movw     r0, #0xfd18
c043790c  bc004ce3   movt     r0, #0xc0bc
c0437910  35ff2fe1   blx      r5
c0437914  0c20d4e5   ldrb     r2, [r4, #0xc]
c0437918  000052e3   cmp      r2, #0
c043791c  0300000a   beq      #0xc0437930
c0437920  d8cc0fe3   movw     ip, #0xfcd8
c0437924  bcc04ce3   movt     ip, #0xc0bc
c0437928  020000ea   b        #0xc0437938
c043792c  00f020e3   nop      
c0437930  d4cc0fe3   movw     ip, #0xfcd4
c0437934  bcc04ce3   movt     ip, #0xc0bc
c0437938  1c20d4e5   ldrb     r2, [r4, #0x1c]
c043793c  000052e3   cmp      r2, #0
c0437940  0200000a   beq      #0xc0437950
c0437944  bc7c0fe3   movw     r7, #0xfcbc
c0437948  bc704ce3   movt     r7, #0xc0bc
c043794c  010000ea   b        #0xc0437958
c0437950  d47c0fe3   movw     r7, #0xfcd4
c0437954  bc704ce3   movt     r7, #0xc0bc
c0437958  202094e5   ldr      r2, [r4, #0x20]
c043795c  000052e3   cmp      r2, #0
c0437960  0200001a   bne      #0xc0437970
c0437964  d43c0fe3   movw     r3, #0xfcd4
c0437968  bc304ce3   movt     r3, #0xc0bc
c043796c  070000ea   b        #0xc0437990
c0437970  202094e5   ldr      r2, [r4, #0x20]
c0437974  020052e3   cmp      r2, #2
c0437978  0200001a   bne      #0xc0437988
c043797c  c43c0fe3   movw     r3, #0xfcc4
c0437980  bc304ce3   movt     r3, #0xc0bc
c0437984  010000ea   b        #0xc0437990
c0437988  cc3c0fe3   movw     r3, #0xfccc
c043798c  bc304ce3   movt     r3, #0xc0bc
c0437990  3d20d4e5   ldrb     r2, [r4, #0x3d]
c0437994  000052e3   cmp      r2, #0
c0437998  0200000a   beq      #0xc04379a8
c043799c  e0ac0fe3   movw     sl, #0xfce0
c04379a0  bca04ce3   movt     sl, #0xc0bc
c04379a4  010000ea   b        #0xc04379b0
c04379a8  d4ac0fe3   movw     sl, #0xfcd4
c04379ac  bca04ce3   movt     sl, #0xc0bc
c04379b0  1d20d4e5   ldrb     r2, [r4, #0x1d]
c04379b4  000052e3   cmp      r2, #0
c04379b8  0200000a   beq      #0xc04379c8
c04379bc  e8bc0fe3   movw     fp, #0xfce8
c04379c0  bcb04ce3   movt     fp, #0xc0bc
c04379c4  010000ea   b        #0xc04379d0
c04379c8  d4bc0fe3   movw     fp, #0xfcd4
c04379cc  bcb04ce3   movt     fp, #0xc0bc
c04379d0  1e20d4e5   ldrb     r2, [r4, #0x1e]
c04379d4  000052e3   cmp      r2, #0
c04379d8  0a00000a   beq      #0xc0437a08
c04379dc  3f20d4e5   ldrb     r2, [r4, #0x3f]
c04379e0  000052e3   cmp      r2, #0
c04379e4  0300000a   beq      #0xc04379f8
c04379e8  582e0fe3   movw     r2, #0xfe58
c04379ec  bc204ce3   movt     r2, #0xc0bc
c04379f0  130000ea   b        #0xc0437a44
c04379f4  00f020e3   nop      
c04379f8  642e0fe3   movw     r2, #0xfe64
c04379fc  bc204ce3   movt     r2, #0xc0bc
c0437a00  0f0000ea   b        #0xc0437a44
c0437a04  00f020e3   nop      
c0437a08  0d20d4e5   ldrb     r2, [r4, #0xd]
c0437a0c  000052e3   cmp      r2, #0
c0437a10  0900000a   beq      #0xc0437a3c
c0437a14  0e20d4e5   ldrb     r2, [r4, #0xe]
c0437a18  000052e3   cmp      r2, #0
c0437a1c  0300000a   beq      #0xc0437a30
c0437a20  a02d0fe3   movw     r2, #0xfda0
c0437a24  bc204ce3   movt     r2, #0xc0bc
c0437a28  050000ea   b        #0xc0437a44
c0437a2c  00f020e3   nop      
c0437a30  f02c0fe3   movw     r2, #0xfcf0
c0437a34  bc204ce3   movt     r2, #0xc0bc
c0437a38  010000ea   b        #0xc0437a44
c0437a3c  d42c0fe3   movw     r2, #0xfcd4
c0437a40  bc204ce3   movt     r2, #0xc0bc
c0437a44  02e0a0e1   mov      lr, r2
c0437a48  084c8de8   stm      sp, {r3, sl, fp, lr}
c0437a4c  401094e5   ldr      r1, [r4, #0x40]
c0437a50  0730a0e1   mov      r3, r7
c0437a54  380e0fe3   movw     r0, #0xfe38
c0437a58  0c20a0e1   mov      r2, ip
c0437a5c  bc004ce3   movt     r0, #0xc0bc
c0437a60  35ff2fe1   blx      r5
c0437a64  042096e5   ldr      r2, [r6, #4]
c0437a68  002092e5   ldr      r2, [r2]
c0437a6c  000052e3   cmp      r2, #0
c0437a70  04209615   ldrne    r2, [r6, #4]
c0437a74  00209215   ldrne    r2, [r2]
c0437a78  01005213   cmpne    r2, #1
c0437a7c  0e00001a   bne      #0xc0437abc
c0437a80  202094e5   ldr      r2, [r4, #0x20]
c0437a84  000052e3   cmp      r2, #0
c0437a88  0b00000a   beq      #0xc0437abc
c0437a8c  382094e5   ldr      r2, [r4, #0x38]
c0437a90  08208de5   str      r2, [sp, #8]
c0437a94  342094e5   ldr      r2, [r4, #0x34]
c0437a98  04208de5   str      r2, [sp, #4]
c0437a9c  302094e5   ldr      r2, [r4, #0x30]
c0437aa0  00208de5   str      r2, [sp]
c0437aa4  241094e5   ldr      r1, [r4, #0x24]
c0437aa8  282094e5   ldr      r2, [r4, #0x28]
c0437aac  2c3094e5   ldr      r3, [r4, #0x2c]
c0437ab0  ac0d0fe3   movw     r0, #0xfdac
c0437ab4  bc004ce3   movt     r0, #0xc0bc
c0437ab8  35ff2fe1   blx      r5
c0437abc  10008de2   add      r0, sp, #0x10
c0437ac0  0210a0e3   mov      r1, #2
c0437ac4  b9dcf7eb   bl       #0xc022edb0
c0437ac8  48d08de2   add      sp, sp, #0x48
c0437acc  f08cbde8   pop      {r4, r5, r6, r7, sl, fp, pc}
c0437ad0  30402de9   push     {r4, r5, lr}
c0437ad4  0040a0e1   mov      r4, r0
c0437ad8  0150a0e1   mov      r5, r1
c0437adc  010015e3   tst      r5, #1
c0437ae0  0200000a   beq      #0xc0437af0
c0437ae4  0400a0e1   mov      r0, r4
c0437ae8  0c10a0e3   mov      r1, #0xc
c0437aec  6a6eefeb   bl       #0xc001349c
c0437af0  3080bde8   pop      {r4, r5, pc}
c0437af4  00f020e3   nop      
c0437af8  70402de9   push     {r4, r5, r6, lr}
c0437afc  04d04de2   sub      sp, sp, #4
c0437b00  0040a0e1   mov      r4, r0
c0437b04  0150a0e1   mov      r5, r1
c0437b08  041094e5   ldr      r1, [r4, #4]
c0437b0c  0330a0e3   mov      r3, #3
c0437b10  0d00a0e1   mov      r0, sp
c0437b14  0520a0e1   mov      r2, r5
c0437b18  d20600eb   bl       #0xc0439668
c0437b1c  00009de5   ldr      r0, [sp]
c0437b20  98f6ffeb   bl       #0xc0435588
c0437b24  0060a0e1   mov      r6, r0
c0437b28  0d00a0e1   mov      r0, sp
c0437b2c  0210a0e3   mov      r1, #2
c0437b30  86dcf7eb   bl       #0xc022ed50
c0437b34  0620a0e1   mov      r2, r6
c0437b38  0200a0e1   mov      r0, r2
c0437b3c  04d08de2   add      sp, sp, #4
c0437b40  7080bde8   pop      {r4, r5, r6, pc}
c0437b44  00f020e3   nop      
c0437b48  f04b2de9   push     {r4, r5, r6, r7, r8, sb, fp, lr}
c0437b4c  08d04de2   sub      sp, sp, #8
c0437b50  0070a0e1   mov      r7, r0
c0437b54  0160a0e1   mov      r6, r1
c0437b58  0250a0e1   mov      r5, r2
c0437b5c  884e0fe3   movw     r4, #0xfe88
c0437b60  bc404ce3   movt     r4, #0xc0bc
c0437b64  708e0fe3   movw     r8, #0xfe70
c0437b68  bc804ce3   movt     r8, #0xc0bc
c0437b6c  000398e8   ldm      r8, {r8, sb}
c0437b70  00038de8   stm      sp, {r8, sb}
c0437b74  00c09de5   ldr      ip, [sp]
c0437b78  08b095e5   ldr      fp, [r5, #8]
c0437b7c  0030a0e3   mov      r3, #0
c0437b80  0c005be1   cmp      fp, ip
c0437b84  0300001a   bne      #0xc0437b98
c0437b88  0cb095e5   ldr      fp, [r5, #0xc]
c0437b8c  04c09de5   ldr      ip, [sp, #4]
c0437b90  0c005be1   cmp      fp, ip
c0437b94  0130a003   moveq    r3, #1
c0437b98  000053e3   cmp      r3, #0
c0437b9c  0300000a   beq      #0xc0437bb0
c0437ba0  904e0fe3   movw     r4, #0xfe90
c0437ba4  bc404ce3   movt     r4, #0xc0bc
c0437ba8  260000ea   b        #0xc0437c48
c0437bac  00f020e3   nop      
c0437bb0  788e0fe3   movw     r8, #0xfe78
c0437bb4  bc804ce3   movt     r8, #0xc0bc
c0437bb8  000398e8   ldm      r8, {r8, sb}
c0437bbc  00038de8   stm      sp, {r8, sb}
c0437bc0  00c09de5   ldr      ip, [sp]
c0437bc4  08b095e5   ldr      fp, [r5, #8]
c0437bc8  0030a0e3   mov      r3, #0
c0437bcc  0c005be1   cmp      fp, ip
c0437bd0  0300001a   bne      #0xc0437be4
c0437bd4  0cb095e5   ldr      fp, [r5, #0xc]
c0437bd8  04c09de5   ldr      ip, [sp, #4]
c0437bdc  0c005be1   cmp      fp, ip
c0437be0  0130a003   moveq    r3, #1
c0437be4  000053e3   cmp      r3, #0
c0437be8  0200000a   beq      #0xc0437bf8
c0437bec  8c4e0fe3   movw     r4, #0xfe8c
c0437bf0  bc404ce3   movt     r4, #0xc0bc
c0437bf4  130000ea   b        #0xc0437c48
c0437bf8  808e0fe3   movw     r8, #0xfe80
c0437bfc  bc804ce3   movt     r8, #0xc0bc
c0437c00  000398e8   ldm      r8, {r8, sb}
c0437c04  00038de8   stm      sp, {r8, sb}
c0437c08  00c09de5   ldr      ip, [sp]
c0437c0c  08b095e5   ldr      fp, [r5, #8]
c0437c10  0030a0e3   mov      r3, #0
c0437c14  0c005be1   cmp      fp, ip
c0437c18  0300001a   bne      #0xc0437c2c
c0437c1c  0cb095e5   ldr      fp, [r5, #0xc]
c0437c20  04c09de5   ldr      ip, [sp, #4]
c0437c24  0c005be1   cmp      fp, ip
c0437c28  0130a003   moveq    r3, #1
c0437c2c  000053e3   cmp      r3, #0
c0437c30  0200000a   beq      #0xc0437c40
c0437c34  984e0fe3   movw     r4, #0xfe98
c0437c38  bc404ce3   movt     r4, #0xc0bc
c0437c3c  010000ea   b        #0xc0437c48
c0437c40  884e0fe3   movw     r4, #0xfe88
c0437c44  bc404ce3   movt     r4, #0xc0bc
c0437c48  0410a0e1   mov      r1, r4
c0437c4c  0600a0e1   mov      r0, r6
