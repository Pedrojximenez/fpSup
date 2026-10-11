# Loader v3 — final Sup Manager alignment

The home entry and list title are Sup Manager. A separate grey page count displays `1 / 2` without angle brackets; it is blank for an empty or single-page list. The page counter and Loader label share x=901 and native left alignment with the Sup dots. The counter is size 32, y=19, height 42. Loader v3 is grey size 26, y=34, height 54, sharing the native footer text baseline. The stale internal r3h preview annotation is removed from the footer and About page.

Sup names are vertically centred in their original 79-pixel rows: name frame x=49, y=16, size 44, height 46. Grey versions are size 26, y=30, height 32, on the name's baseline. Their x positions follow the measured native name ink ends with a 12-pixel gap; versions no longer occupy a fixed column. The same six catalogue entries carry these positions. Measurements come from camera screenshots 1484/1485 with the stock Other_fontsetting at size 44; if those names or font size change, update the recorded ink ends. Uncatalogued Sups retain their filename and have no catalogue version.

Pending/error text is a separate right-aligned field (x=460, width=404, y=31, size 24); it follows the name/version group on the same row. Versions remain grey during pending/error states and are not repeated inside status text. Hardware shows USB-Shell with its grey version and red Unload on restart in this field.

Private data format FT6X adds five integer position variables (68 variables total), native property-subindex bindings for each version's position X, and a 16-byte product entry containing version_x. Each row still occupies 272 bytes, using four of its existing reserved bytes. There are still five visible Sups, 32 stored rows / seven pages, at most 31 loaded products and 30 FSDS entries. Service v4's Sup button/settings ABI is unchanged.

Build: `python3 -B fpSup/fp_usb_shell/v3/build_v3.py --allsups --out projects/usb-shell-sup/cards/20261009-allsups-r3m`.

18 management behavior tests passed (77.606 s); six native parser/matcher tests passed (12.744 s). Saved generic loader/UI bytes equal the final source builds. The default non-management loader remains exactly 7,260 bytes with full SHA-256 41f3218ac1405962eee7182528e969531de4e11adf0c7a0b4868dda79f8cf67c. AutoRun is unchanged.

Hardware confirmed version positions on both pages, first/last paging boundaries, centred names, baseline alignment, right status field and native footer. Only loader/UI were deployed; the original six product Sups and AutoRun were not rewritten. Original SHEL-disabled FSDS was restored through the popup after temporarily enabling the shell for the final reboot; all 128 bytes exactly match before-r3m.BIN. Final complete loader/UI/AutoRun readbacks match the camera variant.

AutoRun.txt: 32768 bytes, SHA-256 `0c5107fff1262ad8ca3bb675329b71c80926c8b35cdd40931b387639b45edbf0`.

fpSup/LOADER.BIN: 27136 bytes, SHA-256 `eef2406e8250d62e2b17b318dc265ccb1cfddb1c21b7eedd46ceb4dc5f35bed5`.

fpSup/UI/ALLSUPS.BIN: 290638 bytes, SHA-256 `54841edc7e7b66e4fd1be687536fe4deef08ea42593163d2a60297642cd2fd7c`.

The generic candidate has empty FSDS; the camera variant preserves SHEL disabled. [Live results](../20261009-allsups-r3k-live1/RESULTS.md), [final first page](../20261009-allsups-r3k-live1/screenshots/1488-final-alignment-page1-r3m.jpg), [final second page](../20261009-allsups-r3k-live1/screenshots/1489-final-inline-version-page2-r3m.jpg).

Sup versions remain build-time catalogue labels. Network/QR update, SD formatting/restore and live unload are unchanged future features. No recording, AF/lens action, physical power-switch cycle, commit, push or publication.
