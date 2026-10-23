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
  '\nreturn {BOOT, CAT, DATA_OFF, compose, checks, readme, picked:()=>picked};')();
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
if (api.CAT.products.some(p => p.id === 'res-lab')){
  const lab = api.CAT.products.find(p => p.id === 'res-lab');
  assert.strictEqual(lab.name, 'RES-Lab v0.1.0test');
  assert.strictEqual(lab.file, '50RES-Lab v0.1.0test.BIN');
  assert(el('tiles').innerHTML.includes('RES-Lab v0.1.0test<span class="m">開發版'));
  change({id:'res-lab'}, true);
  assert.deepStrictEqual(api.picked(), ['res-lab']);
  assert(/data-boot="manager" checked disabled/.test(startup()));
  assert(/data-id="res-custom" checked disabled/.test(el('tiles').innerHTML));
  assert(!el('dl').disabled && el('tree').innerHTML.includes('ALLSUPS.BIN'));
  assert(api.compose(api.picked()).on.includes('res-custom'));
  assert(!api.compose(api.picked()).files.some(f => f.name.endsWith('.RCD')));
  const file = api.CAT.products.find(p => p.id === 'res-custom').data_files[0].path;
  change({file,of:'res-custom'}, true);
  assert(api.compose(api.picked()).files.some(f => f.name === file));
  change({file,of:'res-custom'}, false);
  assert(!api.compose(api.picked()).files.some(f => f.name.endsWith('.RCD')));
  change({boot:'fast'}, true);
  assert(!el('dl').disabled && checked('fast'));
  change({id:'res-lab'}, false);
  assert(!checked('manager') && el('dl').disabled);
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
console.log('passed: defaults, checkbox controls, all four boot choices, unchanged sup selections and download checks');
