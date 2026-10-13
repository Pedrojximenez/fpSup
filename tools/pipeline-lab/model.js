/* Deterministic queue model. CPU use is never extrapolated from this model.
 * Mirror slot_capacity.c/memory_budget.c arithmetic; keep 64 MiB fixed. */
(function(root) {
  'use strict';
  const MiB=1048576, BATCH=64*MiB, PREFIX=0x13400;
  function plan(p) {
    const raster=Math.ceil(p.width*p.height*p.bits/8/512)*512;
    const raw=PREFIX+raster, charge=Math.ceil((0x15400+raster+64)/1024)*1024;
    const floor=PREFIX+Math.ceil(p.width*p.height/8);
    const fps=Math.ceil(p.fps), latency=Math.min(1000,Math.max(100,p.latencyMs));
    const slots=Math.max(96,Math.ceil((2*Math.ceil(BATCH/floor)+Math.ceil(fps*latency/1000)+6)/4)*4);
    const reserveFrames=2*Math.ceil(BATCH/raw)+Math.ceil(fps*latency/1000)+6;
    return {raw,charge,floor,slots,reserveFrames,reserve:reserveFrames*charge,
      compressed:Math.min(raw,Math.max(floor,Math.ceil((PREFIX+raster*p.ratio)/1024)*1024)),
      codecMs:p.codecFhdMs*p.width*p.height/(1936*1090)};
  }
  function simulate(input) {
    const p=Object.assign({width:1936,height:1090,bits:12,fps:59.94,loss:true,
      speed:270,ratio:.25,codecFhdMs:14.4,latencyMs:250,slotsMode:'expanded',
      rawMiB:708,handoffMs:2.5,durationMs:10000},input);
    if (![p.width,p.height,p.bits,p.fps,p.speed,p.rawMiB,p.codecFhdMs,p.latencyMs,p.durationMs].every(x=>Number.isFinite(x)&&x>0)
        ||!Number.isFinite(p.ratio)||!Number.isFinite(p.handoffMs)
        ||p.ratio<=0||p.ratio>1||p.width>8192||p.height>8192||p.fps>240
        ||p.codecFhdMs<=0||p.latencyMs<=0||p.handoffMs<0) throw Error('參數超出模型範圍');
    const q=plan(p),slots=p.slotsMode==='stock'?96:q.slots;
    let time=0,nextArrival=0,nextSample=0,engine=null,waiting=null,sdEnd=Infinity;
    let batch=[],batchBytes=0,sd=null,sdQueue=[],active=new Map(),handoffs=[];
    let captured=0,compressed=0,raw=0,busyRaw=0,pressureRaw=0,freed=0,totalBytes=0;
    let peakFrames=0,peakRam=0,stopped=null,batches=0;
    const samples=[],jobs=[],writes=[],spares=p.loss?2*q.charge:0,events=[],frames=[];
    const freeSlots=Array.from({length:slots},(_,i)=>i),byId=new Map();
    function used(){return active.size*q.charge+spares;}
    function startSd(b) {
      sd=b;sdEnd=time+b.bytes/(p.speed*1e6)*1000;
      let offset=0;
      b.pieces.forEach(piece=>{
        const f=byId.get(piece.id),flowStart=time+offset/(p.speed*1e6)*1000;
        offset+=piece.bytes;
        f.segments.push({start:time,end:sdEnd,flowStart,flowEnd:time+offset/(p.speed*1e6)*1000,
          bytes:piece.bytes,batch:b.number,final:piece.final});
        if(f.writeStart===undefined)f.writeStart=time;
        if(piece.final)f.writeEnd=sdEnd;
      });
      writes.push({start:time,end:sdEnd,ready:b.ready,bytes:b.bytes,frames:b.pieces.length,number:b.number});
    }
    function flush() {
      if (!batch.length)return;
      const b={pieces:batch,bytes:batchBytes,number:++batches,ready:time};batch=[];batchBytes=0;
      b.pieces.forEach(piece=>{const f=byId.get(piece.id);f.batches.push(b.number);if(f.gateOpen===undefined)f.gateOpen=time;});
      if(sd)sdQueue.push(b);else startSd(b);
    }
    function enqueue(frame,isCompressed) {
      const bytes=isCompressed?q.compressed:q.raw;
      const f=byId.get(frame);f.mode=isCompressed?'loss':'raw';f.bytes=bytes;f.queued=time;
      totalBytes+=bytes;
      let left=bytes;
      while(left){
        const part=Math.min(BATCH-batchBytes,left);left-=part;
        batch.push({id:frame,bytes:part,final:left===0});batchBytes+=part;
        if(batchBytes>=BATCH)flush();
      }
      if(isCompressed)compressed++;else raw++;
    }
    function kick(frame) {
      engine={frame,end:time+q.codecMs};
      const f=byId.get(frame);f.encodeStart=time;f.encodeEnd=engine.end;
      jobs.push({start:time,end:engine.end,frame});
    }
    function capture() {
      if (active.size>=slots-2 || used()+q.charge>p.rawMiB*MiB) {
        stopped={time,reason:active.size>=slots-2?'位置不足':'RAW 配置不足'};
        return;
      }
      const id=++captured;active.set(id,time);
      const f={id,slot:freeSlots.shift(),captured:time,mode:null,rawReason:null,segments:[],batches:[]};
      frames.push(f);byId.set(id,f);
      peakFrames=Math.max(peakFrames,active.size);peakRam=Math.max(peakRam,used());
      const free=p.rawMiB*MiB-used();
      if(!p.loss||id===1){f.rawReason=p.loss?'首幀 RAW':'LOSS 關閉';enqueue(id,false);return;}
      if(free<=q.reserve){pressureRaw++;f.rawReason='記憶體保護';enqueue(id,false);return;}
      if((engine?1:0)+(waiting?1:0)+handoffs.length>=2){busyRaw++;f.rawReason='兩通道忙碌';enqueue(id,false);return;}
      if(!engine)kick(id);
      else if(!waiting)waiting=id;
      else {busyRaw++;f.rawReason='兩通道忙碌';enqueue(id,false);}
    }
    // Discrete event order: media completion, encoding completion, handoff,
    // then capture. No USB, renderer, or wall clock is involved.
    while(time<=p.durationMs) {
      if(sdEnd<=time+1e-6){
        sd.pieces.forEach(piece=>{
          if(piece.final&&active.delete(piece.id)){freed++;const f=byId.get(piece.id);f.freed=time;freeSlots.push(f.slot);}
        });sd=null;sdEnd=Infinity;
        if(sdQueue.length)startSd(sdQueue.shift());
      }
      if(engine&&engine.end<=time+1e-6){
        handoffs.push({id:engine.frame,end:time+p.handoffMs});engine=null;
        if(waiting){const id=waiting;waiting=null;kick(id);}
      }
      while(handoffs.length&&handoffs[0].end<=time+1e-6){
        const id=handoffs.shift().id,saving=q.compressed<q.raw;
        if(!saving)byId.get(id).rawReason='壓縮未縮小';
        enqueue(id,saving);
      }
      if(!stopped&&nextArrival<=time+1e-6){capture();nextArrival+=1000/p.fps;}
      if(nextSample<=time+1e-6){
        samples.push({time,frames:active.size,ram:used()/MiB,batch:batchBytes/MiB,
          queued:sdQueue.length,encoded:compressed,raw,completed:freed});nextSample+=50;
      }
      const next=Math.min(stopped?Infinity:nextArrival,engine?engine.end:Infinity,
        handoffs.length?handoffs[0].end:Infinity,sdEnd,nextSample,p.durationMs);
      if(next<=time+1e-7){if(time===p.durationMs)break;time+=1e-4;}else time=next;
    }
    events.push({time:p.durationMs,kind:'stop',pending:active.size});
    return {parameters:p,plan:q,slots,captured,compressed,raw,busyRaw,pressureRaw,
      inflight:(engine?1:0)+(waiting?1:0)+handoffs.length,
      freed,pending:active.size,peakFrames,peakRam:peakRam/MiB,totalBytes,
      dataRate:totalBytes/(p.durationMs/1000)/1e6,batches,stopped,samples,jobs,writes,events,
      frames,finalBatchMiB:batchBytes/MiB,queuedBatches:sdQueue.length};
  }
  const api={MiB,BATCH,plan,simulate};
  if(typeof module==='object'&&module.exports)module.exports=api;
  else root.FPPipeline=api;
})(typeof globalThis!=='undefined'?globalThis:this);
