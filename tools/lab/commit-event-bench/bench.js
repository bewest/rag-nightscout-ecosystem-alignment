'use strict';
// Axis (a): write latency and throughput, base vs prototype, interleaved.
//
//   node bench.js --mongo mongodb://127.0.0.1:27601 --n 200 --nbulk 200 --out results/latency.json \
//     --arm base=<tree>:count --arm base2=<tree>:count --arm noop=<tree>:count \
//     --arm proto=<tree>:count --arm proto0=<tree>:none
//
// Every arm is its own server.js process and database on the same mongod. For
// each iteration and each shape (shape order shuffled per iteration), every
// arm is seeded (untimed), then the measured call runs once per arm in a
// shuffled arm order: the arms see the same load at the same time, so drift
// in the machine or mongod lands on all of them alike.
//
// Controls: base2 is the same tree as base in a second process (noise floor);
// noop is base plus one comment line (a no-op commit). Their ratios to base
// bound what "no difference" looks like.
const fs = require('fs');
const path = require('path');
const L = require('./lib');
const argv = process.argv.slice(2);
const opt = (n, d) => { const i = argv.indexOf(n); return i === -1 ? d : argv[i + 1]; };
const arms = []; argv.forEach((a, i) => { if (a === '--arm') { const [name, rest] = argv[i + 1].split('='); const [tree, listener] = rest.split(':'); arms.push({ name, tree, listener: listener || 'count' }); } });
const MONGO = opt('--mongo', 'mongodb://127.0.0.1:27601');
const N = +opt('--n', 200), NBULK = +opt('--nbulk', 200), NBIG = +opt('--nbig', 10);
const ONLY = opt('--only', null);
const OUT = path.resolve(opt('--out', path.join(__dirname, 'results', 'latency.json')));

(async () => {
  const run = L.hex().slice(0, 6);
  const live = [];
  for (const a of arms) live.push(await L.startArm(a.name, a.tree, MONGO, 'devent_lat_' + a.name + '_' + run, a.listener));
  const shapes = Object.assign({}, L.SHAPES, L.BULK);
  const names = Object.keys(shapes).filter(n => !ONLY || ONLY.split(',').includes(n));
  const times = {}; names.forEach(n => { times[n] = {}; live.forEach(a => { times[n][a.name] = []; }); });
  const errors = {};
  const limit = name => name in L.BULK ? (/-10000$/.test(name) ? NBIG : NBULK) : N;
  const maxIter = Math.max(...names.map(limit));
  const t0 = Date.now();
  for (let it = 0; it < maxIter; it++) {
    for (const name of L.shuffle(names.slice())) {
      if (it >= limit(name)) continue;
      const s = shapes[name];
      const seeds = {};
      // A failed seed (round 3: a v3 POST without a JSON reply crashed the run)
      // is counted as an error of that arm and shape; its call is not timed.
      const SEED_FAILED = {};
      for (const a of live) {
        try { seeds[a.name] = s.seed ? await s.seed(a, name + '-' + run + '-' + it + '-' + a.name) : undefined; }
        catch (e) { seeds[a.name] = SEED_FAILED; errors[name + ' ' + a.name + ' seed'] = (errors[name + ' ' + a.name + ' seed'] || 0) + 1; }
      }
      for (const a of L.shuffle(live.slice())) {
        if (seeds[a.name] === SEED_FAILED) continue;
        const tag = name + '-' + run + '-' + it + '-' + a.name;
        const st = process.hrtime.bigint();
        const r = await s.run(a, tag, seeds[a.name]);
        const ms = Number(process.hrtime.bigint() - st) / 1e6;
        const ok = r === 'NO-ACK' ? false : (r && r.s !== undefined ? r.s < 300 : true);
        if (!ok) { errors[name + ' ' + a.name] = (errors[name + ' ' + a.name] || 0) + 1; continue; }
        times[name][a.name].push(ms);
      }
    }
    if (it % 25 === 0) console.error('iteration ' + it + ' (' + Math.round((Date.now() - t0) / 1000) + ' s)');
  }
  const counts = {};
  for (const a of live) { counts[a.name] = (await a.events()).count; }
  for (const a of live) await a.stop();

  const result = { run, mongo: MONGO, node: process.version, n: N, nbulk: NBULK, nbig: NBIG, arms: arms.map(a => Object.assign({}, a, {
    head: require('child_process').execFileSync('git', ['-C', a.tree, 'rev-parse', 'HEAD']).toString().trim() })),
  wallSeconds: (Date.now() - t0) / 1000, errors, eventCounts: counts, shapes: {} };
  const ref = live[0].name;
  for (const n of names) {
    result.shapes[n] = {};
    for (const a of live) {
      const s = L.stats(times[n][a.name]);
      const r = L.stats(times[n][ref]);
      result.shapes[n][a.name] = Object.assign(s, { medianRatio: s.median / r.median, p95Ratio: s.p95 / r.p95,
        perSecond: 1000 / s.mean });
    }
  }
  fs.mkdirSync(path.dirname(OUT), { recursive: true });
  fs.writeFileSync(OUT, JSON.stringify(result, null, 1));
  // table: median ms and ratio to the first arm
  console.log('| shape | ' + live.map(a => a.name + ' med / p95 ms').join(' | ') + ' | ' + live.slice(1).map(a => a.name + '/' + ref + ' med, p95').join(' | ') + ' |');
  console.log('|---|' + live.map(() => '---').join('|') + '|' + live.slice(1).map(() => '---').join('|') + '|');
  for (const n of names) {
    const row = result.shapes[n];
    console.log('| ' + n + ' | ' + live.map(a => row[a.name].median.toFixed(2) + ' / ' + row[a.name].p95.toFixed(2)).join(' | ') + ' | '
      + live.slice(1).map(a => row[a.name].medianRatio.toFixed(3) + ', ' + row[a.name].p95Ratio.toFixed(3)).join(' | ') + ' |');
  }
  console.log('errors: ' + JSON.stringify(errors) + '; events seen by each arm\'s listener: ' + JSON.stringify(counts));
  process.exit(0);
})().catch(e => { console.error(e); process.exit(2); });
