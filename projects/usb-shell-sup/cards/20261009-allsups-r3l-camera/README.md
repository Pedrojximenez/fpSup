# Loader v3 — Sup Manager and inline Sup versions

Home and list labels are Sup Manager. The fixed list title is size 44; an independent grey, size-32 page count is right aligned in the same row. It displays `1 / 2`, with no angle brackets; empty or single-page lists leave the count blank. Native Left/Right paging hint, first/last boundaries and five visible Sup slots are retained. The final page-count frame is x=850, y=19, width=142, height=42.

Sup names and versions share the primary line in separate aligned columns: name x=49 (size 44, width=250), grey version x=320, y=6 (size 26). Pending/error messages remain on the secondary line, x=49, y=48, size 24, in red or green. A pending state no longer hides the grey version or repeats it inside status text. The six current product names fit the name column; longer names use its bounded native text frame.

The obsolete internal `r3h preview` annotation is removed from the footer and About page. The footer now says Loader v3, grey size 26, right aligned at the lower-right corner (x=730, y=66, width=264, height=30). This is the Loader v3 name, not a newly assigned semantic release version. All text uses the same stock Other_fontsetting.

No private-data field counts or load-chain ABI changed: FT6W, 63 variables, five slots, row stride 272, 32 stored rows / seven pages, product load limit 31, FSDS limit 30. Sup settings ownership and Enable/Disable behavior are retained.

Build: `python3 -B fpSup/fp_usb_shell/v3/build_v3.py --allsups --out projects/usb-shell-sup/cards/20261009-allsups-r3l`.

18 management and six native parser/matcher tests passed. Default non-management loader remains byte-identical (full SHA-256 recorded in verification.txt). AutoRun is unchanged and was not deployed. Only loader and management UI were replaced. See [live evidence](../20261009-allsups-r3k-live1/RESULTS.md) for hardware results and exact readbacks.

AutoRun.txt: 32768 bytes, SHA-256 `0c5107fff1262ad8ca3bb675329b71c80926c8b35cdd40931b387639b45edbf0`.

fpSup/LOADER.BIN: 27040 bytes, SHA-256 `d45e7b3b89e5f1e1d596ede2255369e5268218d42d819374fc3dd671da5e880d`.

fpSup/UI/ALLSUPS.BIN: 290016 bytes, SHA-256 `f6d0530c50fb13f4c76e811fcf0a457933d496d5dbd015204ce28447df439b68`.

The camera variant preserves the full FSDS captured immediately before the final deployment, including changes made by the user during the design session. That captured table was empty; it was not reset by this update. Product Sup files were not rewritten. No release, commit or push.
