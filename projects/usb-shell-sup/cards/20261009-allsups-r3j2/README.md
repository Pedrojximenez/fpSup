# Loader v3 page 6 — r3j2 five-slot management candidate

The original six-row menu layout now holds one paging title plus five Sups. The first management page no longer leaves an unused sixth row. Up to 32 stored Sup rows occupy seven pages; the existing 31-product load limit and 30-entry FSDS limit are unchanged.

Titles, product names and popup choices use the stock `Other_fontsetting` with size 44. Versions and pending/error messages use the same font setting at size 24. The stock Latin font's horizontal scale is 0.80; this revision consistently uses that native setting, without introducing per-object horizontal stretching. Version and pending/error text share a single left-aligned detail line at x=49, y=48. When pending/error text is present, its red/green line contains the version once and the separate grey version is blank. Strings live in each row's existing 196-byte detail storage; row stride remains 272 bytes.

Footer wording and button markup come directly from the pinned firmware's English.nloc during build: Footer01 = OK/Back; Footer05 = OK/Cancel while a popup is open; Footer02 = Further Options. This retains the user's English-only private UI preference; it is not runtime switching to the camera's current language. Enable/Disable, Manage Sups, Page and Sup-specific status text have no exact stock English equivalent. More resources for future Version, format and QR UI are recorded in native-text-audit.json; camera firmware/settings operations are not relabelled as Sup operations.

Final generic build: LOADER.BIN 27,428 B, SHA-256 `0241d5298c9e55496b2af2ff8b689734b75564f2b4f01b634d857838b982fa7f`; ALLSUPS.BIN 289,895 B, SHA-256 `f7a640c92614906a32918d35c610fb0bd72152f20bc738d2a2e5b022ffce6ab0`. AutoRun is unchanged, SHA-256 `0c5107fff1262ad8ca3bb675329b71c80926c8b35cdd40931b387639b45edbf0`.

This generic build has empty FSDS. The actual camera candidate is [r3j2-camera](../20261009-allsups-r3j2-camera/README.md), preserving the user's FLIP/SHEL disabled IDs. Do not replace another card's preferences with this empty table. Only loader/UI were deployed; product Sups and AutoRun were not rewritten.

Private UI data ABI changes to FT6W: five visible slots, 63 variables, and five selection/choice callbacks. Service v4's button ABI is unchanged. Final r3j2 adjusts only the title text rectangle from 79 to its native 54 px height; loader code bytes equal the C-tested r3j candidate. Default released non-management loader remains byte-identical, full SHA-256 `41f3218ac1405962eee7182528e969531de4e11adf0c7a0b4868dda79f8cf67c` (7,260 B).

18 management behavioral tests and six isolated faulty variants passed (19 unittest tests total). Six final native parser/matcher tests passed. Hardware confirmed fifth-row selection, grouped green/red detail, title alignment, native footer wording, paging/boundaries, provider callback eligibility and cleanup. Evidence: [trial results](../20261009-allsups-r3j-live1/RESULTS.md), [final first page](../20261009-allsups-r3j-live1/screenshots/1478-final-five-sups-preserved-settings-r3j2.jpg), [green detail](../20261009-allsups-r3j-live1/screenshots/1475-grouped-green-detail-r3j.jpg), [native Further Options](../20261009-allsups-r3j-live1/screenshots/1476-native-further-options-r3j.jpg).

Build: `python3 -B fpSup/fp_usb_shell/v3/build_v3.py --allsups --out projects/usb-shell-sup/cards/20261009-allsups-r3j2`.

Actual product-owned settings pages, physical power-switch cycles, network/QR update and SD format/restore remain untested/unimplemented. Native MENU memory still returns to SYSTEM page 5 before Right to page 6; hidden unused slots may remain in native focus traversal. Sup versions still come from the build catalogue. No recording, AF/lens operation, SD formatting, commit, push or publication.
