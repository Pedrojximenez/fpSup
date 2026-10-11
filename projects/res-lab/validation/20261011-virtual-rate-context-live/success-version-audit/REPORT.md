# A001_193 successful SSD recording: date and predecessor audit

The strongest supported predecessor is the September 29 H2 RAM prototype,
before the new CinemaDNG rate-tag hook was successfully installed. This is a
version-family inference. An exact installed BIN or Git commit is not identified,
and no historical record located so far explicitly names this exact dated take.

## Original sequence evidence

The originals remain at `/Users/dido/Movies/fpsup/hightspeed/A001_193`.
First/middle/last DNG internal DateTimeOriginal and WAV RIFF DateTimeOriginal
agree on **2026-09-29 09:14:25 +08:00**. The final DNG filesystem time is
09:14:46. The preserved sequence has4809 consecutive frames and20.069771seconds
of audio, supporting the user's prior240 capture report. All sampled files are
1008x672,12-bit, uncompressed, with992x662 crop@(8,5), and a legacy30000/1001
FrameRate. Software is the originalSIGMA fp Ver.5.02.0.V91, not a custom
Sensor Lab build identifier. Examined standard tags do not identify a mod hash;
the proprietary MakerNote has not been fully decoded.

## Historical clock and installation chronology

Selected evidence comes from the project's preserved Open Gate research session
`5acbf12f-3568-4c49-9959-d190b5001045`. Historical commands are retained as data,
not executed. Two original screenshot JPEGs were recovered from relevant records.
Their camera serial agrees with the successful DNG serial.

The screenshots' camera wall times fall about56–60seconds ahead of host capture
windows. Their JPEG DateTimeOriginal is invalid and OffsetTime is a zero/default
value; the comparison uses ModifyDate wall time and host+08:00, not the misleading
JPEG composite UTC date. With unchanged clock/timezone between nearby captures,
the clip start corresponds to host local **09:13:25–09:13:30**. The interval is
an inference including one-second tag precision, not oscillator calibration.

| Host local time | Archived observation |
| --- | --- |
|08:47–08:48|H2 uses p13/fill, M12,1008x672,992x662, RWZM2048/1024; actual25-pair canvas readback saved.|
|08:55|H2 reinstalled with the aspect correction; payload/hook readback verified, actual27-word recipe agrees with host.|
|09:01|Contemporaneous report explicitly says sensor240 while application/container30.|
|~09:13:25–30|Inferred host start of the user's preserved successful take.|
|09:16|First new rate-hook install attempt fails at preflight, zero writes.|
|09:17|Contemporaneous report says the previous H2 without the new rate hook remains installed.|

This chronology and the file's legacy29.97tag agree. The October1 r10 card is a
different later success reference and cannot currently be called this sequence's
exact version. File modification dates alone are insufficient: a RAM-installed
prototype can differ from the card on disk.

## New processing-field difference

The contemporaneous H2 install selected nativep13; the frozen r10 replay selected
p83. Applying the actual archived25-pair live readback to independent native
profile defaults leaves one differing canvas word, excluding FPSLATCH+0x30:

|Field|September29 p13 base|r10 p83 base|
|---|---:|---:|
|PARAM+0x88|0|4|

The actual25-pair H2 readback does not overwrite+0x88. This is distinct from the
current v15 restoration, which matches the later r10/p83 recipe and sets+0x88=4.
Both implementations replace+0x30 from FPSLATCH; an actual full65-word canvas
snapshot at A001_193's start is unavailable. This comparison therefore excludes
that word instead of guessing its recorded value.

The difference is a concrete new comparison target, **not an established cause of
early stop or permission to assert a successful fix**. No camera/card changes,
recording, obsolete fixed-cave installation, or production-source changes were
made during this audit. Currentv15 remains failed on sustained recording.

Machine-readable metadata, original file hashes/stat, selected timestamped
historical excerpts with source-line hashes, original screenshots, clock bounds,
native profile-source hash and independently derived field comparison accompany
this report. `audit_success_version.py` reproduces the bounded read-only audit.
