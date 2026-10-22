# 錄影幾何位址 + 機內鏡頭程式 (2026-08-25, USB shell 實機驗證)

> **2026-09-30 更正入口：** 下方 §1 是早期觀測，不再作錄影幾何來源的結論。
> `0xC37CE210` 曾在有效 DNG 錄影時全為 0，只是下游快取；見
> [CANVAS_IS_NOT_THE_SETTINGS_BLOCK §13](CANVAS_IS_NOT_THE_SETTINGS_BLOCK.md#13-重開機之後位址穩定性以及-0xc37ce210-也出局)。
> 畫布因果驗證見 [CANVAS_MOVED_AT_C043A19C](CANVAS_MOVED_AT_C043A19C.md)。

全部在 USB shell 上驗過才會進 AutoRun —— 換卡開機錄影的迴圈太慢,而且失敗
只看得到「沒有檔案」或凍結。

## 1. ★ 錄影幾何:`0xC37CE210`

```
0xC37CE210 = 1936        寬
0xC37CE214 = 1090        高
0xC37CE218 = 3244544     每幀位元組
```

`3244544` 正是卡上每個 CinemaDNG 的實際檔案大小 —— **這就是錄影幾何,不是猜的**。
相機沒在錄影時就讀得到(是模式設定值,不是每幀值),隨時可讀。

找法:掃活記憶體找 1936 與 1090 相鄰。全 8 MB 只有兩處相鄰,另一處
`0xC3634D28` 是 H,W 反序。

附近還有:
```
0xC37CE1C8 = 2088960 = 1920x1088   0xC37CE1CC = 1920   0xC37CE1D0 = 1080
```
顯示/代理幾何。

**這解掉了 lens profile 缺的「實際解析度」。**

## 2. 機內鏡頭程式 `projects/gyro-sup/fpshell-era/lens_program_shell.S`

一次跑完:建資料夾 → 讀鏡頭 → 解析 → 用鏡頭名當檔名寫檔。實測 0.68 s。

```
mkdir=1  ok(0x2d)=1  ok(0x0a)=1
焦距 40.0 mm   最近對焦 300 mm
路徑 \LENS\LUMIX S 40_F2.TXT
```

### mkdir API(從 shell 的 `mkdir` handler `0xC03E2D00` 反推)
```
r1 = FUN_c0407e20()          取 handle
FUN_c0366918(obj, r1)        ctor   —— obj 只有 4 bytes
FUN_c03669c0(obj, path, 0)   mkdir  —— 已存在時回 0,新建回 1
FUN_c0366940(obj, 2)         dtor
```
跟檔案 API 同一個 `0xC036xxxx` 家族。

### ★ 檔案 API 的 open 模式(實測,韌體自己用的值)
```
1     讀取                    (FUN_c03da510,韌體的 AutoRun 讀檔)
7     寫入,可覆寫已存在的檔案   ← 韌體最常用(x32)
6     寫入,可覆寫
0xF   寫入,可覆寫
0x402 寫入,但【檔案已存在就失敗】 ← 我們一直沿用的舊值,韌體自己從不用
3     開不了
```
`open` **回 0 是失敗、非 0 才是成功**(來源:`FUN_c03da510` 的 `cmp r0,#0` / `beq` 走錯誤路徑)。

**這是一個潛伏的 bug**:陀螺 hook 用 `0x402`,但它每段的檔名都不同,所以從沒撞到。
鏡頭程式每次開機寫同一個檔名 —— 第一次成功之後,**每一次都靜默失敗**,
卡上永遠是第一次的內容。已改用模式 7。

診斷過程本身值得記:我一度誤判成「0x402 可以覆寫」,因為模式測試迴圈的
**第一列跑在新檔上**,後面 7/6/0xF 才是跑在既有檔案上 —— 對照組沒對齊。

### 驗證迴圈:把檔案讀回來
`camera/file_read_shell.S`(open 模式 1 + `FUN_c0366060(obj, buf, len, 0)`)。
先用一定存在的 `\AutoRun.txt` 自證讀取路徑,再讀目標檔。
**不看回讀就不算寫成功** —— `write` 的返回值在失敗時也是 0,分不出來。

### block 0x0a 的欄位(兩次讀取交叉比對定出常數欄)
big-endian u16:
```
+4   0x0190 = 400  → 焦距 40.0 mm   (兩次都一樣)
+12  0x012c = 300  → 最近對焦 0.30 m (兩次都一樣)
+8, +18, ...       → 隨對焦環變動
```
變焦鏡的 +4 會即時反映當前焦段。

### 檔名要消毒
`LUMIX S 40/F2` 帶斜線(路徑分隔符)。規則:保留 `0-9 A-Z a-z _ - 空白`,
其餘換 `_`,再裁掉尾隨空白(區塊是 59 bytes 空白填充的)。
→ `LUMIX S 40_F2.TXT`

## 3. 任務建立 ABI —— 實機驗證,順帶修掉 stage6 的凍結

```
id=125   start=0   entry='WORK'   heartbeat 3 秒 +269
```

`codex/stage6_gyro_double_buffer_hook.S` 有**兩個各自都會致命**的錯,都是靜態可見的:

1. 用 `0xC01F885C`/`0xC01F8D90` —— 那是 **Cyc-thread** 的 create/start,
   wrapper 永遠傳固定 trampoline 當進入點。給它直接進入點會在 start 時損毀。
   probe A/A2 就是這樣**凍結、讀不回來**。正確的是主線 `tk_cre_tsk 0xC0016A58`
   + `tk_sta_tsk 0xC0016BC0`。
2. 把 ASCII 名稱 `"S6GF"` 寫進 descriptor+16,而那是 **stksz**。
   `cre_tsk` 不檢查 stksz 還是回傳合法 id,要等 `sta_tsk` 才炸,
   而且會污染共用堆疊池 `0xC301EAE4`,毒害之後所有任務建立。

stage6 是 2026-08-18 寫的,task ABI 是 08-19 才破解 —— 兩者從來沒對上,
而 stage6 從未實機跑過。**已修正為與 probe A5 逐欄相同。**

descriptor:`+0 exinf, +4 tskatr=0x41, +8 entry, +12 itskpri=28, +16 stksz=0x2000, +20 dsname[8]`

## 4. ~~未解~~ 已解:是 106,捲簾 10.556 ms

> ✅ **2026-09-10 解決,而且不需要找「模式索引欄位」。**
> picker 的三張表(`0xC0BE5810` / `0xC0BE59B0` / `0xC0BE5B50`,26 筆 ×16 bytes,
> `+0x08` 是模式)是 (讀出幾何 × 幀率) 的排列,**FHD 29.97 那一格填的是 106**;
> **mode 111 根本沒出現在 picker 的任何一張表裡**。實錄後 `0xC343B590` 也讀回 106。
>
> 所以 FHD 29.97 CinemaDNG 的捲簾是 **10.556 ms**。下面那段「時序沒被複製進 DRAM」
> 的結論仍然成立(時序表在 ROM 區 `0xC0B59500`,設模式時直接讀),
> 但它不再擋著任何東西 —— 而且那張表**實機上直接 `mem set` 就寫得進去**。
> 見 `FRAME_RATE_IS_VMAX.md`。

原始記錄:


```
mode 106   hmax 445  vmax 5398  → 10.556 ms
mode 111   hmax 330  vmax 7280  →  7.828 ms
```
兩者同解析度、同幀率、同位元深度,只有時序不同。掃過但都沒有:
- `vmax` 5398 / 7280 的 u32 形式
- ROM 表裡的打包 u32(`0x02DF01BD` / `0x00041516` / `0x014A014A` / `0x00041C70`)
- 指向 ROM 記錄的指標(timing / geometry / mode rec,兩個 index 各三個位址)

→ 時序既沒被複製進 DRAM 也沒被指向。下一條路是感光元件的 `0x3021xxxx` shadow bank。

**注意**:焦距不受此影響,只有捲簾未定。

## 相關
- `notes/projects/usb-shell-sup/../../usb-shell-sup/notes/SHELL_MEM_RANGE_LIMITS.md` —— 這輪一半的時間花在被靜默失敗誤導上
- `notes/research/rtos/../../../research/rtos/notes/TASK_PRIORITY_MAP.md` / `notes/research/rtos/../../../research/rtos/notes/TASK_ABI_VERIFIED.md`
- `notes/projects/gyro-sup/../../gyro-sup/notes/ONCAMERA_GCSV_AND_LENS_PROFILE.md`
