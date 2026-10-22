# ⚠️ USB shell 的 mem 讀寫有位址範圍限制 (2026-08-25)

**這一條會讓錯誤的資料看起來像對的,所以放最前面。**

## 寫入:主機端 `mem set` 有保護區,但**不是**乾淨的分界
> ⚠️ **訂正(同日稍晚)**:先前這裡寫「`0xC072F100` 以下一律不可寫」,那是**掃描
> 粒度造成的誤判**。我用 0x80 間隔掃,只測到 `0xC072F000`(worker 表頭,確實受保護)
> 就把整段以下都歸類為不可寫。實測 `0xC072F060 / F070 / F078` **可寫** ——
> 那正是 BATCHPUSH 的參數槽,lensdump 一直在用。

```
0xC072E000 .. 0xC072EFFF   worker 程式碼,寫不進去
0xC072F000                 worker 表頭,受保護
0xC072F060/70/78           可寫(BATCHPUSH 參數槽)
0xC072F100 以上            可寫
```
未逐字組掃過完整分佈。**要用哪個位址就先寫一個標記回讀確認**,不要靠這張表推斷。

`0xC072E000`–`0xC072F0FF` 是 shell worker 自己的程式碼與狀態,worker 擋掉了對它的寫入。
**失敗是靜默的** —— 沒有回傳錯誤,回讀就是舊值。

**相機端的注入程式碼不受此限**,可以寫任何位址。

### 已經被這條坑到的
- `projects/gyro-sup/fpshell-era/lens_write_shell.S` 第一次測試:路徑字串由主機寫進 `0xC072EB80` → 沒生效 →
  那次寫檔用的是垃圾路徑,**結果不可信**。
- 多次「先清空 STATE 再跑」的動作全部是 no-op。

→ 凡是要給注入程式碼的參數,緩衝一律放 `0xC072F100` 以上。

## 讀取:`read_mem` 超出範圍時回傳「指令回音」而不是報錯
```
0xC0016A58 (ROM)      與本地韌體逐位元組一致  ✓
0xC072EC00 (scratch)  正確                    ✓
0xC375D8C0            回傳 "mem read 0xC375D" ← 指令字串本身
0xC37CE1E0            同樣是 ASCII 回音
```
**這是最危險的一種失敗**:回來的是可列印位元組,擺在 hexdump 裡看起來像真資料。
先前一次「descriptor 掃描」就是這樣讀出 ASCII 才發現的。

### ★ 正解:`monitor/pushread.py`(hook-push)
`read_mem` 從一開始就不該用在這裡 —— 專案紀律要求功能實作走 hook-push。
`camera/push_addr.S` 可以從**任意位址**推送,沒有範圍限制、速度是 MB/s 級、
失敗會回報 LIBUSB 錯誤而不是安靜地給你假資料。

```python
pushread.install(sh)                        # 注入常式
pushread.selftest(sh, sock)                 # 推 ROM 回來跟本地韌體比對
data = pushread.read(sh, sock, addr, n)     # 任意位址
```
實測 `0xC3757A7C`(read_mem 到不了)一次就取回,`0xC0016A58` / `0xC03554A0`
與 ROM 逐位元組一致。

### 舊對策(僅供參考):`camera/memcpy_scratch.S`
相機端把要看的區間複製到 `0xC072FC00`(可讀範圍內),主機再讀。
自證方式:複製一段 ROM 跟 `out/MAIN_c0000000.bin` 比對。

```
ARG 0xC072F400: [0]=src [4]=len(≤0x400)
OUT 0xC072FC00: 資料
```

## 通用原則
**任何記憶體檢視工具都要先自證**:寫一個已知標記再找回來 / 複製一段 ROM 再跟本地檔比對。
`camera/u32_scan.S` 第一版因為 ARG 落在不可寫區,`lo > hi`,迴圈立刻結束回報 0 命中 ——
看起來就像「掃過了但沒有」。自證加上去才發現。
