// Local design preview only. No API, credentials, model calls, or directory listing.
const http = require('node:http');
const fs = require('node:fs/promises');
const path = require('node:path');

const files = new Set(require('./frontend-source-manifest.json').map(entry => entry.file)
  .filter(name => !name.endsWith('.test.cjs')));
const types = {'.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8', '.ttf': 'font/ttf', '.txt': 'text/plain; charset=utf-8',
  '.json': 'application/json; charset=utf-8'};

function createServer() {
  return http.createServer(async (request, response) => {
    response.setHeader('X-Content-Type-Options', 'nosniff');
    response.setHeader('Cache-Control', 'no-store');
    if (!['GET', 'HEAD'].includes(request.method)) {
      response.writeHead(405, {'Allow': 'GET, HEAD'}).end();
      return;
    }
    let name;
    try { name = decodeURIComponent(new URL(request.url, 'http://127.0.0.1').pathname); }
    catch { response.writeHead(400).end(); return; }
    if (name === '/yearly' || name === '/monthly') {
      response.writeHead(302, {'Location': name + '/'}).end(); return;
    }
    if (name.startsWith('/monthly/')) name = name.slice('/monthly'.length);
    name = name === '/' ? 'index.html' : name.slice(1);
    if (name === 'yearly/') name = 'yearly/index.html';
    if (!files.has(name)) { response.writeHead(404).end(); return; }
    try {
      const body = await fs.readFile(path.join(__dirname, name));
      response.writeHead(200, {'Content-Type': types[path.extname(name)], 'Content-Length': body.length});
      response.end(request.method === 'HEAD' ? undefined : body);
    } catch { response.writeHead(404).end(); }
  });
}

if (require.main === module) {
  const port = Number(process.argv[2] ?? 8886);
  if (!Number.isInteger(port) || port < 1 || port > 65535) throw Error('INVALID_PORT');
  createServer().listen(port, '127.0.0.1', () => {
    console.log(`Yearly: http://127.0.0.1:${port}/yearly/`);
    console.log(`Monthly: http://127.0.0.1:${port}/monthly/?month=10`);
  });
}
module.exports = {createServer};
