# fp 5.02：Focus drive gate、完成／停止與唯讀查詢

2026-09-16。這是來源審核與只讀實測，不是自製 drive 上機通過的宣告。

同日後續更正與補充見 [native control 稽核](FP_NATIVE_FOCUS_CONTROL_2026-09-16.md)。
`C0017AC8()` 回傳原始 singleton +0x18；實際 shutter gate 是 `C3033A6C`，
真正 MovieRecording 是 `C30338D0`。`C04EF7D0` 本身不啟動 PtpFocusWait worker，
該 worker 還有 PTP 通知的無限 semaphore wait；不可把 submit 當作完整 worker 啟動／收尾。
後續 20-pulse 實測與傳輸中斷／還原紀錄屬於
[`projects/fp-af-assist/`](../../../projects/fp-af-assist/README.md)，不改寫本文較早的只讀紀錄。

## 1. 舊 gate 說法需要撤回

`C04EF7D0(target)` 並非「自己檢查 LiveView、AF busy、recording 後才動」的通用安全入口。
實際 `blk_c04.c:177338–177393` 依序檢查：

- `C035F560()!=0`：底層 lens-controller state==2，不是已證明的 camera LiveView。
- `C0362558()==0`：lens property/protocol 判斷，不是已證明的 AF busy。
- `C02DF7C8()!=2`：保留原始 predicate，不擅自改名。
- `C036E1D8(worker+4)==1`：PTP focus worker readiness。
- target 在 `C02DFFB0/C02DFFD0` inclusive range 內。
- `C04EE890(2,0)` request handshake 成功（該路徑 wait 參數為 5000）。

回 `0x2001` 僅代表提交動作；`0x200F` readiness/property rejection、`0x201D` 越界、
`0x2019` handshake failure。它本身沒有直接讀 capture `+0x220`。
`0x9032` caller `C04F5AE8` 才在 `+0x220==0 && +0x7C==0` 時呼叫它，
但此前已執行 `C04FCDF8` 和 MenuSet 同步 `C04F4E78(param,7)`（181133–181143），
不能把該命令當作已證明不改設定的 move-only 操作。

Native `ptp cmd set_grf` 可到達該 0x9032 路徑；`lens setfpos` 則直接走 ungated `C035FFC0`
（blk_c03.c:169077）。本輪不使用兩者；不能因名稱含 gated 就擴大授權或越過檢查。

## 2. 讀位置、等待完成、停止是三件事

- `C035FD48`：位置 getter，不停止鏡頭。native-L 路徑在 drive completion 更新位置
  （blk_c03.c:42186），重複相同值可能只是 stale cache。
- `C035FF08`：wait-complete；native-L wait 參數 15000，含 timeout error/assert
  （blk_c03.c:41809），不是 abort。
- native-L abort chain：`C035FEE8 → C0360540 → C03325C0 → C033F638`。
  目前沒有找到已核對的 native shell abort 指令；**本輪未呼叫或部署此鏈**。
- `ptp focus_comp` 是 completion notification，不是停止命令。

因此不以 ACK、固定 sleep、host timeout 或單次 getter 相等替代動作完成／停止的實證。
自訂 callfn／ARM 控制路線還需自己的 ABI、所有權、限時與復原審核；不能與 collector 同時借 echo。

## 3. 已核對的只讀 native 命令

| 命令 | Handler | 意義 |
|---|---|---|
| `lens getfpos` | C03F6840 | cached signed position |
| `lens getfedge 0` / `1` | C03F6720 | inf / near **distance** edge，不是 position endpoints |
| `lens cnvfpos D` | C03F67A0 | distance→signed position |
| `lens cnvfdist P` | C03F67F0 | position→unsigned distance；2147483647 是 infinity sentinel |

Handler 在 `blk_c03.c:168962–169038`，dispatcher 先印 `lens <name> `。
數字解析 `C01F5B88 → C01F5A04(arg,0,10)`（blk_c01.c:151856），使用十進位，不用 0x。
兩個 conversion 不帶參數會換算預設 1000；新工具要求明確參數。
已初始化 native-L 路徑使用 cached lens tables／有限迴圈，未見 drive、wait 或 setting call。
wrapper 可能 lazy-init lens singleton，不能泛稱所有未知鏡頭狀態絕對零副作用。

新工具 [af_fusion_lens_readout.py](../af_fusion_lens_readout.py) 只允許上表命令，
沿用 host lock 與有限 socket wait；先確認 w71c1／5.02.0.V91，所有回覆保留。
未開啟移動能力，也不使用 RAM injection。

## 4. 05:59 的只讀實測

[原始證據](../captures/af-fusion/2026-09-16-direction-study/lens-readout.json)：

| 查詢 | 結果 |
|---|---:|
| cached getfpos | 10707 |
| inf distance edge | 2147483647 |
| near distance edge | 300 |
| inf distance→position | 6276 |
| near distance→position | 10706 |

目前 cached position 比 nominal near 換算大 1，因此「current±100 都落在 nominal range」
前置条件失敗，工具在第五個 lens 回覆後停止，未送 ±100 conversion、更沒有位移。
原檔 status=`readout-incomplete`，拒絕原因完整保留；不能把未完成的 local conversion 寫成成功。

端點表支持「較大位置值對應較近端」的粗略方向，但本輪沒有完成 current±100 局部換算，
沒有新的馬達或光學驗證；不把先前 10023 峰位當作現在仍在的實體焦位，也不推斷位置變化原因。
名義端點和 getter 差 1 與取整／額外 allowance 相容，**成因尚未測定**。
`C02DFFB0/C02DFFD0` 本身還會把 distance edge 轉 position，再扣／加 allowance
（blk_c02.c:142773–142791），所以此 nominal range 不能直接取代驅動器真實邊界。

原始 transcript 是權威；工具之後另增加在 guard 前保存 top-level endpoints 的診斷欄位，
未重寫這份已發生的查詢，也沒有為了得到成功回覆反覆上機。
