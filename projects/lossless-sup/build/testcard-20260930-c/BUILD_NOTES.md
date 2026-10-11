# fpLossless TEST card — 2026-09-30

**Not written to any card. Not run on the camera.** Direct compression + current
USB shell + Fast Start 2, per `fpSup/lossless/manifest.json` `requested_test_build`.
No menu, OpenGate or gyro. Banner: `fpLossless TEST`.

## Command

```sh
cd fpSup && python3 -B lossless/build_card.py --out <this directory>
```

## Outputs (SHA256SUMS)

| file | sha256 |
|---|---|
| AutoRun.txt | `35a3141f…f775` — **byte-identical to the Fast AutoRun already on the user's card** (DEPLOY.md, 2026-09-30 r2): only `fpSup.BIN` changes (SUP_BUILD_RULES §5) |
| fpSup.BIN | `376a961b…dddc` — 32,768 B, 11 sections, entries: USB shell worker, then the lossless launcher |
| lossless.bin | `f1422536…2c1b` — the launcher section on its own: 888 B launcher/shims + 13,416 B C |

Rebuilt three times from the same sources: `AutoRun.txt`, `fpSup.BIN`, `lossless.bin` identical each time.

## What it does on the camera

1. Launcher (after the shell's worker): one 64 KiB USER block of its own (`C001D740/C001D7F0`, class 0,
   not the gyro/pool word), copy, zero state, D/I publish, resident init.
2. Arms four sites **all or nothing** — each must still hold its stock word; 48 B of veneers and a state
   record come off the cave bump (`0xC072E060`), never a fixed cave address:

| site | stock | becomes |
|---|---|---|
| `C03A33C8` REC preparation | `EBFFFC1A` | `bl` veneer → reserve workspace, start take |
| `C038BFF0` creator enqueue | `E12FFF33` | `bl` veneer → hold / pass (only if target is `C037DD50`) |
| `C0398D88` stop check entry | `E92D49F0` | `b` veneer → finish held frame, then the displaced push, then `C0398D8C` |
| `C03A5490` final flush | `EB0BD652` | `bl` veneer → trailer + length, then `C069ADE0` |

   Each site is also a 4-byte section holding its stock word: stage2 journals it and the power-off
   callback writes it back.
3. **Never refuses a recording.** If lossless cannot be prepared, the take is stock RAW.
   Readiness (codec/writer/header/playback/storage/REC gate) and CINE/CinemaDNG/SD are
   **asserted for measurement** in `card.c test_readiness()`, not proven.

## Verified offline

- 237 host/ARM tests pass across the lossless tree, 0 skip.
- `test_card_emulation.py`: the real loader + stage2 load this `fpSup.BIN` in Unicorn against the pinned
  image; the launcher runs from the staging buffer; every hook is entered through its veneer and reaches
  its C body and the firmware with the right registers and stack. 10 tests; 7 injected launcher/shim
  defects all caught; `card.S` restored byte-for-byte.
- **Not emulated:** scheduling, the codec hardware, SD, real frames.

## First camera session — needs the operator's authorisation for that run

1. Deploy `fpSup.BIN` (AutoRun unchanged). Boot; the banner reads `fpLossless TEST`; `ver` answers.
2. Hook sanity (SUP_BUILD_RULES §6): boot, do not record, power off, power on — about ten times.
3. FHD 12-bit 29.97 CinemaDNG, SD, static scene, ~5 s. Stop. Confirm the camera is responsive.
4. `card_status.py --dry-run` → ask for consent with that address list → read. It answers
   **question 1** (a frame's own allocation vs the told length) directly.
5. Pull a few frames; LibRaw-decode compressed and RAW ones; count files against stock.
6. A noisy scene (high ISO, cap on) for the refusal check (question 3).

If anything wedges: unplug/replug USB first, not a power cycle. A power cycle restores every site.
