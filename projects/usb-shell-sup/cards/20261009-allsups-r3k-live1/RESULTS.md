# Sup Manager design trial — 2026-10-09

Final source/build: r3m. Earlier r3k/r3l screenshots capture intermediate design feedback; r3k2/r3l2 were offline candidates only. Three shell reboots in this trial applied r3k, r3l and r3m.

Final design: Sup Manager; independent left-aligned `1 / 2`; five Sups per page; vertically centred names; adjacent grey versions with a small measured gap on the same baseline; right-aligned pending/error field; page counter, Loader v3 and dots aligned at the right column; Loader on the Page/Back footer baseline. The obsolete r3h preview development note is removed.

Final candidates are ../20261009-allsups-r3m and ../20261009-allsups-r3m-camera. Their manifests and README files record exact bytes, hashes, geometry and FT6X private format. 18 final management and six native interpreter/matcher tests passed. Source bytes equal saved generic files; default released loader retains its full 41f3218a… hash; AutoRun remains 0c5107ff….

The user changed Sup preferences while reviewing the camera. Each update captured the current table rather than overwriting it with a generic empty table. Before the final r3m update, SHEL alone was disabled (before-r3m.BIN). Native popup temporarily enabled it, verified by full loader readback, then the new loader/UI were applied. After reboot, the native popup restored Disable. The final 128-byte FSDS exactly equals before-r3m.BIN. The shell remains loaded on this boot and disabled for the next. No further reboot was performed after restoring Disable.

A pre-enable guard expected FT_Key=21 after Right and stopped when it read 0. The reviewed callback clears FT_Key; screenshot 1486 verified the actual Disable popup. No Right replay occurred. Selected1 was verified before Up/OK; the resulting preference and full loader were then checked.

Hardware passed: X positions 211/187/151/252/114 on the first page, 222 for RAW-View on the second; the actual rendering follows those positions. Popup state restoration, red Unload on restart field, first/last Left/Right boundaries and return to FT_Y6 were verified. Final is_recording=0 and CM_Language=7. No temporary fixture was added; directory still contains the original six products.

Complete final loader/UI/AutoRun reads are in final-readback-r3m/, with exact-match results in final-readback-r3m.json. Current owned daemon was started by exec session 99354; reuse it after ownership checks.

Final screenshots: 1487 selected SHEL with right-side status, 1488 title-focused first page and Page/Back footer alignment, 1489 RAW-View second page. transcript.txt retains single-send keys and native responses. Screenshots and card-file reads used the maintained shell/file tools.

Preserved limits: catalogue versions are build-time labels; product-owned settings pages were not exercised, only prior callback fixtures; network/QR update and SD format/restore remain future functions. Existing native menu-memory and hidden-slot focus limitations are unchanged. No recording, AF/lens action, SD format, physical power cycle, commit, push or publication.
