00000000 push {r4, r6, r7, lr}
00000002 add r7, sp, #8
00000004 mov r4, sp
00000006 bfc r4, #0, #2
0000000a mov sp, r4
0000000c movw r0, #0x7cd0
00000010 sub.w r4, r7, #8
00000014 movt r0, #0xa
00000018 mov sp, r4
0000001a pop {r4, r6, r7, pc}
0000001c cmp r1, #0
0000001e it eq
00000020 bxeq lr
00000022 push {r4, r6, r7, lr}
00000024 add r7, sp, #8
00000026 mov r4, sp
00000028 bfc r4, #0, #2
0000002c mov sp, r4
0000002e movs r2, #0
00000030 strb r2, [r0], #1
00000034 subs r1, #1
00000036 bne #0x30
00000038 sub.w r4, r7, #8
0000003c mov sp, r4
0000003e pop.w {r4, r6, r7, lr}
00000042 bx lr
00000044 cmp r1, #0
00000046 itt eq
00000048 moveq r0, #1
0000004a bxeq lr
0000004c push {r4, r6, r7, lr}
0000004e add r7, sp, #8
00000050 mov r4, sp
00000052 bfc r4, #0, #2
00000056 mov sp, r4
00000058 ldrb r2, [r0], #1
0000005c cbnz r2, #0x66
0000005e subs r1, #1
00000060 bne #0x58
00000062 movs r0, #1
00000064 b #0x68
00000066 movs r0, #0
00000068 sub.w r4, r7, #8
0000006c mov sp, r4
0000006e pop {r4, r6, r7, pc}
00000070 push {r4, r6, r7, lr}
00000072 add r7, sp, #8
00000074 mov r4, sp
00000076 bfc r4, #0, #2
0000007a mov sp, r4
0000007c lsrs r2, r1, #2
0000007e cmp r1, #0x20
00000080 blo #0x9e
00000082 movs r1, #0
00000084 subs r2, #8
00000086 str r1, [r0, #8]
00000088 str r1, [r0, #0xc]
0000008a cmp r2, #7
0000008c str r1, [r0, #4]
0000008e str r1, [r0, #0x1c]
00000090 str r1, [r0]
00000092 str r1, [r0, #0x18]
00000094 str r1, [r0, #0x14]
00000096 str r1, [r0, #0x10]
00000098 add.w r0, r0, #0x20
0000009c bhi #0x84
0000009e cbz r2, #0xaa
000000a0 movs r1, #0
000000a2 str r1, [r0], #4
000000a6 subs r2, #1
000000a8 bne #0xa2
000000aa sub.w r4, r7, #8
000000ae mov sp, r4
000000b0 pop {r4, r6, r7, pc}
000000b2 push {r4, r5, r6, r7, lr}
000000b4 add r7, sp, #0xc
000000b6 sub sp, #4
000000b8 mov r4, sp
000000ba bfc r4, #0, #2
000000be mov sp, r4
000000c0 cmp r1, #0x20
000000c2 blo #0xf6
000000c4 lsrs r2, r1, #2
000000c6 mov r3, r0
000000c8 ldr.w ip, [r3]
000000cc ldr.w lr, [r3, #4]
000000d0 ldr r6, [r3, #8]
000000d2 ldr r5, [r3, #0xc]
000000d4 orr.w r4, lr, ip
000000d8 orrs r6, r4
000000da orrs r6, r5
000000dc ldr r5, [r3, #0x10]
000000de orrs r6, r5
000000e0 ldr r5, [r3, #0x14]
000000e2 orrs r6, r5
000000e4 ldr r5, [r3, #0x18]
000000e6 orrs r6, r5
000000e8 ldr r5, [r3, #0x1c]
000000ea orrs r6, r5
000000ec bne #0x106
000000ee subs r2, #8
000000f0 adds r3, #0x20
000000f2 cmp r2, #7
000000f4 bhi #0xc8
000000f6 ubfx r2, r1, #2, #3
000000fa cbz r2, #0x10e
000000fc bic r1, r1, #0x1f
00000100 add r0, r1
00000102 ldr r1, [r0]
00000104 cbz r1, #0x10a
00000106 movs r0, #0
00000108 b #0x110
0000010a cmp r2, #1
0000010c bne #0x118
0000010e movs r0, #1
00000110 sub.w r4, r7, #0xc
00000114 mov sp, r4
00000116 pop {r4, r5, r6, r7, pc}
00000118 ldr r1, [r0, #4]
0000011a cmp r1, #0
0000011c bne #0x106
0000011e cmp r2, #2
00000120 beq #0x10e
00000122 ldr r1, [r0, #8]
00000124 cmp r1, #0
00000126 bne #0x106
00000128 cmp r2, #3
0000012a beq #0x10e
0000012c ldr r1, [r0, #0xc]
0000012e cmp r1, #0
00000130 bne #0x106
00000132 cmp r2, #4
00000134 beq #0x10e
00000136 ldr r1, [r0, #0x10]
00000138 cmp r1, #0
0000013a bne #0x106
0000013c cmp r2, #5
0000013e beq #0x10e
00000140 ldr r1, [r0, #0x14]
00000142 cmp r1, #0
00000144 bne #0x106
00000146 cmp r2, #6
00000148 beq #0x10e
0000014a ldr r0, [r0, #0x18]
0000014c cmp r0, #0
0000014e bne #0x106
00000150 b #0x10e