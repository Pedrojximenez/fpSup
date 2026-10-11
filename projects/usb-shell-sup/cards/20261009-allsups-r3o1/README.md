# fpSup management — r3o1

User requested unfinished functions greyed out, and SD Card Format that keeps fpSup directly outside its tools subpage. Home now has active SupManager / About fpSup, and disabled Updates / SD Card Format (Keep fpSup). Existing FT_CARD resource is retained for private pack compatibility but no home activation action enters it. Format is a disabled placeholder; no formatting or restore implementation is added.

Unfinished update/scan/QR information rows use native MainY5 SelectLock, grey0x888888, blank dots/entry arrow and no Right/OK actions. Focus and Menu navigation remain native. Both ends of the donor label's colour clip stay grey, preventing focus animation from restoring white. Live key checks and captures are in ../20261009-allsups-r3n-live1/RESULTS.md.

Build: python3 -B fpSup/fp_usb_shell/v3/build_v3.py --allsups --out projects/usb-shell-sup/cards/20261009-allsups-r3o1

12 native parser/matcher/disabled-action tests passed (19.033s). New regression check rejects a fault that grants activation to unfinished home items. Management Loader/AutoRun unchanged from r3n21; UI-only update with complete readback. Existing management18-test behavior baseline is r3n19. Native row/action change adds no runtime variables or private ABI change; all five pages and96 variables remain. Exact provenance is in PROVENANCE.json.

Live trial and complete readback passed. User language0 preserved. Screenshots1548/1553/1555 show grey home/format/QR. About was active in this intermediate candidate; user follow-up disabling About is implemented in r3o2.
