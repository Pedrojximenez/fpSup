c031be60  f04b2de9   push     {r4, r5, r6, r7, r8, sb, fp, lr}
c031be64  46df4de2   sub      sp, sp, #0x118
c031be68  40008de5   str      r0, [sp, #0x40]
c031be6c  50090ae3   movw     r0, #0xa950
c031be70  43034ce3   movt     r0, #0xc343
c031be74  0160a0e1   mov      r6, r1
c031be78  44008de5   str      r0, [sp, #0x44]
c031be7c  cff7f3eb   bl       #0xc0019dc0
c031be80  9c2f06e3   movw     r2, #0x6f9c
c031be84  b5204ce3   movt     r2, #0xc0b5
c031be88  04208de5   str      r2, [sp, #4]
c031be8c  1c2096e5   ldr      r2, [r6, #0x1c]
c031be90  0130a0e3   mov      r3, #1
c031be94  4010a0e3   mov      r1, #0x40
c031be98  00208de5   str      r2, [sp]
c031be9c  0020a0e3   mov      r2, #0
c031bea0  6af9f3eb   bl       #0xc001a450
c031bea4  c5f7f3eb   bl       #0xc0019dc0
c031bea8  0130a0e3   mov      r3, #1
c031beac  0020a0e3   mov      r2, #0
c031beb0  03c0a0e1   mov      ip, r3
c031beb4  0210a0e1   mov      r1, r2
c031beb8  0e108de8   stm      sp, {r1, r2, r3, ip}
c031bebc  0430a0e3   mov      r3, #4
c031bec0  4010a0e3   mov      r1, #0x40
c031bec4  83f8f3eb   bl       #0xc001a0d8
c031bec8  0040a0e3   mov      r4, #0
c031becc  03dcffeb   bl       #0xc0312ee0
c031bed0  2c008de5   str      r0, [sp, #0x2c]
c031bed4  e3f7ffeb   bl       #0xc0319e68
c031bed8  0070a0e1   mov      r7, r0
c031bedc  0700a0e1   mov      r0, r7
c031bee0  0010a0e3   mov      r1, #0
c031bee4  33f8ffeb   bl       #0xc0319fb8
c031bee8  781500eb   bl       #0xc03214d0
c031beec  401d0be3   movw     r1, #0xbd40
c031bef0  31104ce3   movt     r1, #0xc031
c031bef4  831500eb   bl       #0xc0321508
c031bef8  44009de5   ldr      r0, [sp, #0x44]
c031befc  0010a0e3   mov      r1, #0
c031bf00  0110c0e5   strb     r1, [r0, #1]
c031bf04  44009de5   ldr      r0, [sp, #0x44]
c031bf08  0010a0e3   mov      r1, #0
c031bf0c  0210c0e5   strb     r1, [r0, #2]
c031bf10  44009de5   ldr      r0, [sp, #0x44]
c031bf14  0010a0e3   mov      r1, #0
c031bf18  0310c0e5   strb     r1, [r0, #3]
c031bf1c  b81196e5   ldr      r1, [r6, #0x1b8]
c031bf20  40009de5   ldr      r0, [sp, #0x40]
c031bf24  041080e5   str      r1, [r0, #4]
c031bf28  72f8ffeb   bl       #0xc031a0f8
c031bf2c  28008de5   str      r0, [sp, #0x28]
c031bf30  28009de5   ldr      r0, [sp, #0x28]
c031bf34  0210a0e3   mov      r1, #2
c031bf38  7cf8ffeb   bl       #0xc031a130
c031bf3c  281096e5   ldr      r1, [r6, #0x28]
c031bf40  28009de5   ldr      r0, [sp, #0x28]
c031bf44  8df8ffeb   bl       #0xc031a180
c031bf48  14ddffeb   bl       #0xc03133a0
c031bf4c  30008de5   str      r0, [sp, #0x30]
c031bf50  30009de5   ldr      r0, [sp, #0x30]
c031bf54  99e4ffeb   bl       #0xc03151c0
c031bf58  002090e5   ldr      r2, [r0]
c031bf5c  1c1096e5   ldr      r1, [r6, #0x1c]
c031bf60  020051e1   cmp      r1, r2
c031bf64  0900000a   beq      #0xc031bf90
c031bf68  341096e5   ldr      r1, [r6, #0x34]
c031bf6c  2c009de5   ldr      r0, [sp, #0x2c]
c031bf70  50dcffeb   bl       #0xc03130b8
c031bf74  301096e5   ldr      r1, [r6, #0x30]
c031bf78  0700a0e1   mov      r0, r7
c031bf7c  01f8ffeb   bl       #0xc0319f88
c031bf80  1c1096e5   ldr      r1, [r6, #0x1c]
c031bf84  30009de5   ldr      r0, [sp, #0x30]
c031bf88  1cddffeb   bl       #0xc0313400
c031bf8c  00f020e3   nop      
c031bf90  7e6904eb   bl       #0xc0436590
c031bf94  14108de2   add      r1, sp, #0x14
c031bf98  526c04eb   bl       #0xc04370e8
c031bf9c  14109de5   ldr      r1, [sp, #0x14]
c031bfa0  0150a0e1   mov      r5, r1
c031bfa4  28009de5   ldr      r0, [sp, #0x28]
c031bfa8  0110a0e3   mov      r1, #1
c031bfac  fffaffeb   bl       #0xc031abb0
c031bfb0  948f06e3   movw     r8, #0x6f94
c031bfb4  b5804ce3   movt     r8, #0xc0b5
c031bfb8  000398e8   ldm      r8, {r8, sb}
c031bfbc  0900a0e1   mov      r0, sb
c031bfc0  50808de5   str      r8, [sp, #0x50]
c031bfc4  54008de5   str      r0, [sp, #0x54]
c031bfc8  110e8de2   add      r0, sp, #0x110
c031bfcc  7710a0e3   mov      r1, #0x77
c031bfd0  224200eb   bl       #0xc032c860
c031bfd4  10019de5   ldr      r0, [sp, #0x110]
c031bfd8  48008de5   str      r0, [sp, #0x48]
c031bfdc  420f8de2   add      r0, sp, #0x108
c031bfe0  7710a0e3   mov      r1, #0x77
c031bfe4  1d4200eb   bl       #0xc032c860
c031bfe8  0c019de5   ldr      r0, [sp, #0x10c]
c031bfec  4c008de5   str      r0, [sp, #0x4c]
c031bff0  500085e2   add      r0, r5, #0x50
c031bff4  854bfceb   bl       #0xc022ee10
c031bff8  48109de5   ldr      r1, [sp, #0x48]
c031bffc  11f030e7   udiv     r0, r1, r0
c031c000  48008de5   str      r0, [sp, #0x48]
c031c004  540085e2   add      r0, r5, #0x54
c031c008  a04bfceb   bl       #0xc022ee90
c031c00c  4c109de5   ldr      r1, [sp, #0x4c]
c031c010  11f030e7   udiv     r0, r1, r0
c031c014  4c008de5   str      r0, [sp, #0x4c]
c031c018  481095e5   ldr      r1, [r5, #0x48]
c031c01c  010b51e3   cmp      r1, #0x400
c031c020  0500009a   bls      #0xc031c03c
c031c024  480095e5   ldr      r0, [r5, #0x48]
c031c028  48109de5   ldr      r1, [sp, #0x48]
c031c02c  a020a0e1   lsr      r2, r0, #1
c031c030  011582e0   add      r1, r2, r1, lsl #10
c031c034  11f031e7   udiv     r1, r1, r0
c031c038  48108de5   str      r1, [sp, #0x48]
c031c03c  4c1095e5   ldr      r1, [r5, #0x4c]
c031c040  010b51e3   cmp      r1, #0x400
c031c044  0500009a   bls      #0xc031c060
c031c048  4c0095e5   ldr      r0, [r5, #0x4c]
c031c04c  4c109de5   ldr      r1, [sp, #0x4c]
c031c050  a020a0e1   lsr      r2, r0, #1
c031c054  011582e0   add      r1, r2, r1, lsl #10
c031c058  11f031e7   udiv     r1, r1, r0
c031c05c  4c108de5   str      r1, [sp, #0x4c]
c031c060  002095e5   ldr      r2, [r5]
c031c064  48109de5   ldr      r1, [sp, #0x48]
c031c068  020051e1   cmp      r1, r2
c031c06c  0500009a   bls      #0xc031c088
c031c070  002095e5   ldr      r2, [r5]
c031c074  48109de5   ldr      r1, [sp, #0x48]
c031c078  021041e0   sub      r1, r1, r2
c031c07c  2111a0e1   lsr      r1, r1, #2
c031c080  8110a0e1   lsl      r1, r1, #1
c031c084  50108de5   str      r1, [sp, #0x50]
c031c088  042095e5   ldr      r2, [r5, #4]
c031c08c  4c109de5   ldr      r1, [sp, #0x4c]
c031c090  020051e1   cmp      r1, r2
c031c094  0500009a   bls      #0xc031c0b0
c031c098  042095e5   ldr      r2, [r5, #4]
c031c09c  4c109de5   ldr      r1, [sp, #0x4c]
c031c0a0  021041e0   sub      r1, r1, r2
c031c0a4  2111a0e1   lsr      r1, r1, #2
c031c0a8  8110a0e1   lsl      r1, r1, #1
c031c0ac  54108de5   str      r1, [sp, #0x54]
c031c0b0  260600eb   bl       #0xc031d950
c031c0b4  00b0a0e1   mov      fp, r0
c031c0b8  d81700eb   bl       #0xc0322020
c031c0bc  fc10d0e5   ldrb     r1, [r0, #0xfc]
c031c0c0  000051e3   cmp      r1, #0
c031c0c4  0b00001a   bne      #0xc031c0f8
c031c0c8  501095e5   ldr      r1, [r5, #0x50]
c031c0cc  000051e3   cmp      r1, #0
c031c0d0  54109505   ldreq    r1, [r5, #0x54]
c031c0d4  00005103   cmpeq    r1, #0
c031c0d8  0400001a   bne      #0xc031c0f0
c031c0dc  481095e5   ldr      r1, [r5, #0x48]
c031c0e0  010b51e3   cmp      r1, #0x400
c031c0e4  4c109595   ldrls    r1, [r5, #0x4c]
c031c0e8  010b5193   cmpls    r1, #0x400
c031c0ec  0100009a   bls      #0xc031c0f8
c031c0f0  0b00a0e1   mov      r0, fp
c031c0f4  230600eb   bl       #0xc031d988
c031c0f8  001095e5   ldr      r1, [r5]
c031c0fc  44009de5   ldr      r0, [sp, #0x44]
c031c100  041080e5   str      r1, [r0, #4]
c031c104  041095e5   ldr      r1, [r5, #4]
c031c108  44009de5   ldr      r0, [sp, #0x44]
c031c10c  081080e5   str      r1, [r0, #8]
c031c110  201096e5   ldr      r1, [r6, #0x20]
c031c114  44009de5   ldr      r0, [sp, #0x44]
c031c118  0c1080e5   str      r1, [r0, #0xc]
c031c11c  28009de5   ldr      r0, [sp, #0x28]
c031c120  1cf8ffeb   bl       #0xc031a198
c031c124  44109de5   ldr      r1, [sp, #0x44]
c031c128  100081e5   str      r0, [r1, #0x10]
c031c12c  0700a0e1   mov      r0, r7
c031c130  72f7ffeb   bl       #0xc0319f00
c031c134  301096e5   ldr      r1, [r6, #0x30]
c031c138  000051e1   cmp      r1, r0
