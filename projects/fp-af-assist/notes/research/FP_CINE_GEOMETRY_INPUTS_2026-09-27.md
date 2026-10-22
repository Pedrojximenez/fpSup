# CINE 連續 AF：face／AAT 共用幾何輸入稽核

日期：2026-09-27。範圍：離線閱讀既有 core、decoder、adapter 契約及 bridge 參考；未操作相機、socket、韌體或載入鏈，未據新實機樣本判定 AAT 已初始化。已閱讀 `fpSup/AGENTS.md`，本次只新增本筆記。

**結論：共用方向核心及固定框防護已存在，這輪不再新增 `cine_subject` adapter。** 真正缺口是 CINE 原生來源的尺度／時間／身份驗證，以及鏡頭持續移動時可用的觀測策略。已有 decoder 不能自動填補這些條件；幾何接近／遠離也不能直接換成鏡頭位置增減。

## 1. 已有共用路徑及防護

| 層級 | 已有行為 | 精確來源 |
|---|---|---|
| raw subject decoder | face group、AAT publication、AAT model 分開，保留來源地址、型別、全部 bytes；未知座標參照／時間不補值，`geometry_eligible=false` | [af_subject_observation.py](../../../../research/autofocus/af_subject_observation.py) L23–54、L68–108、L118–148、L151–192 |
| native observer decoder | face／AAT 使用同一 raw decoder；來源時間、曝光序號及跨來源排序／一致性仍未知，不直接產生 FgSample | [observer_decode.py](../../../../fpSup/focus/geometry/observer_decode.py) L13–22、L54–83 |
| 共用幾何核心 | `FG_FACE`／`FG_AAT` 使用同一線性尺度 `size / effective_image_width`；AAT 另外必須具備 `FG_AAT_SCALE_VALIDATED` | [geometry.h](../../../../fpSup/focus/geometry/geometry.h) L6–28、L52–62；[geometry.c](../../../../fpSup/focus/geometry/geometry.c) L194–213 |
| 身份／來源切換 | 比較 target、context、scale generation 及 source kind；任一更換使原錨點失效，重新取得可信光學確認 | [geometry.c](../../../../fpSup/focus/geometry/geometry.c) L87–101、L246–269、L379–407 |
| 離線輸入 provenance | JSONL 明確宣告 synthetic／annotated_replay／camera_capture、normalized_linear_size、共同時鐘；輸出仍明列輸入 assertions 未獨立驗證 | [replay.py](../../../../fpSup/focus/geometry/replay.py) L33–42、L91–104 |
| 合焦事件配對 | join 仍是 shadow 契約；位置、settlement、來源時間不能由快取值推定，candidate 不等於已獲合焦授權 | [confirm_join.h](../../../../fpSup/focus/geometry/confirm_join.h) L6–21、L46–74 |

這是「兩個來源共用一套語意」，不是將 face、AAT 的原始框混成一條連續軌跡。即使目標仍是同一人，face → AAT／AAT → face 或 reseed 也須換 `scale_generation`，目前 source kind 改變本身亦會使錨點失效。分別維持各來源尺度定義，不能用相似的數字宣稱 handover 無縫。

## 2. AAT 哪些數字不能當幾何尺度

1. **publication 可能是固定 64×64 框。** `C05AC690` 一條分支從結果邊界求長寬，另一條直接呼叫 `C05A8B30(..., 0x40, 0x40)`；後續 AF 輸入 tuple 再沿用該長寬。因此固定框不能證明主體靜止，也不能因 `valid`／`quality` 良好便取得 scale validity。原始來源：[blk_c05.c](../../../../out/decomp/full/blk_c05.c) L132714–132727。decoder 將兩個 tuple 分開並保留固定框警示：[af_subject_observation.py](../../../../research/autofocus/af_subject_observation.py) L38–45、L167–180。
2. **model 半軸可變，仍非自然物體輪廓。** 初始半軸由輸入邊界建立並夾限；每幀 `C05B2DC0` 會按半軸大小及 lost 條件乘增益、調整比例、夾限，再回寫 `+4/+6`。它包含 tracker 的搜尋策略，不能直接解釋成主體遠近。來源：[blk_c05.c](../../../../out/decomp/full/blk_c05.c) L139675–139707、L136650–136674。
3. **quality 不是尺度可信度。** `model+0x0C` 是 hits 映射，`+0x0D` 是半軸面積相對上限的比例；都不能獨立設定 `FG_AAT_SCALE_VALIDATED`。來源：[blk_c05.c](../../../../out/decomp/full/blk_c05.c) L139893–139916。

因此 AAT 幾何驗證必須回答「哪個原生量隨同一主體的投影尺寸可靠變化」，不能只比較追蹤框有沒有變大。原廠已有 normalizer；缺失 normalizer 的復刻結果也不能作為原廠尺度失效的證據。

## 3. CINE 連續 AF 的兩條觀測路徑

目前 `FG_LENS_STATIONARY` 不成立時，core 保留仍有效的合焦錨點、清除整段趨勢並輸出 `UNKNOWN / FG_LENS_MOVING`。它**尚不能在鏡頭不停移動時連續判斷方向**。預設至少 5 點、120 ms，窗口 300 ms，這些是開發參數，並非已驗證的 CINE 延遲要求。來源：[geometry.c](../../../../fpSup/focus/geometry/geometry.c) L194–213、L399–403；[README.md](../geometry/README.md) L67–75。

| 路徑 | 必須量測的條件 | 成功／停止 gate |
|---|---|---|
| 短暫穩定窗口 | 在原廠連續 AF 運作中，記錄真實 lens-settled 區段長度、來源更新率及 age；分 face／AAT 計算足夠樣本窗口的覆蓋率、方向延遲與轉向錯判 | 窗口須真的覆蓋多個新鮮同主體樣本，且攝影效果／延遲可接受。若窗口不足以符合既定門檻，就報告不足；不能重讀快取湊點、把 moving 設成 stationary，或未驗證便縮短門檻。是否增加穩定窗口屬後續控制策略，不在本次實作。 |
| 經校準的呼吸補償 | 固定主體與相機，跨焦位量測 normalized size 與實際 lens position 的關係；按鏡頭、焦段、readout／crop、移動方向及曝光時序分組；再用獨立的主體移動序列驗證 | 補償後的靜止假方向、移動方向錯判、殘差與延遲須通過事先訂定的 CINE 標準，並確認 lens position 與主體影格同步。這需要新的「移動中已校準尺度」契約及測試；目前不能把補償候選標成 `FG_LENS_STATIONARY`，亦不能繞過 join 的 `FJ_SETTLE_VALIDATED`。 |

兩條路徑獨立評估。第一條可能只有間歇方向輸出；第二條需要額外校準與輸入契約，未在現有 core 實現。呼吸補償也不會自動解決人臉姿態、遮擋、AAT 模板漂移、變焦、裁切及防震造成的尺度變化。

## 4. 最小下一步：完成原生輸入證據

1. **CINE 來源與影像參照。** 分別釐清 face primary／detector tuple、AAT publication／model 的實際座標參照及有效影像寬度；保存 readout、crop、錄影狀態與來源完成時點。錄影啟停或影像模式切換時，除非證實同一投影，否則換 `context_generation`、重新建立錨點。不可直接將 face size 除以猜測的 320，也不可將未知來源補成 bridge 的 1620。
2. **face／AAT 各自尺度效度。** 用已知接近／遠離／靜止序列，另外加入轉頭、橫移、遮擋／重抓及背景相似色；量測方向覆蓋率、錯向率、靜止假動作與 latency。AAT 需區分固定 publication、搜尋 normalizer、自適應 model；來源內部變化與真正投影尺寸分不開時維持不可信。
3. **同源時間及身份。** adapter 維護 target／context／scale generations；缺幀、重新偵測、reseeding、來源切換明確處理。讀取時間、path counter、native slot／tracking ID 都不能直接冒充曝光時間或永久身份。[geometry.h](../../../../fpSup/focus/geometry/geometry.h) L6–10、L52–62 已有契約，raw decoder 尚未替相機證實。
4. **CINE 光學錨點及 lens-settled 證據。** 以原廠成功 AF、所屬 drive、真實完成／穩定狀態及新鮮同主體樣本形成可重播的配對；不要把 Hpeak、函式 return、command cached position 當合焦。現有 shadow join 的測試證明防護邏輯，不證明這些 native assertions 已成立。

**幾何方向與鏡頭 sign 分開：** core 擬合 `anchor_scale / current_scale` 的相對變化率，負值是接近、正值是遠離；不表示目前離焦的正負，也不表示 native position 要加或減。`lens_position` 目前是診斷／錨點欄位，`motion_authorized` 永遠為 0。來源：[geometry.c](../../../../fpSup/focus/geometry/geometry.c) L103–119、L349–355；[geometry.h](../../../../fpSup/focus/geometry/geometry.h) L62–78、L101–113。

## 5. bridge 可借用的經驗與邊界

唯讀參考 [sigma-fp-bridge/focus-ai/focus/subject.py](/Users/dido/Developer.localized/sigma-fp-bridge/focus-ai/focus/subject.py) L144–200：該 host pipeline 記錄過錄影啟動時 live-view 分辨率變化，先按 `size / frame_width` 統一尺度。這支持「在來源出口統一座標並保留 frame provenance」，不證明本機 native face／AAT 使用同樣分辨率或裁切；L190 的缺 frame fallback 不能照搬到未知 native 來源。

[predict.py](/Users/dido/Developer.localized/sigma-fp-bridge/focus-ai/focus/predict.py) L131–144、L163–176 將倒數尺度預測與 `curve.position` 轉換分開。可借用此分層，不能搬用其鏡頭曲線、馬達 sign、延遲或信心門檻來認定 fp 機內 AAT 已可幾何追焦；相對方向估計本身不要求先知道任意物體的實際尺寸。

## 6. 本輪離線驗證

- `python3 -B -m unittest test_geometry test_confirm_join`（`fpSup/focus/geometry`）：**57 tests PASS**。
- `python3 -B -m unittest test_af_subject_observation`（`research/autofocus`）：**13 tests PASS**。
- 已涵蓋 source／generation 換代丟錨點、未驗證 AAT 無法開始或延續幾何、已明示驗證的 AAT 共用相同物理契約、lens moving 清趨勢、未驗證 settle 被拒絕、正尺寸／valid／quality 不自動產生 geometry authority。來源：[test_geometry.py](../../../../fpSup/focus/geometry/test_geometry.py) L273–331；[test_confirm_join.py](../../../../fpSup/focus/geometry/test_confirm_join.py) L430–468；[test_af_subject_observation.py](../../../../research/autofocus/test_af_subject_observation.py) L162–173。

未改 core、decoder、adapter 或 transport。以上通過是離線契約驗證，並非 CINE 實機精度、AAT 啟動、原生事件同步、呼吸補償或鏡頭控制的驗證。
