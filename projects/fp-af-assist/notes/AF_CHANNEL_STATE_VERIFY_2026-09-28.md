# 高速通道現況核對：EP82 已完善上機，EP83 未接通

2026-09-28 核對。起因是「最新開發應該已經完善了一條高速通道」。結論：**確實有一條已完善且上機量過的高速通道，但那是 shell 的 EP01/EP82 指令／回覆通道；[第一個 AF hook／高速通道增量](AF_FIRST_HOOK_CHANNEL_2026-09-27.md) 所加的 EP83 接收仍未接通相機。** 本輪只做唯讀檔案核對與離線測試，沒有相機 I/O、沒有替換 daemon、沒有安裝 hook、沒有卡片或韌體修改。

## 兩條通道必須分開講

| | EP01/EP82 指令／回覆 | EP83 串流 |
|---|---|---|
| 性質 | host-pull：主機要、相機答 | camera-push：hook 主動送 |
| 相機端 | **已完善**，worker 把來源位址放進 `CAP_PTR`、TRB 直接指過去 | **未完成**，sender 仍是 synthetic |
| 實機量測 | **相機→主機 73 MB/s**（0.42 s）、卡→相機記憶體 183 MB/s（0.17 s）、`getfile.py` 端到端 1.17 s（原 76 s）；每次 1 MB 最快，4 MB 掉到 9.5、16 MB 只剩 2.1，瓶頸在主機端 | 只有 `StartTransfer` 100/100 被接受，**沒有一筆 bytes 實收** |
| 用於第一批 AF | 是。`af_hook_trial.py` transport 寫死 `EP82-raw-bulk`、`ep83_delivery=False` | 否。留給 P0-D 連續 session |

吞吐數字來源為 [fp USB Shell v3 README](../../../fpSup/fp_usb_shell/README.md)（§「The card was never slow」）；那是既有實機量測，不是本輪新量。EP84 另已確認不存在（`DALEPENA=0xA7`、physical 9 未啟用、Start 即刻被拒 100/100）。

## 逐列核對 AF_FIRST_HOOK_CHANNEL 的「驗證界線」

該筆記四列的界線敘述全部準確，沒有誇大：

| 筆記列 | 本輪核對到的事實 |
|---|---|
| 同 daemon EP83 接收「未替換執行中的 daemon」 | 原始碼確有 `EP83 <bytes> <shellline>` → `OK83`；11 tests 重跑全過（真實 `fpshd.c` ＋ fake libusb）。但執行中的是 **PID 69735，啟動於 2026-09-27 05:54:38**，binary `fpshd` mtime `2026-09-25T10:56:31`、52,416 bytes、sha256 `d0a1d48d230eb3e336b56bcb37104e69e721ce8c6d4114275f9937396f6b06fc`，`strings` 抓到 **0 個 `EP83`**，STATUS 字串自報 `transport=EP01-EP82`。原始碼 sha256 `08471e361df89201add030d0a122e28438d79220eca22654a9a8796f4d3444e2`（mtime `2026-09-27T20:39:50`），在 fpSup 仍是未提交的 `M fp_usb_shell/host/fpshd.c`，`host/tests/` 為 untracked |
| ARM helper「未在相機呼叫」 | 今天重跑 `af_hook_trial.py --inspect`：`helper_bytes=1100`、`worker_body_bytes=1404`、`rom_sha256=aaa5208a028d9c4aebb9cc8614add723d456e96b2a95914f433079954320e622` |
| 有限 hook 流程「預設 live guard 關閉」 | 同一次 inspect 回 `live_ready=false`、`shutdown_restore_verified=false`、`ep83_delivery=false`；`live_blocker` 為 AF callsite 與借用 echo 的 loader 關機還原未驗證 |
| recorder 724 bytes、`C022C858` 接點 | `af_publication.S:39-40` 為 `PRODUCER=0xC023E9D0`、`CONTINUATION=0xC022C85C`，檔頭標明 fixed `C022C858` callsite、OFFLINE CANDIDATE |

`hook-offline-20260927-v2/validation.json` 的 68 項（19＋18＋20＋11）離線通過、host candidate sha256 `d49af74430becc84ad77292af6a4f91ceff014b29b4d72a01e37d4bf29dd029f` 與 `installed=false` 亦相符。

## EP83 仍未閉合的部分

- `highrate/af_ep83_camera.c:638` 仍呼叫 `af_ep83_camera_make_synthetic`；`highrate/ep83_host_session.py:435` 硬要求 `camera_state=SYNT`。
- `highrate/build_ep83_camera.py:305/312/317` 的 `deployment_ready`、`loader_integration_complete`、`single_usb_owner_verified` 全為 false。
- 五層（sender result／camera private／control／host session／LibusbOwner）仍 single-use；單一 USB owner 未閉合。詳見 [transport gap](AF_STREAM_TRANSPORT_GAP_2026-09-27.md)。

## 因此第一批實收的真正前置只有兩項

傳輸速度不是目前的瓶頸——已完善的 EP82 通道足以一次取回 8,256 bytes（64 筆 ×128 ＋ 64-byte header）。擋住的是：

1. `verify_shutdown_restore()` 未完成，`--run-live-hook` 在任何相機 I/O 前即落 `status=blocked`。這是純離線工作，須核對實際卡 VBIN manifest 與 ROM PowerOff manager `C30756C4` 兩表，再用真實 loader 跑故障／暖開機模擬。
2. USB 不可用：2026-09-27 20:30 第一個唯讀 `version` 回 `LIBUSB_ERROR_NO_DEVICE moved=0/64`。

`af_hook_trial.py:282` 另會在動作前核對「執行中的 worker body 與已審核的 CAP_PTR 實作一致」，這項依賴上述 EP82 快速回覆路徑，不可繞過。

## 本輪重跑的離線檢查

```sh
python3 -B fpSup/fp_usb_shell/host/tests/test_ep83_host.py            # 11 passed
python3 -B projects/fp-af-assist/highrate/af_hook_trial.py --inspect --output NEW_DIRECTORY
```

沒有新增程式、沒有解除任何 gate、沒有產生新的實收證據。EP82 的 73 MB/s 是既有紀錄，本輪未重新量測；`camera=open` 之類的 STATUS 欄位仍是舊 handle 狀態，不代表相機現在可用。

## 接法已整理進 skill

兩條通道的實際接法（EP82 已完善的 `CAP_PTR`／TRB 回覆路徑與量測界線；EP83 的 host 協定、五項相機端未完成工作、單一 owner、TRB 與 stock PTP event sender 衝突、記憶體所有權、hook 不送 USB）寫入 [`.claude/skills/fp-camera-control/SKILL.md`](../../../.claude/skills/fp-camera-control/SKILL.md) 第 11 節，供後續直接查。skill 只整理已核對的事實與禁則，不含任何解除 gate 的授權。
