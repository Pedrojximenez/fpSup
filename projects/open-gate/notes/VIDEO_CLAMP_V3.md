# OG 的 video clamp(黑位校正)—— v3 鏈式核心

2026-10-07,**離線完成,未上機、未寫卡、未 commit**。只動 v3 + `OG_CHAIN` 建置(`30OG3K.BIN`/`30OG2K.BIN`);
AutoRun 卡的 OpenGate 區段逐位元組不變(新程式碼全在 `#ifdef OG_GTAB_SHARED`,只有 `WITH_CLAMP` 時才定義;
非 v3 的 `og3k_plan.py` 靜態檢查字數照舊:og3k 1005、og2k 1038 筆)。

背景:Jose fpSup-Formats v0.6.1 量到 3:2 用的靜態/LV 模式走 stills clamp,高 ISO 時黑位逐格跳一階、DNG 仍是
BlackLevel 256 → 暗部閃。我們的 donor 模式 98/117/139 在映像裡同樣沒有 video clamp
(`projects/jose-hurtado/notes/JOSE_VS_OURS.md` §5.1)。

## 1. 改了什麼

| 字(clamp 記錄 = `0xC0B5C638 + 0x38 × 模式在時序表的序號`,`+0` = 模式號) | 原廠 | OG 生效時 |
|---|---|---|
| OG3K:mode 98 `C0B5C6AC`(+4)/ `C0B5C6C0`(+0x18) | `0` / `0x00040003` | `0x8` / `0x0004C003` |
| OG3K:mode 117(OG3K100)`C0B5CF34` / `C0B5CF48` | `0` / `0x00040003` | `0x8` / `0x0004C003` |
| OG2K:mode 139 `C0B5CE54` / `C0B5CE68` | `0` / `0x00040002` | `0x8` / `0x0004C002` |

位元 = 原廠影片模式都有的兩欄(+4 bit 3、+0x18 bit 14–15),與 Jose v0.6.1 對 98/139 寫的字相同(117 他會設但從不清,我們會清)。

- **機制**:每個字是一個**私有 GTAB 群組**(筆數 1、選中值、未選值),排在共用的六個預覽高群組之後。
  og3ksel / og3kfmt 的既有交易(關中斷、先撤旗標、最後發布 FLAG)本來就按 `FLAG` 寫 GTAB,所以 clamp **只在 OG 生效**
  (選了本目標且錄影格式是 CinemaDNG)時開;選 UHD/FHD、換成 MOV、關機都回到原廠值。mode 3/98 是原廠 AF/放大鏡也用的模式 —— 只在 OG 生效期間被改。
- **兩個 OG 同卡**:離開時若 `OGSAVE` 是別的 OG(它剛被選),og3ksel 只跳過**前 `OG_GTAB_SHARED`(= 1)個共用群組**
  (預覽高,交給新的那層),自己的 clamp 照樣寫回。兩者的 clamp 字不重疊(98/117 vs 139),所以哪一層先跑都正確。
  (原本是整個 GTAB 都跳過 —— 那只在 GTAB 只有共用群組時成立。)
- **claim**:clamp 字 **EXCL、只登記**(payload 執行期寫),關機由加載器 journal 寫回原廠;共用預覽高維持 CHAIN。
- **建置檢查**(`og3k_plan.clamp_groups`):記錄 `+0` 必須等於模式號;donor 的兩欄在映像裡必須是 0;
  參考影片模式 106(FHD30)必須正好有這些位元 —— 任一不符建置停止。GTAB 仍在 `0xC0732200` 以內(og3k 104 B)。

| 檔案 | 改動 |
|---|---|
| `build/og3k_plan.py` | `CLAMP_BASE/STRIDE/FIELDS`、`WITH_CLAMP`(= `OG_CHAIN` 且 `OG_CLAMP` ≠ 0)、`GTAB_SHARED_GROUPS`;`groups()` 追加 `clamp_groups()`;`OG_GTAB_SHARED` define;字數絆線 +4 + 每字 4 |
| `build/og3ksel.S` | `OG_GTAB_SHARED`:r7 = 要跳過的共用群組數;離開給別的 OG 時 `movne r7,#1` 取代 `bne gdone`;迴圈 `cmp r7/streq`、`subne r7` |
| `build/build_v3_og.py` | 只有前 `GTAB_SHARED_GROUPS` 個群組是 CHAIN,其餘(clamp)EXCL;facts 加 `clamp_words` |
| `build/test_v3_og.py` | 3 個新測試 + 兩個切換測試加 clamp 斷言 |

og3kfmt 不用改:它的離開只在本層生效時才寫,寫的是全部群組(包含共用),跟以前一樣。

## 2. 測試(unicorn,真 loader + LOADER.BIN + 真 30OG*.BIN,參考映像)

- `test_v3_og` **23 項全過**(原 20 + 3):
  - `test_the_clamp_words_are_the_donor_modes_and_claimed_exclusively`:clamp 字 = 測試裡獨立寫死的六個位址(與 Jose 宣告的相同)、映像裡位元為 0、mode 106 有、claim 是 EXCL 只登記。
  - `test_the_clamp_is_on_only_while_the_og_is_live`:選 OG 但格式未知 → 關;CinemaDNG → 開;**經 `C005BE58` 換 MOV → 關**(預覽高也回原廠);換回 CinemaDNG → 開;UHD → 關;選著 OG 關機 → 原廠。
  - `test_a_clamp_word_held_by_another_releases`:別的 sup EXCL 佔一個 clamp 字 → RELEASE、什麼都沒寫。
  - 兩個切換測試(OG2K 檔先 / OG3K 檔先):FHD → OG3K → OG2K → OG3K → OG2K → FHD 每一步,各自的 clamp = 各自的 FLAG;OG2K 生效時關機 → 全部原廠。
- `test_v3_reslab` 16 項、`test_og3k_load` + `test_og_nested_strings` 15 項全過(未受影響)。
- **mutation 8/8 抓到**:離開時整個 GTAB 跳過(舊行為)、共用群組不跳、跳過計數不遞減、`OG_CLAMP` 預設關、只設 bit 3、
  記錄間距錯(建置停)、clamp 字 claim 成 CHAIN、漏掉 mode 117(字數絆線停)。腳本每次用新的 `PYTHONPYCACHEPREFIX`。

## 3. 上機驗證步驟(要使用者同意後才做)

前置:卡 = 00SHELL + 30OG3K(或 30OG2K)+ 對應 LOADER.BIN;SSD 或快卡;固定機位、鏡頭蓋上或暗場(有一點暗部細節更好)。

1. **開機確認**:LOAD.LOG 載入;`mem` 讀六個 clamp 字 = 原廠(表 §1)。選 OG3K、CinemaDNG 12-bit → 讀回 = 「OG 生效」那欄;選 UHD → 原廠。
2. **A/B 錄影**(25p、1/50、ISO 1250,同一場景,每段 ≥ 10 s):
   - A = 本版 30OG3K;B = 同卡把 clamp 關掉的建置(`OG_CLAMP=0` 重建 30OG3K;或 A 錄完用 shell 把六字寫回原廠再錄,只改一個變因);
   - OG3K 25p、OG3K 100p(mode 117)、OG2K 25p 各一組;另錄原廠 UHD 25p 當參考。
3. **逐格分析**(每個 DNG):
   - 讀 DNG 的 `BlackLevel`(原廠 UHD 是逐格值;B 版預期固定 256);
   - 算光學黑/暗區(或鏡頭蓋全幅)四個 Bayer 通道各自的平均;逐格差分;**跳階 = 相鄰格平均差 ≈ 1 DN(12-bit)且成群出現**;
   - 判準:B 版應重現 Jose 的現象(約三分之一的格跳一階);A 版 0 跳、BlackLevel 逐格變動,與原廠 UHD 同型。
4. **副作用檢查**:OG 生效時半按 AF、放大鏡 4×/8×(mode 98 也被它們用)畫面正常;切回 UHD/FHD 後 AF/放大鏡正常、六字 = 原廠;
   MOV 錄一段;選著 OG 撥開關關機 → 冷開機前讀六字 = 原廠(journal 寫回)。
5. **兩個 OG 同卡**(enum 4/7 已分開後):OG3K ↔ OG2K 切換,每次讀六字,只有生效那個的字是開的。

## 4. 未決

- mode 117 只在 OG3K100 被用,但我們在 OG3K 生效時就開(與 98 同時)—— 簡單且對稱;若上機發現 117 被原廠其他功能(例如 MOV 100p)
  在 OG3K 生效期間使用而受影響,改成只在 picker 命中 OG3K100 時開。
- GTAB 寫整字(不是 Jose 的 RMW 位元運算)。前提是韌體不在執行期改這兩字的其他位元;映像裡是靜態表,上機第 1 步順便確認。
