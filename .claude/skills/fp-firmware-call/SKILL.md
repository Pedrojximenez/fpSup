---
name: fp-firmware-call
description: 從主機直接呼叫 SIGMA fp(Ver.5.02)韌體裡的任意函式並讀回結果 —— 反組譯找到函式之後,用 callfn 借 echo 在 shell 任務裡一個一個呼叫、參數讀回驗證才 arm、緩衝區跟 cave.claim 要、建構後立刻解構;以及卡死之後怎麼冷開機恢復、怎麼記錄。Use when a firmware function found by disassembly (a file/dir/allocator/UI API, a getter, an object's vtable method) needs proving on the camera before card code depends on it, or when a "callfn ... DID NOT RETURN" / shell wedge needs diagnosing. Worked example: the dir-enumeration API (research/firmware/notes/DIR_ENUM_API.md).
---

> **設定區風險（2026-10-04 更新）**：原廠在 loader 前讀取持久設定；
> 不支援的值可能使開機或選單失效。**會寫設定區、寫卡、改 UI 狀態的函式不在本 skill 範圍內**，
> 上機前先照 `research/SETTINGS_AREA_FIRST_RULE.md` 調查。

# 上機呼叫韌體函式

目的:**卡片程式要依賴一個韌體函式之前,先從主機把它單獨叫一次,看它真的照反組譯說的那樣做。**
這比寫進 loader 再上機便宜得多 —— 錯了只是 shell 卡住,不是開機卡住。

前置:相機跑著帶 USB shell 的卡、`fpshd` 在跑(連線與 daemon 見 skill `fp-camera-control` §0)。
從 `fpSup/fp_usb_shell/` 匯入工具。

## 1. 先離線,把這個函式讀懂

- capstone 反組譯 `out/MAIN_c0000000.bin`(基底 `0xC0000000`)。**別把腳本命名成 `dis.py`** ——
  它會蓋掉 Python 標準庫的 `dis`,capstone 匯入時就壞了。
- 找函式最快的入口是**原生 shell 指令**:指令表是 24 B 一筆 `{name[20], handler}`,`echo` 在 `0xC0BAC2E4`,
  往前後走就是全部 77 筆。原生指令會用到的 API,它的 handler 就是現成的呼叫範例(參數、順序、緩衝大小)。
- 要回答的問題:參數各是什麼、要不要呼叫端給緩衝(多大、要不要先清零)、回傳值意義、
  **會不會等待**(mutex、事件、guard 初始化)、會不會寫卡或設定區、物件怎麼釋放。
- `movw/movt` 組出來的字串位址要自己拼(`0xC0BB0000 | lo`),別看漏 movt。

## 2. 第一呼叫一定是無害的 getter

```python
from callfn import call
call(0xC0407E20)          # 只回傳 [0xC2F20884](目前磁碟),應該是 1
```

**這一步證明的是工具,不是目標函式。** 沒有它,目標函式掛掉時分不出是誰的錯 ——
2026-10-06 就是跳過這一步,第一個呼叫就卡死,事後只能推測。

`callfn.call(fn, r0..r5, r10)` 在 shell 任務裡執行(借 echo 槽 `0xC0BAC2F8`),所以被呼叫者可以等待。
它**寫完參數會讀回比對、全部對了才 arm**(`mem set` 會靜默丟掉整條指令;P_FN 被丟就是跳到 0)。
如果你看到舊版 callfn 沒有這段,先補上再用。

## 3. 緩衝區:跟 cave.claim 要,用 put 寫

```python
import cave
from putfile import put, mem_get
B = cave.claim('mytool.buf', 0x280)       # 同一次開機同名同址
put(B, b'\0' * 8, 'holder')                # put 會讀回驗證;不要用裸 mem_set 寫輸入
```

- 不要自己挑位址(見 `fp-camera-control` §10)。arena 只有 3,920 B,大緩衝改跟配置器要。
- 字串參數自己補 `\0` 並對齊 4。
- 讀結果用 `mem_get(addr, n)`;**有 `None` 就是那個字沒回來**,重讀,不要拿去解碼。

## 4. 一次只多走一步

```
getter → 建構子(看物件內容合不合反組譯)→ 立刻解構
       → 建構 + 一個方法 + 解構 → 完整流程
```

每一步看到符合預期的值才走下一步:建構完讀物件的前幾個字,vtable / 子物件指標應該跟離線算的一樣。
**建出來的東西一定在同一段腳本裡用 `try/finally` 釋放**,中途出錯也不能留著。

## 5. 卡住了

症狀:`DID NOT RETURN`,之後 `version` 也 `LIBUSB_ERROR_TIMEOUT moved=0/64`。
`mem get` 也是韌體 shell 指令,所以它跟著不回不代表 USB 死了 —— 是 shell 任務卡在你的呼叫裡。

1. 先記下:最後一個送出的呼叫、它的參數、`cave.claim` 拿到的位址。
2. **echo 槽可能還指著 callfn**(還原那一步也逾時了),而它在韌體映像裡,暖開機會保留。所以要冷開機:
   **插著 USB 線關機**(會變冷開機),或拔電池。
3. 重開時**先別插 USB**:插著線開機,相機可能在卡片把介面補丁寫進去之前就跟主機枚舉完,
   `lsdesc` 會一直是 `06/01/01`(PTP),Mac 的 `icdd`/`ptpcamerad` 還會去搶。
   **等進度條跑完再插線**,`./lsdesc` 應該是 `ff/ff/ff`。
4. 舊的 daemon 拿的是失效的 handle(`LIBUSB_ERROR_NO_DEVICE`):用 socket `QUIT` 關掉它再起新的。
5. 回到 §2,從 getter 重來。

## 6. 記下來

- 結論寫進 `research/<主題>/notes/` 的 .md,**標明哪些是離線推論、哪些上機驗過、驗證日期**。
- 探針腳本放在筆記旁邊(例:`research/firmware/dir_enum_probe.py`),只用 `callfn`/`cave`/`put`,不帶自己的 hack。
- 上機看到的意外要寫成「對使用者的影響」,例如 macOS 留的 `._*` 檔會被當成 sup 讀。

## 範例:列目錄 API(2026-10-06)

`research/firmware/notes/DIR_ENUM_API.md` + `research/firmware/dir_enum_probe.py`:
從 `dir` 指令(handler `0xC03E2980`)找到 `dir_ctor/open/next/dtor`,照上面的順序上機驗證 ——
內容與原生 `dir` 一致、未排序、子目錄不回 `.`/`..`、不存在的路徑乾淨失敗。
第一次跳過 §2 卡死一次,原因是舊版 callfn 不讀回參數。
