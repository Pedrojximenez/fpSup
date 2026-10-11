# Loader v3 page 6 hardware trial — 2026-10-08/09

User authorization: 上機測試. Camera: SIGMA fp Ver.5.02, existing USB shell, no recording. Final installed candidate: `../20261009-allsups-r3h7/`.

## Final card and camera

Full reads in `final-LOADER.BIN`, `final-ALLSUPS.BIN`, and `final-AutoRun.txt` match the final candidate exactly; sizes and SHA-256 are in `final-readback.json`. FSDS count is zero and all unused slots are zero. The six original product Sups remain: 00SHELL.BIN, 10LOSS.BIN, 20GYR2.BIN, 32RESCUS.BIN, 40FLIP.BIN and 45RAWV.BIN. The counting fixture 60BTN.BIN was removed before the sixth reboot and is absent in the final listing.

Camera left on FT_Y6 with Manage Sups selected; `is_recording -> 0`. The trial's owned current fpshd remains available. Existing unrelated work was preserved; no commit, push or release.

## Results

| Check | Evidence / result |
| --- | --- |
| Home, fpSup pink, footer/version | 1465-final-home-manage-r3h7.jpg; rendering verified |
| Four product rows on page 1 | 1459-final-manage-page1-r3h7.jpg |
| Page 2, Flip and RAW-View enabled, empty rows hidden | 1464-final-manage-page2-r3h7.jpg; Default1=Default2=0 |
| Title paging | 1/2 to 2/2 and back; extra Left at first / Right at last stays at boundary; FT_Focus remains 3451 |
| Enable / Disable popup | 1451-flip-popup-h5.jpg; both labels visible and selectable |
| Flip Disable persistence | after-disable.BIN differs only in FSDS; FLIP disabled; reboot shows grey/unloaded Flip |
| Flip Enable persistence | 1452-flip-enable-h5.jpg shows Load on restart; after-enable.BIN equals original candidate loader; following reboot restores loaded Flip |
| More Settings eligibility and selection | Temporary BTNS loaded: Max=2, More=1; selected third item calls provider; FT_Key 2107, then 2207 |
| Disable / re-enable eligibility | BTNS Disable removes third item (Max=1, More=0); Enable while still loaded restores it |
| Popup text remains visible while moving selection | 1457-more-selected-h6.jpg; three labels visible after Down twice; callback FT_Key=2107 |
| MENU return from Sup row | Final r3h7: FT_LIST USB-Shell row -> MENU -> FT_Y6 |
| MENU return from title | Final r3h7: FT_LIST title -> MENU -> FT_Y6 |
| Updates / SD Card Tools / About | Screenshots 1460, 1461 and 1462; each entry and MENU return asserted |
| Live-view exit and menu re-entry | MENU -> LV_CINE_MEDIUM; next MENU -> native MainY5; Right -> FT_Y6 |
| Native screen allocation | Final app vector +0x80=0xE2, +0x84=0xE8: 226/232; machine vector observed 18/24 |
| Final full card readback | final-readback.json; exact matches for loader/UI/AutoRun; FSDS empty |

Screenshots are in `screenshots/`. `transcript.txt` retains timestamped key sends, native replies, screen names and assertions. Keys were sent once with no blind retries; screenshots required a newly created filename and full exact-size readback. Deletion timeouts were resolved by directory inspection before proceeding. The failed assertion during final boundary checks was only whitespace formatting in `1 / 2`; the corrected check passed. The native MENU re-entry assertion exposed the documented MainY5 behavior, not a claim of retained page 6.

## Repairs made during trial

The UI donor's draw order hid new grey names, versions and status text; insert these before BG. Private text now has a valid initial string and explicit left alignment. Popup list/highlight boxes span the row; labels use fixed frames; selected BG is transparent. Duplicate literal references are removed when replacing a field. Footer uses the native parent and markup typography, with the old text/selector moved off screen.

Three 8,938-byte position/rect clips per popup row animated labels away on selection changes; removing these clips while preserving list/cursor animations reduced the final UI package to 281,157 bytes. The donor cleanup had also removed the Sup row's Menu transition; r3h7 restores Return and was verified on the camera.

## Verification and limits

Prior offline validation: 66 loader/boot/restore checks, 16 management checks, 9 native/legacy UI checks and four intentional faults detected. This trial reran 16 management checks and 9 native/legacy UI checks after the first text repair; each subsequent UI revision passed the four management-page tests, including final r3h7. Loader bytes stayed unchanged during these revisions. Six shell reboots are logged as reboot-1.txt through reboot-6.txt.

Physical power-switch warm cycles were not tested. More Settings demonstrated callback dispatch with a counting fixture; an actual product Sup-owned settings screen and its return path remain untested. Versions come from the build catalogue. Updates, QR and SD format/restore remain Coming soon. No recording, AF/lens tests or SD formatting occurred.

Original loader, AutoRun and LOAD.LOG backups remain in `backup-before/`. Initial loader SHA-256: 41f3218ac1405962eee7182528e969531de4e11adf0c7a0b4868dda79f8cf67c. Product Sups and original splash files were not replaced.
