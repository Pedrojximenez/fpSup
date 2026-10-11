.syntax unified
.arm
.text
#include "og_pic.inc"
/* Sensor Lab: CUSTOM-only frame-rate / bit-depth lists (sl_lists.py).
 *
 * The page picks a list variant from an app variable:
 *   EXCL_FrameRate         written only by C059B2F8 (movw/movt 0xC2DF26EC)
 *   EXCL_CinemaDNGQuality  written only by C059BA10 (0xC2DF2950)
 * Under CUSTOM we want RATE_INDEX / BIT_INDEX there instead (the private
 * page maps them to SL_RATE / SL_BIT), and the stock value back otherwise.
 *
 * ROLE 1/2  the two setters.  r1 = the stock state, or -1 from ROLE 3-5 when
 *           none was ever seen.  CUSTOM and ready: save the current (stock)
 *           value, write ours.  Else with a state: stock.  Else (-1): if our
 *           value is still there, put the saved stock value back.
 * ROLE 3-5  the resolution notifiers (C05931D0 menu, C059C640 / C059C9F0
 *           standby): stock, then this notifier's +0x6C4 / +0x740 (ROLE 1/2's
 *           sites in all six vtables) with the state last seen -- the stock
 *           notifications only come when the stock state CHANGED.
 * ROLE 6    custom_ready (no site): r0 = 1 when the page is installed, the
 *           resolution setting is CUSTOM (4) and the private NBR registered
 *           -- registering it here, once, on the UI thread, with the stock
 *           loader C05E84D8(resource ctx = [reader+8] = the UI app, pack,
 *           bytes, 0) exactly as OpenGate's NBU hook does.
 *           (r4, 2026-10-02 camera: passing the reader itself froze.)
 *           READY registers only under CUSTOM; READY+8 (ROLE 7) registers in
 *           any resolution, because the MODE / SIZE rows name SL_MODE /
 *           SL_SIZE in every frame.  Refused: B2_5 entry +08 back to stock.
 * ROLE 8    reapply (no site): after the resolution SETTING changed, post the
 *           right value of both variables (C0593F30 queues a GUI message;
 *           its first argument is unused): CUSTOM and ready -> ours (saving
 *           the stock value), else our value still there -> the saved stock.
 * ROLE 9/10 the MV_Resolution GUI setter callbacks FUN_c057a6a0 (movie
 *           record) and FUN_c05824d0 (Settings page): stock first (it sets
 *           the setting synchronously), then ROLE 8.  Camera r5 2026-10-02:
 *           changing resolution inside the menu updated frame rate (its stock
 *           state changes with resolution) but not bit depth, whose stock
 *           state does not -- the notifiers ROLE 3-5 do not run for it.
 * ROLE 7    the page parser C05E82F0 (Thumb, UI thread, before a page is
 *           built): the same choice written straight into the two variables
 *           (no notification needed, the page reads them while parsing), so
 *           a page shown without any notifier since boot is right too.
 * Memory only: nothing here touches a setting (SETTINGS_AREA_FIRST_RULE).
 */
.macro LDA reg, value
#ifdef OG_V3
    OGLDA   \reg, \value
#else
 movw \reg, #:lower16:\value
 movt \reg, #:upper16:\value
#endif
.endm
.macro RETURN_TO address
 ldr pc, [pc, #-4]
 .word \address
.endm
.equ M_RESULT,   0x0C
.equ M_PACK,     0x10
.equ M_PACKLEN,  0x14
.equ M_READER,   0x18
.equ M_NBR,      0x1C     /* 0 not tried, 1 registered, 3 refused */
.equ M_LASTRATE, 0x20     /* -1 = never seen */
.equ M_LASTBIT,  0x24
.equ M_HITRATE,  0x28
.equ M_HITBIT,   0x2C
.equ M_HITRES,   0x30
.equ M_DESCRATE, 0x34     /* descriptors (+08 value), from the installer */
.equ M_DESCBIT,  0x38
.equ M_SAVERATE, 0x3C     /* stock value we replaced, -1 = none */
.equ M_SAVEBIT,  0x40
.equ M_HITPAGE,  0x44
.equ M_CTX,      0x48     /* the resource ctx registration used */
.equ M_BITBACK,  0x4C     /* times 14-bit was put back to 12 on leaving CUSTOM */
.equ M_MODES,    0x50     /* sl_menu_ui (Thumb), from the launcher; 0 = none */
.equ M_LIVE,     0x54     /* sl_menu_live (Thumb), from the launcher; 0 = none */
.equ BIT_GET,    0xC005BF28   /* settings slot +0x198, eRawBitType: 0 = 12, 1 = 14 */
.equ BIT_SET,    0xC005BEF0
.equ BIT_12,     0
.equ BIT_14,     1
.equ SET_VAR,    0xC0593F30
.equ SETTINGS,   0xC0057AE8
.equ RESOLUTION, 0xC005C058
.equ NBR_LOAD,   0xC05E84D9   /* Thumb */
.equ GUI_APP,    0xC37B7048
.equ CUSTOM_RES, 4
.equ S_ENTRY,    0x0C         /* struct sl_menu: result, app, reader, entry */
.equ B25_STOCK,  0x19C130     /* B2_5 entry +08, stock (sl_menu.c B25_OFFSET) */

#if ROLE == 7
.thumb
.global entry
entry:
 bx pc
 nop
.arm
#else
.global entry
entry:
#endif

#if ROLE == 1 || ROLE == 2
#if ROLE == 1
 .equ NAME, 0xC2DF26EC
 .equ INDEX, RATE_INDEX
 .equ LAST, M_LASTRATE
 .equ HITS, M_HITRATE
 .equ DESC, M_DESCRATE
 .equ SAVE, M_SAVERATE
 .equ BACK, 0xC059B2FC
#else
 .equ NAME, 0xC2DF2950
 .equ INDEX, BIT_INDEX
 .equ LAST, M_LASTBIT
 .equ HITS, M_HITBIT
 .equ DESC, M_DESCBIT
 .equ SAVE, M_SAVEBIT
 .equ BACK, 0xC059BA14
#endif
 push {r4, r5, r6, lr}          /* the displaced instruction, and our frame */
 mov r4, r0
 mov r6, r1
 LDA r5, MARK
 cmn r6, #1
 strne r6, [r5, #LAST]
 LDA ip, READY
 blx ip
 cmp r0, #0
 bne 2f
 cmn r6, #1
 beq 3f
 mov r0, r4
 mov r1, r6
 RETURN_TO BACK                 /* stock continues at +4 with the same frame */
3:                              /* no state: undo ours, if it is still there */
 ldr r0, [r5, #DESC]
 cmp r0, #0
 beq 9f
 ldr r1, [r0, #8]
 cmp r1, #INDEX
 bne 9f
 ldr r2, [r5, #SAVE]
 cmn r2, #1
 beq 9f
 mov r0, r4
 LDA r1, NAME
 LDA ip, SET_VAR
 blx ip
 b 9f
2:                              /* CUSTOM: keep the current (stock) value, write ours */
 /* r7 (2026-10-02) also called stock's converter here to save exactly what stock
  * would write; the camera froze entering CUSTOM (FHD -> CUSTOM), the one path
  * only that change runs.  Back to r6's way, proven on the camera. */
 ldr r0, [r5, #DESC]
 cmp r0, #0
 beq 4f
 ldr r1, [r0, #8]
 cmp r1, #INDEX
 strne r1, [r5, #SAVE]
4:
 ldr r0, [r5, #HITS]
 add r0, r0, #1
 str r0, [r5, #HITS]
 mov r0, r4
 LDA r1, NAME
 mov r2, #INDEX
 LDA ip, SET_VAR
 blx ip
9:
 pop {r4, r5, r6, pc}

#elif ROLE == 3 || ROLE == 4 || ROLE == 5
#if ROLE == 3
 .equ BACK, 0xC05931D4
#elif ROLE == 4
 .equ BACK, 0xC059C644
#else
 .equ BACK, 0xC059C9F4
#endif
 push {r4, lr}
 bl stock
 LDA r3, MARK
 ldr r0, [r3, #M_HITRES]
 add r0, r0, #1
 str r0, [r3, #M_HITRES]
 LDA ip, AFTER_CODE
 blx ip
 pop {r4, pc}
stock:
 push {r4, r5, r6, lr}          /* the displaced instruction; stock returns to us */
 RETURN_TO BACK

#elif ROLE == 6
 /* READY (notifier callers) registers only under CUSTOM, as proven on camera.
  * READY+8 (ROLE 7, the page parser, always the UI thread) registers whatever
  * the resolution: the MODE / SIZE rows name SL_MODE / SL_SIZE in every frame,
  * so the page must never be built before they exist.  Refused: B2_5 gets its
  * stock page back (entry +08), so no list of ours is ever looked up. */
 mov r1, #0
 b 1f
 mov r1, #1
1:
 push {r4, r5, r6, lr}
 mov r5, r1
 LDA r4, MARK
 ldr r0, [r4, #M_RESULT]
 cmp r0, #1
 bne 8f
 ldr r0, [r4, #M_NBR]
 cmp r0, #3
 beq 8f
 LDA ip, SETTINGS
 blx ip
 LDA ip, RESOLUTION
 blx ip
 subs r6, r0, #CUSTOM_RES        /* r6 = 0 under CUSTOM */
 ldr r0, [r4, #M_NBR]
 cmp r0, #1
 beq 9f
 cmp r6, #0
 beq 6f
 cmp r5, #0
 beq 8f                          /* notifier outside CUSTOM: not yet */
6:
 /* register, once: ctx = [reader+8], which must be the UI app */
 ldr r0, [r4, #M_READER]
 ldr r1, [r4, #M_PACK]
 ldr r2, [r4, #M_PACKLEN]
 cmp r0, #0
 cmpne r1, #0
 cmpne r2, #0
 beq 7f
 ldr r0, [r0, #8]
 LDA r3, GUI_APP
 ldr r3, [r3]
 cmp r0, #0
 beq 7f                          /* no ctx: refuse */
 cmp r0, r3
 bne 7f                          /* not the UI app: refuse */
 str r0, [r4, #M_CTX]
 mov r3, #0
 LDA ip, NBR_LOAD
 blx ip
 cmp r0, #0
 bne 7f
 mov r0, #1
 str r0, [r4, #M_NBR]
9:
 cmp r6, #0
 moveq r0, #1
 movne r0, #0
 pop {r4, r5, r6, pc}
7:
 mov r0, #3
 str r0, [r4, #M_NBR]
 ldr r0, [r4, #8]                /* struct sl_menu (sl_menu_launch.S) */
 cmp r0, #0
 ldrne r0, [r0, #S_ENTRY]
 cmpne r0, #0
 LDA r1, B25_STOCK
 strne r1, [r0, #8]              /* B2_5 entry +08: the stock page */
8:
 mov r0, #0
 pop {r4, r5, r6, pc}

#elif ROLE == 7
 push {r0, r1, r2, r3, ip, lr}
 LDA ip, READY + 8              /* checks 'installed' itself; may register */
 blx ip
 LDA r3, MARK
 ldr r1, [r3, #M_HITPAGE]
 add r1, r1, #1
 str r1, [r3, #M_HITPAGE]
 add r1, r3, #M_DESCRATE        /* its saved stock value is at +8 */
 mov r2, #RATE_INDEX
 bl apply
 LDA r3, MARK
 add r1, r3, #M_DESCBIT
 mov r2, #BIT_INDEX
 bl apply
 /* sl_menu_ui(state, CUSTOM and ready) -- r0 untouched by apply.  Resident
  * (sl_menu/sl_modes.c): registers the private pages once, whatever the
  * resolution, then under CUSTOM the MODE list (at once when nothing
  * changed).  0 = launcher did not record it: skip. */
 mov r1, r0
 LDA r3, MARK
 ldr ip, [r3, #M_MODES]
 ldr r0, [r3, #8]               /* struct sl_menu */
 cmp ip, #0
 cmpne r0, #0
 blxne ip
1:
 pop {r0, r1, r2, r3, ip, lr}
 push {r4, r5, r6, r7, r11, lr}  /* the displaced push.w {r4-r7, fp, lr} */
 LDA ip, 0xC05E82F5
 bx ip
/* r0 = CUSTOM and ready, r1 = &descriptor (saved value at r1+8), r2 = ours */
apply:
 ldr ip, [r1]
 cmp ip, #0
 bxeq lr
 ldr r3, [ip, #8]
 cmp r0, #0
 beq 1f
 cmp r3, r2                     /* CUSTOM: keep the stock value, write ours */
 strne r3, [r1, #8]
 str r2, [ip, #8]
 bx lr
1:
 cmp r3, r2                     /* not CUSTOM: undo ours, if it is still there */
 bxne lr
 ldr r3, [r1, #8]
 cmn r3, #1
 strne r3, [ip, #8]
 bx lr
#elif ROLE == 8
 /* Not installed: READY says 0 and both descriptors are 0, so nothing moves. */
 push {r4, r5, r6, lr}
 LDA ip, READY
 blx ip
 mov r5, r0
 LDA r4, MARK
 add r1, r4, #M_DESCRATE         /* its saved stock value is at +8 */
 mov r2, #RATE_INDEX
 LDA r3, 0xC2DF26EC              /* "EXCL_FrameRate" */
 bl one
 add r1, r4, #M_DESCBIT
 mov r2, #BIT_INDEX
 LDA r3, 0xC2DF2950              /* "EXCL_CinemaDNGQuality" */
 bl one
 pop {r4, r5, r6, pc}
/* r1 = &descriptor (saved stock value at r1+8), r2 = ours, r3 = name, r5 = CUSTOM and ready */
one:
 ldr ip, [r1]
 cmp ip, #0
 bxeq lr
 ldr r0, [ip, #8]
 cmp r5, #0
 beq 2f
 cmp r0, r2                     /* CUSTOM: already ours, or keep the stock value */
 bxeq lr
 str r0, [r1, #8]
 b 3f
2:
 cmp r0, r2                     /* not CUSTOM: only if ours is still there */
 bxne lr
 ldr r2, [r1, #8]
 cmn r2, #1
 bxeq lr
3:
 mov r1, r3
 mov r0, #0                     /* unused by C0593F30 */
 LDA ip, SET_VAR
 bx ip                          /* tail call: returns to our caller */

#elif ROLE == 9 || ROLE == 10
#if ROLE == 9
 .equ BACK, 0xC057A6A4
#else
 .equ BACK, 0xC05824D4
#endif
 push {r4, lr}
 bl stock
 mov r4, r0
 LDA ip, AFTER_CODE
 blx ip
 mov r0, r4
 pop {r4, pc}
stock:
 push {r4, r5, r6, r7, lr}      /* the displaced instruction; stock returns to us */
 RETURN_TO BACK
#elif ROLE == 12 || ROLE == 13 || ROLE == 14
 /* The MODE list follows the menu at once.  ROLE 12/13: the two MV_FrameRate
  * setter callbacks FUN_c057a6f8 / FUN_c05821b8 -- imx410_rate_native ROLE 6/7
  * owns those sites (RATE240 first), then lands here instead of stock+4.
  * ROLE 14: MV_DNGQuality's callback FUN_c057a5f0 (bit depth), our own site.
  * Stock runs first (it commits the setting), then sl_menu_live([MARK+8])
  * through MARK+0x54 (resident; 0 = none recorded: skip). */
#if ROLE == 12
 .equ BACK, 0xC057A6FC
#elif ROLE == 13
 .equ BACK, 0xC05821BC
#else
 .equ BACK, 0xC057A5F4
#endif
 push {r4, lr}
#if ROLE == 14 && defined(BIT14)
 /* imx410_bit14: row 3 (14 bit) -> BIT14 = 1, else 0, before stock converts
  * the row (both rows 2 and 3 give stock 12-bit).  Order the (0,2)/(0,3)
  * pairs so stock's value -> row lookup lands on the chosen row. */
 ldr r1, [r0, #8]
 LDA r3, BIT14
 ldr r2, [r3]
 cmp r1, #3
 moveq r1, #1
 movne r1, #0
 str r1, [r3]
#ifdef WITH_NOTIFY
 eor r2, r2, r1                 /* changed: stock commits 0 -> 0 and never notifies */
 LDA ip, PENDING
 str r2, [ip]
#endif
 cmp r1, #1
 LDA r3, BIT_PAIR
 moveq r2, #3
 movne r2, #2
 str r2, [r3, #0x14]
 moveq r2, #2
 movne r2, #3
 str r2, [r3, #0x1C]
#endif
 bl stock
 mov r4, r0
#if ROLE == 14 && defined(BIT14) && defined(WITH_NOTIFY)
 LDA r3, PENDING
 ldr r1, [r3]
 cmp r1, #0
 beq 1f
 mov r1, #0
 str r1, [r3]
 LDA ip, NOTIFY_CODE
 blx ip
1:
#endif
 LDA r3, MARK
 ldr ip, [r3, #M_LIVE]
 ldr r0, [r3, #8]               /* struct sl_menu */
 cmp ip, #0
 cmpne r0, #0
 blxne ip
 mov r0, r4
 pop {r4, pc}
stock:
 push {r4, r5, r6, r7, lr}      /* the displaced instruction; stock returns to us */
 RETURN_TO BACK
#elif ROLE == 15
 /* GUI page id (FUN_c05645e8 calls this instead of FUN_c0564638 at C056461C:
  * r0 = the CustomScreenLoader, r1 = the page name).  Our pages (sl_pages.py,
  * "SL_...") are in no stock GUI table; stock then installs NullGuiInterface,
  * whose v1 forwards nothing -- camera r15: every key, half-press included,
  * died on SL_TEST.  Give them their stock parent's id (GUI_PARENT, B2_5 = 36):
  * the parent's handler keeps forwarding keys, as stock's 9 shared-id pages do. */
 cmp r1, #0
 beq 1f
 ldrb r2, [r1]
 cmp r2, #0x53                  /* 'S' */
 ldrbeq r2, [r1, #1]
 cmpeq r2, #0x4C                /* 'L' */
 ldrbeq r2, [r1, #2]
 cmpeq r2, #0x5F                /* '_' */
 bne 1f
 LDA r0, GUI_PARENT
 bx lr
1:
#ifdef GUI_NEXT
 /* Loader v3: the site is shared (CHAIN, ALL_SUPS_MENU.md "0xC056461C"): a page
  * that is not ours goes to whatever was below us, r0/r1/lr as they came.  The
  * entry (rl_v3.c) put svc->chain_next() here before arming. */
 LDA ip, GUI_NEXT
 ldr ip, [ip]
 bx ip
#else
 LDA ip, 0xC0564638
 bx ip
#endif
#elif ROLE == 11
 /* After the resolution SETTING changed (menu: ROLE 9/10; notifiers: ROLE 3-5).
  * Leaving CUSTOM with 14-bit (eRawBitType 1) set: put the stock 12-bit (0)
  * back through the stock setter -- the stock lists have no 14-bit row, so the
  * bit-depth row would be stuck (camera r6, 2026-10-02).  Frame rate needs no
  * such step: stock's normaliser clamps it on the same change.  Then ROLE 8. */
 push {r4, lr}
 LDA ip, SETTINGS
 blx ip
 mov r4, r0
 LDA ip, RESOLUTION
 blx ip
 cmp r0, #CUSTOM_RES
 beq 9f
 mov r0, r4
 LDA ip, BIT_GET
 blx ip
 cmp r0, #BIT_14
 bne 9f
 mov r0, r4
 mov r1, #BIT_12
 mov r2, #0
 LDA ip, BIT_SET
 blx ip
 LDA r3, MARK
 ldr r0, [r3, #M_BITBACK]
 add r0, r0, #1
 str r0, [r3, #M_BITBACK]
9:
 pop {r4, lr}
 LDA ip, REAPPLY_CODE
 bx ip                           /* tail call */
#endif
