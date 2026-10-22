# fpSup management design — r3n13

Intermediate camera candidate, 2026-10-09. The first foreground test passed, but popup/capture redraws still lost chrome; this is not the final candidate. The fixed header uses the root project logo.png, converted to 32 native tinted XCI masks at 64×66. Home/information headers say fpSUP; the manager header says SupManager. The original SHOOT/PLAY/SYSTEM header is hidden. Numbered native page glyphs remain on the manager row, with five Sups per page, adjacent grey versions and right-aligned status. The native grey cursor and pink left stripe remain, with no custom outline. Lower-right Loader v3 uses size 32 instead of 26.

The logo resources use a separate NBR reader so their lazy filenames retain their own string pool. The page reader uses the shared stock pool. Image bytes precede the final page pack because load_builtin reads through pack_off + pack_len. FT6Z is a private loader/data format; AutoRun and the public service ABI are unchanged. Fixed header and Loader text use the native foreground transform-origin Z = -10 to remain above animated stock backing.

Build: python3 -B fpSup/fp_usb_shell/v3/build_v3.py --allsups --out projects/usb-shell-sup/cards/20261009-allsups-r3n13

Source/build exact comparison passed. 18 management behavior tests passed for this loader code (r3n12); the r3n13 native interpreter/matcher checks passed 11 tests. Actual camera results and screenshots are recorded separately in ../20261009-allsups-r3n-live1/RESULTS.md. Earlier r3n candidates are intermediate experiments; r3n9 froze at initial page entry and r3n12 still lost static chrome on redraw.

AutoRun.txt: 32768 bytes, SHA-256 0c5107fff1262ad8ca3bb675329b71c80926c8b35cdd40931b387639b45edbf0

fpSup/LOADER.BIN: 27668 bytes, SHA-256 07907bb42890968fa813431adb56bf5819b705186e2b0924744761e26876d07f

fpSup/UI/ALLSUPS.BIN: 345542 bytes, SHA-256 51e8eb1ec556aff41d0c69959819c630eca9207384eb1790531357f0e9f848b9

