# fp AF 輔助：H 統計更新與 scheduler mode 1 的靜態稽核

日期：2026-09-16。韌體：SIGMA fp Ver.5.02。

本文件是離線原始碼／ROM 稽核，沒有操作 USB、啟動 AF、移動鏡頭或修改相機 RAM。
下列實機讀值由主研究程序提供，並非本文件作者重新量測；應另連結主程序保存的原始證據。

## 結論與適用範圍

**scheduler mode 1 與 mode 3 都可以作為受限的「統計發布路徑有進展」觀測條件。**
mode 1 不是異常，也不能硬性要求所有 Live View 都必須是 mode 3。兩者在 slot 0 都使用
divisor 1，scheduler phase 都以 3 為循環長度。

但 `C31F8CB4` 是 **scheduler 循環相位**，不是 H 的單調 generation ID，也不是感測器曝光 ID。
在下述 producer、observer、timing 條件持續成立時，觀察到不同 phase 可以支持已完成新的
scheduler pass，而這個 pass 會同步走過 H/L 發布。此為有條件的程式路徑推論，
不是已取得曝光對齊的 H／位置真值，更不是 DFD 校準完成。

H 值改變、USB snapshot sequence 改變、普通時鐘前進或 route=14，**都不能單獨證明 H 新鮮**。
如果 producer 或 timing 條件未確認，不應以睡眠若干毫秒取代新鮮度驗證。

## 1. 已提供的實機狀態

主程序提供 `C31F8CB4` 起連續 11 個 u32：

```text
00000001 00000001 C31F8CA0 C31F8C9C 00000001 C31F8CA4
C3206700 C090F0AC C090F2EC 00000001 00000000
```

以及 `C3206700` 起 4 個 u32：

```text
C09185A4 00000002 C09185F8 00000001
```

這些值符合：phase=1、mode=1、slot-0 observer 指向 `C3206700`、兩個排程表指標正確、
slot 啟用、observer state=2、lens-observer readiness 非零。
同次報告 debug counter/callback 均為 0、area 0 H=21015、L=51054。
**H/L 非零不是新鮮度證據**。尚須取得下一節的 timing selector／effective timing／raw subcycle
和實際 phase 進展；這份狀態快照本身未補足這些條件。

`C31F8CC4` 的 1 是 scheduler 在事件仍忙時會設置的旗標。它不是鏡頭 busy 或 H generation；
清除此旗標的路徑又受 scheduler debug 狀態影響，不應要求它恆為 0 作為 producer guard。
見 `C02074C0` 與 `C0207620`：
[blk_c02.c](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c02.c:6649)。

## 2. Mode 1 的排程表、循環長度與發布順序

### 表格直接由 ROM 驗證

slot-0 still table=`C090F0AC`；movie table=`C090F2EC`。表頭為兩個 u32，
之後是 7 組 `{divisor, phase-offset}`。各模式 divisor 為：

| scheduler mode | 0 | 1 | 2 | 3 | 4 | 5 | 6 |
|---|---:|---:|---:|---:|---:|---:|---:|
| slot-0 divisor，兩表相同 | 0 | 1 | 0 | 1 | 2 | 6 | 0 |

mode 1 的 pair 在 `C090F0BC/C090F0C0`、`C090F2FC/C090F300`，都是 `{1,0}`。
mode 3 的 pair 在 `C090F0CC/C090F0D0`、`C090F30C/C090F310`，也是 `{1,0}`。
still 表頭第二字為 0，movie 為 1，會影響 raw subcycle 閘，而不改變 mode-1 divisor。
原始 ROM：
[seg0_c0000000.bin](/Users/dido/Developer.localized/SIGMAfp_re/out/seg0_c0000000.bin)。

`C02075B8` 只對 mode 4 回傳 6、mode 5 回傳 12，其餘回傳 3。因此 mode 1 與 3 的相位通常
為 `0→1→2→0`。phase 自增和歸零不是單一原子步驟，讀到瞬間 3 應丟棄重讀，而非宣判
相機損壞。設定 mode 的 `C02073B8` 也會把 phase 清為 0，因此模式更換造成的重設不能
冒充新 frame。
[modulus getter](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c02.c:6703)、
[mode setter](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c02.c:6601)。

`C0207620` 順序為：

1. 讀取有效 timing，依 0／非 0 選 still／movie 表。
2. 核對 observer 指標、啟用旗標、模式／divisor 和 raw subcycle 條件。
3. 同步呼叫 observer 的 vtable+0x0C，等待其返回。
4. 完成 observer loop 後，raw subcycle 等於本次 timing 時才使 phase+1，然後按 modulus 歸零。

所以在本文限定的 mode 1／3、still timing=0、slot 0 正確啟用條件下，phase 的正常進展發生於
slot-0 callback 返回之後。不是先發布下一個 phase 再更新 H 的設計。
[dispatch 與 phase 更新](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c02.c:6840)。

### producer 與 observer

`AfContinuousObserver::v1 @C022C7E8` 先確認 lens-observer readiness，並要求自身 +4=2，
才走 `C023B968 → C023E9D0 → 後續 AF 決策`。
[observer](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c02.c:33526)。

因反編譯顯示 `C023E9D0(uVar2,0)` 時漏掉第三參數，另核對了 ROM 的 ARM 指令：

```text
C022C84C  mov r2, #0
C022C850  mov r0, r4
C022C854  mov r1, r2
C022C858  bl  C023E9D0
```

因此此 observer 的 **processing mode=0、第三參數=0**；不會走「第三參數=1，不發布 per-area
H/L」的例外路徑。`C023E9D0` 計算後，逐格寫 L 與 H 到 `C32986B4[]/C32985E8[]`。
[publication loop](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c02.c:44363)。

`C023E6F8` 的 +256 offset 僅出現在 processing mode=1；此 background mode=0 沒有該 offset。
`C023F1A8` 的額外 H 修正也只在 mode=1 才可能成立。這不代表 mode=0 是 raw 原值：分帶縮放、
區域累積與飽和仍存在，不能混用原廠 SAF mode-1 曲線門檻。
[offset 與處理](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c02.c:44234)、
[H correction gate](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c02.c:44651)。

## 3. 可直接讀回的 guard

以下是讀值／比對條件，**不是要求寫入這些值**。

| 位址 | 檢查 | 說明 |
|---|---|---|
| `C31F8CB4` u32 | 0、1、2；觀察不同值 | 循環相位，不以數值差換算漏掉的 frame 數 |
| `C31F8CB8` u32 | 本次固定為 1；另可明確支援 3 | 不接受中途變更或混合路徑 |
| `C31F8CCC` u32 | `C3206700` | slot-0 observer 指標 |
| `C31F8CD0` u32 | `C090F0AC` | still table |
| `C31F8CD4` u32 | `C090F2EC` | movie table |
| `C31F8CD8` 低 byte | 1 | slot enable |
| `C3206700` u32 | `C09185A4` | AfContinuousObserver vtable |
| `C3206704` u32 | 2 | producer branch state |
| `C3206708` u32 | `C09185F8` | lens-observer object vtable，額外辨識 |
| `C320670C` 低 byte | 非零（本次為 1） | `C022C4D8 → C022C930` 所讀 readiness |
| `C2F14A38` u32 | 記錄並確認前後不變 | `C0127DF8()` 的 selector |
| `C31D89BC` u32 | selector=1 時使用 | effective timing 的 cached 分支 |
| `30100048` u32 | selector≠1 時用 bits 16..26 | effective timing 的 MMIO 分支 |
| `30100588` u32 | low 11 bits=0 | 本文限定 still path 的 raw subcycle |
| `C3291534` u32 | 固定已驗證的 area；第一版限定 0 | H/L area index，不是畫面中心保證 |
| `C3298918` u32 | 包含所選 area，且保持穩定 | producer 的有效 ROI 數量；不以陣列非零代替 |

AfMgr 基底由 `C022AD58` 回傳 `C32044D8`；observer 分別位於 +2228、+2230。
[construction](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c02.c:32412)、
[base](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c02.c:32485)、
[readiness](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c02.c:33600)。

### Effective timing 不能只讀 MMIO

`C0127DF8()` 只是回傳 `C2F14A38`。`C0126010()` 的語意為：

```text
selector = u32[C2F14A38]
effective_timing = u32[C31D89BC]                    if selector == 1
                 (u32[30100048] >> 16) & 0x7FF     otherwise
raw_subcycle = u32[30100588] & 0x7FF
```

實機另觀察到 selector=`FFFFFFFF`（signed -1），不是讀取錯誤即可推定的值：
`C0127DD0` 明確有 `selector == -1` 分支；`C0126010` 對此仍走 MMIO。
第一版 whitelist 為 -1／0／1，仍必須前後一致、effective timing=0、raw subcycle=0。
不得把它任意改成 0 或 1 來配合主機工具。

本文最窄支援條件是 **effective_timing=0 且 raw_subcycle=0**，並確認 selector、mode 在
取樣前後穩定。非零 timing 並非相機錯誤，只是此第一版 post-publication 推論尚未涵蓋其
子週期／排程漏失情況，應回報 unsupported 而非強改設定。
[selector getter](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c01.c:24492)、
[effective timing](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c01.c:22704)、
[raw subcycle](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c01.c:22052)。

## 4. 第一版可採用的保守取樣流程

1. 先以獨立的 native motor completion／位置條件確認移動結束。`g_afpos` 或舊 sweep history
   不可取代此步。
2. 記下完成後的 scheduler phase 和完整 guards；任何 guard 不支持就停止 H-based 動作，
   不自動發動原廠 AF。
3. 透過主機有期限地讀取 phase。只把 `0..2` 中「與上次不同」算一次**觀察到的進展**；
   不假設讀值相同就是沒有 frame，也不以 modulo 差估計真實 frame 數。
4. 至少丟棄兩次已觀察到的 eligible pass 進展，再加上明確記錄的保守 settling 時間。
   此數量有原廠程式的兩次 Vd wait 先例，但不是本鏡頭光學 settle 已校準的證明。
5. 同一位置取得多筆 H；每筆夾讀 phase／guards，拒絕跨越可見更新邊界、ROI 變化、實際 gain、
   shutter、aperture、AF mode／filter configuration 變化、錄影開始或不明的 controller 活動。
   不比較不同 producer processing mode 的 H。
6. 使用「settled、scheduler-progress-checked experimental contrast」等有限名稱。
   若無進展／timing 不支持／資料一致性不成立，回傳無法判定，不能用最後一筆舊 H 繼續選方向。

原廠先例在 `C028D968` 的一條分支：`C035FF08` → `C0126310` → `C01262B0` ×2 → `C023E9D0`。
[native wait sequence](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c02.c:87273)。
**不要為了實作以上流程直接從 USB shell 呼叫 `C01262B0/C0126310`**：前者使用
`0xFFFFFFFF` event wait，後者又迴圈呼叫前者，會破壞有期限的控制和停止能力。
[blocking wait](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c01.c:22910)。

## 5. 仍不能宣稱的事情

- 目前沒有無條件、逐 H publication 增加的 generation counter。`C328E768` 只在
  debug callback `C33D30E4 != 0` 時增加；本次兩者皆 0。不要偷偷開啟 log／改 callback 來
  補 freshness，這是另一個修改範圍。
  [conditional counter](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c02.c:44394)。
- phase 是循環值；host 可漏讀整個循環，也可能在下一個 publication 進行中读到相同 phase。
  前後相等不是完整 seqlock，不能保證整個 H/L／曝光 tuple 原子同幀。H 單字對 settled 固定場景
  較容易保守使用，但仍應標註此限制。
- mode／selector 可以在兩次觀測間短暫變動再回復，純讀值不能形式化排除所有 ABA。要求使用者
  測試時不操作模式／曝光、保留日誌，是控制實驗條件，不是硬體 interlock。
- scheduler 進展是 CPU callback 執行的證據；本次尚未把 AF DMA 完成／感測器曝光時點／光學
  settle 做獨立時序校準。感測器或 AF DMA 異常時，scheduler 仍可能繼續執行。
- AF-S、route 14、固定 UI ISO 並不各自保證 producer 在跑或曝光不變；必須實測完整 guard，
  並比較實際 gain／HCG／光圈等。AF 原廠流程已觀察過短暫 gain 變化。
- background mode=0 仍使用模型提供的分帶縮放；H 隨 filter、ROI、曝光、主體移動與噪聲變化。
  `C343B7BC/C343B7C0` 是 HPF H/L cached getter 值，可作額外設定不變檢查，但僅這兩個值
  不足以覆蓋所有處理參數。
  [scaling](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c02.c:44579)、
  [HPF getters](/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full/blk_c03.c:29272)。

本稽核不授權改 AF observer、scheduler table、timing register、debug callback、韌體或 SD 卡。
它只界定現有 native 路徑下可以查驗的條件與不能跨越的證據邊界。
