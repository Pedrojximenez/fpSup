# 螢幕常態標示（持久 OSD marker）— 為何失敗 + 正解配方

> 2026-08-24 從上個 session transcript 補記。目標：把「開機雙閃 colorbar」換成螢幕左上角**持久**標記（shell ready 提示）。

## 實機結果：全部失敗（已證）
| 嘗試 | 結果 |
|---|---|
| AutoRun 裡 `display osd 1 <color>` + `display text fpSup!`（`AutoRun.osd-marker.txt`, SHA `1b465155`） | **沒顯示**。卡上檔名被相機改成 `AutoRun_.txt` → 證明它**有執行**，只是畫不出來 |
| `shl` live 下 `display osd` / `display text` | 命令都 **OK**（`display osd` 回 `addr 0xc6754200 (1024,0682)`、`display text` 回 `output fpSup! / ok`），螢幕**完全沒東西** |
| `display peaking 1` | 「好像有閃一下」= 畫出來了但立刻被洗掉 |
| 11Hz 連刷 osd+text 3 秒（32 次） | **啥都沒有** |
| `led N 1` | ⚠️ **真的會點燈** —— 點亮了**錄影燈 + SD 燈**（會誤導使用者）。用 `led N 0` + `led mode normal` 復原。`led` 正式語法是 `led mode <name>`（normal / charging …） |
| `ctrl target` | **不存在**（`display` 無參數回的 usage "first of all, set ctrl targ..." 是誤導） |

## 真因（agent RE 確認 [C]）
`display osd`/`display text` **targeting 是對的**（就是 LCD 合成的那個 OSD layer），錯的是**時機**：
相機的 draw thread 擁有那些 layer 物件，**每個 redraw cycle 開頭先 clear 再重畫** → 把我們 out-of-band 畫的東西整個洗掉。
證據：`FUN_c0528700` → `FUN_c0528b40`（`blk_c05.c:28606`）在每輪開頭呼叫 `layer->fill()`（vtable+0x20，參數 0 / 0xf000f000 / 0xffffffff）。
（`display peaking` 的一閃是 `XC_OnceDrawingObserver` @`0xC0527870` —— 畫一次就自動移除。）

## 正解 ★ 註冊我們自己的 DrawingObserver（不用改 code）
```
FUN_c0528300(0xC3783020, group, observerObj)      @ 0xC0528300   （unregister: FUN_c05283D8）
```
`observerObj` 放在 worker RAM，vtable：
- `+0x0c` = 我們的繪製 stub（每個 cycle 被呼叫，`r1` = live buffer descriptor）
- `+0x10 / +0x14 / +0x18` = no-op
- `+0x1c` = **return 0** ← 這樣才不會被自動移除（跟 OnceDrawingObserver 的差別）

如此標記成為相機**每幀自己重畫的一部分** → 持久、合成正確、零 code patch。

## 繪製細節
buffer descriptor（`getBuffer` = vtable+0x10 = `FUN_c0721328`）：
- `base = *(u32*)(desc + 4)`（線性 framebuffer，活的；**先 guard `base != 0`**）
- `dims = *(u32*)(desc + 8)` → `W = dims[0]`, `H = dims[1]`
- `fmt = *(u32*)(layer + 0x1c)`，layer = `*(u32*)(0xC3783078 + group*8)`：**0 = ARGB8888**（stride W*4，色 `0xAARRGGBB`）、1 = RGB565（W*2）

最小保證可見 = **直接填一塊實心矩形**（純寫記憶體，不呼叫韌體 → 無 reentrancy）：
```c
stride = W*4;
for (y=y0; y<y0+h; y++)
  for (x=x0; x<x0+w; x++)
    *(u32*)(base + y*stride + x*4) = 0xFF00FF00;   // 不透明綠
```
挑相機 OSD 空著的角落（例 x0=24, y0=24, w=40, h=40）。cache-clean（`FUN_c000e91c` @`0xC0528954`）+ compositor swap（opcode `0x800`，`FUN_c001a0d8`）由相機自己在同一函式後段做，我們不用管。
（文字要用 `FUN_c052b348`，程式碼多、在 draw task 裡耗時多 —— **先做矩形**。）

## 備案：code hook（比較簡單注入，但要改 code）
- **hook EA = `0xC052884C`**（`getBuffer` 之後，`r0` = 當前 group 的 live buffer descriptor）
- 被位移的 2 條指令（8 bytes，剛好放 `LDR PC,[PC,#-4]` veneer）：
  ```
  0xC052884C:  00 30 a0 e1   mov r3, r0
  0xC0528850:  20 30 8d e5   str r3, [sp, #0x20]
  ```
- trampoline 必須保 `r0-r5, fp, lr`（`r4`=DrawController、`r5`=group index、`fp`=layer 都是活的）
- 在 observer loop **之前**蓋 → 相機 observer 會蓋過重疊區 → 標記放空角落；或 hook `0xC05288A4`（`blx r3`，bytes `33 ff 2f e1`）做「畫在最上層」版。

## 安全性
`FUN_c0528700` **只有一個 caller**（`DrawThread__v1` @`0xC0528F28`，`blk_c05.c:28898`）→ 純顯示 task，不碰影像/錄影/USB。純 RAM（reboot 復原）、無新 task、無 lock、無配置。

## Quick-ref
- DrawThread `0xC0528F28`（threadObj+0x14 event flag、redraw bit `0x4`、wait pattern `0x207`、`FUN_c036d818`）
- 每幀 draw-all `FUN_c0528700` @`0xC0528700`；getBuffer 呼叫點 `0xC0528848`；observer-draw `blx` `0xC05288A4`；cache-clean `0xC0528954`
- DrawController **`0xC3783020`**；live layer array **`0xC3783078`**（4×8B）
- `getBuffer` `0xC0721328`、`pixelsToBytes` `0xC0721638`、`fill` `0xC0721480`

## 現況
卡上是**穩定版雙閃** `AutoRun.recsafe-original.txt`（SHA `ad46de3d`，6 行 colorbar）。osd-marker 版已從卡上清掉（保留在 repo，`AutoRun.osd-marker.txt`，未 commit）。
