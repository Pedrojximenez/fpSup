# r3i / r3i2 SIGMA fp management UI trial — 2026-10-09

Authorized continuation of the user's Loader v3 page 6 on-camera trial. Requested changes: remove title ellipsis, inspect native paging options, and use the Audio menu's More options presentation. User reference is SS__1458.JPG, retained in ../20261009-allsups-r3i-reference/.

Final camera candidate: ../20261009-allsups-r3i2/. Only LOADER.BIN and ALLSUPS.BIN were updated. AutoRun was not written. Pre-trial r3h7 files are in backup-before/. The six original product files were not modified.

## Hardware observations

- Management title has neither trailing dots nor the submenu arrow. Left/Right pages on this row; native left-right footer glyph says Page. Final six-product page 2 is screenshot 1472; boundaries remain 1/2 and 2/2.
- Popup retains exactly Enable and Disable. Eligible Enable has a right chevron and the native `More options` footer, matching the user's Audio reference. Disable hides both; selecting Disable before pressing Right does not call the provider or change the preference. MENU cancels.
- r3i initially failed to apply FT_Default to the popup List itself: reopening a disabled Sup highlighted Enable. Screenshot 1469 records the failure. r3i2 adds the List binding; 1470 records Disable correctly selected, while 1471 records restored Enable and More options. The temporary Sup's preference was restored before cleanup.
- Provider fixture 60BTN.BIN only counts callbacks. Verified its allocated FSB1 header, provider row, service version and current boot stamp before reading its own counter. Boot 1: 0 → 1 on eligible Right, still 1 on Disable Right. Final r3i2 boot 2 repeated the same result. Proofs: counter-address*.json and counter-proof*.txt. GUI FT_Key is reset by popup FocusOff, so its zero value alone is not a failed-callback result.
- Removed 60BTN.BIN with a single delete, verified absence by directory read, then performed reboot 3. Original six products remain, all enabled. Final screen is FT_Y6 and is_recording=0.

Three shell-triggered reboots are recorded in reboot-1.txt through reboot-3.txt. Reboot command acknowledgement timeouts are expected because USB disconnects; the new shell and management screens establish subsequent boots. Only this trial's owned daemon was stopped/restarted. The final connectivity harness initially compared lowercase `pong` to uppercase `PONG`, causing a false failure after ten successful pings; subsequent native screen reads and full file reads confirm connectivity.

Earlier navigation attempts used blind UP presses; native popup UP wraps and home/header focus cycles, so those attempts entered unrelated menu pages and triggered test assertions. They do not establish a product failure. Final tests read screen/focus/selection before acting. A temporary transport read dropout was resolved through an explicit read and reattempt of an unstarted read operation; no fresh probe or scratch reset was used.

## Final card bytes

Full readbacks and logs are in final-readback/; final-readback.json records exact equality:

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| fpSup/LOADER.BIN | 26,752 | eea6ce21450f97aacc0b719dc4726965346273c8d115c4052f952b10ff5bf80f |
| fpSup/UI/ALLSUPS.BIN | 280,464 | 8eaeff23cba5bfc43057cb34d55dbf01130f33fe95a83468525873233eade182 |
| AutoRun.txt | 32,768 | 0c5107fff1262ad8ca3bb675329b71c80926c8b35cdd40931b387639b45edbf0 |

FSDS magic 0x53445346, count=0, all 30 unused slots zero. Final directory is retained in final-dir.txt. Original products: 00SHELL.BIN 4,552 B; 10LOSS.BIN 70,944 B; 20GYR2.BIN 4,208 B; 32RESCUS.BIN 47,680 B; 40FLIP.BIN 25,936 B; 45RAWV.BIN 38,644 B.

## Offline checks and limits

17 management C tests plus five isolated faulty variants passed before deployment; six final native UI tests passed after the List binding repair. Default released loader bytes remain unchanged. Source whitespace check passed. Previous r3h evidence remains the basis for product disable/enable across restart, shutdown restoration and native vector growth; those broad tests were not repeated unnecessarily.

The fixed two/three-tab native controls and B5_7C's fixed four-page layout do not directly serve variable Sup counts. This revision uses the existing MainY5 row, dynamic title text and native footer glyph, without claiming a transplanted native pager control. Empty rows are visually hidden and locked, but may remain in focus traversal. Native MENU memory still re-enters SYSTEM page 5 before Right to page 6.

Only the callback contract was exercised; no actual product Sup settings page exists in this trial. Updates/QR/SD format-and-restore remain Coming soon; Enable/Disable still applies after restart. No physical power-switch test, recording, AF/lens operation, SD formatting, commit, push or publication.
