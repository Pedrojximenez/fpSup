# r3j/r3j2 management layout and native text trial — 2026-10-09

Continuation of the user's authorized Loader v3 page 6 camera test. Requests: inspect reusable native text, explain the first management page's unused row, align restart status, and make typography consistent.

## Results

- Management now uses all six native rows: one title and five Sups. Final screenshot 1478 contains USB-Shell, Lossless, Gyro2, RES-Custom and Flip; 1479 contains the sixth product, RAW-View. Page title has no dots/arrow. Left/Right boundaries hold at 1/2 and 2/2.
- Explicit stock Other_fontsetting and font sizes 44/24 unify titles/product/popup and secondary text. Native font CSV's Latin scaleHorz is 0.80; no ad-hoc per-object horizontal scaling was added. Both normal version and pending/error detail start at x=49, y=48. Pending detail includes version once followed by its status, entirely red/green; normal grey version is suppressed during that state.
- Screenshot 1475 verifies fifth-slot Flip Enable from boot-disabled state: `v0.1.0test   Load on restart` on one left-aligned green line. Flip was immediately restored to its disabled preference. Final 1478 verifies USB-Shell's one-line red `v3.4.0test   Unload on restart`.
- Firmware English.nloc provides exact Footer01 OK/Back, Footer05 OK/Cancel, Footer02 Further Options. Popup/native footer rendering appears in 1474/1476. The build copies original English text and markup, retaining the prior English-only private UI preference; CM_Language remains 7. It does not claim runtime localization.
- 60BTN.BIN only counts provider callbacks. Its header, row ID, service v4 allocation, hook context and current boot stamp were verified before reading its own counter. Enable Right: 0→1; Disable Right: stays 1; preference unchanged. Evidence: counter-address-boot1.json and counter-proof-boot1.txt. Actual product settings pages were not supplied/tested.
- First r3j title rectangle was 79 px inside the native 54 px Name frame, placing text too low. r3j2 restores the rectangle to 54 px. Final title/home positions were visually checked in 1477/1478; all six native tests reran after that change. Loader bytes did not change.

## Preference preservation and final bytes

At entry the camera had changed since the preceding trial: its loader program exactly matched r3i2, but FSDS contained FLIP and SHEL, and the user was on FT_LIST. The first backup equality assertion caught this preference difference. No file was overwritten to force the old empty-table comparison; actual LOADER.BIN was retained in backup-before/ and its 128-byte preference tail was preserved.

USB-Shell was temporarily enabled through the existing popup before deployment/reboots so USB remained reachable. The deployment loader migrated the original FLIP entry. After trial reboot 2, SHEL was restored via the first Sup's native popup. Final FSDS equals the pre-trial table byte-for-byte (FLIP, SHEL; unused slots zero). No further reboot followed this restoration; USB-Shell remains loaded in this boot, with next-boot Unload on restart. Flip remains boot-disabled.

The final camera artifact is ../20261009-allsups-r3j2-camera/. Full readback equality is recorded in final-readback.json and final-readback/ logs:

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| fpSup/LOADER.BIN | 27,428 | eede52236c08cf03dee596395434ee8847709facca2e3c49e70490f206c03828 |
| fpSup/UI/ALLSUPS.BIN | 289,895 | f7a640c92614906a32918d35c610fb0bd72152f20bc738d2a2e5b022ffce6ab0 |
| AutoRun.txt | 32,768 | 0c5107fff1262ad8ca3bb675329b71c80926c8b35cdd40931b387639b45edbf0 |

Only loader/UI and the temporary counting fixture were written. AutoRun and six original product Sup files were not modified. Temporary 60BTN.BIN absence was checked before reboot 2 and again at final readback. Final-dir.txt retains all six product file names/sizes. Final screen FT_Y6, is_recording=0, CM_Language=7.

Two shell-triggered reboots are recorded in reboot-1.txt/reboot-2.txt. Their command acknowledgements time out as USB disconnects; fresh ping/screen reads prove subsequent boot. Only this trial's owned daemon was stopped/restarted; initial PID 21678/executable/cwd/user were verified and AF lock absent.

## Offline evidence and limits

18 management behavioral tests plus one test of six isolated faulty variants passed (19 unittest tests, 106.164 s). All six faults detected, including fifth choices forwarded to the fourth callback. Native parser/matcher suite: six tests on r3j, then six on r3j2 (13.053 s). Default non-management loader independently rebuilt to the unchanged full SHA-256 41f3218ac1405962eee7182528e969531de4e11adf0c7a0b4868dda79f8cf67c. AutoRun unchanged. Source whitespace check passed.

Source private data ABI is FT6W (five slots, 63 variables); service v4 button ABI remains unchanged. Maximum stored Sup rows 32/seven pages, maximum loaded product Sups 31, FSDS capacity 30. Native text audit is saved in the candidate directories, including potential Version/format/QR resources and labels with no exact original equivalent. Future operation semantics must be checked before borrowing firmware/settings-specific confirmations.

Prior r3h evidence remains the basis for warm shutdown restoration/vector growth; this revision did not repeat the broad 66-test baseline unnecessarily. Physical power-switch cycles, actual product-owned settings pages, recording, AF/lens operation, network/QR update, SD format/restore, commit/push/publication were not performed. Hidden slots may remain in focus traversal; original MENU memory still re-enters SYSTEM page 5. Catalogue versions are build metadata, not live Sup self-report.
