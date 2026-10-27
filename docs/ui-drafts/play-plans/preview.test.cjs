const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const http = require('node:http');
const {once} = require('node:events');
const {createServer} = require('./serve.cjs');
const Yearly = require('./yearly/model.js');

test('synthetic yearly fixture supports 40 candidates and keeps learning read-only', () => {
  const context = {}; context.window = context;
  for (const name of ['data.js', 'yearly/demo-candidates.js', 'curriculum.js']) {
    vm.runInNewContext(fs.readFileSync(path.join(__dirname, name), 'utf8'), context);
  }
  const data = context.PLAY_PROJECT_DEMO;
  assert.equal(data.periods.length, 4);
  assert.ok(data.periods.every(p => p.rows.length === 10));
  const model = new Yearly(data, context.PLAY_CURRICULUM);
  model.toggle('m03_m05', 'cand1');
  model.edit('m03_m05', 'cand1', 'materials', '교사가 준비할 재료');
  assert.throws(() => model.edit('m03_m05', 'cand1', 'learning_content_ids', ['nuri2019.5.1.1', 'nuri2019.5.1.2']));
  assert.throws(() => model.edit('m03_m05', 'cand2', 'play_name', '선택하지 않은 후보'));
});

test('shared UI contains no LLM connection or live-result import', () => {
  for (const name of ['app.js', 'yearly/app.js']) {
    const text = fs.readFileSync(path.join(__dirname, name), 'utf8');
    assert.doesNotMatch(text, /\bfetch\s*\(|XMLHttpRequest|WebSocket|api\/drills|monthly-.*-live\.json/);
  }
  for (const name of ['index.html', 'yearly/index.html']) {
    const html = fs.readFileSync(path.join(__dirname, name), 'utf8');
    assert.match(html, /connect-src 'none'/);
    for (const [, src] of html.matchAll(/(?:src|href)="([^"#]+)"/g)) {
      if (src.startsWith('data:') || src.endsWith('/') || src.includes('?')) continue;
      const file = src.startsWith('/') ? src.slice(1) : path.join(path.dirname(name), src);
      assert.ok(fs.existsSync(path.join(__dirname, file)), file);
    }
  }
});

test('preview serves both views and blocks source files, unknown paths, and POST', async () => {
  const server = createServer();
  server.listen(0, '127.0.0.1');
  await once(server, 'listening');
  const port = server.address().port;
  function request(url, method = 'GET') {
    return new Promise((resolve, reject) => {
      const req = http.request({host: '127.0.0.1', port, path: url, method}, response => {
        response.resume(); response.on('end', () => resolve(response.statusCode));
      });
      req.on('error', reject); req.end();
    });
  }
  try {
    for (const url of ['/yearly/', '/monthly/?month=10', '/monthly/app.js', '/yearly/demo-candidates.js', '/assets/FONT-LICENSE.txt']) assert.equal(await request(url), 200, url);
    for (const url of ['/serve.cjs', '/.env', '/.git/config', '/../README.md', '/api/drills/status']) assert.equal(await request(url), 404, url);
    assert.equal(await request('/api/drills/generate', 'POST'), 405);
  } finally {
    await new Promise(resolve => server.close(resolve));
  }
});
