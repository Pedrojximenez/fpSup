(function(){
  'use strict';
  const $=id=>document.getElementById(id), M=window.FPPipeline, I=window.FPPipelineI18n;
  const E=window.FPPipelineEvidence||{},t=I.t;
  const f=(n,d=1)=>Number(n).toLocaleString(I.locale(),{maximumFractionDigits:d,minimumFractionDigits:d});
  let selected='handoff',result;
  function parameters(){const [width,height]=$('resolution').value.split(',').map(Number);
    return {width,height,bits:12,fps:+$('fps').value,speed:+$('speed').value,loss:$('loss').checked,
      ratio:+$('ratio').value/100,codecFhdMs:+$('codec').value,latencyMs:+$('latency').value,
      slotsMode:$('slots').value,rawMiB:+$('rawmem').value,handoffMs:+$('handoff').value};}
  function detail(){document.querySelectorAll('[data-stage]').forEach(b=>{
    const yes=b.dataset.stage===selected;b.classList.toggle('selected',yes);b.setAttribute('aria-pressed',String(yes));
    b.classList.toggle('inactive',!$('loss').checked&&['codec','handoff'].includes(b.dataset.stage));});
    $('stage-detail').textContent=t(selected+'Detail');}
  function svgText(x,y,s,anchor='start'){return `<text x="${x}" y="${y}" text-anchor="${anchor}">${I.escape(s)}</text>`;}
  function draw(){
    if(!result)return;const svg=$('timeline'),width=Math.max(280,svg.getBoundingClientRect().width);
    const narrow=width<500,left=narrow?72:100,right=22,height=255;
    const chartWidth=width-left-right,x=t=>left+t/10000*chartWidth;
    const peak=Math.max(32,result.peakRam*1.15),y=v=>210-v/peak*88;
    const pts=result.samples.map(s=>`${x(s.time)},${y(s.ram)}`).join(' ');
    let s=`<title>${I.escape(t('timelineTitle'))}</title><desc>${I.escape(t('timelineDesc'))}</desc>`;
    const ticks=narrow?[0,5,10]:[0,2,4,6,8,10];
    ticks.forEach(v=>{s+=`<path class="grid" d="M${x(v*1000)} 16V214"/>`+svgText(x(v*1000),233,v+' s',v===10?'end':v===0?'start':'middle');});
    s+=svgText(left-9,44,t('encode'),'end')+svgText(left-9,92,t('media'),'end')+svgText(left-9,155,t('allocation'),'end');
    result.jobs.forEach(j=>{const end=Math.min(10000,j.end);if(j.start<=10000)s+=`<rect class="loss" x="${x(j.start)}" y="27" width="${Math.max(.6,x(end)-x(j.start))}" height="18"/>`;});
    result.writes.forEach(w=>{const end=Math.min(10000,w.end);if(w.start<=10000)s+=`<rect class="sd" x="${x(w.start)}" y="75" width="${Math.max(.6,x(end)-x(w.start))}" height="18"/>`;});
    s+=`<polygon class="ram-fill" points="${x(0)},210 ${pts} ${x(10000)},210"/><polyline class="raw" points="${pts}"/>`;
    s+=svgText(left,119,t('peakLabel',{n:f(result.peakRam)}))+svgText(width-right,253,t('timeAxis'),'end');
    const cursor=x(+$('time').value*1000);s+=`<path class="grid" style="stroke:var(--ink)" d="M${cursor} 16V214"/>`;
    svg.setAttribute('viewBox',`0 0 ${width} ${height}`);svg.innerHTML=s;
  }
  function state(){if(!result)return;const at=+$('time').value*1000;
    const v=result.samples.reduce((prev,s)=>s.time<=at?s:prev,result.samples[0]);
    $('time-label').textContent=f(at/1000,2)+' s';
    $('state').textContent=t('queueState',{frames:v.frames,ram:f(v.ram),batch:f(v.batch),queued:v.queued});
    draw();window.FPFrameFlow?.draw(at);}
  function measurement(){
    const p=parameters(),match=p.width===1936&&p.height===1090&&Math.abs(p.fps-59.94)<.01;
    let html=match?'':`<p class="note">${t('noMeasurement')}</p>`;
    const runs=[['beforeOff',E.off],['beforeOn',E.on],['afterOn',E.fixed]];
    runs.forEach(([key,r])=>{const label=t(key);
      if(!r){html+=`<p class="note">${label}: ${t('unmeasured')}</p>`;return;}
      const w=r.window||r,pc=w.task_percent||{},cpu=w.cpu_percent;
      const mgr=pc.MRecMgr||0,codec=pc.FPLCODE||0,other=Math.max(0,cpu-mgr-codec);
      html+=`<div class="cpu-row"><span>${label}</span><div class="bar" role="img" aria-label="${label} CPU ${f(cpu)}%"><span class="native" style="width:${mgr}%"></span><span class="codec" style="width:${codec}%"></span><span class="other" style="width:${other}%"></span><span class="idle" style="width:${100-cpu}%"></span></div><span>${f(cpu)}%</span></div>`;
    });
    html+=`<div class="legend"><span class="key">${t('recordManager')}</span><span class="key loss">${t('codecTask')}</span><span class="key sd">${t('otherTasks')}</span><span>${t('idle')}</span></div>`;
    $('measurement').innerHTML=html;
    $('phase-table').innerHTML=[1,2,3,4,5].map(id=>{
      const a=E.phasesBefore?.[id],b=E.phasesAfter?.[id];
      const format=x=>x?t('phaseTiming',{cpu:f(x.cpuMeanUs/1000,3),elapsed:f(x.meanUs/1000,3)}):t('unmeasured');
      return `<tr><td>${t('phase'+id)}</td><td>${format(a)}</td><td>${format(b)}</td><td>${t(a||b?'phaseEvidence':'noPhaseEvidence')}</td></tr>`;
    }).join('');
  }
  function render(){if(!result)return;const r=result,q=r.plan;
    $('flow-heading').textContent=t('flowHeading',{slots:r.slots});
    $('rate').textContent=f(r.dataRate)+' MB/s';$('ram').textContent=f(r.peakRam)+' MiB';
    $('capacity').textContent=t('capacityValue',{n:r.slots});
    $('rate-note').textContent=t('rateNote',{compressed:r.compressed,raw:r.raw});
    $('ram-note').textContent=t('ramNote',{n:r.peakFrames});
    $('capacity-note').textContent=t('capacityNote',{raw:f(q.raw/M.MiB,2),charge:f(q.charge/M.MiB,2)});
    $('capture-value').textContent=t('chargeNote',{n:f(q.charge/M.MiB,2)});
    $('codec-value').textContent=r.parameters.loss?t('codecNote',{n:f(q.codecMs)}):t('rawBypass');
    $('batch-value').textContent=t('batchNote',{n:Math.ceil(M.BATCH/(r.parameters.loss?q.compressed:q.raw))});
    $('outcome').textContent=(r.stopped?t('stoppedOutcome',{time:f(r.stopped.time/1000,2),reason:I.reason(r.stopped.reason)}):t('unstoppedOutcome'))+
      ' '+t('outcome',{freed:r.freed,pending:r.pending,busy:r.busyRaw,pressure:r.pressureRaw});
    detail();state();measurement();
  }
  function update(){try{result=M.simulate(parameters());$('error').hidden=true;}
    catch(e){window.FPFrameFlow?.stop();$('error').textContent=I.reason(e.message);$('error').hidden=false;return;}
    window.FPFrameFlow?.setResult(result);render();
  }
  document.querySelectorAll('.controls input,.controls select').forEach(e=>{
    e.addEventListener('input',update);e.addEventListener('change',update);
  });
  document.querySelectorAll('[data-stage]').forEach(b=>b.addEventListener('click',()=>{selected=b.dataset.stage;detail();}));
  $('time').addEventListener('input',state);new ResizeObserver(draw).observe($('timeline'));
  new ResizeObserver(()=>window.FPFrameFlow?.draw(+$('time').value*1000)).observe($('frame-flow'));
  window.addEventListener('fpsup-languagechange',()=>{if(!$('error').hidden)$('error').textContent=t('invalidParameters');render();});
  update();
})();
