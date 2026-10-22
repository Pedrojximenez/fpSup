# AF Assist：轉向 producer hook 取樣

2026-09-16。使用者指出高速取樣可能需要 hook。本篇是離線方案，不是已部署成果。
目前相機沒有新 AF hook；既有 RAM lease 已結束並核對還原。

## 要解決的問題

現有 host sampler 一筆保守觀察約需 7 秒，包含大量 native getters、context guards、逐字參數
往返。152-byte camera-side copy 已縮短 H/L 本身的讀取窗口，但沒有降低整個 host 控制流程
的往返數，也沒有修復 native PTP 與 shell 的共享端點問題。

方向為：**統計發布 → 相機端有界記錄 → USB 低頻批次讀回 → host 分析**。
第一階段只記錄、不控鏡、不更改原廠 AF 決策；不從 hook 發 USB、印 printf、寫卡、配置記憶體
或等待事件。先量到每次發布的成本與遺失情形，再談相機端控制迴路。

## 候選與資料語意

優先候選是背景 observer 中 `C022C858` 的 `BL C023E9D0(model,0,0)` 返回點 `C022C85C`。
它在 H/L 發布後、後續 AF decision 前；原始呼叫字組 `EB00485C` 已由 ROM 核對。
這是 CameraMgrScheduler task 路徑，不是直接 VD ISR。共通審核見
[掛點候選](research/FP_AF_PUBLICATION_HOOK_CANDIDATES_2026-09-16.md)。

記錄需求候選：本工具的 publication sequence、producer mode、area、H/L、
cached lens position、實際 gain 與必要 ROI/context 身分。sequence 只計 eligible publication，
**不是 sensor frame ID**；cached position 不是曝光中心位置。
CPU 時間暫不列為最小必需欄位：呼叫 clock 會擴大 ABI／stack 契約，且不是曝光時間。
先從 producer input 路徑確認有無適合直接複製的完成序號／buffer 身分，再決定最小格式。
原廠 Near history 可作另一條索引／補償對照，但不與背景 processing mode=0 混為同一訊號。

buffer 需要固定容量、完整寫入後才發布的 commit marker、overflow/lost 計數；host 必須拒絕
半筆、重複、覆寫或來源不符的記錄。第一試驗宜採小型有界 capture，滿後停止收集，不追求
無限串流。傳回時沿用已審核的 CPU-copy→DMA 路徑，不能讓 USB DMA 直接讀 cacheable code cave。

## 部署前仍缺的證據／權限

- 目前授權只有 echo `C0BAC2F8`、`C072F700..F9FF`，以及本機診斷 daemon。
  **不包含修改 `C022C858` 或任何新的 AF callback／buffer 區域。**
- 現有小 RAM 區已分配給 control、snapshot 與參數，不能把 hook/ring 隨意疊上去。
  需核對實際 build、所有 resident users、確切 code/record 範圍及原始 before-image；零值不等於可用。
- 需建立新掛點的原指令驗證、原函式呼叫／返回 ABI、最坏執行時間與 code-cache publication。
- 卸載必須證明 **AF task** 不再使用 handler，再還原 code/buffer；USB shell same-worker 成功
  回覆不等於 AF task quiescent。disabled flag 或一瞬間 active=0 也不能單独排除尚未進入／即將返回。
- 取樣 hook 不解決鏡頭控制命令的 PTP/FPSH 競爭；不能以低頻讀回成功當成 exactly-once 控制證明。

先完成上述離線設計，再列出精確新增地址、有限記錄次數與復原步驟請使用者同意。
不以先前 RAM bridge 或 host-only 診斷的同意，自動推定新 hook 部署權限。

## 已完成的原廠程式碼審核

- [ABI／stack](HOOK_ABI_AUDIT_2026-09-16.md)：固定 callsite 的原 producer 不使用 entry LR 作資料；
  可研究不改 SP、原函式恰好一次、返回後僅使用 r0/r1 的 leaf recorder。原 continuation 會覆寫
  NZCV，但不能因此破壞 APSR Q/GE。這是實作形狀依據，尚無 payload／已批准 buffer。
- [lifecycle](HOOK_LIFECYCLE_AUDIT_2026-09-16.md)：原廠已有 slot disable → scheduler ready 的配對。
  ready 在同步 callbacks 全數返回後發布；不能將原無限等待或含 abort 的整個函式直接重用。
  仍需查明阻止並行 re-register 的 owner 路徑、實際執行 core 與 cache publication。

上述未知應先從既有反編譯與 ARM 原指令追完；不是直接要求相機試錯。
不能把 ABI 可行、native ready 或主機健康鎖任一項，單獨當作完整 hook／AF 驗收。
