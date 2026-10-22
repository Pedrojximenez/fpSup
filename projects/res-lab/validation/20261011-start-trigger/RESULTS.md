# 相機啟動檢查，2026-10-11

完整讀回 AutoRun 4,666 B（SHA `2e77dfe3529006d2cb95ac01e206048efe495493434c05f1ed8fad4ecd22bf96`）
及 LOADER 27,652 B（SHA `ecae97aff1c484d878f1ae5c277bc1b9607860f49601c4832c08da97ff0b801a`）。
兩者目前不成套：AutoRun 已有新 Fast bootstrap，LOADER 仍為舊零 section 的管理版 core，
没有 store provision／abort／Instant hook 的 shared stage2 封裝。

- 本次啟動的 Fast bootstrap 程式確實在 `C072F700`；它要求 magic `93528A87`，
  設定區 `C3075264` 實際為 `5C502AA9`。不匹配時會返回，走完整 AutoRun fallback。
- Instant callsite `C03DA420` 是原廠 `EB0000CC`，尚未掛鉤。
- registry depth 1、只有 console callback；echo slot 已還原 `C03D99A0`；待機未錄影。
- LOAD.LOG START 8.192911 s，DONE rendezvous 13.095816 s，相差 4.902905 s。
  這是最後一次 Sup 初始化的時間戳，DONE 不含 LOAD.LOG 寫入及完成畫面／AutoRun 收尾；
  不是螢幕可操作時間或精確的電源開關秒數。

原始檔與結論在本目錄；shell 原生 getter 記錄在既有 sidebar-v13 commands.jsonl。
沒有寫入卡片、改設定區、重啟或錄影。後續更新需使用帶 SupManager 的完整 boot_card 配對，
保留既有 Sup 與停用清單，不能只更新 AutoRun 或拿普通 Merge loader 替換管理版。
