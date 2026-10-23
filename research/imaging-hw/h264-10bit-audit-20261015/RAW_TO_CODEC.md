# CinemaDNG 12-bit 來源到 MOV codec：ISP 交接追查

2026-10-15。**12-bit Bayer 來源已成立；尚未找到可驗證的 10-bit YUV 交接或 H.264 10-bit 開關。** 本輪新增的是 ISP 打包器、DITHER 設定及 MOV buffer 描述子的靜態接線，並排除一組容易誤認為位深的列舉。

只讀原廠映像、既有反編譯與研究資料；沒有相機 I/O、執行韌體、寫 RAM 或寫卡。映像 SHA-256 為 `aaa5208a028d9c4aebb9cc8614add723d456e96b2a95914f433079954320e622`。

重跑 `python3 -B research/imaging-hw/h264-10bit-audit-20261015/trace_raw_to_codec.py`。輸出 [raw-to-codec.json](raw-to-codec.json)、[相關函式全文](raw-to-codec-evidence.c)、[ROM 指令節錄](raw-to-codec-disassembly.txt)。報告保留反編譯來源及行號；本輪核對 35 支函式、306 列 profile 的 19,890 個 ROM words。

## 1. 已有來源與本輪邊界

CinemaDNG 的 RAW buffer 可以直接作為候選來源，無須先寫 DNG 再讀回。既有 [RAW writer 稽核](../native-calibration-20260924/cinemadng-raw-sink-audit.md) 已追到 12-bit 全幀 buffer 與 writer 交接；[Bayer 格式圖](../notes/BAYER_FORMAT_MAP.md) 記錄 `FrameExpos_s @ C0315C10` 及 `C3439404` 描述子，位深欄位在 `+0x20`。

本輪沒有證明一個新的「CDNG buffer → 高位深 YUV → codec」完整路由。以下輸出設定追查來自原生 ISP/MOV 呼叫鏈，仍需把當前 RAW 幀、ISP 輸出與 codec 的幀所有權、packing、stride 對上。

## 2. 打包與 DITHER 區塊已定位

診斷函式 `C01597B8` 直接引用名稱，`C019C810` 的傳輸描述子提供 MMIO 與 shadow 的交叉映射。名稱及位址不是由排列順序猜測。

| 區塊 | MMIO | shadow | words | setter |
|---|---|---|---:|---|
| YUV_PACK | `3011E004` | `3021236C` | 7 | `C01570D0` |
| YUV_PACK 相關區 | `3011E130` | `30212388` | 11 | 本輪未解欄位語意 |
| YUV_PACK 相關區 | `3011E1B0` | `302123B4` | 11 | 本輪未解欄位語意 |
| PST_TOP DITHER | `30116580` | `3021100C` | 2 | `C010C9D0` |

各 setter 使用 `C07D4360` 的 context offset 表，不能忽略 bank。`C010C9D0` 除寫入 DITHER 兩個 words，還清除 shadow `302110F0`，並把參數 `[2]&3` 及 `[3]&0xF` 寫入 `302110EC`。後兩個位址不在上述 DITHER 兩個 words 的傳輸描述子內，不能直接命名為同區塊的 MMIO。

`C01199C0` 從 `C31D738C` 複製 20 bytes 後呼叫 DITHER setter；`C011AB80` 提供相同參數的 getter。具名畫質設定函式 `PictureQualityCommonPrePst__v30 @ C0690618` 也會取得或調整這組參數，再呼叫 setter。這證明它是原生畫質設定的一部分，**沒有證明關掉它就會輸出 10-bit**，也尚未定位唯一的 8-bit 量化點。

## 3. 描述子 +0x101 不是已確認的位深欄位

已追到的資料流：

```text
profile/canvas +0x94
  → C0434EF8: engine config +0x60
  → C01D1630: C31DF5C4 + channel*0x1B0
  → C01D3580(channel)
  → C01CB9B8: 只有回傳值 == 1 時，設定 frame descriptor +0x101
       C01D3558(channel) == 0 → 2
       其餘                   → 3
  → C0179B38: 半高計算與打包器設定
```

`C01D3558` 的來源是另一個欄位 canvas `+0x90`，經 config `+0x84` 存入 `C31DF5E8`。這個旗標不能當作位深。

`C0179B38` 在 `+0x101 > 1` 時，會將部分輸出高度／列計算除以 2；值 2、3 另選不同的 writer packing bits。當描述子 `+0x2C` 低四位為 1，送往 `C01570D0` 的值如下：

| 描述子 +0x101 | setter 第一個 word | shadow 30212374／MMIO 3011E00C |
|---:|---:|---:|
| 0 或 1 | `00000000` | `00000000` |
| 2 | `00280000` | `00000101` |
| 3 | `00680000` | `00000301` |

表格是依 setter 算出的**驅動寫值**，不是硬體執行或輸出像素的驗證。半高與打包聯動較符合色度取樣／儲存方式的差異；尚未解出確切格式名稱，不能把 2、3 直接稱為 10、12-bit。

從原廠 ROM 重新讀取全部 **306 列、65 欄**，並與既有 profile 抽取逐 word 比對：**所有列的 canvas `+0x94` 都是 0**。因此沒有從這張原廠表找到可直接借用的特殊分支 donor。這不排除執行期改寫或其他路徑，也不能證明硬體不支援高位深。

## 4. MOV buffer 交接與格式旗標

`C0429910` 透過 `C0434EF8 → C01D1630` 發布 engine config，並為各輸出通道建立描述子後呼叫 `C01D69D0`。

`C0436F00(manager, channel)` 回傳 `manager + 0x18 + channel*0x34`。`C0428690` 從此描述子取得寬、高、張數、每張間距及位址，建立 ring；地址經 `C03C7E40` 轉換。它另呼叫 `C0428628(desc[12])`，將來源 flags 的 bit 0、1、5 映射為 1、2、4，再經 `C01D51C8 / C01D5200` 等設定路由。**這組 flags 不是已確認的 bit-depth enum。**

輸出完成端 `C0429470 → C01D7638` 取得當前輸出描述子；`C01822B8` 讀取硬體 bank index，`C0022FB8` 從目前的 ring handle 取得 buffer。此處讀到的是尺寸、路由及 buffer metadata，尚無已解碼的 10-bit precision 契約。

原生分配 helper `C0435D78` 對所選尺寸計算 `W*H*2` bytes。它是目前分配方式的證據，不能用來否定其他 packing 或重新配置 buffer 的可能性。

## 5. 尚不能從這些數字判斷位深

- `CNRO @ C015C230` 的 debug dumper：RAW 分支會依位深調整寫出長度，YUV 分支直接使用 `W*H*2`，不讀 depth。這只能證明 dumper 的假設。
- `C070AB40`：codec 描述子 `[5]` 控制 `300C02C0[4:3]`；原生 `C07254E0` 固定給 2。尚不能區分此列舉是排列、端序或精度。
- `C070D638`：對 `300C0238[2:0]` 寫 0、5、3，並保存列舉供 level 選擇使用。不是已確認的 10-bit 輸入選擇器。
- gamma／矩陣的係數位寬、1023／8191 等常數、名稱中有 DITHER，都不能單獨證明輸出 buffer 的有效位深。

公開資料也沒有完成 fp codec IP 的身分對應。[Socionext 的 codec 產品頁](https://www.eu.socionext.com/solutions/visual-solutions/video-codec.html)列有可編碼 AVC 10-bit 的其他產品；這不能套用到料號與 IP 尚未確認的 fp。

## 6. 下一個能改變結論的證據

1. 解出 YUV_PACK 與 writer 的每像素位數、每行 stride，找到可保留超過 8-bit 的輸出格式。須沿用 12-bit RAW 來源，避免先經已確認的 8-bit 預覽 buffer。
2. 解出 codec 輸入列舉及參考／重建幀配置，確認能保留 10-bit。即使只改 profile 選擇值能出碼流，也未必有真實的高位深像素。
3. 解出控制程式如何產生 SPS 的 profile 與 depth 欄位，或以受控單幀實驗取得原生 SPS 與解碼結果。合格結果須由標準解碼器接受，且成對輸入只改來源低兩位時，能觀察到可重現的輸出差異。

目前可據以繼續的是上述具體入口；尚沒有可標示為「10-bit 解鎖」的補丁。
