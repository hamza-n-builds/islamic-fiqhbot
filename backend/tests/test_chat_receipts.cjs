// Actual frontend functions in a DOM fixture. This is not browser rendering QA.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');
const source = fs.readFileSync(path.resolve(__dirname, '../../frontend/script.js'), 'utf8');

function extract(name) {
  let start = source.indexOf(`    async function ${name}(`);
  if (start < 0) start = source.indexOf(`    function ${name}(`);
  assert.ok(start >= 0, `${name} exists`);
  const end = source.indexOf('\n    }\n', start);
  assert.ok(end > start, `${name} has a body`);
  return source.slice(start, end + 7);
}

test('askBackend forwards server proof alongside the exact previous answer', async () => {
  let body;
  const context = {
    BACKEND_URL: 'http://127.0.0.1:12345',
    fetch: async (url, options) => {
      assert.equal(url, 'http://127.0.0.1:12345/ask');
      body = JSON.parse(options.body);
      return { ok: true, json: async () => ({ ok: true, answer: 'fixture' }) };
    },
  };
  vm.createContext(context);
  vm.runInContext(extract('askBackend'), context);
  await context.askBackend('translate', 'Hanafi', 'Exact old answer', 'server-proof');
  assert.deepEqual(body, { question: 'translate', madhab: 'Hanafi', prev_answer: 'Exact old answer', prev_answer_receipt: 'server-proof' });
});

test('old saved history does not acquire a fabricated proof', async () => {
  let body;
  const context = {
    BACKEND_URL: '',
    fetch: async (_, options) => {
      body = JSON.parse(options.body);
      return { ok: true, json: async () => ({ ok: true }) };
    },
  };
  vm.createContext(context);
  vm.runInContext(extract('askBackend'), context);
  await context.askBackend('translate', 'General', 'Old unverified history');
  assert.equal(body.prev_answer_receipt, '');
});

test('rejected source validation does not display confidence or disagreement badges', () => {
  const context = {};
  vm.createContext(context);
  vm.runInContext(extract('buildMetaBadges'), context);
  assert.equal(context.buildMetaBadges({ mode: 'low_confidence', consensus: null, confidence_percent: null }), '');
});

test('sendMessage reads the last bot proof and saves the newly issued one', async () => {
  let args;
  let saves = 0;
  const chat = { id: 'fixture-chat', title: 'Fixture', madhab: 'General', messages: [
    { sender: 'bot', text: 'Exact old answer', meta: { answer_receipt: 'old-proof' } },
  ] };
  const context = {
    chats: [chat], currentChatId: chat.id,
    pendingChats: new Set(), sendBtn: {}, chatIntro: {},
    userInput: { value: 'translate' },
    chatContainer: { insertBefore() {}, scrollTop: 0, scrollHeight: 100 },
    stopSpeech() {}, appendMessageUI() {},
    saveChats() { saves++; }, requestAnimationFrame(callback) { callback(); },
    document: { createElement() { return { classList: { add() {} }, remove() {} }; } },
    askBackend: async (...received) => {
      args = received;
      return { ok: true, mode: 'fiqh_comparison', response_schema: 'school_comparison_v1', answer_sections: [],
        answer: 'Translated fixture', answer_receipt: 'new-proof',
        citation_validation: { status: 'passed', scope: 'provided_reference_membership' },
        scholarly_review: { status: 'not_completed', scope: 'answer_and_ruling_support' },
        sources: { fiqh: [], quran: [], hadith: [] } };
    },
    console,
  };
  vm.createContext(context);
  vm.runInContext(extract('resizeComposer'), context);
  vm.runInContext(extract('sendMessage'), context);
  await context.sendMessage();
  assert.deepEqual(args, ['translate', 'General', 'Exact old answer', 'old-proof']);
  assert.equal(chat.messages.at(-1).meta.answer_receipt, 'new-proof');
  assert.equal(chat.messages.at(-1).text, 'Translated fixture');
  assert.equal(chat.messages.at(-1).meta.citation_validation.scope, 'provided_reference_membership');
  assert.equal(chat.messages.at(-1).meta.scholarly_review.status, 'not_completed');
  assert.equal(chat.messages.at(-1).meta.response_schema, 'school_comparison_v1');
  assert.equal(context.pendingChats.size, 0);
  assert.ok(saves >= 2);
});

function comparisonContext() {
  const context = {};
  vm.createContext(context);
  for (const name of ['escapeHtml', 'isUrduText', 'sourceEntries', 'formatAnswerInline', 'formatAnswerContent', 'buildSchoolSections']) vm.runInContext(extract(name), context);
  return context;
}

test('comparison displays all three full answers as compact rows without answer dropdowns', () => {
  const sections = ['hanafi', 'shafi', 'maliki'].map(school => ({ school, status: 'available', answer: 'Fixture answer' }));
  const html = comparisonContext().buildSchoolSections(sections);
  assert.equal((html.match(/class="school-answer"/g) || []).length, 3);
  assert.doesNotMatch(html, /<details|<summary|hidden/);
  assert.equal((html.match(/Fixture answer/g) || []).length, 3);
  assert.match(html, /Hanafi/);
  assert.match(html, /Shafi‘i/);
  assert.match(html, /Maliki/);
  assert.doesNotMatch(html, /Sources|References matched|Answer<\/span>/);
});

test('unavailable or withheld schools keep their own message without a sources panel', () => {
  const sections = [
    { school: 'hanafi', status: 'unavailable', answer: 'Missing material' },
    { school: 'shafi', status: 'available', answer: 'Fixture answer' },
    { school: 'maliki', status: 'withheld', answer: 'Answer withheld' },
  ];
  const html = comparisonContext().buildSchoolSections(sections);
  assert.match(html, /Not available/);
  assert.match(html, /Withheld/);
  assert.match(html, /Missing material/);
  assert.match(html, /Answer withheld/);
  assert.doesNotMatch(html, /<details|<summary|data-school-sources/);
});

test('provider text is escaped and malformed stored school metadata is not rendered as a comparison', () => {
  const sections = ['hanafi', 'shafi', 'maliki'].map(school => ({ school, status: 'available', answer: '<script>alert(1)</script>' }));
  const context = comparisonContext();
  const html = context.buildSchoolSections(sections);
  assert.doesNotMatch(html, /<script>/);
  assert.match(html, /&lt;script&gt;/);
  assert.equal(context.buildSchoolSections(sections.slice(0, 2)), '');
  assert.equal(context.buildSchoolSections([sections[2], sections[1], sections[0]]), '');
});

test('requests from an old selected-school chat still ask for all schools', async () => {
  let args;
  const chat = { id: 'old', title: 'Old chat', madhab: 'Hanafi', messages: [] };
  const context = {
    chats: [chat], currentChatId: 'old', pendingChats: new Set(), sendBtn: {}, chatIntro: {},
    userInput: { value: 'Fixture question' }, chatContainer: { insertBefore() {} },
    stopSpeech() {}, appendMessageUI() {}, saveChats() {}, requestAnimationFrame(f) { f(); },
    document: { createElement() { return { classList: { add() {} }, remove() {} }; } },
    askBackend: async (...received) => { args = received; return { ok: true, answer: 'Fixture' }; }, console,
  };
  vm.createContext(context);
  vm.runInContext(extract('resizeComposer'), context);
  vm.runInContext(extract('sendMessage'), context);
  await context.sendMessage();
  assert.equal(args[1], 'General');
});

test('in-flight replies stay in the original chat and duplicate sends are blocked', async () => {
  let finish;
  let requests = 0;
  const displayed = [];
  const chat = { id: 'original', title: 'Fixture chat', messages: [] };
  const other = { id: 'other', title: 'Other', messages: [] };
  const context = {
    chats: [chat, other], currentChatId: 'original', pendingChats: new Set(), sendBtn: {}, chatIntro: {},
    userInput: { value: 'Fixture question' }, chatContainer: { insertBefore() {} },
    stopSpeech() {}, appendMessageUI(...args) { displayed.push(args); }, saveChats() {}, requestAnimationFrame(f) { f(); },
    document: { createElement() { return { classList: { add() {} }, remove() {} }; } },
    askBackend: () => { requests++; return new Promise(resolve => { finish = resolve; }); }, console,
  };
  vm.createContext(context);
  vm.runInContext(extract('resizeComposer'), context);
  vm.runInContext(extract('sendMessage'), context);
  const pending = context.sendMessage();
  context.userInput.value = 'Duplicate question';
  await context.sendMessage();
  assert.equal(requests, 1);
  context.currentChatId = 'other';
  finish({ ok: true, answer: 'Original answer' });
  await pending;
  assert.equal(chat.messages.at(-1).text, 'Original answer');
  assert.equal(other.messages.length, 0);
  assert.equal(displayed.filter(args => args[0] === 'bot').length, 0);
  assert.equal(context.pendingChats.size, 0);
});

test('actual message renderer mounts a single response card with school-scoped reference groups', () => {
  function element() {
    return {
      children: [], selectors: {}, innerHTML: '',
      classList: { values: new Set(), add(...names) { names.forEach(name => this.values.add(name)); } },
      appendChild(child) { this.children.push(child); }, addEventListener() {}, setAttribute() {},
      querySelector(selector) {
        if (selector.startsWith('[data-school-sources=') || selector === '.speak-btn' || selector === '.copy-btn') {
          return this.selectors[selector] ||= element();
        }
        return null;
      },
    };
  }
  const mounted = [];
  const container = { insertBefore(child) { mounted.push(child); }, scrollHeight: 100 };
  const context = { document: { createElement: element }, chatContainer: container,
    chatIntro: { parentNode: container }, requestAnimationFrame(f) { f(); } };
  vm.createContext(context);
  for (const name of ['escapeHtml', 'isUrduText', 'sourceEntries', 'formatAnswerInline', 'formatAnswerContent', 'buildSchoolSections', 'buildSchoolSources', 'bindResponseSources', 'responseActionContent', 'buildMetaBadges', 'buildSourcesAccordion', 'appendMessageUI']) {
    vm.runInContext(extract(name), context);
  }
  const sections = ['hanafi', 'shafi', 'maliki'].map(school => ({ school, status: 'available', answer: school + ' fixture',
    sources: { fiqh: [{ topic_name: school + ' topic' }], quran: [], hadith: [] } }));
  context.appendMessageUI('bot', 'FLAT COPY-ONLY RESPONSE', false,
    { mode: 'fiqh_comparison', response_schema: 'school_comparison_v1', answer_sections: sections });
  assert.equal(mounted.length, 1);
  assert.ok(mounted[0].classList.values.has('comparison-message'));
  const content = mounted[0].children[0];
  assert.doesNotMatch(content.innerHTML, /FLAT COPY-ONLY RESPONSE/);
  assert.match(content.innerHTML, /response-header/);
  assert.match(content.innerHTML, /Fiqhbot/);
  assert.equal((content.innerHTML.match(/class="response-source-dialog"/g) || []).length, 1);
  assert.match(content.innerHTML, /data-open-sources aria-haspopup="dialog"/);
  assert.match(content.innerHTML, /<span>Listen<\/span>/);
  assert.match(content.innerHTML, /<span>Copy<\/span>/);
  assert.doesNotMatch(content.innerHTML, /class="school-sources"|sample confidence|92%/);
  for (const section of sections) {
    const holder = content.selectors[`[data-school-sources="${section.school}"]`];
    assert.equal(holder.children.length, 1);
    assert.match(holder.children[0].children[0].innerHTML, new RegExp(section.school + ' topic'));
  }
});

test('reference groups omit unavailable and withheld school sources even if stale metadata includes them', () => {
  const context = comparisonContext();
  vm.runInContext(extract('buildSchoolSources'), context);
  const sections = ['hanafi', 'shafi', 'maliki'].map((school, i) => ({ school,
    status: ['unavailable', 'available', 'withheld'][i], answer: 'Fixture',
    sources: { fiqh: [{ topic_name: 'Synthetic topic' }], quran: [], hadith: [] } }));
  const html = context.buildSchoolSources(sections);
  assert.match(html, /data-school-sources="shafi"/);
  assert.doesNotMatch(html, /data-school-sources="hanafi"|data-school-sources="maliki"/);
  assert.equal(context.buildSchoolSources(sections.map(s => ({ ...s, sources: {} }))), '');
});

test('comparison keeps multilingual answer direction and paragraph breaks local to each school', () => {
  const sections = ['hanafi', 'shafi', 'maliki'].map(school => ({ school, status: 'available',
    answer: school === 'shafi' ? '\u0627\u062c\u0627\u0628\u06c1 [fiqh:fixture]' : '**First paragraph.**\n\nSecond paragraph. [fiqh:fixture]' }));
  const html = comparisonContext().buildSchoolSections(sections);
  assert.equal((html.match(/font-urdu/g) || []).length, 1);
  assert.equal((html.match(/dir="auto"/g) || []).length, 5);
  assert.match(html, /<strong>First paragraph\.<\/strong><\/p><p/);
  assert.match(html, /Second paragraph\. \[fiqh:fixture\]/);
  assert.doesNotMatch(html, /School comparison.*font-urdu/);
});

test('individual source records use native keyboard-operable disclosures and build text only once', () => {
  function element(tag) {
    return { tag, children: [], handlers: {}, classList: { add() {} },
      appendChild(child) { this.children.push(child); }, addEventListener(type, fn) { this.handlers[type] = fn; },
      hasChildNodes() { return this.children.length > 0; } };
  }
  let builds = 0;
  const context = { document: { createElement: element },
    buildTrilingualContent() { builds++; return element('div'); }, responseActionContent() { return '<svg></svg>'; } };
  vm.createContext(context);
  vm.runInContext(extract('buildClickableLine'), context);
  const row = context.buildClickableLine('Synthetic reference', 'quran', {});
  assert.equal(row.tag, 'details');
  assert.equal(row.children[0].tag, 'summary');
  row.open = true;
  row.handlers.toggle();
  row.open = false;
  row.handlers.toggle();
  row.open = true;
  row.handlers.toggle();
  assert.equal(builds, 1);
  assert.equal(row.children[1].children.length, 1);
});

test('response actions preserve exact text and reply scrolling respects the viewers reading position', async () => {
  function element() {
    return { children: [], selectors: {}, attrs: {}, handlers: {}, innerHTML: '',
      classList: { add() {}, remove() {} },
      setAttribute(key, value) { this.attrs[key] = value; },
      appendChild(child) { this.children.push(child); },
      scrollIntoView() { this.scrolledToStart = true; },
      addEventListener(type, callback) { this.handlers[type] = callback; },
      querySelector(selector) {
        if (selector.startsWith('[data-school-sources=') || selector === '.response-source-dialog') return null;
        return this.selectors[selector] ||= element();
      } };
  }
  const mounted = [];
  const copied = [];
  const spoken = [];
  const timers = [];
  let readEnd;
  const container = { insertBefore(child) { mounted.push(child); }, scrollHeight: 2000, scrollTop: 0, clientHeight: 500 };
  const context = { document: { createElement: element }, chatContainer: container,
    chatIntro: { parentNode: container }, requestAnimationFrame(f) { f(); },
    navigator: { clipboard: { async writeText(text) { copied.push(text); } } },
    setTimeout(f) { timers.push(f); }, stopSpeech() {},
    async speakText(text, callback) { spoken.push(text); readEnd = callback; } };
  vm.createContext(context);
  for (const name of ['escapeHtml', 'isUrduText', 'sourceEntries', 'formatAnswerInline', 'formatAnswerContent', 'buildSchoolSections', 'buildSchoolSources', 'bindResponseSources', 'responseActionContent', 'buildMetaBadges', 'appendMessageUI']) {
    vm.runInContext(extract(name), context);
  }
  const sections = ['hanafi', 'shafi', 'maliki'].map(school => ({ school, status: 'available', answer: 'Fixture' }));
  const exactAnswer = '## Hanafi\nFixture [fiqh:test]\n\n## Shafi\'i\nFixture [fiqh:test]\n\n## Maliki\nFixture [fiqh:test]';
  context.appendMessageUI('bot', exactAnswer, true,
    { mode: 'fiqh_comparison', response_schema: 'school_comparison_v1', answer_sections: sections });
  const controls = mounted[0].children[0].selectors;
  assert.equal(container.scrollTop, 0);
  assert.equal(mounted[0].scrolledToStart, undefined);
  await controls['.copy-btn'].handlers.click();
  assert.deepEqual(copied, [exactAnswer]);
  assert.match(controls['.copy-btn'].innerHTML, /Copied/);
  timers[0]();
  assert.match(controls['.copy-btn'].innerHTML, /<span>Copy<\/span>/);
  controls['.speak-btn'].handlers.click();
  await Promise.resolve();
  assert.deepEqual(spoken, [exactAnswer]);
  assert.equal(controls['.speak-btn'].attrs['aria-pressed'], 'true');
  assert.match(controls['.speak-btn'].innerHTML, /<span>Stop<\/span>/);
  readEnd();
  assert.equal(controls['.speak-btn'].attrs['aria-pressed'], 'false');
  assert.match(controls['.speak-btn'].innerHTML, /<span>Listen<\/span>/);
  container.scrollTop = 1500;
  context.appendMessageUI('bot', exactAnswer, true,
    { mode: 'fiqh_comparison', response_schema: 'school_comparison_v1', answer_sections: sections });
  assert.equal(mounted[1].scrolledToStart, true);
});

test('legacy saved confidence and consensus never reappear as badges', () => {
  const context = { escapeHtml: text => text };
  vm.createContext(context);
  vm.runInContext(extract('buildMetaBadges'), context);
  for (const consensus of [true, false]) {
    assert.equal(context.buildMetaBadges({ mode: 'fiqh', confidence_percent: 99,
      confidence_label: 'Very High', consensus }), '');
  }
});

test('new status clearly limits source checks and displays incomplete review', () => {
  const context = { escapeHtml: text => text };
  vm.createContext(context);
  vm.runInContext(extract('buildMetaBadges'), context);
  const meta = { mode: 'fiqh', confidence_percent: 99, consensus: true,
    citation_validation: { status: 'passed', scope: 'provided_reference_membership' },
    scholarly_review: { status: 'not_completed', scope: 'answer_and_ruling_support' } };
  const html = context.buildMetaBadges(meta);
  assert.match(html, /References matched/);
  assert.match(html, /Scholarly review not completed/);
  assert.match(html, /does not verify the answer's accuracy/);
  assert.doesNotMatch(html, /99|Confidence:|agree|Scholars differ/);
  for (const mode of ['greeting', 'capability', 'low_confidence']) {
    assert.equal(context.buildMetaBadges({ ...meta, mode }), '');
  }
});

test('unknown or rejected status does not acquire a passed badge', () => {
  const context = {};
  vm.createContext(context);
  vm.runInContext(extract('buildMetaBadges'), context);
  for (const citation_validation of [undefined, { status: 'rejected' }, { status: 'passed', scope: 'accuracy' }]) {
    assert.equal(context.buildMetaBadges({ mode: 'fiqh', citation_validation }), '');
  }
});

test('sources in old saved chats do not turn false consensus into disagreement', () => {
  function element() {
    return { innerHTML: '', children: [], classList: { add() {} }, setAttribute() {},
      appendChild(child) { this.children.push(child); } };
  }
  const context = { document: { createElement: element }, escapeHtml: text => text };
  vm.createContext(context);
  vm.runInContext(extract('sourceEntries'), context);
  vm.runInContext(extract('buildSourcesAccordion'), context);
  const result = context.buildSourcesAccordion({ fiqh: [{ topic_name: 'Fixture', consensus: false }] });
  assert.equal(result.children.length, 1);
  assert.doesNotMatch(result.children[0].innerHTML, /Scholars differ/);
});
