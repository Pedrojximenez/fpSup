# 列目錄 API(Ver.5.02)

2026-10-06,從原生 shell 的 `dir` 指令反組譯(`out/MAIN_c0000000.bin`,capstone),**同日上機逐一呼叫驗證**(`../dir_enum_probe.py`)。
用途:Loader v3 的加載器列 `\fpSup\*.BIN`([LOADER_V3.md](../../../projects/usb-shell-sup/notes/LOADER_V3.md) §7)。

## 從哪找到的

shell 指令表是 24 B 一筆 `{ name[20], handler }`,77 筆,`echo` 在 `0xC0BAC2E4`(handler 槽就是我們借的 `0xC0BAC2F8`)。
`dir` 在 `0xC0BAC29C` → handler **`0xC03E2980`**(ARM)。

## API

holder 是 4 B(一個指標),放在呼叫端的堆疊或自己的塊裡。

| 函式 | 呼叫 | 回傳 |
|---|---|---|
| `0xC0366918` dir_ctor | `(holder*, drive)` | holder*;內部 `0xC0366888(drive)` 用 `new(0x10)` 建實體,vtable `0xC0B96FFC` |
| `0xC0366990` dir_open | `(holder*, const char *path)` | 非 0 = 成功 |
| `0xC03669F8` dir_next | `(holder*, entry*)` | 非 0 = 讀到一筆;0 = 沒了 |
| `0xC0366940` dir_dtor | `(holder*, 2)` | 刪掉內部實體(vtable+8, 參數 3);2 的 bit0 = 0 → 不釋放 holder 本身 |

- **drive**:`0xC0366888` 只接受 1、2、3、5,其他值會走斷言。`dir` 自己傳的是 `0xC0407E20()` = `[0xC2F20884]`(目前磁碟)。
  loader 的 `F_VOL` 慣例是 1 = SD、5 = SSD,值域吻合 → **加載器明確傳 1**,就不會跑去 SSD(推論,未上機)。
- **path**:char*,**第一個字元必須是 `\`**,否則直接失敗並記 log(`0xC0367B38`)。例:`"\\fpSup"`。
- open/next 自己會拿磁碟的 mutex(`0xC036B1E0` → `0xC0010298`/`0xC00102D0`),並檢查磁碟已掛載(`[vol+0x1C]`)。
- 呼叫 next 前,`dir` 先把 entry 清零(`memset 0xC0015058`, 0x238)。

## entry(0x238 B)

| 偏移 | 內容 |
|---|---|
| `+0x000` | 檔名,**UTF-16LE**、0 結尾(`0xC03E27B0` 逐個 u16 轉成 UTF-8 印出),最多約 0x108 個字元 → **支援長檔名** |
| `+0x210` | 大小,u64 |
| `+0x218` | 屬性 u8;`0x10` = 目錄 |
| `+0x21A..` | 建立/修改/存取的日期與時間(u16,`0xC03E2760`/`0xC03E2558` 格式化) |

## 對加載器的意義

- 回傳順序 = 目錄裡的順序(FAT 的寫入順序),**沒有排序** → 加載器要自己依檔名排序。
- 檔名比對用 u16,只認 ASCII 子集就夠;大小寫要自己決定規則。
- 檔案大小直接從 entry 拿,不必再 stat。
- 韌體裡另有 42 處呼叫 dir_ctor(例如 `0xC00D103C`、`0xC03097FC`、`0xC0409C04`),可以拿來當呼叫範例。

## 上機結果(2026-10-06,drive 1,shell 任務經 echo/callfn)

- `\`:8 筆,與原生 `dir \` 的內容與順序一致。`\FPSUPUI`:10 筆,順序 4,3,2,0,1 —— **確實未排序**。
- **子目錄沒有回傳 `.` 與 `..`**(韌體自己濾掉了)。
- 不存在的 `\fpSup`:open 回 0,乾淨失敗,dtor 照常;shell 正常。
- `+0x218` 就是 FAT 屬性:`0x10` 目錄、`0x20` 封存、`0x02` 隱藏。
- ⚠ **macOS 會在卡上留 `._xxx` AppleDouble 檔**(屬性 0x22、4096 B),例如 `._fpSup.BIN`。
  加載器列 `\fpSup\*.BIN` 時**必須跳過 `._` 開頭的檔名**(或屬性含 0x02),否則會把它當 sup 讀。
- 實體:vtable `0xC0B96FFC`、磁碟物件 `0xC351EE18`(= `0xC351ECB8+0x160`),與離線分析一致。

## 踩到的雷

第一次上機呼叫 `dir_ctor` shell 就卡死(冷開機恢復)。原因幾乎確定是 **`callfn.py` 寫參數不讀回**:
`mem set` 會靜默丟指令,P_FN 若被丟,echo 就跳到 0。已修 `fpSup/fp_usb_shell/callfn.py`(參數讀回比對才 arm、
echo 槽改用 `set_echo_handler` 讀回)。修完後同一個呼叫序列跑了 4 輪都正常。

## 未驗證

- drive 5(SSD)—— 這次沒接 SSD。
