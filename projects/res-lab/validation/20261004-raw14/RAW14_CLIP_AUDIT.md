# RAW14 CinemaDNG 短片只讀稽核

`projects/open-gate/build/raw14_clip_audit.py` 逐格讀取現有 CinemaDNG 短片，並對照 WAV。它不呼叫相機或 USB shell，不改動 DNG、WAV 或卡片。請先以實際新錄成的片段路徑與當次設定格率執行；不要用舊片當成新韌體的錄影證據。

從 `projects/open-gate/build` 執行，例如：

```sh
python3 -B raw14_clip_audit.py --fps 24000/1001 --expect 4176x2174 \
  --require-wav --sample-all --json /Volumes/fpSup2/CINEMA/A001_010

python3 -B raw14_clip_audit.py --fps 18 --expect 6064x4042 \
  --require-wav --sample-all --wall-seconds 10.2 --json \
  /Volumes/fpSup2/CINEMA/A001_011
```

`--fps 23.976` 是 `24000/1001` 的別名；`--fps 18` 比對 `18000/1000` 或任何等價的 18/1 DNG 有理數。`--expect` 為選用，應填實際模式主影像尺寸。預設只抽樣首、中、末三格的 14-bit 像素低兩位；`--sample-all` 對短片逐格抽樣。`--wall-seconds` 只適用單一片段，填人工記下的 REC 到停止秒數。`--duration-tolerance` 預設 0.5 秒，可依計時精度調整。工具輸出 JSON 到標準輸出；若需保存報告，將輸出重新導向到工作區的驗證資料夾，勿寫回 SD 卡。

每格都檢查主 IFD 是最大影像、`BitsPerSample=14`、`Compression=1`、`WhiteLevel=16383`、BlackLevel 範圍、StripOffsets/StripByteCounts 不越界或重疊、14-bit packed 長度、`FrameRate`、可用的 8-byte TimeCodes，以及檔名六位序號連續。TimeCodes 以預期名義格率檢查相鄰 BCD frame 數；私有 18p 的 18-count BCD 僅作診斷，不視為 SMPTE 已支援的 18p 時碼。WAV 檢查 RIFF 封口、16-bit PCM 的通道/取樣率/長度、BWF TimeReference、iXML `MASTER_SPEED`／`CURRENT_SPEED`／`TIMECODE_RATE`，並列出 WAV 秒數減 `DNG_count/fps` 與人工計時的差。

fp 原廠 WAV 的 iXML 外層 `<SPEED>` 未配對，工具只擷取明確的速度欄位，不因外層 XML 不完整而略過速度檢查。對 23.976p，iXML `TIMECODE_RATE` 以名義 24 比對；對私有 18p，以診斷用 18 比對。這能指出原廠 23.976 承載值的錯誤標籤，但不會修復任何韌體錄影路徑。

**解讀限制：** `PASS` 只表示讀到的檔案符合上述結構與標籤規則。低位元有變化不能證明感測器的類比 14-bit 精度或正確增益；DNG 標籤不能量到真實影像產生節奏；單段 WAV 與畫面片長差也無法區分固定啟停偏移與持續漂移。18p 音畫同步仍需有兩次可對應的可見/可聽事件，量相隔影格數與 PCM 樣本數，並以實際短片與人工計時核對。

目前沒有 RAW14 電影片可執行此稽核。先前 `card-read-20261004.json` 的 r83 九段、699 格全為 12-bit；它們只作 12-bit 拒絕基線。合成 DNG/WAV 測試由 `python3 -B test_raw14_clip_audit.py` 驗證解析、逐格時碼、iXML 格率及壞 strip／片長拒絕，不能替代實錄。
