const express = require(process.argv[2] + '/node_modules/express');
const http = require('http');
const app = express();
const p = '/api/v3/entries';
app.get(p + '/history', (q, r) => r.json({ route: 'history' }));
app.get(p + '/history/:lastModified', (q, r) => r.json({ route: 'history/:lm' }));
for (const m of ['get', 'put', 'patch', 'delete'])
  app[m](p + '/:identifier', (q, r) => r.json({ route: m + ' :identifier', id: q.params.identifier }));
app.use((err, q, r, n) => r.status(err.status || 500).json({ error: err.message }));
const raw = [
  ['uuid', '0b7e2ef2-7a4b-4c9d-8e2f-1a2b3c4d5e6f'],
  ['colon', 'g7:SERIAL:12345'],
  ['space %20', 'a%20b%20c'],
  ['plus', 'a+b'],
  ['slash %2F', 'a%2Fb'],
  ['slash raw', 'a/b'],
  ['percent malformed', 'a%zzb'],
  ['percent %25', 'a%25b'],
  ['hash %23', 'a%23b'],
  ['question %3F', 'a%3Fb'],
  ['dot', '.'],
  ['dotdot', '..'],
  ['history', 'history'],
  ['long 8000', 'x'.repeat(8000)],
  ['long 20000', 'x'.repeat(20000)],
];
const server = app.listen(0, async () => {
  const port = server.address().port;
  for (const method of ['GET', 'PUT', 'DELETE']) for (const [label, id] of raw) {
    await new Promise(res => {
      const req = http.request({ port, method, path: p + '/' + id, headers: { 'content-type': 'application/json' } }, r => {
        let b = ''; r.on('data', d => b += d); r.on('end', () => {
          let j; try { j = JSON.parse(b); } catch (e) { j = { body: b.slice(0, 40) }; }
          const idOut = j.id === undefined ? '-' : (j.id.length > 30 ? 'len=' + j.id.length : JSON.stringify(j.id));
          console.log([method, label, r.statusCode, j.route || j.error || j.body, idOut].join(' | ')); res();
        });
      });
      req.on('error', e => { console.log([method, label, 'ERR', e.code].join(' | ')); res(); });
      req.end(method === 'GET' || method === 'DELETE' ? undefined : '{}');
    });
  }
  server.close();
});
