	.syntax	unified
	.eabi_attribute	67, "2.09"	@ Tag_conformance
	.eabi_attribute	6, 10	@ Tag_CPU_arch
	.eabi_attribute	7, 65	@ Tag_CPU_arch_profile
	.eabi_attribute	8, 1	@ Tag_ARM_ISA_use
	.eabi_attribute	9, 2	@ Tag_THUMB_ISA_use
	.eabi_attribute	34, 1	@ Tag_CPU_unaligned_access
	.eabi_attribute	17, 1	@ Tag_ABI_PCS_GOT_use
	.eabi_attribute	20, 1	@ Tag_ABI_FP_denormal
	.eabi_attribute	21, 0	@ Tag_ABI_FP_exceptions
	.eabi_attribute	23, 3	@ Tag_ABI_FP_number_model
	.eabi_attribute	24, 1	@ Tag_ABI_align_needed
	.eabi_attribute	25, 1	@ Tag_ABI_align_preserved
	.eabi_attribute	38, 1	@ Tag_ABI_FP_16bit_format
	.eabi_attribute	18, 4	@ Tag_ABI_PCS_wchar_t
	.eabi_attribute	26, 2	@ Tag_ABI_enum_size
	.eabi_attribute	14, 0	@ Tag_ABI_PCS_R9_use
	.file	"af_sender.c"
	.text
	.globl	af_crc32                        @ -- Begin function af_crc32
	.p2align	2
	.type	af_crc32,%function
	.code	32
af_crc32:                               @ @af_crc32
	.fnstart
@ %bb.0:
	.save	{r4, lr}
	push	{r4, lr}
	ldr	lr, .LCPI0_0
	mov	r12, #0
	mvn	r2, #0
.LBB0_1:                                @ =>This Loop Header: Depth=1
                                        @     Child Loop BB0_3 Depth 2
	cmp	r12, r1
	beq	.LBB0_6
@ %bb.2:                                @   in Loop: Header=BB0_1 Depth=1
	ldrb	r3, [r0, r12]
	eor	r2, r2, r3
	mov	r3, #8
.LBB0_3:                                @   Parent Loop BB0_1 Depth=1
                                        @ =>  This Inner Loop Header: Depth=2
	cmp	r3, #0
	beq	.LBB0_5
@ %bb.4:                                @   in Loop: Header=BB0_3 Depth=2
	eor	r4, lr, r2, lsr #1
	tst	r2, #1
	lsreq	r4, r2, #1
	sub	r3, r3, #1
	mov	r2, r4
	b	.LBB0_3
.LBB0_5:                                @   in Loop: Header=BB0_1 Depth=1
	add	r12, r12, #1
	b	.LBB0_1
.LBB0_6:
	mvn	r0, r2
	pop	{r4, pc}
	.p2align	2
@ %bb.7:
.LCPI0_0:
	.long	3988292384                      @ 0xedb88320
.Lfunc_end0:
	.size	af_crc32, .Lfunc_end0-af_crc32
	.cantunwind
	.fnend
                                        @ -- End function
	.globl	af_ep83_completion_ok           @ -- Begin function af_ep83_completion_ok
	.p2align	2
	.type	af_ep83_completion_ok,%function
	.code	32
af_ep83_completion_ok:                  @ @af_ep83_completion_ok
	.fnstart
@ %bb.0:
	mov	r1, r0
	mov	r0, #0
	cmp	r1, #0
	beq	.LBB1_2
@ %bb.1:
	ldr	r2, [r1]
	cmp	r2, #0
	ldreq	r2, [r1, #4]
	cmpeq	r2, #0
	beq	.LBB1_3
.LBB1_2:
	bx	lr
.LBB1_3:
	ldr	r2, [r1, #8]
	cmp	r2, #0
	beq	.LBB1_2
@ %bb.4:
	ands	r3, r2, #15
	ldreq	r3, [r1, #12]
	cmpeq	r3, r2
	bne	.LBB1_2
@ %bb.5:
	ldr	r2, [r1, #16]
	cmp	r2, #0
	beq	.LBB1_2
@ %bb.6:
	ands	r3, r2, #63
	bne	.LBB1_2
@ %bb.7:
	ldr	r12, [r1, #20]
	adds	r3, r12, r2
	bxhs	lr
.LBB1_8:
	.save	{r11, lr}
	push	{r11, lr}
	movw	r3, #32897
	sub	lr, r12, r3
	movw	r3, #32895
	movt	r3, #65535
	cmp	lr, r3
	pop	{r11, lr}
	blo	.LBB1_2
@ %bb.9:
	ands	r3, r12, #127
	ldreq	r3, [r1, #24]
	cmpeq	r3, r2
	bne	.LBB1_2
@ %bb.10:
	ldr	r2, [r1, #28]
	cmp	r2, #0
	ldreq	r2, [r1, #32]
	cmpeq	r2, #0
	bne	.LBB1_2
@ %bb.11:
	ldr	r0, [r1, #36]
	movw	r1, #2066
	sub	r0, r0, r1
	clz	r0, r0
	lsr	r0, r0, #5
	bx	lr
.Lfunc_end1:
	.size	af_ep83_completion_ok, .Lfunc_end1-af_ep83_completion_ok
	.cantunwind
	.fnend
                                        @ -- End function
	.globl	af_tx_send                      @ -- Begin function af_tx_send
	.p2align	2
	.type	af_tx_send,%function
	.code	32
af_tx_send:                             @ @af_tx_send
	.fnstart
@ %bb.0:
	.save	{r4, r5, r6, r7, r8, r9, r10, r11, lr}
	push	{r4, r5, r6, r7, r8, r9, r10, r11, lr}
	.pad	#52
	sub	sp, sp, #52
	mov	r6, r0
	mvn	r0, #0
	cmp	r6, #0
	beq	.LBB2_2
@ %bb.1:
	cmp	r1, #0
	mov	r4, r1
	movne	r8, r2
	cmpne	r2, #0
	bne	.LBB2_3
.LBB2_2:
	add	sp, sp, #52
	pop	{r4, r5, r6, r7, r8, r9, r10, r11, pc}
.LBB2_3:
	ldr	r1, [r4]
	mvn	r0, #1
	cmp	r1, #0
	bne	.LBB2_2
@ %bb.4:
	ldr	r0, [r6]
	add	r3, sp, #28
	ldr	r1, [r6, #4]
	ldr	r2, [r6, #8]
	stm	r3!, {r0, r1, r2}
	mov	r0, #64
	str	r0, [sp, #4]
	mov	r0, #24
	ldr	r7, [r6, #12]
	ldr	r3, [r6, #16]
	ldr	r11, [r6, #24]
	str	r0, [sp, #24]
	mov	r0, #32
	str	r0, [sp, #20]
	cmp	r11, #0
	str	r0, [sp, #16]
	mvn	r0, #0
	str	r8, [sp, #48]
	str	r4, [sp, #44]
	str	r6, [sp, #40]
	str	r7, [sp, #8]
	str	r3, [sp, #12]
	beq	.LBB2_2
@ %bb.5:
	ldr	r1, [r6, #28]
	movw	r5, #2001
	sub	r1, r1, r5
	cmn	r1, #2000
	blo	.LBB2_2
@ %bb.6:
	movw	r1, #32769
	sub	r1, r7, r1
	cmn	r1, #32768
	blo	.LBB2_2
@ %bb.7:
	ands	r1, r7, #127
	bne	.LBB2_2
@ %bb.8:
	movw	r1, #32896
	cmp	r3, r1
	bhi	.LBB2_2
@ %bb.9:
	add	r1, r7, #128
	cmp	r3, r1
	blo	.LBB2_2
@ %bb.10:
	ldr	r7, [r6, #20]
	rsb	r1, r7, #0
	cmp	r3, r1
	bhs	.LBB2_2
@ %bb.11:
	ands	r1, r7, #63
	andseq	r1, r2, #63
	bne	.LBB2_2
@ %bb.12:
	ldr	r12, [r8, #4]
	cmp	r12, #0
	beq	.LBB2_2
@ %bb.13:
	ldr	r1, [r8, #8]
	cmp	r1, #0
	ldrne	r1, [r8, #12]
	cmpne	r1, #0
	beq	.LBB2_2
@ %bb.14:
	ldr	r1, [r8, #16]
	cmp	r1, #0
	ldrne	r1, [r8, #20]
	cmpne	r1, #0
	beq	.LBB2_2
@ %bb.15:
	add	lr, sp, #28
	add	r1, sp, #4
	mov	r10, #0
	b	.LBB2_21
.LBB2_16:                               @   in Loop: Header=BB2_21 Depth=1
	add	r2, r2, r9
	mov	r7, #0
.LBB2_17:                               @   Parent Loop BB2_21 Depth=1
                                        @ =>  This Inner Loop Header: Depth=2
	cmp	r10, r7
	beq	.LBB2_20
@ %bb.18:                               @   in Loop: Header=BB2_17 Depth=2
	ldr	r5, [lr, r7, lsl #2]
	ldr	r3, [r1, r7, lsl #2]
	add	r7, r7, #1
	cmp	r2, r5
	add	r3, r3, r5
	bls	.LBB2_17
@ %bb.19:                               @   in Loop: Header=BB2_17 Depth=2
	cmp	r3, r9
	bls	.LBB2_17
	b	.LBB2_2
.LBB2_20:                               @   in Loop: Header=BB2_21 Depth=1
	add	r10, r10, #1
.LBB2_21:                               @ =>This Loop Header: Depth=1
                                        @     Child Loop BB2_17 Depth 2
	cmp	r10, #6
	beq	.LBB2_24
@ %bb.22:                               @   in Loop: Header=BB2_21 Depth=1
	ldr	r9, [lr, r10, lsl #2]
	ldr	r2, [r1, r10, lsl #2]
	adds	r3, r2, r9
	bhs	.LBB2_2
@ %bb.23:                               @   in Loop: Header=BB2_21 Depth=1
	cmp	r9, #0
	cmpne	r2, #0
	beq	.LBB2_2
	b	.LBB2_16
.LBB2_24:
	mov	r0, #0
	mov	r7, #1
	str	r0, [r4, #20]
	mov	r1, r6
	str	r0, [r4, #16]
	str	r0, [r4, #12]
	str	r0, [r4, #28]
	str	r0, [r4, #8]
	str	r0, [r4, #24]
	ldr	r0, [r8]
	str	r7, [r4]
	str	r11, [r4, #4]
	blx	r12
	cmp	r0, #1
	bne	.LBB2_30
@ %bb.25:
	ldr	r11, [r6, #12]
	ldr	r0, [r6]
	ldr	r2, [r6, #24]
	lsr	r5, r11, #7
	str	r7, [r4, #28]
	mov	r1, r5
	bl	header_valid
	cmp	r0, #0
	beq	.LBB2_45
@ %bb.26:
	ldr	r0, [r6, #4]
	mov	r1, r5
	ldr	r2, [r6, #24]
	bl	records_valid
	cmp	r0, #0
	beq	.LBB2_45
@ %bb.27:
	ldr	r7, [r6, #8]
	mov	r0, #0
	mov	r1, #0
.LBB2_28:                               @ =>This Inner Loop Header: Depth=1
	cmp	r1, #64
	beq	.LBB2_31
@ %bb.29:                               @   in Loop: Header=BB2_28 Depth=1
	strb	r0, [r7, r1]
	add	r1, r1, #1
	b	.LBB2_28
.LBB2_30:
	str	r0, [r4, #20]
	mvn	r0, #2
	b	.LBB2_46
.LBB2_31:
	add	r9, r7, #64
	mov	r0, #0
.LBB2_32:                               @ =>This Inner Loop Header: Depth=1
	cmp	r0, #64
	beq	.LBB2_34
@ %bb.33:                               @   in Loop: Header=BB2_32 Depth=1
	ldr	r2, [r6]
	add	r1, r7, r0
	ldrb	r2, [r2, r0]
	add	r0, r0, #1
	strb	r2, [r1, #64]
	b	.LBB2_32
.LBB2_34:
	add	r10, r7, #128
	mov	r0, #0
.LBB2_35:                               @ =>This Inner Loop Header: Depth=1
	ldr	r1, [r6, #12]
	cmp	r0, r1
	bhs	.LBB2_37
@ %bb.36:                               @   in Loop: Header=BB2_35 Depth=1
	ldr	r2, [r6, #4]
	add	r1, r7, r0
	ldrb	r2, [r2, r0]
	add	r0, r0, #1
	strb	r2, [r1, #128]
	b	.LBB2_35
.LBB2_37:
	ldr	r2, [r6, #24]
	mov	r0, r9
	mov	r1, r5
	bl	header_valid
	cmp	r0, #0
	beq	.LBB2_45
@ %bb.38:
	ldr	r2, [r6, #24]
	mov	r0, r10
	mov	r1, r5
	bl	records_valid
	cmp	r0, #0
	beq	.LBB2_45
@ %bb.39:
	ldr	r0, [r6]
	mov	r1, #0
.LBB2_40:                               @ =>This Inner Loop Header: Depth=1
	cmp	r1, #64
	beq	.LBB2_42
@ %bb.41:                               @   in Loop: Header=BB2_40 Depth=1
	add	r2, r7, r1
	ldrb	r2, [r2, #64]
	ldrb	r3, [r0, r1]
	add	r1, r1, #1
	cmp	r2, r3
	bne	.LBB2_45
	b	.LBB2_40
.LBB2_42:
	ldr	r10, [r6, #12]
	mov	r0, #0
.LBB2_43:                               @ =>This Inner Loop Header: Depth=1
	cmp	r10, r0
	beq	.LBB2_48
@ %bb.44:                               @   in Loop: Header=BB2_43 Depth=1
	ldr	r2, [r6, #4]
	add	r1, r7, r0
	ldrb	r1, [r1, #128]
	ldrb	r2, [r2, r0]
	add	r0, r0, #1
	cmp	r1, r2
	beq	.LBB2_43
.LBB2_45:
	mov	r0, #0
	str	r0, [r4, #20]
	mvn	r0, #3
.LBB2_46:
	str	r0, [r4, #16]
	mov	r1, #5
.LBB2_47:
	str	r1, [r4]
	b	.LBB2_2
.LBB2_48:
	mov	r0, #64
	add	r1, r10, #64
	str	r0, [r7, #8]
	mov	r0, #1
	str	r0, [r7, #4]
	lsr	r2, r1, #24
	ldr	r0, .LCPI2_0
	str	r0, [r7]
	ldr	r0, [r6, #24]
	strb	r2, [r7, #27]
	lsr	r2, r1, #16
	strb	r2, [r7, #26]
	lsr	r2, r1, #8
	strb	r2, [r7, #25]
	mov	r2, #128
	str	r2, [r7, #20]
	lsr	r2, r11, #31
	strb	r2, [r7, #19]
	lsr	r2, r11, #23
	strb	r2, [r7, #18]
	lsr	r2, r11, #15
	strb	r2, [r7, #17]
	lsr	r2, r0, #24
	strb	r2, [r7, #15]
	lsr	r2, r0, #16
	strb	r0, [r7, #12]
	lsr	r0, r0, #8
	strb	r0, [r7, #13]
	mov	r0, r9
	strb	r1, [r7, #24]
	strb	r5, [r7, #16]
	strb	r2, [r7, #14]
	bl	af_crc32
	mov	r1, #1
	strb	r0, [r7, #28]
	str	r1, [r7, #32]
	lsr	r1, r0, #24
	strb	r1, [r7, #31]
	lsr	r1, r0, #16
	lsr	r0, r0, #8
	strb	r1, [r7, #30]
	strb	r0, [r7, #29]
	mov	r0, r7
	mov	r1, #64
	mov	r9, #1
	bl	af_crc32
	add	r5, r10, #128
	str	r0, [r7, #36]
	mov	r0, r7
	str	r5, [r4, #8]
	mov	r1, r5
	bl	af_crc32
	str	r0, [r4, #12]
	mov	r0, #2
	str	r0, [r4]
	mov	r1, r7
	ldr	r0, [r8]
	mov	r2, r5
	ldr	r3, [r8, #8]
	blx	r3
	cmp	r0, #1
	bne	.LBB2_51
@ %bb.49:
	mov	r0, #0
	ldr	r2, [r6, #20]
	str	r0, [r4, #28]
	mov	r0, #3
	str	r0, [r4]
	mov	r1, #7
	ldr	r0, [r8]
	mov	r3, r5
	ldr	r7, [r8, #12]
	str	r9, [r4, #24]
	blx	r7
	cmp	r0, #0
	beq	.LBB2_52
@ %bb.50:
	str	r0, [r4, #20]
	mvn	r0, #5
	b	.LBB2_57
.LBB2_51:
	str	r0, [r4, #20]
	mvn	r0, #4
	b	.LBB2_46
.LBB2_52:
	ldr	r2, [r6, #28]
	mov	r1, #3
	ldr	r0, [r8]
	ldr	r3, [r8, #16]
	blx	r3
	cmp	r0, #0
	beq	.LBB2_54
@ %bb.53:
	str	r0, [r4, #20]
	mvn	r0, #6
	b	.LBB2_57
.LBB2_54:
	ldr	r1, [r6, #24]
	mov	r2, r5
	ldr	r0, [r8]
	ldr	r3, [r8, #20]
	blx	r3
	cmp	r0, #1
	bne	.LBB2_56
@ %bb.55:
	mov	r0, #1
	mov	r1, #4
	str	r0, [r4, #28]
	mov	r0, #0
	str	r0, [r4, #24]
	b	.LBB2_47
.LBB2_56:
	str	r0, [r4, #20]
	mvn	r0, #7
.LBB2_57:
	str	r0, [r4, #16]
	mov	r1, #6
	b	.LBB2_47
	.p2align	2
@ %bb.58:
.LCPI2_0:
	.long	826426945                       @ 0x31424641
.Lfunc_end2:
	.size	af_tx_send, .Lfunc_end2-af_tx_send
	.cantunwind
	.fnend
                                        @ -- End function
	.p2align	2                               @ -- Begin function header_valid
	.type	header_valid,%function
	.code	32
header_valid:                           @ @header_valid
	.fnstart
@ %bb.0:
	.save	{r4, r5, r6, r7, r11, lr}
	push	{r4, r5, r6, r7, r11, lr}
	mov	r7, r2
	mov	r6, r1
	mov	r5, r0
	bl	rd
	ldr	r1, .LCPI3_0
	mov	r4, #0
	cmp	r0, r1
	bne	.LBB3_13
@ %bb.1:
	add	r0, r5, #4
	bl	rd
	cmp	r0, #1
	bne	.LBB3_13
@ %bb.2:
	add	r0, r5, #8
	bl	rd
	cmp	r0, #128
	bne	.LBB3_13
@ %bb.3:
	add	r0, r5, #12
	bl	rd
	cmp	r0, r6
	bne	.LBB3_13
@ %bb.4:
	add	r0, r5, #16
	bl	rd
	cmp	r0, r7
	bne	.LBB3_13
@ %bb.5:
	add	r0, r5, #20
	bl	rd
	cmp	r0, #0
	bne	.LBB3_13
@ %bb.6:
	add	r0, r5, #24
	bl	rd
	cmp	r0, r6
	bne	.LBB3_13
@ %bb.7:
	add	r0, r5, #28
	bl	rd
	cmp	r0, #1
	bne	.LBB3_13
@ %bb.8:
	add	r0, r5, #32
	bl	rd
	ldr	r6, .LCPI3_1
	cmp	r0, r6
	bne	.LBB3_13
@ %bb.9:
	add	r0, r5, #36
	bl	rd
	ldr	r1, .LCPI3_2
	cmp	r0, r1
	bne	.LBB3_13
@ %bb.10:
	add	r0, r5, #40
	bl	rd
	add	r1, r6, #4
	cmp	r0, r1
	bne	.LBB3_13
@ %bb.11:
	add	r0, r5, #44
	bl	rd
	cmp	r0, #64
	bne	.LBB3_13
@ %bb.12:
	add	r0, r5, #48
	bl	rd
	mov	r4, r0
	add	r0, r5, #52
	bl	rd
	orr	r4, r0, r4
	add	r0, r5, #56
	bl	rd
	orr	r4, r4, r0
	add	r0, r5, #60
	bl	rd
	orr	r0, r4, r0
	clz	r0, r0
	lsr	r4, r0, #5
.LBB3_13:
	mov	r0, r4
	pop	{r4, r5, r6, r7, r11, pc}
	.p2align	2
@ %bb.14:
.LCPI3_0:
	.long	826689601                       @ 0x31464841
.LCPI3_1:
	.long	3223504984                      @ 0xc022c858
.LCPI3_2:
	.long	3223579088                      @ 0xc023e9d0
.Lfunc_end3:
	.size	header_valid, .Lfunc_end3-header_valid
	.cantunwind
	.fnend
                                        @ -- End function
	.p2align	2                               @ -- Begin function records_valid
	.type	records_valid,%function
	.code	32
records_valid:                          @ @records_valid
	.fnstart
@ %bb.0:
	.save	{r4, r5, r6, r7, r8, r9, r10, lr}
	push	{r4, r5, r6, r7, r8, r9, r10, lr}
	mov	r9, r2
	mov	r10, r1
	mov	r7, r0
	mov	r6, #0
	mvn	r8, #1
.LBB4_1:                                @ =>This Inner Loop Header: Depth=1
	mov	r5, r6
	cmp	r6, r10
	beq	.LBB4_6
@ %bb.2:                                @   in Loop: Header=BB4_1 Depth=1
	mov	r0, r7
	bl	rd
	mov	r6, r0
	add	r0, r5, #1
	cmp	r6, r0
	bne	.LBB4_6
@ %bb.3:                                @   in Loop: Header=BB4_1 Depth=1
	add	r7, r7, #4
	mov	r0, r7
	bl	rd
	cmp	r0, r9
	bne	.LBB4_6
@ %bb.4:                                @   in Loop: Header=BB4_1 Depth=1
	add	r7, r7, #4
	mov	r0, r7
	bl	rd
	cmp	r0, r6
	bne	.LBB4_6
@ %bb.5:                                @   in Loop: Header=BB4_1 Depth=1
	add	r0, r7, #116
	sub	r4, r8, r5
	bl	rd
	add	r7, r7, #120
	cmp	r0, r4
	beq	.LBB4_1
.LBB4_6:
	mov	r0, #0
	cmp	r5, r10
	movwhs	r0, #1
	pop	{r4, r5, r6, r7, r8, r9, r10, pc}
.Lfunc_end4:
	.size	records_valid, .Lfunc_end4-records_valid
	.cantunwind
	.fnend
                                        @ -- End function
	.p2align	2                               @ -- Begin function rd
	.type	rd,%function
	.code	32
rd:                                     @ @rd
	.fnstart
@ %bb.0:
	ldrb	r1, [r0]
	ldrb	r2, [r0, #1]
	orr	r1, r1, r2, lsl #8
	ldrb	r2, [r0, #2]
	ldrb	r0, [r0, #3]
	orr	r1, r1, r2, lsl #16
	orr	r0, r1, r0, lsl #24
	bx	lr
.Lfunc_end5:
	.size	rd, .Lfunc_end5-rd
	.cantunwind
	.fnend
                                        @ -- End function
	.ident	"Apple clang version 21.0.0 (clang-2100.3.27.1)"
	.section	".note.GNU-stack","",%progbits
	.addrsig
	.eabi_attribute	30, 4	@ Tag_ABI_optimization_goals
