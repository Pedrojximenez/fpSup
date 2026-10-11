# 把第三方純 AutoRun 卡變成可合併的 payload —— 用分配器,不要佔 cave

2026-09-21。對象:lachgil 的 sigma-fp-lab False Color / EL Zone 卡(Ver.5.02
only)。卡片存檔 `../cards/fp-fc-scale-card/`。

| 檔案 | 做什麼 |
|---|---|
| `../fc_scale_pool_card.py` | **正解**:payload 跟分配器要記憶體,cave 只留 188 B 錨點 |
| `../fc_pool_entry.S` | 那張卡的 entry:配置 → 複製 → 填 trampoline → 發佈 → 武裝 hook → 再發佈 |
| `../test_fc_pool_card.py` | 用 unicorn 跑 entry,檢查結果與**順序** |
| `../fc_scale_to_vbin.py` | 原卡逐字轉容器(參考/對照用,位址照原卡) |
| `../fc_scale_entry.S` | 上者用的 hook 表 entry |

## 為什麼原樣不能合

那張卡是**純 AutoRun**:七百多行 `mem set`,沒有容器、沒有 loader。fpSup-Merge
合併的是 payload 容器(`"VBIN"` + 段數 + entry + 每段 `(dest,len)`)。

卡片拆出來:狀態 144 B @`0xC072E200`、程式+資料 2,748 B @`0xC072E400`、三個 hook
字(`0xC03722E8`/`0xC0372330` 按鍵,`0xC02E8A08` **每幀**的 display submit),以及
借 `echo` handler 呼叫 `0xC000E91C` 讓快取發佈。

`fc_scale_to_vbin.py` 把它逐字轉成容器,726 字全同,但**位址原封不動**——於是跟
陀螺的 payload 正面重疊(`accel 0xC072E200`、`drain 0xC072E300`、`start 0xC072E4E0`、
`stop 0xC072E620`、`mode 0xC072E6A0`、`space 0xC072EC60`)。

## cave 沒有 3 KB 可搬(這條路是死的)

掃 stock MAIN(`out/MAIN_c0000000.bin`,sha256 `92a8ee99…`)的連續零:

```
0xC072DE64..0xC0732A40   19,420 B
0xC0732C84..0xC0734C84    8,192 B
往上不是零 —— 所以 0xC0735000 之類的位址他的 build 會直接擋掉
```

扣掉已經有主的:loader `0xC072DE64`+512、payload window ..`0xC072EFB4`(陀螺)、
park stub、shell 狀態/abort `0xC072F000..0xC072F118`、boot descriptor/交握
`0xC072F6D8`/`0xC072F6F8`、主機注入區 `0xC072F100..0xC0730000`
(`shl.py` 的 `INJ_LO/INJ_HI`,一次性模板 `0xC072F700`/`0xC072F800`)、
og3k/og2k `0xC0730700..0xC0732A14` 與 `0xC0732C84..0xC07343B8`。

**沒有一個縫塞得下 ~3 KB**,所以「搬到別的固定位址」只能換成跟別人撞:放 payload
window 就撞陀螺,放 `0xC0730000` 就撞開閘。試過、量過,兩個位址版本都做出來過,
然後丟掉了——因為問題不在位址。

## 正解:跟分配器要,cave 只留錨點

worker.S 跟陀螺的 profile generator 早就這樣做了:**要記憶體就跟分配器要**。
FC 改成一樣:

```
0xC072E080  狀態      144 B   他的程式碼用 movw/movt 指名,所以留在 cave
0xC072E110  trampoline 24 B   韌體 hook 點跳得到這裡;pool 在 48 MB 外而 b 只有 32
0xC072E128  descriptor 16 B   要活過 H_GET 那次呼叫
0xC072E138  pool 位址   4 B   發佈出去,主機工具找得到
                      = 188 B,全部在 0xC072E064..0xC072E200
```

`0xC072E064..0xC072E200` 是 payload window 的頭 412 B,**沒有任何出廠卡片用**
(陀螺第一段在 `0xC072E200`,開閘在 `0xC0730700`)。所以這張卡跟誰都不撞。

程式碼(2,924 B)放分配器給的 pool,class 0(USER,不是 10 RAW)。entry 跟 payload
放在**同一個 dest 0 段**裡,用 `adr` 找 payload —— 合併會重排檔案,任何「檔案內
偏移」的寫法都會被重排弄壞,pc 相對的不會。

**他的原始碼一行都不用改。** 那段程式碼本來就是位置無關的:60 個分支全在內部、
四個取址是 `ldr rX,[pc,#4]; add rX,pc,rX`、沒有字面值存 cave 位址;唯一的絕對
自我參照就是狀態基底,而狀態正好是留在 cave 的那塊。要動的只有他 builder 裡的
`STATE` 常數,那本來就是常數。

entry 的順序就是它存在的理由:

1. `H_GET`/`H_ADDR` 配置(拒絕就什麼都不武裝,相機保持原狀)
2. 複製 payload 進 pool
3. 填三個 trampoline 的目標字 = pool + 各 hook 的偏移
4. **發佈**(`0xC000E91C` + `0xC000EABC`)
5. 才武裝三個韌體 hook 點(各一個 `b` 指到自己的 trampoline)
6. 再發佈一次

武裝放最後是關鍵:display submit 每幀都跑,先武裝就是跳進 pool 上一輪的垃圾。
原卡靠 AutoRun 的行順序 + 借 `echo` 得到同樣的保證;容器沒有行順序(段照表放、
整趟結束才發佈一次),所以這件事必須由 entry 自己負責。

trampoline 是 `ldr pc, [pc, #-4]` + 目標字,8 B 一個。要它是因為 `b` 只到 ±32 MB,
而分配器給的區塊在 `0xC3xxxxxx`,離 hook 點約 48 MB。代價是每次呼叫多一次間接
載入,三個 hook 裡只有 submit 是高頻的。

## 驗證

`test_fc_pool_card.py`(unicorn,把檔案放暫存緩衝、cave 與三個 hook 點當記憶體、
分配器與兩個快取常式當 stub,記錄每一次寫入的順序):

```
分配器答應:
  entry 回 0(stage2 要求)                        ok
  2,924 B 逐位元組進了 pool                        ok
  pool 位址發佈在 0xC072E138                       ok
  H_GET(0xC072E128, class 0, 0xC00, 0) 一次        ok
  三個 trampoline 各指 pool+0x478/0x4E4/0x63C      ok
  三個 hook 點各指自己的 trampoline                ok
  pool 與 trampoline 都寫在任何 hook 武裝之前      ok
  中間有 D-cache clean + I-cache invalidate        ok
  hook 自己也在之後被發佈                          ok
相機跟著跳:
  三個 hook 點各兩跳落在 pool+偏移                 ok
分配器拒絕:
  回 0、三個 hook 點都沒被碰、trampoline 沒被指、
  什麼都沒被複製                                   ok
```

fpSup-Merge 自己的檢查(抽出 `compose` block 用 node 跑,現在九項):

| 組合 | 結果 | 容器 |
|---|---|---|
| FC | 9/9 | 3,716 B |
| FC + shell | 9/9 | 5,844 |
| FC + gyro | 9/9 | 16,616 |
| FC + gyro + shell | 9/9 | 18,656 |
| FC + og3k | 9/9 | 17,100 |
| FC + og2k | 9/9 | 18,204 |
| FC + gyro + og3k | 9/9 | 30,000 |
| FC + gyro + shell + og3k | 9/9 | 32,040 |
| FC + gyro + shell + og2k | 9/9 | 33,144(padding 改成 61,440) |

**位址衝突全沒了,檔案大小也不是問題了。**

## 順手修掉的 composer:padding 不是上限

`composeVshl` 本來固定配 `CAT.pad_to`(32,768)的陣列,選到超過就寫出界**丟
例外** —— 而一個例外會把整頁的 render 帶走,包括那個本來要說「放不下」的檢查。
找出它的組合就是 FC+gyro+shell+og2k(33,144,超 376 B)。

但更根本的是:**32,768 從來不是上限,是 padding**。它存在的理由是 `putfile` 走
USB 寫檔不能縮短檔案,所以固定長度才不會留下上一版的尾巴
(`build_autorun.py` 的 `BIN_PAD` 註解)。真正的上限是 loader 讀得進多少:
`loader.S` 的 `MAXLEN = 0xF000` = **61,440**(= `CAT.read_cap`)。

所以改成兩段:放得下 32,768 就照舊 padding 到 32,768(每一個原本能組的選擇
**逐位元組不變**),放不下就 padding 到 read cap。四個產品加一個上傳的 payload
到 33 KB,對相機來說不是問題。原本那個「fpSup.BIN fits」的檢查在這之後永遠不會
失敗,所以拿掉,把 padding 併進「The loader can read the whole card」的說明裡。

`template.html` 改、`build_catalogue.py` 重新產頁,五個組合的自我驗證照舊
(兩個 STALE 是本來就有的那兩個)。

### loader 的暫存為什麼不照 bin 大小宣告

不是讀不下,是它**不去問**:loader 固定跟分配器要 64 KiB(`POOL_BYTES 0x10000`)、
最多讀 `MAXLEN` 進去,不 stat([[firmware-file-read-idiom]] 的慣用法)。理由是
loader 的硬約束不是記憶體而是**它自己的長度**:fast start 要把它整份塞進
`XC_CommonSaveData` 的 `STORE_MAX` = **468 bytes**,而 loader.S 現在正好 468。
要照檔案大小配置就得先知道大小 —— stat,或先讀 16 B 標頭算
`16 + 8*count + bodyLen` 再配置再重讀 —— 那是多一次讀加十幾個字,468 裡沒有。

真要做也做得到(標頭 +0x0C 就是 payload 長度),但今天最大的組合 33 KB,離
61,440 還很遠;真的撞到那條線,最便宜的一步是把 `POOL_BYTES`/`MAXLEN` 調大,
而不是加 stat。

## 用法

```sh
git clone https://github.com/lachgil/sigma-fp-lab            # 到暫存區
ln -s .../out/MAIN_c0000000.bin  sigma-fp-lab/analysis/
mkdir -p sigma-fp-lab/reference/fpSup
ln -s .../fpSup/fp_usb_shell     sigma-fp-lab/reference/fpSup/

./projects/fc-scale/fc_scale_pool_card.py --lab-repo sigma-fp-lab --out DIR
./projects/fc-scale/test_fc_pool_card.py  --lab-repo sigma-fp-lab
```

他的 builder 要 `analysis/MAIN_c0000000.bin`,sha256 **正好等於**我們
`out/MAIN_c0000000.bin`;`armasm.py` 也有他 import 的 `assemble` 與 `symbols`。
用的是 commit `40ae9981`(2026-09-21),`src/fcscale.S` sha256 `cbc411d7ad3d…`。

產出 `fpSup.BIN` 丟進 `fpSup/tools/card-composer/index.html` 的 drop zone(先展開
"Show the technical detail"),勾產品,下載的 `AutoRun.txt` + `fpSup.BIN` 就是合併
卡。**上傳會重畫並清掉勾選**,上傳完再勾一次、讀回來確認。

兩個成品在 `~/Downloads/fp-fc-scale-vbin/`:`allocator/`(正解)與 `as-is/`(原卡
逐字轉檔,只能跟 shell/開閘合,留著當對照)。

## 沒做的事

- **沒上相機。** 以上是靜態檢查 + unicorn:分配器會不會給可執行的記憶體、
  `0xC000E91C` 是不是真的發佈、畫面畫不畫得出來,都還沒驗。第一次先只勾 FC
  開機看畫面,再往上疊。
- 沒加進 catalogue 當內建產品。它不是 fpSup 的發行物,走 upload 這條路才對。
- 沒改 `PAD_TO` / `BIN_PAD` 的**值**,也沒動 `build_autorun.py`:改的只有頁面
  「放不下 32,768 就 padding 到 read cap」這個行為,放得下的卡逐位元組不變。
- 行為跟你下載那張卡不同:他 repo HEAD 是「按一下開/關、按住半秒切刻度」,
  卡片是「按 1/2/3 下」。`allocator/` 是 HEAD。
- 這張卡帶 dest 0 的段,所以頁面會選 task loader 那個 AutoRun(`task + state +
  iface`)。**陀螺卡本來就是這樣**(`carriesWorker(gyro) = true`),不是新行為。
