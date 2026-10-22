---
name: fp-merged-card
description: "Build and verify SIGMA fp development cards containing open gate, gyro and USB-shell components through the maintained shared loader and composer. Use for merged-card or Fast Start artifacts, exact-byte provenance and offline boot validation; deployment follows the user's authorized scope."
---

# SIGMA fp development cards

Adapted from the project's Claude Code skill on 2026-09-27. Default repository: `/Users/dido/Developer.localized/SIGMAfp_re`; honor an alternate checkout. Paths below are repository-relative.

Before producing or modifying a card, read `fpSup/AGENTS.md` and the full `fpSup/SUP_BUILD_RULES.md` (or English counterpart), then inspect the selected builder. Those maintained contracts supersede historical command examples. Keep the shared loader/stage2, journal, cache publication and component contracts together; do not fork a loader to add a payload.

## Select the build

Existing entrypoints include:

- `fpSup/gyro/build_base_card.py --edition gcsv --debug --version VERSION --banner BANNER --out DIR` for gyro plus shell.
- `projects/open-gate/build/build_og3k_gyro.py --dev-card --out DIR` for an OG3K/gyro/shell development card; `OG_TARGET=og2k` selects the documented OG2K variant.
- `projects/usb-shell-sup/cards/warm-boot-2026-09-25/repack_release.py` for taking exact released payload sections onto the current loader, after verifying the current script's supported input and contract.
- `fpSup/tools/card-composer/build_catalogue.py` and the associated tests for the maintained page's composition checks.

Use a new explicit output directory under the appropriate project's cards/build artifacts, following its rules; do not overwrite released bytes. A script-built card is permitted, but it still needs the same applicable verification as a page-composed card. Running a build is not permission to write a physical card, restart the camera, record, commit/push or publish. Existing authorization persists within its stated scope.

For an AF-plus-shell request, first read `projects/fp-af-assist/PLAN.md` and `projects/fp-af-assist/notes/geometry/OFFLINE_INTEGRATION.md`. The current observer/emulator artifacts are not an installable AF payload and the EP83 integration remains incomplete. Prepare the missing owned-memory launcher and verified entry/hook integration within the requested development scope before claiming an AF card exists. Do not enable OG or gyro just because the examples above include them.

## One coherent boot chain

`store_boot`, stage2, abort, loader fingerprint and hook entry must come from the same coherent build. Mixing these between builds can fail before a shell exists. Fast Start uses persistent settings-block state; it is not removed merely by deleting AutoRun or pulling the battery. Keep it opt-in and apply the current single-product release restrictions.

`--fast --loader-hook --four-box-bar` were the merged development-card options at import. Check current parsing and required `FPSUPUI` assets before use. Do not infer today's layout from a dated example's fixed mark address.

Validate journal coverage and power-off write-back for the components included. A gyro payload relying on the shared journal must not be combined with an older loader lacking that contract. USB handler return does not establish quiescence for resident producer hooks or DMA.

## Verify exact artifact bytes

Decode the actual VBIN container: magic, section count, entry, payload length, destination/length table and aligned blobs. Compare section bytes by destination and occurrence against the intended released/source artifacts. Only the designated stage2 section may be replaced as part of the loader update; other destination-zero sections can be launchers and must not be skipped indiscriminately.

The composer verifies coherent combinations, not that a selected card contains the intended revision. Record hashes for AutoRun, payload, UI assets, source/build identity and test output. A rebuild from a changed shared core is a new artifact even if the version label is unchanged.

Run applicable composer verification after a card change through its offline refs and `projects/open-gate/build/test_boot_entry_chain.py`. Do not execute the website-writing `build_catalogue.py` main solely to test a card; the current build rules explicitly separate these paths. Use [fp-unicorn-emulation](/Users/dido/.codex/skills/fp-unicorn-emulation/SKILL.md) to test the exact card's boot path, fallback, journal, restoration and ABI before an authorized hardware trial.

Older comparisons found extra EP83 patches in page cards. That does not prove equivalence, current endpoint ownership, or AF streaming support. Recompare current sections and transport integration; AF highrate ownership remains a separate acceptance gate.

## Authorized deployment and readback

Use the current project's deployment flow with its actual shell owner. `putfile.py` writes card files; `getfile.py` can borrow RAM/code. Do not start another daemon, interrupt an active transfer or silently switch the user's card.

When hot-update is supported and authorized, follow the reviewed ordering (payload before AutoRun and all required UI assets), then read back using actual lengths and compare hashes. Historical notes and current source comments disagree about truncation: verify the actual workflow's resulting file length and bytes. If a tail remains, establish that it is valid for that format; matching only the new prefix is insufficient for an arbitrary payload. Confirm required directories exist.

An armed old loader may execute on the first boot after a hot update. Check old-loader/new-payload compatibility before deploying; never assume waiting for a second boot makes an incompatible first boot safe. Attach every result to the bytes actually read back.

## Hardware interpretation and recovery

The boot paths are image-retained loader-hook start, settings fast path after image reload, and full AutoRun fallback. USB presence can change retained-image behavior. Record cable state, active card identity and measured stamps; historical timing is not a current pass criterion. A zero power-off count alone cannot distinguish image reload from a callback that never ran.

Do not turn a “build a test card” request into an automatic sequence of recordings and power cycles. Perform the authorized hardware matrix needed for the changed behavior, distinguishing offline checks from actual boot and recording evidence.

Recovery depends on the armed hook, current card and persistent state. A historical no-BIN recovery card restored `C03DA420` to `EB0000CC`, but do not apply that recipe to an unverified build. Read the maintained recovery procedure and original expected bytes first; scope any deployment before it happens.

Maintained references: `projects/usb-shell-sup/notes/LOADER_V2.md`, `projects/usb-shell-sup/notes/DEV_MERGED_CARDS.md`, and `fpSup/tools/card-composer/README.md`. Release publication is a separate workflow; importing this skill does not inherit the old instruction to push every test build.
