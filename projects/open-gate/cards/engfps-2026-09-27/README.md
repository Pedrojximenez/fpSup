# 引擎組態三欄的 A/B 測試卡(2026-09-27)

兩張**開發卡**,不是要給人下載的。差異只有三欄:畫布的 `+0x030`(引擎格率)、
`+0x090`、`+0x0C0`。背景與反編證據見
`projects/open-gate/notes/OG3K_ENGINE_CONFIG_THREE_FIELDS.md`。

| 目錄 | 內容 | fpSup.BIN sha256 |
|---|---|---|
| `shell-og3k/` | **修正版**:三欄補成原廠影片 profile 的值 | `be50b605…ddddf097` |
| `shell-og3k-baseline/` | **對照組**:`OG_HIRATE=none OG_ENGFPS=0`,逐位元組等於 2026-09-26 的建置 | `e005e16b…aa3186f7` |

`AutoRun.txt` 兩張完全相同(`56802a82…c2e44473`)—— 它只寫 loader。
97 個區段裡只有 4 個不同,其餘 90 個逐位元組相同:

```
0xC0731C40  只在修正版        FPSLATCH 資料字
0xC0730800  256 vs 240 B     fmttable +4 字(鎖存)
0xC0731000  同長度,內容不同    格式表 +0x2C:整數 nominal → 引擎格率 float bits
0xC0732400  476 vs 432 B     og3kcanvas +11 字(5 engfps + 3 PUT 0x90 + 3 PUT 0xC0)
0x00000000  同長度,內容不同    launcher(區段數與偏移移動了)
```

## 這兩張卡不留下任何永久痕跡

**沒有 Fast Start 2、沒有 loader hook** —— 刻意的。Fast Start 2 會寫設定區塊,
那撐得過抽電池;這次測試不需要快開機,所以不帶。卡上的東西全部寫進 RAM,
**抽電池即全部還原**。

## 裝法

兩個檔案複製到卡的根目錄(`AutoRun.txt` + `fpSup.BIN`),就這樣。
換組態就換整張卡或換這兩個檔,然後**冷開機**(USB 拔掉時關機,不然每次都是冷啟)。

熱更新(相機上已經有帶 shell 的卡在跑時):

```sh
cd fpSup/fp_usb_shell
python3 -B putfile.py ../../projects/open-gate/cards/engfps-2026-09-27/shell-og3k/fpSup.BIN '\fpSup.BIN'
python3 -B putfile.py ../../projects/open-gate/cards/engfps-2026-09-27/shell-og3k/AutoRun.txt '\AutoRun.txt'
python3 -B getfile.py '\fpSup.BIN' /tmp/rb.BIN --size 32768   # 讀回來比 sha
```

`putfile` 不截斷,比較前 32768 bytes 就好。

## 上機後要確認的事

選了 OG3K(`menu SetMovRecSize 4`)之後,`FLAG` 要是 1。
**熱載入時 `og3krestore` 不會跑**,所以要先用格式 setter 餵鎖存:
`menu SetMovRecFormat 0` -> `FMTLATCH` 0xFFFFFFFF 變 0 -> 再選解析度。

```python
import sys; sys.path.insert(0,'.../fp_usb_shell'); sys.path.insert(0,'.../open-gate/build')
from putfile import sh
import og3k_plan as P
rd=lambda a:int(sh(f'mem get 0x{a:08X},,4').strip().split('D:')[1],16)
rd(P.FLAG)        # 1
rd(P.FPSLATCH)    # 29.97p -> 0x41F00000 = 30.0；25p -> 0x41C80000
```

**錄影當下**讀引擎組態(channel 0,base `0xC31DF564`):

```
0xC31DF574  引擎格率        修正 30.0(0x41F00000)   對照 18.0(0x41900000)
0xC31DF5D0  管線延遲選擇     修正 0                   對照 1
0xC31DF5E8  影片旗標        修正 1                   對照 0
```

旁證:**待機**時 `0xC31DF574` 應該讀到 60.0,因為待機 LV 跑 MONIT1_60 @ 60 fps
(`imager mode_now` 可對)。這一條與我們的修正無關,是用來確認那一欄真的是格率。

## 每次錄影都要解 DNG

專案規則:錄影路徑的任何改動都必須解 DNG 驗證,不能看 live view。檢查項:

```
ImageWidth 3024   ImageLength 2010   BitsPerSample 12
DefaultCropSize 3008x2000 @ (8,5)    StripByteCounts 9,117,360
FrameRate 30000/1001                 BaselineExposure 3072/1024 (= +3.000)
```

2026-09-27 修正版實測 `A001_111` 以上全部相符(`build/fpcam.py` 的
`frame_tags()` 可自動抓)。

## ⚠️ 這兩張卡修的不是閃爍

`OG3K_ENGINE_CONFIG_THREE_FIELDS.md` §7:量到的閃爍在我們的程式碼**完全失效**
時照樣發生,全原廠 UHD 的事件率是 OG3K 的三倍多,而且使用者在乾淨卡冷開機後
FHD/UHD 仍然閃。**三欄是正確性修正,不是閃爍的修復。**
A/B 要比的是「有沒有把引擎組態補成原廠影片的值」,不要指望閃爍消失。
