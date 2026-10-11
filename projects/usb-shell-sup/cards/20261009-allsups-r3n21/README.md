# fpSup management — r3n21

Local UI spacing refinement, 2026-10-09. User asked for the logo and title closer together, and for the logo slightly lower. Header logo2 frame x28/y16/64×64; title frame x104/y13/800×62. Compared with r3n20: logo moves down4 pixels and title moves left13; frame gap reduces25→12. Applies to SupManager and fpSUP headers on all five pages.

Build: python3 -B fpSup/fp_usb_shell/v3/build_v3.py --allsups --out projects/usb-shell-sup/cards/20261009-allsups-r3n21

The native interpreter/duplicate-local-ID check passed for all five pages (1 test,14.062s). Only those two geometry values changed. All other source hashes, management Loader, AutoRun, glyph/logo resource pixels and callbacks match r3n20; r3n19's11 native /18 management tests remain the prior behavior baseline. UI-only deployment, whole-file readback and one single-send shell reboot. Final camera checks are recorded in ../20261009-allsups-r3n-live1/RESULTS.md; exact file/source hashes in PROVENANCE.json.

Final camera header verified in screenshot1546; all three files fully reread and match. FSDS unchanged. Preserved the user's existing Lossless popup focus rather than navigating. UI SHA-256 e7cb5478b60ee63b0d00841aa8c1628b47bceb02e7ce7f106e81a5f265c40ca4.
