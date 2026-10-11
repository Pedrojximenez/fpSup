/* Experimental native menu resident. Built/tested offline before camera demo.
 * Capture table changes use the stock interrupt-mask convention. No filesystem,
 * UI queue or settings calls are made inside the capture critical section.
 */
.syntax unified
.arm
.text
.global menu_install
.equ BASE, 0xC072DE64
.equ STATE, 0xC0732000
.equ MAGIC, 0x314D334B
.equ UI_RANGE, 0xC1A709BC
.equ UI_RANGE_STOCK, 0x0000803F
.equ UI_RANGE_THREE, 0x00000040
/* STATE: legacy fields0..24, HUD receivers28/32, UI context36, ready40, error44. */
.macro addr reg,value
 movw \reg, #:lower16:\value
 movt \reg, #:upper16:\value
.endm
.macro call target
 addr ip,\target
 blx ip
.endm
.macro self reg,label
 ldr \reg,90f
 b 91f
90: .word BASE+(\label-menu_install)
91:
.endm
.macro lock saved
 mrs \saved,cpsr
 orr ip,\saved,#0xc0
 msr cpsr_c,ip
.endm
.macro unlock saved
 mrs ip,cpsr
 bic ip,ip,#0xc0
 and \saved,\saved,#0xc0
 orr ip,ip,\saved
 msr cpsr_c,ip
.endm
menu_install:
 push {r4-r10,lr}
 addr r8,STATE
 /* Immutable file sum must be zero. */
 addr r0,BASE
 movw r2, #:lower16:((payload_end-menu_install)/4)
 mov r1,#0
1: ldr r3,[r0],#4
 add r1,r1,r3
 subs r2,r2,#1
 bne 1b
 cmp r1,#0
 bne install_bad
 lock r9
 self r4,hooks
 movw r5, #:lower16:HOOK_COUNT
2: ldm r4!,{r0-r2}
 ldr r3,[r0]
 cmp r3,r1
 bne install_mismatch
 subs r5,r5,#1
 bne 2b
 addr r0,UI_RANGE
 ldr r3,[r0]
 addr r1,UI_RANGE_STOCK
 cmp r3,r1
 bne install_mismatch
 addr r0,0xC0F8E7EC
 self r1,csv_stock
 mov r2,#89
3: ldrb r3,[r0],#1
 ldrb r6,[r1],#1
 cmp r3,r6
 bne install_mismatch
 subs r2,r2,#1
 bne 3b
 self r4,patch_table
 movw r5, #:lower16:PATCH_COUNT
4: ldm r4!,{r0-r2}
 ldr r3,[r0]
 cmp r3,r1
 bne install_mismatch
 subs r5,r5,#1
 bne 4b
 addr r0,MAGIC
 str r0,[r8]
 mov r0,#0
 str r0,[r8,#8]
 str r0,[r8,#12]
 str r0,[r8,#16]
 str r0,[r8,#20]
 str r0,[r8,#24]
 str r0,[r8,#28]
 str r0,[r8,#32]
 str r0,[r8,#36]
 str r0,[r8,#40]
 str r0,[r8,#44]
 str r0,[r8,#48]
 str r0,[r8,#56]
 str r0,[r8,#60]
 str r0,[r8,#52]
 /* Resources first, entry branches last, then native cache synchronization. */
 addr r0,UI_RANGE
 mov r1,#UI_RANGE_THREE
 str r1,[r0]
 addr r0,0xC0F8E7EC
 self r1,csv_new
 mov r2,#89
5: ldrb r3,[r1],#1
 strb r3,[r0],#1
 subs r2,r2,#1
 bne 5b
 self r4,hooks
 movw r5, #:lower16:HOOK_COUNT
6: ldm r4!,{r0-r2}
 str r2,[r0]
 subs r5,r5,#1
 bne 6b
 dsb sy
verify_install:
 addr r0,UI_RANGE
 ldr r3,[r0]
 cmp r3,#UI_RANGE_THREE
 bne install_rollback
 self r4,hooks
 movw r5, #:lower16:HOOK_COUNT
12: ldm r4!,{r0-r2}
 ldr r3,[r0]
 cmp r3,r2
 bne install_rollback
 subs r5,r5,#1
 bne 12b
 addr r0,0xC0F8E7EC
 self r1,csv_new
 mov r2,#89
13: ldrb r3,[r0],#1
 ldrb r6,[r1],#1
 cmp r3,r6
 bne install_rollback
 subs r2,r2,#1
 bne 13b
 call 0xC000E91C
 mov r0,#16
 str r0,[r8,#4]
 unlock r9
 pop {r4-r10,pc}
install_rollback:
 str r0,[r8,#8]
 str r3,[r8,#12]
 addr r0,UI_RANGE
 addr r1,UI_RANGE_STOCK
 str r1,[r0]
 self r4,hooks
 movw r5, #:lower16:HOOK_COUNT
14: ldm r4!,{r0-r2}
 str r1,[r0]
 subs r5,r5,#1
 bne 14b
 addr r0,0xC0F8E7EC
 self r1,csv_stock
 mov r2,#89
15: ldrb r3,[r1],#1
 strb r3,[r0],#1
 subs r2,r2,#1
 bne 15b
 dsb sy
 call 0xC000E91C
 unlock r9
 mov r0,#0x33
 str r0,[r8,#4]
 pop {r4-r10,pc}
install_mismatch:
 str r0,[r8,#8]
 str r3,[r8,#12]
 unlock r9
 mov r0,#0x31
 str r0,[r8,#4]
 pop {r4-r10,pc}
install_bad:
 mov r0,#0x32
 str r0,[r8,#4]
 pop {r4-r10,pc}

/* Native MV_Resolution callback: index2 is private and never becomes enum4. */
resolution_select:
 push {r4-r8,lr}
 mov r7,#0
 b select_begin
qs_resolution_select:
 push {r4-r8,lr}
 mov r7,#1
select_begin:
 ldr r4,[r0,#8]
 cmp r4,#2
 bhi select_refresh
 bl idle_check
 cmp r0,#0
 beq select_refresh
 cmp r4,#2
 bne select_stock
 /* A third choice is allowed only in the supported existing recording setup. */
 bl compatible
 cmp r0,#0
 beq select_refresh
 mov r0,#1
 bl transition
 cmp r0,#0
 beq select_refresh
 mov r5,#3
 b select_write
select_stock:
 mov r0,#0
 bl transition
 cmp r0,#0
 beq select_refresh
 cmp r4,#0
 moveq r5,#3
 movne r5,#2
select_write:
 addr r6,STATE
 mov r0,#1
 str r0,[r6,#24]
 call 0xC0057AE8
 mov r1,r5
 mov r2,r7
 call 0xC005C020
 mov r0,#0
 str r0,[r6,#24]
select_refresh:
 bl refresh
 mov r0,#0
 pop {r4-r8,pc}

/* Keep normal resolution readback while rendering the private choice as row2. */
resolution_display:
 push {r4-r6,lr}
 mov r4,r0
 mov r5,r1
 addr r6,STATE
 str r4,[r6,#20]
 /* The native queue publisher does not dereference its receiver. Publish
  * LV explicitly even if its observer was created before AutoRun. */
 mov r2,#0
 cmp r5,#2
 moveq r2,#1
 cmp r5,#4
 moveq r2,#2
 ldr r0,[r6,#16]
 cmp r0,#1
 cmpeq r5,#3
 moveq r2,#3
 mov r0,r4
 self r1,lv_name
 call 0xC0593F30
 ldr r0,[r6,#16]
 cmp r0,#1
 cmpeq r5,#3
 bne display_stock
 mov r0,r4
 self r1,var_name
 mov r2,#2
 call 0xC0593F30
 b display_done
display_stock:
 mov r0,r4
 mov r1,r5
 bl display_original
display_done:
 pop {r4-r6,pc}
display_original:
 .word 0xe92d4070
 addr ip,0xC05931D4
 bx ip
refresh:
 push {r4-r6,lr}
 addr r4,STATE
 call 0xC0057AE8
 call 0xC005C058
 mov r5,r0
 ldr r0,[r4,#20]
 cmp r0,#0
 beq 21f
 mov r1,r5
 bl resolution_display
21:
 ldr r0,[r4,#28]
 cmp r0,#0
 beq 22f
 mov r1,r5
 bl hud_display_a
22:
 ldr r0,[r4,#32]
 cmp r0,#0
 beq 23f
 mov r1,r5
 bl hud_display_b
23:
 pop {r4-r6,pc}

/* Each settings wrapper preserves the stock argument/result ABI. A setting
 * change deselects 3K before it can select an incompatible capture profile.
 * The resolution callback's own setter is the only bypass. */
.macro wrap name,target
\name:
 self ip,\name\()_original
 b settings_change
\name\()_original:
 .word 0xe92d4070
 addr ip,(\target+4)
 bx ip
.endm
wrap set_resolution,0xC005C020
wrap set_format,0xC005BE58
wrap set_quality,0xC005BEF0
wrap set_rate,0xC005C0B8
wrap set_crop,0xC005BB60
wrap set_media,0xC0062EC8
settings_change:
 push {r0-r3,r4-r8,lr}
 mov r8,ip
 addr r4,STATE
 ldr r0,[r4,#16]
 cmp r0,#0
 beq settings_forward
 ldr r0,[r4,#24]
 cmp r0,#0
 bne settings_forward
 mov r0,#0
 bl transition
 cmp r0,#0
 beq settings_reject
settings_forward:
 ldm sp,{r0-r3}
 blx r8
 mov r5,r0
 /* Do not recursively refresh while the private selection is being written. */
 ldr r0,[r4,#24]
 cmp r0,#0
 bne settings_return
 bl refresh
settings_return:
 mov r0,r5
 add sp,sp,#16
 pop {r4-r8,pc}
settings_reject:
 bl refresh
 mov r0,#0
 add sp,sp,#16
 pop {r4-r8,pc}

compatible:
 push {r4,lr}
 call 0xC0057AE8
 mov r4,r0
 call 0xC005BE90       /* CinemaDNG enum0 */
 cmp r0,#0
 bne incompatible
 mov r0,r4
 call 0xC005BF28       /* 12-bit enum0, mapped to third quality row */
 cmp r0,#0
 bne incompatible
 mov r0,r4
 call 0xC005C0F0       /* true24 enum12, distinct from 23.98 enum1 */
 cmp r0,#12
 bne incompatible
 mov r0,r4
 call 0xC005BB98       /* Crop off */
 cmp r0,#0
 bne incompatible
 call 0xC0444658
 mov r1,#0
 call 0xC0444698
 cmp r0,#5             /* SSD route */
 bne incompatible
 mov r0,#1
 pop {r4,pc}
incompatible:
 mov r0,#0
 pop {r4,pc}

/* r0 desired active flag. All table reads/writes and state publication are
 * serialized with the same interrupt mask used by the native memory pool.
 * No native setting or UI calls here. */
transition:
 push {r4-r10,lr}
 mov r7,r0
 addr r8,STATE
 lock r9
 bl idle_check
 cmp r0,#0
 beq transition_refuse
 ldr r6,[r8,#16]
 cmp r6,r7
 beq transition_ok
 cmp r7,#0
 beq transition_expected
 /* Recheck supported cached properties while no task can change them. */
 self r4,config_table
 mov r5,#4
7: ldm r4!,{r0,r1}
 ldrb r2,[r0,#5]
 cmp r2,#1
 bne transition_refuse
 ldr r2,[r0,#0x14]
 cmp r2,r1
 bne transition_refuse
 subs r5,r5,#1
 bne 7b
transition_expected:
 self r4,patch_table
 movw r5, #:lower16:PATCH_COUNT
8: ldm r4!,{r0-r2}
 cmp r6,#0
 moveq r10,r1
 movne r10,r2
 ldr r3,[r0]
 cmp r3,r10
 bne transition_mismatch
 subs r5,r5,#1
 bne 8b
 self r4,patch_table
 movw r5, #:lower16:PATCH_COUNT
9: ldm r4!,{r0-r2}
 cmp r7,#0
 moveq r3,r1
 movne r3,r2
 str r3,[r0]
 subs r5,r5,#1
 bne 9b
 dsb sy
verify_transition:
 self r4,patch_table
 movw r5, #:lower16:PATCH_COUNT
10: ldm r4!,{r0-r2}
 cmp r7,#0
 moveq r10,r1
 movne r10,r2
 ldr r3,[r0]
 cmp r3,r10
 bne transition_rollback
 subs r5,r5,#1
 bne 10b
 str r7,[r8,#16]
transition_ok:
 unlock r9
 mov r0,#1
 pop {r4-r10,pc}
transition_rollback:
 str r0,[r8,#8]
 str r3,[r8,#12]
 self r4,patch_table
 movw r5, #:lower16:PATCH_COUNT
11: ldm r4!,{r0-r2}
 cmp r6,#0
 moveq r3,r1
 movne r3,r2
 str r3,[r0]
 subs r5,r5,#1
 bne 11b
 dsb sy
 b transition_refuse
transition_mismatch:
 str r0,[r8,#8]
 str r3,[r8,#12]
transition_refuse:
 unlock r9
 mov r0,#0
 pop {r4-r10,pc}
idle_check:
 addr r0,0xC343B58C
 ldr r1,[r0]
 cmp r1,#8
 bne busy
 addr r0,0xC3476609
 ldrb r1,[r0]
 cmp r1,#0
 bne busy
 addr r0,0xC347E08F
 ldrb r1,[r0]
 cmp r1,#0
 bne busy
 addr r0,0xC358E140
 ldr r1,[r0]
 cmp r1,#0
 bne busy
 addr r0,0xC35A952C
 ldr r1,[r0]
 cmp r1,#0
 bne busy
 mov r0,#1
 bx lr
busy:
 mov r0,#0
 bx lr
var_name: .asciz "MV_Resolution"
.align 2
.include "tools/fp3k_native_ui.S"
.include "tools/fp3k_preview_output.S"
.include "tools/fp3k_preview_layout.S"
.include "tools/fp3k_native_menu_data.inc"
checksum_word: .word 0
payload_end:
