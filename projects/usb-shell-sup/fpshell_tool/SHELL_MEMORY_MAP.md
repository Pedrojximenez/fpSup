# USB shell session 的位址地圖

**這份存在的原因**:我在這個只有約 3.8 KB 的視窗裡憑手感分配位址,撞車三次,
其中兩次要拔電池:

| 撞的東西 | 後果 |
|---|---|
| 注入常式蓋掉 `PEEK_CODE` | peek 全部回傳垃圾 |
| `FILEOBJ` 放進 worker 程式碼區 | 檔案開檔失敗(誤導了半小時) |
| 串流任務的 `CTL` 蓋掉 `push_addr` | BATCHPUSH 執行垃圾 → **相機凍結** |

**分配新位址之前先查這張表,並在使用前寫一個標記回讀確認。**

## 固定佔用(工具鏈,不要碰)

```
0xC072E000 .. 0xC072EFFF   USB shell worker 的程式碼        受保護,主機寫不進去
0xC072F000                 worker 表頭                      受保護
0xC072F060                 BATCHPUSH 來源(bus 位址)         可寫
0xC072F064                 fpstate PEEK_ARG                 可寫
0xC072F068                 fpstate PEEK_RES                 可寫
0xC072F070                 BATCHPUSH 幀數                   可寫
0xC072F078                 BATCHPUSH 幀大小                 可寫
0xC072F07C                 telemetry 每幀延遲               可寫
0xC072F100 .. 0xC072F1xx   fpstate PEEK_CODE(注入的常式)
0xC072F200                 lensdump BLOCK_CAVE
0xC072F300                 lensdump RAW_CAVE
0xC072F400                 telemetry RECORD
0xC072F600 .. 0xC072F674   ★ push_addr 常式(pushread / BATCHPUSH 的呼叫位址,
                             daemon 寫死在這裡,不能搬)
```

上界約 `0xC0730000`。

## 共用區間 —— 先到先得,不能同時跑
```
0xC072F700 .. 0xC0730010   lensdump RESULT。**只有 lensdump 在跑時才佔用**,
                           其他一次性測試可以借,但兩者不能並行。
```

## 真正一直空著的
```
0xC072F480 .. 0xC072F5FF    約 384 bytes
0xC072F680 .. 0xC072F6FF    約 128 bytes
```
就這樣,連一個 600 bytes 的常式都放不下。

**所以:狀態與緩衝一律放 `memmgr bufmem` 的池** —— 起點 `0x44F6ADC0`,
配置大小不影響回傳位址(4 KB 與 8 MB 兩種配置實測都回同一個位址),空間充足。
`0xC072Fxxx` 只留給**必須在韌體 code cave 裡執行的常式**(寫進 DRAM 再執行還要處理
I-cache 一致性,不要為了省事去踩)。

## 紀律
1. 用之前先寫標記回讀確認,不要靠推斷。
2. `pushread.read()` 每次推送前會檢查自己的常式沒被蓋掉(`verify()`)。
3. 常式與它的狀態/緩衝**永遠分開配置**,不要讓某個東西的 base 落在別人的程式碼裡。
