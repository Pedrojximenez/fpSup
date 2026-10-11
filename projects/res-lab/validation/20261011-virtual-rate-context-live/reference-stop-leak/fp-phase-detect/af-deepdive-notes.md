# Autofocus deep-dive — why it pulses and every path to fix it (2026-10-10, read-only decode)

6-agent parallel decode. The pulsing is **largely a firmware/algorithm choice layered on a hardware
question that is NOT yet settled.** One decisive camera test decides the ceiling.

## THE CENTRAL UNRESOLVED CONFLICT (do not overclaim either way)
The agents disagree on whether the fp sensor has usable phase-detect (PD) pixels:
- **Evidence FOR phase hardware (agent "why-cdaf"):** the firmware has a sensor-mode-dependent PD-LINE
  READOUT configurator (0xC0283830/0xC0283B20: "PDAF size=.., line=.., interval=.., sensor=.."), PD
  defect-correction coefficients ("PDAF Marginal Correction Coefficient", 0xC0BB88CC), a phase→signed-
  defocus path (AfMgrMeasurePdafDefocus 0xC091AF54, "DiffPh %d Reliability %d", pd_dir_route /
  pd_change_speed_route = direction+speed in one shot), a hybrid-AF stack (AfMgrProcessHybrid 0xC091EE70)
  and motion prediction — and DEBUG DISABLE commands ("pdaf invalid : disable phase detection",
  "pdaf caf") that would only exist if the path normally runs. Sensor = Sony IMX410, the same part Sony
  runs hybrid PDAF on in the A7 III.
- **Evidence AGAINST (agents search-loop / dfd / prior-art + community):** the community concluded no PD
  hardware (digest_gyro_og_chat.md:54, Axolotl_MX "the sensor doesn't have any specific hardware for
  phase detection"); focus-ai empirically measured ZERO single-frame optical direction signal on two
  lenses; and the PDAF code is argued to be dormant shared-platform (fp L / other bodies) code with
  nothing feeding it on the fp.
- **Honest reconciliation:** the firmware unquestionably CONTAINS the full PDAF/hybrid machinery, and
  there is PD-line-readout + defect-correction config in the image — but whether valid phase pixels are
  actually read out and produce a usable DiffPh/Reliability **in the user's UHD-24p CDNG video mode** is
  NOT proven offline, and community field tests found no usable phase signal. This is THE question.

## THE ONE DECISIVE CAMERA TEST (read-only, needs the user's go-ahead)
Hook/log `DiffPh` + `Reliability` (func 0xC0234A4C, string 0xC091AFD4), the `pd_raw_size`/PDAF-size
config (0xC0283830/0xC0283B20), `pd_dir_route`, and the `pdaf caf` output **while recording UHD 24p
CDNG**. If those values are valid/non-zero → the fp reads real phase in video, and snappy non-pulsing AF
is achievable. If the PD lines are only populated in a stills/AF LV mode not used for video → fall back
to the DFD/subject path below. Nothing here has been run; all taps are offline candidates
(native_hook_sites.json: hardware_io_performed=false).

## NEW (2026-10-10): the test is likely RUNNABLE via the existing debug shell — no patch
Confirmed a `pdaf` debug-command group in the image (help lines, verbatim):
- `pdaf caf`      : "pdaf caf debug output."
- `pdaf image`    : "pdaf subject determination debug output."
- `pdaf sequence` : "pdaf sequence debug output."
- `pdaf invalid`  : "disable phase detection."
Plus a PD telemetry logger `pd_%04d%02d%02d_%02d%02d%02d.csv` and live per-area readouts:
`DiffPh %5d Reliability %5d g_af_h_data %5d`, `pd_area=%u, rel=%d, diff_ph=%d, err=%u`,
`pd_area=%u, rel=%d, thr=%d , diff_Ph=%d, ty..`, `PDAF size=%u, %u, line=(%u,%u),(%u,%u), interval=%u, sensor=%`,
`PDAF Marginal Correction Coefficient TEST` / `PDAF Cor: %d` / `pd_cor %6.5f pd_cor_total %6.5f max_dp %d`.
So the decisive "is phase live in UHD video" question is an OBSERVATION, not a patch: run `pdaf caf` /
`pdaf sequence` (and/or the pd CSV log) while recording UHD 24p CDNG and read whether DiffPh / Reliability /
rel / diff_ph are valid and non-zero. bei's USB shell is the likely host for these commands → coordinate.

## WHY IT PULSES (not disputed)
The live continuous AF the user gets is CONTRAST (CDAF): the focus metric (green-band sharpness —
peakNow 0xC32915C4, peakMax 0xC32915C8, target gafpos 0xC32914E0; "AF:%d peak=%d g_afpos=%d" 0xC091A130)
is a **sign-less scalar** — it tells you how sharp, never which way. To get direction the firmware must
dither the lens and watch the metric; that probing IS the wobble. Named in code: AfMgrProcessRocking
0xC091F7F8, shell "cafwob / caf drive wobbling", and the flat sharpness peak forces overshoot-and-return
to confirm. The AMOUNT/persistence (wobble amplitude/step, caf_stable_time re-validation, dead-band,
no sign memory) are firmware parameters, not hardware.

## PATHS TO BETTER AF (all buildable, all need the camera test above first)
Common actuator (verified): **GIMBAL 0x9413 ExecAbsoluteFocusDriving** (0xC04EF298, sub-cmd 6) drives the
lens to an absolute position and is designed to work DURING recording.

1. **Phase-servo (best, IF the camera test passes):** feed signed PDAF defocus straight to 0x9413 — lens
   goes to focus, no gradient probing, no wobble. Depends entirely on the decisive test.
2. **Subject-locked hold-and-correct (strong, hardware-independent):** targeting is FULLY decoded —
   DetectionMgr emits per-detection {label, x, y, w, h, score} + face count ("%s:x=%d,y=%d,w=%d,h=%d,
   sc=%d" 0xC2DFB55B), **eye detection is real and separate from face**, plus a colour/subject-tracking
   model (0xC37CDFA8) and motion prediction. Policy: pick eye>face>box, drive 0x9413 to the subject,
   then HOLD and only re-drive when a change metric exceeds hysteresis — replaces the contrast dither
   with a servo. Smooth tracking.
3. **DFD/geometry-seeded single-probe (minimise wobble):** the repo "DFD" taps are NOT a true signed
   defocus (mposm 0xC3291958 is actually the AF TARGET; peakNow/peakMax are contrast d600 min/max search
   bounds). But subject size→distance geometry (geometry.py: pos = a·d²+b·d+c) plus ONE deliberate micro-
   probe to resolve near/far gives a direction, then jump to target via 0x9413 and hold. Pre-roll a
   whole-scene depth scan to solve per-subject scale before rolling.
4. **Open-loop to lens distance:** the L-mount lens reports DefocusPerPulse, focus-speed limits, focal
   range, and capability flags (CanGetCurrentDistance, NeedFocusPlsReset). If CanGetCurrentDistance==1,
   compute a pulse target from an estimated distance and drive once (no hunt). Per-lens one-time
   calibration (home to infinity if NeedFocusPlsReset==1).
5. **Light-touch tuning (quickest):** patch the stock CAF params in RAM — raise dead-band + lock-hold,
   stretch re-validation, shrink wobble amplitude, clip drive-pulse max (AfMgrModelContinuous_w71c1 /
   ProcessContShooting). Calms pulsing with no new logic, IF those CAF processes even run during CDNG
   record (unknown — camera test).

## THE SDK CONFIRMS THE TARGETING SURFACE
The Sigma SDK (notes/sdk-cross-reference.md) exposes FaceDetectionAF, AF-area position/size, AFMode over
documented USB commands, and DataGroupFocus as an IFD-tag channel — so the targeting half is documented,
not guesswork.

## CEILING (honest)
- Single-shot AF: can be made as good as stock, likely snappier (seed + absolute drive).
- Continuous/tracking: can be made SMOOTH and non-pulsing via subject-lock hold-and-correct (path 2),
  hardware-independent. True phase-servo (path 1) is the dream and hinges on the one camera test.
- What firmware alone cannot create: a signed single-frame defocus cue IF the PD pixels are genuinely
  absent/unread in video — then direction always needs at least one probe move (tiny, not continuous).
- Everything is decode-only; nothing run on the camera. The decisive test gates which path is real.

## Corrections to earlier notes
jetson-autofocus.md:36 ("No phase-detect (CDAF sensor)") is too strong — the firmware has a full PDAF
stack and PD-readout config; whether it's live in video is the open question. gimbal.md's relative-only
claim was already corrected (absolute 0x9413 exists).
