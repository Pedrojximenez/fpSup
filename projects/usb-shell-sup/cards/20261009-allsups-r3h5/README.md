# Loader v3 management UI / r3h5 candidate

Camera trial: 2026-10-08 to 2026-10-09. Evidence and original-card backups: `../20261008-allsups-r3h-live1/`.

Only `fpSup/UI/ALLSUPS.BIN` changes from r3h. LOADER.BIN and AutoRun remain byte-identical. Do not replace a live loader without migrating its FSDS disabled table. This candidate table is empty. No product Sups are supplied.

Fixes from hardware observation: valid initial text references; explicit left alignment; row text inserted beside the native Name before its background; full-width popup frames; transparent selected background so it cannot cover the selected label; original MainY5 Footer text and typography; loader version placed at the footer's right side.

Native page/transition tests: 4 passed. Prior 9 native/legacy page tests and 16 loader-management tests passed. Hardware acceptance is recorded separately in the trial evidence; building this candidate does not establish hardware acceptance.
