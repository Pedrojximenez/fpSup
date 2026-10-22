# fp PDAF shell commands and PD-line geometry: both gates are closed (with A7 III comparison)

Date: 2026-10-11. Prompted by a community question: "Can `pdaf caf` / `pd_*.csv` show DiffPh while recording UHD CDNG? Is PD-line readout programmed in the video modes?"
Method: capstone disassembly of the firmware image plus the IMXOBJ00/IMXCFG00 dumps in `research/imx410/captures/NIKON_D80_preformat_2026-08-17/`. An independent subagent tried to disprove each claim. All offline, with no camera access.
Chinese version: [PDAF_SHELL_AND_PDLINE_GATES_2026-10-11.md](PDAF_SHELL_AND_PDLINE_GATES_2026-10-11.md)

## Conclusions

- **(a)** `pdaf caf/sequence/image/invalid` aren't commands. They're `af dbg` debug bits. The command that actually measures DiffPh, `af msr pddef`, is blocked by AF-model vtable `+0x184`, which unconditionally returns 0, so **by default it does nothing and prints nothing**.
- **(b)** PD-line geometry doesn't exist on the fp **in any mode**, video or stills. Sensor-info `+0xFC` works as a "sensor supports PDAF" flag, and it's 0 for IMX410, so the geometry getter is never called. Even if it were called, IMX410's `+0xBC` is an empty stub.
- Both agree with the 08-18 RAW scan ([investigation report](SIGMA_FP_PDAF_INVESTIGATION_REPORT_2026-08-18.md)) and the 09-27 review ([cross-camera](CROSSCAM_PDAF_FEASIBILITY_2026-09-27.md)). What's new in this note is the `+0xFC` flag and the pddef gate.

## 1. `af msr pddef` and the pdaf debug bits

- **The gate.** `setParam @ 0xC0233A98` checks it starting at 0xC0233AAC: `bl c02a4398; ldr r3,[r7,#0x20]; add r3,#0x184; ldr r3,[r3]; blx r3; cmp r0,#0`. The instruction sequence matches the gate in `CalcCafDriveSpeed` exactly.
- **The object.** It's the static singleton `0xC3404678`, built by FUN_c02a4528. The constructor first stores base vtable `0xC096B150` (`AfMgrModelSingleOem_Sig`), then subclass vtable `0xC092B8D0`.
  - `+0x20` holds the vtable **header**: word 0 = 0, word 1 = typeinfo.
  - The `+0x184` offset is relative to that header.
- **The slot.** `0xC092BA54 = 0xC029BA08`. The base class has the same value, so the subclass doesn't override it. The function body is `mov r2,#0; mov r0,r2; bx lr`: no branches, no global reads.
- **The error message.** `###ERROR### cannot be executed the function is disabled.` goes through `FUN_c022cbf0(0x40,…)`. It only prints if both of these hold:
  - an output callback is registered (0xC33D30E4), and
  - debug bit 0x40 is on (`af dbg 1 7`, "measure").

  Our first answer said the command prints this error, which was wrong.
- **How `af dbg` works.** The handler is FUN_c03dca18, registered as "dbg" in command table 0xC0BAE014.
  - Argument 1: 0 = reset, 1 = printData, 2 = setData.
  - Argument 2 is n; the handler writes mask 1<<(n-1) to 0xC3207030.
  - The four pdaf strings are items 17–20 of help table 0xC0BAD2BC.
- **What reads each bit:**
  - 0x10000 sequence: DoOneShotRanging, DoContShooting, isExecOnPdafData
  - 0x20000 image: calcJudgeImageParamaeter, calcJudgeImageYuvCheck, FUN_c0283df8
  - 0x40000 invalid: **no reader found statically** (a dead flag)
  - 0x80000 caf: CafPdDriveMain, CalcPdCafDriveDir, CafMode5_*

  Every reader is debug output on the PDAF path, so the bits do nothing unless that path runs.
- Note that `af msr` is not read-only: it can enter an S2 capture flow.

## 2. PD-line geometry (`PDAF size=… line=…`)

**Where the printed fields come from.** `calcJudgeImageParamaeter @ 0xC0283830` prints them. Fields `param_4[0x27..0x2B]` are 0x14 bytes that `FUN_c0312ac8` copies from 0xC343A68C, and `FUN_c0312ac8` is the only writer of 0xC343A68C.

**The `+0xFC` gate.** `FUN_c0312ac8` checks it at 0xC0312AE4 with `ldrb r0,[r0,#0xFC]`. Here r0 = `FUN_c0322020()`, the sensor-info struct at 0xC2F1E654, so the byte read is **0xC2F1E750**.
- At boot it's initialised to **0** from ROM 0xC0B5F89C (at 0xC0322F88). The dump also shows 0, and nothing else writes it.
- On IMX455 the same field comes from 0xC0B728A4 and is **1**. So `+0xFC` is effectively a "sensor supports PDAF" flag.
- `PdafCorrect` (FUN_c030fb20) is blocked by the same `+0xFC` check.

**The object is IMX410.** FUN_c0311448 writes `[0xC3201B14+0x18] = FUN_c0322e48(0)`, which is always 0xC343B588. That object's `+0xD0` is 0xC0B5FCC0, whose typeinfo is "XC_ImageSensorIMX410". The dump matches: `+0` = 0xC2F1E654.

**Even with the gate open, the geometry would be zero.**
- IMX410's `+0xBC` and the base class's `+0xBC` are both 0xC0322330 (`XC_ImageSensor::v45`). The body is `push{r4,r5}; mov…; nop; nop; pop; bx lr`, which never writes the output buffer.
- `+0xC4` (0xC0322370) is empty too.
- The caller, Face (0xC027B4B0), first copies 0x800 bytes from all-zero ROM at 0xC0921A1C into the buffer, so the geometry fields stay 0.

**For comparison, IMX455 implements it.** Its `+0xBC` = 0xC0329BC0 is real: FUN_c032c4a8 looks up a per-mode PD record table with 0x5C bytes per entry.

**There's no other source.**
- IMX410's `+0xD8` holder object (0xC343B67C) points only to mode table 0xC0B5FDAC (0x46 entries). It has none of the second PD table that IMX455's holder has (from FUN_c032c710). In the dump its `+4` = 1 is a guard word, not a table.
- The fp firmware also contains the IMX455 second singleton (FUN_c0322e48(1) → 0xC343B6AC), but this path never uses it.
- `calcJudgeImageParamaeter`'s return value ignores the geometry. It only checks FUN_c02aa7c0's vtable `+0x20` ("sensor modes that cannot use phase detection").

## 3. Comparison with the Sony A7 III 4.04 (summary)

Full details are in `sony_a7m3/a7m3-re-20260904/outputs/sony_a7iii_v404_imx410_pdaf_reverse_comparison.md` and `…/sony_a7iii_phase_data_route_followup.md`.

| | A7 III | fp |
|---|---|---|
| IMX410 driver | RTTI `C_ImagerCtrl_IMX410` | `XC_ImageSensorIMX410` |
| Register overlap | 155 of the fp's 161 mode registers appear in Sony's write tables (96.3%). The best mode pairing matches 144/155 values. | — |
| Normal read path | `0x003D–0040`, `0x041F`, `0x05E2` bit 0 | Same |
| ZAF exposure | `SetExposure_ZAF`: `0x000B–0010`, `0x0036` | Not seen in the static table or the dynamic writes found so far |
| ZAF read | `SetRead_ZAF`: `0x0047–004A`, `0x0424`, `0x05E2` bit 1 (identical in A7C 2.03) | Not seen |
| Downstream | DFE ZpdPre/FOPD → AFMAP; ZPD defect/fitting buffers; `A_CAP_RAW_PHASE_DIFF_INFO` has a real handler | No equivalent; `+0xFC` = 0, `+0x184` = 0 |
| VC1 | DFE output formatter `Ofmt_Mwrap`, **not** a sensor-native PDAF channel | — |

**What this means.** On the A7 III, phase AF needs three things together: sensor-side ZAF readout config, DFE phase extraction, and calibration data. The fp has none of the three.

**What's still open.** We haven't established whether the fp's silicon carries masks at all. The A7 III's 693 PD points don't prove the fp's variant has them. The only test that could tell is a minimal readback/ACK probe of `0x0047–004A` on the fp. We haven't run it, because earlier readout-window writes hung the camera. "Not seen on the fp" covers only the parts we've searched, not an exhaustive check of the whole binary.

## 4. Assessment of the proposed approaches

- **Feed the signed defocus straight to 0x9413.** Not possible: the data source doesn't exist. Force-enabling `+0x184` or `+0xFC` would only make the code read the sentinel `-0x80000000` or all-zero geometry.
- **Subject lock with hold-and-correct, driving 0x9413 from CDAF/DFD stats** ([DFD_VIA_AF_STATS](DFD_VIA_AF_STATS.md)). A viable direction.
- ⚠ That 0x9413 works during recording is still only a strong inference from the gate code on our side ([PTP_FOCUS_RECORDING](PTP_FOCUS_RECORDING.md)). We haven't verified it on the camera.
