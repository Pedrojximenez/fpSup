# fpSup management — r3n17

Local development candidate, 2026-10-09. Uses the user's logo2.png (31 native tinted XCI layers, transparent 64×64). Header says fpSUP at home/information and SupManager in the list, with original SHOOT/PLAY/SYSTEM chrome hidden. Lower-right Loader v3 remains size 32. Sup name/version/status geometry remains as agreed.

The numbered pager follows the user's factory references SS__1520/1521/1522: the active page has a white stock glyph, other pages have grey stock glyph shapes, and grey backing is visible only while the page strip is focused. Cursor01's original Focus_On / Focus_Off animation controls the backing; no new runtime variable or Loader code is needed. The donor stripe is hidden on the page strip. Private dim XCI copies preserve stock glyph dimensions and alpha because inline image markup ignores drawText colour. Stock resources remain unchanged.

Enable/Disable keeps the existing native two-choice popup and callback routing. Its width is 420 pixels at x604; top follows the selected Sup slot at y180/261/342/421/421, clamped to end above the footer. Label and native item/background frames resize together.

Build: python3 -B fpSup/fp_usb_shell/v3/build_v3.py --allsups --out projects/usb-shell-sup/cards/20261009-allsups-r3n17

Validation: 11 native interpreter/matcher tests passed (19.021 s), 18 management behavior tests passed (84.173 s). Image resource pack has its own reader and retains its filename pool; page reader uses shared stock pool. FT6Z, public service v4, management Loader and AutoRun match r3n14. Camera deployment updates only fpSup/UI/ALLSUPS.BIN and reads the whole file back, comparing all bytes and directory size. Camera visual results are recorded in ../20261009-allsups-r3n-live1/RESULTS.md.

Exact artifact/source provenance: PROVENANCE.json. This is local development evidence, not a release or a claim of physical power-cycle validation.

Intermediate camera trial only: the first ARGB4444 conversion produced pink inactive digits. Corrected in r3n19. Sup popup slot geometry and pager focus transitions were verified here.
