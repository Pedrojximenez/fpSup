<p align="center">
  <img src="fpSup/assets/fpsup-logo.png" width="180" alt="fpSup">
</p>

<h3 align="center">SIGMA fp 韌體 Ver.5.02 的研究與開發指南</h3>

<p align="center">
  fp L 的韌體高度相似,也可以參考;<br>
  但記憶體位址不同,這裡的卡和程式<b>不能直接用在 fp L 或其他韌體版本</b>。<br>
  其他相機的開發者,或許也可以參考<a href="JOURNEY.zh-TW.md">開發故事與經驗</a>。
</p>

<p align="center">
  <a href="https://ijigen.github.io/fpSup/"><img src="https://img.shields.io/badge/fpSup-%E7%B6%B2%E7%AB%99-e0405e?style=flat" alt="fpSup 網站"></a>
  <a href="https://ijigen.github.io/fpSup/tools/card-composer/"><img src="https://img.shields.io/badge/fpSup--Merge-%E4%B8%8B%E8%BC%89%E6%95%B4%E5%BC%B5%E5%8D%A1-e8c400?style=flat" alt="fpSup-Merge"></a>
  <a href="https://discord.gg/XeFK5zNZpT"><img src="https://img.shields.io/badge/Discord-%E5%8A%A0%E5%85%A5-5865F2?style=flat&logo=discord&logoColor=white" alt="Discord"></a>
  <a href="https://www.youtube.com/@fp-sup"><img src="https://img.shields.io/badge/YouTube-%E4%BD%9C%E5%93%81%E5%B1%95%E7%A4%BA-FF0000?style=flat&logo=youtube&logoColor=white" alt="YouTube"></a>
  <a href="https://ko-fi.com/fpsup"><img src="https://img.shields.io/badge/Ko--fi-%E8%B4%8A%E5%8A%A9%E9%96%8B%E7%99%BC-FF5E5B?style=flat&logo=kofi&logoColor=white" alt="Ko-fi"></a>
</p>

<p align="center">
  <a href="README.md">EN</a> / <a href="README.zh-CN.md">中</a> / <b>繁</b>
</p>

> [!TIP]
> **迷路了嗎?** 這裡是給開發者的 repo。
> **要下載 fpSup → [fpSup 網站](https://ijigen.github.io/fpSup/)**(下載、安裝、每個工具的使用指南),
> 或直接用 **[fpSup-Merge](https://ijigen.github.io/fpSup/tools/card-composer/)** 選好工具、下載整張卡。
> 有問題、想回報、想聊天 → **[Discord](https://discord.gg/XeFK5zNZpT)**

---

## 🛠️ 這個 repo 怎麼幫你開發

<table>
<tr>
<td width="33%" valign="top">

### 🔌 USB Shell
讓電腦直接跟相機說話:讀寫記憶體、呼叫韌體函式、按鍵、截圖、高速傳檔。

**不用拔卡、不用一直按按鈕。**

</td>
<td width="33%" valign="top">

### 📚 研究筆記
韌體、感光元件、介面、儲存的事實都整理好了,**不用從零反編譯。**

想知道硬體極限 → [網站研究頁](https://ijigen.github.io/fpSup/research.html)的解說與模擬工具。

</td>
<td width="33%" valign="top">

### 🤖 AI Skills
給 AI 的操作手冊,讓**你的 AI** 會上機、建卡、改選單。

</td>
</tr>
</table>

**你描述想要的功能 → AI 讀筆記、用 USB 上機測 → 一起做出你自己的 sup。** [→ 開發指南](#-開發指南)

---

## 💭 理念

在 AI 輔助開發的過程中,我明白研究過程本身的價值。
所以我分享的不只是成果,還有一路累積下來的**知識、工具、方法和 AI Skills**。

> [!IMPORTANT]
> **但請把這些資料當作參考,而非真理。**
> 我的 AI 犯過很多錯,其中有些錯誤可能還留在我的研究筆記或 Skills 裡。
> 請小心別讓我的 AI 那些未經驗證的資訊污染了你的開發環境。

### 🌱 開發與協作

每個人都用自己覺得最舒服的姿勢開發 —— 包括我自己。
不需要每個人都做同一個專案,或遵守同一套規則只為了方便管理。

我認為時代變了:**專案之間互相理解、整合的成本,在 AI 時代大幅降低了。**
與其大家綁在一起、朝同一個目標前進,
或許讓每個人放開手腳,由 AI 吸收掉互相理解的成本,會更好。
即使做了相同的研究,也可能發現不同的細節。
我不確定,但我覺得這種交互成長,可能會走得更遠。

我鼓勵自願分享、互相學習,但每個人有權利決定要分享多少。

- 🐛 **歡迎用 PR 來修正錯誤、修 bug 和改進。**
- 🌟 至於新功能和獨立的 Sup 模組,我一般鼓勵開發者自己維護自己的專案。
- 🧩 經作者同意,我可能會把他的作品收進 **fpSup-Merge**,而且一定會註明出處。

**每個開發者都值得擁有自己發光的舞台。**
我的目的不是把每個人的作品都收到我名下,而是讓更多人發現、享受別人創造的東西。

### 🤝 人與人的連結

我不知道 fpSup 還能有意義多久。

AI 進步得這麼快,也許幾年後,這些研究很多都會顯得微不足道。
人們也許只要跟自己的 AI 聊一聊,就能解決這些問題。
那也完全沒關係。

因為在這一路上,我發現對我來說,重要的不只是技術本身。
那些實驗、失敗、發現,尤其是因為這個專案認識的人,都變成了很珍貴的東西。
就算技術終究會過時,這些經歷和連結都會留在我心裡。

**我想創造人與人之間的連結。因此成立了社群 👉 [Discord](https://discord.gg/XeFK5zNZpT)**

**— bei / 夏曉雨 / ijigen ❤️**(這些都是我,只是用不同的名字 😆)

---

## 🔓 開發過程:當初我如何找到修改的入口

#### 🎥 起點

我常常一個人拍,自己既是攝影師也是被攝者,所以很需要可靠的自動對焦。
超焦距、PDMOVIE Live Air、DJI Focus Pro 都試過,沒有一個讓我滿意。

於是我用下班時間做了 [sigma-fp-bridge](https://github.com/ijigen/sigma-fp-bridge):用 PTP 控制對焦、做人臉偵測、預測對焦距離。
幾乎每晚熬夜測,AI 還會用語音指揮我站到哪裡,好拿我做測試。

#### 💀 死路

就在我以為快要成功的時候,第一次真正拿去拍,按下錄影鍵 ——

> ### 錄影中 PTP 對焦完全停了。

測了那麼久,我從來沒想過要測錄影中能不能用。我覺得自己是世界上最大的白痴。😱

#### 🔍 拆開韌體

我不甘心,深信 SIGMA 的工程師一定留了隱藏的指令,於是讓 AI 把韌體拆開、反編譯。
PTP 確定是死路,但也順便找到了雲台介面、工廠測試點,還有一個叫 `AutoRun.txt` 的東西。

AI 一直覺得它沒什麼,只是個簡單的腳本語言。
直到我注意到 shell 指令裡有 **`mem set`**,可以寫任意記憶體位址 —— 憑過去對逆向工程的了解,我直覺撿到寶了。

> ### 🗝️ 這就是入口。

#### 🌀 做一個夠大的

我做了幾個小玩具貼到社團,幾乎沒有人理。大家還沒意識到,這個發現已經證明一切都可以改變。
於是我花了一個多月,熬掉無數個夜,做出了 **fpSup-GYRO**,並公開了過程中的開發工具。

而就在我即將拿下 Open Gate 的時候,國外開發者 Vitaly Li 率先發布了成功的消息。

> 我一直知道,也許換台相機、甚至用手機就好了。
> 但我真的很愛 fp 的設計,所以就固執地黏上了。😅

我想這份對 fp 的愛,正是 fp 用戶即使非常小眾,卻如雨後春筍般誕生優秀作品的原因。

📖 **更完整的開發故事與經驗 → [JOURNEY.zh-TW.md](JOURNEY.zh-TW.md)**
或許能幫助你,尤其是想在其他相機上從零開始的人。

---

## 🧭 開發指南

> [!WARNING]
> 這個 repo 包含實驗性的韌體研究和非官方修改。
> 有些程式碼可能不完整、未經測試,甚至有潛在危險。使用它可能導致錄影失敗、資料遺失、設定出問題,甚至讓相機無法使用。
> **使用風險自負。**

### 💡 怎麼開始一個新功能

| | |
|:-:|---|
| **1️⃣ 想清楚需求** | 你想讓 fp 做到什麼?研究方向是從需求來的,不是從索引來的。 |
| **2️⃣ 看硬體極限** | 用[網站研究頁](https://ijigen.github.io/fpSup/research.html)判斷行不行得通:<br>・解析度、格率合不合理,資料率(MB/s)卡不卡得進儲存媒體<br>・硬體無損壓縮的能力和限制<br>・SIGMA 原本就有的感光元件模式能做到哪些事<br>・ISP 的流程:畫面從感光元件到 CinemaDNG 經過哪些關卡 |
| **3️⃣ 交給你的 AI** | 讓它讀 [`INDEX.md`](INDEX.md)、相關的 `projects/<名字>/` 和 `.claude/skills/`,找出已經知道什麼、還缺什麼,再一起上機驗證。 |

### 🎒 準備

- 📷 SIGMA fp,**韌體 Ver.5.02**(fp L 可參考,但卡不能直接用)
- 🔌 一條 USB-C 線、一張 SD 卡
- 💻 Mac(USB Shell 的主機工具目前在 macOS 上開發)
- 🤖 一個能讀檔、跑指令的 AI 程式助手(Codex、Claude Code)

### 🚀 三步上手

| 步驟 | 做什麼 | 參考 |
|---|---|---|
| **1. 接上 USB Shell** | 用 fpSup-Merge 建一張帶 USB Shell 的卡 → 插上 USB → 主機工具就能讀寫記憶體、按鍵、截圖 | skill `fp-camera-control`、`fp-usb-shell` |
| **2. 讓你的 AI 接手** | 讓它先讀 `INDEX.md` 和 `.claude/skills/`。<br>⚠️ **這些是我的 AI 寫的,有錯。** 重要的結論請自己驗證。 | |
| **3. 做一個自己的 sup** | 建卡、測改動、發布 | `fpSup/BUILDING.md`、skill `fp-merged-card` |

### ⚠️ 上機前要知道的

- 完成自己的功能、上機測試前,先用模擬跑過再寫卡 → skill `fp-unicorn-emulation`
- 寫入相機設定區要小心:它會跨關機保存。過去的分析可參考 [`research/SETTINGS_AREA_FIRST_RULE.md`](research/SETTINGS_AREA_FIRST_RULE.md)(只是參考)。
- 相機卡死了:先讀卡(hook 寫的資料還在),再拔電池冷開機。

<details>
<summary><b>📁 這個 repo 怎麼分</b></summary>

```
README*.md      ← 你在這裡(EN / 中 / 繁)
JOURNEY*.md     ← 完整故事
INDEX.md        ← 研究總索引:從這裡找任何主題
research/       ← 相機本身的事實(韌體、感光元件、介面、儲存…),換個專案還成立
projects/       ← 各 sup 與實驗的開發樹:原始碼、測試卡、驗證紀錄、失敗紀錄
fpSup/          ← 網站、正式發布卡(releases/)、各 sup 的發布版原始碼、fpSup-Merge
.claude/skills/ ← AI 用的操作手冊(上機、呼叫韌體函式、建卡、改選單…)
```

</details>

<details>
<summary><b>📦 只想拉一部分?</b>(整個 repo 約 14 GB)</summary>

只要原始碼的話:

```sh
git clone --filter=blob:none --sparse https://github.com/ijigen/fpSup.git
cd fpSup && git sparse-checkout set fpSup .claude
```

</details>
