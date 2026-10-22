/* UI strings only. Simulation values and measured evidence are independent
 * of language. Use fpSup's persisted language and Simplified conversion. */
(function () {
  'use strict';
  const L = window.FPSupLanguage;
  const messages = {
    title: ['SIGMA fp pipeline analysis', 'SIGMA fp 管線分析'],
    subtitle: ['Follow the work, frame releases and waits as codec and media speeds change.', '查看工作在哪裡發生、影格何時釋放，以及媒體與壓縮速度如何改變等待。'],
    research: ['Firmware research', '韌體研究'],
    description: ['Interactive per-frame SIGMA fp recording model: 96 buffer slots, the 64 MiB write gate, lossless compression, media speed and measured CPU costs.', 'SIGMA fp 逐幀錄影管線模型：96 個緩存位置、64 MiB 寫入閘門、無損壓縮、媒體速度與相機實測 CPU 成本。'],
    resolution: ['Frame dimensions · RAW', '影格尺寸 · RAW'],
    fps: ['Frame rate', '幀率'],
    speed: ['Sustained media write speed · MB/s', '媒體持續寫速 · MB/s'],
    lossOn: ['Enable hardware compression', '開啟硬體壓縮'],
    assumptions: ['File size, slots and timing assumptions', '檔案大小、位置與時間假設'],
    ratio: ['Compressed pixels / RAW pixels · %', '壓縮像素／RAW 像素大小 · %'],
    codecTime: ['FHD encode completion · ms (with scheduling)', 'FHD 編碼完成時間 · ms（含排程）'],
    latency: ['Observed completion latency · ms', '觀察的完成延遲 · ms'],
    slotPolicy: ['Buffer slot policy', '位置策略'],
    stockSlots: ['Stock · 96 slots', '原廠 96 位置'],
    expandedSlots: ['Expand for two batches', '依兩批公式擴充'],
    rawMemory: ['Available RAW allocation pool · MiB', 'RAW 類別可用配置 · MiB'],
    handoffTime: ['Compressed frame handoff · ms', '壓縮幀交接完成時間 · ms'],
    assumptionsNote: ['Dimensions and speeds are model inputs; the camera does not support every combination. Batches stay at 64 MiB. Initial encode/handoff timings refer to the corrected FHD short test; other sizes scale with pixel count. CPU figures are measured only.', '尺寸與速度是模型輸入，並不表示機身支援所有組合。批次固定 64 MiB。初始編碼／交接時間參考修正後的 FHD 短測；其他尺寸依像素比例推估。CPU 使用率只呈現實測。'],
    flowHeading: ['Frame flow · {slots} slots and the 64 MiB gate', '逐幀流向 · {slots} 個位置與 64 MiB 閘門'],
    play: ['Play', '播放'], pause: ['Pause', '暫停'],
    step: ['Next frame', '下一幀'], eventStep: ['Next event', '下一事件'], restart: ['Restart', '回到起點'],
    playbackSpeed: ['Playback speed', '播放速度'], fineSpeed: ['0.05× · inspect the flow', '0.05× · 細看流動'], slowSpeed: ['0.25× · slow motion', '0.25× · 慢放'],
    slotPage: ['Buffer slot page', '緩存位置頁'],
    flowAria: ['Each frame’s buffer slot, compression or RAW route, and the 64 MiB media gate', '每一幀占用的緩存位置、壓縮或 RAW 路徑與 64 MiB 媒體閘門'],
    viewTime: ['View time', '查看時間'], rawFrame: ['RAW frame', 'RAW 幀'], compressedFrame: ['Compressed frame', '壓縮幀'],
    sentFrame: ['Data sent; awaiting batch callback', '資料已送出，等整批回呼'],
    ringLegend: ['Bright ring: passing the gate · grey cell: free slot', '亮圈＝正在過閘；灰格＝空位'],
    flowNote: ['A slot and its moving markers refer to the same frame. Encoding and media completion are different events: passage through the gate does not release a slot until the batch callback.', '格子保留同一幀的位置；路徑上的資料點對應同一幀。壓縮與寫入完成是不同事件，資料過閘後仍需等整批回呼才釋放位置。'],
    framePicker: ['Click a slot or marker, or select a frame to inspect its route', '點選幀格／資料點，或選擇幀號查看完整去向'],
    noFrames: ['No frames yet', '尚未產生影格'],
    ratesHeading: ['Data rates and pipeline stages', '資料率與管線說明'],
    dataRate: ['File data rate over the 10 s model', '10 秒模型產生的檔案資料率'],
    peakMemory: ['Peak allocations: pending frames + two spares', '待完成影格＋兩份 spare 的配置峰值'],
    batchCapacity: ['64 MiB batch / available slots', '64 MiB 批次／可用位置'],
    pathHeading: ['The route a frame takes', '影格走過的路徑'],
    captureResource: ['Stock · capture', '原廠 · 擷取'], captureNode: ['RAW allocation', 'RAW 配置'],
    codecResource: ['LOSS · hardware', 'LOSS · 硬體'], codecNode: ['Two lanes / one engine', '兩通道／一引擎'],
    handoffResource: ['LOSS · CPU + DMA', 'LOSS · CPU＋DMA'], handoffNode: ['Complete DNG / swap', '完成 DNG／交換'], handoffNote: ['Keep native frame identity', '保留原生幀身分'],
    writerResource: ['Stock · files', '原廠 · 檔案'], writerNode: ['Create / submit file', '建立／送出檔案'], writerNote: ['LOSS changes final length', 'LOSS 只改最終長度'],
    batchResource: ['Stock · media', '原廠 · 媒體'], batchNode: ['Accumulate 64 MiB', '累積 64 MiB'],
    freeResource: ['Stock · callback', '原廠 · 完成回呼'], freeNode: ['Release RAW allocation', '釋放 RAW 配置'], freeNote: ['STOPFX completes cleanup on abnormal stop', '異常停錄時由 STOPFX 補足丟棄清理'],
    allocationNote: ['Uncompressed frames and those bypassed due to busy lanes or memory protection use the native file route. Compressed frames retain a RAW-sized allocation until their batch completes.', '原始 RAW、通道忙碌或記憶體保護退回的幀，直接進入原廠檔案路徑。壓縮幀在批次完成前仍持有原始尺寸的 allocation。'],
    queueHeading: ['Queue history and camera measurements', '整段佇列與相機實測耗時'],
    timelineHeading: ['10 s queue simulation', '10 秒佇列推演'], timelineQualifier: ['Model · no camera recording', '模型，不是相機錄影'],
    timelineAria: ['Hardware codec, media batch timeline and allocations held by pending frames', '壓縮引擎與媒體批次的時間軸，以及待完成影格記憶體'],
    encodeJobs: ['Encode jobs', '編碼工作'], mediaWrites: ['Media writes', '媒體寫入'], frameAllocations: ['Frame allocations', '影格配置量'],
    measuredHeading: ['Camera measurements · FHD 12-bit / 59.94p', '相機實測 · FHD 12-bit／59.94p'],
    measuredNote: ['Short tests at FHD / 59.94p, observed 1.1–2.1 s after the task monitor started, with the same diagnostic communication priority. OFF is an earlier reference; ON before and after were measured following separate reboots. Other camera work affects total load. Phase CPU timings locate added work more precisely; task time can include interrupts and memory waits.', '相同 FHD／59.94p 條件的短測，觀察窗在任務監測起點後 1.1–2.1 秒；診斷通訊優先序一致。OFF 為較早一輪的參考，ON 前後分別在重開後量測。整體負載會受相機其他工作影響，分段 CPU 時間較能定位新增成本；任務時間可能包含中斷及記憶體等待。'],
    phaseHeading: ['Added work: phase timings', '新增工作分段計時'], work: ['Work', '工作'], before: ['Before', '修正前'], after: ['After', '修正後'], evidence: ['Evidence', '證據'],
    footer: ['Interactive research model · speeds in MB/s, memory in MiB. Unmeasured results are left blank.', '互動研究模型 · 速度以 MB/s、記憶體以 MiB 表示。尚未量測的項目保留空白。'],
    evidenceLink: ['Download measured data', '下載實測資料'], modelLink: ['Model calculations', '模型計算來源'],
    captureDetail: ['Native capture allocates a RAW-sized buffer and frame descriptor. Compression does not shrink that allocation. Slot count determines how many frames can be tracked at once.', '原廠擷取配置一張 RAW 大小的緩衝與幀描述子。檔案壓縮後，這份配置的容量仍是 RAW 大小。位置數只決定能同時追蹤多少幀。'],
    codecDetail: ['Two LOSS lanes share one hardware engine. The CPU sets up the engine, then blocks on completion events. When both lanes are busy, new frames use RAW. The model scales observed FHD completion time with pixel count.', 'LOSS 有兩個等候通道，共用一個硬體引擎。CPU 設定引擎後阻塞等待完成事件；兩通道忙碌時，新幀直接走 RAW。模型依觀察的 FHD 完成時間與像素數推算硬體服務時間。'],
    handoffDetail: ['After compression, copy the header, complete the trailing DNG tables, swap allocation records and pixel pointers, then enqueue natively. Added CPU work is concentrated here and in engine completion fixups. No CPU copy of the full compressed pixel payload is needed. This describes the measured version, not the newer offline prepared-header prototype.', '壓縮完成後複製表頭、完成 DNG 尾表、交換 allocation 記錄與像素指標，再交回原廠。新增的 CPU 工作集中在此處與引擎完成修補；不需要 CPU 複製整張壓縮像素。此處描述實測版本，尚未套用較新的預備檔頭離線原型。'],
    writerDetail: ['Native file creation and submission still run. LOSS only replaces the completed DNG’s actual file length in the writer. Submission does not mean the frame allocation can be released.', '原廠檔案建立與送出仍然執行。LOSS 在 writer 只替換已完成 DNG 的實際檔案長度。建立與送出的完成，還不表示幀配置已可釋放。'],
    batchDetail: ['The media layer submits a batch after accumulating about 64 MiB. Smaller compressed files allow more frames in one batch, while each frame still holds a RAW-sized allocation. Slow media let later batches and captured frames accumulate.', '媒體累積約 64 MiB 後送出一批。壓縮讓檔案變小，因此同一批可以含更多幀；每幀仍持有 RAW 大小配置。慢媒體會讓下一批與擷取繼續累積。'],
    freeDetail: ['After media completion callbacks, native code releases frame allocations and descriptors. Ruari’s independent STOPFX cleans up discarded frames on abnormal stop; it does not reduce recording CPU load. The model counts pending frames and codec spares, excluding other camera allocations.', '媒體完成回呼後，原廠釋放每幀 allocation 與描述子。STOPFX（Ruari）獨立處理異常停錄時被丟棄的幀，不負責降低錄影時 CPU 負載。模型只計算待完成幀與 codec spare，其他相機配置未納入。'],
    timelineTitle: ['10 s discrete-event queue model', '十秒離散事件佇列推演'],
    timelineDesc: ['Hardware encoding, media writes and allocations held by pending frames. The model does not estimate CPU usage.', '硬體編碼、媒體寫入與待完成影格的配置量；CPU 未經此模型推估。'],
    encode: ['Encode', '編碼'], media: ['Media', '媒體'], allocation: ['Memory', '配置'],
    peakLabel: ['{n} MiB peak', '{n} MiB 峰值'], timeAxis: ['Time (s)', '時間（秒）'],
    queueState: ['{frames} frames held · {ram} MiB · partial batch {batch} MiB · {queued} batches awaiting media', '{frames} 幀持有配置 · {ram} MiB · 未滿一批 {batch} MiB · {queued} 批等待媒體'],
    noMeasurement: ['No CPU measurement for this combination; the FHD / 59.94p reference remains below.', '此組合沒有 CPU 實測；下方保留 FHD／59.94p 的比較基準。'],
    beforeOff: ['Before · OFF', '修正前 OFF'], beforeOn: ['Before · ON', '修正前 ON'], afterOn: ['After · ON', '修正後 ON'], unmeasured: ['Unmeasured', '待量測'],
    recordManager: ['Record manager', '錄影管理'], codecTask: ['LOSS task', 'LOSS 工作任務'], otherTasks: ['Other busy tasks', '其他忙碌任務'], idle: ['Blank: idle', '空白：閒置'],
    phase1: ['Header DMA', '表頭 DMA'], phase2: ['DNG trailer packing', 'DNG 尾表封裝'], phase3: ['Native enqueue', '原生入列'], phase4: ['Engine wait + completion fixups', '引擎事件等待＋完成修補'], phase5: ['Engine setup / start', '引擎設定／啟動'],
    phaseTiming: ['{cpu} ms CPU / {elapsed} ms elapsed', '{cpu} ms CPU／{elapsed} ms 經過'], phaseEvidence: ['Task switches × phase intervals', '任務切換 × 分段區間'], noPhaseEvidence: ['No phase measurement yet', '尚未取得分段實測'],
    capacityValue: ['64 MiB / {n} slots', '64 MiB / {n} 格'],
    rateNote: ['{compressed} compressed / {raw} RAW frames; includes busy-lane and memory bypass', '壓縮 {compressed} 幀／RAW {raw} 幀；包含忙碌與記憶體保護退回'],
    ramNote: ['Peak {n} frames; not total camera RAM', '{n} 幀峰值；不是整機 RAM 使用量'],
    capacityNote: ['RAW file {raw} MiB; allocation {charge} MiB', '原始每幀 {raw} MiB；每配置 {charge} MiB'],
    chargeNote: ['{n} MiB / frame', '{n} MiB／幀'], codecNote: ['{n} ms / completion; scaled by pixels', '{n} ms／完成；像素比例推估'], rawBypass: ['RAW bypass', 'RAW 旁路'],
    batchNote: ['About {n} frames / batch of equal-sized files', '約 {n} 幀／全同大小批次'],
    stoppedOutcome: ['Capture stopped at {time} s: {reason}.', '{time} 秒因{reason}停止擷取。'], unstoppedOutcome: ['No allocation limit reached in the 10 s model.', '十秒內模型未碰到配置上限。'],
    outcome: ['Media completed {freed} frames; {pending} remain pending. Busy lanes bypassed {busy} frames to RAW; memory protection bypassed {pressure}. The partial final batch under 64 MiB is settled outside this window.', '媒體完成 {freed} 幀、仍待完成 {pending} 幀。通道忙碌退回 RAW {busy} 幀、記憶體保護退回 {pressure} 幀。停止時未滿 64 MiB 的尾批在此窗外結算。'],
    invalidParameters: ['Parameters are outside the model’s range', '參數超出模型範圍'], slotsFull: ['No free slots', '位置不足'], memoryFull: ['RAW pool exhausted', 'RAW 配置不足'],
    firstRaw: ['First frame: RAW', '首幀 RAW'], lossOff: ['LOSS off', 'LOSS 關閉'], memoryBypass: ['Memory protection', '記憶體保護'], busyBypass: ['Both lanes busy', '兩通道忙碌'], noSaving: ['Compression did not reduce size', '壓縮未縮小'],
    flowTitle: ['Frame flow and the 64 MiB gate', '逐幀流向與 64 MiB 閘門'], flowDesc: ['Cells show frame numbers. Data passage does not clear a slot; release waits for the batch callback.', '格內為幀號；資料通過媒體後仍等整批完成才清空原始緩存位置。'],
    capturedStats: ['{time} s · {captured} captured · {freed} released', '{time} s · 已擷取 {captured} 幀 · 已回收 {freed} 幀'],
    slotStats: ['{slots} slots | {used} used | showing {start}–{end}', '{slots} 個位置｜占用 {used}｜顯示 {start}–{end}'],
    frameSlot: ['F{frame} · slot {slot}', 'F{frame} · 位置 {slot}'], slotTitle: ['Slot {slot}: {frame}', '位置 {slot}：{frame}'],
    freeSlot: ['Free', '空閒'], stageFree: ['Released', '已回收'], stageMedia: ['Awaiting batch completion', '等媒體批次完成'], stagePassing: ['Passing gate', '正在過閘'], stageBatch: ['Awaiting gate', '等待過閘'], stageHandoff: ['DNG handoff', 'DNG 交接'], stageEncode: ['Encoding', '編碼中'], stageWaiting: ['Awaiting codec', '等候壓縮'],
    engine: ['One codec engine', '一個壓縮引擎'], engineShort: ['Codec', '壓縮'], lanes: ['Two lanes', '兩個通道'], lanesShort: ['2 lanes', '兩通道'],
    batchBuffer: ['Batch buffer', '批次累積'], awaitingPassage: ['{n} waiting', '{n} 幀待通過'], batchQueue: [' · {n} batches queued', ' · {n} 批排隊'],
    held: ['Held until batch done', '整批完成前仍持有'], heldShort: ['Held', '等待回收'], newBatch: ['Waiting for a new batch', '等待新批次'], newBatchShort: ['Next batch', '待新批次'],
    gateOpen: ['OPEN', '開閘'], gateClosed: ['SHUT', '關閘'], batchNumber: ['Batch {n}', '批 {n}'],
    callback: ['Batch callback → release completed frame allocations', '完成回呼 → 才釋放整批內已完成的幀配置'], callbackShort: ['Batch done → free finished frames', '整批完成 → 釋放已完成幀'],
    stoppedFlow: ['{time} s: {reason}; capture stopped', '{time} s：{reason}，停止新增幀'], followLatest: ['Follow latest frame', '跟隨最新幀'],
    traceCapture: ['Captured', '擷取'], traceEncode: ['Encode', '編碼'], traceEncoded: ['Encoded', '完成編碼'], traceQueued: ['Into batch', '送入批次'], traceBatches: ['Batches {n}', '批次 {n}'], tracePassage: ['Passage begins', '資料開始過閘'], traceReleased: ['Callback / released', '完成回呼／釋放'],
    notYet: [' (pending)', '（尚未）'], stillHeld: ['RAW allocation still held', '仍持有 RAW 配置'], traceEmpty: ['Play or advance a frame to follow its route.', '播放或逐幀前進，查看每一幀的去向。']
  };
  const reasons = {'參數超出模型範圍':'invalidParameters','位置不足':'slotsFull','RAW 配置不足':'memoryFull',
    '首幀 RAW':'firstRaw','LOSS 關閉':'lossOff','記憶體保護':'memoryBypass','兩通道忙碌':'busyBypass','壓縮未縮小':'noSaving'};
  const language = () => L.get();
  const simplifiedMessages = {};
  function simplified(text) {
    const terms = {'韌體':'固件','硬體':'硬件','記憶體':'内存','影格':'帧','表頭':'文件头','檔頭':'文件头',
      '檔案':'文件','資料':'数据','佇列':'队列','擷取':'采集','回呼':'回调','入列':'入队',
      '設定':'设置','閒置':'空闲','支援':'支持','量測':'测量'};
    Object.entries(terms).forEach(([from,to])=>{text=text.split(from).join(to);});
    return L.toSimplified(text);
  }
  function t(key, values={}) {
    if (!messages[key]) throw Error('Missing pipeline UI translation: '+key);
    const [en,zh,cn] = messages[key], lang = language();
    const text = lang === 'en' ? en : lang === 'cn' ? (cn || (simplifiedMessages[key] ??= simplified(zh))) : zh;
    return text.replace(/\{(\w+)\}/g, (_,name) => String(values[name] ?? '{'+name+'}'));
  }
  function apply() {
    document.querySelectorAll('[data-i18n]').forEach(el => { el.textContent = t(el.dataset.i18n,el.dataset.i18n==='flowHeading'?{slots:96}:{}); });
    document.querySelectorAll('[data-i18n-aria-label]').forEach(el => { el.setAttribute('aria-label',t(el.dataset.i18nAriaLabel)); });
    document.querySelectorAll('[data-i18n-content]').forEach(el => { el.setAttribute('content',t(el.dataset.i18nContent)); });
    document.title = t('title')+' — fpSup';
  }
  window.FPPipelineI18n = {t, language, reason: s => reasons[s] ? t(reasons[s]) : s,
    locale: () => language()==='en'?'en-US':language()==='cn'?'zh-CN':'zh-TW',
    escape: s => String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))};
  const requested = new URLSearchParams(location.search).get('lang');
  if (['en','cn','zh'].includes(requested)) L.set(requested);
  window.addEventListener('fpsup-languagechange', apply);
  apply();
})();
