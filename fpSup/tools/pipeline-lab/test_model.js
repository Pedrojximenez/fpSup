const assert=require('node:assert/strict'),M=require('./model.js');
const fast=M.simulate({loss:false,speed:1000});
assert.equal(fast.compressed,0);assert.equal(fast.captured,600);assert.equal(fast.raw,600);
assert.equal(fast.stopped,null);assert(fast.pending>0);assert(fast.freed>500);
const slow=M.simulate({loss:false,speed:20,slotsMode:'stock'});
assert(slow.stopped);assert(slow.stopped.time<5000);assert.equal(slow.peakFrames,94);
const on=M.simulate({loss:true,speed:270,rawMiB:708});
assert(on.compressed>on.raw);assert(on.dataRate<fast.dataRate);
assert(on.peakRam>fast.peakRam,'more compressed files must hold RAW-size allocations until a batch completes');
const overloaded=M.simulate({loss:true,width:3840,height:2160,fps:119.88,speed:3000,rawMiB:2048});
assert(overloaded.busyRaw>0,'one engine and two lanes cannot encode every arrival');
assert(overloaded.compressed<overloaded.captured/2);
assert.equal(M.plan({width:1936,height:1090,bits:12,fps:59.94,latencyMs:481.873,ratio:.25,codecFhdMs:15.6}).slots,428);
assert.throws(()=>M.simulate({speed:0}));assert.throws(()=>M.simulate({ratio:1.1}));
assert.throws(()=>M.simulate({ratio:NaN}));assert.throws(()=>M.simulate({handoffMs:NaN}));
const noSaving=M.simulate({ratio:1,speed:1000});
assert.equal(noSaving.compressed,0);assert(noSaving.frames.some(f=>f.rawReason==='壓縮未縮小'));
for(const r of [fast,slow,on,overloaded]){
  assert.equal(r.compressed+r.raw+r.inflight,r.captured);
  assert.equal(r.freed+r.pending,r.captured);
  assert(r.samples.every(s=>s.ram>=0&&s.frames<=r.slots-2));
  assert(r.writes.every(w=>w.bytes===M.BATCH));
  for(const f of r.frames){
    assert(f.slot>=0&&f.slot<r.slots);
    if(f.freed!==undefined)assert.equal(f.freed,f.writeEnd);
    assert(f.segments.every(s=>s.flowEnd<=s.end&&s.flowStart>=s.start));
  }
}
const held=M.simulate({handoffMs:100,speed:1000,rawMiB:2048});
assert(held.busyRaw>0);assert.equal(held.compressed+held.raw+held.inflight,held.captured);
console.log('Queue conservation, native slot formula, RAW retention, overload and input checks passed.');
