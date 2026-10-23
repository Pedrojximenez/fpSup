/* Pure presentation motion, inserted into the controller's private scope. */
function qsMotionStart(x,velocity,target) {
  return {x,velocity,target,elapsed:0,done:false};
}
function qsMotionStep(state,ms) {
  if (state.done || !Number.isFinite(ms) || ms<=0) return state;
  // Exact critically damped solution: position and velocity survive hand-off.
  const omega=0.028, displacement=state.x-state.target;
  const c=state.velocity+omega*displacement, decay=Math.exp(-omega*ms);
  state.x=state.target+(displacement+c*ms)*decay;
  state.velocity=(state.velocity-omega*c*ms)*decay;
  state.elapsed+=ms;
  if ((Math.abs(state.x-state.target)<0.25 && Math.abs(state.velocity)<0.008) || state.elapsed>=700) {
    state.x=state.target; state.velocity=0; state.done=true;
  }
  return state;
}
function qsMotionSample(samples,x,ms) {
  if (!Number.isFinite(x) || !Number.isFinite(ms)) return;
  const last=samples[samples.length-1];
  if (last && ms<last.ms) return;
  if (last && ms===last.ms) last.x=x;
  else samples.push({x,ms});
  while (samples.length>1 && (samples[0].ms<ms-80 || samples.length>10)) samples.shift();
}
function qsMotionVelocity(samples,atMs=samples[samples.length-1]?.ms) {
  if (samples.length<2) return 0;
  const first=samples[0],last=samples[samples.length-1],dt=last.ms-first.ms;
  if (atMs-last.ms>=64) return 0;
  return dt>0 ? Math.max(-8,Math.min(8,(last.x-first.x)/dt)) : 0;
}

/* Shared quick snap for pointer release and the end of horizontal wheel input. */
function qsPagerDestination(page,offset,velocity,width,count) {
  const flick=Math.abs(velocity)>=Math.max(0.35,width*0.0008) && Math.abs(offset)>=8;
  let destination;
  if (flick) destination=Math.sign(velocity)===Math.sign(offset) ? page-Math.sign(velocity) : page;
  else destination=page-Math.round(offset/width);
  return Math.max(0,Math.min(count-1,Math.max(page-1,Math.min(page+1,destination))));
}
function qsPagerStart(x,velocity,target,width) {
  const distance=Math.abs(target-x),forward=Math.max(0,velocity*Math.sign(target-x));
  if (distance<0.5) return {x:target,velocity:0,target,from:x,slope:0,duration:0,elapsed:0,done:true};
  const ceiling=60+50*Math.min(1,distance/width);
  const duration=Math.max(55,Math.min(ceiling,forward>0 ? distance/forward*1.5 : ceiling));
  // A release is already in motion: use a fast ease-out, never ease in from rest.
  const slope=Math.max(2,Math.min(3,forward*duration/distance));
  return {x,velocity:(target-x)*slope/duration,target,from:x,slope,duration,elapsed:0,done:false};
}
function qsPagerStep(state,ms) {
  if (state.done || !Number.isFinite(ms) || ms<=0) return state;
  state.elapsed+=ms;
  const t=Math.min(1,state.elapsed/state.duration),t2=t*t,t3=t2*t,delta=state.target-state.from;
  state.x=state.from+delta*((-2*t3+3*t2)+state.slope*(t3-2*t2+t));
  state.velocity=delta/state.duration*((-6*t2+6*t)+state.slope*(3*t2-4*t+1));
  if (t===1 || Math.abs(state.target-state.x)<0.5) { state.x=state.target; state.velocity=0; state.done=true; }
  return state;
}
