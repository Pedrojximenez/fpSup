# OG2K 3×3 後製修正對照(2026-09-26)

來源:舊 session `final3/`(A001_269–271 一格)。修正工具 `notes/reduction-kernel/og2k3x3_fix.py`
(解包/打包/讀回三道比對;先以同色 r−2 補末列,再把 G2/B 向上移 1/3 平面列)。

| 檔案 | 說明 |
|---|---|
| 1_stock.dng | 原廠 OG2K |
| 2_3x3_uncorrected.dng | 3×3 未修正 |
| 3_3x3_old_cr0.3711.dng | §7.51 舊修正(錯核,§7.58.2) |
| 4_3x3_lanczos6.dng | 新修正,Lanczos-6(12 抽頭) |
| 5_3x3_fourier.dng | 新修正,Fourier(反射延伸 96 列) |
| *_full.png | rawpy AHD、相機白平衡、bright=4,五張同參數 |
| compare_edges.png / compare_ring_zoom.png | 邊緣最多的區域,3× / 7× 最近鄰放大 |

分頻帶量測見 `REDUCTION_KERNEL_MEASURED.md` §7.61:新修正邊緣頻帶殘差 −0.023、G2 銳利度 0.92 = G1;舊修正 −0.222、0.54。
目視(rawpy AHD):差異細微;3×3 整體比原廠軟;Fourier 在高光邊下方似有輕微振鈴 [?]。
| 6_3x3_lanczos6_split.dng | 新修正,Lanczos-6 兩邊各 1/6(§7.62,預設) |
| compare_flat.png | 平坦區,上兩排正常、下兩排對原廠均值拉 4× 對比 |
