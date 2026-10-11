# SIGMA fp 5.02 Bluetooth 韌體稽核

日期：2026-08-18

## 結論

在 SIGMA fp 5.02 的解包 MAIN、完整 strings、反編譯輸出、RTTI、vtable 與
source-path 清單中，沒有找到可歸屬於內建 Bluetooth 裝置的驅動或協定棧。因此無法
從此韌體確認任何 Bluetooth 模組型號、功能或速度；現有證據較支持 fp 本體沒有由
MAIN firmware 管理的內建 Bluetooth radio。

## 對「先前分析認為有」的追查與更正

本次進一步追到兩個很容易造成誤判的名稱，但兩者都不是 Bluetooth：

1. 系統 task 名單中的 `BtrMgr`，其建構函式是 `BTRMGR @ 0xC0205D00`。
   呼叫者 `0xC0201D20` 建立的是 `BatteryChargeObserver`，同區 source path 明確為
   `src/library/BatteryMgr/...`，並包含 `BatteryChargeIcBase`、
   `BatteryRemainingMM3556` 等類別。因此 `BtrMgr` 是 battery manager 的縮寫，
   不是 Bluetooth manager。
2. `RemoteControlConnection`／`RemoteControlDevice` 看似無線遙控，但連線 alarm
   名稱為 `MICRCDET`；`RemoDev @ 0xC02E3198` 的裝置事件一路進入
   `FUN_C0683800`，該函式 source path 為 `src/hal/ADC/src/XC_Adc_Adapter...`。
   這是麥克風／快門線插孔的 ADC 電阻按鍵偵測，不是 Bluetooth transport。

`WiFiMgr` 也出現在通用 task-name 表，但目前可達、可辨認的資料結構是
`Grp5 Eye_Fi_Status_*`，即 Eye-Fi SD 卡相容功能；未找到機身 radio driver、
association/security protocol 或 controller transport。

## 未找到的必要構成

- Bluetooth / BLE 裝置或廠牌／型號字串；
- HCI transport、HCI command/event；
- L2CAP、ATT、GATT、SMP；
- RFCOMM/SPP、A2DP、HFP；
- pairing、bonding、passkey、BD_ADDR；
- controller firmware blob、NVRAM 或 radio calibration；
- Bluetooth menu、狀態事件或通訊 task；
- 可對應 Bluetooth controller 的 UART／SPI 初始化與 baud-rate 設定。

## 容易誤判的字串

- `WiFiMgr`、`LV_WiFiStatus`、`Grp5 Eye_Fi_Status_*`：Eye-Fi 無線 SD 卡的狀態與
  UI 資料，不是機身內建 radio。
- `ExtStrbGvConverterWireless`、`L_wireless`／`M_wireless`：外接閃燈／無線閃燈
  狀態圖示，不是 Bluetooth stack。
- `uart` shell command：通用 debug UART baud-rate 控制；沒有呼叫鏈證明它連接
  Bluetooth controller。

## 型號、功能、速度

| 項目 | 韌體稽核結果 |
|---|---|
| Bluetooth 模組型號 | 未找到；不可由 fp 5.02 MAIN 確認 |
| Bluetooth Classic / BLE | 未找到任何協定棧證據 |
| 相機控制／檔案傳輸功能 | 未找到 |
| HCI UART／SPI 速度 | 未找到 Bluetooth transport，無速度可報告 |
| Wi-Fi | 只確認 Eye-Fi SD 卡相關 UI／metadata，不等同內建 Wi-Fi |

因此，先前的「有」若是由 `BtrMgr` 或 `RemoteControl*` 推得，應撤回。韌體目前
只能確認有線 remote-release ADC 功能與 Eye-Fi 相容欄位，不能確認 Bluetooth
設備型號、Bluetooth 功能或連線速度。

## 證據界線

韌體缺少 Bluetooth stack 不能以邏輯上百分之百證明 PCB 絕無一顆完全獨立、由其他
MCU 管理的 radio；但若存在可由主相機使用的 Bluetooth 功能，正常應能看到初始化、
transport、狀態、配對或應用層呼叫鏈。目前均不存在。若要排除獨立硬體，下一步是查
PCB／BOM、FCC/認證資料或量測開機 bus traffic，而不是繼續從 MAIN 猜型號。

## PCB、規格與認證交叉檢查

- SIGMA 官方 fp 規格的通訊／端子項目列出 USB 3.1 Gen 1（Mass Storage、UVC、
  Camera Control）、HDMI 1.4，以及與外接麥克風共用的 3.5 mm Remote；沒有列出
  Bluetooth 或 Wi-Fi。
- Kolari Vision 公開拆機照包含主板裝機狀態與主板背面。照片中未見可辨識的
  Bluetooth/Wi-Fi radio module、2.4 GHz PCB/陶瓷天線、微型同軸天線座或典型
  RF shield/module 區域。這是照片觀察，不能取代原廠 BOM，但與韌體結果一致。
- 機底照片可見一般 FCC 合規標誌，但未見無線發射器產品通常標示的 FCC ID。
- 以 `SIGMA fp`／型號搜尋 Bluetooth SIG qualification 與 FCC 無線設備資料，
  未找到可歸屬 fp 的 Bluetooth qualification 或 transmitter filing。

外部資料：

- SIGMA 官方規格：https://www.sigma-global.com/en/cameras/fp/
- Kolari/PetaPixel 拆機：https://petapixel.com/2020/10/07/a-teardown-of-the-sigma-fp-mirrorless-camera/
