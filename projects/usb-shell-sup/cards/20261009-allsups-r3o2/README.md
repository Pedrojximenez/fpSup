# fpSup management — r3o2

User follow-up requested About fpSup also greyed out because it has little useful content and some entries can hang. About now has the same native SelectLock/grey label/blank dots and arrow/no Right or OK actions as Updates and SD Card Format (Keep fpSup). SupManager is the only active home entry. SD formatting/keep fpSup remains a direct-home disabled placeholder. No format or restore action is implemented.

Only the UNFINISHED_HOME set changes from r3o1. Information page resources are retained but no home activation enters Updates, SD, or About. Existing native focus and Menu return remain. The regression check independently requires all three home rows to have zero Right/OK actions.

12 native parser/matcher/action tests passed (18.500s); source rebuild matches ALLSUPS.BIN exactly. UI347,378 B; SHA-256 acd15bdad956f36bb44818b089bd6aa3745ecbe08f93dc4f1cd8430a8db57204. Loader/AutoRun exactly match r3o1 and r3n14. No runtime, ABI, management code, or product payload changes. Previous management18-test baseline r3n19 remains applicable.

Build: python3 -B fpSup/fp_usb_shell/v3/build_v3.py --allsups --out projects/usb-shell-sup/cards/20261009-allsups-r3o2

Live deployment passed after user reopened camera. Only ALLSUPS.BIN was written; complete readback and directory size verified, one single-send shell reboot. Maintained host daemon restarted cleanly via socket QUIT. Exact observed macOS interface claimant PIDs58509 (user reboot),59325 then59606 (shell reboot/daemon startup race) were released within the scoped recovery; final owned daemon PID59604. No kill loop or service configuration change.

Right/OK on Updates, SD Card Format (Keep fpSup), and About remain on FT_Y6; SupManager opens on both Right and OK and Menu returns. Raw screenshot1558 is a complete home frame with all three rows grey;1561 shows About focused and grey, with no activation affordance. Other captures retain the known missing-static-chrome USB limitation; no composite made. Final UI/Loader/AutoRun full readback matches candidate exactly; Loader/FSDS unchanged from preflight. Six original product files remain, language0 preserved, is_recording0, final FT_Y6 homefocus3451. See ../20261009-allsups-r3n-live1/RESULTS.md and final-readback-r3o2.json.
