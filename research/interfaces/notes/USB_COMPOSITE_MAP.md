# SIGMA fp Ver.5.02 — USB composite / mode map (PTP vs vendor coexistence)

<!-- index-stamp -->
> 這份寫的是 EP 0x05 OUT / EP 0x84 IN。現行 build 用 EP 0x01 / 0x82 / 0x83(`host/fpshd.c:31-32`、`patches.py:15-20`),EP84 在現行描述元下不存在。
> 先看 [`USB_SHELL_INDEX.md`](../../../projects/usb-shell-sup/notes/USB_SHELL_INDEX.md)。


Firmware: `out/MAIN_c0000000.bin`, base `0xC0000000` (file_off = addr − 0xC0000000).
Decomp: `out/decomp/full/blk_c00.c`, `blk_c04.c`. Method: read-only static analysis
(byte-scan of descriptor templates + decompiled descriptor-construction code).

---

## VERDICT (the question)

**CONFIRMED MUTUALLY-EXCLUSIVE.** The SIGMA fp does **not** present a composite USB
configuration in which the PTP / Still-Image interface (class 0x06) coexists with the
vendor interface (class 0xFF, bulk OUT + bulk IN). Each USB "mode" is a **separate
single-function USB gadget** — one device descriptor + one configuration descriptor,
built on (re)connect from a per-mode template and registered to the DWC3 gadget layer.
Selecting a mode **tears down and re-enumerates** the whole gadget; only one is on the
wire at a time.

Decisive facts (all CONFIRMED from descriptor bytes / construction code):

- The **entire image contains exactly ONE class-0x06 (PTP) interface descriptor**
  (`0xC0CF373C`) and **exactly ONE class-0xFF (vendor) interface descriptor**
  (`0xC072B030`). They live in **different** descriptor sets built by **different**
  builder functions.
- The **PTP** config descriptor has **bNumInterfaces = 1** (the class-0x06 interface only).
- The **vendor** config descriptor has **bNumInterfaces = 1** (the class-0xFF interface only).
- No configuration descriptor anywhere in the image has an interface list that pairs
  class 0x06 with class 0xFF. The only multi-interface configs are single-purpose
  composites (CDC = 0x02+0x0A; UVC = 0x0E+0x01 audio) — neither includes PTP+vendor.

So: bringing up the vendor interface **excludes** PTP, and vice-versa.

---

## 1. Architecture — how descriptors are produced (CONFIRMED)

The fp does **not** store a ready-made 18-byte device descriptor with VID `03 10` / PID
`32 c4`; a byte-scan for that signature returns **zero** hits. Descriptors are **assembled
at runtime**:

- **idVendor** is written as a literal `0x1003` by `FUN_c0040140` (`blk_c00.c:50458`,
  `*param_1 = 0x1003`). idBcd/product filled there too.
- **idProduct** is a **runtime variable**: `FUN_c00410a0` returns `&DAT_c2efaf30`
  (`blk_c00.c:51137`) — a RAM cell in the `0xC2EF6E00` segment set per mode. This is why
  PID `0xc432` never appears as a static literal; each USB mode writes its own PID.

**Gadget selection / enumeration path** (CONFIRMED):

```
FUN_c0031910(func_id)        blk_c00.c:41180   top-level "start USB gadget = func_id"
  └ FUN_c0031a40(func_id)    41244             installs per-id SETUP handler (local_18):
        id 4  -> FUN_c0034398
        id 5  -> FUN_c04dbc10        (PTP setup family: FUN_c04dbe28/FUN_c04dc308…)
        id 8  -> FUN_c003e028        (CDC)
        id 0xc-> FUN_c003c4a0
      └ FUN_c0031c10(func_id) 41329             builds the descriptor set for the mode:
            id 4   -> FUN_c0034270
            id 5   -> FUN_c04dc4c0(5) -> FUN_c04e9148    (PTP, class 0x06)
            id 8   -> CDC   (FUN_c003ecb0 / FUN_c003f4a8)
            id 0xc -> FUN_c003c410                        (UVC region template c072b2b4)
            else   -> FUN_c00333d0                        (VENDOR, class 0xFF)  <-- DEFAULT
```

Each builder memset's a working descriptor struct, copies a **per-mode template** into it,
sets SuperSpeed fields when `FUN_c01e9438() >= 0x300` (SS: OR `0x210` into bcd/maxpacket),
then calls `FUN_c00328b8(&working_struct)` to hand the finished set to the controller.
Exactly one template is used per (re)connect ⇒ single-function gadget.

**The project's hook `0xC04DC618`** sits **inside `FUN_c04dc4c0`** (`@0xC04DC4C0`, the
`func_id == 5` / PTP branch; it stores the handle in `_DAT_c30257fc`, resets USB state, and
calls `FUN_c04e9148()` to build the class-0x06 descriptor). `FUN_c04dc4c0` is invoked as
`FUN_c04dc4c0(5)` from `FUN_c0031c10` (`blk_c00.c:41345`). This is the "op-code 5 USB state
dispatcher / (re)connect enumeration" anchor. In **stock** firmware this branch enumerates a
**PTP (class 0x06) gadget**, not a vendor one.

---

## 2. Per-mode interface + endpoint tables (CONFIRMED from descriptor bytes)

All templates read directly from the image. bLength/bDescriptorType parsed literally.

### A. VENDOR gadget — class 0xFF  (built by `FUN_c00333d0`, the DEFAULT func_id)
Template block `0xC072AFC0–0xC072B068`; builder copies `DAT_c072b030` (iface),
`DAT_c072b048/060` (config SS/HS), `DAT_c072b000…` (endpoints) into `0xC3079340/…C8`
then `FUN_c00328b8(&DAT_c3079354)` (`blk_c00.c:42406-42496`).

| field | value |
|---|---|
| Device class/sub/proto | 0xFF / 0xFF / 0xFF (from DEV_QUAL `0a 06 00 02 ff ff ff 40 01`, `@0xC072B018`) |
| Config `@0xC072B048` (SS) | bLength 9, **wTotalLength 0x32 = 50**, **bNumInterfaces = 1**, cfg 1, attr 0xC0 |
| Config `@0xC072B060` (HS) | wTotalLength 0x20 = 32, bNumInterfaces = 1 |
| **Interface `@0xC072B030`** | num 0, alt 0, **bNumEndpoints 2**, **class 0xFF sub 0xFF proto 0xFF**, iInterface 0 |
| EP (SS) `@0xC072B000` | `07 05 01 02 00 04` → **addr 0x01 OUT, bulk, mps 1024** |
| EP (SS) `@0xC072B008` | `07 05 82 02 00 04` → **addr 0x82 IN, bulk, mps 1024** |
| EP (HS) `@0xC072AFD8/E0` | addr 0x01 OUT bulk 64 / addr 0x82 IN bulk 64 |
| Product string | "Default Camera" (`@~0xC072AF9C`), mfr "OEM  " |

Only **2 bulk endpoints** (one OUT, one IN) — matches the project's vendor bulk channel.

> **Endpoint-address caveat (INFERRED / open):** the on-wire descriptor bytes give
> **bEndpointAddress 0x01 (OUT) / 0x82 (IN)**, whereas the project reports **EP05 OUT /
> EP84 IN** (ctx5/ctx4, DALEPENA 0x2100C720). `FUN_c00333d0` copies the endpoint bytes
> verbatim (no runtime address rewrite), so as-read the stock vendor descriptor uses
> 0x01/0x82. The "0x05/0x84" almost certainly refers to the **DWC3 physical-endpoint /
> context numbering** (ctx4/ctx5) rather than bEndpointAddress, OR reflects the project's
> own patched endpoint assignment. This discrepancy does **not** affect the coexistence
> verdict (it is still a single class-0xFF interface with one bulk OUT + one bulk IN).
> Note: the *PTP* builder `FUN_c04e9148` **does** rewrite endpoint-address bytes at build
> time via `FUN_c0032320()/FUN_c0032348()`; the vendor builder does not — so if the
> project drives EP05/EP84 it is likely via the class-5/PTP builder path it hooks, not the
> stock default vendor template.

### B. PTP / Still-Image gadget — class 0x06  (built by `FUN_c04e9148`, func_id 5)
Template blob `0xC0CF373C–0xC0CF3820`; builder `FUN_c04e9148` (`blk_c04.c:174289`) copies it
into `0xC3774820/…C0` and registers via `FUN_c00328b8(&DAT_c37748c0)`.

| field | value |
|---|---|
| Config `@0xC0CF37B8` (SS) | **wTotalLength 0x39 = 57**, **bNumInterfaces = 1**, cfg 1, attr 0xC0 |
| Config `@0xC0CF37D0` (HS) | wTotalLength 0x27 = 39, bNumInterfaces = 1 |
| **Interface `@0xC0CF373C`** | num 0, alt 0, **bNumEndpoints 3**, **class 0x06 sub 0x01 proto 0x01** (PIMA-15740 / PTP) |
| EP (SS) `@0xC0CF3770` | addr 0x01 OUT bulk mps 1024 |
| EP (SS) `@0xC0CF3778` | addr 0x82 IN bulk mps 1024 |
| EP (SS) `@0xC0CF3780` | addr 0x83 IN interrupt mps 64 |
| EP (HS) `@0xC0CF3788/90/98` | 0x01 OUT bulk 64 / 0x82 IN bulk 64 / 0x83 IN int 64 |
| Device desc (in blob) | bcdUSB 0x0320, VID **0x296B**, PID 0xFFFE, serial `1122…eeff` |

Standard PTP: **3 endpoints** (bulk OUT, bulk IN, interrupt IN). **bNumInterfaces = 1 — no
class-0xFF interface present.** The VID `0x296B`/PID `0xFFFE`/serial `1122…eeff` mark this
particular blob as a **development/debug PTP identity**; the shipped-camera VID (0x1003) is
patched in by `FUN_c0040140`/the runtime PID cell. Structurally it is the *only* class-0x06
interface in the image and it is always alone in its config.

### C. Mass Storage gadget — class 0x08  (builder `FUN_c003b7b0`, template `0xC072B0BC`)

| field | value |
|---|---|
| Interface `@0xC072B0BC` | num 0, nEP 2, **class 0x08 sub 0x06 proto 0x50** (SCSI transparent / Bulk-Only) |
| Config `@0xC072B138/150` | wTotalLength 44 / 32, **bNumInterfaces = 1** |
| EPs | 0x01 OUT bulk (1024/64) + 0x82 IN bulk (1024/64) |

### D. CDC (serial / "usb cdc DEBUG") gadget — class 0x02+0x0A  (func_id 8)

| field | value |
|---|---|
| Interface `@0xC072B1BC` | num 0, nEP 1, **class 0x02 sub 0x02 proto 0x01** (CDC-ACM comm) |
| Interface `@0xC072B1C8` | num 1, nEP 2, **class 0x0A** (CDC data) |
| Config `@0xC072B214/244` | wTotalLength 67, **bNumInterfaces = 2** |
| EPs | 0x83 IN int 64 (notif) ; 0x01 OUT bulk + 0x82 IN bulk |

### E. UVC webcam gadget — class 0x0E (+0x01 audio)  (func_id 0xc, builder in `FUN_c003e1xx`)

| field | value |
|---|---|
| VideoControl iface `@0xC072B2D0` | num 0, class 0x0E sub 0x01 |
| VideoStreaming iface `@0xC072B2C4` | num 1, class 0x0E sub 0x02, nEP 1, iInterface 5 |
| Audio ifaces `@0xC072B38C / B380` | num 2 (AudioControl 0x01/0x01), num 3 (AudioStreaming 0x01/0x02), alt @B438 |
| Config `@0xC072B304/31C` | wTotalLength 156, **bNumInterfaces = 4** |

UVC config = Video(control+streaming) + Audio(control+streaming) = webcam-with-mic.
**No PTP interface and no class-0xFF interface in the UVC config.**

---

## 3. Coexistence analysis (task 3) — CONFIRMED

- **PTP + vendor in one config?** No. PTP config nIf=1 (class 0x06 only); vendor config
  nIf=1 (class 0xFF only). Image-wide there is exactly one of each interface descriptor and
  they are in different builders' output.
- **Separate configurations / mutually-exclusive modes?** Yes. The gadget is chosen by a
  **function-id** passed to `FUN_c0031910`/`FUN_c0031c10`. Only one template is assembled
  and registered (`FUN_c00328b8`) per (re)connect.
- **Can more than one be active at once?** No. There is a single working descriptor struct
  per gadget and a single registration call; a mode change re-runs the connect path and
  re-enumerates (see `FUN_c00319d0`, which on mode change tears down id-specific state,
  e.g. `param_1==4 -> FUN_c0034318`, `param_1==8 -> FUN_c003f570`).

### Mode-selection mechanism (task 3, CONFIRMED)
- **Menu:** `MenuItemUsbConnectionMode` / `MenuUsbModeHandler` (`eXC_MenuUsbConnectionMode`),
  `SetUsbConnectionMode`, transition logged by `"UsbDoConnect1 connect %d->%d class %d->%d"`
  / `"UsbDoConnect2 …"` — i.e. a **class transition** (old class → new class), proving a
  single active class that changes wholesale.
- **Shell** (`out/MAIN.strings.txt`): the mode words are explicitly *exclusive*:
  - `usb msc  : Change USB MODE to MassStorage (MENU)`
  - `usb uvc  : Change USB MODE to UVC (MENU)`
  - `usb ptp  : Change USB MODE to PTP/Camera Control (MENU)`
  - `usb cdc  : CDC Connect Mode (DEBUG)`
  Each "Change USB MODE **to** X" replaces the current mode.
- **High-level function objects** (one instantiated at a time), each returns its class id
  from vtable slot `v4` (`blk_c04.c`):
  - `XC_MassStorage::v4 → 1`  (`@0xC04D57D8`)
  - `XC_UsbPTP::v4 → 2`       (`@0xC04D5DB0`)
  - `XC_UsbCom::v4 → 3`       (`@0xC04D5A70`)
  - `XC_UsbUvc::v4 → 4`       (`@0xC04D6270`)
  Backing "spec" descriptor classes: `XC_MscSpecBase`, `XC_UsbPtpSpecBase`,
  `XC_UsbComSpecBase`, `XC_UsbUvcSpecBase`, base `XC_UsbSpecBase`
  (src `library/Communication/UsbCtrl/src/model/TH/XC_UsbSpec_TH.cpp`). The **vendor**
  class-0xFF gadget is the low-level **default** function (`FUN_c00333d0`), product string
  "Default Camera".

---

## 4. What the builder hook `0xC04DC618` enumerates (task 4) — CONFIRMED (stock) / open (patched)

`0xC04DC618` is an instruction **inside `FUN_c04dc4c0` (`@0xC04DC4C0`)**, the `func_id==5`
connect handler. Stock, that path builds the **class-0x06 PTP** descriptor set
(`FUN_c04e9148`, §2B) — a **PTP-only, single-interface** config. It does **not** add a
vendor interface to a PTP config, nor a PTP interface to a vendor config; it builds one
single-function gadget and registers it. Whether the vendor channel the project drives is
(a) the stock **default** vendor gadget (`FUN_c00333d0`, class 0xFF, §2A) enumerated by
forcing the default func_id, or (b) a **patched** class-5 blob where the project overwrites
the class-0x06 PTP descriptor with vendor bytes, **cannot be resolved from the stock image**
— the patch itself is not present here. Either way the result is a **single** gadget on the
wire; **it does not co-present PTP + vendor.** Bringing up the vendor channel therefore
**excludes** PTP.

---

## 5. Liveview / UVC angle (task 5) — CONFIRMED

- Liveview-as-webcam is exposed as the **UVC gadget** (class 0x0E, §2E; tasks `Uvc16ms/
  Uvc33ms/CYC_DRAW`, `uvc_SpecInit/StartCapture/…`, string `USB Video Class (UVC)`).
- The **UVC config is nIf=4** (Video control+streaming + Audio control+streaming) and
  contains **neither a class-0x06 (PTP) interface nor a class-0xFF (vendor) interface.**
- Therefore **UVC does NOT coexist with PTP, nor with the vendor channel**, in one config.
  UVC is its own exclusive mode (`usb uvc : Change USB MODE to UVC`).
- Consequence for the "liveview + control over one cable" goal: **not achievable with a
  stock single active configuration** — UVC (liveview) and PTP (control) and the vendor
  channel are three mutually-exclusive gadgets. Achieving simultaneous liveview + control
  would require a *custom composite descriptor* (patch a config whose bNumInterfaces bundles
  UVC + vendor/PTP interfaces and their endpoints) that the stock firmware does not build.

---

## 6. Interface / product strings (task 6)

- `SIGMA fp`, `SIGMA fp Ver.%s` — product strings.
- Vendor gadget product: **"Default Camera"**, mfr **"OEM  "**, serial `00000000000000`
  (`@~0xC072AF90`).
- UVC uses `iInterface` indices (VideoStreaming iInterface=5); string `USB Video Class (UVC)`.
- CDC/debug identity blob VID 0x296B / serial `1122…eeff` (dev descriptor in PTP blob).
- Symbols: `XC_UsbPTP`, `XC_UsbClass{,Device,ExtDevice,Charging,NotConnect,ConnectSuspend}`,
  `XC_UsbPtpSpecBase`, `XC_MscSpecBase`, `XC_UsbComSpecBase`, `XC_UsbUvcSpecBase`,
  `HOST_{set,get}_var_CAM_GeneralVendorCommandAddr`, `CAM_GENERAL_VENDOR_COMMAND_ADDR`.

---

## Evidence index (addresses)

| item | address |
|---|---|
| Device-descriptor filler (VID=0x1003) | `FUN_c0040140` `@0xC0040140` (`blk_c00.c:50457`) |
| idProduct runtime cell | `FUN_c00410a0 → &DAT_c2efaf30` (`blk_c00.c:51137`) |
| Gadget starter (func_id) | `FUN_c0031910` `@0xC0031910` (`blk_c00.c:41180`) |
| Per-id builder dispatch | `FUN_c0031c10` `@0xC0031C10` (`blk_c00.c:41329`) |
| VENDOR (class 0xFF) builder | `FUN_c00333d0` `@0xC00333D0` (`blk_c00.c:42406`) |
| PTP (class 0x06) builder | `FUN_c04e9148` `@0xC04E9148` (`blk_c04.c:174289`) |
| PTP connect handler (contains hook 0xC04DC618) | `FUN_c04dc4c0` `@0xC04DC4C0` (`blk_c04.c:165914`) |
| MSC (0x08) builder | `FUN_c003b7b0` `@0xC003B7B0` |
| UVC (0x0E) builder region | `FUN_c003e1xx` (template refs `@0xC072B2C4`) |
| VENDOR interface descriptor | `@0xC072B030` (`09 04 00 00 02 ff ff ff 00`) |
| VENDOR config SS/HS | `@0xC072B048` (wTot 50, nIf 1) / `@0xC072B060` (wTot 32, nIf 1) |
| VENDOR bulk EPs | `@0xC072B000` (0x01 OUT) / `@0xC072B008` (0x82 IN) |
| PTP interface descriptor | `@0xC0CF373C` (`09 04 00 00 03 06 01 01 00`) |
| PTP config SS/HS | `@0xC0CF37B8` (wTot 57, nIf 1) / `@0xC0CF37D0` (wTot 39, nIf 1) |
| MSC interface | `@0xC072B0BC` (class 0x08/06/50) |
| CDC interfaces | `@0xC072B1BC` (0x02) + `@0xC072B1C8` (0x0A), config `@0xC072B214` nIf 2 |
| UVC interfaces | `@0xC072B2D0` (0x0E VC) + `@0xC072B2C4` (0x0E VS) + audio `@0xC072B380/B38C`, config `@0xC072B304` nIf 4 |
| Register-descriptor-set call | `FUN_c00328b8(...)` (tail of every builder) |

*Byte-scan note:* image contains exactly **1** class-0x06 interface descriptor and **1**
class-0xFF interface descriptor; a device-descriptor signature `12 01 … 03 10 32 c4` has
**0** static hits (descriptors are built at runtime, PID is a runtime variable).
