# SIGMA fp Ver 5.02 — Startup / Boot / Opening Animation (RE reconstruction 2026-08-19)

Reconstructed from firmware (Ghidra out/decomp, out/MAIN_c0000000.bin, out/lzss_full.bin) after the original
verbally-delivered research was lost to context compaction. Flags: [C] confirmed in disasm/data, [I] inferred,
[P] needs live probe. EAs are ARM addrs (base 0xC0000000); file offset in MAIN = EA − 0xC0000000.

## TL;DR
Power-on splash = a UIC ("UI Conductor", declarative) **"Logo screen"** state that plays a `CAnimationClip`
over the SIGMA-logo bitmap, composited via DrawMgr/OSD to the display(s). It is an ANIMATED BITMAP (not a
movie, not a still, not an SD file). Logo bitmaps are `.xci` icons **embedded in MAIN firmware** (~2.9 MB icon
archive at 0xC1240000–~0xC151C387), **16bpp YUV, LZ4-compressed**. **No crypto signature** — only a byte-sum
per container — so it is replaceable, but only by REFLASH (repack the LZSS MAIN + fix two checksums); there is
NO boot-time read of the logo from SD/NAND, so no drop-in file swap.

## 1. Assets [C]
- Type: still bitmap(s) animated by the UIC clip player.
- Three opening/logo `.xci` (of 2006 total icons in ROM):
  - `cmn_logo_sigma.xci` — SIGMA wordmark
  - `menu_startlogo.xci` — opening logo, fp (model code **C43**)
  - `menu_startlogo_c44.xci` — fp **L** variant (model code **C44**; one firmware serves both bodies)
- Location: EMBEDDED in MAIN (DFI seg0, load 0xC0000000, inside the LZSS-compressed payload). Icon archive at
  file offsets 0x1240014 → ~0x151C387 (EA 0xC1240014–0xC151C387), ~2.9 MB, 4-byte aligned. Font-config CSV just
  before (~0xC123FF00); embedded TrueType/sfnt fonts just after (~0xC151C387); layout/offset table ~0xC1200000.
- Proof it's in the LZSS payload, not a separate partition: name strings `cmn_logo_sigma`/`menu_startlogo` appear
  0× in compressed FP__V502.bin but 3× in decompressed MAIN/lzss_full.bin. NAND driver XC_PromDriverNand is NOT
  the source. Icons looked up by BINARY-SEARCH-BY-NAME over a descriptor array built at archive mount (source-path
  strings ~0xC0D22000 and name pools 0xC0D474D8 / 0xC18E5D14 are vestigial TOC).

## 2. Player / decoder EAs [C]
Boot chain: BootGui @0xC0020DF0 (str 0xC072808C) → disp init FUN_c0020AE0 → GUI FUN_c0020D78 → UIC app start
FUN_c0030B88 / FUN_c036D490 → initial transition edge "to Logo screen" (UIC id 0xC18EA5C8) →
__TransitionAnimationScreen__ @0xC05E0D60 + CAnimationClip (factory "FanimationClip" 0xC05E1DA7) plays
menu_startlogo.xci → display pipeline FUN_c02e6b90 @0xC02E6B90 raises display-state 3 "OPENING DISP" (tracer
FUN_c0365C88, str "OPENING DISP" 0xC0B967CC) → present via DrawMgr FUN_c0698d80 @0xC0698D80 (obj 0xC3824F98) →
OSD commit FUN_c02e8a08 @0xC02E8A08. Display-state markers 0xC0B9677C..0xC0B967CC:
REQ START LV → S/E DISP DEV ON → OPENING DISP → IMG DISP START → NORMAL OSD DISP; state counter _DAT_c3498e80
flips OPENING→NORMAL after first pass.
XCI decoder: header parse FUN_c05a6a50 @0xC05A6A50; bpp logic FUN_c05a7330 @0xC05A7330; codec dispatch
FUN_c05a6ce8 @0xC05A6CE8 (NoCompress 0xC05A71A8; RLE Byte/Word/DWord 0xC05A71E8/218/248; LZ4 0xC05A7278, frame
parse FUN_c05a7570, block decode FUN_c05a7630); decode-into-planes FUN_c03cfed0 @0xC03CFED0; name→resource
FUN_c05e0320 → binary-search FUN_c05dfe88 @0xC05DFE88 → load/decode FUN_c05d8910 @0xC05D8910; GUI Image loader
FUN_c06025a0; resource cache UicResourceCache::v1 0xC0565288. FB push via DrawMgr/OSD (see DISPLAY_OSD_MAP.md:
getBuffer 0xC0721328 / commit 0xC0721370 / present FUN_c02e8a08).
Animation attributes (data-driven, compiled UIC resource ~0xC2E011xx) [I]: speed 0xC2E01184, loop-nb [1,99]
0xC2E011D0, overwrite-loop, apply-frame → multi-frame + loopable(1–99) + speed-controlled. Frame count/fps live
in the UIC/XCI data, not code constants.

## 3. Format [C] — .xci container, 32-byte (0x20) header (verified vs 2005 samples)
```
0x00 u32 magic "XC\0\0" (58 43 00 00)
0x04 u32 compressed payload size (excl header; predicts next entry ±3 pad)
0x08 u16 width
0x0A u16 height
0x0C u8  format/palette flag (1 = palette/indexed 1B/px)
0x0D u8  depth: 4 => 16bpp(2B/px), 8 => 32bpp(4B/px)
0x0E u8  colorspace: 0=YUV, 1=RGB
0x11 u8  compression: 0=none, 1=RLE, 2=LZ4
0x20 ... payload
```
All shipped icons incl. logo: depth=4 (16bpp), colorspace=0 (YUV), compression=2 (LZ4; payload starts LZ4 frame
magic 0x184D2204). OSD overlay itself is ARGB8888 — 16bpp-YUV icons are converted into OSD at draw. Logo exact
w/h = read its archive entry (index built at runtime — [P]).

## 4. Customization [C]/[I] — replaceable by REFLASH, no signature
- No crypto integrity (SECURITY.md re-confirmed): no SHA/MD5/AES/RSA/ECDSA. Only `SUM=` byte-sum per container
  segment (lens fw uses CRC32; NAND uses BCH-ECC). MAIN header parser analyze_firmware_bin_head_main @0xC04CED60
  checks only LENGTH=/SUM=/… → a correctly re-summed custom image is accepted [I high-confidence].
- Swap the opening logo: (1) LZSS-decompress MAIN (tools/lzss.py), find target `.xci` (XC\0\0) at ~0xC1240000;
  (2) author replacement .xci (16bpp YUV LZ4 native; none/RLE also decode), KEEP width/height identical and
  payload ≤ original (archive packed contiguously, size@0x04 predicts next entry, addressed via built index —
  growing shifts/breaks it; pad to original slot); (3) re-LZSS seg0, fix DFI segment record (compressed-size +
  byte-sum, FORMAT.md §2), fix top-level container SUM=. Replace the body-matching variant (fp = C43).
- Non-reflash: shell verb dump.xci/"capture" FUN_c03e4ad0 @0xC03E4AD0 only EXPORTS the OSD framebuffer to
  \SAMPLE\dump.xci (sel main=1/sub=2/both=3, compress none/RLE/LZ4; palette dump FUN_c03e4d78) — good for
  grabbing the real logo, not injecting. No boot-time SD/NAND logo read → the practical no-reflash route is
  AutoRun/injected-code + DrawMgr/OSD overlay (DISPLAY_OSD_MAP.md): paint a custom XCI/TIF over the display.

## 5. Strings / IDs [C]
"OPENING DISP" 0xC0B967CC, "NORMAL OSD DISP" 0xC0B967AC, "IMG DISP START" 0xC0B967BC, "S/E DISP DEV ON",
"REQ START LV", BootGui 0xC072808C. UIC: "to Logo screen" 0xC18EA5C8 (siblings "to LV screen" 0xC18EA584,
REC/Menu/QS…), **skip-anim** (vocab 0xC18EA218; in a compiled transition block 0xC2E012B8 — the bypass
mechanism), __TransitionAnimationScreen__ 0xC05E0D60, "Transition Animation" 0xC05ED698, CAnimationClip/
FanimationClip. Assets cmn_logo_sigma / menu_startlogo / menu_startlogo_c44; source-path table ~0xC0D22000;
name pools 0xC0D474D8 and 0xC18E5D14.
Skip/disable: only the UIC declarative `skip-anim` transition attribute; no user-facing menu setting found [I].

## Open [P]
Map cmn_logo_sigma/menu_startlogo names → exact archive byte-offset + w/h (trace mount/index builder
FUN_c05dfe88 feed at ~0xC1200000 TOC + name pool 0xC18E5D14); confirm opening renders to HDMI (monitor 1) as
well as LCD (monitor 0).
