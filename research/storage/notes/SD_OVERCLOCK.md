# SD 卡匯流排超頻可行性(2026-10-02,靜態分析,未上機)

[C]=程式碼證實 [I]=推論

## 硬體
- SD 卡槽(id 0x0E,MMIO 0x28A00000)是 **PCIe 後面的 O2Micro SD 主控**(vendor 0x1217,device 0x8520/0x8740),不是 SoC 內建。[C]
  PCIe RC 0x302D0000/0x302D8000(FUN_c01f3028/3b40/3d60);身分檢查 FUN_c065fa40;0x8520 config 走 BAR1+0x200 信箱(FUN_c065fed8/fd70)。
  FUN_c01f1a00 對 id 0xE 直接 return → SoC 不供時脈。[C]

## 模式
- UHS-II 初始化 FUN_c06604c0:HC2 |=0x11000000、UHS Mode Select=7、0x2C PLL Enable。[C]
- 協商 FUN_c0662bc8 → c06611e0…c0661a28;結果:線道 0xC2F2E834、2L-HD 0xC2F2E830、Range 0xC2F2E838、N_FCU 0xC2F2E828、N_DATA_GAP 0xC2F2E82C;降級等級 0xC2F2E7C8(≠0 強制 Range A);MaxBlkLen 512。[C]
- 讀 218 MB/s > FD156 → 實際 HD312。[I] UHS-I 退路 FUN_c066b718(SDR104→…),CMD19 調校只在 UHS-I。[C]

## 時脈
- 0x2C 除頻欄位 0x02 → RCLK = 基準 ÷4;O2 PLL(config 0x304)= 0x2c28xxxx。[C]
- 依 Linux O2Micro 驅動,基準 200 MHz → RCLK ≈ 50 MHz,Range A 上限 52 MHz 的 96%。[I]
- 改 RCLK 需重做 UHS-II PHY 協商,否則斷鏈。[I]

## 驅動
- ADMA2 26-bit,單描述元 64 MiB,1024 項(FUN_c065f388);UHS-II 一請求一個 CMD25(TLEN),無 ACMD23、無 CMD12。[C]
- WAIT_EBSY:每命令等卡忙完,一次一個命令,無 CMDQ;每命令開銷 1–2 tick。[C]

## 結論 [I]
- HD312 @50 MHz 原始約 300 MB/s,扣開銷約 260;寫入穩態約 105 MB/s 只用到 1/3 → **卡限制,超頻匯流排對寫入幾乎無效**。
- 寫入每次約 56 ms 固定成本(兩點擬合),遠大於驅動 1–2 ms → 來自 FS 或卡提交延遲。
- 超頻風險:鏈路錯誤會升降級等級、降到 Range A 或 UHS-I,寫到一半可能損壞檔案系統。

## 建議順序
1. 換 V90 卡(最多約 2.5×,零風險)。
2. 攢大塊、4 MB 對齊、預先配置(已實測 +48%,未到頂)。
3. N_FCU/N_DATA_GAP(<5%,要 hook)。
4. ACMD23 預抹除、拿掉 EBSY 管線化(改驅動,有一致性風險)。
5. 超頻 RCLK/PLL(寫入 ≈0,不建議)。

## 唯讀確認清單
`sdcard sdmode`;0x28A0003C(HC2)、0x28A0002C、0x28A00040/44、0x28A000E0 → base+P+0/4/8/C;
0xC2F2E7C8、0xC2F2E810–0xC2F2E850;0xC381B300。不要碰 0x20 data port 與 0x8520 config 信箱。
