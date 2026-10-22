"use client";

import { useState } from "react";

const stages = [
  {
    n: "01",
    title: "選區",
    sub: "臉／眼／追蹤框",
    text: "DetectionMgr 只回答『對哪裡』。它把目標框交給 AF 高／低頻對比評價區，並不直接算焦點。AE 的 YLevel 是另一個量，只用來做低光／低對比閘控。",
  },
  {
    n: "02",
    title: "判方向",
    sub: "低頻 HPF + Rocking",
    text: "嚴重失焦時高頻已消失，低頻仍保留方向線索；不確定時小幅搖擺，以遲滯投票避免被單幀雜訊翻向。",
  },
  {
    n: "03",
    title: "連續爬升",
    sub: "Fast → Slow",
    text: "鏡頭等速掃描，影像串流持續量測。接近峰時交給更細的策略，而不是每一步都停下來拍一張。",
  },
  {
    n: "04",
    title: "越峰確認",
    sub: "down-check",
    text: "對比開始下降仍不立刻停；連續證據確認已越峰，犧牲一點行程換取不被局部雜訊峰欺騙。",
  },
  {
    n: "05",
    title: "三點內插",
    sub: "次脈衝估計",
    text: "以峰左右三點擬合拋物線頂點。這是局部內插，不是拿遠端三點外插；前者穩定，後者會因曲率估計而爆掉。",
  },
  {
    n: "06",
    title: "回驅與鎖定",
    sub: "backlash + settled",
    text: "回到估計峰，反向時補償鏡頭背隙，最後以穩定條件確認；找不到可靠峰則反向重試或全掃。",
  },
];

const trades = [
  [
    "CDAF，而非相位對焦",
    "不需片上相位像素、最終判準直接是成像銳利度",
    "必須移動鏡頭才能知道方向；天然有 hunting 與延遲",
  ],
  [
    "多頻帶評價",
    "低頻負責遠離焦，高頻負責近峰精度",
    "濾波器、模式與曝光正規化更複雜",
  ],
  [
    "越峰後再回來",
    "能確認真峰，對雜訊與假峰較穩健",
    "畫面可見過衝；錄影觀感不如預測式落點",
  ],
  [
    "鏡頭校準表",
    "DPP、速度、背隙讓移動更快更準",
    "不同鏡頭資料品質不一；必須保留 default fallback",
  ],
  [
    "等速連續掃描",
    "符合韌體行為，取樣時間軸可推算且不反覆啟停",
    "速度受影像幀率限制，不只受馬達上限限制",
  ],
  [
    "單一決策者",
    "所有驅動嚴格排序，策略只是狀態，不需仲裁",
    "重運算必須拆成 worker，以最新值槽交付",
  ],
];

export default function Home() {
  const [active, setActive] = useState(0);
  return (
    <main>
      <nav>
        <a className="brand" href="#top">
          <span>Σ</span> fp / AF
        </a>
        <div>
          <a href="#flow">流程</a>
          <a href="#why">權衡</a>
          <a href="#implementation">實作</a>
        </div>
      </nav>
      <header id="top">
        <div className="eyebrow">FIRMWARE DESIGN STUDY · fp VER. 5.02</div>
        <h1>
          焦點不是被「看見」的。
          <br />
          <em>它是被爬出來的。</em>
        </h1>
        <p className="lead">
          SIGMA fp
          沒有片上相位對焦。它用影像對比當山勢、鏡頭脈衝當腳步，先找方向、越過山頂，再內插回真正的峰。
        </p>
        <div className="hero-grid">
          <div className="curve-card" aria-label="對比對焦曲線示意圖">
            <div className="curve-label peak">真峰</div>
            <div className="curve-label over">越峰確認</div>
            <svg
              viewBox="0 0 720 260"
              role="img"
              aria-label="對比值隨鏡頭位置先升後降，鏡頭越峰後回驅"
            >
              <path
                className="grid"
                d="M40 40H690M40 100H690M40 160H690M40 220H690"
              />
              <path
                className="curve"
                d="M42 218 C170 214 238 195 310 126 C365 72 403 38 448 47 C505 60 532 144 573 187 C612 220 652 220 690 222"
              />
              <path
                className="motion"
                d="M80 232 H544 M544 232 C560 232 560 246 544 246 H449"
              />
              <circle cx="449" cy="47" r="7" />
              <circle className="overdot" cx="544" cy="163" r="7" />
            </svg>
            <div className="axis">
              <span>遠端</span>
              <span>鏡頭位置（pulse）</span>
              <span>近端</span>
            </div>
          </div>
          <div className="fact-stack">
            <div>
              <b>H / L</b>
              <span>
                兩組 AF 帶通評價
                <br />
                不是 AE 的 YLevel
              </span>
            </div>
            <div>
              <b>6</b>
              <span>
                種驅動策略
                <br />
                由單一狀態機調度
              </span>
            </div>
            <div>
              <b>30 fps</b>
              <span>
                實作的真正速度瓶頸
                <br />
                不是 37k pps 馬達上限
              </span>
            </div>
          </div>
        </div>
      </header>
      <section className="principle">
        <div>
          <span className="kicker">核心原理</span>
          <h2>對比是山，位置是橫軸。</h2>
        </div>
        <p>
          每一幀先經數位增益、LPF、兩組 IIR 帶通／差分濾波與中值處理，分別累加{" "}
          <b>saf_jdat_h</b> 與 <b>saf_jdat_l</b>
          。合焦時細節能量最高，因此形成峰。YLevel 則屬 AE
          亮度均值，只參與低光／低對比判斷。
        </p>
      </section>
      <section id="flow" className="flow-section">
        <div className="section-head">
          <span className="kicker">一次 AF-S</span>
          <h2>六步走完一座山</h2>
          <p>點擊各階段查看它解決的問題。</p>
        </div>
        <div className="flow">
          <div className="stage-list">
            {stages.map((s, i) => (
              <button
                key={s.n}
                className={active === i ? "active" : ""}
                onClick={() => setActive(i)}
              >
                <i>{s.n}</i>
                <span>
                  <b>{s.title}</b>
                  <small>{s.sub}</small>
                </span>
              </button>
            ))}
          </div>
          <article className="stage-detail">
            <span>{stages[active].n} / 06</span>
            <h3>{stages[active].title}</h3>
            <p>{stages[active].text}</p>
            <div className="rule">
              設計意圖：
              <b>
                {
                  [
                    "把主體辨識與合焦控制解耦",
                    "在訊號最弱時仍取得方向",
                    "讓馬達與量測同時工作",
                    "以遲滯換可靠性",
                    "只在峰附近相信拋物線",
                    "把機械誤差納入閉環",
                  ][active]
                }
              </b>
            </div>
          </article>
        </div>
      </section>
      <section id="why" className="trade-section">
        <div className="section-head">
          <span className="kicker">設計理由與代價</span>
          <h2>每個「穩」都用別的東西換來</h2>
        </div>
        <div className="trade-table">
          <div className="thead">
            <span>選擇</span>
            <span>得到</span>
            <span>付出</span>
          </div>
          {trades.map((r, i) => (
            <div className="trow" key={i}>
              <strong>{r[0]}</strong>
              <span className="gain">＋ {r[1]}</span>
              <span className="cost">− {r[2]}</span>
            </div>
          ))}
        </div>
      </section>
      <section className="aat-section">
        <div className="section-head">
          <span className="kicker">AAT · AutoTracking</span>
          <h2>它追蹤畫面中的主體，不直接追蹤焦點深度。</h2>
          <p>
            AAT 每個 Live View frame 更新目標框，再把框轉成 CDAF
            評價區；真正的焦點位置仍由該區的高／低頻對比曲線決定。
          </p>
        </div>
        <div className="aat-flow">
          <article>
            <b>01 · Seed</b>
            <h3>使用者 AF 框</h3>
            <p>
              Tap 先由 CoordinateMgr 轉成 LV 像素框，AAT
              以此初始化目標；追蹤器本身不直接讀 tap 座標。
            </p>
          </article>
          <article>
            <b>02 · Track</b>
            <h3>自適應單一參考色</h3>
            <p>
              出貨機使用 YCbCr
              色彩後端；直方圖後端雖編入韌體，但旗標關閉。每幀以色距、色相楔形與空間罰定位。
            </p>
          </article>
          <article>
            <b>03 · Gate</b>
            <h3>Confidence &gt; 19</h3>
            <p>
              目前框位於 <code>0xC3033E00</code>，信心在 <code>0xC3033E26</code>
              ；低於 20 不鎖定、不交給 AF。
            </p>
          </article>
          <article>
            <b>04 · Focus</b>
            <h3>框 → AF 評價區</h3>
            <p>
              無臉／眼、AF-C 且 AAT 模式啟用時才採用。輸出端將框重塑為
              2.5×W、1.5×H，再交給 CDAF。
            </p>
          </article>
        </div>
        <div className="aat-note">
          <strong>AF-C 的真正耦合</strong>
          <p>
            AAT
            框移動只會搬移「看哪一區」；韌體沒有把框的像素速度直接換成焦點速度。框尺寸改變會進入
            drift monitor（約 2%／10% 門檻）觸發重對焦；峰位預測則使用該 AF
            區自己的歷史峰位。
          </p>
          <p>
            優化切入點：保留 AAT 選區，加入「框尺度速度 +
            峰位速度」聯合可信度；但不能只靠框變大／變小決定鏡頭脈衝，因為主體姿態與構圖也會改變框尺寸。
          </p>
        </div>
      </section>

      <section className="routing-section">
        <div className="section-head">
          <span className="kicker">AF-C 觸發與策略路由</span>
          <h2>「重新驅動」是觸發結果；Fast／Slow 是後續路由。</h2>
          <p>
            兩者不是同一層。監視器只決定要不要離開保持狀態；外層序列器再依
            route、近距模式、連拍與 phase capability 選策略。
          </p>
        </div>
        <div className="route-map">
          <div className="route-trigger">
            <b>監視器觸發</b>
            <span>框尺寸／邊界、亮度網格、AF 評價漂移、逾時、體動</span>
          </div>
          <div className="route-arrow">↓</div>
          <div className="route-state">
            <b>普通重驅</b>
            <span>外層 state 0 → 1 → 2 → 3</span>
          </div>
          <div className="route-arrow">↓</div>
          <div className="route-grid">
            <article className="route-live">
              <b>fp 一般路徑</b>
              <h3>Fast</h3>
              <p>
                冷啟動或普通 research route；fp 的 phaseAvailable 為
                false，因此初始路徑選 Fast。
              </p>
            </article>
            <article>
              <b>Fast route 8</b>
              <h3>Slow</h3>
              <p>
                不是獨立觸發。只有 Fast 成功後把 NextRoute 設為
                handoffSlow（8），外層才選 Slow。
              </p>
            </article>
            <article>
              <b>Near mode / route 2</b>
              <h3>Near</h3>
              <p>近距條件成立才選；不能把一般 AF-C 重驅概括成 Near。</p>
            </article>
            <article>
              <b>外層 state 6</b>
              <h3>Rocking</h3>
              <p>
                不在 <code>FUN_c028d2b0</code>{" "}
                選擇器內。由體動謂詞走專用連續伺服迴圈。
              </p>
            </article>
            <article>
              <b>需要 phase</b>
              <h3>Hybrid</h3>
              <p>
                route C／D 且 phaseAvailable 才成立；fp 的 capability gate 回
                0，正常會退回 Fast。
              </p>
            </article>
            <article>
              <b>連拍旗標</b>
              <h3>ContShooting</h3>
              <p>
                只在 continuous-shooting 條件成立時優先選擇，與一般錄影 AF-C
                不同。
              </p>
            </article>
          </div>
        </div>
        <div className="route-summary">
          <strong>因此一般 fp AF-C 重驅的主要可證鏈：</strong>
          <code>
            drift trigger → state 0/1/2/3 → Fast →（route 8）Slow → hold
          </code>
          <span>
            體動 Rocking 是旁路；Near、Hybrid、ContShooting 都有額外條件。
          </span>
        </div>
      </section>

      <section className="lens-section">
        <div className="section-head">
          <span className="kicker">鏡頭資料的角色</span>
          <h2>影像決定「有沒有合焦」；鏡頭資料決定「多快到那裡」。</h2>
        </div>
        <div className="lens-grid">
          <article>
            <b>必要回授</b>
            <h3>感光元件的對比值</h3>
            <p>即使沒有鏡頭校準資料，仍可盲爬山找到峰。這是最小可運作核心。</p>
          </article>
          <article>
            <b>速度先驗</b>
            <h3>Defocus per pulse</h3>
            <p>
              把估計離焦量換成驅動脈衝；少了它仍能工作，但只能更保守地掃描。
            </p>
          </article>
          <article>
            <b>機械先驗</b>
            <h3>pps、端點與 backlash</h3>
            <p>限制安全速度、避免撞端點，並修正反向時齒輪空程。</p>
          </article>
          <article>
            <b>映射先驗</b>
            <h3>位置 ↔ 距離</h3>
            <p>
              SIGMA 原廠鏡頭提供非線性曲線；部分副廠鏡頭僅有均勻軸，因此距離與
              DOF 顯示較粗。
            </p>
          </article>
        </div>
      </section>
      <section id="implementation" className="implementation">
        <div className="section-head">
          <span className="kicker">專案如何忠實實作</span>
          <h2>復刻機制，不假裝硬體相同</h2>
        </div>
        <div className="truth-grid">
          <article>
            <span>[D]</span>
            <h3>直接核對反編譯碼</h3>
            <p>
              <code>calIntrPolAreaAfPeakPoint @ c0263ff8</code>、
              <code>JudgeSubjectMoveByPeakData @ c02766a8</code> 與策略 caller
              可達路徑，不只依賴文件摘要。
            </p>
          </article>
          <article>
            <span>[M]</span>
            <h3>真機量測優先</h3>
            <p>
              GIMBAL 錄影中可驅動、位置回報、HDMI 時序、鏡頭資料
              dump。與反編譯衝突時，實測勝。
            </p>
          </article>
          <article>
            <span>[?]</span>
            <h3>等效替代明標</h3>
            <p>
              讀不到陀螺儀、PDAF
              可靠度或部分內部量時，不冒充原廠；用概念對應並留下可驗證假設。
            </p>
          </article>
        </div>
        <div className="deadcode">
          <strong>重要可達性結論</strong>
          <p>
            <code>CalcCafDriveSpeed @ c027eeb0</code> 的 caller 先呼叫 AF model
            vtable <code>+0x184</code>；fp runtime subclass 對應函式無條件回
            0。因此這條 PdCaf 速度路徑在 fp 上不會進入。真正的 CDAF
            掃描、越峰與回峰機制必須從可達的 Fast／Slow／DriveScan
            路徑理解，不能把共用庫死碼當成 fp 行為。
          </p>
        </div>
        <div className="architecture">
          <div className="arch-copy">
            <h3>12,000 pps 與錄影幀率</h3>
            <p>
              fp 的 AF 統計跟隨當下 sensor
              mode；錄影時感光元件更新率與錄影格式相同。 以 30 fps 計算，12,000
              pps 約為每幀 400 pulse，但這不等於原廠會漏峰：
              粗掃使用較寬的低頻評價找方向與越峰，再交給 Slow 與三點內插精定位。
            </p>
            <p className="answer">
              專案目前採用 <strong>2,400 pps</strong>，是外部 HDMI
              復刻在尚未量完 「速度 × 評價曲線 ×
              成功率」前的保守實驗設定；不是已證明的 fp 原廠限制。 是否能提高到
              12,000，應由實機掃描成功率決定。
            </p>
          </div>
          <div className="meter">
            <div>
              <span>馬達能力</span>
              <i style={{ width: "100%" }}></i>
              <b>37,000</b>
            </div>
            <div>
              <span>錄影上限</span>
              <i style={{ width: "32%" }}></i>
              <b>12,000</b>
            </div>
            <div>
              <span>目前粗掃</span>
              <i className="hot" style={{ width: "6.5%" }}></i>
              <b>2,400 pps</b>
            </div>
          </div>
        </div>
      </section>
      <section className="new-af">
        <span className="kicker">下一條路</span>
        <h2>
          原廠：越峰後知道答案。
          <br />
          研究版：接近時就預測答案。
        </h2>
        <div className="compare">
          <div>
            <b>韌體 CDAF</b>
            <p>爬升 → 越峰 → 三點內插 → 回驅</p>
            <span>可靠，但畫面會看見過衝</span>
          </div>
          <div className="arrow">→</div>
          <div>
            <b>Lorentzian 先驗</b>
            <p>持續估計峰位 → 提前非線性減速</p>
            <span>更像對焦員，但模型與控制器仍待跨光圈驗證</span>
          </div>
        </div>
        <p className="fineprint">
          專案實測顯示：三點拋物線外插在離峰約 80 pulse 外會不穩；固定
          Lorentzian 形狀後，線上只需搜尋峰位，估計會隨接近持續收斂。這是新 AF
          研究，不是 fp 韌體行為。
        </p>
      </section>
      <footer>
        <span>
          依據 sigma-fp-gimbal-ai 與 SIGMAfp_re；不確定處回查 Ver.5.02
          out/decomp/full/blk_c02.c
        </span>
        <a href="#top">回到頂端 ↑</a>
      </footer>
    </main>
  );
}
