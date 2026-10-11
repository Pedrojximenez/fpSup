# focus

Code and method for [focus sup](FOCUS_SUP.md).

對焦相關的程式與方法,說明見 [focus sup](FOCUS_SUP.md)。

2026-09-27：目前主線為機內 face／AAT 幾何方向＋原廠 CDAF，DFD 位移候選並行；電腦即時 AF 控制暫緩。第一個離線核心在 [geometry/](../geometry/README.md)，需先合焦建立基準，尚未接入機內或控制鏡頭。

| | |
|---|---|
| [**geometry/**](../geometry/README.md) | 首次合焦基準、主體接近／遠離方向器、離線重播、ARM 建置；同一份 C 核心，無相機 I/O |
| [**dfd/**](../../../../fpSup/focus/dfd) | Depth from defocus using the camera's own AF statistics — no frame extraction. Method, addresses, and the code that streams the green AF band<br>用相機自己的 AF 統計做 depth-from-defocus,不必抽幀。方法、位址,以及串出綠 AF band 的程式 |
| [**lens/**](../../../../fpSup/focus/lens) | Reading lens data through the firmware's own API — focal length, minimum focus distance, calibration blocks<br>透過韌體自己的 API 讀鏡頭資料:焦距、最近對焦距離、校準區塊 |

`dfd/` and `lens/` are historical programs using an older USB endpoint. Their
notes are research references, not compatibility evidence for the current loader.

`dfd/` 與 `lens/` 是舊端點程式；修改兩個常數不足以證明與現行 loader 相容。
新 `geometry/` 不使用 USB 端點；EP83 保留作後續觀測與驗證通道。
