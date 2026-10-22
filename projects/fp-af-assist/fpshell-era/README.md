# fpshell 時代的 AF 工具(2026-10-06 從 usb-shell-sup/fpshell_tool 搬來)

- `dfd_green_bench.py` / `dfd_image.py` / `dfd_server.py` —— DFD 綠通道 AF-band 工作台(`dfd_live.py` 的正本在 `fpSup/focus/dfd/`)
- `lens_probe.py` + `lens_read.S` —— 鏡頭 CmdRead 探針(較新版在 `fpSup/focus/lens/`)

依賴 `projects/usb-shell-sup/fpshell_tool/monitor/fpstate.py`(路徑已改成相對)。
⚠ `dfd_server.py` 原本就有語法錯誤(bytes 字面值含非 ASCII),搬移前就壞了。
