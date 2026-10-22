# Face 啟用與結果來源的固定地址稽核

2026-09-27；僅離線檢查 Ver.5.02 decomp 與 `out/seg0_c0000000.bin`，未呼叫相機或 getter。此筆記提供 bounded read 候選，不能把結果旗標、debug override 或 stored menu enum 混成「臉辨目前有有效輸出」。

## 1. 結果管理器與三個 prefix bytes

`M=0xC37CCA9C` 是確切的 singleton 地址。ROM `C05A9E14 MOVW r4,#CA9C`、`C05A9E18 MOVT r4,#C37C`；`C05A9E90 MOV r0,r4` 返回同一地址。初始化 guard 為 `C37CCA8C`，初始化將 `[M]=C2DFAB00`，清 `M+4..+473` 與 `M+474..+87F`。此路徑未見依 still/movie 模式改變 M，亦未見 `C037...` 替代地址；不能據此排除別處的 UI 副本或 MMU alias，但不可自行改讀推測 alias。

| 地址 | 寬度 | 已核對 writer / 精確限制 |
|---|---:|---|
| `M+4=C37CCAA0` | byte | `Detections::v7 C05A8CB0` 在 `C05A8CE0` 寫 1；`Detections::v2` 在 `C05A8F14` 清 0 後呼叫 publication；`Detections::v3 C05A9298` 也清 0。face parser 與 eye result 在此值為 0 才 publish。可描述為 publication hold/deferred flag；不是啟用 face detect 的設定。 |
| `M+0C=C37CCAA8` | byte | face parser `C05AAFF8` 依通過篩選的 `uVar6` 是否非零寫 1/0；ROM `C05AB2CC` / `C05AB2DC`。不是選單啟用狀態；零值可代表沒有保留下來的 parsed face。初始化與 face reset 的 bulk copy 也能清除此欄。 |
| `M+0D=C37CCAA9` | byte | face parser：`param_3!=0` 清 0；否則當 Detections+0D=0 或 accepted count=0 時設 1，並設 M+471=1；ROM `C05AB2E0..328`。eye publisher `C05AE4F0` 同樣依 param_3==0 設 1 與 M+471，否則清 0。它是 face/eye publication 路徑旗標，不能當 user eye setting 或幾何 valid。 |

decomp：`blk_c05.c:130081`（v7）、`:130171`（v2）、`:130324`（v3）、`:130902`（singleton）、`:131593`（parser）、`:134165`（eye publisher）。不是對全映像所有 bulk writer 的完備證明。

真正 Detections runtime gate 在另一物件 `D=C37CCA04` 的 `+0C/+0D/+0E`。`C05A8BE0` 將外部三個 bytes 複製至此處；`Detections::v2` 以 D+0C gate face 工作，將 D+0D 傳給 `C05AA8F8`（寫 FaceAndEyeDetection object+4），以 D+0E gate AAT。可另讀固定 `C37CCA04,0x14` 和 guard `C37CCA18,4`，保留 vtable、face/AAT object pointers 與三個 raw flags；不得與 M+0C/+0D 混用。getter `C05A8B88` 會初始化 singleton，不執行。

### D runtime prefix 的 ROM guard 與解碼

| D 相對 offset | 寬度 | 初始化後的預期 / raw 語意 |
|---|---:|---|
| +00 | u32 | vtable `C2DFA528`，由 `C05A9DCC..DD4` 寫入 |
| +04 | u32 | face object pointer `C37CCA64`；`C05A8BAC` 呼叫 C05A9D60，後者 `C05A9DA0..DA8` 回此地址 |
| +08 | u32 | AAT facade pointer `C37CD408`；`C05AC1BC..1C4` 以 C37CD3E4+24 得到此地址，`C05AC220` 返回 |
| +0C | byte | face runtime gate |
| +0D | byte | eye runtime gate |
| +0E | byte | tracking runtime gate |
| +0F | byte | Detections::v7 暫時設 1，呼叫 v2 後清 0；不是第四項使用者設定 |
| +10 | 4 B raw | native lock storage；不解為主體或 mode |

guard `C37CCA18=D+14`，ROM `C05A8B94` 與 `C05A8BCC` 分別傳給 guard-acquire / guard-release。三個 runtime gate 的名稱不僅由消費分支推測：原廠 shell handler `C03E0A50` 接受三個值，依序交 `C05A8810→C05A8BE0`；其 usage 字串 ROM `C0BAFD3C` 明列 `(face) (eye) (tracking)` 與 `0=off 1=on`。此 handler 是 setter，不可為驗證而呼叫。D 的 flags 非零只證明該工作允許執行，仍不代表成功辨識。

## 2. 已提出的三個固定讀取範圍

| 範圍 | 內容 / 限制 |
|---|---|
| `C358E260,0x50`；guard `C358E2B8,4` | `C03A0410` 的 detection config singleton，ROM `C03A0430..478` 確認；constructor `C03A0480` 將前 0x1A bytes、+1C..43 清零，+4C 最後寫 vtable `C2DFA464`。這是 config/debug override 區，**不是 face menu setting**。例如 +0C 非零改走 C05A9C10 路徑；+0F 非零時 publication 清兩個 validity bytes；+0D 影響 detector request local_44=7/0。保留整塊 raw，勿只憑全零判定未啟用。`C03A0410` 會 lazy-init，不執行。 |
| `C37CCDB8,0x20` = M+31C | +00/+04 是 reference dimensions；`C05AB428` 的 param_3==0 選 ROM C2DFC540 的 **320×240**，非 0 選 C2DFC548 的 **640×480**。+08..14 對應 M+324..330 的四個 ROI/reference words；+18 對應 M+334 的 face state；+1C 只有 M+338 transformed-reference 的第一 word，不能當完整 tuple。 |
| `C37CCF10,0x28` = M+474 | parser `C05AAFF8` 在 `C05AB00C..01C` 把原始 0x40C-byte packet 複製至 M+474。此 40 B 前綴含 count u32、第二個未命名 header word、第一個完整 0x20-byte raw face record（P=M+47C=C37CCF18）。P+08/+0C center、+10 size、+14 score、+18 angle u16、+1C tracking ID；P+00/+04 保留未知。不要把 packet header 第二 word 自動當 exposure timestamp。 |

`M+334` 的 setter `C05AB3B8`：入 1 前更新 M+338 參考；`FaceAndEyeDetection::v3/v4/v5` 分別設 3/2/0，callback `C05AA7B8` 僅在值 1 時解析。此表只提供已核對的數字與分支，不把數字當完整狀態名稱。decomp：`blk_c05.c:131705`、`:131728`。

## 3. Face menu 的 stored enum 可用固定地址讀

`menu SetFaceDetectMode`（無值）確實在 `C03FC398` 的 argc!=1 分支走 getter；但**不適合當「全程無原廠內部寫入」的 getter**：

- `C0057AE8` 含 C31AC570/578/580/**588** 四個 lazy-init guards，還會經 C007B9C8 的 factory 初始化。
- `C005A180` 下游 `C0068D38` 會寫 menu-item +11 recursion byte；可能更新 +14 cache 與 +5 cache-valid。
- `C00B5480` 又呼叫 `C008ACF0`（storage lazy-init）與 `C00897E8`（native lock）。

所以既有 no-arg menu 指令應描述為「不要求變更使用者設定」，不能宣稱原廠函式完全沒有任何內部 RAM 寫入。本次候選改讀固定 stored bytes，完全不呼叫以上函式。

定位鏈已核對 ROM：

1. `C005A180` 取 factory vtable+E4；ROM `[C07397D8+E4]=C0084B00`，函式回 factory+`B80`。factory 固定 base C31AC59C，因此 face menu item 為 C31AD11C。
2. factory constructor `C007BA18` 對 `param_1+2E0`（word offset，即 +B80）建立 item id **0x39**，vtable 設 C073FD68。該 vtable 的 +18 是 C0080DF8，後者以 id 呼叫 `C00B81E8`。
3. ROM `[C07461DC+0x39*4]=[C07462C0]=C00B5480`；`C00B5498 MOVW sb,#49C` 後回 storage-selected-bank+49C。
4. `C008ACF0` ROM 明示 storage base **B=C31AE3B0**、guard **C31AE3A8**。
5. `C0089808..82C` 讀 **byte** `[B+B19C]`：零選 B+4F0C；非零選 B+A7D4。最後加 +49C。`C0068D38` 的 `*puVar1` 是 **4-byte enum**，不能只讀一個 byte。

最小固定範圍：

| 名稱 | 地址 | 長度 |
|---|---|---:|
| menu-storage initialization guard | `C31AE3A8` | 4 B |
| bank selector（只解最低 byte） | `C31B954C` = B+B19C | 4 B |
| selector==0 的 stored FaceDetectMode | `C31B3758` = B+4F0C+49C | 4 B |
| selector!=0 的 stored FaceDetectMode | `C31B9020` = B+A7D4+49C | 4 B |
| 再讀同一 selector | `C31B954C` | 4 B |

若 guard 未證明 initialized、selector 前後變化，則不選 active stored value。即使一致也只是夾讀，不是 seqlock：A→B→A 仍可能，且沒有防止欄位在區間內改變。保留兩銀行原值，對被選者標 `stored_menu_face_mode_raw`；**尚未核對 off / FaceOnly / FaceEyeAuto 的 enum 名稱映射，不補造名稱**。此 stored 值也可能經 menu constraints/override 才成為目前 applied 值，不能單獨证明 face engine 正在跑。

相關行：`blk_c00.c:64348`、`:66315`、`:76164`、`:84844`、`:85091`、`:95788`、`:100670`、`:101455`、`:139700`、`:142878`；`blk_c03.c:172774`。

另有 UserSetting applied face enum 位於 `*(C3075230)+E8`（u32；`MenuItemFaceDetectMode::v3 C00A3538`）。因需核對當前 active pointer 及其生命週期，此次固定候選**不追指標**；不要誤讀 shell `setting` 編輯副本 C3758C80 作為 applied 值。

### 限時 enum 查核補充

未找到足以直接把 stored enum 數字綁到 UI 字串的列表。ROM 存在 `FaceEyeAuto`（C18D21B4）與 `FaceOnly`（C18D21C0），但它們位於排序字串庫；相邻次序不證明 enum 值，不能據此命名 1/2。

已核對的是 **applied** AF 設定的行為分支：`C0275E60` 在 `C0275EB0` 讀 snapshot+E8；值 0 跳過 face 選擇，1 於 `C0275EDC` 呼叫 `C0276030`（固定使用 group0 face），2 於 `C0275F04` 呼叫 `C02760B8`（讀 published selected-subrecord index，選 face/eye）。decomp `blk_c02.c:72461`、`:72529`、`:72560`。故可標 `applied enum 2 = selected face/eye path`，但**stored menu=2 尚不等於已量到 applied snapshot=2，更不等於成功辨識**。

`C02760B8` 的 selector 路徑先檢查 status face-present byte `S+280` 與 group0 face-valid `S+2B4`，兩者非零才檢查被選子記錄 valid；ROM `C02760E4..60F4`。因此即使 eye 子記錄殘留非零尺寸、selector=1，也不能繞過 face-present/face-valid 為零的 gate。

## 4. 解讀界線

上述檢查可辨別「singleton 未初始化、來源沒有 parsed result、runtime gate、stored menu bank」幾種不同事實。不能憑單次零值判定相機畫面、目標不存在、face detect 沒啟用或資料位置一定錯誤，也不能產生 source freshness、幾何尺度或合焦有效旗標。所有讀取保留不一致與未知，不做 setter、lazy-init getter、任意記憶體掃描或 alias 猜測。
