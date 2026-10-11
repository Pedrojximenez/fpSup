# 暖開機閘門:利用 hook 殘存,讓穩態開機零條 AutoRun

2026-09-25 設計稿。**最小測試已上機通過**(`fpSup/fp_usb_shell/warm_gate_card.py`):暖開機閘門在通電後 1.400 s 進入,1.402 s 載入完成,AutoRun 跳過,shell 正常。

前提是同一天推翻的那件事(`fpSup/HOOKS_AT_POWER_OFF.md`「What survives a restart」、
記憶 `warm-restart-keeps-the-cave`):撥電源開關是暖開機,

| 區域 | 撥開關後 |
|---|---|
| 映像 + cave `0xC0000000..0xC2F30800` | **保留**(補丁、cave 程式、cave 狀態字) |
| BSS `0xC3000000..0xC38D6FB0` | 清零(註冊、池指標 `0xC3757A7C`) |
| 堆積 / 池 | 配置器重來 |

2026-09-17 那個「hook 一個命令,有 hook 就代表注入區還在」的設計
(`research/firmware/notes/AUTORUN_INTERPRETER_AND_ABORT.md` §6)當時因為「RAM 不留」被放棄,
改走設定區。**前提已經翻了,那條路可以回來 —— 而且可以走得比當時更遠:不是提早中止 AutoRun,
是根本不讓它開始。**

---

## 1. 一句話

把韌體**唯一**啟動 AutoRun 的那條 `bl` 改成跳進 cave 的閘門。暖開機時補丁還在,閘門直接叫
住在 cave 的 loader 讀 `fpSup.BIN`,然後**不呼叫 AutoRun 就返回**。冷開機映像重載,補丁自然消失,
走今天的路徑,順手把閘門裝回去。

## 2. 掛點(靜態讀出,`out/MAIN_c0000000.bin`)

```
0xC03DA3F8  push {r4,r5,lr}
            ldrb r3,[r1] ; ldrb r2,[r1,#3] ; tst r2,r3 ; beq 不跑
0xC03DA414  movw/movt r0, 0xC0BABDD8        ; "\AutoRun.txt"
0xC03DA41C  mov  r1, #1
0xC03DA420  bl   0xC03DA758                 ; ★ 原字 0xEB0000CC
0xC03DA424  mov  r2, #0                     ; 回傳值不看
```

只改 `0xC03DA420` 一個字:`bl gate`。閘門拿到的 `r0/r1` 原封不動,放行時就是
`b 0xC03DA758`(尾呼叫,`lr` 仍指向 `0xC03DA424`)。

**好處是這個點天然帶了兩個閘:** 韌體已經判斷「這次要跑 AutoRun」,而且它接下來本來就要在
這個情境開檔、配 ctx —— 所以檔案 I/O 與配置在這裡是合法的(比陀螺回呼安全,
見 `release-build-notask-loader` 的反證)。

## 3. 零件

| 零件 | 住哪 | 大小 | 誰寫 |
|---|---|---|---|
| `gate.S`(新) | **固定**位址 `GATE_AT = LOADER_END`,`CAVE_ARENA` 往上推同樣長度 | ~24 字 | `fpSup.BIN` 的一個區段 |
| 掛點字 `0xC03DA420` | 映像 | 1 字 | `fpSup.BIN` 的**最後**一個區段(在 gate 之後、同一次快取維護) |
| loader | `CAVE_LOW 0xC072DE64`(已經在、已經會殘存) | 不變 + 幾字 | 不變 |
| 握手字 `STORE_FROM 0xC072F6F8` | 注入區 | 新值 `2` = 從閘門來 | 閘門 |

閘門**不能跟 cave 配置器要**:stage2 每次載入都把 `CAVE_BUMP` 重設回 arena 底,
閘門若在 arena 裡,下一次載入就會被發給別人。所以它是 arena 下方的固定錨點 —— 正符合
`cave-zero-map-is-full` 的規則「cave 只留錨點」。
(順帶確認:閘門路徑一樣經過 stage2,所以 `CAVE_BUMP` 每次開機照樣重設,**不會因為跳過
AutoRun 而逐次洩漏**。)

## 4. 閘門流程

```
gate(r0, r1):                       ; 只用立即數,不讀 literal pool
    [0xC3757A7C] != 0 ?  → b 0xC03DA758     ; 這次開機已載過(熱插卡再觸發)→ 照舊
    loader 區 sum == GATE_SUM ?  否 → b 0xC03DA758    ; 殘存的不是我們認得的 loader
    STORE_FROM = 2
    r = loader.boot()               ; 開 fpSup.BIN → 先驗表頭 → 才配池、放區段、跑 entry
    r != 0 ?  → 還原 r0/r1,b 0xC03DA758    ; 卡上沒有檔、或檔不是這個 loader 的
    return 0                        ; 不跑 AutoRun
```

loader 要改的只有三處:

1. **`STORE_FROM == 2`**:不寫設定區、不武裝 abort、不動 `ECHO_SLOT`(根本沒有腳本在跑,
   武裝 abort 會留下 `echo` 指向 cave 的陷阱)。
2. **身分檢查提前**:`fpSup.BIN` 表頭加一個字 `LOADER_MAGIC`(= 現有的 `sha256(loader)[:4]`),
   loader 讀完表頭**先比對**,不符就還檔案物件、回傳非零 —— **在配池之前**,否則放行後
   AutoRun 會再配一次,兩個 1 MiB。
3. 失敗路徑要回傳值(今天 `load_stop` 在 debug 版是空轉,閘門情境下絕對不能空轉)。

## 5. 開機路徑

| 情況 | 走哪 | 命令數 |
|---|---|---|
| 冷開機(映像重載) | 掛點是原廠 → AutoRun → store_boot → loader → stage2 **裝閘門** | 今天的 66 / 211 |
| 暖開機,同一張卡 | 閘門 → loader → 返回 | **0** |
| 暖開機,換了一張別的 sup 卡 | 閘門 → 表頭 magic 不符 → 放行 → 那張卡的 AutoRun | 那張卡的 |
| 暖開機,空白卡 / 沒有 `fpSup.BIN` | 閘門 → 開檔失敗 → 放行 → AutoRun 自己找不到檔 | 0 |
| 開機前接 SSD | loader 已有「F_VOL 開不了就改開 volume 1」的退路 | 0 |
| 熱插卡 | 池指標非零 → 放行,等於今天的行為 | 同今天 |

預期:穩態開機 ≈ 相機自己的 ~8.9 s + 載入 3.5 ms。省掉的是整份 AutoRun
(`boot-time-levers`:42 條 ≈ 2.8 s;加上解譯器本身的啟動)。

## 6. ⚠ 風險與必須先有的安全網

**這是第一個「上一次開機的程式碼決定這一次開機怎麼走」的設計。** 一個壞掉的閘門會跟著
每一次暖開機,不管插什麼卡。所以:

1. **先量「什麼會重載映像」。** 拔電池、關 30 分鐘都還沒驗(記憶裡明寫待測)。
   這是唯一的「重設鈕」,沒量到之前不上閘門卡。
2. **先做復原卡 `fpSup-GATEOFF`**:沒有 `fpSup.BIN`,AutoRun 只有一行
   `mem set 0xC03DA420 0xEB0000CC`。閘門在它上面開檔失敗 → 放行 → 補丁拆掉。
   **這條路徑就是空白卡那一列**,所以閘門「開檔失敗就放行」必須是最先驗、最簡單的一段。
3. **閘門在開檔之前不能做任何會等、會寫的事。** 表頭檢查之前唯一的動作是讀兩個字。
4. **換卡殘留(既有問題,不是新的)**:og 的映像補丁今天就會殘留到只有 shell 的卡上。
   閘門讓這件事變成可以處理的:stage2 在放每個**落在 cave 之外**的區段前記下
   `(位址, 原字)` 到 cave 的復原表,閘門在 magic 不符時先回放復原表再放行。
   **要不要做看使用者:** 做了,拔卡換卡就回原廠;不做,og 會跟著機身直到冷開機。
5. **掛點字與 poweroff 拆除互不相干**:它是映像→映像,`poff_disarm` 不能拆它;
   反過來指向池的 hook 照舊在關機拆(閘門路徑一樣跑 payload 的 `s_poff`,BSS 的註冊每次重做)。
6. **執行情境未驗**:`0xC03DA3F8` 是誰呼叫、在哪個任務、開機第幾毫秒、熱插卡 / USB 大量儲存
   退出後會不會再呼叫 —— 全是推測。§7 第 1 步先量。

## 7. 上機步驟(照 `freeze-postmortem-discipline`:一次一件)

1. **觀察版閘門**:永遠放行,只做 `[GATE_LOG]++` 和記 `TICK_US`。
   debug 卡上暖開機 ×5、熱插卡 ×2 → 讀出呼叫次數與時間點。
2. **復原卡**先做、先在觀察版上驗一次拆除。
3. 閘門與 loader 的改動先用 `runprobe.py` 借 echo 在活著的相機上跑一次(既有規則)。
4. 開快路徑,shell 卡:
   - 暖開機 ×10(ping 有回、`tickm` 記開機時間)
   - 不錄影關機 ×10、錄完關機 ×3(`HOOKS_AT_POWER_OFF` 測法,gyro 合併卡)
   - 換卡矩陣:shell→og3k、og3k→shell、gyro→空白卡、任何→復原卡
   - 冷開機 ×2:確認掛點回原廠、走慢路徑、裝回閘門
   - 開機前接 SSD ×2
5. 合併卡(`fp-merged-card`)與發布路徑最後才接;`release_card.check_sections` 要認得
   掛點區段與 `GATE_AT`,`cave_audit.py` 加 `GATE_AT` 這個錨點。

## 8. 不做的

- **不把閘門再往前挪**(例如掛到 SD 掛載完成)。AutoRun 的觸發點是「檔案系統好了、
  而且韌體本來就要在這裡開檔」的最早時刻;更早沒有證據能開檔。
- **不靠熱記憶體放 payload**。堆積位址每次不同,讀一次 `fpSup.BIN` 只要 3.5 ms,沒有東西可省。
- **不刪設定區路徑**。冷開機仍然要它,閘門只負責暖開機。

相關:`AUTORUN_STORE_BOOT.md`、`BOOT_TIMING.md`、`fpSup/HOOKS_AT_POWER_OFF.md`、
`research/firmware/notes/AUTORUN_INTERPRETER_AND_ABORT.md`。
