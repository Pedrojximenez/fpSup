# Claude Code skills 匯入 Codex

2026-09-27。依使用者澄清，盤點本機 Claude Code 的專案 skills，將目前 fp 開發有用的能力適配到 Codex。此輪沒有相機／USB 操作，也沒有建卡、改韌體或發布。

## 安裝結果

| Claude 來源 | Codex 處理 |
|---|---|
| 根目錄 `.claude/skills/fp-camera-control` | 新增 `fp-camera-control`，保留 UI／key／截圖／GUI log 知識，加入目前 CINE 原生觀測入口 |
| 根目錄 `.claude/skills/fp-unicorn-emulation` | 新增同名 skill，修正路徑、payload stub 證明範圍、skip 判定及隔離 mutation 做法 |
| `fpSup/.claude/skills/fp-merged-card` | 新增同名 skill，以現行 SUP_BUILD_RULES／離線 refs 為準，標明 AF observer 尚非可部署 payload |
| `fpSup/.claude/skills/fp-usb-shell` | 更新既有 Codex 版及來源快照；同步動態 cave、worker 獨立 pool 與目前 telemetry 整合狀態 |
| `fpSup/.claude/skills/fp-camera` | 將適用的單 owner、狀態診斷知識併入 camera-control，不新增重疊 skill；捨棄過時 stage 5 指令 |
| `fpSup/.claude/skills/fp-release` | 本輪不安裝；目前不是發布任務，其歷史自動 commit／push 指引不能當作本次授權 |

Claude 全域的文件類 skills 與已提供的 Word／PDF／簡報／試算表能力重疊，本輪未重複安裝。已安裝的 Swift／clangd LSP 屬 Claude plugins，沒有冒充可直接複製的 skills。備份、worktree 中重複的 fp skills 不作新版來源。

安裝位置為 `/Users/dido/.codex/skills/`，新增三項、更新一項，共九個檔案。下一輪可供技能探索／使用。Claude 原檔均未改動。

## 重要適配

- 沿用既有授權，不引入逐次重問已授權記憶體讀取／半按的要求；也不沿用 blanket kill、PTP kill loop、自動重載或自動推送。
- 保留單一 USB owner、AF lock、不確定執行不盲重試、cache publication 與資源壽命限制。
- 現行 `putfile` lazy block 存取可能實際配置相機記憶體；單純 import 才不連線。worker pool 與 legacy/logger pool 分開，均不等於 AF lease。
- CINE 待機以 native preflight／baseline／paired acquisition runner 為入口；舊 collector live guard 不繞過。既有 `sigma-fp-af-research` 本輪未改，新入口明文僅沿用其 offline/history 部分，舊 live recipe 已失效。
- Unicorn loader harness 執行 loader／stage2、stub payload entry；全 skip 不算通過。新關鍵測試的 mutation 在隔離副本或測試輸入執行。
- 卡片驗證走離線 refs／相關測試，不為了測卡執行會重寫網站的 catalogue main；文件對 truncate 的矛盾保留為待實際 readback 核對事項。

## 驗證與追溯

四個 skill 均通過官方 `quick_validate.py`、UI metadata 與本地連結檢查；安裝後九個檔案 SHA-256 與準備版一致。Claude 來源 hash 亦重新比對通過。格式參照 [OpenAI skills 文件](https://developers.openai.com/plugins/build/skills)，作業程序沿用本機 skill-creator／skill-installer。

另做五個離線情境 review：CINE 不發鏡頭命令的觀測、只建 AF＋shell 卡、全部 skipped 的模擬結果、要求現有 EP83 連續收 20 秒、以及已授權 CINE 半按。修正跨 skill 舊 live 路由、非錄影適用條件及 AF 建卡能力邊界；沒有透過這些情境執行硬體操作。

- [來源與安裝檔案 hash 清單](claude-skill-import-20260927.json)
- [可 review 的技能副本](../handoff/skills/)
- [更新前 fp-usb-shell 備份](../handoff/backups/2026-09-27-claude-import/fp-usb-shell/)
- [P0 hook＋USB 開發平台](AF_TELEMETRY_PLATFORM_PLAN_2026-09-27.md)

這次是技能與規劃更新，不新增 AF 性能或 EP83 實收證據。
