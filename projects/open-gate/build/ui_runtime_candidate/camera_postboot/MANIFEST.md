# OG3K UI candidate — camera postboot validation

Date: 2026-09-14 (Asia/Taipei)  
Camera: SIGMA fp, firmware `5.02.0.V91`  
Candidate AutoRun SHA-256: `3a2a58c9b7f20db8a2f47d0a62774fd1aabb8c396e734fe4780fac0e6b5f7c53`  
Candidate VSHL SHA-256: `583190c93bc56aa5b1429d9a61a22d72d5dd6715314c5d26005c7fd32f22ab06`

The candidate was started by a real cold boot: USB and external power removed,
battery removed for at least 30 seconds, booted without USB, then USB attached.
No hot loader or overlapping diagnostic was run.

## Timing gate

The resident state is 72 bytes at `0xC0732700..0xC0732747`.  Each acquisition
was a separately authorized exact read and was decoded locally with
`decode_og3k_ui_state.py`.

| Point | Pack | Stock records after install | Exact copies | Unique target bits |
|---|---:|---:|---:|---:|
| cold-boot baseline, before target screens | ready | 6,596 | 0 | 0/360 |
| after controlled OG3K Quick Set draw | ready | 41,133 | 164 | 164/360 |
| after Record Settings summary | ready | 46,010 | 165 | 165/360 |

The baseline proves that late private-NBR registration alone does not replay
records.  Opening Quick Set lazily parsed the active resource family: eight
`20_MV_Resolution` groups and eight paired `21_MV_Resolution` groups became
complete (144 layout records + 16 endpoint records), together with one active
QS limit and three active footer/cursor records.  Opening Record Settings then
added the exact summary record `0xC1A7246B`.  The remaining 195 bits belong to
screen/style variants not activated in this configuration; they are not claimed
as tested.

## Image-load evidence

The controlled second Quick Set draw used the cross-frame discipline documented
in `research/ui/README.md`.  The built-in GUI image log paired names at
`0xC055FDF4` with dimensions at `0xC055FE14`:

```text
OG3K_FONT.xci  -> 150,38,0,0
OG3K_QS.xci    ->  86,49,0,0
```

With the RES. tile selected, the same log reported all three footer resources:

```text
set_resolution_1.xci
set_resolution_2.xci
OG3K_SET.xci
```

`key QSON` and `display capture` both sometimes returned a USB timeout after
the camera had acted.  They were issued with `retries=0`; success was determined
from the GUI log and exact card-file readback, never from the missing reply.

## Visual evidence

| File | What it proves | Bytes | SHA-256 |
|---|---|---:|---|
| `settings_summary_clean_0469.jpg` | Record Settings shows CinemaDNG, 12 bit, OG3K, 29.97 fps after the first polluted draw was discarded | 144,947 | `f5d03e7b8c499bdf9d2c76b3a6ee064769124bd71ab2f9230801d2542f6b68bb` |
| `settings_resolution_three_choices_0471.jpg` | Native Settings selector contains UHD 3840x2160, FHD 1920x1080, and OG3K 3008x2000 | 162,341 | `c7b9972bf7ea2f8c624185eb7686dc1957a4b0513b9db9e1a143d2f84367d39b` |
| `OG3KQS2.XCI` / `OG3KQS2.png` | Quick Set main and small resolution values both draw OG3K | 42,657 / 33,543 | `bb221ba3862db5bdd65eab47bfd397d2b6eb6b28c489e1d88ad0fc8614afef4c` / `4037a0089e4039732ce61db222d447360b11883fd989c31d06e89320077375c8` |
| `OG3KQS4.XCI` / `OG3KQS4.png` | Selected RES. tile shows UHD/FHD/OG3K footer and cursor on OG3K | 42,130 / 34,299 | `5caca43560b740d2a7e81b2b600fa81de134d69ec6467113778d646e6572fb73` / `90a0dad04cb732b6c122e3a4ee311b0fc20fb6124d2ebc980ff16d4311075818` |

The XCI files are full 1024x682 L8A8 UI layers captured with the firmware's
`display capture` command and rendered by the project-neutral
`research/ui/tools/render_xci.py` tool.  Numbered XCI companions and failed/live
view attempts are retained here as experimental trace material, not acceptance
evidence.

## Result and remaining scope

For the tested CINE configuration, the UI drawing blocker is cleared:

- Settings summary: pass.
- Native Settings three-choice list: pass.
- Quick Set large and small OG3K values: pass.
- Quick Set UHD/FHD/OG3K footer and cursor: pass.

## Recording follow-up

The first user-driven OG3K attempt later created `CINEMA/A001_082` and froze;
the camera was recovered by removing the battery.  Exact card readback after
recovery still matched both candidate hashes above, so the installation was not
corrupt.  A fresh cold boot loaded the same three UI hooks and payload.

That same resident candidate then completed one FHD recording transition,
three OG3K transitions of about one second each, and three UHD transitions of
about one second each.  They created consecutive outer containers
`A001_083..A001_089`; after every controlled take `is_recording` returned to 0
and the USB shell remained responsive.  A post-recording second-draw Quick Set
probe again loaded `OG3K_FONT.xci` at 150x38 and `OG3K_QS.xci` at 86x49.  The
runtime state still reported the same resource context, pack ready, 164 exact
copies, and the same 164-bit active Quick Set set.

This passes the immediate record start/stop transition but not sustained media
writing or clip-content validation.  The installed SD card is too slow for a
long UHD/OG3K recording, so those tests were deliberately capped at one second.
The initial freeze was not reproduced and remains an unresolved incident rather
than a demonstrated UI regression.  Full evidence and the exact A/B control are
in `../camera_freeze_20260914/MANIFEST.md` and `../../ui_recording_ab/`.

This is still a debug candidate, not an `fpSup` product release.  No sustained
recording, playback, Still-like style, or other inactive UI variant was
validated beyond the short transition scope above.  The candidate remains
installed on the card; the paired
pre-candidate AutoRun/VSHL backup is in
`projects/open-gate/build/camera_backups/pre-ui-runtime-20260914/`.
The final confirmed setting was `SetMovRecSize = 4` on firmware `5.02.0.V91`.
