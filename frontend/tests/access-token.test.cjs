const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const test = require('node:test');
const source = fs.readFileSync('frontend/static/app.js', 'utf8');
const definitions = source.slice(0, source.indexOf('// ---- Sidebar events ----'));
const KEY = 'weles.accessToken';

function setup({ stored, entered = 'new-token', responses = [200], storage } = {}) {
  const data = new Map(stored ? [[KEY, stored]] : []);
  const calls = [];
  let prompts = 0;
  const context = vm.createContext({
    Headers,
    sessionStorage: storage || {
      getItem: key => data.get(key) || null,
      setItem: (key, value) => data.set(key, value),
      removeItem: key => data.delete(key),
    },
    window: { prompt() { prompts++; assert.equal(data.has(KEY), false); return entered; } },
    fetch: async (path, options) => {
      calls.push({ path, token: options.headers.get('Authorization') });
      const status = responses.shift();
      return { status, headers: new Headers(status === 401 ? { 'X-Packing-Auth-Required': '1' } : {}) };
    },
  });
  vm.runInContext(definitions, context);
  return { context, data, calls, prompts: () => prompts };
}

test('restores a session token on load and uses it without prompting', async () => {
  const app = setup({ stored: 'saved-token' });
  await app.context.apiFetch('/orders/');
  assert.deepEqual(app.calls, [{ path: '/api/orders/', token: 'Bearer saved-token' }]);
  assert.equal(app.prompts(), 0);
});

test('token setter persists replacements and clear helper removes credentials', () => {
  const app = setup({ stored: 'old-token' });
  app.context.setAccessToken('setup-token');
  assert.equal(app.data.get(KEY), 'setup-token');
  app.context.clearAccessToken();
  assert.equal(app.data.has(KEY), false);
  assert.equal(vm.runInContext('accessToken', app.context), '');
});

test('401 discards stale stored token before prompting and retries with new token', async () => {
  const app = setup({ stored: 'stale-token', entered: '  replacement  ', responses: [401, 200] });
  await app.context.apiFetch('/orders/');
  assert.deepEqual(app.calls.map(call => call.token), ['Bearer stale-token', 'Bearer replacement']);
  assert.equal(app.prompts(), 1);
  assert.equal(app.data.get(KEY), 'replacement');
});

test('rejected retry clears both memory and session storage', async () => {
  const app = setup({ stored: 'stale-token', responses: [401, 401] });
  assert.equal((await app.context.apiFetch('/orders/')).status, 401);
  assert.equal(app.prompts(), 1);
  assert.equal(app.data.has(KEY), false);
  assert.equal(vm.runInContext('accessToken', app.context), '');
});

test('cancelled replacement prompt leaves stale credentials cleared', async () => {
  const app = setup({ stored: 'stale-token', entered: null, responses: [401] });
  await assert.rejects(app.context.apiFetch('/orders/'), /Token/);
  assert.equal(app.data.has(KEY), false);
  assert.equal(app.calls.length, 1);
});

test('concurrent unauthorized requests share one token prompt', async () => {
  const app = setup({ stored: 'stale-token', responses: [401, 401, 200, 200] });
  await Promise.all([app.context.apiFetch('/orders/'), app.context.apiFetch('/picking-lists')]);
  assert.equal(app.prompts(), 1);
  assert.deepEqual(app.calls.map(call => call.token), ['Bearer stale-token', 'Bearer stale-token', 'Bearer new-token', 'Bearer new-token']);
});

test('unavailable session storage does not prevent authentication or clearing', async () => {
  const blocked = () => { throw new Error('storage blocked'); };
  const app = setup({ storage: { getItem: blocked, setItem: blocked, removeItem: blocked }, responses: [401, 200] });
  await app.context.apiFetch('/orders/');
  assert.equal(vm.runInContext('accessToken', app.context), 'new-token');
  app.context.clearAccessToken();
  assert.equal(vm.runInContext('accessToken', app.context), '');
});

test('401 without operator-auth header clears token without prompting', async () => {
  const app = setup({ stored: 'saved-token' });
  app.context.fetch = async () => ({ status: 401, headers: new Headers() });
  assert.equal((await app.context.apiFetch('/orders/')).status, 401);
  assert.equal(app.data.has(KEY), false);
  assert.equal(app.prompts(), 0);
});

test('setup-issued token is persisted before continuing to the application', async () => {
  const app = setup();
  const nodes = new Map();
  app.context.document = { getElementById(id) {
    if (!nodes.has(id)) nodes.set(id, {
      value: 'setup input', textContent: '',
      classList: { add() {}, remove() {}, toggle() {} },
      setAttribute() {}, removeAttribute() {}, focus() {},
    });
    return nodes.get(id);
  } };
  vm.runInContext(source.slice(source.indexOf('function setupMessage('), source.indexOf("document.getElementById('setup-retry').addEventListener")), app.context);
  app.context.api = async path => path === '/setup/status'
    ? { configured: false, sandbox: true, redirect_uri: 'https://example.test/callback', setup_token: 'setup-key' }
    : { access_token: 'issued-token' };
  await app.context.boot();
  await nodes.get('setup-form').onsubmit({ preventDefault() {} });
  assert.equal(app.data.get(KEY), 'issued-token');
  assert.equal(vm.runInContext('accessToken', app.context), 'issued-token');
  assert.equal(nodes.get('setup-access-token').value, 'issued-token');
});
