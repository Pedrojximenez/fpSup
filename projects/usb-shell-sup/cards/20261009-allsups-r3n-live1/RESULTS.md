# fpSup SupManager r3n20 — live trial results

2026-10-09. User authorized live testing and subsequently requested logo2, narrower row-anchored Enable/Disable, factory-style page focus, and lower logo alignment. Final local candidate: ../20261009-allsups-r3n20/. Camera ends at FT_LIST, page1, pager focus3451, language7, is_recording0.

The final header uses root logo2.png, 31 native tinted 64×64 XCI layers with premultiplied ARGB4444 alpha. Frame x28/y12 has vertical centre44, matching title x117/y13/height62. Home/information heading is fpSUP; manager heading is SupManager. Original SHOOT/PLAY/SYSTEM and SYSTEM segment paint are hidden; internal FT_Y6 route remains. Lower-right Loader v3 uses size32. Native grey Sup selection with pink left stripe remains, without a custom outline.

Factory references SS__1520/1521/1522 are copied exactly to user-native-reference/. The numbered strip keeps active digit white and inactive stock shapes grey. Current-page grey backing inherits existing Cursor01 Focus_On/Focus_Off visibility, so it disappears on content focus. Stock image pixels are premultiplied ARGB4444; private dim copies retain dimensions/alpha. r3n17 initially scaled low bytes as luminance and produced pink numbers; corrected in r3n19. Original digit resources remain untouched.

Popup width420 at x604; slot tops180/261/342/421/421, clamped above footer583. Native item/background frames are resized together. Removed only donor text/firmware-version background scrolling and width clips; cursor position/focus and callback routing remain native. Choice text is in front of the grey selected background. No Enable/Disable confirmation was sent in this trial; all popup tests cancel with MENU. Selecting Disable with DOWN changes FT_Selected1 only and cancellation resets it; final complete Loader bytes prove no persistent preference change.

Evidence: 1528 popup slot1, 1530 slot3, 1532 slot5; 1533 page1-focused and grey inactive2; 1536 Enable selected, 1538 Disable selected; 1540 page2-focused and grey inactive1; 1542 final lower logo + header + page1 focus. Raw captures and complete getfile replies are retained. Several first/repeat USB captures omit fixed title/logo/footer or other unchanged paint. User explicitly confirmed the physical screen is normal; these are capture artefacts, not proven visible UI failures. No images were composited to hide this limitation.

Resource registration: canonical NBR1.5 image pack retains its own filename pool; independent NBR1.9 page reader adopts the shared stock string pool. Images precede the final page pack so loader read extent includes them. r3n9 combined-reader candidate actually froze on first private page entry and the user physically rebooted; r3n11 misplaced image bytes were rejected offline. r3n12 onward separate reader booted; r3n14 physical screen normal per user. The final format is FT6Z, with96variables, five visible Sup slots and32 stored rows/seven maximum tabs; public servicev4, row272, product/FSDS limits unchanged.

Validation: r3n19 native interpreter/matcher11 tests passed (17.966s); management18 tests passed (83.270s). Final r3n20 changes only logoY by+4; all five pages pass native interpreter and duplicate-local-ID check (1test,15.798s). Final source rebuild matches ALLSUPS.BIN byte for byte. Management Loader and AutoRun exactly match r3n14; r3n17/r3n19/r3n20 live deployments wrote only ALLSUPS.BIN and each performed complete readback and directory-size comparison. Single-send shell reboots and scoped USB claimant recovery are logged; no blanket service kills or repeated uncertain keys.

Final files fully reread from camera, matching candidate and directory size:

- fpSup/LOADER.BIN: 27668 bytes; SHA-256 07907bb42890968fa813431adb56bf5819b705186e2b0924744761e26876d07f
- fpSup/UI/ALLSUPS.BIN: 347740 bytes; SHA-256 d2fcbe9d90ac326a1d1be39f649631e7bd89f89407eeeb702bdd01ff9a899ffc
- AutoRun.txt: 32768 bytes; SHA-256 0c5107fff1262ad8ca3bb675329b71c80926c8b35cdd40931b387639b45edbf0

All128FSDSbytes match before-r3n19-loader.BIN and r3n14; disabled list empty. Six original product files remain; no fixture added. AutoRun was not written. No recording, AF/lens operation, formatting, QR/network updates, actual hot unload, physical power-cycle validation, commit, push, or release. Updates/QR/SD tools remain placeholders; existing hidden-row focus and stock MENU memory limitations remain.

PROVENANCE.json in the final candidate records exact source and artifact hashes; transcript.txt, test/deploy/reboot/getfile logs and final-readback-r3n20.json retain the evidence.


## r3n21 spacing follow-up

User requested logo/title closer and logo lower. Only manager_header geometry changed: logo y12→16, title x117→104; frame gap25→12. Applied on all five headers. All other source hashes, native asset bytes, management Loader and AutoRun match r3n20. Native interpreter/duplicate-local-ID check passed on all five pages (1 test,14.062s); exact source rebuild matches saved UI.

Updated only ALLSUPS.BIN, whole-file readback and directory size verified, one single-send shell reboot. User had already entered FT_LIST and opened the Lossless popup; LV navigation guard stopped without sending a menu key. Captured the current view directly, preserving their focus/selection. Screenshot1546 shows the complete new header;1547 is retained with known incomplete static chrome. Final UI/Loader/AutoRun fully reread and match candidate; all128FSDSbytes match before-r3n21, empty disabled list. No Enable/Disable confirmation or provider callback sent.

UI347,740 B, SHA-256 e7cb5478b60ee63b0d00841aa8c1628b47bceb02e7ce7f106e81a5f265c40ca4; Loader27,668 B still07907bb4…; AutoRun32,768 B still0c5107ff…. Final screen/focus/page replies are in final-readback-r3n21.json. is_recording0, CM_Language7. Final candidate ../20261009-allsups-r3n21/ with exact provenance. No commit/push/release or other camera function change.


## r3o1 disabled unfinished features

User requested unfinished functions greyed out and SD Card Format (Keep fpSup) placed directly on the home page. Updates and SD format are native SelectLock rows with grey text, blank dots/arrow, no Right/OK actions, and normal Up/Down/Menu navigation. Unfinished information rows (update/scan/QR/keep fpSup) receive the same lock. SupManager and About remain active in this intermediate candidate. No format/restore implementation is added.

12 native interpreter/matcher/action tests passed (19.033s), and the home-activation fault mutation was rejected. Source rebuild is an exact UI byte match. Management code/Loader/AutoRun unchanged; previous18-test management baseline retained. Only ALLSUPS.BIN updated, full readback and directory size checked, then one single-send shell reboot. Scoped recovery of the observed macOS USB claimant is logged.

Live: Right and OK on Updates and SD format remain FT_Y6; About opens FT_ABOUT; Right and OK on fpSup QR Code remain FT_ABOUT. SupManager entry and Menu return pass. Raw1548 shows complete home header and disabled rows;1553 focused format stays grey;1555 focused QR stays grey.1556/1557 omit static header in the known USB capture limitation; no composite made.

Final complete readback: UI347,504 B SHA-25692e9b9b8220fed7878fae23bc5fb8ca416704636241244f6b847cac89eef894e; Loader27,668 B SHA-25607907bb42890968fa813431adb56bf5819b705186e2b0924744761e26876d07f; AutoRun32,768 B SHA-2560c5107fff1262ad8ca3bb675329b71c80926c8b35cdd40931b387639b45edbf0. Loader entire bytes/FSDS128 match before-r3o1; empty disabled list and six original products retained. Test ends FT_Y6 focus3451. During later readback user navigation was observed (FT_ABOUT then FT_Y6 focus33547); no further navigation keys sent. User language0 preserved, is_recording0. Results in final-readback-r3o1.json. User subsequently requested About also disabled; r3o2 supersedes this intermediate candidate.


## r3o2 About entry follow-up — live passed

About home entry added to the native disabled set; independent action regression now covers home indices1/2/3.12 tests pass18.500s and source rebuild exact. UI347,378 B SHA-256acd15bdad956f36bb44818b089bd6aa3745ecbe08f93dc4f1cd8430a8db57204; Loader/AutoRun identical to r3o1. First camera app-pointer read failed before any file/key mutation, host STATUS camera=closed, SIGMA absent from current IOUSB tree. User asked to reconnect/reboot if hung. No r3o2 write started.

User confirmed power on. Camera re-enumerated and scoped observed PTP claimant58509 was released; original owned daemon58483 pinged and backups/preflight passed (LV_CINE_MEDIUM, recording0, language0, FSDS empty). UI-only deploy replaced347504→347378 with exact full readback and directory size check. One single-send shell reboot returned expected IO error. Socket QUIT cleanly closed daemon58483. New owned daemon59604 started; claimant59325 had respawned as59606 during startup and was observed owning interface0. Scoped release of59606 followed by ping succeeded. No blanket kills/watchdog/service change, no in-flight transfer interrupted.

Live checks pass: Right and OK on all three disabled home rows remain FT_Y6 with the same focus; About33571 stays grey while focused. SupManager both Right and OK enter FT_LIST; Menu returns FT_Y6.1558 is complete home/all three grey,1561 is complete About-focus lock.1559/1560/1562/1563 retain static-chrome capture omissions; no compositing.

Final complete UI/Loader/AutoRun readback matches exact candidate hashes and real directory lengths. Loader all bytes and FSDS128 match before-r3o2; empty disabled list, six original product files retained. AutoRun/products not written, no fixtures. Final FT_Y6 homefocus3451, CM_Language0 preserved, is_recording0. No Enable/Disable confirmation, provider callback, recording, AF/lens operation, actual formatting/restoration, QR/network update, hot unload, commit/push/release. Final candidate ../20261009-allsups-r3o2/; full evidence final-readback-r3o2.json, deploy-r3o2.txt, reboot-r3o2.txt, screenshots and transcript.txt.
