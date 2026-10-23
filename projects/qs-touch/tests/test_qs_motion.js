const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../preview/qs-motion.js'),'utf8');
const {qsMotionStart:start,qsMotionStep:step,qsMotionSample:sample,qsMotionVelocity:velocity,
  qsPagerDestination:destination,qsPagerStart:pager,qsPagerStep:pagerStep}=
  vm.runInNewContext(source+'; ({qsMotionStart,qsMotionStep,qsMotionSample,qsMotionVelocity,qsPagerDestination,qsPagerStart,qsPagerStep})');
const near=(a,b,epsilon=1e-8)=>assert.ok(Math.abs(a-b)<epsilon,`${a} != ${b}`);

// Release starts at exactly the last dragged position and velocity.
const handoff=start(-140,-1.4,-328);
step(handoff,0); near(handoff.x,-140); near(handoff.velocity,-1.4);
step(handoff,0.001); near((handoff.x+140)/0.001,-1.4,0.0001);
assert.ok(handoff.x < -140);

// Refresh rate and missed frames do not change the physical trajectory.
for (const ms of [8,16,33,80,120]) {
  const one=start(-80,-0.7,-328),split=start(-80,-0.7,-328);
  step(one,ms); step(split,ms/2); step(split,ms/2);
  near(one.x,split.x); near(one.velocity,split.velocity);
}

// A finger reversing direction at release must not abruptly reverse velocity.
const reverse=start(-120,0.8,-328);
step(reverse,0.001); assert.ok(reverse.x > -120);

// Both directions, snap-back and overscroll all converge in bounded time.
for (const width of [288,328,704,720]) for (const sign of [-1,1]) for (const target of [0,sign*width]) {
  const s=start(sign*width*0.42,sign*width/200,target);
  for (let n=0;n<100 && !s.done;++n) step(s,[8,16,33][n%3]);
  assert.ok(s.done); near(s.x,target); near(s.velocity,0); assert.ok(s.elapsed<750);
}

// Velocity comes from recent movement; a pause removes stale momentum.
const samples=[];
sample(samples,0,0); sample(samples,-40,20); sample(samples,-80,40);
near(velocity(samples),-2);
near(velocity(samples,55),-2); // A button-up at the same position does not dilute movement.
near(velocity(samples,104),0); // An actual pause does clear momentum.
sample(samples,-80,200); near(velocity(samples),0);
sample(samples,-60,220); near(velocity(samples),1);
for (let n=221;n<2000;++n) sample(samples,n,n);
assert.ok(samples.length<=10);
const length=samples.length; sample(samples,1,0); assert.equal(samples.length,length);
console.log('PASS: continuous release position/velocity, frame-rate independence, reversal, bounded settling, recent velocity');

// Deliberate paging: short slow movement stays, flicks page, reversal comes back.
for (const width of [288,328,704,720]) {
  assert.equal(destination(1,-width*0.1,0.02,width,3),1);
  assert.equal(destination(1,-width*0.55,0,width,3),2);
  assert.equal(destination(1,width*0.55,0,width,3),0);
  assert.equal(destination(1,-width*0.1,-1,width,3),2);
  assert.equal(destination(1,-width*0.7,1,width,3),1);
  assert.equal(destination(0,width*0.6,1,width,3),0);
  assert.equal(destination(2,-width*0.6,-1,width,3),2);
  for (const v of [-8,-1,0,1,8]) for (const target of [0,-width]) {
    const s=pager(-width*0.35,v,target,width),min=Math.min(s.x,target),max=Math.max(s.x,target);
    for (let n=0;n<40 && !s.done;++n) {
      pagerStep(s,8); assert.ok(s.x>=min-1e-8 && s.x<=max+1e-8);
    }
    assert.ok(s.done && s.elapsed<=112); near(s.x,target);
  }
}
// Even a zero-speed release must move decisively on the very next display frame.
for (const width of [288,328,704,720]) for (const from of [-width*0.05,-width*0.5,-width*0.95]) {
  for (const target of [0,-width]) {
    const p=pager(from,0,target,width),distance=Math.abs(target-from);
    pagerStep(p,16);
    assert.ok(Math.abs(p.x-from)>=distance*0.25);
    const speeds=[Math.abs(p.velocity)];
    while (!p.done) { pagerStep(p,8); speeds.push(Math.abs(p.velocity)); }
    for (let n=1;n<speeds.length;n++) assert.ok(speeds[n]<=speeds[n-1]+1e-8);
  }
}
const p=pager(-140,-1.4,-328,328); pagerStep(p,0.001);
assert.ok((p.x+140)/0.001<=-1.4); // No restart from rest or slowdown at hand-off.
assert.ok(pager(0,0,0,328).done);
console.log('PASS: half-page distance, flick/reversal, boundaries, immediate ease-out, monotone deceleration, snap within 110ms');
