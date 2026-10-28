const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const http = require('node:http');
const {once} = require('node:events');
const {createServer} = require('./serve.cjs');
test('24 original frontend files match source hashes', () => {
  const manifest = require('./frontend-source-manifest.json');
  assert.equal(manifest.length, 24);
  for (const entry of manifest) {
    const bytes = fs.readFileSync(path.join(__dirname, entry.file));
    assert.equal(crypto.createHash('sha256').update(bytes).digest('hex'), entry.sha256, entry.file);
  }
});
test('original screens and live fixtures work without a paid backend', async () => {
  const server = createServer();
  server.listen(0, '127.0.0.1'); await once(server, 'listening');
  function request(url, method = 'GET') {
    return new Promise((resolve, reject) => {
      const req = http.request({host:'127.0.0.1',port:server.address().port,path:url,method}, response => {
        response.resume(); response.on('end', () => resolve(response.statusCode));
      }); req.on('error', reject); req.end();
    });
  }
  try {
    for (const url of ['/yearly/', '/monthly/?month=10', '/yearly/live-candidates.js', '/yearly/sol-candidates.js', '/monthly-july-live.json', '/monthly-october-core-live.json']) assert.equal(await request(url), 200, url);
    for (const url of ['/server.py', '/.env', '/.env.sol', '/.git/config']) assert.equal(await request(url), 404);
    assert.equal(await request('/api/drills/generate', 'POST'), 405);
  } finally { await new Promise(resolve => server.close(resolve)); }
});