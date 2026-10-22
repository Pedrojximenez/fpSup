# SIGMA fp Ver.5.02 — Display / OSD drawing map

> ⚠️ 2026-09-19 實機更正,見 [`SPLASH_BAND.md`](SPLASH_BAND.md):
> (1) `osdfile` **沒有 TIF 解碼器**,它把檔案內容當原生像素 memcpy 到 layer 左上角,
>     `(h)(v)` 是來源影像的寬高、`(offset)` 是來源位元組偏移,**沒有 x/y**;
> (2) 「fmt 1 = RGB565」**錯了** —— 主層是 **1024×682 ARGB4444**(`0xF000` = 不透明黑),
>     而且**沒有調色盤**;有調色盤的是副層(8bpp,30 筆 YUVA)。fill 只吃顏色參數的低 16 bits;
> (3) layer 是**三重緩衝**,`getBuffer` 每次給不同的 base,所以每個動作要連下三次。

Goal: draw custom on-screen feedback ("fpSup loading...", progress bar) from injected
code + persistent worker task, instead of the crude `display colorbar` flash.

Firmware: `out/MAIN_c0000000.bin`, ARM32 LE, base `0xC0000000`. Decomp: `out/decomp/full/blk_c0X.c`.
Legend: **[C]** = confirmed from disasm/decomp, **[I]** = inferred, **[P]** = needs live probe.

TL;DR: **YES, we can draw text.** The firmware has a real "put string" glyph renderer
(`DrawTextSimpleFont`) plus an ARGB8888 OSD overlay layer with getBuffer / fill / commit /
present. Both the shell `display text "msg"` command and the `display osd`/`osdfile` commands
go through the same DrawMgr singleton and OSD layer. The single easiest robust path is to
replicate the `display osd 1` + `display text` handlers from our worker (or just send those
two shell strings over the AutoRun/USB shell).

---

## 1. Shell `display` command path  [C]

- Shell command table for `display` subcommands: **`0xC0BB1410`**, 24 entries.
- Entry stride = **12 bytes**: `{ char* name, char* help, void(*handler)(printf_ctx*, int argc, char** argv) }`.
- Dispatcher: FUN_c03d9c20 (given). Handler signature (from decomp):
  `handler(undefined4* param_1, int argc, int* argv)` where `param_1[0]` is a printf-like fn,
  `argc` = number of args, `argv` = arg string pointers.

Key subcommand handlers:

| subcmd    | handler       | what it does |
|-----------|---------------|--------------|
| colorbar  | `0xC03E3438`  | test pattern: `FUN_c00e1ff8(pattern)` toggles image-pipe reg `_DAT_3019002c` bit `0x3256`. NOT a framebuffer paint — it's a sensor/DIFM test-pattern enable. |
| **osd**   | `0xC03E3D00`  | enable/clear/fill OSD overlay layer (ARGB, default color `0xffff0000`). |
| osdPalette| `0xC03E3E90`  | load `.pal` palette (for paletted OSD modes). |
| image     | `0xC03E4150`  | blit image to layer. |
| **osdfile** | `0xC03E4270`| **Rosetta stone**: load TIF → memcpy rows into OSD layer buffer → commit → present. |
| **text**  | `0xC03E4620`  | **render an ASCII string** into the OSD layer via DrawTextSimpleFont. |
| faceframe | `0xC03E4840`  | draw face rect overlay. |
| focusarea | `0xC03E49A0`  | draw AF-frame overlay. |
| palette   | `0xC03E4D78`  | dump/set layer palette. |
| peaking   | `0xC03E5010`  | focus peaking overlay. |
| address   | `0xC03E5128`  | dump display addresses (probe helper). |

`colorbar` is a red herring for our purpose — it does not reveal a framebuffer; it flips an
imaging-pipeline test-pattern register (`0x30190000` block, ISP MMIO). The real drawing
subsystem is the **OSD layer** reached by `osd` / `osdfile` / `text`.

---

## 2. The DrawMgr singleton + OSD layers  [C]

Accessor (shared by `text`, `osd`, `osdfile`):

```
mgr = FUN_c0698d80()          // returns 0xC3824F98 (constructed once, lazy init)
```

`mgr` layout: `mgr[+4]` = DrawController vtable object (`&DAT_c2e38e4c`), `mgr[+0x10]` =
layer group A, `mgr[+0x7c]` = layer group B.

getLayer method = `(*(mgr[+4] + 0xc))(mgr, idx)` == **`FUN_c0698d20(mgr, idx)`**:

| idx | returns        | used by |
|-----|----------------|---------|
| 0   | `mgr + 0x10` (group A) | osdfile |
| 1   | `mgr + 0x7c` (group B) | text |
| 2   | `mgr + 0x10` (group A) | |
| 3   | `mgr + 0x7c` (group B) | |

idx encodes (monitor, layer). Two monitors × two layers (matches help
`monitor (MonitorNum0-1),(layer0-1)`). Both layer classes are the **same Display-library
`SurfacePixel` class** — group A vtable `0xC2EF6280`, group B vtable `0xC2E38E5C` — with
identical draw methods (only the +0x30 "get-state" slot differs).

### Layer object vtable (both groups identical)  [C]

Called as byte offsets into `*layer`:

| off   | fn          | meaning |
|-------|-------------|---------|
| +0x0c | `0xC07212E0`| **getDrawTextInterface()** → DrawText ctx object (used by `text`) |
| +0x10 | `0xC0721328`| **getBuffer()** → buffer descriptor (see below) |
| +0x14 | `0xC0721370`| **commit()** — finalize drawn buffer |
| +0x20 | `0xC0721480`| **fill(color32)** — fill layer with an ARGB color |
| +0x28 | `0xC0721638`| **pixelsToBytes(nPixels)** → byte count (reveals bpp) |
| +0x30 | grpA `0xC0721F98` / grpB `0xC0698C08` | isReady/getState (returns 0 if not allocated) |

### getBuffer descriptor  [C]

`desc = getBuffer(layer)` returns a struct:
- `*(u32*)(desc + 4)` = **framebuffer base address** (linear).
- `*(u32*)(desc + 8)` = pointer to dims: `dims[0]` = **width**, `dims[1]` = **height**.

The base is dynamic (allocated when the layer/OSD is enabled) → must be read at runtime; do
not hardcode.

### Pixel format  [C] — `FUN_c0721110(nPixels, fmtCode)`, fmtCode = `layer[+0x1c]`

```
fmt 0 -> bytes = nPixels << 2   =>  32bpp ARGB8888   (default OSD; `osd` fill color 0xffff0000 = opaque red)
fmt 1 -> bytes = nPixels << 1   =>  16bpp RGB565
fmt 2 -> bytes = nPixels >> 1   =>  4bpp paletted
fmt 3 -> bytes = nPixels        =>  8bpp paletted
else  -> assert "src/library/Display/src/DisplayO..."
```

Stride = `pixelsToBytes(width)`. For the default OSD overlay (32bpp) stride = width*4, color
word = **0xAARRGGBB** (alpha in high byte; `0xff......` = opaque). **[P]** Confirm the live
fmtCode of the layer you target by reading `layer[+0x1c]` or just calling `pixelsToBytes(1)`.

---

## 3. Text rendering — DrawTextSimpleFont  [C]

Class `DrawTextSimpleFont` (RTTI string at `0xC0D00DD4`). Two global instances:
`0xC37830D0` (id 0) and `0xC37830C8` (id 1), constructed by `FUN_c052b310`
(vtable `0xC0D00DB4`).

Render entry (the "put string"): **`FUN_c052b348`** = vtable+0xc of the DrawText object:

```
DrawText(self, ctx, rect, char* str, fontCfg)
```
- iterates bytes of `str`, requires each char < 0x80 (ASCII 0x20..0x7f),
- advances **16 px** per glyph (font descriptor `font[+2]=0x10`), line height 32 (`font[+4]=0x20`),
- calls per-glyph blitter `FUN_c052b550(ctx, fontDesc, &{x,y}, char, fontCfg)`.

Font descriptor (set by `FUN_c052b4a0` at `0xC37830E8`):
- firstChar `0x20`, lastChar `0x7f` (ASCII space..DEL),
- **font bitmap data pointer** `= &DAT_c2f24558` (`_DAT_c37830f4`), table size `0xbe0`,
  1bpp glyph cells. (Font bytes at `0xC2F24558`; **[P]** the byte region in the static dump
  looks unexpanded — confirm live if you ever want to rasterize yourself, but you don't need
  to: the firmware blitter handles it.)

The shell `text` handler (`FUN_c03e4620`) does exactly:
```
mgr   = FUN_c0698d80()
layer = getLayer(mgr, 1)                       // group B
dt    = (*(*layer+0xc))(layer)                 // getDrawTextInterface -> FUN_c07212e0
FUN_c0529bd8(ctx16, dt)                         // copy 4-word ctx wrapping the layer buffer
rect  = {x=0, y=0, w=0x180(384), h=0x20(32)}
fontCfg = { color=0xFFFFFFFF (white), font=0 } // = {DAT_c0bb1208, DAT_c0bb120c}
FUN_c0529cb8(ctx16, 0, rect, str, &fontCfg, 0x10, 0x18)   // draws; 0x10,0x18 = start x,y
// (no explicit present — see note in §5)
```
`FUN_c0529cb8` → `FUN_c052b2a8(0)`→object `0xC37830D0` → `FUN_c0529e78` →
`(*(*obj+0xc))(obj, ctx, rect, str, fontCfg)` == `FUN_c052b348`.

So: **there is a general draw-text/put-string API**, color and font-id parameterizable,
targeting the OSD layer surface. ASCII only (fine for "fpSup loading...").

---

## 4. Graphics primitives  [C]

- **fill-rect / fill-layer**: layer vtable +0x20 (`FUN_c0721480`), `fill(layer, color32)`.
  Fills the whole layer; for a sub-rect fill use raw buffer writes (below) — a growing rect
  is the progress bar.
- **blit / memcpy rows**: `osdfile` uses `FUN_c001510c` = memcpy (word-optimized) to copy
  pixel rows into the layer buffer; `FUN_c000e91c` = D-cache clean (DCCISW + DSB/ISB) to push
  the buffer to the display DMA.
- **pixelsToBytes**: layer vtable +0x28 for stride math.
- **palette set**: `osdPalette` handler `FUN_c03e3e90` (for 4/8bpp modes).
- No dedicated line/circle primitive found; compose from fills + text.

---

## 5. OSD overlay & presenting a frame  [C]

The OSD layer composites *over* liveview (it's a separate ARGB surface, alpha-blended), so we
can overlay "fpSup loading..." without destroying the live image.

Enable / clear / fill (`osd` handler `FUN_c03e3d00`, on=1):
```
ctx   = FUN_c03e5698()                 // OSD state singleton 0xC3757994
layer = FUN_c03e56d8()                 // getLayer for current monitor/flag (calls FUN_c0698d80 internally)
desc  = (*(*layer+0x10))(layer)        // getBuffer -> {addr=*(desc+4), dims=*(desc+8)}
(*(*layer+0x20))(layer, 0xffff0000)    // fill(color)  [optional]
FUN_c000e91c()                         // cache clean
(*(*layer+0x14))(layer)                // commit
FUN_c02e8a08(monTarget, desc, flag)    // PRESENT to the physical monitor
```
Disable: `FUN_c02e8e58(monTarget, flag)`.

Present target (`monTarget`):
```
osdMgr    = FUN_c02e4128()             // 0xC3425E38
monTarget = FUN_c02e44b0(osdMgr)       // = FUN_c02e44f0(osdMgr,0)  -> monitor 0 (main)
          / FUN_c02e44d0(osdMgr)       // = FUN_c02e44f0(osdMgr,1)  -> monitor 1
```
`FUN_c02e44f0` picks the active physical output (LCD panel / EVF / HDMI) based on the current
output state — you get the currently-displayed monitor automatically. **[I]** monitor 0 = the
active internal display (LCD/EVF); monitor 1 = the secondary/HDMI.

`FUN_c02e8a08` actually posts a compositor message (`FUN_c0019dc0`/`FUN_c001a048`, opcode
`0x800`) to swap/enable the OSD buffer — this is what makes the drawn buffer visible. **[I]**
The `text` handler does NOT call present itself, which means the OSD layer it targets (group B)
is expected to be already-enabled and live-scanned — i.e. you run `display osd 1 ...` once
first, then `display text` just paints into the live buffer. **[P]** Confirm: enable OSD, then
draw text, and check text appears without a second present.

---

## 6. Timing / update cadence  [I]

- Display compositor tasks: **DrawMgr** (idx 24, prio 17), **CYC_DRAW** (Cyc, prio 16),
  **OSD_CYC** (Cyc, prio 50), **DISPSATU** (Cyc). These run the periodic redraw.
- For animation, our injected worker does NOT need to sync to their tick. Each update:
  paint the buffer (fill/text/memcpy) → `FUN_c000e91c()` (cache clean) → `commit(+0x14)` →
  (if double-buffered / first time) `FUN_c02e8a08(monTarget, desc, flag)` to present.
- A 5–15 Hz update from the worker is plenty for a progress bar. **[P]** Whether the OSD is
  single- or double-buffered is set by the layer; if single-buffered, in-place buffer writes
  appear on the next scan without a present. Probe by drawing twice and observing tearing.

---

## 7. RECOMMENDED RECIPE

### Easiest robust: drive the shell (zero new code)
Over the AutoRun / USB mem shell, send:
```
display osd 1 0x00000000        # enable a transparent OSD overlay over liveview
display text fpSup loading...   # paint the string (white, 16px font, top-left)
```
For a text progress bar, re-issue `display text` each tick with a growing bar, e.g.
`fpSup [##########----------] 50%`. This reuses fully-tested firmware paths and needs no
address-level pokes. **This is the recommendation for first light.**

### Programmatic (injected worker calling firmware fns) — static text
Replicate the `text` handler once OSD is enabled:
```c
void* mgr   = FUN_c0698d80();                       // 0xC3824F98
void* layer = FUN_c0698d20(mgr, 1);                 // getLayer(1) -> mgr+0x7c
void* dt    = (*(void*(**)(void*))(*(void**)layer + 0xc))(layer);   // getDrawTextInterface
uint32_t ctx[4]; FUN_c0529bd8(ctx, dt);
int32_t rect[4] = {0, 0, 0x180, 0x20};              // x,y,w,h
uint32_t font[2] = {0xFFFFFFFF, 0};                 // color=white, font id 0
FUN_c0529cb8(ctx, 0, rect, "fpSup loading...", font, 0x10, 0x18);   // start (16,24)
```
(Ensure OSD enabled first: call the `osd` handler body / `display osd 1` once.)

### Programmatic — progress bar (pixel-accurate, ARGB8888)
```c
void* layer = FUN_c0698d20(FUN_c0698d80(), 0);       // group A
void* desc  = (*(...+0x10))(layer);                  // getBuffer
uint32_t base = *(uint32_t*)((char*)desc + 4);
uint32_t* dims= *(uint32_t**)((char*)desc + 8);
int W = dims[0], H = dims[1];
int stride = FUN_c0721638(layer, W);                 // pixelsToBytes(W) == W*4 for ARGB8888
// draw a filled bar rect [x0..x0+barw) x [y0..y0+barh) with color 0xFF00FF00 (opaque green):
for (int y=y0; y<y0+barh; y++){
  uint32_t* row = (uint32_t*)(base + y*stride);
  for (int x=x0; x<x0+barw; x++) row[x] = 0xFF00FF00;
}
FUN_c000e91c();                                       // cache clean
(*(...+0x14))(layer);                                 // commit
FUN_c02e8a08(FUN_c02e44b0(FUN_c02e4128()), desc, 0);  // present
```
Grow `barw` each tick for animation. Combine with a `display text`/DrawText call above it for
the label. Prefer these firmware calls over blind pokes — the base/stride come from the
firmware so you can't miss the surface.

---

## Live probes to run over the USB mem-read/mem-set shell  [P]

1. `display osd 1 0xffff0000` — expect a full-screen red overlay ⇒ confirms OSD path + ARGB8888.
2. `display text fpSup loading...` (after #1) — expect white text top-left ⇒ confirms text path
   and that no explicit present is needed.
3. Read `mgr = FUN_c0698d80()` return, then `getBuffer(getLayer(mgr,0))` → dump `desc+4`
   (base) and `desc+8`→dims to capture the live framebuffer base, W, H.
4. Read `layer[+0x1c]` (or call `pixelsToBytes(layer,1)`) to lock the fmtCode (expect 0 ⇒ 4 B/px).
5. `display osdfile \SAMPLE\TEST.TIF 1 0` — sanity of the memcpy-blit path if you want raw
   image overlays.

## Key addresses (quick ref)
- display cmd table `0xC0BB1410`; handlers: text `0xC03E4620`, osd `0xC03E3D00`,
  osdfile `0xC03E4270`, colorbar `0xC03E3438` (ISP test-pattern, not a paint).
- DrawMgr singleton accessor `FUN_c0698d80` → `0xC3824F98`; getLayer `FUN_c0698d20`.
- Layer methods: getDrawText `0xC07212E0` (+0xc), getBuffer `0xC0721328` (+0x10),
  commit `0xC0721370` (+0x14), fill `0xC0721480` (+0x20), pixelsToBytes `0xC0721638` (+0x28).
- DrawText render `FUN_c052b348`; helpers `FUN_c0529bd8` (ctx copy), `FUN_c0529cb8` (draw str).
- OSD present `FUN_c02e8a08`, disable `FUN_c02e8e58`, monitor target `FUN_c02e44b0`/`FUN_c02e44d0`,
  OSD mgr `FUN_c02e4128`→`0xC3425E38`.
- memcpy `FUN_c001510c`, cache-clean `FUN_c000e91c`.
- Font: DrawTextSimpleFont, data `0xC2F24558`, ASCII 0x20-0x7f, 16px advance.
