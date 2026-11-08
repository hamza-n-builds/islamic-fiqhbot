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
    userInput: { value: 'translate' },
    chatContainer: { insertBefore() {}, scrollTop: 0, scrollHeight: 100 },
    madhabSelection: {}, stopSpeech() {}, appendMessageUI() {},
    saveChats() { saves++; }, requestAnimationFrame(callback) { callback(); },
    document: { createElement() { return { classList: { add() {} }, remove() {} }; } },
    askBackend: async (...received) => {
      args = received;
      return { ok: true, mode: 'reexpress', answer: 'Translated fixture', answer_receipt: 'new-proof',
        citation_validation: { status: 'passed', scope: 'provided_reference_membership' },
        scholarly_review: { status: 'not_completed', scope: 'answer_and_ruling_support' },
        sources: { fiqh: [], quran: [], hadith: [] } };
    },
    console,
  };
  vm.createContext(context);
  vm.runInContext(extract('sendMessage'), context);
  await context.sendMessage();
  assert.deepEqual(args, ['translate', 'General', 'Exact old answer', 'old-proof']);
  assert.equal(chat.messages.at(-1).meta.answer_receipt, 'new-proof');
  assert.equal(chat.messages.at(-1).text, 'Translated fixture');
  assert.equal(chat.messages.at(-1).meta.citation_validation.scope, 'provided_reference_membership');
  assert.equal(chat.messages.at(-1).meta.scholarly_review.status, 'not_completed');
  assert.ok(saves >= 2);
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
    return { innerHTML: '', children: [], classList: { add() {} },
      appendChild(child) { this.children.push(child); } };
  }
  const context = { document: { createElement: element }, escapeHtml: text => text };
  vm.createContext(context);
  vm.runInContext(extract('buildSourcesAccordion'), context);
  const result = context.buildSourcesAccordion({ fiqh: [{ topic_name: 'Fixture', consensus: false }] });
  assert.equal(result.children.length, 1);
  assert.doesNotMatch(result.children[0].innerHTML, /Scholars differ/);
});
