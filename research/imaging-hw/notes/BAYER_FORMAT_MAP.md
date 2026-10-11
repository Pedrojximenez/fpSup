# fp RAW Bayer 格式圖 (從韌體 RE，非盲猜)

來源：`FrameExpos_s @0xC0315C10`（rawpath.c，即每幀曝光提交點）。它 param_2 =
raw-path descriptor **0xC3439404**（frameexpos_capture.S 已用同一顆）。descriptor 內
是 per-slot 陣列（0x10 stride），加上模式欄位。

## 兩個 RAW 來源

### A. 全幀 RAW（stills / movie 主路徑）
| 欄位 | 位址 | 意義 |
|---|---|---|
| raw_addr | `*(0xC3439404 + slot*0x10 + 0x38)` | 全幀 Bayer buffer |
| small_raw_addr | `*(0xC3439404 + slot*0x10 + 0x3c)` | 同幀降採樣 Bayer |
| analog_gain | `*(0xC3439404 + slot*0x10 + 0x34)` &0xFFFF | |
| bit depth | `*(0xC3439404 + 0x20)` | **0=12bit, 1=14bit, 3=10bit, 4=8bit** |
| endian | `*(0xC3439404 + 0x28)` | 0=little, 1=big, 2=middle |
| width×height | 動態 struct：`FUN_c0436590()` → `FUN_c04370e8(ret,&buf)`；`buf+0x58` 的 `[0]=w [1]=h`。另備援 `*(0xC3439404+0x1c)` mode struct |
| hvbin | struct `[0x14],[0x15]` | 水平/垂直 binning |
| zoom | struct `[0x12],[0x13]` | |

### B. LV Sample ring（subsampled，連續預覽 raw）
- 位址：**`0x50000000 + idx*0x100000`**（韌體自己的存取子 `Sample::v1 @0xC040F268` 確認）
- idx = `*(this+4)`，範圍 0..10（11 slots × **1MB**），由 `Sample::v3 @0xC040F528` 每幀 `idx=(idx+1)%11`
- **1MB/slot → 一定是降採樣**（全幀 1920×1088×2=4MB 塞不下）。之前用 1920×1088 解出垃圾就是因為尺寸錯。
- hook 點 0xC040F528 是好的 per-frame 節拍，但**它不含 buffer 指標**，位址用上面公式。

## 為什麼之前解出垃圾
1. MovSig latch `*(0xC375BF88)=0x49xxxxxx` 是 **YUV develop 輸出**（跟 gimbal-ai 的 HDMI 資料同源），不是 RAW。
2. 0x50000000 ring 是 **small/subsampled** raw，用全幀尺寸解必錯。

## 對 DFD 的結論
- **LV Small Raw ring（B）= 正確目標**：連續、1MB 好傳、能與 shell 對焦記錄共存（不必錄影→不會凍）。
- 降採樣對 DFD 沒問題（gimbal-ai 的 ROI 才 ~640px）；但**寬高/bit 要先 live 讀一次鎖定**，別再盲解。
- 全幀乾淨 Bayer = CinemaDNG（A 的 raw_addr），但要錄影 → 與 shell 焦點記錄互斥（會凍）。

## 鎖定格式的下一步（一次 live 讀）
shell 活後：`call FUN_c0436590` → `call FUN_c04370e8(ret, SCRATCH)` → 讀 `SCRATCH+0x58` 的
`[0]=width [1]=height`、`[8]==1?14bit`、`[0x10]=endian`。拿到真尺寸即可正確解 0x50000000 slot。

韌體 EA：FrameExpos_s 0xC0315C10、descriptor 0xC3439404、Sample::v1 0xC040F268、
Sample::v3 0xC040F528、smallraw manager getter 0xC0436590（singleton 0xC375D840）、
param copier 0xC04370E8。
