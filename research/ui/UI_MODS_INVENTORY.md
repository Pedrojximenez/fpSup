# 誰改過 fp 的 UI —— 全部清單

2026-09-29 盤點。導航與路線在 [`UI_NAVIGATOR.md`](UI_NAVIGATOR.md);
`python3 research/ui/tools/uinav.py who <id>` 可以查單一產品動到的每個位址。

分成三種東西,混在一起講會亂:

- **A 原生 UI**(選單列、Quick Set 圖磚、底列、收合摘要)—— 改韌體自己的資源與解譯器。
- **B 疊圖**(畫在畫面上面)—— 跟原生 UI 無關,自己畫自己的。
- **C 讀 UI 狀態**(讀使用者選了什麼,不畫任何東西)。

---

## A. 原生 UI

### A1 · fpSup-OG3K / OG2K —— 本專案,已出貨,已上機

`fpSup/releases/fpsup-og3k-v0.2.7a`、`fpsup-og2k-v0.1.4a`
建置:`projects/open-gate/build/build_og3k_ui_candidate.py --release`

解析度選單多出**第三列**,而且是原生外觀:MENU 收合摘要、三選項清單、
Quick Set 大/小值、UHD/FHD/OG3K 底列與游標,全部實機驗證過。

- 原生 UI 2538 words、**360 筆選定的 NBU 記錄**、私有 NBR pack。
- 4 個 Thumb hook,武裝順序寫死在 builder 裡:
  `0xC05E5B58` 字串 → `0xC05E84D8` NBR 載入 → `0xC05E6400` 記錄解譯 → `0xC05D90F0` 佈局。
  最後那個是把 hook 之前就建好的 Quick Set 佈局丟掉,下次載入才會重新解析。
- 目標群組 `WANTED_GROUPS = {20_MV_Resolution, 21_MV_Resolution}`,
  別名 `FP3K_QS/FP3K_SET/FP3K_FONT`(沿用 FP3K 的命名)。
- 每筆記錄都有「持久一位元命中」的 bitmap:**全 0 是時機沒對上,不是畫不出來**。
- 仍未回歸:v0.2 的 full-UI 回放、非當前 screen/style variants。

### A2 · fpSup-Formats v0.3.0a —— 外部交付,新收進來,規模最大

`research/other/external/fpsup-formats-v0.3.0a/`(2026-09-29 從 `~/Downloads/fpsup-formats-v0.3.0a.tar` 收進來)

**一個解析度選單裡六列**:UHD、FHD、S16、OG2K、OG3K、OG3.5K。原生 UI 做到:

- Settings 清單 + 收合列、Quick Set 圖磚、**六個標籤的底列加游標**;
- **每列灰掉它做不到的幀率**(popup 與 Quick Set 都灰),而且保留使用者原本存的幀率
  (OG3K 存 50 → 換到 OG3.5K 讀 29.97 → 換回 OG3K 又讀 50);
- **Crop Mode 在四個新列灰掉並實質關閉**,存的值保留;
- 拔電池冷開機後由卡片自己套用上次選的列(載入後約 20 秒)並刷新畫面。

我在這裡**獨立驗過**的部分(不是照抄它的 MANIFEST):

| 項目 | 結果 |
|---|---|
| `SHA256SUMS` 與檔案 | 相符 |
| payload | `VBIN`,106 個 section,資料到 24,464 byte(檔案 32,768) |
| MANIFEST 列的 UI section | **全部在 section 表裡找得到** |
| `0xC1A709BC` 寫入值 | `40 A0 00 00` = **big-endian float 5.0**(六列需要的 controller 最大值)。順帶證實 NBU 的 float 是 big-endian |
| `0xC0793060` 寫入內容 | 開頭 `4E 42 52 00 01 05` = **"NBR" 1.5**,就是私有資源 pack,6,972 bytes(MANIFEST 寫 6,956,差 16 —— 可能是 pack 內容 vs section 長度的差,未追) |
| `0xC0D4DE04` 寫入內容 | `00 5A 58 F8 00 00 00 9C`,改掉 16-byte big-endian 記錄的中間 8 bytes |
| hook 字 | `0xC05E6400/0xC05E84D8/0xC05E5B58` 各 4 bytes(Thumb `B.W`);**沒有** `0xC05D90F0` |

**它比 A1 多的技術,有兩點值得抄回來:**

1. **資源目錄改指向(路線 R3)。** 不是只靠 loader hook,而是直接改 `0xC0D4DDC0` 起
   那張 16-byte big-endian 記錄表裡的一筆(`0xC0D4DE04`,8 bytes),讓原廠 loader 自己
   去載私有 pack;pack 放在韌體零區 `0xC0793060`,兩者都進 journal,關機寫回原狀。
   ⚠️ 我把記錄欄位讀成 `{length, offset, count, hash}` 是**推論**:改寫後的
   offset `0x5A58F8` / count `0x9C` 用這個讀法對不上,而 length 欄沒動卻只有 3,644。
   **欄位語意還沒追過 —— 這是一件很值得做的離線工作。**
2. **灰掉(greying)是 UI 控制項的權限問題,不是畫圖問題。** 四個新 hook:
   `0xC04A121C` regfrclass(用該列的最高幀率決定幀率清單狀態)、
   `0xC00A87E4` regfrmax(幀率正規化的上限)、
   `0xC04A1788` regcropstate(Crop Mode 灰)、
   `0xC00A93BC` regcropeff(Crop Mode 實質關閉)。
   `research/ui/tools/native_control_probe`(14 個離線案例)研究的就是這件事,兩邊可以對起來。

還有一個 UI 手法:`0xC005C054` regseltail —— 換解析度之後補 apply + change 事件,
並且**在待機外觀會變時把 crop 切換一次**,逼相機在 Quick Set 裡重建 live view。
代價是換不同長寬比時會閃一格 Super35 裁切。已知缺陷,沒修。

它沒帶的:USB shell(release 版不含)、`0xC05D90F0` 佈局 hook。
來源樹(`projects/open-gate/build/registry/`)**不在這台機器上**,所以這張卡目前只能
拿現成的 BIN 用、不能在這裡重建。

### A3 · fpLossless —— 本專案,只有離線設計

`fpSup/lossless/`、`projects/lossless-sup/notes/{NATIVE_ROW_DONOR,FIXED_POPUP}.md`、
`research/ui/MAINB2_ROW_EXTENSION.md`

目標跟 A1/A2 不同:不是既有設定多一個值,而是 **SHOOT 頁 2 多一個全新的設定項**(路線 R5)。
做法是拿原廠的兩選項 donor(MainY4 裡的 `Y4_4_STILL`,`0xC216C8B8`..`0xC2172BC6`,
21 個物件、`MenuItem_Select` 19459、List 19463)改嫁到 MainB2 root 116,
每個欄位逐一釘住(位置 `(0,162)`→`(0,243)`、visibility clip 反轉成 CINE-only、
文字改成字面值並把後面的 flag 設 0、List 的 min/max/value/loop 明確寫出來)。

配套的私有變數註冊 ABI 已經在離線模擬器裡跑通(`0xC05DB308` 註冊 / `0xC05DB418` 查找 /
`0xC05ED248` map),但**名字是借用的不是複製的**,必須活得比 registry 久;
沒有單一變數的移除對應函式。**相機上不存在。**

### A4 · FP3K v0.3.2 —— Vitaly Li,已上機,是 A1/A2 的前例

`research/other/external/FP3K-technical-handoff-2026-09-10/HANDOFF.md` §7

第三個解析度 UI index,**47 個 resolution group、380 處資源變更、2 個 QS 上限**。
16 個 hook 裡 6 個是 UI:`0xC05824D0` QS 選擇、`0xC059C640`/`0xC059C9F0` HUD publisher、
`0xC05E84D8` NBR 載入、`0xC05E6400` 記錄解析、`0xC05E5B58` 字串解析(後三個是 Thumb)。

這份交付給了三個關鍵訂正,現在都還成立:

- CSV 加一列會「看得到但選不到」,`0xC1A709BC` 的 controller max 要從 1 變 2(六列就是 5)。
- 只改 resolution 的 image key 會**弄壞 QS** —— 每個伴隨的 layout/visibility/animation 屬性都要有新狀態。
- 正確的收合摘要記錄是 `0xC1A7246B`(在 B2_5_4 底下),`0xC1A6E777` 是錯的;
  QS 底列記錄 `0xC2278C02`/`0xC24D1DC8` 需要第三格值 700 與加寬的游標範圍;
  長得很像的 `0xC23E1F9C` 屬於靜態照片控制,**不要動**。

沒攔到的:實體 CINE/STILL 切換、preset、媒體真的被拔掉。使用者得先切回原廠解析度。

---

## B. 疊圖 —— 不是原生 UI

### B1 · 本專案的 display 原生指令

`research/display/notes/{DISPLAY_OSD_MAP,OSD_PERSISTENT_MARKER}.md`、`SPLASH_BAND.md`

`display text` + `display osd 1 <ARGB>` 就能顯示(「要 DrawingObserver」的舊結論已推翻,
只有要撐過重繪才需要);`display faceframe` 是顯示控制器的硬體 marker
(LCD 置中 y=288、HDMI y=456);`display osdfile` 把原始點陣貼到左上角,`offset` 就是翻頁。
主層是 **ARGB4444 三重緩衝**,不是 L8A8。開機橫幅的 x/y 是程式碼立即數,會撞 I-cache。

### B2 · lachgil 的 module platform —— 第三方,已上機

`lachgil/module-platform.md`、`c-modules.md`、`sideload.md`

一張卡上放最多八個模組,共用一張版本化的服務表(`lookup`/`call`/`report`/`ticks`),
位置無關,模組之間可以互相呼叫。UI 部分是 **provider `0x100`**:
LCD `(464,560)` 的 96x32 共用畫布,六字請求 `{op,a,b,c,d,e}`
(QUERY / FILL / PRESENT / HIDE / BUTTONS / STATUS)。

- 兩個受檢查的 cave veneer:顯示提交 `0xC02E8A08`、被指派的 FalseColor 自訂功能鍵按下 `0xC03722E8`
  (只觀察並原樣轉發,release 沒掛)。
- 13 個離線情境過;實機上使用者確認了 `C 1 / B 0` 圖磚、用完之後 FalseColor 鍵行為正常。
- 限制:PRESENT/HIDE 只能等下一次符合條件的原生提交(主層、format 1、寬 1024、高 592..2048、
  live-view state 2),不能強制刷新;hook 與配置會留到重開機。

**他明確說這不是 compositor 也不是原生選單 API。** 跟 A 那條路完全不衝突,
而且他的 `sideload.md` 把 FP3K loader 當成「單一固定 blob」的反例來對照 —— 值得注意的是,
A2 那種 journal + 關機寫回的做法已經解掉了他批評的一部分。

### B3 · sigma-fp-lab 的 False Color / EL Zone

`projects/fc-scale/notes/FC_SCALE_CARD_AS_VBIN.md`

第三方純 AutoRun 卡,把 FalseColor 鍵改成自己的用途、在 live view 上畫刻度。
已經被重新打包成可合併的 VBIN payload(cave 沒有 3 KB 可搬,正解是跟分配器要、
cave 只留 188 B 錨點),unicorn 驗過 entry 順序,跟 shell / 陀螺 / 開閘都能合。

---

## C. 讀 UI 狀態,不畫東西

### C1 · wjhrdy PR #2 —— Indoor 自訂 P 模式(已關閉)

<https://github.com/wjhrdy/fpSup/pull/2>,8 個檔案,`custom-modes/`

**沒有任何 UI 繪製或資源修改。** 它做的是:讀出使用者選中的自訂預設名稱
(叫 `Indoor`、簡寫 `IN`),如果是它就把 P 模式的快門家族換成 60 Hz 照明用的
1/120、1/60、1/40、1/30 及更慢;選普通 P 或別的預設就停用。

- 走「實驗性上傳」流程:ZIP 裡的 `fpSup.BIN` 丟到 fpSup-Merge,不進內建目錄、不改共用 loader。
- 驗證是三種模擬器方法 + 變異檢查:12 個原生 program model、固定/自動 ISO、
  快門轉換、六個自訂槽、兩個設定 bank 與 dial 欄位、模式守衛。**全離線,沒有上機紀錄。**

放在這份清單裡的理由:它示範了**兩個設定 bank 加 dial 欄位**怎麼讀 —— 想做
「原生 UI 完全控制」的話,讀狀態這一半它已經做過了。

### C2 · fpSup-RAW-View

`research/liveview/view-lut-format-20260927/`

改的是 Custom View LUT(索引表 `0xC0971118`,88×{ptr,id},曲線 2048×uint16,值域 0–8190),
是 live view 的**色彩**不是 UI chrome。列在這裡只是為了不要跟 UI 工作混淆。

---

## 往「完全控制」還缺什麼

1. **`0xC05E6400` 還沒有離線模擬。** R2 的核心,目前只能燒卡試。它是純解譯器、外部依賴少,
   `research/ui/tools/native_*_probe` 已經證明這種 harness 寫得出來。做掉它,
   六列選單的記錄副本會被怎麼解析就能在桌面上跑出來。**最大的槓桿。**
2. **資源目錄(`0xC0D4DDC0` 起)的欄位語意沒追過。** A2 靠它載 pack,我們只是照抄位址。
   追出來之後,「註冊任意數量的私有資源」才算真的握在手上。
3. **A3 的私有列從來沒上過相機。** 原生 UI 目前能做的只是「既有設定多一個值」;
   「多一個設定」還停在離線配方。
4. **A1 與 A2 的 UI 程式碼各自一份。** A2 的灰掉 / 冷開機套用 / Quick Set 重建是通用能力,
   應該回到共用層,而不是綁在六列那張卡上。
5. **時機仍然是靠 bitmap 事後才知道。** 沒有辦法在載入時就知道某筆記錄會不會被解析到;
   第 1 點做掉的話,這件事至少能在離線先答一半。
