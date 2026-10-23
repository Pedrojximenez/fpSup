# USB Storage → Write Mode(Standard / Custom)

> **2026-10-14 補完:** 實際作用已追到 —— `settings+0x9C = (MediaSelect==0) ? 1 : (WriteMode==1)`,
> 只在錄影初始化 C03A50F8 讀一次;SD 永遠聚合 64 MiB,SSD 只有 Custom 聚合、Standard 逐幀同步寫。
> 完整寫入路徑見 [WRITE_PATH_AFTER_BULK.md](WRITE_PATH_AFTER_BULK.md)。9/24 ledger 的 vtable 偏移錯 4 bytes。

2026-09-15。使用者在選單裡看到 SSD 寫入模式有兩檔,問它的作用。以下全部從
`out/MAIN_c0000000.bin` 靜態讀出。**它實際改變寫入行為的那段程式碼還沒讀到**,
見最後一節。

---

## 1. 完整命名鏈

```
選單          MENU → USB Storage → Write Mode → Standard / Custom
字串資源      id 1649 'USB Storage'   id 1650 'Write Mode'
              id 1651 'Standard'      id 1652 'Custom'
選單項目      MenuItemMediaWriteMode      0xC07430F8
處理器        MenuMediaWriteModenHandler  0xC0CD0668
GUI 變數      CM_MediaWriteMode           0xC0D1C0D4
              (另有 CM_MediaWriteModeAj / ...Fix)
相機參數      cam_is_bulk_write           0xC0BC8F88
```

**`Custom` = bulk write。** 參數名自己說了,而且值域是 `{0, 1}`。

## 2. 參數的後端

註冊在 `0xC041B584`,呼叫 `0xC0419C28(表, 名稱, 後端, ...)`:

```
設定物件基底   r4 = 0xC375953C
後端位址       r4 - 0x908 = 0xC3758C34
值域           {0, 1}
```

`setting get cam_is_bulk_write` 應該讀得到。⚠ **`setting set` 是鏡像**,
錄影開始會被刷掉(`cam_movie_imagesize` 就是這樣沒用的),要真的改用下面那條。

## 3. 從程式碼改:property call

`SetMediaWriteMode` 的 shell handler 在 `0xC03FFF68`,它做的是:

```
strtol(argv, 0, 10)        0xC01F5898
obj = 0xC0057AE8()         設定物件
0xC005F300(obj, value, 1)  ← property function
```

**所以 property function = `0xC005F300`**,呼叫慣例跟 `SetMovFramerate`
(`0xC005C0B8`)完全一樣 —— 就是 lachgil 在 overlay 那份文件裡用來從自己的
執行緒改設定的那條路,`analysis/menu_setters.json` 的一列。

## 4. ★ 順帶挖到:CinemaDNG writer 自帶效能記錄器

追 bulk 字串時撞到的,**比這個開關本身更有用**。

`src/framework/recMgr/src/CinemaDngFile.cpp`,程式碼約 `0xC03A4D80..0xC03A5900`:

```
0xC0B9E653  'request  ,finish   ,diff,gap ,reqcnt,fincnt,diff,sdb,MB/s'
0xC0B9E693  '%9u,%9u,%4u,%4u,%6u,%6u,%4u,%3u,%4u'
0xC0B9E613  'file-size=%u, bulk-size=%u(%.1f)'
0xC0B9E637  'req_cnt=%u, fin_cnt=%u%s'
0xC0B9E6C3  '\\cine_log.txt'
```

統計區塊在 `0xC359xxxx`,印出點 `0xC03A56C0`:

```
+0x00  req_cnt      +0x04  file-size
+0x30  bulk-size    +0x38  fin_cnt      +0x34/+0x3C  時間戳
```

**相機自己在量每次寫入的 request/finish 時間、間隔、請求與完成的差、以及 MB/s,
並寫成 CSV。** 這正是 `fpSup/projects/6k-to-ssd.md` 卡住的三個問題所需要的儀器:

- 錄影當下的真實持續速率(不是 benchmark)
- `req_cnt − fin_cnt` 就是 backlog —— **掉幀前的預警**
- 雙媒體到底加不加得起來

比自己掛 hook 量準,而且不碰錄影路徑。`0xC03A56C0` 的 log 在
`ldr r0,[r4,#4]; cmp r0,#0; beq` 之後才跑,**啟用條件還沒查**。

## 5. 還沒讀到的:它到底改了什麼

**目前只能說「Custom = bulk write」,不能說 bulk write 做什麼。** 沒有在 writer
裡找到讀那個旗標、據以改變寫入行為的分支。

**合理猜測(未證實)**:`file-size` 對 `bulk-size` 這組 log 欄位暗示 Standard 是
每幀一次寫入、Custom 是累積到 `bulk-size` 再一次送出。區塊大小本來就是我們量到
SD 94 MB/s / SSD 390 MB/s 的關鍵變因(見 `STORAGE_SPEED.md`),所以這個開關**可能
直接影響持續寫入速率**。但這是猜的。

要定案的兩條路:

1. **靜態**:把 `0xC03A4D80..0xC03A5900` 讀完,找旗標分支與 `cine_log.txt` 的啟用條件。
2. **上機**:`setting get cam_is_bulk_write` 看現值,兩個模式各錄一段量速率,
   並找卡上有沒有 `cine_log.txt`。

相關:[[STORAGE_SPEED.md]]、`fpSup/projects/6k-to-ssd.md`。
