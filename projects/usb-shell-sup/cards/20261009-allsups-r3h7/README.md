# Loader v3 SYSTEM page 6 — r3h7 hardware-tested candidate

Final candidate from the 2026-10-08/09 SIGMA fp trial. Accent: fpSup logo pink `#E03858`.

`Manage Sups < page / total >` shares one row with paging; four product rows per page. Right or OK opens Enable / Disable and, when an enabled, loaded Sup provides a handler, More Settings. Changes to Enable / Disable persist in the loader's FSDS tail and take effect after restart.

This directory contains the loader, UI package, unchanged AutoRun, and splash UI assets. It does not contain the camera's six product Sups and is not a replacement for their files. The trial deployed only LOADER.BIN and ALLSUPS.BIN.

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| fpSup/LOADER.BIN | 25,964 | 46dc1c7a936ddb4e0c638fd8daf2b8344f9dbe8be1e33224e68761159a43cdbb |
| fpSup/UI/ALLSUPS.BIN | 281,157 | edecd5ba3eeea91a7053d712fd31954bb616be3cf6e52b31ee9ed4ebf82e3a12 |
| AutoRun.txt | 32,768 | 0c5107fff1262ad8ca3bb675329b71c80926c8b35cdd40931b387639b45edbf0 |

All three files were fully read back from the card and matched this candidate exactly. FSDS is empty. A future loader replacement must preserve an existing card's disabled IDs rather than blindly installing this empty table.

Hardware passed rendering, two-page navigation and boundaries, native screen vector expansion, popup selection, Flip disable/restart/enable/restart, a temporary Sup's More Settings callback, and MENU return from product rows, the paging header, and all three information pages. The temporary Sup was removed; the original six product Sups remain enabled. Six shell-triggered reboots were used; physical power-switch cycles were not tested.

Reopening MENU from live view follows native menu memory back to SYSTEM page 5. One Right reaches page 6. Actual Sup-owned settings pages are not yet supplied/tested; the provider callback was verified with a counting fixture. Updates, QR and SD format/restore are Coming soon. Sup versions currently come from the build catalogue.

Build: `python3 -B fpSup/fp_usb_shell/v3/build_v3.py --allsups --out projects/usb-shell-sup/cards/20261009-allsups-r3h7`

Evidence: [trial results](../20261008-allsups-r3h-live1/RESULTS.md), [final readback](../20261008-allsups-r3h-live1/final-readback.json), [final home](../20261008-allsups-r3h-live1/screenshots/1465-final-home-manage-r3h7.jpg), [page 1](../20261008-allsups-r3h-live1/screenshots/1459-final-manage-page1-r3h7.jpg), [page 2](../20261008-allsups-r3h-live1/screenshots/1464-final-manage-page2-r3h7.jpg).
