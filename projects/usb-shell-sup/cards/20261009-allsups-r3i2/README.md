# Loader v3 SYSTEM page 6 — r3i2 hardware-tested candidate

Management title dots and submenu arrow are removed. Focus the shared `Manage Sups < page / total >` row and press Left/Right to page; the footer uses the native left-right button glyph. Four Sup rows per page, up to eight pages, retain fpSup logo pink `#E03858`.

Sup Right/OK opens a two-choice Enable/Disable popup. OK confirms the next-boot preference. An enabled, loaded Sup with a registered provider shows a chevron on Enable and the native right-button `More options` footer; Right invokes that provider. Selecting Disable hides both hints and blocks the callback. Reopening the popup selects the current preference. Sup-owned settings pages remain the provider's responsibility.

Native fixed two/three-tab controls and the fixed four-page B5_7C control were inspected. Their fixed layouts were not transplanted into the variable-sized Sup list. Paging uses MainY5's existing focusable row and native footer typography.

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| fpSup/LOADER.BIN | 26,752 | eea6ce21450f97aacc0b719dc4726965346273c8d115c4052f952b10ff5bf80f |
| fpSup/UI/ALLSUPS.BIN | 280,464 | 8eaeff23cba5bfc43057cb34d55dbf01130f33fe95a83468525873233eade182 |
| AutoRun.txt | 32,768 | 0c5107fff1262ad8ca3bb675329b71c80926c8b35cdd40931b387639b45edbf0 |

The trial deployed only LOADER.BIN and ALLSUPS.BIN. All three files above were fully read back and matched exactly. The temporary 60BTN.BIN counting fixture was removed; the original six product Sups remain enabled. FSDS count is zero and unused slots are zero. When replacing another card's loader, preserve that card's disabled IDs rather than installing this empty table blindly.

UI data ABI is FT6V (52 variables and popup/footer state); service v4's `button` ABI is unchanged. The default loader without management remains byte-identical to the released 7,260-byte loader, SHA-256 41f3218ac1405962eee7182528e969531de4e11adf0c7a0b4868dda79f8cf67c. AutoRun is unchanged. Internal r3i2 is an artifact revision; the preview footer still reads Loader v3 / r3h preview.

Verification: 17 management loader tests, five isolated fault variants, and six final native UI tests passed. Hardware verified title paging/boundaries, the Audio-style two-choice popup, selected-state restoration, MENU cancellation, and an eligible Right callback counting exactly once while Disable Right counts zero. Three shell reboots were used. Previous r3h hardware evidence covers product disable/enable across restart and native vector growth.

Actual product settings pages are not yet supplied/tested. Updates, QR and SD format/restore remain Coming soon. Reopening MENU from live view uses native menu memory back to SYSTEM page 5; Right reaches page 6. Hidden empty rows may still participate in native focus traversal. Physical power-switch cycles were not tested.

Build: `python3 -B fpSup/fp_usb_shell/v3/build_v3.py --allsups --out projects/usb-shell-sup/cards/20261009-allsups-r3i2`

Evidence: [trial results](../20261009-allsups-r3i-live1/RESULTS.md), [final readback](../20261009-allsups-r3i-live1/final-readback.json), [final page 2](../20261009-allsups-r3i-live1/screenshots/1472-final-manage-page2-r3i2.jpg), [More options](../20261009-allsups-r3i-live1/screenshots/1471-enable-more-options-final-r3i2.jpg), [disabled popup](../20261009-allsups-r3i-live1/screenshots/1470-disabled-popup-state-fixed-r3i2.jpg), [user Audio reference](../20261009-allsups-r3i-reference/SS__1458.JPG).
