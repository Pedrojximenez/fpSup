# UHD24 recording capture: complete diagnostic, incomplete clip

Fresh diagnostic output collected from SSD; SD contains INFO.TXT only. Both were prepared with clean FPD003 directories before this boot. Original files remain on media and all outputs were copied into diagnostics/v003-uhd24-retry. Loaded code matches the verified payload exactly; allocation matches the finalized 120-record capture.

## Live state

- Samples 0–7: sensor 8, profile 5, recording flags [0,0].
- Samples 8–26: sensor 151, profile 429, recording flags [1,0].
- Samples 27–119: sensor 8, profile 5, recording flags [0,0].
- All 120 profile copies match stock parameters; no pointer/mode transition flags were set within individual snapshots.
- Active RAW dimensions 3856×2170, crop 3840×2160, zoom parameters 1600/1600. Static reduction enums for this profile are 0/0; their interpretation does not prove that every sensor pixel contributes.
- Acquisition state at C343A950 starts with zero dimensions, later holds width 3856 and height 2170, and retains them after standby. This confirms that acquisition fields can remain stale after recording.
- Sampling interval is nominal 250 ms; 19 active samples are not a calibrated clip-duration measurement. Recording flags may include setup/finalization.

## Clip

User reports self-stop at three seconds. Preserved all ten DNG frames, WAV and XMP under diagnostics/v003-uhd24-retry/clip with a SHA-256 inventory. DNGs declare 24 fps, 12 bits, uncompressed, 3856×2170 raster and 3840×2160 crop. Ten frames represent 0.4167 seconds at the declared rate. WAV contains 138005 stereo sample frames at 48000 Hz (2.875104 seconds). These lengths disagree substantially. No cause is established: this capture does not contain writer errors, queue occupancy, media latency or stop reasons. Prior self-stops without AutoRun remain relevant; neither SSD bandwidth nor the diagnostic is proven responsible.

## Next engineering step

The live profile ambiguity is resolved. Use confirmed route sensor151/profile429 as baseline for tracing capture-buffer sizing and full-height reduction semantics. No additional camera take is needed for that trace. No 3000×2000 patch is built or validated. Keep the user’s all-pixels-contributing requirement explicit; reduced sensor modes are not a demonstrated substitute.
