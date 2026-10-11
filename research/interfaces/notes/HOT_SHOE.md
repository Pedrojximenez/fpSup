# 熱靴:觸點、匯流排與協定

SIGMA fp Ver.5.02,`out/MAIN_c0000000.bin` 靜態分析。

> ⚠️ **這份全部是靜態分析,一次都沒有上機驗證。**
> 沒有發過任何 shell 指令,沒有接過閃燈或 EVF。
> 下面標 **(靜)** 的是從程式碼直接讀出來的事實,標 **(推)** 的是我的推論。

---

## 一句話

**熱靴是「SPI 第 6 通道 + 兩條輸入狀態線 + 兩條觸發線」,而且是真雙向 ——
相機會從閃燈收 model id 與 fw version id,並據此切換協定子類與 GN 換算表。**

---

## 1. 熱靴在韌體裡的名字

映像裡**沒有** `shoe` / `hotshoe` / `sync` 這類字串。熱靴被拆成兩個子系統:

```
src/hal/ExtStrbCtrl/src/th/ExtStrbCtrlTh.cpp          外閃控制(主體)
src/hal/Lens/src/StrbTimerDelay.cpp                   X 同步的硬體計時器
src/hal/ExtEvfMgr/src/XC_ExtEvfMgr.cpp                外接 EVF(共用偵測線)
src/library/CameraController/ExtStrbMgr/src/AnyDevice/ExtStrbMgrAnyDevice.cpp
src/library/CameraController/StrbMgr/src/StrbMgr.cpp
```

`StrbTimerDelay` 放在 **Lens** HAL 底下,因為閃燈同步跟快門/鏡頭時序共用同一組計時器。(靜)

---

## 2. ★ 六個訊號 —— `FUN_c05080b0` @ `0xC05080B0`

這是整份筆記最有用的一條。這個函式**一次抓六個 port 物件**塞進同一個 0x18 位元組結構,
這六個就是熱靴的訊號集合:

```c
undefined4 * FUN_c05080b0(undefined4 *p) {
    p[0] = FUN_c00248c8(0x44);
    p[1] = FUN_c00248c8(0x45);
    p[2] = FUN_c00248c8(0x46);
    p[3] = FUN_c00248c8(0x47);
    p[4] = FUN_c00248c8(0x48);
    p[5] = FUN_c00248c8(0x49);
    return p;
}
```

`FUN_c00248c8(id)` @ `0xC00248C8` 是 **port 查表**:走 `XcPortList_w71c1` 取 `{id, 物件}` 配對陣列。
`w71c1` 是板子代號。(靜)

### 角色表

| port | 靜置腳位功能 | 角色 | 證據 |
|------|-------------|------|------|
| 0x44 | 0x0219 | 序列匯流排 (推) | 初始化設成 alt func,之後再也沒被當 GPIO 碰過 |
| **0x45** | (不重設) | **忙碌/就緒,輸入** (靜) | 每送一個位元組後輪詢它直到非 0 |
| 0x46 | 0x010E | 序列匯流排 (推) | 同 0x44 |
| **0x47** | (不重設) | **接上偵測,低電位=接上** (靜) | `FUN_c0505a98` 回傳 `level == 0`;EXT_EVF 也用這根 |
| 0x48 | 0x0116 | 第二觸發脈衝 (靜) | 條件式打脈衝(`*(ctx+0x50) != 1` 時) |
| **0x49** | 0x002B | **X 同步觸發** (靜) | 切成 GPIO 輸出打脈衝,打完切回 0x2B |

預設腳位功能是在 `FUN_c0505370` @ `0xC0505370` 尾端設的:

```c
port[4](0x48) -> mode 0x2C   port[0](0x44) -> mode 0x24
port[2](0x46) -> mode 0x14   port[5](0x49) -> mode 0x6D
// 0x45 與 0x47 不重設 —— 它們就是純 GPIO 輸入
```

`mode` 經 `FUN_c0025100` @ `0xC0025100` 查表 `0xC0729370` 轉成腳位功能碼:

```
mode 0x01 -> 0x0000   GPIO 輸出
mode 0x00 -> 0x0200   GPIO 輸入 (推:0x200 這個 bit 看起來是方向)
mode 0x14 -> 0x010E   mode 0x24 -> 0x0219
mode 0x2C -> 0x0116   mode 0x6D -> 0x002B
```

**0x49 平常掛在周邊功能 0x2B 上,不是 GPIO。** 只有做手動測試閃時才暫時切成 GPIO。
真正曝光時 X 同步由硬體計時器發 —— 見 §4。(靜)

### XC_PortGpio 的 vtable

`XC_PortGpio` vtable @ `0xC07292EC`(物件第 0 個字就存這個值):

```
+0x0C  讀電位          XC_PortGpio::v1  @ 0xC0024D70
+0x10  型別標記        回 1 = GPIO;XC_PortDmy 回 3
+0x1C  寫電位          XC_PortGpio::v5  @ 0xC0024DC0
+0x20  改腳位功能      XC_PortGpio::v6  @ 0xC0024E50
+0x24  掛邊緣中斷      XC_PortGpio::v7  @ 0xC0024E80
```

寫電位是**直接寫 set/clear 暫存器**,沒有 read-modify-write:

```c
v5(obj, 0): *(uint32**)(obj+0x14) = *(uint32*)(obj+0x18);   // 一組
v5(obj, 1): *(uint32**)(obj+0x0C) = *(uint32*)(obj+0x10);   // 另一組
```

那兩組「暫存器位址 + 遮罩」是建構時由 `FUN_c00fe608` / `FUN_c00fe658` 從 pin id 解出來的
(`FUN_c0024c48` @ `0xC0024C48`,XC_PortGpio 的建構子)。(靜)

---

## 3. 資料通道:SoC 序列控制器第 6 通道

```
控制器基底   0x21C00000
通道         8 條,stride 0x100  =>  第 6 通道在 0x21C00600
每通道       9 個暫存器(指標表在 0xC07D2050,stride 0x24)
```

(靜。表是 ROM 裡的常數指標陣列,直接讀得到。)

### 開通道

```
FUN_c012b388()                 @ 0xC012B388   模組時脈: _DAT_30000800 |= 0x10
                                              另外動 0x300021B0 / 0x300021B8
FUN_c012b598(6, 1, 1, 0xFF)    @ 0xC012B598   設定第 6 通道
```

**全韌體只有熱靴用這個序列控制器。**`FUN_c012b598` 在整份反編譯裡只被呼叫這一次;
`FUN_c012b7b0` / `FUN_c012b948` 的**每一個**呼叫點(19 組交易函式,60 多處)通道參數都是 `6`,
而且全部落在 `blk_c05` 的 ExtStrb 區。(靜)

### 傳輸

```c
FUN_c012b7b0(6, &tx, &rx, 1, 0)    // 一次一個位元組,同時收發
FUN_c012b948(6)                     // 等完成 / 檢查錯誤,非 0 = 失敗
```

**同時給 tx 和 rx 緩衝區 => 全雙工。**所以是 SPI 類,不是 UART。(靜)
哪根是 CLK、哪根是 MOSI/MISO 沒有確定(見 §7)。

### 訊框

主體在 `FUN_c05082f0` @ `0xC05082F0` 一族(十幾個同構副本,對應不同指令):

```
一筆交易 = 3 個位元組,逐個送:

  1. 位元組在線上是「反相」的        local_3d = ~value
  2. FUN_c012b7b0(6, &b, &rx[i], 1, 0)
  3. FUN_c012b948(6) != 0  ->  斷言失敗 (ExtStrbCtrlTh.cpp:0x1BB)
  4. 比對 rx[i] 是否等於預期值,不符則整筆交易回 false
  5. log "%02d snd 0x%02x rec 0x%02x"
  6. 延遲 0x32 -> 輪詢 port 0x45 直到非 0(每次隔 0x14) -> 再延遲 0x32

三個位元組跑完:
  FUN_c05078c0(..., &rx, 0) -> FUN_c0504e28(rx[1], ctx)
  收到的第 2 個位元組進狀態結構
```

延遲用 `FUN_c05047c8` @ `0xC05047C8`,小值走 `FUN_c0000a08`(忙等迴圈,
次數 = `n * *(uint32*)0xC3033260 >> 4`)。
**單位沒有證實** —— 校正字在 RAM,靜態讀不到。慣例上是 µs
(`manual_flash` 裡用 `FUN_c0000a08(1000)` 當 1 ms),但我沒有量過。(推)

---

## 4. X 同步是硬體計時器發的

`src/hal/Lens/src/StrbTimerDelay.cpp`,符號 `STRB_WAI0` / `STRB_WAI1`:

```
FUN_c06aeb90  @ 0xC06AEB90   設延遲後啟動,延遲上限 999,999(斷言 0x3C)
FUN_c06aec30  @ 0xC06AEC30   寫計時器比較值
FUN_c06aec68  @ 0xC06AEC68   停止
三條通道,計時器 handle 表在 &DAT_c2e3bbc4(+0/4/8)
```

`STRB_WAI1(0/1/2)` 各自等一個旗標。(靜)

**這解釋了為什麼 0x49 平常不是 GPIO** —— 曝光時要的是硬體時序,不是 CPU 打脈衝。(推)

---

## 5. ★ 相機確實會「收」

五條獨立證據:

**(a) 傳輸原語就是全雙工** —— `FUN_c012b7b0` 每次都給 rx 緩衝區。(靜)

**(b) 收到的位元組會被比對,也會被消費** —— 見 §3 的步驟 4 與收尾。(靜)

**(c) 有一支把回傳值解析成兩個欄位** —— `FUN_c0505908` @ `0xC0505908`:

```c
ctx+0x54 = (rx & 0xFF) * 100;                      // 整數
ctx+0x58 = C + ((rx >> 8) & 0xFF) * k1 * k2;       // double
log "recv %d,%f"
// 不支援的機型走另一支,log "skip fw %d"
```
(靜)

**(d) 廠商自己的字面說明** —— `extstrb param` 的參數表 @ `0xC0BB1F34`(日文原文):

```
force_m_id     カメラが受信する model id を強制固定する (bool)      -> 0xC03E61E8
m_id           model_id の指定 (uint32_t)                          -> 0xC03E6268
force_f_id     カメラが受信する fw version id を強制固定する (bool) -> 0xC03E62E8
f_id           fw version id の指定 (uint32_t)                      -> 0xC03E6368
print_eve_sw   主なイベントログと送受信コマンドを表示する            -> 0xC03E63E8
```

「カメラが**受信する** model id / fw version id」—— 各 32 bit。
而且有 force 旗標可以覆寫,代表收到的值確實是驅動後續行為的那個東西。(靜)

**(e) 收到的東西改變程式分支** —— 通訊層依對方韌體版本分成五個子類:

```
XC_ExtStrbCommunicatorThDefault
XC_ExtStrbCommunicatorThFwVerIsUnder109
XC_ExtStrbCommunicatorThFwVerIs110
XC_ExtStrbCommunicatorThFwVerIs111
XC_ExtStrbCommunicatorThFwVerIsAft112
```

GN 換算器依型號分成:

```
ExtStrbGvConverterDefault / Ef610dg / Ef140dg / Em140dg / Wireless
```
(靜)

另外還有兩條純輸入線:**0x45**(忙碌/就緒)與 **0x47**(接上偵測)。

**速度層面**:一筆三位元組交易 = 3 ×(傳輸 + 完成檢查 + 兩段延遲 + 握手輪詢)。
是**控制通道等級,不是資料管線**。拿來下指令/讀身分可以,搬影像不行。(推)

---

## 6. 從 shell 摸得到的入口

`extstrb`,handler `0xC03E66E0`,子指令表 `0xC0BB2270`(`{名稱, 說明, 處理函式}` 三個字一筆):

```
test           0xC03E5A88   basic test
print          0xC03E5F38   toggle show the log or not
print_with_eve 0xC03E65F0
print_state    0xC03E6180   print ext strb state
start          0xC03E5C30   task start
stop           0xC03E5C60   task stop
flash          0xC03E5C90   flash when task runnning
toggle         0xC03E5FB8   Toggle some setting
manual_flash   0xC03E5E48   test emmiting manual flash
param          0xC03E6530   set get params   (底下再接 set/get,見 §5d)
```

另有 `strb`,handler `0xC040F7F0`(還沒看)。

`manual_flash`(`FUN_c03e5e48`)展開就是 §2 那組 0x49 脈衝:

```c
FUN_c0504160();                           // task start
if (!FUN_c0503f08()) { "strb is not connected"; return; }
FUN_c0504230();
p = FUN_c00248c8(0x49);
p->v6(p, 1);        // 腳位功能 -> GPIO 輸出
FUN_c0000a08(0x32);
p->v5(p, 1);        // 拉起
FUN_c01f89c4(1);
p->v5(p, 0);        // 放掉
FUN_c01f89c4(1);
FUN_c0504180();                           // task stop
```

⚠️ **這些指令都沒有實際送過。**`flash` / `manual_flash` / `test` 都會真的觸發閃燈輸出;
在沒有外接閃燈、也沒有確認 0x49 這根接到哪裡之前不要送。

**唯一不需要硬體的入口是 `extstrb param set force_m_id / m_id / force_f_id / f_id`** ——
可以讓相機以為接了某型號某版本,不用真的插閃燈。(推,未測)

---

## 7. 還沒確定的

- **六個 port id 對應的實體腳位編號。**
  `{id, 物件}` 配對陣列 `&DAT_c2ef83e8` 在 BSS,ROM 映像裡是垃圾(我掃過,那一段是
  遞增的 16-bit 樣式,不是配對),只能執行期讀。
  要收掉:讀 `0xC2EF83E8` 起的配對陣列找到 id 0x44..0x49 的物件位址,
  再讀各物件 `+4` 的 pin id(`FUN_c0024c48` 的 `param_2`,形如 `0x507` = bank 5 pin 7)。
  **需要 `mem read`,必須先取得同意。**
- **0x44 / 0x46 / 0x48 三根裡哪根是 CLK、哪根是資料。**
- **三位元組訊框的欄位語意。**`0xC0CFA210` 那張描述表 Ghidra 推出來的 stride
  (`[i*4]` 與 `[i*0x10]` 混用)跟實際位元組對不上,我不拿它當證據。
- **`strb`(`0xC040F7F0`)** 完全沒看。
- **實體觸點數。**韌體用到六個訊號,加接地至少七個導體;但「韌體用到的訊號數」
  不等於「靴座上的觸點數」(可能有共用/未接)。沒有拆機或量測,不下結論。
- **Wireless 那條路**(`ExtStrbGvConverterWireless`)是同一組觸點還是另一回事,沒查。

---

## 相關

- `notes/projects/usb-shell-sup/../../../projects/usb-shell-sup/notes/SHELL_COMMANDS.md` —— 韌體 shell 的 77 條指令表
- `notes/research/interfaces/EGRESS_MAP.md` —— 其他把資料弄出機身的路
