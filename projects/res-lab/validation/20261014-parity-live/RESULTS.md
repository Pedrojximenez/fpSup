# 虛擬 mode 230 / p74 與 9/29 原生 mode 12 / p13 的對等檢查 — 2026-10-14
consumer v22c（524f8853…，卡上含設定區 110a804e…）= v21 + 掛鉤計數 + 最後一份虛擬 profile 記錄抓取（S−0x400）。

1. 靜態稽核（../20261014-parity-audit/PARITY_AUDIT.md）：韌體沒有在 8 個查表掛鉤之外辨識 mode / pid 而影響錄影。
2. clone 列（rowdiff.json、donordiff.py）：mode 230/231 的 TIM、META、R28、R38、R14、R68、REG 七張表與原生 mode 12 列逐字相同，只差 mode 編號；HS280（231）的 R38 另有預定的 video clamp 位元。
3. 錄影 profile 記錄（cap-h2s240.json）：SD 錄影時抓到的 p74 記錄 67 字，與「原廠 p13 欄 + 9/29 的 25 組實機讀回 + 0x30 = 239.76」**逐字相同**。
4. 程式碼全區比對（codediff-c0000000-c0730000.json）：0xC0000000–0xC0730000 共 72 個非 cave 的改動字。
   - consumer：54 個掛鉤 + 9 個 PAIR 字 + C0189440。其中 13 個與 9/29 同址。
   - 00SHELL：C0033B3C（bl → mov r0,#0）、C01E7704（beq → b）。SSD 測試關掉 shell 時不存在。
   - loader：C0000020、C03DA420。
   - LOAD.LOG：05STOPFX、10LOSS、20GYR2 未載入。
結論：表格、mode 判斷、profile 記錄都與 9/29 相同；剩下的差異只在 consumer 多出的掛鉤（錄影中每幀只有 hdrcopy 會跑）、PAIR 字與時脈閘門。
