/* Every marker is a model frame, with a persistent descriptor slot and
 * byte-level media segments. Data passage does not release the allocation. */
(function(){
  'use strict';
  const $=id=>document.getElementById(id),F=window.FPPipeline,I=window.FPPipelineI18n,T=I.t;
  let data=null,playing=false,lastPaint=0,lastCount=-1,eventTimes=[];
  const fmt=(v,d=2)=>Number(v).toFixed(d),color=f=>f.mode==='raw'?'var(--raw)':'var(--loss)';
  const txt=(x,y,s,anchor='start')=>`<text x="${x}" y="${y}" text-anchor="${anchor}">${I.escape(s)}</text>`;
  const stageNames={free:'stageFree',media:'stageMedia',passing:'stagePassing',batch:'stageBatch',handoff:'stageHandoff',encode:'stageEncode',waiting:'stageWaiting'};
  const box=(x,y,w,h)=>`<rect x="${x}" y="${y}" width="${w}" height="${h}" fill="var(--panel)" stroke="var(--line)" rx="3"/>`;
  const path=(d,c='var(--line)')=>`<path d="${d}" fill="none" stroke="${c}" stroke-width="1.5" marker-end="url(#flow-arrow)"/>`;
  function stage(f,t){
    if(f.freed!==undefined&&f.freed<=t+.00001)return 'free';
    if(f.segments.some(s=>s.flowStart<=t+.00001&&t<s.flowEnd-.00001))return 'passing';
    if(f.segments.some(s=>s.flowEnd<=t+.00001&&t<s.end-.00001))return 'media';
    if(f.queued!==undefined&&f.queued<=t+.00001)return 'batch';
    if(f.encodeEnd!==undefined&&f.encodeEnd<=t+.00001)return 'handoff';
    if(f.encodeStart!==undefined&&f.encodeStart<=t+.00001)return 'encode';
    return 'waiting';
  }
  function marker(f,x,y,r=5,label=false){
    return `<g data-frame="${f.id}" class="frame-mark"><circle cx="${x}" cy="${y}" r="${r}" fill="${color(f)}"/><title>${I.escape(T('frameSlot',{frame:f.id,slot:f.slot+1}))}</title>${label?txt(x,y-10,'F'+f.id,'middle'):''}</g>`;
  }
  function draw(t){
    if(!data)return;const svg=$('frame-flow'),W=Math.max(280,svg.getBoundingClientRect().width),small=W<720;
    const cols=small?8:12,cellH=25,page=+$('slot-page').value||0,start=page*96;
    const gx=12,gy=58,bw=small?W-24:W*.43-12,cw=bw/cols;
    const rows=Math.ceil(Math.min(96,data.slots-start)/cols),gh=rows*cellH;
    const ex=small?12:W*.47,ey=small?gy+gh+58:60,ew=small?W*.25:W*.22;
    const bx=small?W*.34:ex,by=small?ey:192,bw2=small?W*.34:ew,bh=142;
    const gate=small?W*.715:W*.742,mx=small?W*.76:W*.81,mw=W-mx-12;
    const H=small?by+bh+86:415;
    const captured=data.frames.filter(f=>f.captured<=t+.00001),active=captured.filter(f=>f.freed===undefined||f.freed>t+.00001);
    const occupied=new Map(active.map(f=>[f.slot,f])),ready=active.filter(f=>f.queued!==undefined&&f.queued<=t+.00001);
    const writing=data.writes.find(w=>w.start<=t+.00001&&t<w.end-.00001),done=captured.length-active.length;
    const submitted=captured.filter(f=>f.queued!==undefined&&f.queued<=t+.00001).reduce((n,f)=>n+f.bytes,0);
    const sample={batch:(submitted%F.BATCH)/F.MiB,
      queued:data.writes.filter(w=>w.ready<=t&&w.start>t).length};
    let s=`<title>${I.escape(T('flowTitle'))}</title><desc>${I.escape(T('flowDesc'))}</desc>`;
    s+='<defs><marker id="flow-arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="6" markerHeight="6" orient="auto"><path d="M0 0L8 4L0 8" fill="var(--dim)"/></marker></defs>';
    s+=txt(gx,20,T('capturedStats',{time:fmt(t/1000),captured:captured.length,freed:done}));
    s+=txt(gx,43,T('slotStats',{slots:data.slots,used:active.length,start:start+1,end:Math.min(data.slots,start+rows*cols)}));
    for(let i=0;i<rows*cols&&start+i<data.slots;i++){
      const slot=start+i,f=occupied.get(slot),x=gx+i%cols*cw,y=gy+Math.floor(i/cols)*cellH;
      const sd=f&&['media','passing'].includes(stage(f,t)),c=f?(sd?'var(--sd)':color(f)):'var(--line)';
      s+=`<g ${f?'data-frame="'+f.id+'" class="frame-mark"':''}><rect x="${x+1}" y="${y+1}" width="${cw-3}" height="${cellH-3}" fill="${c}" fill-opacity="${f ? 0.22 : 0.1}" stroke="${c}" stroke-opacity=".4"/>`;
      s+=txt(x+cw/2,y+17,f?String(f.id):'·','middle')+`<title>${I.escape(T('slotTitle',{slot:slot+1,frame:f?'F'+f.id+' · '+T(stageNames[stage(f,t)]):T('freeSlot')}))}</title></g>`;
    }
    const cpu=active.filter(f=>['waiting','encode','handoff'].includes(stage(f,t)));
    s+=box(ex,ey,ew,76)+txt(ex+8,ey+21,data.parameters.loss?T(small?'engineShort':'engine'):'LOSS OFF')+txt(ex+8,ey+42,data.parameters.loss?T(small?'lanesShort':'lanes'):T('rawBypass'));
    cpu.slice(0,2).forEach((f,i)=>{s+=marker(f,ex+ew-18,ey+25+i*31,5,true);});
    s+=box(bx,by,bw2,bh)+txt(bx+8,by+21,T('batchBuffer'))+txt(bx+8,by+42,small?`${fmt(sample.batch,1)}/64M`:`${fmt(sample.batch,1)} / 64 MiB`);
    s+=`<rect x="${bx+8}" y="${by+52}" width="${bw2-16}" height="6" fill="var(--line)"/><rect x="${bx+8}" y="${by+52}" width="${Math.min(1,sample.batch/64)*(bw2-16)}" height="6" fill="var(--raw)"/>`;
    const queued=ready.filter(f=>!f.segments.some(seg=>seg.final&&seg.flowEnd<=t+.00001));
    queued.slice(0,96).forEach((f,i)=>{const cc=Math.max(4,Math.floor((bw2-16)/5));s+=marker(f,bx+11+(i%cc)*5,by+71+Math.floor(i/cc)*5,1.6);});
    s+=txt(bx+8,by+bh-8,T('awaitingPassage',{n:queued.length})+(!small&&sample.queued?T('batchQueue',{n:sample.queued}):''));
    s+=box(mx,by,mw,bh)+txt(mx+8,by+21,T('media'))+txt(mx+8,by+41,`${data.parameters.speed} MB/s`);
    const sent=ready.filter(f=>f.segments.some(seg=>seg.flowEnd<=t+.00001&&t<seg.end-.00001));
    sent.slice(0,80).forEach((f,i)=>{const cc=Math.max(3,Math.floor((mw-16)/5));s+=marker(f,mx+11+i%cc*5,by+67+Math.floor(i/cc)*5,1.6);});
    s+=txt(mx+8,by+bh-8,T(writing?(small?'heldShort':'held'):(small?'newBatchShort':'newBatch')));
    s+=path(small?`M${gx+bw*.2} ${gy+gh}V${ey-20}H${ex+ew/2}V${ey}`:`M${gx+bw} ${ey+37}H${ex}`);
    s+=path(small?`M${ex+ew} ${ey+38}H${bx}`:`M${ex+ew/2} ${ey+76}V${by}`,'var(--loss)');
    s+=path(small?`M${gx+bw*.6} ${gy+gh}V${by-15}H${bx+bw2/2}V${by}`:`M${gx+bw} ${gy+gh-15}H${bx}`,'var(--raw)');
    s+=txt(small?W*.56:gx+bw+8,small?by-21:gy+gh-22,T('rawBypass'));
    s+=path(`M${bx+bw2} ${by+70}H${mx}`);
    s+=`<path d="M${gate} ${by+47}V${by+98}" stroke="${writing?'var(--sd)':'var(--bad)'}" stroke-width="${writing?2:5}"/>`;
    s+=txt(gate,by+26,T(writing?'gateOpen':'gateClosed'),'middle');
    if(writing)s+=txt(gate,by+115,T('batchNumber',{n:writing.number}),'middle');
    for(const f of ready){
      const seg=f.segments.find(a=>a.flowStart<=t+.00001&&t<a.flowEnd-.00001);
      if(seg){const fraction=(t-seg.flowStart)/(seg.flowEnd-seg.flowStart),xx=bx+bw2+fraction*(mx+mw/2-bx-bw2);
        s+=`<circle cx="${xx}" cy="${by+70}" r="9" fill="none" stroke="var(--sd)" stroke-width="2"/>`+marker(f,xx,by+70,6,true);}
    }
    s+=path(`M${mx+mw/2} ${by+bh}V${H-36}H${gx+bw/2}V${gy+gh+8}`,'var(--sd)');
    s+=txt(gx,H-12,T(small?'callbackShort':'callback'));
    if(data.stopped&&data.stopped.time<=t)s+=txt(gx,H-56,T('stoppedFlow',{time:fmt(data.stopped.time/1000),reason:I.reason(data.stopped.reason)}));
    svg.setAttribute('viewBox',`0 0 ${W} ${H}`);svg.innerHTML=s;
    if(captured.length!==lastCount){
      const selected=$('frame-picker').value;
      $('frame-picker').innerHTML=`<option value="">${T(captured.length?'followLatest':'noFrames')}</option>`+captured.map(f=>`<option value="${f.id}">${T('frameSlot',{frame:f.id,slot:f.slot+1})}</option>`).join('');
      if(captured.some(f=>String(f.id)===selected))$('frame-picker').value=selected;
      lastCount=captured.length;
    }
    const chosen=captured.find(f=>String(f.id)===$('frame-picker').value)||captured[captured.length-1];
    if(chosen){
      const f=chosen,when=(v,key)=>`${T(key)} ${fmt(v/1000)} s${v>t+.00001?T('notYet'):''}`;
      const pieces=[T('frameSlot',{frame:f.id,slot:f.slot+1}),when(f.captured,'traceCapture')];
      if(f.encodeStart!==undefined)pieces.push(when(f.encodeStart,'traceEncode'),when(f.encodeEnd,'traceEncoded'));
      if(f.rawReason)pieces.push(I.reason(f.rawReason));
      if(f.queued!==undefined)pieces.push(when(f.queued,'traceQueued'));
      if(f.segments.length)pieces.push(T('traceBatches',{n:f.segments.map(seg=>seg.batch).join(', ')}),when(f.segments[0].flowStart,'tracePassage'));
      pieces.push(f.freed!==undefined?when(f.freed,'traceReleased'):T('stillHeld'));
      $('frame-trace').textContent=pieces.join(' → ');
    }else $('frame-trace').textContent=T('traceEmpty');
  }
  function stop(){playing=false;$('play').textContent=T('play');}
  function setTime(t){$('time').value=String(Math.max(0,Math.min(10,t)));$('time').dispatchEvent(new Event('input'));}
  function loop(now){
    if(!playing)return;
    const current=window.FPFrameFlow.clock+(now-window.FPFrameFlow.lastTick)/1000*+$('play-speed').value;
    window.FPFrameFlow.clock=current;window.FPFrameFlow.lastTick=now;
    if(now-lastPaint>32){setTime(current);lastPaint=now;}
    if(current>=10){setTime(10);stop();return;}requestAnimationFrame(loop);
  }
  $('play').addEventListener('click',()=>{if(playing){stop();return;}
    if(+$('time').value>=10)setTime(0);playing=true;
    window.FPFrameFlow.clock=+$('time').value;window.FPFrameFlow.lastTick=performance.now();
    $('play').textContent=T('pause');requestAnimationFrame(loop);});
  $('restart').addEventListener('click',()=>{stop();setTime(0);});
  $('step').addEventListener('click',()=>{stop();if(!data)return;const period=1/data.parameters.fps;
    setTime((Math.floor((+$('time').value+1e-7)/period)+1)*period);});
  $('event-step').addEventListener('click',()=>{stop();const next=eventTimes.find(t=>t>+$('time').value*1000+.00001);
    setTime(next===undefined?10:next/1000);});
  $('slot-page').addEventListener('change',()=>draw(+$('time').value*1000));
  $('frame-picker').addEventListener('change',()=>{stop();draw(+$('time').value*1000);});
  $('time').addEventListener('input',e=>{if(e.isTrusted)stop();});
  $('frame-flow').addEventListener('click',e=>{const mark=e.target.closest('[data-frame]');if(!mark)return;
    stop();$('frame-picker').value=mark.dataset.frame;draw(+$('time').value*1000);});
  window.addEventListener('fpsup-languagechange',()=>{lastCount=-1;$('play').textContent=T(playing?'pause':'play');draw(+$('time').value*1000);});
  window.FPFrameFlow={clock:0,lastTick:0,draw,stop,setResult(result){stop();data=result;lastCount=-1;
    eventTimes=[...new Set(data.frames.flatMap(f=>[f.captured,f.encodeStart,f.encodeEnd,f.queued,f.freed,
      ...f.segments.flatMap(s=>[s.start,s.flowStart,s.flowEnd,s.end])]).filter(t=>Number.isFinite(t)&&t<=10000))].sort((a,b)=>a-b);
    const n=Math.ceil(data.slots/96);$('slot-page-label').hidden=n<=1;
    $('slot-page').innerHTML=Array.from({length:n},(_,i)=>`<option value="${i}">${i*96+1}–${Math.min(data.slots,(i+1)*96)}</option>`).join('');
    $('time').value='0';}};
})();
