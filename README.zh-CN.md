<p align="center">
  <img src="fpSup/assets/fpsup-logo.png" width="180" alt="fpSup">
</p>

<h3 align="center">SIGMA fp 固件 Ver.5.02 的研究与开发指南</h3>

<p align="center">
  fp L 的固件高度相似,也可以参考;<br>
  但内存地址不同,这里的卡和程序<b>不能直接用在 fp L 或其他固件版本</b>。
</p>

<p align="center">
  <a href="https://ijigen.github.io/fpSup/"><img src="https://img.shields.io/badge/fpSup-%E7%BD%91%E7%AB%99-e0405e?style=flat" alt="fpSup 网站"></a>
  <a href="https://ijigen.github.io/fpSup/tools/card-composer/"><img src="https://img.shields.io/badge/fpSup--Merge-%E4%B8%8B%E8%BD%BD%E6%95%B4%E5%BC%A0%E5%8D%A1-e8c400?style=flat" alt="fpSup-Merge"></a>
  <a href="https://discord.gg/XeFK5zNZpT"><img src="https://img.shields.io/badge/Discord-%E5%8A%A0%E5%85%A5-5865F2?style=flat&logo=discord&logoColor=white" alt="Discord"></a>
  <a href="https://www.youtube.com/@fp-sup"><img src="https://img.shields.io/badge/YouTube-%E4%BD%9C%E5%93%81%E5%B1%95%E7%A4%BA-FF0000?style=flat&logo=youtube&logoColor=white" alt="YouTube"></a>
  <a href="https://ko-fi.com/fpsup"><img src="https://img.shields.io/badge/Ko--fi-%E8%B5%9E%E5%8A%A9%E5%BC%80%E5%8F%91-FF5E5B?style=flat&logo=kofi&logoColor=white" alt="Ko-fi"></a>
</p>

<p align="center">
  <a href="README.md">English</a> · <b>简体中文</b> · <a href="README.zh-TW.md">繁體中文</a>
</p>

> [!TIP]
> **迷路了吗?** 这里是给开发者的 repo。
> **要下载 fpSup → [fpSup 网站](https://ijigen.github.io/fpSup/)**(下载、安装、每个工具的使用指南),
> 或直接用 **[fpSup-Merge](https://ijigen.github.io/fpSup/tools/card-composer/)** 选好工具、下载整张卡。
> 有问题、想反馈、想聊天 → **[Discord](https://discord.gg/XeFK5zNZpT)**

---

## 🛠️ 这个 repo 怎么帮你开发

<table>
<tr>
<td width="33%" valign="top">

### 🔌 USB Shell
让电脑直接跟相机对话:读写内存、调用固件函数、按键、截图、高速传文件。

**不用拔卡、不用一直按按钮。**

</td>
<td width="33%" valign="top">

### 📚 研究笔记
固件、传感器、接口、存储的事实都整理好了,**不用从零反编译。**

想知道硬件极限 → [网站研究页](https://ijigen.github.io/fpSup/research.html)的讲解与模拟工具。

</td>
<td width="33%" valign="top">

### 🤖 AI Skills
给 AI 的操作手册,让**你的 AI** 会上机、建卡、改菜单。

</td>
</tr>
</table>

**你描述想要的功能 → AI 读笔记、用 USB 上机测 → 一起做出你自己的 sup。** [→ 开发指南](#-开发指南)

---

## 💭 理念

在 AI 辅助开发的过程中,我明白了研究过程本身的价值。
所以我分享的不只是成果,还有一路积累下来的**知识、工具、方法和 AI Skills**。

> [!IMPORTANT]
> **但请把这些资料当作参考,而非真理。**
> 我的 AI 犯过很多错,其中有些错误可能还留在我的研究笔记或 Skills 里。
> 请小心别让我的 AI 那些未经验证的信息污染了你的开发环境。

### 🌱 开发与协作

每个人都用自己觉得最舒服的姿势开发 —— 包括我自己。
不需要每个人都做同一个项目,或遵守同一套规则只为了方便管理。

我认为时代变了:**项目之间互相理解、整合的成本,在 AI 时代大幅降低了。**
与其大家绑在一起、朝同一个目标前进,
或许让每个人放开手脚,由 AI 吸收掉互相理解的成本,会更好。
即使做了相同的研究,也可能发现不同的细节。
我不确定,但我觉得这种交互成长,可能会走得更远。

我鼓励自愿分享、互相学习,但每个人有权利决定要分享多少。

- 🐛 **欢迎用 PR 来修正错误、修 bug 和改进。**
- 🌟 至于新功能和独立的 Sup 模块,我一般鼓励开发者自己维护自己的项目。
- 🧩 经作者同意,我可能会把他的作品收进 **fpSup-Merge**,而且一定会注明出处。

**每个开发者都值得拥有自己发光的舞台。**
我的目的不是把每个人的作品都收到我名下,而是让更多人发现、享受别人创造的东西。

### 🤝 人与人的连接

我不知道 fpSup 还能有意义多久。

AI 进步得这么快,也许几年后,这些研究很多都会显得微不足道。
人们也许只要跟自己的 AI 聊一聊,就能解决这些问题。
那也完全没关系。

因为在这一路上,我发现对我来说,重要的不只是技术本身。
那些实验、失败、发现,尤其是因为这个项目认识的人,都变成了很珍贵的东西。
就算技术终究会过时,这些经历和连接都会留在我心里。

**我想创造人与人之间的连接。因此成立了社区 👉 [Discord](https://discord.gg/XeFK5zNZpT)**

**— bei / 夏晓雨 / ijigen ❤️**(这些都是我,只是用不同的名字 😆)

---

## 🔓 开发过程:当初我如何找到修改的入口

#### 🎥 起点

我常常一个人拍,自己既是摄影师也是被摄者,所以很需要可靠的自动对焦。
超焦距、PDMOVIE Live Air、DJI Focus Pro 都试过,没有一个让我满意。

于是我用下班时间做了 [sigma-fp-bridge](https://github.com/ijigen/sigma-fp-bridge):用 PTP 控制对焦、做人脸检测、预测对焦距离。
几乎每晚熬夜测,AI 还会用语音指挥我站到哪里,好拿我做测试。

#### 💀 死路

就在我以为快要成功的时候,第一次真正拿去拍,按下录像键 ——

> ### 录像中 PTP 对焦完全停了。

测了那么久,我从来没想过要测录像中能不能用。我觉得自己是世界上最大的白痴。😱

#### 🔍 拆开固件

我不甘心,深信 SIGMA 的工程师一定留了隐藏的指令,于是让 AI 把固件拆开、反编译。
PTP 确定是死路,但也顺便找到了云台接口、工厂测试点,还有一个叫 `AutoRun.txt` 的东西。

AI 一直觉得它没什么,只是个简单的脚本语言。
直到我注意到 shell 指令里有 **`mem set`**,可以写任意内存地址 —— 凭过去对逆向工程的了解,我直觉捡到宝了。

> ### 🗝️ 这就是入口。

#### 🌀 做一个够大的

我做了几个小玩具发到社群,几乎没有人理。大家还没意识到,这个发现已经证明一切都可以改变。
于是我花了一个多月,熬掉无数个夜,做出了 **fpSup-GYRO**,并公开了过程中的开发工具。

而就在我即将拿下 Open Gate 的时候,国外开发者 Vitaly Li 率先发布了成功的消息。

> 我一直知道,也许换台相机、甚至用手机就好了。
> 但我真的很爱 fp 的设计,所以就固执地粘上了。😅

我想这份对 fp 的爱,正是 fp 用户即使非常小众,却如雨后春笋般诞生优秀作品的原因。

📖 **更完整的开发故事与经验 → [JOURNEY.md](JOURNEY.md)**(目前是繁体中文)
或许能帮助你,尤其是想在其他相机上从零开始的人。

---

## 🧭 开发指南

> [!WARNING]
> 这个 repo 包含实验性的固件研究和非官方修改。
> 有些代码可能不完整、未经测试,甚至有潜在危险。使用它可能导致录像失败、数据丢失、设置出问题,甚至让相机无法使用。
> **使用风险自负。**

### 💡 怎么开始一个新功能

| | |
|:-:|---|
| **1️⃣ 想清楚需求** | 你想让 fp 做到什么?研究方向是从需求来的,不是从索引来的。 |
| **2️⃣ 看硬件极限** | 用[网站研究页](https://ijigen.github.io/fpSup/research.html)判断行不行得通:<br>・分辨率、帧率合不合理,数据率(MB/s)能不能塞进存储介质<br>・硬件无损压缩的能力和限制<br>・SIGMA 原本就有的传感器模式能做到哪些事<br>・ISP 的流程:画面从传感器到 CinemaDNG 经过哪些关卡 |
| **3️⃣ 交给你的 AI** | 让它读 [`INDEX.md`](INDEX.md)、相关的 `projects/<名字>/` 和 `.claude/skills/`,找出已经知道什么、还缺什么,再一起上机验证。 |

### 🎒 准备

- 📷 SIGMA fp,**固件 Ver.5.02**(fp L 可参考,但卡不能直接用)
- 🔌 一条 USB-C 线、一张 SD 卡
- 💻 Mac(USB Shell 的主机工具目前在 macOS 上开发)
- 🤖 一个能读文件、跑命令的 AI 编程助手(Codex、Claude Code)

### 🚀 三步上手

| 步骤 | 做什么 | 参考 |
|---|---|---|
| **1. 接上 USB Shell** | 用 fpSup-Merge 建一张带 USB Shell 的卡 → 插上 USB → 主机工具就能读写内存、按键、截图 | skill `fp-camera-control`、`fp-usb-shell` |
| **2. 让你的 AI 接手** | 让它先读 `INDEX.md` 和 `.claude/skills/`。<br>⚠️ **这些是我的 AI 写的,有错。** 重要的结论请自己验证。 | |
| **3. 做一个自己的 sup** | 建卡、测改动、发布 | `fpSup/BUILDING.md`、skill `fp-merged-card` |

### ⚠️ 上机前要知道的

- 完成自己的功能、上机测试前,先用模拟跑过再写卡 → skill `fp-unicorn-emulation`
- 写入相机设置区要小心:它会跨关机保存。过去的分析可参考 [`research/SETTINGS_AREA_FIRST_RULE.md`](research/SETTINGS_AREA_FIRST_RULE.md)(只是参考)。
- 相机卡死了:先读卡(hook 写的数据还在),再拔电池冷启动。

<details>
<summary><b>📁 这个 repo 怎么分</b></summary>

```
README*.md      ← 你在这里(英文 / 简体 / 繁體)
JOURNEY.md      ← 完整故事
INDEX.md        ← 研究总索引:从这里找任何主题
research/       ← 相机本身的事实(固件、传感器、接口、存储…),换个项目还成立
projects/       ← 各 sup 与实验的开发树:源码、测试卡、验证记录、失败记录
fpSup/          ← 网站、正式发布卡(releases/)、各 sup 的发布版源码、fpSup-Merge
.claude/skills/ ← AI 用的操作手册(上机、调用固件函数、建卡、改菜单…)
```

</details>

<details>
<summary><b>📦 只想拉一部分?</b>(整个 repo 约 14 GB)</summary>

只要源码的话:

```sh
git clone --filter=blob:none --sparse https://github.com/ijigen/fpSup.git
cd fpSup && git sparse-checkout set fpSup .claude
```

</details>
