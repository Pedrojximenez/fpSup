# 量測腳本 —— `../REDUCTION_KERNEL_MEASURED.md` 的附件

2026-09-22。素材:`~/Downloads/quality-tests-frames-public`(7 個 DNG)。
依賴:`numpy`、`rawpy`(scipy 不需要)。

| 檔案 | 用途 |
|---|---|
| `common.py` | 載入 DNG、減 black level、拆 CFA 平面 |
| `kernel.py` | 自由抽頭最小平方(整數對齊用,OG3K) |
| `local.py` | 分塊局部核擬合 |
| `warpfit.py` `freefit.py` `og2k.py` | 仿射對齊 + 自由核(OG2K 隔組用) |
| `noise2.py` | 光子轉移曲線,求 N_eff |
| `phslope.py` `subpix.py` | G1/G2 平面次像素相位(幾何判定) |
| `sep.py` `rwzm.py` | 16 相位 polyphase 擬合(RWZM) |
| `routes.py` `coh.py` | 路線模擬與疊紋/相干分解 |
| `psd.py` `spec.py` | 頻譜比較(早期驗證用,結論以上面為準) |
| `dmtest.py` `rowfix.py` `demo.py` | demosaic 比較與成對列幾何修正 |
| `rwzm_proto_clean.npz` | 量到的 RWZM 原型核(`OG3K → FHD`,r²=0.99923) |

腳本裡的路徑指向當時的 scratchpad,重跑要改 `common.py` 的 `S`。

## 2026-09-23 追加

- `cand.py` —— 候選路線模擬器。載入 `fhd_Wv.npy` / `fhd_Wh.npy`(16 條 RWZM 相位核),
  **把儲存順序還原成真相位順序** `W_true[q] = W_stored[(9q) mod 16]`(比例 25/16 之下
  第 n 個輸出樣本的相位是 `(9n) mod 16`,擬合時用的是 `n mod 16`),
  然後用一個通用 polyphase(相位取自 `floor(16*frac(m))`)模擬任意比例。
  內建路線:`bin2` `bin3`(感測器 ÷2 / ÷3)、`idbox(k)`(完美 k×k 盒,參考線)、
  `direct(R)`(全讀出 + RWZM R)、`after2(R)`(感測器 ÷2 + RWZM R)。
  數字見 `REDUCTION_KERNEL_MEASURED.md` §7.5。
- 依賴 `routes2.py`、`coh.py`、`common.py` 與那兩個 `.npy`。

## 2026-09-23 追加(二)

- `banding.py` —— 橫向痕跡的量化與評分(§7.7–7.8)。`phase_term()` 回報
  相位項佔輸出對比多少、以及列/欄方向的 mod-P 不均。
  **關鍵:兩相位路線的列不均剛好是 1.0×,不是巧合** ——
  偏離在相鄰列等量反向,所以圖樣落在 Nyquist,看起來是顆粒不是條帶。
- `blurmatch.py` —— 「低光用 FHD」的檢定(§7.9)。把對照組逐步模糊到紋理
  對比等於 FHD,再讀雜訊底。兩個場景都是 ×1.01。
- `final.py` —— 五區塊(織紋 / 控制列 / 畫框 / 椅布 / 桌面)的路線評比。
  **不要再用三區塊版本**:舊的「面板」有四成是同一塊白布(§7.6)。

**跑之前:** `common.py` 的 `load()` 讀的是解碼快取 `<S>/<mode>.npy`(6K / OG3K /
OG2K / FHD / 4K),不是 DNG 本身。快取不在 repo 裡 —— 先從
`~/Downloads/quality-tests-frames-public` 解出來,並把 `common.py` 的 `S` 指過去。
只有 `blurmatch.py` 是直接吃 DNG(用 rawpy),可以單獨跑。

