const http = require('http');
const agent = new http.Agent({ keepAlive: true, maxSockets: 1 });
function once(port, path) {
  return new Promise((res, rej) => {
    const t0 = process.hrtime.bigint();
    http.get({ host: '127.0.0.1', port, path, agent }, r => {
      r.resume(); r.on('end', () => res(Number(process.hrtime.bigint() - t0) / 1e6));
    }).on('error', rej);
  });
}
(async () => {
  const path = process.env.P || '/api/v1/entries.json?count=10';
  const ports = process.argv.slice(2).map(Number);
  const out = {};
  for (const p of ports) for (let i = 0; i < 100; i++) await once(p, path);
  for (const p of ports) {
    const t = [];
    for (let i = 0; i < 400; i++) t.push(await once(p, path));
    t.sort((a, b) => a - b);
    out[p] = t[200];
    console.log(`port ${p} median=${t[200].toFixed(3)} ms  min=${t[0].toFixed(3)} ms`);
  }
  console.log(`RATIO ${ports[0]}/${ports[1]} = ${(out[ports[0]] / out[ports[1]]).toFixed(2)}x   path=${path}`);
})();
