// Unit-test the page's actual render/change handlers with a minimal DOM.
// No browser, camera or external service is involved.
const fs = require('fs'), assert = require('assert');
const page = fs.readFileSync(process.env.MERGE_INDEX || __dirname + '/index.html', 'utf8');
const grab = id => page.match(new RegExp(`<script id="${id}"[^>]*>([\\s\\S]*?)</script>`))[1];
const elements = new Map(), handlers = new Map();
const el = id => {
  if (!elements.has(id)) elements.set(id, {innerHTML:'', textContent:'', style:{}, dataset:{}, setAttribute(){}});
  return elements.get(id);
};
global.atob = s => Buffer.from(s, 'base64').toString('binary');
global.localStorage = {getItem: () => 'zh', setItem(){}};
global.document = {
  documentElement: {dataset:{}},
  getElementById: id => id === 'cat' ? {textContent:grab('cat')} : el(id),
  querySelector: s => s.startsWith('#') ? el(s.slice(1)) : null,
  querySelectorAll: () => [],
  addEventListener: (name, fn) => handlers.set(name, fn),
};
const api = new Function(grab('compose') + grab('ui') +
  '\nreturn {BOOT, CAT, DATA_OFF, compose, checks, readme, zipFor, picked:()=>picked, history:p=>versionHistory(p,T[lang])};')();
const change = (dataset, checked) => handlers.get('change')({target:{dataset, checked}});
const startup = () => el('startup').innerHTML;
const checked = key => new RegExp(`data-boot="${key}" checked`).test(startup());
assert(checked('instant') && !checked('fast'));
assert(!checked('manager'));
assert(startup().includes('瞬間啟動') && startup().includes('快速啟動'));
assert(startup().includes('type="checkbox" data-boot="fast"') && !startup().includes('role="switch"'));
const id = api.CAT.products[0].id;
change({id}, true);
assert.deepStrictEqual(api.picked(), [id]);
const original = api.compose([id]).files;
change({boot:'fast'}, true);
assert(checked('instant') && checked('fast'));
assert.deepStrictEqual(api.picked(), [id]);
assert(api.checks([id]).every(r => r.ok));
const now = api.compose([id]).files;
assert.notStrictEqual(now.find(f => f.name === 'AutoRun.txt').sha256, original.find(f => f.name === 'AutoRun.txt').sha256);
assert.strictEqual(now.find(f => f.p).sha256, original.find(f => f.p).sha256);
change({boot:'instant'}, false);
assert(!checked('instant') && checked('fast'));
assert.deepStrictEqual(api.picked(), [id]);
change({boot:'fast'}, false);
assert(!checked('instant') && !checked('fast'));
assert(api.checks([id]).every(r => r.ok));
change({boot:'instant'}, true);
assert(checked('instant') && !checked('fast'));
assert(api.checks([id]).every(r => r.ok));
change({id}, false);
change({boot:'manager'}, true);
assert(checked('manager') && !el('dl').disabled);
assert(api.compose([]).files.some(f => f.name === 'fpSup/UI/ALLSUPS.BIN'));
change({boot:'manager'}, false);
assert(!checked('manager') && el('dl').disabled);
const lab = api.CAT.pending.find(p => p.id === 'res-lab');
assert(lab && lab.stage === 'dev');
assert(!api.CAT.products.some(p => p.id === 'res-lab'));
assert(el('tiles').innerHTML.includes('RES-Lab<span class="soon">開發中'));
assert(!el('tiles').innerHTML.includes('data-id="res-lab"'));
assert(/<input type="checkbox" disabled[^>]*>\s*<span class="name">RES-Lab/.test(el('tiles').innerHTML));
for (const [lang, label] of [['en','In development'], ['cn','开发中'], ['zh','開發中']]){
  handlers.get('click')({target:{closest:()=>({dataset:{lang}})}});
  assert(el('tiles').innerHTML.includes(`RES-Lab<span class="soon">${label}`));
  assert(!el('tiles').innerHTML.includes('data-id="res-lab"'));
}
for (const id of ['desqueeze', 'tap-to-zoom']){
  const p = api.CAT.products.find(p => p.id === id);
  assert(p && p.author === 'Jose Hurtado' && p.category === 'monitor');
  assert(el('tiles').innerHTML.includes(`data-id="${id}"`));
  assert(el('tiles').innerHTML.includes(`../../guide/${id}.html`));
  change({id}, true);
}
assert.deepStrictEqual(api.picked(), ['desqueeze', 'tap-to-zoom']);
assert(api.checks(api.picked()).every(r => r.ok) && !el('dl').disabled);
const monitorFiles = api.compose(api.picked()).files.filter(f => f.p);
assert.deepStrictEqual(monitorFiles.map(f => f.name), ['fpSup/41DSQZ.BIN', 'fpSup/42TAPZ.BIN']);
assert(el('tiles').innerHTML.includes('作者 <b>Jose Hurtado</b>'));
assert(api.readme(api.picked()).includes('by Jose Hurtado'));
for (const id of ['desqueeze', 'tap-to-zoom']) change({id}, false);
assert(el('dl').disabled);
console.log('passed: defaults, checkbox controls, all four boot choices, unchanged sup selections, download checks and pending RES-Lab in three languages, and Jose monitor selection/attribution');

// History is available on every tile, including Sups without a release.
for (const p of api.CAT.products.concat(api.CAT.pending || [])){
  assert(el('tiles').innerHTML.includes(`data-history="${p.id}"`));
  const html = api.history(p);
  assert(html.includes('版本改動'));
  if (p.history.length){
    for (const h of p.history){
      assert(html.includes(h.label));
      if (h.source && h.source_kind !== 'manifest') assert(html.includes(`href="${h.source}"`));
    }
    assert.strictEqual(p.history.filter(h => h.current).length, p.release ? 1 : 0);
  } else assert(html.includes('尚無版本改動紀錄'));
}
const raw = api.CAT.products.find(p => p.id === 'raw-view');
const rawLegacy = ['0.3.0test','0.2.3test','0.2.2test','0.2.1test','0.2.0test','0.1.0test'];
assert.deepStrictEqual(raw.history.filter(h => rawLegacy.includes(h.version)).map(h => h.version), rawLegacy);
const beforeHistory = Buffer.from(api.zipFor(['raw-view']));
const toggle = open => handlers.get('toggle')({target:{dataset:{history:'raw-view'},open}});
const language = lang => handlers.get('click')({target:{closest:()=>({dataset:{lang}})}});
toggle(true);
change({id:'raw-view'}, true);
assert(el('tiles').innerHTML.includes('data-history="raw-view" open'));
language('en');
assert(api.history(raw).includes('Version changes') && api.history(raw).includes('Currently offered'));
assert(api.history(raw).includes('data-history="raw-view" open'));
language('cn');
assert(api.history(raw).includes('版本改动') && api.history(raw).includes('完整版本说明'));
language('zh');
toggle(false);
change({id:'raw-view'}, false);
assert(!api.history(raw).includes('data-history="raw-view" open'));
assert.deepStrictEqual(api.picked(), []);
assert(Buffer.from(api.zipFor(['raw-view'])).equals(beforeHistory));
const stopfx = api.CAT.products.find(p => p.id === 'stopfx');
assert(stopfx && stopfx.author === 'Ruari');
assert.strictEqual(stopfx.sha256, 'f9f26a092c5676ead5771ba8be4aac9c3734e9ed0cd144002a73b3f6b657c9d9');
assert(el('tiles').innerHTML.includes('作者 <b>Ruari</b>'));
for (const id of ['stopfx', 'fcap']){
  change({id}, true);
  assert.deepStrictEqual(api.compose(api.picked()).on, [id]);
  assert(api.checks(api.picked()).every(r => r.ok));
  change({id}, false);
}
// Ticking Lossless ticks FCAP too (user 2026-10-15), but FCAP stays optional
change({id:'lossless'}, true);
assert.deepStrictEqual(api.picked(), ['lossless', 'fcap']);
change({id:'fcap'}, false);
assert.deepStrictEqual(api.compose(api.picked()).on, ['lossless']);
assert(api.checks(api.picked()).every(r => r.ok));
change({id:'lossless'}, false);
change({id:'fcap'}, true);                         // FCAP first: nothing ticked twice
change({id:'lossless'}, true);
assert.deepStrictEqual(api.picked(), ['fcap', 'lossless']);
change({id:'fcap'}, false);
change({id:'stopfx'}, true);
assert.deepStrictEqual(api.compose(api.picked()).files.filter(f => f.p).map(f => f.name),
  ['fpSup/05STOPFX.BIN', 'fpSup/10LOSS.BIN']);
assert(api.readme(api.picked()).includes('by Ruari'));
assert(el('tree').innerHTML.includes('STOPFX') && !el('tree').innerHTML.includes('.BIN'));
assert.strictEqual(el('status').textContent, '已準備好，可以下載。');
for (const id of ['stopfx', 'lossless']) change({id}, false);
const res = api.CAT.products.find(p => p.id === 'res-custom');
assert(!/consumer|dev-r19|RCD|宣告/.test(api.history(res)));
assert(!api.history(stopfx).includes('manifest.json'));
assert(!page.includes('<small>Loader v3</small>') && !page.includes('id="hashtbl"'));
assert.strictEqual(api.CAT.products.find(p => p.id === 'gyro2').credits.length, 0);
const unsafe = api.history({id:'example',name:'<example>',history:[{label:'v1',
  changes:{en:['<script>unsafe</script>'],zh:['<script>unsafe</script>']}}]});
assert(!unsafe.includes('<script>') && unsafe.includes('&lt;script&gt;'));
console.log('passed: boot choices, selections, download checks, version history, languages and retained disclosure state');
