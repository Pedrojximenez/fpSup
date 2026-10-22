# Bayer 擷取 hook(2026-10-06 從 usb-shell-sup/fpshell_tool 搬來)

`build_bayer_hook.py` + `bayer_hook_oneshot.S`、`build_frameexpos_hook.py` + `frameexpos_capture.S`。
兩支都是失敗的嘗試,原因見記憶 bayer-not-in-dram-liveview;格式筆記在 `../notes/BAYER_FORMAT_MAP.md`。
`build_stage5_autorun` 從 `projects/gyro-sup/` 匯入。
