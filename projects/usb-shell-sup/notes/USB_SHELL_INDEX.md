# USB shell 筆記索引 — 哪一份還算數 (2026-09-09)

兩週下來 shell 相關的筆記累積到 16 份,互相推翻但**沒有一份說自己被推翻了**。
這份的用途只有一個:先看這裡,再決定要不要翻下去。

內容沒有被改寫或刪除,只在被推翻的檔案頂端加了一行指路。

## 製作新 sup 的入口（2026-09-23）

agent 製作／修改 sup、AutoRun、loader、stage2 或 Fast start 前，先讀
[SUP_BUILD_RULES.md](../../../fpSup/SUP_BUILD_RULES.md)。這是單一製作規範，
不是另一份日誌；實作與驗證仍併入 [CARD_BUILD_PIPELINE.md](CARD_BUILD_PIPELINE.md) 及相關產品的共用紀錄。

## Loader v3 設計(2026-10-06)

[LOADER_V3.md](LOADER_V3.md):一個 sup 一塊(PC 相對)、`\fpSup\*.BIN` 依檔名載入、sup 自己 claim/放棄;**設計未實作**。

## 開機時間(2026-10-04)

[AUTORUN_CHAR_DELAY.md](AUTORUN_CHAR_DELAY.md):AutoRun 每個可見字元 ~1.9 ms(註解也算),11.5 → 3.0 s;**第一次把 echo 交給 cave 之後的 AutoRun 指令不會執行**。推翻 BOOT_TIMING 的「8.9 s 不歸我們管」。

---

## 現在是真的(用程式碼查得到,不是回憶)

**端點 —— 這是最大的一個落差。**

| 端點 | 用途 | 出處 |
|---|---|---|
| EP 0x01 OUT | 指令 | `host/fpshd.c:31` |
| EP 0x82 IN | 回應 | `host/fpshd.c:32` |
| EP 0x83 IN | 推送(interrupt→bulk,1024/burst 3) | `patches.py:15-20` |
| ~~EP 0x05 OUT / EP 0x84 IN~~ | **不存在** | 描述元沒啟用;實測 StartTransfer 100/100 回 −1 |

**21 份筆記把 EP05/EP84 當成活的傳輸層**,那是 8 月中的配置。
EP83 這個更正**一份筆記都沒寫到**,只活在記憶裡([[push-endpoint-is-ep83]])。
這就是「資料很亂」的具體形狀:更正在一個地方,文件在另一個地方。

**程式碼位置**:`fpSup/fp_usb_shell/`。
`codex/usbshell/` 還在磁碟上但不是現行樹。

**版本**:`fpshd` 3.0.0(`host/fpshd.c:33`)。最後一個 git tag 是 `fp-usb-shell-v2.0.0`,
中間的改動(端點搬家、worker 熱抽換、`--loader`、`HOOK_RESTORE`)沒有版本邊界。

---

## 錄影凍結 —— 被推翻了五次的那條線

按時間讀,不要單獨讀任何一份:

| # | 日期 | 檔案 / 出處 | 當時的結論 | 後來 |
|---|---|---|---|---|
| 1 | 08-20 | `SHELL_COEXIST.md` (37 KB) | worker armed 的端點衝突 | ❌ |
| 2 | 08-21 | `V27_FREEZE_ROOTCAUSE.md` | idle-suspend/link-down 單一機制 | ❌ |
| 3 | 08-23 | `RECORD_SHELL_COEXIST_RESOLVED.md` | host 在 record-start 下交易 | 部分 |
| 4 | 08-25 | 記憶 `daemon-blocks-recording` | 是連線本身,不是輪詢 | ❌ |
| 5 | 09-07 | 使用者 | 「跟斷開 daemon 無關,那是過時資訊」 | **現行** |

②的結尾寫著「根因錨定 —— 單一機制、6 條全自洽、替代假設全排除」,兩天後就被推翻。
自洽不等於對,這正是 `re-verification-discipline` 記的那個陷阱。

**現行做法**:不要因為 daemon 連著就作廢一次錄影測試,也不要要求使用者拔線。
真正踩過的限制只有兩條,在 `USB_SHELL_HOOK_WORK_POSTMORTEM.md`:
池 `0x44F6ADC0` 是 shell 自己的傳輸緩衝、閒置狀態量不到錄影中的數字。

---

## 重複與撞名(兩個真的會害人的)

- `notes/projects/usb-shell-sup/USB_SHELL.md` 與 `fp_usb_shell/docs/RE_NOTES.zh-TW.md` **逐位元組相同**。
  改一份不會動到另一份。
- `notes/projects/usb-shell-sup/SHELL_COMMANDS.md` 的內容其實是 `fpSup/docs/SHELL_CAPABILITIES.md`,
  而 `fpSup/docs/` 裡另有一份**不同內容**的 `SHELL_COMMANDS.md`。
  同名不同內容,兩邊都在。

---

## 逐份狀態

| 檔案 | 日期 | 狀態 |
|---|---|---|
| `SHELL_COMMANDS.md` | 08-21 | 現行(77 條指令表 @ `0xC0BAC14C`),但檔名見上 |
| `USB_MODES_COMPLETE.md` | 08-25 | 現行(六組 gadget、DALEPENA) |
| `USB_SHELL_HOOK_WORK_POSTMORTEM.md` | 08-25 | 現行,而且是這批裡最該讀的一份 |
| `SHELL_MEM_RANGE_LIMITS.md` | 08-25 | 現行(靜默失敗,會讓錯資料看起來像對的) |
| `USB_GADGET_REGISTRATION.md` | 08-25 | 進行中,沒有結論 |
| `RECORD_SHELL_COEXIST_RESOLVED.md` | 08-25 | 部分 —— 見上表 ③ |
| `USB_SHELL.md` | 08-26 | 重複檔;指的 `codex/usbshell/` 不是現行樹 |
| `HOOKPUSH_PACING.md` | 08-24 | 節奏規則可能仍成立,但寫的是 EP84 |
| `RAW_PUSH.md` | 08-20 | 設計仍可用,端點全部要換 |
| `USB_COMPLETION_PATHS.md` | 08-19 | 同上 |
| `USB_COMPOSITE_MAP.md` | 08-19 | 同上 |
| `USB_COMPOSITE_RECIPE.md` | 08-19 | 同上 |
| `EGRESS_MAP.md` | 08-13 | 最舊的一份總表 |
| `RAW_GRAB.md` | 08-14 | 現行(still_raw_dump 會當機) |
| `SHELL_COEXIST.md` | 08-20 | **已推翻** |
| `V27_FREEZE_ROOTCAUSE.md` | 08-21 | **已推翻** |
| `LOADER_V2.md` | 09-25 | **現行載入流程**:關機寫回(所有卡)、loader hook 瞬開、Fast Start 2、上機結果、未解問題 |
| `WARM_BOOT_GATE.md` | 09-25 | 暖開機閘門的設計稿與最小測試(1.40 s 載入);後續以 LOADER_V2 為準 |
| `CARD_BUILD_PIPELINE.md` | 09-22 | 現行(出貨卡怎麼建、開機做什麼、哪些還沒收乾淨) |
| `BOOT_TIMING.md` | 09-22 | 現行(戳記、指令單價、快載入值 2.18 s、載入本身只有 3.5 ms) |

---

## 這份自己也會過期

加新結論的時候,回來改這裡的一行,或在被推翻的檔案頂端加指路。
成本是一行;不加的代價這兩週已經付過了 —— 我照著 EP84 找了不只一次。
