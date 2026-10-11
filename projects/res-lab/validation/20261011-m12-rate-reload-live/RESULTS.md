# M12 rate-notification candidate: on-camera validation, 2026-10-11

User explicitly requested on-camera testing after the private git:3000 backup.

Current result: deployment, running-code verification and live trials completed.
The rate notification correction does NOT fix the 240/280p premature stop or
preview mosaic. Detailed results below supersede the original USB blocker.

## Verified deployment

- Read and backed up AutoRun.txt, LOADER.BIN, 32RESCUS.BIN and 50RESLAB.BIN
  using exact directory lengths and maintained getfile with tagged chunks.
- Existing consumer matches frozen v38 outside the 96-byte CFG record. Saved
  CFG is structurally valid and its FNV checksum passed. Preserved those exact
  bytes in the candidate.
- Candidate source SHA-256:
  `57d3587cb6df182a2a8de613ba5458e6e902182d5ca242a1ee63fd6e6c1428ca`.
  Installed 183104-byte consumer, with saved CFG, SHA-256:
  `a28babd6f65a1086bf401d1fed09a162090079ce478e6c4d88d37bd463669641`.
- Full consumer readback equals the prepared file. Full readback of AutoRun,
  loader and producer after installation equals each corresponding backup.
  See `deployment/deployment.json` and its saved before/after files.
- Before reboot, runtime is M12 AUTO, 992x662, bin1x1, no crop/desqueeze,
  12-bit, virtual rank23976, sensor239.76023976, engine239.76023865. The prior
  record log identifies SSD, 5000Mbps, req=fin94 and a vbuf stop.
- Sent one reboot only. USB I/O error is retained and the reboot was never
  replayed. Exact owned fpshd62470 cleanly released via socket QUIT; new
  task-owned daemon66057 started. HDMI shows green STBY after boot.

## USB blocker

- Fresh enumeration confirms SIGMA interface0 is class6 and exclusively owned
  by pid62526 `/usr/libexec/ptpcamerad`.
- A read-only status query returns LIBUSB_ERROR_ACCESS.
- Automatic approval review rejected terminating the exact verified claimant:
  user authorized camera testing but had not explicitly authorized stopping
  another service. Consent requested; no termination or workaround performed.
- Raw enumeration evidence: `usb-after-boot.plist`. Full shell transcript:
  `commands.jsonl`.

No claim that early recording termination, mosaics, sustained 240p or continuous
preview has passed. Candidate code/header verification and normal-UI recipe
restoration remain necessary before any recording trial.

## Authorized continuation and exact running code

The user explicitly authorized USB recovery. Fresh IOUSB inspection found the
SIGMA interface already class255 with no claimant, so no process was stopped.
Existing task-owned fpshd66057 was reused. `connected-runtime.json` verifies the
entire 50,436-byte immutable v10 core and both rate-commit shims; normal UI
restored M12 992x662, RAW1008x672, 12-bit, bin1x1, crop0, desqueezeOFF.
Same-carrier selections increment RATE_LV_RELOADS with no pending owed flag.

## Recording results (UHS-II SD, original batch size unless stated)

| Trial | Clip | Requested / finished | Stop and interpretation |
|---|---|---:|---|
| reload-120-control | A001_046 | 400 / 400 | Button, green STBY. Scene ROI freezes 116 HDMI frames; no continuous-preview pass. |
| reload-240-a | A001_047 | 94 / 94 | vbuf/94, raw1, automatic stop. |
| reload-280-a | A001_048 | 94 / 94 | vbuf/94, raw1, automatic stop. |
| reload-280-eightbit-a | A001_049 | 94 / 94 | 8-bit/757248 bytes per DNG also stops at descriptor limit. |
| reload-280-eightbit-observe | A001_050 | 94 / 94 | Added fixed scalar observations; last sample free=1, captured=94, requests=3, finished=3. These independent reads are not atomic. |
| reload-120-observe | A001_051 | 94 / 94 | Dense observation perturbs the nominal control; not valid as proof that ordinary120 fails. |
| reload-120-quiet | A001_052 | 388 / 388 | No camera polling during frames. Button stop, STBY. |
| reload-240-quiet | A001_053 | 94 / 94 | No camera polling during frames; vbuf still occurs. |
| reload-240-bulk16-quiet | A001_054 | 94 / 94 | Actual FS batch reduced64→16MiB, later batches14–15 frames; initial exhaustion unchanged. Restored original literal with readback. |

All completed rows have native REC0 and positive final HDMI STBY. Stop toggles
were sent only after fresh REC1; no stop was sent after an automatic stop. Quiet
trials do not observe the exact transition time; their nonzero finished counts
and HDMI establish that recording occurred.

The 8-bit menu uses SetMovCinemaDNGQuality enum4 (12bit enum0). An initial
incorrect enum2 guard stopped before any MOV key. Empty failed-preflight folders
are not recordings. `SetMovImageQuality` was an unavailable getter, not a setter.
The fetch runner's first two import errors also occurred before camera access.

## Picture and RAW evidence

Every frame of the original 240/280 HDMI captures was checked for scene changes;
unique transition contact sheets retain each distinct picture. 280 frame55 has
a clear vertical scale mismatch and remains byte-identical through85. The
120 scene freezes52–167. Automated equality and selected-frame visual review
are separate; absence of a magenta score is not a no-mosaic verdict.

A001_046 frames1/200/400, A001_047 frames1/47/94 and A001_048 frames1/47/94
were fetched through maintained getfile with source-address-tagged chunks,
exact1095168-byte lengths, fresh native/HDMI standby and known filenames.
All nine parse and decode; raw shape672x1008,12bit, crop992x662. The RAW contact
sheet does not show the same preview tiling. Sampling three frames per clip is
not a complete sequence integrity or cadence proof. DNG FrameRate remains
120000/1001 on v10, confirming the separate metadata propagation defect.

## Bounded batch-size experiment, withdrawn

Read the actual vtable words: XC_MediaFileSdCard vptr C0B972C4 has two prefix
words. Wrapper C0366168 uses +0x18 → C03686C0 → C063B898 → C063F380.
C03689C8 is +0x20 (rename), not the scatter-write call. Some earlier project
notes incorrectly equated v6 with offset0x18; they are not used as proof here.

Native C03A5050 loads C0B9E5D8 =64MiB and forwards it to C0366790, then
C0369058 → C063B908 → C063F220, which sets volume+4828 and rounds to a cluster.
This is distinct from C359BE98, the rec-log display constant. The exact native
setup body was executed offline with only calls at declared boundaries modeled;
16/64MiB, work buffer, completion callback and non-bulk fallback checks passed.

A single data word C0B9E5D8 was temporarily64→16MiB. No code, pool, descriptor
count or card file changed. `reload-240-bulk16-quiet-mutation.json` records the
fresh STBY proof and verified restoration to64MiB. The experiment did not fix
the stop and is not included in production source or the v11 candidate.

HDMI is archived as FFV1 only after full decoded RGB byte count and SHA256
match; task-owned RGB temporary files are then removed. Camera files remain.
