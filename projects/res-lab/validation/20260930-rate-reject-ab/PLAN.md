# r2 CUSTOM 格率一律被拒:A/B 計畫(尚未上機)

症狀:r2 fast-debug 在 CinemaDNG / 12-bit / CUSTOM 下選任何格率(含 23.98)都跳
「因以下的狀態無法選擇: 位元深度 12 bit / 記憶媒體 SD記憶卡」。preflight 卡正常。

## 離線已排除
- 五個原生 hook 的列舉域與呼叫慣例(反組譯):正規化器在 CUSTOM 下恆等、類別 hook 回 0、
  選單/QS 清單 {ptr,count} 正確、合法表 key 為 internal。
- 格率 CSV 與描述子:preflight 與 r2 逐字相同。
- 實機唯讀:FLAG=1、FMTLATCH=0;11 個外部字、5 張 cave 表、5 段 hook 程式與 build 逐字相同。
- class 0x19 每次即時呼叫 C04A1120(無快取),但畫面仍顯示 SD 的 excl4 變體 ——
  變體名在 NBU 字串池 0xC18CA008,選擇與對話框很可能在 NBU 腳本端。

## 兩張卡(皆以 r2 fast-debug 的 AXIS 建,AutoRun/FPSUPUI 與 r2 相同 → 只寫 fpSup.BIN)
| 卡 | 相對 r2 | fpSup.BIN sha256 |
|---|---|---|
| `cards/20260930-240-menu-r2-ab/A-no-native/fast-debug` | 少原生層(11 外部 + 185 cave 字) | 599a5d7a…03de |
| `cards/20260930-240-menu-r2-ab/B-no-ui/fast-debug` | 少 B2_5 NBU 改動(2201 字) | 1e136ee2…51c |

## 判讀
- A 可選 23.98、B 仍拒 → 原生 hook。
- A 仍拒、B 可選 → 借用 Icon 4458 的 B2_5 改動。
- 兩者都可選 → 兩層交互作用;都拒 → 兩者之外(RATE_LV)。
B 卡上第十個收合摘要標籤不存在是預期的。

## 部署 A(2026-09-30,使用者「部署A吧」)
部署前唯讀:卡上 fpSup.BIN = r2 `b877d174…821d`;AutoRun 前 32768 B 與 r2 相同(getfile 多讀 4 B 補齊)。
`deploy.py …/A-no-native/fast-debug`:fpSup.BIN、AutoRun.txt 各一次寫入,讀回逐位元組相同。
尚待:重開機 → 唯讀確認 11 個外部位址為原廠字 → 使用者選 23.98。
還原:`deploy.py cards/20260930-240-menu-r2/fast-debug`。

## A 卡 + RAM CSV(使用者「寫吧」)
更正:23.98 一直可選;被拒的是反灰列 100/119.88(與 240)。A 卡上 100/119.88 仍反灰 → 類別 hook 與反灰無關。
五個 excl 變體第 8/9 列 0,0 -> 1,2,共 13 字,全部讀回確認。重開即還原。
```
B2_5_5_excl row 8 now b'0,0'
B2_5_5_excl row 9 now b'0,0'
  0xc0f8e9f8: b'p,0,' -> b'p,1,'
  0xc0f8e9fc: b'0\r\n9' -> b'2\r\n9'
  0xc0f8ea0c: b'0,0\r' -> b'1,2\r'
B2_5_5_excl2 row 8 now b'0,0'
B2_5_5_excl2 row 9 now b'0,0'
  0xc0f8eafc: b'p,0,' -> b'p,1,'
  0xc0f8eb00: b'0\r\n9' -> b'2\r\n9'
  0xc0f8eb10: b'0,0\r' -> b'1,2\r'
B2_5_5_excl3 row 8 now b'0,0'
B2_5_5_excl3 row 9 now b'0,0'
  0xc0f8ec00: b'p,0,' -> b'p,1,'
  0xc0f8ec04: b'0\r\n9' -> b'2\r\n9'
  0xc0f8ec14: b'0,0\r' -> b'1,2\r'
B2_5_5_excl4 row 8 now b'0,0'
B2_5_5_excl4 row 9 now b'0,0'
  0xc0f8ed04: b'p,0,' -> b'p,1,'
  0xc0f8ed08: b'0\r\n9' -> b'2\r\n9'
  0xc0f8ed18: b'0,0\r' -> b'1,2\r'
B2_5_5_excl5 row 8 now b'1,2'
B2_5_5_excl5 row 9 now b'0,0'
  0xc0f8ee1c: b'0,0\r' -> b'1,2\r'
13 words
```

### 結果(A 卡 + CSV)
使用者:「沒有反灰了，選完後變59.94」。唯讀:AXIS[1] 3 -> 6,FPSLATCH = 0x426FC29F(59.94f),
RECIPE 已依 59.94 重算。→ 介面層由 CSV 變體決定且可用資料打開;值被原廠正規化器依 SD/12-bit 壓到 59.94。
下一點:r2(有 normaliser hook)+ 同樣 13 字,預期保持 119.88。

## 部署 r2 回卡(使用者「部署r2吧」)
卡上原為 A(599a5d7a…)。deploy.py r2 fast-debug:兩檔各一次寫入、讀回相同。待重開。

### r2 重開後
唯讀:hook 11 個在;13 CSV 字為原廠;AXIS[1]=8、FPSLATCH=0x42EFC29F(119.88)—開機即為 119.88。使用者:100/119.88 反灰。
使用者「寫吧」:重寫同 13 字,讀回確認。

### 結果(r2 + CSV)
選 29.97:AXIS[1]=3、FPSLATCH 29.97。選 119.88:第一次讀仍 29.97(配方尚未重算,讀太早),
約 3 秒後連讀兩次:AXIS[1]=8、FPSLATCH 119.88。

## 結論(兩點對照)
| | 介面(CSV 13 字) | 選 119.88 後 |
|---|---|---|
| A(無原生層) | 開 | 59.94(原廠正規化器依 SD/12-bit 截斷) |
| r2(有 normaliser hook) | 開 | 119.88 保持 |
- 反灰與「無法選擇」對話框 = CSV 變體的 Enabled,由 NBU 腳本依媒體挑變體,與 C04A1120 類別 hook 無關。
- 設定層上限 = 原廠正規化器;r2 hook 在 CUSTOM 下放行有效。
- 待辦:把 excl 變體全開寫進 build;更正 imx410_menu.py 第 63 行註解;240 列仍未畫出另案。

## 全開寫進 build(使用者「先全開，在做240」)
`imx410_plan.WITH_RATE_ALL_OPEN = True`:`rate_row_csv()` 產完十列後以 `csv_set_enabled()` 等長改成全 `1,2`。
測試:menu 15/15(新增全開、關掉回原廠反灰兩條)、plan 42/42、load 27/27、原生 4/4、摘要/LV OK。
成品 `cards/20260930-240-menu-r3-allopen/`(H2),四種各 16/16。相對 r2 只變 40 字,全在五個 excl 變體 CSV;
AutoRun/FPSUPUI 相同。fast-debug fpSup.BIN `e246be7c…6903`。尚未上機。
⚠ CSV 全機共用:原廠 UHD/FHD、MOV 下也全亮,但那裡正規化 hook 不放行,超過上限的值會被原廠壓回。

## 240:r4(離線)
popup 第十列與摘要各缺一個範圍值(設計 §8.11b):ListItem `0xC1A7519D` 9.0->10.0、MenuItem_Select `0xC1A73D43` 8.0->9.0。
rate_ui 13/13(新增兩條)、plan 42、menu 15、load 27、native 4、lv OK、full 58、recipe 14、fmt 16、canvas 10。
`cards/20260930-240-menu-r4/` 四種各 16/16;相對 r3 只多 `0xC1A73D64`、`0xC1A751C0` 兩字。
fast-debug fpSup.BIN `c9f30290…dbf2`,AutoRun/FPSUPUI 與卡上相同。未上機。

## 部署 r4(使用者「部署吧」)
部署前唯讀:卡上 r2 b877d174…。deploy.py r4 fast-debug:兩檔各一次、讀回相同。待重開。

## r4 上機結果
100/119.88 不反灰(全開有效)。第 10 列仍看不見;游標在 119.88 按下一次畫面無反應、再按一次才繞回頂端 —— 有選到一個看不見的項目
(使用者更正:r2 時就是如此,ListItem 10.0 沒有可見差異)。**選下第 10 項 → 整機凍結、需拔電池。** 重開後 AXIS[1]=8(119.88),240 未存下。
離線:原廠 `C00ADAA8` 一般路徑把不合法格率改成 internal 1(23.98)。凍結二分卡已建 `cards/20260930-240-freeze-bisect/`,暫緩(使用者:先讓 240 看得到)。

## r5:popup 第十列的游標事件(離線)
List 4439 每列一組 controlValueEvent(值 v)+ controlFocus(實例 "v"),原廠 v=0..8;v=9 沒有 → 游標到了畫面不動。
複製 v=8 那組為 v=9(事件 "10"、焦點 "9"、key 0x14),List 元件數 16->17;空間取自最後一個空 Icon08(4465),
其 drawImage/animationClip 容量轉給 controlValueEvent/controlFocus,多餘位元組為新 focus 記錄的零尾端(原廠收尾跳過)。
後段記錄在集合內移位(集合長度不變)。rate_ui 15/15(原廠解譯器實跑整集合)、其餘九套全過。
`cards/20260930-240-menu-r5/` 四種各 16/16;BIN 內容 34,584 B(上限 61,440)。fast-debug `ad058ca6…480a`。未上機。

## 部署 r5(使用者「建好就部署吧」)
部署前唯讀:卡上 r4 c9f30290…。deploy.py r5 fast-debug 結果見上。待重開;只看不選。

### r5 結果
使用者:「看到240了」—— popup 第 10 列 `240 fps` 顯示出來。**只看,未選**(選下會凍結,待追)。

## 凍結二分(以 r5 為底)—— 已建,未部署
使用者在 r5 選第 10 項:確實凍結(要拔電池)。`imx410_rate_ui.WITH_SUMMARY` 把 popup 與摘要拆開(rate_ui 16/16,含 popup-only 原生解譯)。
`cards/20260930-240-freeze-bisect-r5/`(AXIS 同 r5,AutoRun/FPSUPUI 同 r5):
| 卡 | 相對 r5 拿掉 | fpSup.BIN |
|---|---|---|
| M | LV(437 字)、摘要(B2_5 2131 字 + 摘要配對表 3 立即值 + 20 cave 字)、選單格率→AXIS(123 cave 字) | 7b757bcd… |
| M+sensor | LV、摘要 | b43f0dce… |
| M+sensor+summary | LV | ab69ef67… |
三張都保留:原生 11 位址、CSV 全開、popup 第 10 列游標事件(M 卡位元組以原廠解譯器實跑通過)。

## 部署 M(2026-10-01,使用者「lossless 可以複寫」「重新部署」)
卡上原為 lossless:fpSup.BIN 258,048 B(0xF000 後接 FPLM 選單區塊)、AutoRun 為 lossless 的。FPSUPUI/0..4 與 M 逐位元組相同,未寫。
putfile 不截短 → M(32,768 B)直接寫會讀回不符。第一次我的補零檢查寫死 61,440 而失敗,但部署指令仍執行:
fpSup.BIN 寫了 5 次未通過(deploy 停在 DO NOT REBOOT,AutoRun 未動)。修正:M 補零到 258,048 B(也清掉 lossless 的 FPLM 區塊)後部署,
兩檔各一次、整檔讀回相同。熱更新後第一次開機可能仍跑舊 loader hook,以第二次開機判讀。

### M 卡開機(兩次後)
唯讀:LOAD_DONE_US 0xB0B4C6、原生 11 位址在、B2_5 抽查 81 字與 M 相同、FLAG=0、AXIS[1]=9。
發現:H2 初始 AXIS 格率=240,M 無選單同步 → 一進 CUSTOM 感測器就是 240,變因混淆。另建 M-axis11988(只差 AXIS[1]=8)備用。
使用者選 A:RAM 寫 0xC0732494 9->8,讀回兩次=8(重開後回 9)。

### M 結果(使用者:「當機了」)
AXIS[1]=8、FLAG=1 確認後選第 10 項 → 凍結(拔電池)。→ 問題不在感測器/摘要/LV,在選單第 10 列 + 原生值鏈(internal 8 / export 11)。
使用者另指出:「240 fps 不是真的240」—— 實際 240000/1001。CSV 第 10 列改 `239.76 fps`(plan 42、menu 15 通過);摘要/LV 的 "240" 待共用字串池。

## 離線追凍結
- 原廠 assert `C0011100`:設旗標 C3033469、`C0016D30(1)` 停系統、`C00111FC` 原地迴圈 → 整機凍結,訊息只在堆疊。
- 全機 K=12..15 跳表 36 個:只有 LiveViewConfig `C043CB04` 對 export 0/5 assert;export 11 在多處有原廠專屬分支
  (`C0452704` → C04A8CD8/C04A8EA8、`C0487C9x` → 0x1F、LiveViewConfig → "240")。internal→export 表只有已搬的 rank/legal 兩張。
- 診斷工具 `projects/open-gate/build/diag/assert_catch.{S,py}`:RAM 掛 C0011100,記錄第一個 assert 的 file/line/lr/sp/16 堆疊字到 0xC0732E00,
  該 task 停在 dly_tsk(1000),USB shell 可讀。unicorn 驗證通過。未上機。

### 診斷上機(使用者「寫」)
AXIS[1] 9->8 讀回;assert_catch --go:28 字讀回相符、sync、C0011100=0xEA1C86FE、sync。RECORD 未觸發。

### M 上的診斷結果
選第 10 項 → 卡住;USB 列舉在但 shell 指令全逾時 → 讀不到 RECORD。重開為冷開機(code/RECORD 清空)。
推論:非一般 task 內的原廠 assert(否則 shell 應存活);可能是例外/死鎖/不可睡眠情境。

## 部署 M-no-native(使用者「部署」)
= M-axis11988 去掉原生層(11 外部 + 185 cave),CSV 文字維持 240 fps 以免多一變因;AXIS[1]=8 內建。
部署前唯讀:卡上為 M(補零版)。補零到 258,048 B,deploy 兩檔各一次、讀回相同。待重開兩次。

### M-no-native 結果
使用者:「不會當機了，但會跳回59.94 100 120 也會」→ **凍結在原生值鏈(internal 8)**。跳回 59.94 = 無正規化 hook 的原廠上限(同 A 卡);第 10 列此卡對到 internal 0。

## 部署 M-no-normaliser(使用者「部署」)
= M-axis11988 但 C00A87E4 不武裝(DISARM)。部署前唯讀:卡上為 M-no-native。補零 258,048 B,deploy 結果見上。

### M-no-normaliser 結果
使用者:「沒凍結 變成59.94」→ **凍結只在原廠設定值真的成為 internal 8(240)時發生**:原廠自己的 240 下游路徑。選取當下的查表 hook(rank/合法表/清單/類別/選列)無害。

## 凍結根因(源碼 out/decomp/full,使用者「看源碼」)
格率 getter `C005C0F0` 的原廠消費者中,六個以 internal 值做 switch(cmp #13 + byte 跳表),8..11 落 default:
- **`FUN_c058f380`**:回傳格率的值字串 ID("0316".."0322"),default 回 **NULL**。它登記在設定項目表 `0xC2DEBF10`(41 筆 ×28 B,
  格率為第 0x10 項、標題 "0334"),由 `FUN_c058eb58` 呼叫、交給 **`HELP_FactorValueType0`(GuiExclFunc)** → NULL 字串進 GUI。
- **`FUN_c0554758`**:每格率建一個 std::function;default 存**空**的(呼叫即 bad_function_call)。
- `FUN_c0553ab8`、`MenuItemFactory_w71c1__v294`、`MenuItemSutterSpeedSettingMode__v10`、`C058FB00` 那支:default 用原廠預設值(不會當)。
修法(`imx410_rate_native.RATE_SWITCHES` / `switch_patches`):六個跳表的第 8 格改成第 7 格(119.88),每處 1 個字。
原廠流程把 240 當 119.88 處理;感測器 240 由我們的配方負責。⚠ 快門上限也比照 119.88,240 的實際上限要另驗。
測試:原生 5 個(新增以 unicorn 實跑 FUN_c058f380:原廠 8→NULL、改後 8→"0322"、其餘值不變)、plan 42(外部寫入登記)、其餘全過。
r6 = r5 + 第 10 列 `239.76 fps` + 六處 switch 修正:`cards/20261001-240-r6/`,四種各 16/16;相對 r5 只差 48 字(6 switch + 42 CSV/描述子),AutoRun/FPSUPUI 同。fast-debug `41c4ca9f…`。未上機。

## 決定(2026-10-01,使用者):放棄修改原廠流程,240 不得存進設定區(做法 1)
理由:設定區存 internal 8 時,開機到 loader 之前的原廠流程無法證明安全 ——
- `ShutterAngleMaxLimitListBuilder::v2`(`FUN_c0554948`)直接呼叫 `FUN_c0554758` 建的 std::function,不檢查空;
  `FUN_c055b258` 對空物件呼叫 `C0012EF4`(bad_function_call)→ 凍結。開機時會不會建這張清單:靜態追不完(builder 在 Thumb 端建構)。
- `FUN_c058f380` NULL 只經 `HELP_FactorValueType0`(選單限制說明)。
- 唯一「不合法→23.98」的檢查 `C00ADAA8` 屬 `MenuItemHdmiOutputFramerate`,非動態影像格率。
`RATE_SWITCHES` 程式與測試保留,建置預設關閉。

做法 1 設計(離線,源碼確認):
- 格率選單的列→值唯一入口 `FUN_c057a750` = GUI 變數 `MV_Binning` 的 setter 回呼(列→值 → settings vtable+0x144 設格率);
  值→列在 `XC_GuiMenuNotifierCine_w71c1__v61`(寫回 `MV_Binning`)。轉換表 `(internal,row)`,值→列取第一筆。
- 選列表第 10 筆改 `(7,9)`;前置 hook `FUN_c057a750`:row 9 → 記號 1、表內 (7,9) 排在 (7,8) 前;其他列 → 記號 0、順序還原。原廠永遠只拿到 7。
- 原生清單 hook(選單/QS)回傳的清單要拿掉 internal 8(轉盤/QS 可直接選到 8)。
- 待確認:原廠值 7→7 不發變更通知(`FUN_c0074d78` 只在值改變時通知)→ 119.88↔239.76 互切時配方會不會重算(RAM 實驗)。

## RAM 實驗:原廠值不變、只改 AXIS(使用者「寫吧」)
卡 M-no-normaliser,CINE CUSTOM、原廠 59.94、AXIS[1]=8/FPSLATCH 119.88。寫 AXIS[1] 8->3(29.97)讀回。
靜置 0/3/6 s:FPSLATCH 仍 119.88 → **不會自動重算**。待:開關選單、半按。
開關格率選單(不改選項)後:FPSLATCH 29.97(連讀兩次)→ **關選單會讓配方依 AXIS 重算**,原廠值不變也一樣。
→ 做法 1 不需主動觸發原廠變更通知;記號 + AXIS 即可。半按未測(不需要)。

## r7:做法 1 實作(離線,未上機)
- 選列表第 10 筆 `(7,9)`:第 10 列交給原廠 119.88,internal 8 從任何列/清單都到不了(測試逐列檢查)。
- ROLE 6 前置 hook `FUN_c057a750`(放在 ROLE 3 的空槽 0xC0732B20):列 9 → `RATE240=1`、(7,9) 排前、摘要 export 10 → 狀態 9;其他列 → 全部還原。
  記號 `0xC0731C48` 由 loader 每次開機寫 0。⚠ 一度把 cave 擴到 0xC0732CC0,被 loader 靜態檢查擋下(禁區 0xC0732C84 起),已改回。
- ROLE 3/4(選單/QS 清單加 8)不裝(`NOT_ARMED`);六處 switch 改寫預設關(`WITH_SWITCH_ALIAS=False`)。
- `imx410_fmt`:尾碼 "120" + 記號 → AXIS 240。
- 測試:原生 5(新突變:列 9 給 8、hook 未裝、記號未寫、順序未換)、fmt 17、plan 42、其餘全過;建卡 16×4,含「記號 1 → 240000/1001」與「記號 0 → 119.88」。
- `cards/20261001-240-r7-ramonly/`;**上機用 `cards/20261001-240-r7-ramonly-no14bit/fast-debug`**(`80793888…`):依第一守則拿掉未調查的 14-bit 列。
- 設定區:格率只會存原廠值;解析度 CUSTOM(enum 4)照舊會存(歷次測試與已發行 OG 佐證,仍屬待正式調查)。

## 部署 r7-ramonly-no14bit(使用者「部署」)
部署前唯讀:卡上為 M-no-normaliser。補零 258,048 B 後 deploy,結果見上。待重開兩次。

### r7 上機結果
選 239.76 → 顯示 119.88,重開選單仍 119.88。兩次 90/150 s 唯讀連續輪詢(各約 2.6 萬次):RATE240、表順序、摘要狀態始終不變 → hook 沒被觸發。
原因(源碼):`FUN_c057a750` 是 **MV_Binning** 的回呼(轉換器槽 +0x64);格率是 **MV_FrameRate** → `FUN_c057a6f8`(C06BDAB0,槽 +0x60,
再 settings vtable+0x140)。值→列 `C06CCD70` 同樣取第一筆。誤掛處只在改分格讀出時觸發,這次無副作用。

## r8:hook 改掛 `FUN_c057a6f8`
與 r7 只差 3 字:掛點 C057A750→C057A6F8、跳回 C057A754→C057A6FC。新增測試以反編譯源碼確認掛點只註冊給 `MV_FrameRate`
(改回 C057A750 會失敗,得到 MV_Binning)。`cards/20261001-240-r8-ramonly/` 16×4;上機 `…-r8-ramonly-no14bit/fast-debug`(`acb48514…`)。未上機。

## 部署 r8-ramonly-no14bit(使用者「部署」)
部署前唯讀:卡上為 r7-no14bit。補零 258,048 B 後 deploy,結果見上。待重開兩次。

### r8 上機結果
重開一次即判讀(使用者:重開兩次的規定改掉 —— AutoRun 不變時一次就夠;fp-merged-card 已改)。
掛點 C057A6F8 已裝、C057A750 已還原;選 239.76 → 仍 119.88,180 s 輪詢記號始終 0 → 選單走的不是這個回呼。
源碼:`MV_FrameRate` 有**兩個**寫入回呼 —— `FUN_c057a6f8`(`_DAT_c37b7538`)與 `FUN_c05821b8`(`_DAT_c37b75c8`,另一組畫面)。

## r9:兩個 MV_FrameRate 回呼都掛
ROLE 7 掛 `FUN_c05821b8`(放 ROLE 4 空槽 0xC0732BA0,跳回 C05821BC),程式與 ROLE 6 共用。
新測試:源碼裡所有 `s_MV_FrameRate…,FUN_x` 的回呼集合必須等於兩個掛點;兩條路徑都模擬;突變「第二個未裝」被抓到。
相對 r8 只多 29 字(ROLE 7 槽 + 掛點 C05821B8)。上機 `cards/20261001-240-r9-ramonly-no14bit/fast-debug`(`8c9ed86a…`)。未上機。

## 部署 r9-ramonly-no14bit(使用者「部署」)
部署前唯讀:卡上為 r8-no14bit。補零 258,048 B 後 deploy,結果見上。重開一次。

### r9 上機結果
兩個 MV_FrameRate 回呼都裝上;選 239.76 → 仍 119.88,180 s 輪詢記號始終 0 → 設定選單 popup 的提交不經這兩個回呼,但確實用我們的表把列 9 轉成 7。
下一步:RAM 紀錄器掛表取得函式 C06BDB00,記錄呼叫者 lr,找出真正提交路徑。

### RAM 紀錄器(使用者「寫吧」)
diag/getter_log:27 字於 0xC0732D00、sync、C06BDB00=0xEA01D47E、sync;紀錄環 0xC0732E00。
紀錄器更新(使用者「寫吧」):每筆加記 RATE240 與第一個值 7 的列;重新載入。
相機曾重開(LOAD_DONE_US 0xB92748->0xB1340F,原因待使用者確認);依使用者「再做一次」重新安裝紀錄器。

### 紀錄器(含記號快照)結果
#9 回呼列 9:RATE240=1、表已換序(hook 有效);#10 通知值 7→列(此時記號 1);#11 巢狀回呼**列 8**(未經表取得函式)、#12 列 8 → 記號被清。相機未重開(0xB0D688 全程不變)。

### RAM 驗證 IconChange 上限(使用者 ok)
0xC1A744F4 寫入:IconChange(4438) prop 0x12 8.0→9.0(只變 0xC1A744F6)。
**結果:成功。** 退出重進後選 59.94 → 239.76:紀錄只有 #11 回呼列 9(RATE240=1)與 #12 通知值 7→列 9,**不再有列 8 寫回**;
記號保持 1、表已換序、摘要狀態 9;使用者確認游標停 239.76、摘要正確。關選單後 AXIS[1]=9、RECIPE 格率 9、PICKOK=1、FPSLATCH 239.76。
原廠設定為 internal 7(119.88),設定區不會存 240。
**根因:** `XC_GuiMenuNotifierCine::v60` 把值 7 轉成列 9 寫入 GUI 變數,而 IconChange(4438)prop 0x12 上限仍是原廠 8.0,
把 9 夾成 8 寫回 → 回呼以列 8 清掉記號。格率選單的三個上限:List `C1A74B44`、MenuItem_Select `C1A73D63`、**IconChange `C1A744F5`** —— 必須三個都是 9.0。
待辦:IconChange 上限寫進 build(r10);反向測試(239.76 → 119.88)。
反向:選 119.88 → 記號 0、表還原、摘要 8;關選單後 AXIS[1]=8、FPSLATCH 119.88。兩向皆通。紀錄器已 --off。

## r10:IconChange 上限進 build(離線)
`imx410_rate_ui.CONTROLLERS` 加 IconChange(4438)prop 0x12 8.0→9.0;測試:rate_ui 檢查 9.0、plan 新增「三個上限都 9.0」(讀最終寫入計畫;
拿掉 IconChange 會失敗)。r10 相對 r9 只差 `0xC1A744F4` 一字 = RAM 驗證過的那個。上機 `cards/20261001-240-r10-ramonly-no14bit/fast-debug`(`918c9b51…`)。

## 部署 r10-ramonly-no14bit(使用者「部署吧」)
部署前唯讀:卡上為 r9-no14bit。補零 258,048 B 後 deploy,結果見上。重開一次。
fpSup.BIN 第 4 次才讀回一致;另以 getfile 整檔比對:相同。

### r10 上機結果(最終確認)
開機:三上限 9.0、兩掛點在、紀錄器不在、記號 0。選 239.76 關選單 → RATE240=1、表換序、摘要 9、AXIS/RECIPE 9、FPSLATCH 239.76(連讀兩次)。
選回 119.88 關選單 → RATE240=0、表還原、摘要 8、AXIS/RECIPE 8、FPSLATCH 119.88。**r10 實機通過:239.76 兩向切換正確,原廠設定只存 119.88。**

## 14-bit(使用者 2026-10-01)
實測:14-bit 會造成原韌體位元深度選單壞掉,但不至於當機。依第一守則不得存入設定區;建議比照 240 做法 1。細節待補。

## 240 錄影(使用者 2026-10-01)
r10:「240已經完成錄影，結果很好」。實機錄影通過(使用者觀察;檔案 metadata 未由我核對)。
14-bit 細節(使用者):選了立刻壞;位元深度選單空白;只能靠 USB shell 或裝 Sensor Lab 卡手動改回 12。→ 一般使用者無法自救,必須做成記憶體記號。

14-bit 決定(使用者):「可以接受風險」→ 第一守則例外:執行時原廠 14-bit,關機時改回 12;不需開機自動改回(用 Sensor Lab 開機選單本來就有 14-bit 列,不會空白)。

## 14-bit 關機改回:暫停(2026-10-02 使用者「先別管了」)
imx410_poff.S 已寫(入口註冊 PowerOffMgr 清單 A + 呼叫 RESTORE;回呼 14→12 經 C005BEF0),位置 0xC0730260(避開 og3k 禁區)。
⚠ OG_BOOT_RESTORE_STABILITY_REVIEW §3.2:SaveOnPowerOffObserver 較早註冊,先 v9(快照覆回 active)再 v2(序列化 0x4F00 record);
我們的回呼在其後 → 很可能錯過序列化而無效。WITH_BIT_POFF=False;建卡測試的註冊斷言尚未更新。

## 第 0 步:B2_5 子頁執行期轉向(使用者「寫吧」)
B2_5 執行期項目 0xC6A26E00(位移 0x19C130),B2_6 0xC6A26CCC(0x1B8E9B)。寫 0xC6A26E08 = 0x1B8E9B(暫指音訊頁)。
結果:退出重進錄影設定 → 顯示音訊頁內容(使用者確認)。**B2_5 子頁可在執行期以 entry+08 轉向。** 已寫回 0x19C130。
