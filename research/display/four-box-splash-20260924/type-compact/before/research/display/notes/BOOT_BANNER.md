# 開機橫幅:fpSup + 進度條(2026-09-21 收工,未定案)

目標:把開機那行 `fpSup[####....]040` 換成「畫面中央一條黑線,上面 `fpSup` 和進度條,
跑完變成白色版本字串」。**版面全部做出來過,但沒有一版通過開機驗證。**

標記:**[M]** 實機量到、**[C]** 反編譯、**[?]** 還沒定論。

---

## 0. 目前最好的版本(主機端畫得出來,未上卡驗證)

```
# 一次性
mem set 0xC0528700 0xE12FFF1E      # bx lr — 關掉重繪循環(見 §3)
mem set 0x30190624 0x00180018      # marker 邊框 24 → 48px 實心
mem set 0x301906A4 0x00180018
display faceframe -8 264 2000 48   # 黑線,螢幕 317–364
mem set 0x30190400 0x00000004      # 只留外框 slot
mem set 0x30190410 0x00000004
display monitor 0 1
mem set 0xC03E4698 0xE3A08F52      # 文字 y = 328
mem set 0xC03E46A0 0xE3A05F6E      # 文字 x = 440  ← 之後絕不再改(見 §2)
mem set 0xC03E469C 0xE3A0CB01      # ★ 繪圖矩形寬 0x180 → 0x400(見 §4)
mem set 0xC0BB120C 0x00000000      # 字底透明
display osd 1 0x00000000  ×3

# 每一個畫面(由長到短的前綴覆蓋,疊出多種顏色)
mem set 0xC0BB1208 0x00000007 / display text fpSup####     # 灰 = track
mem set 0xC0BB1208 0x00000001 / display text fpSup##       # 白 = 已完成 k 格
mem set 0xC0BB1208 0x000000B2 / display text fpSup         # 桃紅
mem set 0xC0BB1208 0x000000A6 / display text fp            # 黃
display osd 1

# 完成:把 `fpSup##` 那行換成 `display text fpSupGYRO!`(白)

# 最後
mem set 0xC0528700 0xE92D4BF0      # 還原重繪,否則螢幕是死的
```

**前綴覆蓋是這一版的關鍵**:短字串畫在同一個 x 就是覆蓋前面幾格,所以
`fp`/`Sup`/進度/版本四種顏色**不需要改 x、不需要墊位字元、不需要改字形**。

---

## 1. 硬體 marker 的部分 [M]

- `display faceframe` 在 **AutoRun 開機期就能用**(實機驗過,把探針插進卡上 AutoRun,
  開機時畫面中央確實出現黑線)。
- marker **不在 OSD 圖層**,所以不受三重緩衝影響,寫一次就固定。
- **顏色可以改**:`0x30190420 + (slot>>3)*4` 的 4-bit 欄位,實機掃出只有三個有效值 ——
  **1 = 橘 `#FD9944`、2 = 黑、4 = 紅**,其餘值線會消失。寫顏色暫存器是安全的
  (不像寫矩形暫存器會讓 marker 消失)。
- **只有一個矩形可用。** `display faceframe` 畫的是外框(slot 2)+ 內框(slot 1),
  幾何鎖在一起。要第二個獨立矩形**五種方法全部失敗**,見 §5。
- marker 在 **OSD 下層** —— OSD 畫了什麼就會蓋住它。

---

## 2. ⚠ 文字的 x/y 是程式碼立即數,改了會撞 I-cache [M]

`0xC03E46A0`(x)和 `0xC03E4698`(y)在**同一條快取線**上。剛跑完 `display text`
再改它,CPU 會執行快取裡的舊指令 —— **回讀是新值、畫出來卻是舊位置**。

這個在一次會話裡咬了四次,症狀每次都像別的東西:
- 「fp 不見了」→ 其實是 `Sup` 用 fp 的 x 把它蓋掉
- 「完成狀態變成 `SupupGYRO!`」→ 同一件事
- 卡上「整個橫幅跑到畫面最上面」→ y 沒生效,停在韌體原值 `MOV r8,#0`

**原廠 AutoRun 之所以沒事,是因為它 x/y 只在最開頭設一次、之後再也不碰。**
新版也必須這樣 —— 這就是前綴覆蓋法存在的理由。

顏色(`0xC0BB1208`/`120C`)是**資料**,隨便改沒問題。

---

## 3. 關掉重繪循環 [M]

```
mem set 0xC0528700 0xE12FFF1E    # bx lr
mem set 0xC0528700 0xE92D4BF0    # 還原
```

`FUN_c0528700` 是重繪循環、只有一個呼叫者(DrawThread)。實機:關掉後
緩衝輪替計數器 `0xC3825064` **凍住不動**,還原後立刻恢復;相機沒凍、shell 照常。

為什麼要關:相機開機後 GUI **持續在 present**(10 秒內輪替七八次),那就是
「一個畫面要送三次」的根源。關掉它理論上 ×1 就夠。

⚠ **關著的時候整個畫面都不更新**,包括相機自己的東西。最後一定要還原。
⚠ 在相機**剛退出選單**時關掉,主層會凍在半畫好的狀態(白色殘影)。
  **開機期主層也不是空的**(見 §10),所以關掉重繪之後一定要自己清主層。

---

## 4. ⚠ 繪圖矩形寬度會讓長字串**整串不畫** [M]

`0xC03E469C` 是 `MOV r12,#0x180`(384)。字串超過就**整串不畫**,不是截斷,
而且 shell 照樣回 `ok` 和 `output <字串>` —— 完全沒有錯誤訊號。

實測:x=440 時 `fpSup####`(9 格)畫得出來、`fpSupGYRO!`(10 格)完全不畫。
改成 `0xE3A0CB01`(0x400)才夠長。**版本字串的長度上限由這個決定。**

---

## 5. 第二個硬體矩形 —— 五種方法全部失敗 [M]

| 做法 | 結果 |
|---|---|
| poke 沒配置過的 slot(25)的矩形/顏色/樣式/致能 | 完全沒畫出東西 |
| 同上 + `FUN_c00e6d90` 的 **bit 28 latch**(`0x10000000`) | 一樣沒有 |
| `display focusarea 1` 借它配 slot | **跟 faceframe 共用同一個管理器 `0xC3435A54` 和同兩個 slot**;而且 `focusarea 0` 會把我們的線一起清掉 |
| `menu SetDisplayGridLines 1/3` 讓韌體配 slot | **有效** —— 致能 `0x04`→`0x2C`/`0x7C`,slot 3/4/5/6 是韌體正式開的 |
| poke 那些**已配置**的 slot 的矩形(± latch) | 線消失;使用者肉眼看到「格線越來越透明」 |

**結論:暫存器是活的,但 poke 湊不出韌體建 paste 物件(`FUN_c02edf08`→`FUN_c02f1bd8`)
時做的完整設定。** 要第二個矩形得把那條配置路徑完整逆出來。

`SetFrameGuide*` 那一組(`CustomArea`/`CustomOffset`/`CustomScaling`)全部回 `NG`,
因為 `SetFrameGuideSupport` 是 NG。但選單裡「畫面比例指引」是開的、「中心標記」有「點」
的選項 —— **這兩個原生疊圖還沒查過,是下一個該看的地方。**

---

## 6. ×3:GUI 在跑的時候一定要 [M](2026-09-21 使用者更正)

- 你們 `build_autorun.py` 的註解:「two sends read as the bar vanishing and coming back」
- 相機開機後 GUI 持續 present(§3),所以那個狀態下 ×1 **一定**不安全
- 關掉重繪後,一次實測 ×1 放 10 秒穩定不動 [M]
- **但同一天稍後,關著重繪 ×1 畫不上畫面、×3 才出來** [M]

**兩個觀測互相矛盾,我沒有解釋。** 不要相信任何一邊,上卡開機量。

---

## 7. 方法論:這一輪我量錯了幾次

1. **細筆畫不能拿來量顏色** —— JPEG chroma 是半解析度,2 px 筆畫跟黑底平均掉,
   索引 178 量成 `#895087` 而不是 `#FF6668`。填滿整層才對。
2. **機身截圖抓的是特定 buffer,不能拿來判斷螢幕在閃** ——
   出現過「1 次有 / 2 次沒有 / 3 次有」這種無意義的圖樣。
3. **HDMI 只帶硬體 marker,不帶 OSD 副層的字** —— 我用 HDMI 做的閃爍測試整個無效。
4. **「橘色直線」是畫面下方的 `F2.0` 文字**,不是 marker 的邊。
5. 三次關鍵進展都是**使用者肉眼看出來的**(「字還在」「格線越來越透明」「第一次顯示很久」),
   我的儀器都沒看到。**畫面的真相在螢幕上。**

---

## 8. 成本

| | 原本(合併卡) | 新版(未驗證) |
|---|---|---|
| display | 64 | ~20–43(看 ×1 還是 ×3) |
| mem set | 101 | 14(前綴覆蓋版)/ 200(字形補丁版) |

⚠ **`mem set` 在 AutoRun 不便宜。** 使用者實測:字形補丁版「第一次顯示橫條花了很久」,
原因是第一個畫面之前塞了約 90 條 `mem set`。**第一個畫面之前的指令數才是體感。**
固定位址的固定資料(字形點陣之類)該進 `fpSup.BIN` 的 VBIN section,不是 `mem set`。

---

## 9. 改卡的流程(比重建卡快很多)[M]

```
getfile.py '\AutoRun.txt' local.txt --size N     # 取下
…本機編輯…
putfile.py new.txt '\AutoRun.txt'                # 寫回
getfile.py '\AutoRun.txt' verify.txt --size N    # 回讀比 sha
```

⚠ **`putfile` 是 mode 7:覆寫但不截短。** 寫一個比較短的檔回去,尾巴會留著舊內容,
而且**會被當成指令執行** —— 還原時實測留下一行 `uncate`(被切半的註解)。
短檔要自己用註解補到原長度。

⚠ 合併卡的 AutoRun 有**兩套進度條**(`000→030→060→090` 然後 `050→060→090`),
改的時候要全部換掉。只換第一套的話,後半段會用新的 x/y 把版面蓋掉 ——
我因此以為「開機卡在第二格」,其實 AutoRun 跑完了(shell 有起來)。

---

## 10. ⚠ AutoRun 跑得很晚(2026-09-21 使用者更正)

**進度條顯示的是「fpSup 自己載入到哪」,一直都是** —— 不是相機開機進度。
AutoRun 開始跑的時候相機早就開好了,所以那幾格對應的是補丁、worker、loader、啟動
這些節點,不是開機階段。

**我整份筆記原本假設「AutoRun 畫圖的時候 GUI 還沒接手、螢幕是乾淨的」—— 這是錯的。**
AutoRun 很晚才開始跑,它能畫圖的時候相機該開的東西早就都開好了。

被這個假設影響的結論,已就地更正:

| 原本以為 | 實際 |
|---|---|
| 開機期沒人 present,所以 ×1 可能夠 | GUI 一直在 present,**×3 是必要的**(除非關掉重繪) |
| 開機期主層是空的 | 主層有相機自己的 UI(STBY、檔名、電池…) |
| 黑底可能不用畫 | **一定要**,否則字壓在 live view 和 UI 上 |
| 「字被洗掉」是理論風險 | 是真的會發生 |

**所以「關掉重繪」不是加分項,是核心** —— 一個 word 同時解掉 ×3 和被洗掉兩件事。

### 由此推出的設計(未驗證)
```
mem set 0xC0528700 0xE12FFF1E      # 停住重繪:相機不再重畫,我們的字不會被洗掉
display monitor 0 0
display osd 1 0x0000F000  ×3       # 主層填不透明黑 → UI 和 live view 一起消失
display monitor 0 1
display osd 1 0x00000000  ×3       # 副層清空
…橫幅(理論上 ×1 即可,但見 §6)…
mem set 0xC0528700 0xE92D4BF0      # 還原,相機自己重畫回來
```
**這樣連黑線 marker 都不用畫**(省 4 條 mem set + 1 條 display),
開機畫面是純黑底加橫幅,收尾把重繪還原就交還給相機。

⚠ 代價:那幾秒 live view 是黑的。開機畫面本來就不需要 live view,
但這是設計取捨,不是免費的。

⚠ 只想蓋掉**上排 UI**、保留 live view 的話,fill 做不到(它是整層)。
要用 `display osdfile` 貼一條 1024×56 的圖到左上角(見 `SPLASH_BAND.md`,
上排 UI 實測佔 y = 11..44),代價是卡上要放一個 ~115 KB 的檔。


## 11. 2026-09-24：透明四框候選，只做離線

使用者指定：減少載入條 AutoRun、`fp` 黃色、`Sup` 原本桃紅橘紅、四個小框依序填滿、
完成幾秒後恢復 UI，並明確要求先不上機。後續更正：**關掉原廠 UI 後不需要黑線**。
本輪沒有操作相機、寫卡、啟停 daemon、commit/push 或更新發行品。

維護來源新增 `fpSup/fp_usb_shell/build_autorun.py --loader --four-box-bar`，
`boot_splash.py` 產生透明 ARGB4444 圖，`templates/splash_finish.S` 由共用 stage2 同步呼叫。
保持 opt-in；普通 builder／網站 composer 的現行預設不改，因為還沒有上機確認這個版本。

- 開始先 `C0528700 = E12FFF1E`，借 echo 呼叫既有 ROM `C000E91C()`→`C000EABC()`，
  明確發布 pause patch；清主／副 OSD 三個緩衝為透明。不是全黑填色，也不碰 marker。
- `fp` 的預览黃是 `#FFDD44`；`Sup` 使用主層 4-bit 量化後的 `#FF6666`，
  對應原 palette B2 約 `#FF6668`。字形邊緣有 4-bit alpha。
- 每個 frame 為 656×56×2 = **73,472 bytes**；LCD 1024 座標上的圖形置中，
  只保留固定左上角貼圖所需的前導透明像素，裁掉右側／底部空白。
- 沒用五張連在一起的 atlas：native osdfile 每次讀**整份檔案**。
  分成 `FPSUPUI/0.BIN`…`4.BIN`，一次只讀當前那張。五階段各 ×3：
  合計 **1,102,080 bytes ≈ 1.05 MiB** 的圖檔讀取；不能把它宣稱為零 I/O。
- 保留 ×3：即使 GUI 停住，commit 仍輪替三個 descriptor，present 仍走非同步佇列；
  D/I flush 不會替我們排空之前的 present。沒有上機新證據，不能把 ×1 當已解決。
- AutoRun 只畫 0/1/2/3 格，Fast miss 進慢路徑不倒退；stage2 兩 pass／entry 返回後，
  在寫完 `LOAD_DONE_US` 後畫第四格，native sleep **2000 ms**，還原 prologue 並做 D/I。
- 收尾直接呼叫 native `C03E4270(ctx,6,argv)`，ctx 是本地 no-op printf，
  不經巢狀 shell parser。helper 在 staging 中**同步跑完**才返回；無新增 task、resident hook
  或固定 cave allocation，loader 隨後才釋放 staging。loader bytes 不变。
- 已查反編譯：只還原 prologue 不保證立即清掉所有自畫像素。成功路徑接著
  `CYC_DRAW/C05278F8()` → `C0527DD8(mgr,0,1)` → `C0527DD8(mgr,1,1)` →
  `C0527E40(mgr)`，要求原生主／副層透明 clear + redraw。實際 clear/present 交回 DrawThread。
- Fast 成功仍走原本 abort；完成顯示／UI 還原已在 abort 前結束。
  首次 fallback 仍走原本 AutoRun 收尾，不新增一次 abort。
- BIN 缺失／失敗：AutoRun 尾端直接還原 prologue、D/I、echo，不依賴 BIN helper。
  這個失敗路徑沒有上述 native full-redraw 呼叫，畫面完全更新仍依賴後續原廠事件，未上機確認。
- 初始化 pause 與 AutoRun 兜底仍是既有固定 firmware word 的寫法；不能宣稱整條鏈對任意
  外部 draw-hook 具有完整所有權偵測。builder 拒絕靜態 section 覆蓋同一字；自裝該 hook 的 payload
  不支援此選項。已有漏寫／三緩衝筆記仍適用，不把離線驗證冒充硬體保證。

同一主機從目前維護來源建置，非註解命令數：

| 配置 | 舊版 | 四框 | 其中 display：舊→新 |
|---|---:|---:|---:|
| 普通／debug 全腳本 | 104 | 106 | 31→20 |
| Fast 全腳本（含不一定會走到的 fallback） | 169 | 142 | 64→20 |
| Fast 命中時實際 AutoRun 前綴 | 69 | 58 | 37→20 |

**普通版總數多 2 條**，不能說整份 AutoRun 每種配置都縮短。
顯示步驟／還原／快取發布是不同成本；BIN 內還有 3 次直接 native osdfile 與 2 秒停留，
不計在 AutoRun display 條數裡。秒數、LCD 實際亮色、殘影、liveview 是否持續動態，均未上機驗證。
原始檔 32 KiB padding 保留，條數降低不等於 AutoRun.txt 檔案 bytes 減少。

離線輸出與 hash：`codex/four-box-splash-20260924/`，以其 README／validation 為準。
`cards/plain` 和 `cards/fast` 是無產品 payload 的載入鏈範例，debug 多帶 shell；
不是已整合完成的 OG／gyro 產品卡，也沒有取代 frozen release。


### 2026-09-24 後續視覺修正：置中與白色 fp

使用者指出四框比 fpSup 低，並提供配色圖，更正 **fp 是白色**。
`boot_splash.py` 現在依量化後 logo 的可見 alpha 範圍計算框的位置：
logo y=10..46，框 y=16..39；中心差 0.5 pixel（偶數寬高框的整數像素配置），
修掉先前框 y=20..43 的 3.5 pixel 下偏。字型與尺寸不變。

參考圖字體實色取樣：fp 約 RGB252/251/252 → 白色 `#FFFFFF`／`0xFFFF`；
Sup 約 `#E03959` → 最接近的 ARGB4444 `0xFD35`（展開 `#DD3355`）。
先前黃色 fp／coral Sup 是舊配色，以上述使用者更正為準。
僅改主機端圖案排版與配色，以及描述文字；未改載入器、UI 還原或等待流程。
預覽／四組離線範例重建於 `codex/four-box-splash-20260924/alignment-white-fp/`；
實際命令序列、BIN、圖檔尺寸與讀取量不變，沒有上機或寫卡。
