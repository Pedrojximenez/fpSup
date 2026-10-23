# Can the fp read IMX410 registers back? (offline RE, 2026-10-20)

Evidence: **[C]** read in the code (capstone on `out/MAIN_c0000000.bin`) · **[I]** inferred. Nothing here was run on the camera.

## Answer

- **[C] Stock firmware never reads the sensor.** The only sensor-bus access is the write-only routine
  `FUN_c0128898` (Thumb), reached only via `FUN_c0322c70` (ARM, 570 callers) → `blx 0xC0126550` (Thumb) → `bl 0xC0128898`.
  No shell command (`imager` has no read subcommand; `reg_add` is a write-list entry) and no HAL function reads it.
  Sensor temperature (`temp_cmos`) is an **ADC channel** (name table at 0xC2E35B60..), not a sensor register.
- **[C] The controller can receive.** 0x21C00000 is an 8-channel serial (SPI-type) block, stride 0x100; the sensor is
  channel 1 (0x21C00100). Two other drivers for the same block read RX data from **+0x1C** after completion, and one of them
  (driver A) explicitly accepts channel 1.
- **[I] Unknown: whether the IMX410 SDO pin is wired to ch1's RX, and what the read chip-ID byte is** (0x81 = write; Sony
  4-wire convention suggests 0x82 for read, unverified).

## Register map of one channel (base 0x21C00000 + ch*0x100)

| off | use | evidence |
|---|---|---|
| +0x00 | control: 0x11 then 0x13 (reset → enable); driver A `|= 1` before each xfer | [C] c0128906, c012a98e, c012a4dc |
| +0x04 | config: bit0 = "TX-only" flag (driver A **clears it for reads**, raw ch0 writer sets it), [15:8] clock divider, bits 16–18,1–6 mode flags | [C] c012a700, c012a508 (`str 0,[sp,#0x34]`), c012a660 |
| +0x08 | 0x30 (bits 7:4, mode/CS) | [C] c012891c, c012b748 |
| +0x0C | [7:0] bit count of word in +0x14, [15:8] bit count of word in +0x18 (bits 16/17 flags) | [C] c012b8ee (`len<<11` into [15:8]), c012a718 |
| +0x10 | 1 = start/enable, 0 = stop | [C] c012892c, c012a830 |
| +0x14 | first word (header) | [C] c012894a, c012a790 |
| +0x18 | second word (TX data) | [C] c012894c, c012a7ca, c012b938 |
| +0x1C | **RX data** (byte i in bits 8i..8i+7) | [C] c012a6ac, c012ba68, c012be4e |
| +0x20 | status/IRQ: bit0 = done; driver A read waits for `(st & 0x11) == 0x11` (bit4 = RX valid [I]); 0x4000/0x2000 = IRQ enables | [C] c0128952, c012a6b2, c012bbdc |

Pointer tables (8 ch × 9 regs, stride 0x24): 0xC07D1E00 / 0xC07D1F20 / 0xC07D2050 (+0x3C regs at 0xC07D1DE0).

## The sensor write (FUN_c0128898, Thumb, arg r0 = u8 buf[3] = {reg_hi, reg_lo, val})

```
c01288b0 movs r1,#0x81 ; strb [sp,#3]          header byte is a constant, not a parameter
c0128906 str 0x11,[ch1+0] ; str 0x13,[ch1+0] ; str 0,[+0x10] ; str 0,[+0x2c]
c0128916 str 0x100,[+4] ; str 0x30,[+8] ; str 0x818,[+0xc] ; str 0,[+0x20] ; str 1,[+0x10]
c0128942 pkhbt/orr  -> [+0x14] = 0x81 | reg_hi<<8 | reg_lo<<16   (24 header bits, LSByte first on wire [I])
c012894c str val,[+0x18]                                         (8 data bits)
c0128952 poll [+0x20] bit0, max 10000 loops ; return 0 (always)
```
- **[C] No mutex/semaphore, no IRQ masking**, busy-wait only; re-initialises the channel on every call. Buffer is built by
  `FUN_c0322cb0` (ARM): buf[0]=reg>>8, buf[1]=reg&0xFF, buf[2]=val.
- **[C] +0x04 = 0x100 → bit0 = 0**, i.e. the firmware already writes in the mode driver A uses for reads, so the RX register
  is probably loaded during every stock write too [I].

## Other drivers on the same block (for reference)

- **Driver A** (0xC012A190–0xC012B300, Thumb; table 0xC07D1E00): open `c012a190(cfg,handle)`, write `c012a270`, read
  `c012a310(handle, cmd, rx*, ...)` → setup `c012a508` + receive **`c012a5e8(port, u8 *rx, nbits)`** → `c012a690` polls
  `+0x20 & 0x11` and reads `+0x1C`. IRQ variant `c012a878(port)` only accepts ports 0..1 (IRQ 0x46 / 0x48).
  Users: display-panel init script interpreter `c00f4560` (op 2 = read byte), lens (`c0358fa4`, port 0). No sensor user. [C]
- **Driver B** (0xC012B388–0xC012BF90; table 0xC07D2050): `c012b7b0(ch, tx, rx, len, 0)` full duplex; length limit ch0 ≤16,
  **ch1 ≤ 0x200**, ch2–7 ≤ 4 (`c012b820`); only user is the hot shoe (ch6, see research/interfaces/notes/HOT_SHOE.md). [C]

## Suggested experiments (not run)

1. **Zero-risk first:** after the camera has been in live view, `mem get` 0x21C0011C and 0x21C00120 a few times
   (read-only MMIO; nothing else reads ch1 RX). Varying, non-0x00/0xFF values ⇒ SDO is wired and sampled during writes. [I]
2. **Hand-rolled read** (tiny Thumb stub run through callfn/echo — not `c0128898`, its 0x81 is hard-coded):
   ```
   cpsid i                                  ; stock writers take no lock, so block interleaving
   [ch1+0x00]=0x11; [ch1+0x00]=0x13; [+0x10]=0; [+0x2c]=0
   [+0x04]=0x100; [+0x08]=0x30; [+0x0C]=0x818; [+0x20]=0; [+0x10]=1
   [+0x14]=0x82 | reg_hi<<8 | reg_lo<<16     ; 0x82 = guessed read chip-ID
   [+0x18]=0                                 ; dummy data phase
   poll [+0x20]&1 (≤10000); val = [+0x1C] & 0xFF ; also record [+0x20]
   cpsie i ; return val | status<<16
   ```
   Validate on a register whose current value is known from a write we just made (e.g. `0x0022/0x0023` window start,
   IMX410_RULES §7/§15). If every chip-ID candidate returns the same constant, SDO is not wired (or needs other +0x04 bits).
   Risk [I]: a wrong chip-ID should be ignored by a Sony sensor, but this is not guaranteed; never try 0x81 with a
   "dummy" data byte (that is a real write of 0x00).

## Live step 1 (2026-10-20, read only, during the sweep)
`mem get 0x21C0011C,0x21C00120` × 8 (0.3 s apart): RX = 0x00000000 every time, status = 0x11.
ch1 block 0x21C00100..2C: 13 100 31 818 1 **80081** 0 0 11 0 0 0 — the last header is a write of reg 0x0008 (= SVR high,
written 0 every frame), TX 0. RX 0 is what a write would return if the sensor does not drive SDO during a write,
so this does not decide whether SDO is wired. Status bit 4 is set (RX valid [I]). Next: step 2 (an actual read
command) — needs the user's go-ahead.

## Live step 2 (2026-10-20, `sensor_read/spi_read.py`, reg 0x0016 = harmless, mode 8)
Same channel setup as the stock writer, IRQs masked, header low byte = chip-ID, TX data 0:
chip 0x82, 0x83, 0x80, 0xC1, 0x41 → RX 0x00000000, status 0x01, done after 21 polls. Control: a real write (0x81, 0x32)
→ RX 0, status 0x01. Status bit 4 (seen as 0x11 when idle after stock traffic) never set by our transactions.
**No read-back with the stock channel setup.** Either SDO is not wired, or the RX path needs driver A's configuration
(+4 bit 0 / the template at 0xC2F14A6C) — not pursued further for now; the image was unaffected.

## Driver A read recipe (offline RE, 2026-10-20, nothing run)

### Main finding: a read is the same transaction as a write; only the way it finishes differs
- **[C] Driver A's read setup `c012a508` is the same code as its write setup `c012a448`**, except one store:
  `str 0,[sp,#0x34]` = template field +0x30 → **+0x04 bit0 = 0**. There is no separate RX phase, no RX bit count
  and no direction bit. The stock sensor writer already writes +0x04 = 0x100 (bit0 = 0), so **our step-2 setup was
  already a "read" setup**.
- **[C] The controller is full duplex and +0x1C is an RX FIFO pop.** In the IRQ/FIFO path (`c012aa38` → `c012ae98` /
  `c012b0a0`) every TX word goes into +0x18 (dummy 0 words once the TX data runs out, `c012af28`), and RX is collected by
  reading +0x1C once per word (`c012b270/290/2b0` = 8/16/32-bit pops). So a read = clock out dummy bits and collect what
  came in during them.
- **[C] Completion of a polled read (`c012a690`):** loop up to 10000 times { `rx = [+0x1C]`; `st = [+0x20]`;
  break if `(st & 0x11) == 0x11` }; then `[+0x10] = 0`; the result is the **last** `rx`. `c012a5e8` then splits it
  LSByte first: `rx_buf[i] = rx >> 8i`, for nbits/8 bytes.
- **Why step 2 got 0 [I]:** `spi_read.S` stopped on status bit0, then read +0x1C once. Driver A does not trust bit0
  alone; it keeps popping until bit4 is also set. With the stock framing (+0x0C = 0x818, two phases) there are probably
  two RX entries (header phase, data phase) and we read only the first, which is all zeros because the sensor does not
  drive SDO during the header. Step 2 also showed status 0x01 at exit (bit4 still clear) while the idle status is
  0x11, which fits "bit4 not set yet". This is the cheapest thing left to test; see `sensor_read/spi_read2.S`.

### Register bits
| reg | bits | meaning | evidence |
|---|---|---|---|
| +0x00 | 0x11 → 0x13 | stock writer + FIFO/IRQ path (`c012abd8`) write 0x13 to start; IRQ open (`c012a98e`) writes 0x11; driver B open sets bit0, clears bit1. bit1 = run/start, bit0 = enable, bit4 = ? | [C] values, [I] meanings |
| +0x04 | bit0 | **1 = TX only / drop RX** (driver A write template default), **0 = keep RX** (driver A read, driver B always, stock sensor writer) | [C] c012a730, c012a53e, template |
| | bit1 | continuous CS across several FIFO words: set when the transfer has more than one word (`c012ab80`); driver B leaves it as it was **for ch1 only** (`c012b65e`) | [C] / [I] meaning |
| | bits 2–6 | mode fields: all 0 in every user found (template, lens, hot shoe, sensor) | [C] |
| | [15:8] | clock divider (sensor 1, lens 0xD0, hot shoe 0xFF) | [C] c012a72c, c012aa16, c05054bc |
| | 16, 17 | template fields, always 0 | [C] |
| | 18 | clock mode (CPOL/CPHA [I]): sensor 0, lens 0, hot shoe 1 | [C] c012aa12, c05054c0 |
| +0x08 | [7:4] | **3 when divider ≤ 1, else 0 (2 on ch0)** (driver B rule `c012b748`); probably the RX sample delay at high clock [I]. Sensor: 0x30 | [C] |
| | bit0 | set by the IRQ config `c012a9c8`; the live dump shows 0x31 on ch1 | [C] |
| | [15:8] | driver A write path `c012a410`: cfg+0x24 << 8 (CS setup/hold or gap between phases [I]); 0 for the sensor | [C] |
| +0x0C | [7:0] | number of bits taken from **+0x14** (phase 1) | [C] |
| | [15:8] | number of bits per **+0x18** word (phase 2 / each FIFO word): driver B `len_bytes << 11`; FIFO path `0x800 << size` = 8/16/32 | [C] c012b8ee, c012ab6e |
| | 16, 17 | both = bit order flag `f0` (cfg+4): sensor 0, lens 1, hot shoe 1. The sensor header is sent as `0x81 | hi<<8 | lo<<16` with the chip ID in the low byte, so f0 = 0 = LSB first (matches Sony's LSB-first serial) [I] | [C] values |
| +0x10 | | 1 before loading data; 0 after the read (driver A) | [C] |
| +0x14 | | phase-1 word (header). The FIFO path writes the first word here. Driver A with n ≤ 32 bits puts **0 bits** here and everything in +0x18 | [C] |
| +0x18 | | phase-2 word / TX FIFO push; **writing it starts the transfer** (it is written last on every path) | [C] / [I] |
| +0x1C | | RX FIFO pop (one word per TX word) | [C] |
| +0x20 | bit0 | done | [C] |
| | bit4 | second completion bit; a polled read needs both bits (RX drained/valid [I]) | [C] c012a6b6 |
| | writes | 0 = IRQs off (stock writer, polled paths); 0x01004000 / 0x01002000 \| n<<20 = TX/RX FIFO IRQ enables + RX threshold (IRQ path) | [C] c012ab9c, c012abca |
| +0x3C | | driver A write path `c012a410`: cfg+0x28 | [C] |

Global: driver A/B quit silently unless **0x30000800 bit4** is set (driver B open sets it) and they set
**0x300021B8 bit0 / 0x300021B0 bit0** (`c012a808`, probably the block's clock/reset). Boot sets **0x30001250 bit0 = 1**
(`c0020dd8` → `c012b560`). The stock sensor writer touches none of these, so on a running camera they are already set. [C]

### The template at 0xC2F14A6C (question 3)
- **[C] It lives in the data segment, which is LZSS-compressed in `MAIN_c0000000.bin`.** The words read from that file at
  this address (e.g. 0x1E1EC800…) are compressed bytes, not the template. The real contents are in
  `out/seg1_c2ef6e00.bin` (base 0xC2EF6E00): 14 words, **all 0 except +0x30 = 1**.
- **[C] Only one reference in the whole image:** `c012a6d8` copies it (0x38 bytes) onto the stack. Nothing fills it at
  run time and it holds nothing per port. It only gives the defaults "every +0x04 mode bit 0, bit0 = 1 (TX only)".
  Per-port values come from the caller's cfg (`c012a190` copies cfg+0 port, +4 bit order, +8 divider, +0xC nbits,
  +0x18 → +0x04 bit18, +0x24 → +0x08[15:8], +0x28 → +0x3C into a 0x2C-byte port slot at 0xC31D8FFC).
- For the sensor (port 1) that gives exactly what the stock writer writes: +0x04 = 0x100, +0x08 = 0x30, +0x0C = 0x818 /
  0x2000, bit order 0.

### Step list for one read of register R with chip ID C (question 4)
```
IRQs off
[ch1+0x00]=0x11 ; [ch1+0x00]=0x13 ; [+0x10]=0 ; [+0x2C]=0
[+0x04]=0x100          ; divider 1, bit0 = 0 → RX kept   (already the stock value)
[+0x08]=0x30           ; RX sample delay for divider 1 [I]
[+0x0C]=0x818          ; A) stock framing: 24 header bits + 8 data bits
     or 0x2000         ; B) driver-A framing: 0 + 32 bits
[+0x20]=0 ; [+0x10]=1
A) [+0x14]=C | R_hi<<8 | R_lo<<16 ; [+0x18]=0
B) [+0x14]=0 ;                      [+0x18]=C | R_hi<<8 | R_lo<<16 | 0<<24
loop ≤10000: rx=[+0x1C] ; st=[+0x20] ; until (st & 0x11)==0x11
[+0x10]=0 ; IRQs back
value: A) last rx [7:0] (data phase entry) [I]   B) rx [31:24] (last byte received, LSB-first shift-in) [I]
```
- Sony 4-wire convention [I]: write ID 0x81 (confirmed from the stock writer), read ID most likely 0x82; data comes out
  on SDO during the 8 bits after the address. **Full duplex covers this**: the bits clocked in during the data byte are
  the register value, so no separate half-duplex RX phase is needed or available.
- `sensor_read/spi_read2.S` (ARM, r0 header, r1 TX, r2 result block of 29 words, **r3 = mode**: bit0 framing A/B,
  [15:8] divider) does this and records the first 12 (RX, status) pairs, plus the status before start, so a single run
  shows how many RX entries a transaction produces and when bit4 sets. Assembled offline (268 bytes); **not run**.
  Suggested order: reg 0x0016, chip 0x82, mode 0 then mode 1; control = 0x81 with the stock value, as in step 2.
  If every pair is 0 in both modes, the next suspects are wiring/pinmux (below) and the clock divider (try mode 0x0400:
  divider 4, +0x08 = 0).

### Is SDO wired / pinmuxed for ch1? (question 5)
- **[C] Sensor power code doesn't touch any serial pin.** `ImageSensor_factoryIMX455.cpp` power on/off (`c0326f60`,
  `c0327388`; the IMX410 shares that factory) only sets pins to GPIO (function 0) plus direction, and one pin to
  function 0x29 (INCK clock out, pin table +0x58). The XVS/XHS timer pins use functions 0x2A/0x2B (`c0126620`, `c01267f0`;
  timers 0x30100C00/0x30100C40). `c03258c8`-area code (`c0325184`) only makes pin 0x544 a GPIO.
- **[C] The board pin table** (seg1 0xC2EF8FBC, two variants at 0xC2EF8FBC / 0xC2EFA3AC, 167 entries of
  {pin, function, dir, pull, drive}, ending at 0x10003; applied by `c0024bd0`) has no entry that looks like a serial
  port group: functions are 0, 0x200 (default), 0x201..0x20B on a few pins, and 0x10000 on pins 0..3.
- **[I] So the ch1 SCK/SDO/SDI/XCE pads are dedicated pins, or are muxed by code not found here.** No firmware code sets
  or needs an RX pin function for ch1, and no firmware path ever reads ch1. Whether the IMX410 SDO ball is routed to the
  SoC can only be answered on the camera (spi_read2) or from the board.

## Live step 3 (2026-10-20, `spi_read.py --v2`, driver-A completion, reg 0x0016, mode 8)
| framing / clock | chip | RX words popped (all) | status sequence |
|---|---|---|---|
| stock 0x818, div 1 | 0x82, control 0x81 write | 0x00000000 ×6–7 | 10 10 10 10 10 01 11 |
| driver-A 0x2000 (one 32-bit phase), div 1 | 0x82, 0x83 | 0x00000000 | same |
| stock, div 4 (+0x08 = 0) | 0x82 | 0x00000000 ×12 | 10 … |
| driver-A, div 4 | 0x82 | 0x00000000 ×12 | 10 … |
Every popped RX word is 0 in every framing, chip-ID and clock, including a real write. A floating input would
not read a clean 0 every time; **the ch1 RX line is held low → SDO is not connected to the SoC** [I, strong].
Serial read-back is closed; the remaining route is embedded data in the image stream (next section).

## Embedded data / readback (offline RE, 2026-10-20; nothing run on the camera)

Scripts and dumps: scratchpad `ebd/` (`syms.py`, `kodis.py`, `a64.py`, `wr.py`, `row0scan.py`, `row0b.py`, `row0c.py`).
[C] = read in code/data · [D] = computed from our existing captures · [I] = inferred.

### Most actionable
1. **[D] Row 0 is a real line slot of the sensor stream and the fp receiver passes it to DRAM.** Of the **6264** existing
   BUFA frames taken with `--ystart 0` (every sweep since the OB test), row 0 is all-zero words in 6231. The other 33 are
   all explained: `0019`/`001B`/`001D` = 02/04 make row 0 a **real scene row** (correlation 0.997 with row 1601 resp. 575
   of the reference frame), 08…FF make it OB-like (≈254); `072B` bits 3–5 (mode 8) make it OB-like (≈260).
   With the test pattern on (`02B2 = 1`, `captures/testpattern2/p1`) rows 1.. carry the ramp but **row 0 stays 0**.
   ⇒ row 0 is not produced by the pixel / test-pattern path; it is a slot the sensor sends with a zero payload (a
   dummy line, or the embedded-data line position with EBD output off) [I]. **Whatever the sensor puts in that slot
   reaches DRAM already** — no receiver change is needed to see a top embedded line if the sensor emits it there.
2. **[D] No single register write so far turned embedded data on.** Row 0 was in every frame of: the 187 Sony-only
   registers walked over 00/FF/each bit/Sony value (`sweep_sony_bits*`, `fast_sony`), 183 non-table registers × 4 values
   (`sweep_05a9_partner4`, with 05A9 = 1), all 161 table registers × 8 bits (`sweep_table_bits*`), the 176-point const scan.
   None produced non-pixel content (no Sony EBD tag bytes 0x0A/0x55/0xAA/0xA5/0x5A/0x07, no copy of a written value).
   ⇒ the enable is (a) a register never swept, (b) needs two registers (a 16-bit size/line count, as on the IMX283 below),
   (c) latches only at a mode set (fast-path points), or (d) goes to a line outside our window.
   Never swept: **`00C4`, `00CE`, `00D1–00D3`, `00D4`, `00D5`, `00D7`, `00DA`, `0011`**, and `0002` only with 05A9 = 1.
3. **[C] The IMX410 *does* answer reads — the fp just has no wire for it.** Z CAM `imvt_camera`: `sensor_spi_read`
   (0xB94D50) → `sensor_bus_pack_read_buffer` (0xB96538) builds **`82 addrH addrL 00`** (write: `81 addrH addrL val`),
   one 4-byte full-duplex `SPI_IOC_MESSAGE` (cs_change 1), and returns **rx[3]**. `sensor_spi_init` sets
   **SPI_MODE_3 | SPI_LSB_FIRST (0x0B), 8 bits/word**. Users: `sensor_standby`/`_cancel` (read-modify-write of `0000`
   bit 0), `sensor_dump_all_register` (reads back every init-table register), the IQ shell and a debug request.
   So the read chip ID 0x82 and the "value in the byte after the address" framing are confirmed; together with live
   step 3 (RX held at 0 in every framing) the fp's SDO is simply not connected [I, strong].
   (The fp keeps RAM shadows instead of reading: `0000` at 0xC343B688, `0002` at 0xC343B68C — `FUN_c0325858/78`.)

### 1. Z CAM E2-F6 (Hi3559AV100, `mpp/hi_mipi.ko` + `usr/bin/imvt_camera`)
- **[C] Receiver attributes** (`combo_dev_attr_t`, 0x26C B, symbols `SLVS_8lane_CHN0_SENSOR_IMX410_12BIT_*_ATTR`):
  input_mode 4 (SLVS-EC), data_rate 1, img_rect = (0, 0, W, H) — e.g. (0,0,6064,4040), (0,0,2020,1342);
  slvs: RAW12 (2), WDR none, lane_rate high, **sensor_valid_width 6104** (6064 modes; 2020 → 2036, 4096 → 4184,
  5596 → 5596), lane_id 0..7. **y = 0: no lines are discarded at frame start by configuration.**
- **[C] The SLVS-EC link driver has no embedded-data / data-type control at all.** `mipi_set_slvs_dev_attr` only calls
  lane num/rate/cken/en/sel, `set_raw_type` (+0x2C [14:12]), `set_data_rate`, `set_wdr_mode` (+0x2C [5:4], +0x30),
  deskew symbol, clear_en, mem_ck_en, `set_sensor_avalid_width` (+0x3C), **`set_image_rect`** (+0x34 = y | (y+h−1)<<16,
  +0x44 = x | (w−1)<<16), `set_crop_en` (+0x2C bits 0, 2), CRC enable, ECC option/block sizes, lane order.
  Proc output knows ECC/HeaderCRC/PayloadCRC/DataFifo errors, nothing about EBD. The user-DT check ("must be in [0x38,0x3f]")
  is the MIPI-CSI path, not SLVS-EC.
- **[C] No IMX410 register around those settings is EBD-like**, and nothing in `imvt_camera` parses a sensor line
  (temperature = `HwMonitor::readTemperature`, a board sensor; frame count = `ISP_FrameCntGet`).
- [I] Z CAM's crop starts at 0 yet delivers 4040 image rows, while the fp needs y0 = 40 for the same register set (only
  `0058` differs). Either the Hi link counts only header-"line valid" lines (OB/dummy lines flagged invalid) or the
  sensor output differs — a hint that the SLVS-EC header flags are meaningful to Sony-family receivers.

### 2. Astro SDKs
- **[C] ZWO:** `CCameraFX3::ReadSONYREG(u16, u8*)` → `ReadCameraRegisterByte` = vendor request **0xB7**, wValue = reg,
  1-byte IN (the FX3 firmware does the SPI). `WriteFPGAREG` 0xBD, `ReadFPGAREG` 0xBC. **`CCameraS2400MC_Pro` (IMX410)
  never calls ReadSONYREG**; other Sony classes do (IMX455/571/461/411/2600/6200 `CamSetStandby`/`Wakeup` RMW of `0000`,
  IMX252 `GetSensorTempInside`). astrocam's IMX455/571 drivers read `0000` and IMX571 the black level `0042/43` the same way.
- **[C] QHY410C:** the FX3 routine 0x4000347C bit-bangs GPIO 0x15 (SCK), 0x16 (SDI), 0x18 (XCE) as outputs only — no
  input pin is sampled: **write-only**. The host library has no sensor-read request.
- **[C] No SDK parses a frame header / embedded line for the IMX410.** The vendor FPGAs crop leading lines instead:
  ZWO skip 0x3D lines (14-bit) / 0x2B (bin 2) and 4 columns; IMX455 49/29/27, IMX571 45/25/23 (astrocam).
- ToupTek: stripped, not traced.

### 3. SIGMA fp firmware (receiver 0x30100000, CRCT 0x300F0000)
- **[C] No string mentions embedded/EBD/SLVS/header/line number.** Nothing reads an embedded line or a sensor
  temperature from the image stream (`temp_cmos` is an ADC channel).
- **[C+live dump] Receiver registers** (code + `research/imx410/captures/slvsec_*` dumps, mode 8 idle / still):

  | reg | value (mode 8 / still) | meaning |
  |---|---|---|
  | +0x000 | 0x00601008 / 0x00201008 | control; bit21 (`c0125bf0`), bit22 (`c0125c28`, `c0635e38/58`), bit12 status |
  | +0x004, +0x020 | HMAX/tail, VMAX−1 | SoC timing (RULES §2) |
  | +0x00C | 0xA8 / 0x1FA | x window in 12-px units |
  | **+0x024** | 0x000E054E / 0x00280FF2 | **y window y0<<16 \| y1, 13-bit fields** (= SLVS-EC 13-bit line number [I]) |
  | +0x060 | bit8 toggled after reconfiguration | commit/latch strobe (`c0126480`, `c0127e58`) |
  | +0x068/6C/70/74 | 0x21 / 1 / 0x8000001A / 0x60012 | receiver start config (`c0127e58`, `c01280b8`) |
  | +0x08C | (y0 + (y1−y0)/4) << 16 | line-position interrupt (`c0128a88`) |
  | +0x184/188, +0x190..1DC | 0x3FFF/0x3FFFF = off | second window/region unit, `XC_ImageSensorIMX410::v28` → `c0125a68` |
  | +0x310/314 | copy of 00C/024 | second output channel window (`c0636048`) |
  | +0x800 | 0x112011 / 0x112013 | SLVS-EC link config from ROM table 0xC07D1780 (bit1 differs live/still) |
  | +0x980 | 1 | bit0 link on, bit4 hvbin bypass |
  | +0xB00, B08, B10..B28 | 0x101, 0xFF, lane map, 0x22222222 | link/lane setup (`c0128b68`, `c0128d60`) |
  | 0x300E1000.., 0x300EA024.. | lane order 0x76543210 … | PHY (`c0128b68`) |
  | +0x5D8 | 0xE38 / 0x1024 | lines per frame = VMAX (status) |
  | **+0x5F4/5F8** | **0x55A (1370) / 0xFFE (4094)** | status = **y1 + 12** in both modes → the sensor sends ≈12 lines after the window end [I] |
  | +0x584..5D4 | changing | line/frame counters |

  **No register could be identified as a data-type or EBD filter**; the only line selection the firmware programs is
  the y window. Candidates for an undocumented filter bit: +0x000 bits 21/22, +0x800, +0xB00 [I].
- **[C] Sensor writes outside the mode table** (all 569 call sites of `FUN_c0322c70` grouped by function):
  - power-on `IMX410::v1` (C03233D8): `00E9=80, 00D9=60, 04E6=00`, 10 ms, `00C5=80` (Z CAM/astro write 00), `00C6=00`,
    `0000=04`, `00CA=00`, then the mode table;
  - mode set `c03258c8`: table + `00CE=0` + `00D1/D2/D3` (24-bit 0x2FFFA ↔ 0x2FFFB toggle) [+ `0003`, `0022–0025` via v32];
    `v16`: `0011` 0→1; `v6`: up to 10 user override pairs (`mode_reg_add`);
  - stream/standby `v27`: stop `00CA=0, 0000|=2, 00C6=1, 00C5=11`; start `0000&=~2, 00C6=0, 00C5=0, 00CA=1`; `c03231c8`: `00CA=0`;
  - `v7`: `005C/005D` black level (exists, unused); `v15`: `0002` bit0 (shadowed); `v17`: `02B2` test pattern;
  - per frame: `0005–0008`, `003D–0040`, `041F 05E2 05A6 05A8 05E1`.
  None is an embedded-data enable that we can see; **`00D1–00D3` looks like a "settings tag"** of the kind Sony bodies
  read back from embedded data to confirm that a mode latched [I].
- **[C] Correction to RULES §9:** the "second, unused driver table" (0x460 stride, `C032A068`, writes `005B … 00CE 00D1
  00D3 00D4 00D5 00D7 00DA 010E …`) belongs to **`XC_ImageSensorIMX455`** — the fp image contains a full IMX455 driver
  (C0327790..C032A6xx: stream gate `019E`, test pattern `00C4`, gain `002D–0031`, `004D`, `03A2–03A5`).

### 4. Sibling sensors (address maps differ — concepts only)
- **IMX477 / IMX708** (CCS-style map, RPi drivers): 1 (IMX708: 2) embedded line(s) of register data sent on its own
  CSI-2 data type (0x12); both write **`0xBCF1 = 0x02`** in the common table (no comment; the only EBD-related write) —
  i.e. EBD is a sensor-side setting with a line count, and the receiver routes it by data type.
- **IMX283** (Sony 0x30xx map, SLVS/subLVDS family): **`EBD_X_OUT_SIZE` 0x3A54/55 (16-bit LE), 0 = embedded data off**
  (the mainline driver writes 0); `OB_SIZE_V` 0x3033 = OB lines output (16 or 4); `VWINPOS` 0x300F / `VWIDCUT` 0x3011 /
  `Y_OUT_SIZE` 0x302F / `WRITE_VSIZE` 0x3031 = Y_OUT + OB.
- **IMX455/571**: astro drivers never use EBD; OB is cropped in the FPGA.
- ⇒ For the IMX410 expect a **16-bit EBD width (or line count) register pair**, probably near the output-format block
  (`0001`, `001C`, `0019/1B/1D`, `0058`) or the init block (`00C4–00DA`). A single-byte write of 01/FF to one half of a
  width pair gives a ≤255-byte or ≤0xFF00 width — the latter should already have shown in row 0, so a pair is most likely
  something whose low byte alone is too small to notice, or an enable + size combination.

### Live test plan (minimal, in order of risk; needs the user's go-ahead and the camera broadcast)
| # | action | what it decides | risk |
|---|---|---|---|
| L0 | `mem get` 0x30100580..0x301005FC and 0x30100000/800/B00 × 10 in mode 8 and mode 10 (read only) | whether +0x5F4/5F8 = last header line number (expect y1+12) and whether +0x5F0 holds a first/EBD line number | none |
| L1 | `bufa_probe.py frame --ystart 0` with **y1 += 12** (0x30100024 low half 0x054E → 0x055A in mode 8; BUFA height 1358 → 1370; restore after) | shows the 12 trailing lines the sensor sends; a bottom embedded line or a status line would appear here | low: same mechanism as the y0 = 0 test; if those lines don't exist the frame never completes (RULES §15) → restore the window, no sensor write |
| L2 | mode 10, y0 = 0 (+L1's tail if it worked), **slow path** (`sweep.py`, write at a mode set, `poff 1` between) of the never-swept registers `00C4, 00CE, 00D4, 00D5, 00D7, 00DA` × {01, 02, 10, 80, FF}; criterion: row 0 / tail rows non-zero and non-pixel (byte histogram, Sony tags, the value 0x2FFFA/B of `00D1–D3` appearing) | finds a single-register EBD enable among the init-block neighbours | low–medium: init-block registers can stop the sensor (`00D9`, `00E9` do) → `poff` recovers; skip `00D9/00E9/0000/0013/0017` |
| L3 | same criterion, 16-bit pairs: write (rN, rN+1) = (00, 10), (00, 20), (FF, 0F) for adjacent pairs in `0004–0020` and `00C0–00E0` that are not in the stop list | the IMX283-style "EBD width" pair | medium: more points, same recovery |
| L4 | only if L0 shows a separate EBD/line-valid counter: toggle +0x000 bit21/22 or +0x800 bit1 (still value 0x112013) for one frame, then restore | whether the receiver has its own EBD/invalid-line filter | medium: receiver misconfig can stall BUFA/live view until restore; never during recording |
- Analysis tool: `row0scan.py` (scratchpad `ebd/`) already scans every `--ystart 0` capture for non-zero row 0; extend it to the tail rows.
- If L2/L3 find nothing, the honest conclusion is: the IMX410 EBD enable is not reachable by single/paired writes in the
  known address space, and register readback stays closed on the fp (no SDO wire).

## Live L0–L2 (2026-10-20)
- L0: 0x30100580… in mode 8 includes 0x055A = y1 + 12 (twice) and 0x087B002F, 0x104203BF, 0x102A013A.
- L1 (mode 10, window end 2062 → 2064/2066/2070/2074): 2064–2070 complete; **rows 2062+ are all-zero words**, exactly like
  row 0; 2074 never completes. So the sensor sends ≥8 rows after the image, all zero, like the leading row 0.
- L2 (slow mode-set path, `captures/ebd_l2/`): 00C4, 00CE, 00D4, 00D5, 00DA × {01, 02, 10, 80, FF}: row 0 and the 8 tail
  rows stay zero (00CE = FF: tail mean 0.1). 00CE = 02 moves the OB to ≈1014. 00D7 (all) and 00DA 01/FF stopped the sensor.
**Conclusion:** no embedded data found; the zero rows at both ends are blank lines. With SDO unwired, read-back on the
fp is closed for now (§L3 16-bit pairs not attempted).
