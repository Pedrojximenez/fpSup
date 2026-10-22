/* Native UI extension. Included in the resident's ARM text section. */
.align 2
.thumb
ui_load:
 bx pc
 nop
.arm
 push {r4-r8,lr}
 mov r4,r0
 mov r5,r1
 self ip,ui_load_original
 add ip,ip,#1
 blx ip
 mov r6,r0
 cmp r6,#0
 bne ui_load_done
 addr r0,0xC0D22400
 cmp r5,r0
 bne ui_load_done
 mov r0,r4
 bl ensure_ui_pack
ui_load_done:
 mov r0,r6
 pop {r4-r8,pc}
/* Also called from NBU parsing if stock resources predate AutoRun. */
ensure_ui_pack:
 push {r4-r6,lr}
 mov r4,r0
 addr r5,STATE
 ldr r1,[r5,#36]
 cmp r1,r4
 bne ensure_ui_new
 ldr r0,[r5,#40]
 cmp r0,#0
 bne ensure_ui_result
ensure_ui_new:
 str r4,[r5,#36]
 mov r0,#2
 str r0,[r5,#40]
 mov r0,r4
 self r1,ui_pack
 movw r2, #:lower16:(ui_pack_end-ui_pack)
 mov r3,#0
 self ip,ui_load_original
 add ip,ip,#1
 blx ip
 str r0,[r5,#44]
 cmp r0,#0
 moveq r0,#1
 movne r0,#3
 str r0,[r5,#40]
ensure_ui_result:
 cmp r0,#1
 moveq r0,#1
 movne r0,#0
 pop {r4-r6,pc}
.align 2
.thumb
ui_load_original:
 push {lr}
 sub sp,#24
 movw ip,#0x84dd
 movt ip,#0xc05e
 bx ip
.align 2
ui_string:
 bx pc
 nop
.arm
 cmp r1,#0xfffffff0
 blo ui_string_stock
 cmp r1,#0xfffffff6
 bhi ui_string_stock
 ldr ip,[r0,#20]
 push {r2,lr}
 addr r2,0xC18C0474
 cmp ip,r2
 pop {r2,lr}
 bne ui_string_stock
 add r1,r1,#16
 self ip,ui_aliases
 ldr r0,[ip,r1,lsl #2]
 bx lr
ui_string_stock:
 self ip,ui_string_original
 add ip,ip,#1
 bx ip
.align 2
.thumb
ui_string_original:
 cmp.w r1,#-1
 movw ip,#0x5b5d
 movt ip,#0xc05e
 bx ip
.align 2
ui_record:
 bx pc
 nop
.arm
 push {r4-r11,lr}
 sub sp,sp,#4
 mov r4,r0
 ldr r5,[r4,#36]
 addr r6,0xC18C0460
 cmp r5,r6
 bne ui_record_stock
 /* Diagnostic only: distinguish QS records arriving after installation from
  * records actually extended. Bits0/1 are limits; bits2/3 are footer clips. */
 ldr r0,[r4,#4]
 add r0,r5,r0
 mov r1,#48
 bl ui_trace_qs
 ldr r0,[r4,#8]
 bl ensure_ui_pack
 cmp r0,#1
 bne ui_record_stock
 ldr r7,[r4,#4]
 add r8,r5,r7
 self r9,ui_records
 mov r10,#0
 movw r11, #:lower16:UI_RECORD_COUNT
ui_record_find:
 cmp r10,r11
 bhs ui_record_stock
 add r0,r10,r11
 lsr r0,r0,#1
 add r1,r0,r0,lsl #1
 add r1,r9,r1,lsl #2
 ldr r2,[r1]
 cmp r8,r2
 beq ui_record_found
 addhi r10,r0,#1
 movlo r11,r0
 b ui_record_find
ui_record_found:
 mov r9,r1
 ldr r10,[r9,#4]
 ubfx r10,r10,#0,#10
 mov r0,r8
 mov r1,r10
 addr r2,0x811c9dc5
 addr r3,0x01000193
ui_record_hash:
 ldrb ip,[r0],#1
 eor r2,r2,ip
 mul r2,r3,r2
 subs r1,r1,#1
 bne ui_record_hash
 ldr r0,[r9,#8]
 cmp r2,r0
 bne ui_record_stock
 mov r0,r8
 mov r1,#52
 bl ui_trace_qs
 /* One bounded stack copy; original input and pool remain immutable. */
 sub sp,sp,#512
 ldr r6,[r9,#4]
 ubfx r6,r6,#10,#3
 cmp r6,#4
 beq ui_literal_delta
 cmp r6,#2
 bhs ui_replace_word
 cmp r6,#1
 beq ui_layout_copy
 mov r11,#32
 mov r0,r8
 mov r1,sp
 mov r2,r11
ui_copy_prefix:
 ldrb r3,[r0],#1
 strb r3,[r1],#1
 subs r2,r2,#1
 bne ui_copy_prefix
 mov r6,#0
 cmp r6,#0
 beq ui_insert_limit
 mov r2,#0
 strb r2,[r1],#1
 strb r2,[r1],#1
 strb r2,[r1],#1
 strb r2,[r1],#1
 strb r2,[r1],#1
 lsr r2,r6,#24
 strb r2,[r1],#1
 /* Synthetic string offset fffffff0..f5, resolved by ui_string. */
 mvn r2,#0
 strb r2,[r1],#1
 strb r2,[r1],#1
 strb r2,[r1],#1
 strb r6,[r1],#1
 mov r6,#10
 b ui_copy_tail
ui_insert_limit:
 mov r2,#0x40
 strb r2,[r1],#1
 mov r2,#0
 strb r2,[r1],#1
 strb r2,[r1],#1
 strb r2,[r1],#1
 mov r6,#4
ui_copy_tail:
 sub r2,r10,r11
 cmp r2,#0
 beq ui_copy_done
ui_copy_tail_loop:
 ldrb r3,[r0],#1
 strb r3,[r1],#1
 subs r2,r2,#1
 bne ui_copy_tail_loop
ui_copy_done:
 add r0,r10,r6
 rev r0,r0
 str r0,[sp,#4]
 mov r1,#31
 cmp r6,#4
 moveq r0,#0x1a
 beq ui_count_store
 ldrb r0,[sp,r1]
 add r0,r0,#1
ui_count_store:
 strb r0,[sp,r1]
ui_copy_parse:
 /* The reader uses base+position. Keep positions and string-pool identity. */
 sub r0,sp,r7
 str r0,[r4,#36]
 mov r0,r4
 self ip,ui_record_original
 add ip,ip,#1
 blx ip
 str r5,[r4,#36]
 add r1,r7,r10
 str r1,[r4,#4]
 add sp,sp,#512
 b ui_record_return
/* Fixed-size record correction: timeline endpoint or summary text. */
ui_replace_word:
 mov r0,r8
 mov r1,sp
 mov r2,r10
1: ldrb r3,[r0],#1
 strb r3,[r1],#1
 subs r2,r2,#1
 bne 1b
 mov r1,#32
 mvn r0,#9
 cmp r6,#3
 beq 2f
 mov r1,#36
 ldr r0,[r9,#4]
 ubfx r0,r0,#13,#7
2: rev r0,r0
 str r0,[sp,r1]
 b ui_copy_parse
/* Clone each UHD property key into the private state. This keeps companion
 * visibility, positions and image rectangles synchronized with the badge. */
ui_layout_copy:
 mov r0,r8
 mov r1,sp
 mov r2,#28
1: ldrb r3,[r0],#1
 strb r3,[r1],#1
 subs r2,r2,#1
 bne 1b
 ldr r11,[sp,#12]
 rev r11,r11
 mov r6,#1
ui_layout_property:
 ldr ip,[r9,#4]
 ubfx r2,ip,#13,#7
 mov r3,#0
 ubfx ip,ip,#20,#4
 cmp ip,r6
 bne 2f
 ldr r3,[r9,#4]
 lsr r3,r3,#24
 sub r3,r3,#256
2: bl ui_clone_property
 add r6,r6,#1
 subs r11,r11,#1
 bne ui_layout_property
 sub r2,r1,sp
 rev r2,r2
 str r2,[sp,#4]
 b ui_copy_parse
ui_literal_delta:
 mov r0,r8
 mov r1,sp
 self r2,ui_edits
 ldr r3,[r9,#4]
 add r2,r2,r3,lsr #13
 mov r3,r10
 bl ui_apply_delta
 b ui_copy_parse
/* Bounded immutable edit recipes, checked by source FNV before entry. */
ui_apply_delta:
 push {r4-r8,lr}
 mov r4,r0
 add r5,r0,r3
 mov r6,r2
ui_delta_next:
 ldrh r7,[r6],#2
 movw r2,#65535
 cmp r7,r2
 beq ui_delta_tail
 ldrh r8,[r6],#2
 ldrh ip,[r6],#2
 add r3,r4,r7
 sub r3,r3,r0
 cmp r3,#0
 beq 2f
1: ldrb r2,[r0],#1
 strb r2,[r1],#1
 subs r3,r3,#1
 bne 1b
2: add r0,r0,r8
 cmp ip,#0
 beq 2f
1: ldrb r2,[r6],#1
 strb r2,[r1],#1
 subs ip,ip,#1
 bne 1b
2: add r6,r6,#1
 bic r6,r6,#1
 b ui_delta_next
ui_delta_tail:
 sub r3,r5,r0
 cmp r3,#0
 beq 2f
1: ldrb r2,[r0],#1
 strb r2,[r1],#1
 subs r3,r3,#1
 bne 1b
2: pop {r4-r8,pc}
/* r0/r1 input/output cursors; r2 time; r3 optional new string index.
 * Return advanced cursors. Exact firmware-record hash bounds all counts. */
ui_clone_property:
 push {r4-r8,lr}
 mov r4,r2
 mov r5,r3
 ldr r6,[r0]
 rev r6,r6
 add r7,r0,#20
 mov r8,r1
 mov r2,#20
1: ldrb r3,[r0],#1
 strb r3,[r1],#1
 subs r2,r2,#1
 bne 1b
 add r2,r6,#1
 strb r2,[r8,#3]
 add r2,r6,r6,lsl #2
 lsl r2,r2,#1
1: ldrb r3,[r0],#1
 strb r3,[r1],#1
 subs r2,r2,#1
 bne 1b
 mov r8,r1
 mov r2,#10
1: ldrb r3,[r7],#1
 strb r3,[r1],#1
 subs r2,r2,#1
 bne 1b
 mov r2,#0
 strb r2,[r8,#2]
 strb r2,[r8,#3]
 strb r2,[r8,#4]
 strb r4,[r8,#5]
 cmp r5,#0
 beq 2f
 mov r2,#255
 strb r2,[r8,#6]
 strb r2,[r8,#7]
 strb r2,[r8,#8]
 strb r5,[r8,#9]
2:
 pop {r4-r8,pc}
ui_record_stock:
 mov r0,r4
 self ip,ui_record_original
 add ip,ip,#1
 blx ip
ui_record_return:
 add sp,sp,#4
 pop {r4-r11,pc}
.align 2
.thumb
ui_record_original:
 push.w {r4-r11,lr}
 movw ip,#0x6405
 movt ip,#0xc05e
 bx ip
.align 2
.arm

.macro hud_entry name,target,slot
\name:
 push {r4-r6,lr}
 mov r4,r0
 mov r5,r1
 addr r6,STATE
 str r4,[r6,#\slot]
 ldr r0,[r6,#16]
 cmp r0,#1
 cmpeq r5,#3
 bne \name\()_stock
 mov r0,r4
 self r1,lv_name
 mov r2,#3
 call 0xC0593F30
 pop {r4-r6,pc}
\name\()_stock:
 mov r0,r4
 mov r1,r5
 bl \name\()_original
 pop {r4-r6,pc}
\name\()_original:
 .word 0xe92d4070
 addr ip,(\target+4)
 bx ip
.endm
hud_entry hud_display_a,0xC059C640,28
hud_entry hud_display_b,0xC059C9F0,32
/* Two diagnostic bitmaps only; no UI, allocation or file calls. */
ui_trace_qs:
 push {r2,r3,ip,lr}
 mov r2,#0
 addr r3,0xC237249F
 cmp r0,r3
 orreq r2,r2,#1
 addr r3,0xC25E405A
 cmp r0,r3
 orreq r2,r2,#2
 addr r3,0xC23535A3
 cmp r0,r3
 orreq r2,r2,#4
 addr r3,0xC25B9EF1
 cmp r0,r3
 orreq r2,r2,#8
 cmp r2,#0
 beq ui_trace_done
 addr r3,STATE
 ldr ip,[r3,r1]
 orr ip,ip,r2
 str ip,[r3,r1]
ui_trace_done:
 pop {r2,r3,ip,pc}
lv_name: .asciz "LV_Resolution"
.align 2
ui_aliases:
.word BASE+(ui_name_l-menu_install),BASE+(ui_name_m-menu_install)
.word BASE+(ui_name_qs-menu_install),BASE+(ui_name_set-menu_install)
.word BASE+(ui_name_lh-menu_install),BASE+(ui_name_mh-menu_install)
.word BASE+(ui_summary_label-menu_install)
ui_summary_label: .asciz "3K"
ui_name_l: .asciz "FP3K_L"
ui_name_m: .asciz "FP3K_M"
ui_name_qs: .asciz "FP3K_QS"
ui_name_set: .asciz "FP3K_SET"
ui_name_lh: .asciz "FP3K_FONT"
ui_name_mh: .asciz "FP3K_MH"
.align 2
.include "tools/fp3k_native_ui_data.inc"
