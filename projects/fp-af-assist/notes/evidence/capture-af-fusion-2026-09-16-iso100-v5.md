# ISO 100 return baseline — 2026-09-16

原程式／證據目錄：[research/autofocus/captures/af-fusion/2026-09-16-iso100-v5](../../../../research/autofocus/captures/af-fusion/2026-09-16-iso100-v5/)。筆記已集中至 fp-af-assist；下文歷史結果與限制保留。

Session: `2026-09-16-iso100-v5`, collector schema v5, binary record version 2.
User confirmed the requested return to fixed ISO100 before collection.

## Acquisition and validation

- 60 records, sequence 0–59; all 60 snapshot-coherent.
- 0 missing sequences, duplicates, invalid replies, or out-of-order records.
- 1 prior-session reply rejected by session nonce.
- Snapshot duration 4–19 µs; host USB round-trip 0.410–1.259 ms.
- Post-capture echo handler directly read as `0xC03D99A0` (restored).
- No camera AF/exposure setter was called in this session. The collector temporarily installs its
  snapshot handler in the shell work area and restores the echo dispatch afterward.

## Stable values

| Field | Value |
|---|---:|
| IMX410 relative gain / AF RGBgain | 117 |
| Applied analog code | 985 / `0x3D9` |
| Analog ratio ×100 | 131 |
| HCG RAM flag | 0 |
| AF sensitivity | 219 |
| AF shutter raw | 8333 |
| AF f-number raw | 2164 |
| H/L area index | 0 |
| Sweep index / mposm | 9 / 11068 |
| H median | 24718.5 |
| L median | 57894 |

Direct 16-word read at IMX410 singleton `0xC343B588`, after collection:

```text
C2F1E654 00000008 00000008 00000034 00000034 00000034 00000075 00000075
000003D9 000003D9 000003D9 00000083 00000064 00000000 00000064 0000410F
```

This additionally gives overflow digital=100, inter-node trim=100, and force-LCG byte `+0x37=0`.
These values are sensor-driver RAM; this session did not directly read the sensor's I2C latch.

## Independent mode query

`imager mode_now` (reviewed `FUN_c03eb8c8`, no exposure/sensor-setting setter):

```text
No ,mode                         ,enum,bit,size     ,frame ,fps ,aspect ,crop,
053,MONIT1_60                    ,0008, 12,2016x1344,016683,0060,  3: 2 ,full,
shutter:00016663,gain:000117
frame_count:00254651,trans_count:00254622
gain_state: through
small_raw
base_size h:2016 v:1344
raw_zoom  h:1024 v:1024
hvbin     h:0001 v:0001
bef_size  h:2016 v:1344
offset    h:0000 v:0000
v_down_sample    v:0001
```

## Interpretation limits

H/L medians returned close to the previous ISO100-b baseline (−0.234% / −0.105%). This does not
separate clipping, scene variation, sensor noise and AF processing at high ISO. No synchronized image
or histogram was recorded. The sweep index/mposm stayed fixed, so these are idle observations with
DFD eligibility undetermined. Face/AAT rectangles were zero throughout.

The earlier `check_convert_abs_gain` and no-argument `high_gain_off` calls in preceding sessions
were mistakenly described as read-only. Code audit shows they change gain / force-LCG state.
The current explicit ISO100 setup and independent telemetry confirm the present state; they cannot
recover the force-LCG flag's unknown value before the earlier setter call.
