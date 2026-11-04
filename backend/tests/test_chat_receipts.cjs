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
      return { ok: true, mode: 'reexpress', answer: 'Translated fixture', answer_receipt: 'new-proof', sources: { fiqh: [], quran: [], hadith: [] } };
    },
    console,
  };
  vm.createContext(context);
  vm.runInContext(extract('sendMessage'), context);
  await context.sendMessage();
  assert.deepEqual(args, ['translate', 'General', 'Exact old answer', 'old-proof']);
  assert.equal(chat.messages.at(-1).meta.answer_receipt, 'new-proof');
  assert.equal(chat.messages.at(-1).text, 'Translated fixture');
  assert.ok(saves >= 2);
});
