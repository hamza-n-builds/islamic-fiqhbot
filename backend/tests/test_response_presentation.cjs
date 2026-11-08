// Actual UI functions, synthetic records. Does not assert browser rendering.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const test = require('node:test');
const source = fs.readFileSync(path.resolve(__dirname, '../../frontend/script.js'), 'utf8');
function extract(name) {
  let start = source.indexOf(`    function ${name}(`);
  if (start < 0) start = source.indexOf(`    async function ${name}(`);
  assert.ok(start >= 0, name + ' exists');
  const end = source.indexOf('\n    }\n', start);
  return source.slice(start, end + 7);
}
function context(extra = {}, names = []) {
  const ctx = { ...extra };
  vm.createContext(ctx);
  for (const name of ['escapeHtml', 'isUrduText', 'sourceEntries', 'formatAnswerInline', 'formatAnswerContent', ...names]) {
    vm.runInContext(extract(name), ctx);
  }
  return ctx;
}
const sources = {
  fiqh: [{ topic_id: 'fixture', topic_name: 'Fixture topic' }],
  quran: [{ ref: '1:1', surah: 'Synthetic fixture', english: 'Layout fixture only.' }],
  hadith: [{ ref: 'Sahih Muslim #11a', text_en: 'Synthetic fixture only.' }],
};

test('canonical source labels bind to the actual scoped records and ignore malformed metadata', () => {
  const ctx = context();
  const records = ctx.sourceEntries(sources);
  assert.equal(records.length, 3);
  assert.equal(records[0].tag, '[Fixture topic]');
  assert.equal(records[1].tag, '[Quran 1:1]');
  assert.equal(records[2].tag, '[Sahih Muslim #11a]');
  assert.equal(ctx.sourceEntries({ fiqh: null, quran: {}, hadith: [null, 'bad', {}] }).length, 0);
  assert.equal(ctx.sourceEntries({ hadith: [{ ref: 'Textless narration' }] }).length, 0);
});

test('inline references become accessible source controls only when present in that schools sources', () => {
  const html = context().formatAnswerInline('Note [Fixture topic] [Quran 1:1] [Quran 9:9]', sources, 'hanafi');
  assert.equal((html.match(/class="inline-citation"/g) || []).length, 2);
  assert.match(html, /data-citation-school="hanafi"/);
  assert.match(html, /data-citation-key="quran-0"/);
  assert.match(html, /aria-haspopup="dialog"/);
  assert.match(html, /\[Quran 9:9\]/);
  assert.doesNotMatch(html, /data-citation-key="quran-1"/);
});

test('school rendering cannot borrow another schools references and never changes stored answer text', () => {
  const ctx = context({}, ['buildSchoolSections']);
  const sections = ['hanafi', 'shafi', 'maliki'].map((school, i) => ({ school, status: 'available',
    answer: 'Original [Quran 1:1]', sources: i === 0 ? sources : {} }));
  const snapshot = JSON.stringify(sections);
  const html = ctx.buildSchoolSections(sections);
  assert.equal((html.match(/class="inline-citation"/g) || []).length, 1);
  assert.equal((html.match(/\[Quran 1:1\]/g) || []).length, 2);
  assert.equal(JSON.stringify(sections), snapshot);
});

test('safe response formatting supports paragraphs, headings and lists without rendering provider HTML', () => {
  const ctx = context();
  const html = ctx.formatAnswerContent('**Short answer.**\n\n### Conditions\n- First [Quran 1:1]\n- <img src=x onerror=alert(1)>\n\n1. Step one\n2. Step two\n\n`<script>` and [unprovided]', sources, 'shafi');
  assert.match(html, /<strong>Short answer\.<\/strong>/);
  assert.match(html, /<h4/);
  assert.match(html, /<ul>/);
  assert.match(html, /<ol start="1">/);
  assert.doesNotMatch(html, /<img|<script>/);
  assert.match(html, /&lt;img/);
  assert.match(html, /<code>&lt;script&gt;<\/code>/);
  assert.match(html, /\[unprovided\]/);
});

test('malicious reference names stay text and cannot inject attributes into source chips', () => {
  const evil = { fiqh: [{ topic_name: '\"><img src=x onerror=alert(1)>' }] };
  const html = context().formatAnswerInline('[\"><img src=x onerror=alert(1)>]', evil, 'maliki');
  assert.doesNotMatch(html, /<img| onerror="/);
  assert.match(html, /&lt;img/);
});

function inspectorFixture(native = true) {
  const viewport = { scrollTop: 1200 };
  const record = { tagName: 'DETAILS', open: false, focused: false,
    querySelector() { return { focus() { record.focused = true; } }; }, scrollIntoView() {} };
  const dialog = { open: false, handlers: {}, attrs: {}, classList: { add() {}, remove() {} },
    addEventListener(type, fn) { this.handlers[type] = fn; },
    setAttribute(k, v) { this.attrs[k] = v; if (k === 'open') this.open = true; },
    removeAttribute(k) { delete this.attrs[k]; if (k === 'open') this.open = false; },
    querySelector(selector) {
      if (selector === '[data-source-group="hanafi"]') return { querySelector(selector) { return selector === '[data-source-key="quran-0"]' ? record : null; } };
      return null;
    },
  };
  if (native) {
    dialog.showModal = () => { dialog.open = true; };
    dialog.close = () => { dialog.open = false; dialog.handlers.close(); };
  }
  const trigger = { dataset: { citationSchool: 'hanafi', citationKey: 'quran-0' }, handlers: {}, isConnected: true,
    addEventListener(type, fn) { this.handlers[type] = fn; }, focus() { this.focused = true; } };
  const close = { handlers: {}, addEventListener(type, fn) { this.handlers[type] = fn; } };
  const root = { closest() { return viewport; }, querySelector(selector) { return selector === '.response-source-dialog' ? dialog : selector === '.source-close-btn' ? close : null; },
    querySelectorAll() { return [trigger]; } };
  return { root, dialog, trigger, close, record, viewport };
}

test('a source chip opens its answer inspector, expands the exact record, and returns focus on close', () => {
  const ui = inspectorFixture();
  const ctx = context({ requestAnimationFrame(fn) { fn(); } }, ['bindResponseSources']);
  ctx.bindResponseSources(ui.root);
  ui.trigger.handlers.click({ currentTarget: ui.trigger });
  assert.equal(ui.dialog.open, true);
  assert.equal(ui.record.open, true);
  assert.equal(ui.record.focused, true);
  ui.viewport.scrollTop = 1700; // A browser ancestor scroll must not move the saved reading position.
  ui.close.handlers.click();
  assert.equal(ui.dialog.open, false);
  assert.equal(ui.trigger.focused, true);
  assert.equal(ui.viewport.scrollTop, 1200);
});

test('source inspector has a nonmodal inline fallback when dialog.showModal is unavailable', () => {
  const ui = inspectorFixture(false);
  const ctx = context({ requestAnimationFrame(fn) { fn(); } }, ['bindResponseSources']);
  ctx.bindResponseSources(ui.root);
  ui.trigger.handlers.click({ currentTarget: ui.trigger });
  assert.equal(ui.dialog.open, true);
  assert.equal(ui.dialog.attrs['aria-modal'], undefined);
  ui.close.handlers.click();
  assert.equal(ui.dialog.open, false);
  assert.equal(ui.trigger.focused, true);
});

test('composer Enter submits on desktop; Shift+Enter, IME and touch Enter retain editing', () => {
  let sends = 0;
  let prevents = 0;
  let touch = false;
  const ctx = context({ window: { matchMedia() { return { matches: touch }; } }, sendMessage() { sends++; } }, ['handleComposerKeydown']);
  const event = extra => ({ key: 'Enter', preventDefault() { prevents++; }, ...extra });
  ctx.handleComposerKeydown(event({ shiftKey: true }));
  ctx.handleComposerKeydown(event({ isComposing: true }));
  touch = true;
  ctx.handleComposerKeydown(event({}));
  touch = false;
  ctx.handleComposerKeydown(event({}));
  assert.equal(sends, 1);
  assert.equal(prevents, 1);
});
