/* Return a private primary-output template only for the two observed 3K
 * policy objects. Do not mutate the stock template or a live buffer. */
.align 2
.include "tools/fp3k_preview_output_data.inc"
preview_output:
 push {r4-r6,lr}
 mov r4,r0
 cmp r1,#0
 bne preview_output_stock
 addr ip,STATE
 ldr ip,[ip,#16]
 cmp ip,#1
 bne preview_output_stock
 addr ip,0xC375EB68
 cmp r4,ip
 beq preview_output_idle
 addr ip,0xC375ED3C
 cmp r4,ip
 bne preview_output_stock
 ldr r5,[r4]
 addr ip,0xC2F21494
 cmp r5,ip
 bne preview_output_stock
 addr r6,PREVIEW_RECORD_HASH
 b preview_output_hash
preview_output_idle:
 ldr r5,[r4]
 addr ip,0xC375E934
 cmp r5,ip
 bne preview_output_stock
 addr r6,PREVIEW_STANDBY_HASH
preview_output_hash:
 addr r2,0x811C9DC5
 addr r3,0x01000193
 mov r0,#44
preview_output_hash_loop:
 ldrb ip,[r5],#1
 eor r2,r2,ip
 mul r2,r3,r2
 subs r0,r0,#1
 bne preview_output_hash_loop
 cmp r2,r6
 bne preview_output_stock
 self r0,preview_output_template
 pop {r4-r6,pc}
preview_output_stock:
 mov r0,r4
 pop {r4-r6,lr}
 /* Displaced instruction from the stock primary-output accessor. */
 .word 0xE92D4030
 addr ip,0xC0437E9C
 bx ip
