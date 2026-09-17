const http = require('http');
function once(port, path) {
  return new Promise((res, rej) => {
    const t0 = process.hrtime.bigint();
    http.get({ host: '127.0.0.1', port, path, agent: false }, r => {
      r.resume(); r.on('end', () => res(Number(process.hrtime.bigint() - t0) / 1e6));
    }).on('error', rej);
  });
}
(async () => {
  const path = '/api/v1/entries.json?count=10';
  const ports = process.argv.slice(2).map(Number);
  const out = {};
  for (const p of ports) { for (let i = 0; i < 50; i++) await once(p, path); } // warm
  for (const p of ports) {
    const t = [];
    for (let i = 0; i < 300; i++) t.push(await once(p, path));
    t.sort((a, b) => a - b);
    out[p] = { median: t[150], p10: t[30], mean: t.reduce((a, b) => a + b, 0) / t.length };
  }
  for (const p of ports) console.log(`port ${p}  median=${out[p].median.toFixed(3)} ms  p10=${out[p].p10.toFixed(3)} ms  mean=${out[p].mean.toFixed(3)} ms`);
  const ps = ports;
  console.log(`RATIO median base/cache = ${(out[ps[0]].median / out[ps[1]].median).toFixed(2)}x`);
})();
