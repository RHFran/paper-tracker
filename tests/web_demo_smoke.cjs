/* Dependency-free interaction smoke test. This models the DOM, not browser layout. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.resolve(__dirname, '../docs');
const html = fs.readFileSync(path.join(root, 'index.html'), 'utf8');
class Node {
  constructor(tag = 'div') {
    this.tagName = tag; this.children = []; this.dataset = {}; this.attrs = {}; this.events = {}; this.value = ''; this._text = ''; this.className = '';
    this.classList = { toggle: (name, enabled) => { const classes = new Set(this.className.split(' ')); enabled ? classes.add(name) : classes.delete(name); this.className = [...classes].join(' '); } };
  }
  set textContent(value) { assert.notEqual(value, undefined, 'missing translation'); this._text = String(value); this.children = []; }
  get textContent() { return this._text + this.children.map(child => child.textContent).join(''); }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this._text = ''; this.children = children; }
  setAttribute(name, value) { this.attrs[name] = value; }
  addEventListener(type, callback) { this.events[type] = callback; }
  dispatch(type) { this.events[type]({ target: this }); }
}
function boot(search = '') {
  const nodes = new Map(), translated = [], buttons = [];
  for (const match of html.matchAll(/<([a-z][a-z0-9-]*)\b([^>]*)>/gi)) {
    const node = new Node(match[1]), attrs = match[2];
    for (const a of attrs.matchAll(/([\w-]+)="([^"]*)"/g)) node.attrs[a[1]] = a[2];
    if (node.attrs.id) nodes.set(node.attrs.id, node);
    if (node.attrs['data-i18n']) { node.dataset.i18n = node.attrs['data-i18n']; translated.push(node); }
    if (node.attrs['data-language']) { node.dataset.language = node.attrs['data-language']; buttons.push(node); }
  }
  for (const [id, value] of Object.entries({ topic: 'all', schedule: 'weekdays', time: '08:00', timezone: 'Asia/Shanghai', 'output-language': 'zh-CN' })) nodes.get(id).value = value;
  const document = { documentElement: { lang: '' }, title: '', createElement: tag => new Node(tag), createTextNode: text => { const node = new Node('#text'); node.textContent = text; return node; }, getElementById: id => { assert(nodes.has(id), `missing id: ${id}`); return nodes.get(id); }, querySelectorAll: selector => selector === '[data-i18n]' ? translated : buttons };
  const context = vm.createContext({ window: { location: { search } }, document, URLSearchParams });
  vm.runInContext(fs.readFileSync(path.join(root, 'assets/fixtures.js'), 'utf8'), context);
  vm.runInContext(fs.readFileSync(path.join(root, 'assets/app.js'), 'utf8'), context);
  return { nodes, buttons, document };
}
const { nodes, buttons, document } = boot();
assert.equal(document.documentElement.lang, 'zh-CN');
assert.match(document.title, /^Smart Paper Tracker/);
assert.equal(nodes.get('paper-list').children.length, 2);
assert.equal(nodes.get('reference-list').children.length, 2);
assert.match(nodes.get('schedule-summary').textContent, /08:00/);
for (const [topic, count] of [['bvoc',1],['canopy',1],['all',2],['bvoc',1]]) {
  nodes.get('topic').value = topic; nodes.get('topic').dispatch('change');
  assert.equal(nodes.get('paper-list').children.length, count);
  assert.equal(nodes.get('reference-list').children.length, 2, 'global references must survive filtering');
}
buttons[1].dispatch('click');
assert.equal(document.documentElement.lang, 'en');
assert.match(document.title, /^Smart Paper Tracker/);
assert.equal(nodes.get('output-language').value, 'en');
assert.equal(nodes.get('paper-list').children.length, 1, 'filter must survive language switch');
assert.equal(nodes.get('paper-count').textContent, '1 synthetic paper');
assert.equal(nodes.get('email-preview-link').href, 'preview/demo.en.html');
assert.equal(nodes.get('ris-link').href, 'preview/demo.en.ris');
assert.equal(nodes.get('bib-link').href, 'preview/demo.en.bib');
assert.equal(buttons[1].attrs['aria-pressed'], 'true');
assert.match(nodes.get('paper-list').textContent, /Moderate drought/);
assert.match(nodes.get('paper-list').textContent, /SYNTHETIC SOURCE/);
for (const [id, value] of Object.entries({ schedule: 'weekly', time: '09:30', timezone: 'UTC' })) { nodes.get(id).value = value; nodes.get(id).dispatch('change'); }
assert.match(nodes.get('schedule-summary').textContent, /Every Monday · 09:30 · UTC \(not enabled\)/);
nodes.get('time').value = ''; nodes.get('time').dispatch('input');
assert.match(nodes.get('schedule-summary').textContent, /Choose a time/);
nodes.get('output-language').value = 'zh-CN'; nodes.get('output-language').dispatch('change');
assert.equal(document.documentElement.lang, 'zh-CN');
assert.equal(nodes.get('topic').value, 'bvoc');
assert.match(nodes.get('schedule-summary').textContent, /每周一/);
buttons[0].dispatch('click'); buttons[0].dispatch('click');
assert.equal(nodes.get('paper-list').children.length, 1, 'repeated clicks must not duplicate cards');
assert.equal(boot('?lang=en').document.documentElement.lang, 'en');
assert.equal(boot('?lang=invalid').document.documentElement.lang, 'zh-CN');
console.log('PASS: demo translations, evidence, global references, topic filters, language sync, downloads, local schedule preview, and repeated interactions. Browser layout is not covered.');
