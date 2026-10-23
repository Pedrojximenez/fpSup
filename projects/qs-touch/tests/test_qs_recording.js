const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../preview/qs-recording.js'),'utf8');
const model=vm.runInNewContext(source+'; qsRecording');
const plain=value=>JSON.parse(JSON.stringify(value));
let state=model.defaults();
for (const format of ['MOV','CDNG 8bit','CDNG 10bit','CDNG 12bit','CDNG 14bit']) {
  state=model.select(state,'format',format); assert.equal(state.format,format);
}
const raw=plain(state); assert.deepEqual(plain(model.select(state,'format','arbitrary')),raw);
state=model.select(state,'dc','HD');
assert.ok(model.resOptions(state).includes('FHD (2K)') && model.resOptions(state).includes('UHD (4K)'));
state=model.select(state,'res','FHD (2K)');
assert.equal(state.res.width,1920); assert.equal(state.res.height,1080);
state=model.select(state,'res','UHD (4K)');
assert.equal(state.res.width,3840); assert.equal(state.res.height,2160);
state=model.select(state,'dc','OG');
assert.equal(model.resLabel(state),'4K'); assert.equal(state.res.width,4096);
assert.ok(!model.resOptions(state).includes('FHD (2K)'));
for (const dc of ['OG','HD','S35','APS-C']) for (const res of ['1K','2K','3K','3.5K','4K']) {
  const s=model.select(model.select(state,'dc',dc),'res',res);
  assert.ok(s.res.width>0 && s.res.height>0);
  assert.ok(Math.abs(s.res.width/s.res.height-s.dc.width/s.dc.height)<0.003);
}
state=model.dimension(state,'dc','ratio','16:9');
assert.equal(state.dc.preset,'HD'); // Applying the ratio reaches the exact HD window.
state=model.dimension(state,'dc','width',4096);
assert.equal(state.dc.preset,'自訂'); assert.equal(state.dc.height,3375);
assert.equal(state.dc.ratio,model.ratioOf(4096,3375));
assert.equal(model.dcLabel(state),`CUSTOM(${state.dc.ratio})`);
const cropBefore=plain(state.dc);
state=model.dimension(state,'res','width',2016);
state=model.dimension(state,'res','height',1344);
assert.deepEqual(plain(state.dc),cropBefore); // Output dimensions do not rewrite the sensor crop.
assert.equal(state.res.preset,'自訂');
state=model.dimension(state,'dc','width',5000);
assert.equal(state.res.width,2016); assert.equal(state.res.height,1344); // Custom output is retained.
state=model.dimension(state,'res','ratio','3:2');
state=model.dimension(state,'res','height',1000);
assert.equal(state.res.width,2016); assert.equal(state.res.height,1000);
assert.equal(state.res.ratio,'2.02:1');
state=model.dimension(state,'res','ratio','16:9');
assert.equal(state.res.width,2016); assert.equal(state.res.height,1134);
assert.deepEqual(plain(model.restore(state)),plain(state));
for (const value of [0,-1,2.5,Infinity,NaN,16385,'4096']) {
  assert.deepEqual(plain(model.dimension(state,'dc','width',value)),plain(state));
}
const malformed=model.restore({format:'unknown',dc:{preset:'__proto__',width:0,height:NaN,ratio:'0:0'},res:null});
assert.deepEqual(plain(malformed),plain(model.defaults()));
const old=[]; old[4]='FHD'; old[6]='DNG';
const migrated=model.restore(null,old);
assert.equal(migrated.format,'CDNG 12bit'); assert.equal(migrated.dc.preset,'HD');
assert.equal(migrated.res.width,1920); assert.equal(migrated.res.height,1080);
for (const ratio of model.ratios) for (const field of ['width','height']) for (const edge of [1,model.limit]) {
  let s=model.dimension(state,'dc','ratio',ratio);
  s=model.dimension(s,'dc',field,edge);
  assert.ok(Number.isInteger(s.dc.width) && Number.isInteger(s.dc.height));
  assert.ok(s.dc.width>=1 && s.dc.height>=1 && s.dc.width<=model.limit && s.dc.height<=model.limit);
}
// Manual dimensions control the aspect; preset recognition requires both exact dimensions.
let recognized=model.defaults();
recognized=model.dimension(recognized,'dc','width',4000);
assert.equal(recognized.dc.height,4000); assert.equal(recognized.dc.ratio,'1:1');
assert.equal(model.dcLabel(recognized),'CUSTOM(1:1)');
for (const [width,height,preset,ratio] of [[6000,3375,'HD','16:9'],[6000,4000,'OG','3:2'],[4000,2250,'S35','16:9'],[4000,2667,'APS-C','3:2']]) {
  recognized=model.dimension(recognized,'dc','width',width);
  recognized=model.dimension(recognized,'dc','height',height);
  assert.equal(recognized.dc.preset,preset); assert.equal(recognized.dc.ratio,ratio);
  assert.equal(model.dcLabel(recognized),preset);
  assert.deepEqual(plain(model.restore(recognized)),plain(recognized));
}
recognized=model.dimension(recognized,'dc','width',3200);
recognized=model.dimension(recognized,'dc','height',1800);
assert.equal(recognized.dc.ratio,'16:9'); assert.equal(recognized.dc.preset,'自訂');
assert.equal(model.dcLabel(recognized),'CUSTOM(16:9)');
const stale=model.restore({format:'MOV',dc:{preset:'HD',width:6000,height:3500,ratio:'16:9'},res:{preset:'自訂',width:2048,height:1200,ratio:'自由'}});
assert.equal(stale.dc.height,3500); assert.equal(stale.dc.preset,'自訂'); assert.equal(stale.dc.ratio,'1.71:1');
assert.equal(stale.res.height,1200); assert.equal(stale.res.ratio,'1.71:1');
for (const [width,height,label] of [[2048,1200,'1.71:1'],[4096,1714,'2.39:1'],[3200,1800,'16:9'],
  [3000,2000,'3:2'],[4093,1711,'2.39:1'],[2000,1000,'2.00:1'],[1000,2000,'0.50:1']]) {
  assert.equal(model.ratioOf(width,height),label);
}
assert.ok(Number.parseFloat(model.ratioOf(1,16384))>0); // Do not round a valid thin window to zero.
const decimalRestore=model.restore({dc:{preset:'自訂',width:4093,height:1711,ratio:'4093:1711'}});
assert.equal(decimalRestore.dc.width,4093); assert.equal(decimalRestore.dc.height,1711);
assert.equal(model.dcLabel(decimalRestore),'CUSTOM(2.39:1)');
const oldMatching=model.restore({dc:{preset:'自訂',width:6000,height:3375,ratio:'自由'}});
assert.equal(oldMatching.dc.preset,'HD');
assert.deepEqual(plain(model.cropMm(model.defaults())),{width:35.9,height:23.9});
assert.deepEqual(plain(model.cropMm(model.select(model.defaults(),'dc','HD'))),{width:35.9,height:20.17});
for (let w=1;w<=model.limit;w+=127) {
  const s=model.dimension(recognized,'dc','width',w);
  assert.equal(s.dc.height,recognized.dc.height); assert.equal(s.dc.ratio,model.ratioOf(w,s.dc.height));
}
// Every output axis is bounded by its corresponding sensor crop axis, including old records.
let bounded=model.select(model.defaults(),'dc','S35');
assert.ok(!model.resOptions(bounded).includes('4K'));
const unchanged=plain(model.select(bounded,'res','4K'));
assert.deepEqual(unchanged,plain(bounded));
bounded=model.dimension(bounded,'res','width',8000);
assert.equal(bounded.res.width,4000); assert.equal(bounded.res.height,1728);
bounded=model.dimension(bounded,'res','height',8000);
assert.equal(bounded.res.height,2250); assert.equal(bounded.res.ratio,'16:9');
bounded=model.dimension(bounded,'dc','width',1200);
bounded=model.dimension(bounded,'dc','height',800);
assert.equal(bounded.res.width,1200); assert.equal(bounded.res.height,800);
assert.deepEqual(plain(model.resOptions(bounded)),['1K','CUSTOM(3:2)']);
bounded=model.dimension(bounded,'res','ratio','1:1');
assert.equal(bounded.res.width,800); assert.equal(bounded.res.height,800);
const migratedLarge=model.restore({dc:{preset:'自訂',width:1977,height:1600,ratio:'16:9'},res:{preset:'自訂',width:4000,height:2160,ratio:'16:9'}});
assert.equal(migratedLarge.res.width,1977); assert.equal(migratedLarge.res.height,1600);
const shrinkStandard=model.dimension(model.select(model.defaults(),'res','4K'),'dc','width',3000);
assert.equal(shrinkStandard.res.preset,'自訂'); assert.ok(shrinkStandard.res.width<=3000);
for (const [width,height] of [[1,16384],[16384,1],[1,1],[900,600],[1977,2160],[4000,2250]]) {
  let s=model.dimension(model.dimension(model.defaults(),'dc','width',width),'dc','height',height);
  for (const res of model.resOptions(s)) {
    const next=model.select(s,'res',res);
    assert.ok(next.res.width<=width && next.res.height<=height);
    assert.equal(model.resLabel(next),res);
  }
  for (const ratio of model.ratios) {
    s=model.dimension(s,'res','ratio',ratio);
    s=model.dimension(s,'res','width',model.limit);
    s=model.dimension(s,'res','height',model.limit);
    assert.ok(s.res.width<=width && s.res.height<=height);
    assert.deepEqual(plain(model.restore(s)),plain(s));
  }
}
// Custom labels stay consistent with the selectable value, including bounded legacy state.
const customOutput=model.dimension(model.dimension(model.defaults(),'res','width',2048),'res','height',1200);
assert.equal(model.resLabel(customOutput),'CUSTOM(1.71:1)');
assert.ok(model.resOptions(customOutput).includes(model.resLabel(customOutput)));
assert.equal(model.resLabel(model.restore(customOutput)),'CUSTOM(1.71:1)');
assert.equal(model.resLabel(model.select(customOutput,'res','2K')),'2K');
const oldOversize=model.restore({format:'CDNG 8bit',dc:{preset:'S35',width:4000,height:2250,ratio:'16:9'},
  res:{preset:'自訂',width:16384,height:2304,ratio:'7.11:1'}});
assert.equal(model.dcLabel(oldOversize),'S35');
assert.equal(model.resLabel(oldOversize),'CUSTOM(16:9)');
assert.equal(oldOversize.res.width,4000); assert.equal(oldOversize.res.height,2250);
assert.ok(model.resOptions(oldOversize).includes('CUSTOM(16:9)'));
console.log('PASS: formats, independent axes, cinema aspect, DC and RES CUSTOM labels/options, preset recognition, mm, migration and RES/DC bounds');
