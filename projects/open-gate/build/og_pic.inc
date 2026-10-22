/* OpenGate payloads as one Loader v3 block (2026-10-06).
 * projects/usb-shell-sup/notes/LOADER_V3.md §3, §8 step 4.
 *
 * Every OpenGate address in the cave (0xC0730000..0xC0735000) and the private
 * NBR pack (0xC0793060) is a coordinate in ONE layout.  The v3 builder
 * (build_v3_og.py) puts that layout in the sup's block at the same relative
 * places, so code reaches its own data PC-relative:
 *
 *     block offset = address - 0xC0730000      (cave image, 0x5000 bytes)
 *     pack         at OG_PACK_OFF                (right after it)
 *
 * Without OG_V3 nothing here emits a byte and every address is what it always
 * was: the AutoRun/fpSup.BIN cards assemble byte for byte as before.
 *
 * With OG_V3:
 *   OGA(x)   a cave address as a layout coordinate, OGV + (x - 0xC0730000)
 *   OGP(x)   the pack's address, OGV + OG_PACK_OFF + (x - 0xC0793060)
 *   OGLDA    loads a coordinate inside the layout PC-relative (movw, movt,
 *            add pc) and anything else as the absolute it is (movw, movt).
 *            OG_ORG = this payload's own coordinate (the builder passes it).
 * OG_V3_PAIR (Sensor Lab, whose payloads have no room for a third word):
 * OGLDA stays a movw/movt pair and og_pic.py rewrites it PC-relative at
 * build time.
 * The builder assembles everything twice, at two OGV, and refuses the block
 * unless the bytes are identical: no absolute reference into the block can
 * survive that. */
#ifndef OG_PIC_INC
#define OG_PIC_INC

#define OG_CAVE0     0xC0730000
#define OG_PACK0     0xC0793060
#define OG_PACK_OFF  0x5000
#define OG_SPAN      0x8000

#ifdef OG_V3
#ifndef OGV
#define OGV OG_CAVE0
#endif
#define OGA(x) ((x) - OG_CAVE0 + OGV)
#define OGP(x) ((x) - OG_PACK0 + OGV + OG_PACK_OFF)

_og0:

.macro OGLDA reg, value
#ifdef OG_V3_PAIR
    /* Sensor Lab: the coordinate as a plain pair; og_pic.py rewrites it
     * PC-relative at build time, in the same two words. */
    movw    \reg, #:lower16:\value
    movt    \reg, #:upper16:\value
#else
.if ((\value) >= OGV) && ((\value) < (OGV + OG_SPAN))
    movw    \reg, #:lower16:((\value) - (OG_ORG + (1001f - _og0) + 8))
    movt    \reg, #:upper16:((\value) - (OG_ORG + (1001f - _og0) + 8))
1001: add   \reg, pc, \reg
.else
    movw    \reg, #:lower16:\value
    movt    \reg, #:upper16:\value
.endif
#endif
.endm

/* OG_CHAIN (Loader v3, stackable cores): the hook's way down.  OG_NEXT is this
 * payload's word in the layout; the entry (og_v3.c) puts there what the site
 * branched to before (svc->chain_next: another sup's layer) or, when nothing
 * was, this payload's og_replay -- the displaced instruction and the way back. */
#ifdef OG_CHAIN
.macro OG_PASS
    OGLDA   ip, OG_NEXT
    ldr     ip, [ip]
    bx      ip
.endm
#endif

#else
#define OGA(x) (x)
#define OGP(x) (x)
#endif

#endif
