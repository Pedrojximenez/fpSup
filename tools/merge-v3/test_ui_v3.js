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
  '\nreturn {BOOT, CAT, DATA_OFF, compose, checks, picked:()=>picked};')();
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
console.log('passed: defaults, checkbox controls, all four boot choices, unchanged sup selections, download checks and pending RES-Lab in three languages');
