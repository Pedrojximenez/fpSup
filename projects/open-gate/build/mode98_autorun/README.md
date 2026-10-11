# 3032×2012 open gate @29.97 — mode 117 / mode 98 A/B、live view、選單標籤

對既有的 `test_autorun/` 加了三件事：

1. **mode 98 也改成 29.97**，picker 開機仍指向 mode 117，切換只要三個字。
2. **live view 修正**（`dispfit`，掛在 `0xC0437ECC`）——錄製時的花屏。
3. **CINE 解析度選單標籤**就地改名，`FHD 1920x1080` → `3:2 3032x2012`。

全部只寫 RAM。移除 `AutoRun.txt` 並完整斷電重開就回原廠。

---

## 1. mode 98 A/B — 判斷 `ACQ_12BIT_MIX` 是不是電荷合併

如果是，open gate 的暗部可以補回約 2 級光；如果只是跳行加上比較慢的 ADC，就不是。

### 時序的根據

`0xC0B59500` 時序表，`frame_cycles = hmax × (vmax − 1) + tail`，`fps = 72e6 / frame_cycles`。

```
                     hmax  tail  vmax    cycles      fps      捲簾     幾何
mode  98  出貨        445   445  2094    931,830   77.267   12.435 ms  3032×2012
mode 106  出貨        445   735  5398  2,402,400   29.970   10.556 ms  3032×1708
mode  98  改後        445   735  5398  2,402,400   29.970   12.435 ms  3032×2012
```

mode 98 與 mode 106 出貨時 **hmax 同為 445、line length 同為 3036**，只差 tail/vmax
與行窗。把 106 的 `tail 735 / vmax 5398` 搬進 98，兩半都是原廠既有的組合——跟
mode 117 當初借用 mode 111 的 `330 / 7280` 是同一個手法。結果是 **29.97003 fps，
0 ppm**；hmax 不動，捲簾維持 **12.435 ms**（mode 117 是 9.222 ms，慢 35%，
佔一格 33.4 ms 的 37%）。

### A/B 流程

兩段一定要**同場景、同光、同構圖、同曝光**。上腳架，不要動相機，不要動曝光。

1. 冷開機（USB 拔除），等 `fpOGtest!`，進 CINE 選 CinemaDNG / **3:2 3032x2012** / 29.97p。
2. **第一段**：錄 5 秒。這是 mode 117 基準。
3. 接 USB，切到 mode 98：

   ```
   mem set 0xC0BE5888 0x00000062
   mem set 0xC0BE5A28 0x00000062
   mem set 0xC0BE5BC8 0x00000062
   ```

4. 在 CINE 選單把解析度切到別的再切回來，讓 picker 重新被讀。
   用 `mem get 0xC343B590` 確認讀到 **98**（`0x62`）。
   若仍是 117，改成完整關機、用讀卡機把這三個字寫進 AutoRun 再冷開機。
5. **第二段**：再錄 5 秒，一樣不要動相機。
6. 完全關機，用讀卡機取出兩段。

### 怎麼判讀

```
python3 codex/opengate/measure_photodiodes.py <mode117 資料夾> <mode98 資料夾>
```

看最後一欄「感光點/像素」（第一個資料夾當 1.00 基準）：

```
真的是電荷合併      mode 98 ≈ 4.0      暗部好 2 級以上，疊紋明顯減少
只是跳行 + 慢 ADC   mode 98 ≈ 1.0~1.3   跟現在一樣
```

差 3～4 倍，不會模稜兩可。另外兩件要一併看：

- **高光**。電荷合併把四份電荷疊在同一個浮動擴散節點上，容量沒跟著變四倍，
  可能提早飽和。拍有明顯高光的，看有沒有比 mode 117 早切掉。
- **疊紋**。找細密紋理（布料、磚牆、遠樹），看鏡頭移動時有沒有爬行閃爍。

---

## 2. live view — `dispfit`，掛在 `0xC0437ECC`

**還沒上過機。** 這是本份 AutoRun 唯一沒有實機驗證的部分。

`FUN_c0437e98(obj, idx)` 只是 `return *(obj + idx*8)`。兩個 LiveViewState 物件的
entry 0 是顯示路徑用來決定自己尺寸的幾何描述子，而它仍然描述一個 16:9 的來源——
這就是為什麼錄下來是對的、預覽是花的：我們搬了錄製幾何，從來沒有通知顯示層。

```
C0437EC4  add r2, r5, r4, lsl #3
C0437EC8  ldr r2, [r2]          r2 = 描述子
C0437ECC  mov r0, r2            <- 掛這裡，位移指令在返回時補回
C0437ED0  pop {r4, r5, pc}
```

掛在這裡而不是函式開頭，形狀跟已經驗證過的 `C043A19C` 完全一樣：一條位移的
`mov`，`r5` = 物件、`r4` = 索引都還活著。

和社群那份 FP3K 的做法有兩點不同：

- 描述子是**執行期從韌體自己那份複製**過來、只改幾何，我們看不懂的欄位保留韌體
  放進去的值，而不是在編譯期就凍死；
- 寬度是**由高度推導**（`w := h × 3/2`），不是寫死 1620，面板幾何跟假設不同時也還是對的。

守衛：`idx` 必須是 0、物件必須是 `0xC375EB68` / `0xC375ED3C` 其中之一、寬高都要
在 1..8192。任何一項不符就原樣放行。所以最壞情況是「沒作用」，不是壞掉。

回傳的描述子放在 `0xC072FA20`（避開 `C043A19C` 的 telemetry `0xC072FA00`）。
接上 USB 後可以讀它確認 hook 有沒有命中：

```
python3 codex/opengate/dispfitctl.py read     # 只用 mem get，安全
python3 codex/opengate/dispfitctl.py off      # 只用 mem set，安全
python3 codex/opengate/dispfitctl.py arm      # 用 put()，hook 生效期間不可用
```

`arm` 不要在這份 AutoRun 開機後使用——AutoRun 已經裝好了，而 `arm` 會動到
host 工具的暫存區。

---

## 3. 選單標籤 — 就地改名，沒有搬 CSV

CINE 錄影格式清單是一份 89 bytes 的 CSV，在 `0xC0F8E7EC`：

```
<BOM>NO,TEXT,Popup,IMAGE,Enabled,Enabled2
1,0313,Popup,blank,1,2
2,0314,Popup,blank,1,2
```

`0313` / `0314` 是字串 id。在字串表裡：

```
id 0313  len 13  "UHD 3840x2160"    ← 沒動
id 0314  len 13  "FHD 1920x1080"    ← 我們佔用的那一格
```

`"3:2 3032x2012"` 剛好也是 **13 個字元**，所以可以原地覆蓋，記錄長度欄位不用動、
不用搬 CSV、不用新資源、不用字型。17 種語言各 4 個 32-bit 字，共 68 個字，
全部由建置時掃描映像產生並逐一核對 stock 值。

另外有 17 筆 id **1279** 也是 `"FHD 1920x1080"`，但它鄰近的是 LCD 亮度那一區，
應該是 HDMI 輸出格式——那個確實還是 1920×1080，**刻意不動**。

想換字串的話改 `build_mode98_autorun.py` 的 `LABEL_NEW`，長度必須是 13。

### ⚠ 這個標籤只有在 29.97 才是誠實的

`0314` 是**解析度**的標籤，FHD 那一格在所有幀率下共用它。但 picker 只有
**idx7（29.97 那一格）**被改成 mode 117/98。所以：

- FHD **29.97** → 真的是 3032×2012，標籤正確。
- FHD 其他幀率（23.976 / 24 / 25 / 59.94…）→ 標籤會說謊。
  而且 `rowpatch_v4` 的守衛是「row 等於 1936×1090」，那在所有 FHD 幀率下都成立，
  所以畫布還是會被改成 3032×2012，但感光元件不在對應模式——**預期會產生不完整
  的畫格**。未測，不要用。

換句話說：這份 build 只有 **CinemaDNG / 3:2 3032x2012 / 29.97p** 一個組合是有效的。

### 沒有做的事：真的多加一列選單

社群那份 FP3K 是**新增**一列 `3,3K 3000x2000,,1,2`。那需要把 89 bytes 的 CSV 搬到
cave 再重新指標——原地只剩 3 bytes 空檔，塞不下第 21 個 byte。而且新增的那一列還要
對應到一個 enum 值、那個 enum 再要能選到感光元件模式與幾何，而我們已經確認
`MenuItemMovieRecSize` 的轉換表（`0xC0742204`，`{2→1920x1080, 3→3840x2160}`）
**不控制 DNG 畫布**——畫布是 `C043A19C` 的 hook 無條件決定的。

所以多一列選單在目前的架構下是純裝飾：你還是坐在 FHD 29.97 那一格，只是名字不同。
改名拿到了同樣的資訊，代價是 68 個資料字而不是搬表 + 新資源 + 字型。
真要做「多一列且那一列自己決定幾何」，那是把 hook 從「無條件覆寫」改成
「依 enum 分派」，屬於另一階段的工作。

---

## patch 總表

```
0xC0B59A28  0x00040888 -> 0x00041C70   mode 117 vmax 2184 -> 7280
0xC0B59544  0x01BD01BD -> 0x02DF01BD   mode  98 tail  445 -> 735
0xC0B59548  0x0004082E -> 0x00041516   mode  98 vmax 2094 -> 5398
0xC0BE5888  0x0000006A -> 0x00000075   picker 1 idx7 -> 117（開機值，0x62 = 98）
0xC0BE5A28  0x0000006A -> 0x00000075   picker 2 idx7
0xC0BE5BC8  0x0000006A -> 0x00000075   picker 3 idx7
0xC0BD9A34  0x00000640 -> 0x00000400   profile122 live   RWZM H
0xC0BE1684  0x00000640 -> 0x00000400   profile122 record RWZM H
0xC0BD9EFC  0x00000640 -> 0x00000400   profile122 live   RWZM V
0xC0BE1B4C  0x00000640 -> 0x00000400   profile122 record RWZM V
0xC0D7xxxx  68 words                   選單標籤 id 0314 × 17 語言
0xC072F800  232 bytes                  幾何 payload (rowpatch_v4)
0xC072F900  184 bytes                  live view payload (dispfit)
0xC072FA00  4 words = 0                幾何 telemetry
0xC072FA20  11 words = 0               dispfit 描述子緩衝
0xC043A19C  0xE1A00004 -> 0xEB0BD597   幾何 hook，倒數第二 arm
0xC0437ECC  0xE1A00002 -> 0xEB0BDE8B   live view hook，最後 arm
```

所有 stock 值都在建置時對本機 Ver.5.02 映像核對過。cave
`0xC072F800..0xC072FA4C` 在映像裡確認為空。

## 已知限制

- 僅 Ver.5.02，沒有執行期版本 guard。
- 只寫 RAM；移除 `AutoRun.txt` 並完整斷電重開即回原廠。
- hook 生效期間 USB 只能用 direct `mem get` / `mem set`，
  不可用 `getfile.py` / `putfile.py` / `inject.py` / `callfn.py`。
- 只有 CinemaDNG / 3:2 3032x2012 / 29.97p 這一個組合有效（見上面的 ⚠）。
- `dispfit` 未經實機驗證。
- `ACQ_*` 屬靜態擷取類，picker 三張表出貨時全填 `MONIT_` 類。mode 98 是跨類別的
  嘗試，沒有前例；不成立的預期表現是錄不起來或幾何不對，不是損壞。
