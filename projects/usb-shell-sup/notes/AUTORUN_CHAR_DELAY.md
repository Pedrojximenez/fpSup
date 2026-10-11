# AutoRun 逐字延遲:開機 11.5 s → 3.0 s

> **2026-10-11 v3 差異**：目前 `worker.S:spawn` 與 loader 都會返回，下面「交棒後不執行、補白不計入時間」是舊入口的歷史結果，不能套用目前卡。逐字延遲已在交棒前恢復，後面的約 29 KB 可見字元補白會繼續被讀；實機約 61.85 s 仍有 AutoRun 註冊。完成動畫 2 秒已取消，收尾仍待修正。詳見 [現行實機證據](../../res-lab/validation/20261011-boot-speed/RESULTS.md)。

2026-10-04。相機 Ver.5.02,Sensor Lab fast-debug 卡(r70 BIN,Fast Start 2 的 fast 路徑),
儀器 `LOAD_DONE_US`(`0xC072F6F8`)。起因是網友回報(下方),使用者要求實測。

---

## 0. 一句話

**原廠 shell 讀 AutoRun 時,每個可見字元(0x20–0x7E)後面都睡一下,註解也算。**
實測每字元約 1.9 ms。拿掉註解省一半,把那一下 NOP 掉再省一半。
[BOOT_TIMING.md](BOOT_TIMING.md) 說的「相機自己開機約 8.9 s,完全不歸我們管」**大部分其實是這個**。

| 組 | AutoRun | `LOAD_DONE_US`(三次) |
|---|---|---|
| A | 原本(含註解) | 11.42 / 11.52 s |
| B | 只拿掉 `#` 註解,指令逐字相同 | 5.67 / 5.75 / 5.75 s |
| C4 | B + 開頭 NOP 延遲、交棒前寫回原廠 | **3.01 / 3.06 / 3.13 s** |

三組 `fpSup.BIN` 相同(SHA `a7851c2e…`),只差 AutoRun。都不寫設定區。

---

## 1. 機制(反編譯 `out/decomp/full/blk_c04.c`,行編輯器)

```c
else if ((0x1f < c) && (c < 0x7f) && (len < max)) {   // 可見字元
    ... param_2[pos] = c;
    FUN_c0421770(1);                                    // 0xC04215F4: bl 0xC0421770
    echo(...);
}
```

`FUN_c0421770(n)`:旗標(`[FUN_c04217b0()+0x28]`)為 0 → `FUN_c03705d8(n)`(task sleep),
否則忙等 `n*1000` µs。實測 ~1.9 ms/字,比網友說的 1 ms 長 —— 大概是 sleep 進位到下一個 tick。

- 換行、控制字元不睡;超過行長上限的字元直接丟掉、也不睡。
- `//` 開頭的行是原廠的註解語法;`#` 開頭的行對 shell 只是一條不認得的指令 —— 字元照樣逐字睡。

**網友那行寫反了**:`0xC04215F4` 上原廠就是 `0xEB00005D`。拿掉延遲是寫 NOP `0xE320F000`,
`0xEB00005D` 是還原。

> 網友原文:「every character read has a 1ms delay, so 1. remove comments from the autorun,
> and 2. remove the delay using mem set 0xC04215F4 0xEB00005D … i restore it after the last
> command … reduced the time from like 13 seconds to 2.」

---

## 2. ★ 交棒之後的指令不會執行

第一次把還原放在 AutoRun 最後一行 → 三次開機都還是 NOP。寫三次 → 一樣。
放在 loader 交棒(`mem set 0xC0BAC2F8 0xC072DE64` + `echo`)之前 → **還是一樣**。

原因:**第一次把 echo 交給 cave 的程式碼**(fast 路徑是 store bootstrap
`mem set 0xC0BAC2F8 0xC072F700`,slow 路徑是 loader `0xC072DE64`)之後,它變成 USB shell
的 worker、不再回來,AutoRun 就停在那一行。產生器在那之後寫的
`mem set 0xC0528700 …` / echo 還原三連等,**在 shell 卡上從來沒跑過**,只是 loader 自己也做了同樣的還原,
所以一直沒人發現。

→ **一定要跑的指令放在第一次交棒之前。** `--fast-echo` 的還原就是這樣放的(C4),
三次開機讀回都是 `0xEB00005D`。

同一份 AutoRun 裡 105 條 `mem set`(含整段 loader 程式碼)在 NOP 之下逐字讀回比對,
**0 個漏掉** —— 這次沒有證據顯示延遲是防丟字用的。不過產生器原本就記錄過「`mem set` 會漏指令」,
所以必須生效的寫入仍然寫三次。

---

## 3. 產生器

`fpSup/fp_usb_shell/build_autorun.py`:

- `--strip-comments`:拿掉所有 `#` 開頭的行。補白(檔尾的 `#`)照舊補到 32,768 B
  (putfile 不截短,見 `PAD_TO`);補白在交棒之後,不計入開機時間。
- `--fast-echo`:第一行 `mem set 0xC04215F4 0xE320F000`,第一次交棒前寫三次 `0xEB00005D`。

`projects/open-gate/build/build_res_lab_card.py --autorun-flag=--strip-comments --autorun-flag=--fast-echo`
轉傳。**2026-10-04 起兩個都預設開啟**(使用者決定套用到所有專案與 merge;`--no-strip-comments` / `--no-fast-echo` 關掉)。
同日 `--four-box-bar` 也改成所有 `--loader` 卡的預設(單卡統一用四格進度條;`--no-four-box-bar` 回舊文字顯示)。
合併頁的 Fast Start 2 更名 **Fast Start 3**,勾選時顯示對 Andy_hal9000 的致謝。

卡:`projects/res-lab/cards/20261004-b25-menu-r70-autorun{B,C,C2,C3,C4}/fast-debug`
(C/C2/C3 是還原沒生效的三版,留著當紀錄)。

## 4. 還沒做

- instant 路徑(不跑 AutoRun)不受影響;slow 路徑沒量。
- 其他產品卡與 composer 頁面已透過預設值套用(離線測試全過),**但只有 Sensor Lab fast 路徑上機量過**;一般(非 Fast)路徑與各產品卡未上機。
- `FUN_c03705d8` 的 tick 長度沒查;1.9 ms 是從 3,059 個字元省 5.8 s 反推的。

## 2026-10-11：移除尾端補白

第 3 節的 32 KiB 補白已停用。v3 Loader 返回後，AutoRun 還會繼續讀到真正 EOF；
尾端補白不能視為不會執行。共用 builder 與兩個 Merge 現在都輸出實際內容。
相機 AutoRun 已由 32,768 B 先刪後寫成 3,561 B，完整讀回相符；重啟後登記深度、
echo、DRAW 與字元延遲皆恢復原值。未捕捉精確結束時刻，不宣稱此輪總開機秒數。
詳見 [無補白驗證](../../res-lab/validation/20261011-no-padding/RESULTS.md)。
