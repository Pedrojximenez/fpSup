# fp USB 連線速度上限(2026-10-01,靜態)

- 控制器:Synopsys DWC3 系列,基址 0x21000000(全域暫存器 +0xC100、DCFG 0x2100C700、DSTS 0x2100C70C)。
- 速度設定 DCFG.DEVSPD(bits 2:0)韌體只寫 **0(HS)/1(FS)/4(SS 5 Gbps)**:
  - 初始化 FUN_c01e3170:設定值 0xC2F165B4 = 0x320(<0x300 才用 HS)→ 4。
  - 連線/偵測流程 0xC01E3B..:DAT_c3032a92 1→0、2→4,強制 1(FS)。
  - **從不寫 5(SuperSpeedPlus,只有 DWC_usb31 才有)**。DSTS 也只比對 &7==4。
- 0x300B00xx(0x84/0x88/0xA0)是 BC/接頭偵測類暫存器,不是 SS PHY PLL。
- 韌體裡沒有 Gen2/SSP/10G 字串;只有 "SS (USB3.0)"。
- 未知:IP 是 DWC_usb3 還是 DWC_usb31 → 要上機讀 GSNPSID 0x2100C120、GHWPARAMS0-7 0x2100C140..0x2100C15C、
  GVERSION 0x2100C1A0(只有 usb31 有意義)。GHWPARAMS3 的 SSPHY 介面欄位可看 PHY 型態。
- 超頻(PHY PLL 偏離 5 GT/s)原理上不可行:主機端接收器 CDR 只容許 ±300 ppm(+SSC 5000 ppm 下展),
  鏈路訓練就會失敗;這不是相機單方面能改的。
- 實務(使用者 2026-10-01 更正):USB 測試目前 **390 MB/s**。5 Gbps 經 8b/10b 後線速 500 MB/s,扣協定開銷實用約 400–450 MB/s
  → 已貼近 Gen1 天花板,再快只能靠 Gen2(10 Gbps,128b/132b)。所以 IP 是否為 DWC_usb31 是關鍵問題。
  (skill 裡的 73 MB/s 是舊的 EP82 數字。)

## 上機實讀(2026-10-01,唯讀)
| 暫存器 | 值 | 解讀 |
|---|---|---|
| GSNPSID 0x2100C120 | 0x5533300A | **DWC_usb3 版本 3.00a**(不是 DWC_usb31 的 0x3331xxxx) |
| GVERSION 0x2100C1A0 | 0 | 一致:usb31 才有 |
| GHWPARAMS3 0x2100C14C | 0x0618C085 | SSPHY_IFC(bits1:0)=1 = **Gen1**;HSPHY_IFC=1(UTMI) |
| DCFG 0x2100C700 | 0x0048080C | DEVSPD=4(SS) |
| DSTS 0x2100C70C | 0x0082F2FC | CONNECTSPD=4,目前以 SS 5 Gbps 連線 |
| GUSB3PIPECTL 0x2100C2C0 | 0x01080002 | |

**結論:控制器是 DWC_usb3 3.00a,硬體本身只到 Gen1 5 Gbps,沒有隱藏的 10 Gbps。** 390 MB/s 已是天花板。
