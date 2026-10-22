# fp 設定重置的所有入口(2026-10-01,靜態分析,未上機)

## 1. shell `menu` 指令族(表 0xC0BBB0FC,分派 FUN_c0402f98,頂層名在 0xC0BAC4AC)
| 指令 | handler | 動作 |
|---|---|---|
| `menu reset` | 0xC03FA8F8 | FUN_c0058100:設定物件 vtable+0x14 重置、寫回 0x5E4 CameraSetting,立即生效 |
| `menu bootReset` | 0xC03FA920 | NonVolatileFlag 第 3 號 = 1(暫存器 0x2D000320),下次開機重置 |
| `menu factoryReset` | 0xC03FA958 | FUN_c04ee628(8) 重置請求並等待(= 選單 FactorySettingResetReq) |

## 2. 開機時的選單設定載入 MenuSettingStorage_w71c1::v1 @ 0xC0088A88
- 若 NonVolatileFlag(3) 為 1 **或** 標頭驗證 FUN_c0088d08 失敗 → 清旗標、vtable+0x14 套預設值。
- 驗證只看 magic `0x4D444C00` + 版本號(vtable+100),**沒有 checksum**。
  → 格式正確但內容會讓相機當機的設定,不會被自動救回。
- NonVolatileFlag 映射表在 0xC31CC2C4;旗標 1/2/4/5/6/7 是電源/待機狀態用。

## 3. PTP 廠商指令(Xacti 協定)—— 唯一不需要相機跑完開機的外部入口
- `set_long` (0xC0030EB0) 查表 0xC072BB94,條目 {id, handler, name}:
  `CAM_INITIALIZE_SETTING_ADDR` = **id 0x6D** → handler 0xC04EAC00:
  呼叫 FUN_c04ee670(=重置請求 8,與 factoryReset 同一條)後再呼叫 FUN_c0042870 物件的 vtable+0x10、+0x14。
- 另有 `CAM_DEFAULT_PARAMS_ADDR` id 0x4C → 0xC04EAC40 → FUN_c04ee680(未追)。
- 註冊:FUN_c00315b8 → PTP(PTP_PortingApi_CmdXacti,data 4 bytes,FUN_c0500858);
  FUN_c0031618 → UsbCtrl 模組(第二條傳輸,未追)。
- **opcode 推定 XCSetLong = 0x9202**(0x9201..0x9205 = XCGetLong/SetLong/GetVar/SetVar/Execute;
  0x9202、0x9204 走 data-out 分支 FUN_c04e49a0)。**未驗證**。
- 安全驗證法:先用 0x9201 GetLong 讀無害位址(get 表 0xC072B7C0,例如 `CAM_READY_ADDR` 0x12)。

## 4. 找過但沒有的
- IPL(PureNAND IPL)不讀 SD,沒有 SD 救援入口。
- 字串與開機流程裡找不到「開機按住某鍵」的組合鍵重置。
- `FP__V***.BIN` 韌體更新只由選單 FirmwareUpdateReq 觸發。

## 5. 「開機時重置」旗標的實體位置與設法(2026-10-01 補)
- NonVolatileFlag 編號→位元 映射(FUN_c00cdc40/c00cde10):
  1→bit8、**3→bit9(0x200)**、4→bit10、2→bit11、5→bit12、6→bit7、7→bit31。
- 存取只有一對函式:讀 FUN_c01227c8、寫 FUN_c01227b0(= `0x2D000320`),寫入由 FUN_c00cdd58 在關中斷下做讀-改-寫。
- 韌體內把 3 號設為 1 的只有 `menu bootReset`;清為 0 的只有設定載入(0xC0088A88)本身。
- 我們能設的方式:`menu bootReset`(USB shell / AutoRun)、直接讀-改-寫 `0x2D000320 |= 0x200`(mem set / worker poke / 自己的 hook,例如 PowerOffMgr 回呼)。
- 未知:拔電池後是否保留(撥開關關機一定保留,否則 bootReset 不能運作)。

## 6. 特殊開機模式搜尋(2026-10-01,兩個代理靜態分析,未上機)
**結論:沒有實體可觸發、又能跳過/重置設定的安全模式。**

IPL(VA = 檔案偏移 − 0x4000 + 0x2E000000):
- 暖開機:0x2D000280 bit0 → 直接跳 FIRM 進入點。
- 冷開機選擇 0x2E0033F0:只有電源原因為 USB/VBUS 喚醒(0x308==0、0x30C&~0x80000==0x100000,推定)時,
  才讀 PSQ 輸入 0x2D000314 bit2 + 0x2D000310 bit7/13,三者皆 0 → 載 **BOOT**;否則 FIRM。三條線對應哪顆鍵未知,像治具腳。
- FIRM 載入失敗 → "Instead, I'll load BOOT for you."(0x2E000154)。FIRM2/DEBUG 從不載入。IPL 不讀 bit9。
- BOOT 分割區(0x2800 單位)推定為工廠備援映像,內容未看 → 可用 prom 唯讀倒出。

MAIN:
- 載入鏈 0xC00207F8 → BootGui 0xC0020DF0 → 0xC0020D58 → 0xC00789D0 → MenuSettingStorage v1(0xC0088A88)+ CameraSetting(0xC0058128,無任何驗證)。之前無分支可跳過。
- 開機按鍵判斷全在設定載入**之後**:PLAY+REC → USB 連線模式強制 3(FUN_c00218E8);PLAY → 播放模式(FUN_c0020D88);id0x16 → XC_PowerTest;id0x24 治具腳 → 工廠模式。都不碰設定。
- 按鍵取樣 FUN_c02DCFD0,表在資料段 0xC2F1CE68/0xC2F1D024(讀 out/seg1_c2ef6e00.bin)。
- 工廠/VendorTestMode 等存在 NAND 調校資料(FUN_c04CDB20),只能經 PTP/shell 寫。
- POWOR_ON_RESET/FwRecovery/recoverySequence 都是 L 卡口鏡頭通訊,與機身救援無關。

## 7. BOOT 分割區實際內容(2026-10-01 上機唯讀傾印)
- `prom readfile 2 5242880 \BOOT_P2.BIN` → `research/firmware/captures/BOOT_P2_5MB.bin`(卡上那份仍在)。
- `@DFI` 容器、載入位址 0xC0000000、有效資料到 0x40E5FF(約 4 MB)、**未壓縮**(MAIN 的 LZSS 解不開,直接看得到字串)。
- 版本字串 `v50_BOOT`,git hash 0bdcc8cb…(與 MAIN 13aa6210… 不同)。
- **有**:SD 卡驅動(exFAT)、USB(PTP、MSC、Type-C)、NAND PromDriver、Xacti 廠商指令全套
  (`set_long`、`CAM_INITIALIZE_SETTING_ADDR`、`CAM_DOWNLOAD_FIRMWARE_ADDR`、`CAM_WRITE_DATA_OPCODE`、工廠調整項目)、
  LED、鏡頭/AF/AE 模組、`XC_UserSetting`。
- **沒有**:MenuSetting、GUI/Lua/.xci、shell、AutoRun、FP__V 更新檔名、CommonSave。
- 推定:工廠用的最小韌體,靠 USB 寫入/下載韌體。**不載入選單設定**,所以是天然的「安全模式」;
  若其中的 `CAM_INITIALIZE_SETTING_ADDR` 有實作,就能在不跑 FIRM 的情況下重置設定。未驗證,需 RE BOOT 本體。

## 8. IPL 何時判定 FIRM「壞了」(0x2E000154)
- 0x2E003930 載入分割區;只有兩種失敗會回非 0:
  1. PTBL 找不到該 id(0x2E0020E8)。
  2. 分割區第一頁不是 `@DFI`(0x49464440)→ "Not found firminfo"(0x2E0037D8)。
- 讀取過程的錯誤(ECC 等)只印 "error occurred during loading, but ignored",**照樣開機**。沒有 checksum 檢查。
- 失敗且 id == FIRM(0x10000012)→ 改載 BOOT。

## 9. 「USB 喚醒 + 三條線全低」是哪三條(2026-10-01,靜態)
- `0x2D000314 bit2` = PSQ port 2 → GPIO 鍵表(seg1 0xC2F1CE68)keyid 0,事件 2/3 = **POWERSWITCH ON/OFF**,讀值 1 = ON。
- `0x2D000310 bit7` / `bit13` 與鍵矩陣(0x2D000188,5×6)遮罩同位:0x80 → 事件 0x14/0x15 = **UP**;0x2000 → 0x35/0x36 = **DISP**
  (矩陣表 seg1 0xC2F1D024,鍵名表 0xC2F205C0)。0x310 與 0x188 同一佈局是**推定**。
- 極性推定為高電位有效(矩陣位元 1 = 按下;0x310 去彈跳路徑在 popcount 小時走,符合閒置全 0)。
- 所以 IPL 條件 = **USB/VBUS 喚醒 + 電源開關 OFF + UP、DISP 都沒按** → 載 BOOT;
  任一不符(例如按住 UP 或 DISP 再插 USB)→ 載 FIRM。
- 推論:BOOT 就是「關機插 USB」時跑的韌體(充電/USB 模式),是日常路徑而不是隱藏救援。
  它不讀選單設定、有 USB PTP/MSC 與 Xacti 指令 → 若關機插 USB 時相機會列舉,就是不經 FIRM 對相機說話的入口。
- 待上機驗證(無害):關機 → 插 USB → 看 host 端列舉出什麼。
