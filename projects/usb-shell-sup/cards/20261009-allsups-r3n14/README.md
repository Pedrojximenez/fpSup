# fpSup management — r3n14

Local development candidate, 2026-10-09. The fixed header uses the unchanged project logo.png, encoded as 32 native tinted XCI layers at 64×66. Home/information headings say fpSUP; the manager says SupManager. Original SHOOT/PLAY/SYSTEM categories and SYSTEM segments are hidden. Numbered native page glyphs remain on the manager row. Five Sups per page retain adjacent grey versions and a separate right-aligned status field. Native grey selection and a pink left stripe replace the previous custom outline. Lower-right Loader v3 uses size 32 instead of 26.

Logo resources have a separate NBR 1.5 reader retaining their filename pool. Only the NBR 1.9 page reader adopts the shared stock pool. Image bytes precede the final page pack because load_builtin reads through pack_off + pack_len. FT6Z is a private loader/data format; public service v4 and AutoRun are unchanged. Fixed header and version use the native foreground Z = -10 and is-render-group property.

Build: python3 -B fpSup/fp_usb_shell/v3/build_v3.py --allsups --out projects/usb-shell-sup/cards/20261009-allsups-r3n14

Source and saved bytes match. 18 management behavior tests passed on this loader code in r3n12; r3n14 passed 11 native interpreter/matcher tests. Actual camera evidence is in ../20261009-allsups-r3n-live1/RESULTS.md. r3n9 had an actual first-entry freeze. r3n12 and r3n13 showed incomplete USB screenshots; the user later confirmed the physical camera screen is normal; r3n11 was rejected offline because image bytes lay beyond the loader's read extent.

AutoRun.txt: 32768 bytes, SHA-256 0c5107fff1262ad8ca3bb675329b71c80926c8b35cdd40931b387639b45edbf0

fpSup/LOADER.BIN: 27668 bytes, SHA-256 07907bb42890968fa813431adb56bf5819b705186e2b0924744761e26876d07f

fpSup/UI/ALLSUPS.BIN: 344082 bytes, SHA-256 c8956087354a3b3d0dd13aacb9bee9aac5cddcbfaef091fc3ad3400a50ec1811

