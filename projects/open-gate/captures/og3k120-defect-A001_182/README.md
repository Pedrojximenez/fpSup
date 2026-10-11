# A001_182 —— OG3K + 119.88 缺陷的實體證物

2026-09-27 09:11:19,使用者的 SSD(卡名 "Untitled"),原始 clip 共 33 個檔。
這裡只留第一幀。機制與四個指紋見
notes/OG3K_ENGINE_CONFIG_THREE_FIELDS.md §7d。

選了 OG3K + 119.88 -> 鍵 `OG3K120` 兩張表都查不到 -> 原廠退回
TAB3[0] = UHD30,而只看 FLAG 的 og3kout/aspect/aspect2/gs/fps 還開著。

## 解出來的標籤
```
NewSubfileType       0
ImageWidth           3856
ImageLength          2170
BitsPerSample        12
Compression          1
StripOffsets         79872
StripByteCounts      12551292
BlackLevel           ('262005/1024', '262005/1024', '262005/1024', '262005/1024')
WhiteLevel           4095
DefaultCropOrigin    (8, 5)
DefaultCropSize      (3840, 2160)
BaselineExposure     330/1024
FrameRate            120000/1001
```

## 四個指紋

| 指紋 | 值 | 該是 |
|---|---|---|
| 幾何 | 3856x2170 (UHD) | 3024x2010 |
| 幀率 | 120000/1001 | OG3K 做不到 119.88(上限 108.4 fps) |
| BaselineExposure | +0.322 | 12-bit 該是 +3.000 |
| 幀數 | 31 | UHD 12-bit @119.88 = 1.5 GB/s,寫不動 |

⚠️ 當時選了什麼沒有被記錄,所以這是很強的間接證據而不是證明。
