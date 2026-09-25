#!/usr/bin/env node
'use strict';
/*
 * analyze.js - turn one rc-soak run directory into a verdict.
 *
 *   RUN=<run dir> node analyze.js      prints a report, writes <run>/analysis.json
 *   exit 0 PASS, 1 FAIL (findings), 2 INVALID (liveness or coverage not shown)
 *
 * Reads what traffic.js, sampler.js, preload.js and lab.sh wrote, plus both
 * arms' databases (the mongo containers must still be up). Checks, in order:
 *   liveness   every arm alive, answering and fresh in the samples (outside
 *              disturbance windows); traffic ran every tick; metrics and
 *              socket data exist. Any gap makes the run INVALID, never PASS.
 *   http       status distribution per endpoint label per arm; any 5xx not in
 *              expected-diffs.json's allow list, and any transport error outside
 *              a disturbance window, is a finding
 *   responses  normalised reply differences between arms, by signature; each
 *              is matched against expected-diffs.json (intentional 15.0.9
 *              changes, with the release-notes section). An A/A run expects none.
 *   ledger     every write an arm acknowledged is in that arm's database
 *              (deleted ones absent, soft-deleted ones isValid=false)
 *   parity     every stored document, normalised, compared between arms as a
 *              multiset; per soakKey: missing, extra, duplicated, or different
 *   memory     heap/RSS leak slope (windowed minima), event-loop delay
 *   latency    p50/p95/p99 per label per arm; B much slower than A is a finding
 *   socket     every acknowledged sgv inside the web client's 48 h window
 *              reached that arm's socket.io follower in a dataUpdate, and how fast
 */
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const RUN = process.env.RUN;
const HERE = __dirname;
const rd = (f) => { const p = path.join(RUN, f); return fs.existsSync(p) ? fs.readFileSync(p, 'utf8') : ''; };
const jsonl = (f) => rd(f).split('\n').filter(Boolean).map((l) => { try { return JSON.parse(l); } catch (e) { return null; } }).filter(Boolean);
const json = (f) => { try { return JSON.parse(rd(f)); } catch (e) { return null; } };
const pct = (xs, p) => { if (!xs.length) return null; const s = [...xs].sort((a, b) => a - b); return s[Math.min(s.length - 1, Math.floor(p * s.length))]; };
const md5 = (s) => crypto.createHash('md5').update(s).digest('hex');
const hexId = (k) => md5('id:' + k).slice(0, 24);
const uuid = (k) => { const h = md5('uuid:' + k); return `${h.slice(0, 8)}-${h.slice(8, 12)}-4${h.slice(13, 16)}-a${h.slice(17, 20)}-${h.slice(20, 32)}`; };
const stable = (v) => JSON.stringify(v, (k, x) => (x && typeof x === 'object' && !Array.isArray(x) ? Object.keys(x).sort().reduce((o, kk) => { o[kk] = x[kk]; return o; }, {}) : x));

const run = json('run.json');
if (!run) { console.error('no run.json in ' + RUN); process.exit(2); }
const { MongoClient } = require(path.join(run.arms.a.dir, 'node_modules', 'mongodb'));
const AA = run.aa === 1;
const expected = JSON.parse(fs.readFileSync(path.join(HERE, 'expected-diffs.json'), 'utf8'));
const findings = []; const invalid = []; const expectedSeen = [];
const find = (kind, msg, extra) => findings.push({ kind, msg, ...(extra || {}) });
function classify (sig) {
  if (AA) return null;
  return expected.diffs.find((e) => new RegExp(e.match).test(sig)) || null;
}

(async () => {
  const report = { run: run.id, aa: AA, arms: run.arms, node: run.node, mongo: run.mongo_version, config: run.config, fault: run.fault };
  const traffic = json('traffic.json'); const done = json('done.json');
  report.traffic = { ...(traffic || {}), done };
  const disturb = jsonl('disturb.jsonl');
  const GRACE = 90000;
  const inWindow = (t) => { const ms = Date.parse(t); return disturb.some((d) => ms >= Date.parse(d.start) - 5000 && ms <= Date.parse(d.end) + GRACE); };
  report.disturbances = disturb;

  // ---------------- liveness and coverage
  if (!traffic) invalid.push('traffic never started (no traffic.json)');
  if (!done) invalid.push('traffic did not finish (no done.json): the driver died or is still running');
  else if (done.ticks_run < done.N && !done.stopped_early) invalid.push(`traffic ran ${done.ticks_run}/${done.N} ticks`);
  const samples = jsonl('samples.jsonl');
  report.liveness = {};
  for (const arm of ['a', 'b']) {
    const ss = samples.map((s) => ({ t: s.t, x: s.samples.find((y) => y.arm === arm) })).filter((s) => s.x);
    const out = ss.filter((s) => !inWindow(s.t));
    const bad = out.filter((s) => !(s.x.proc.alive && s.x.live.ok && s.x.fresh.ok && s.x.mongo.ok));
    report.liveness[arm] = { samples: ss.length, outside_disturbance: out.length, not_ok: bad.length,
      first: ss.length ? ss[0].t : null, last: ss.length ? ss[ss.length - 1].t : null,
      not_ok_examples: bad.slice(0, 3).map((s) => ({ t: s.t, alive: s.x.proc.alive, live: s.x.live.st, fresh: s.x.fresh, mongo: s.x.mongo.ok })) };
    if (ss.length < 5) invalid.push(`arm ${arm}: only ${ss.length} liveness samples`);
    if (bad.length) find('liveness', `arm ${arm}: ${bad.length} of ${out.length} samples not alive/answering/fresh outside disturbance windows`, { examples: report.liveness[arm].not_ok_examples });
    if (out.length && bad.length > out.length * 0.1) invalid.push(`arm ${arm}: more than 10% of samples not live`);
    if (done && ss.length && Date.parse(done.t) - Date.parse(ss[ss.length - 1].t) > 180000) invalid.push(`arm ${arm}: no sample in the last 3 min of traffic`);
    const m = jsonl('metrics-' + arm + '.jsonl');
    if (m.length < 3) invalid.push(`arm ${arm}: ${m.length} in-process metric lines (preload not loaded?)`);
    const so = jsonl('socket-' + arm + '.jsonl');
    if (!so.some((x) => x.ev === 'authorized' && x.read)) invalid.push(`arm ${arm}: socket follower never authorized with read`);
    if (!so.some((x) => x.ev === 'dataUpdate')) invalid.push(`arm ${arm}: socket follower saw no dataUpdate`);
  }

  // ---------------- http
  const reqs = jsonl('requests.jsonl');
  const by = {};
  let transport = { a: 0, b: 0 };
  for (const r of reqs) {
    const arms = r.arm ? [r.arm] : ['a', 'b'];
    r.r.forEach((x, i) => {
      if (!x) return;
      const arm = arms[i]; const k = r.label; by[k] = by[k] || { a: { n: 0, st: {}, ms: [], dep: 0 }, b: { n: 0, st: {}, ms: [], dep: 0 } };
      const o = by[k][arm]; o.n += 1; o.st[x[0]] = (o.st[x[0]] || 0) + 1; o.ms.push(x[1]); o.dep += x[3] || 0;
      if (x[0] === 0 && !inWindow(r.t)) transport[arm] += 1;
      if (x[0] >= 500) {
        const allow = expected.allow_5xx.find((e) => new RegExp(e.label).test(k));
        if (!allow) find('http-5xx', `arm ${arm}: ${k} answered ${x[0]} at ${r.t}`);
      }
    });
  }
  const labels = Object.keys(by).sort();
  report.http = {};
  for (const k of labels) {
    report.http[k] = {};
    for (const arm of ['a', 'b']) {
      const o = by[k][arm];
      report.http[k][arm] = { n: o.n, status: o.st, p50: pct(o.ms, 0.5), p95: pct(o.ms, 0.95), p99: pct(o.ms, 0.99), deprecation: o.dep };
    }
  }
  for (const arm of ['a', 'b']) {
    if (transport[arm]) find('http-transport', `arm ${arm}: ${transport[arm]} requests got no HTTP answer outside disturbance windows`);
    const tot = reqs.reduce((n, r) => n + (r.arm ? (r.arm === arm ? 1 : 0) : 1), 0);
    const ok = reqs.reduce((n, r) => { const i = r.arm ? (r.arm === arm ? 0 : -1) : (arm === 'a' ? 0 : 1); const x = i >= 0 ? r.r[i] : null; return n + (x && x[0] >= 200 && x[0] < 300 ? 1 : 0); }, 0);
    report.liveness[arm].requests = tot; report.liveness[arm].requests_2xx = ok;
    if (tot < 50) invalid.push(`arm ${arm}: only ${tot} requests`);
    else if (ok < tot * 0.8) invalid.push(`arm ${arm}: only ${ok}/${tot} requests answered 2xx`);
  }
  // expected 5xx seen
  for (const e of expected.allow_5xx) {
    const hits = labels.filter((k) => new RegExp(e.label).test(k) && (by[k].a.st['500'] || by[k].b.st['500']));
    if (hits.length) expectedSeen.push({ kind: 'allowed-5xx', label: hits.join(','), why: e.why });
  }

  // ---------------- latency
  report.latency_flags = [];
  {
    for (const k of labels) {
      const a = by[k].a; const b = by[k].b;
      if (a.n < 50 || b.n < 50) continue;
      const pa = pct(a.ms, 0.95); const pb = pct(b.ms, 0.95);
      if (pb > 2 * pa + 20) { report.latency_flags.push({ label: k, p95_a: pa, p95_b: pb, n: b.n }); find('latency', `${k}: p95 ${pb} ms on b vs ${pa} ms on a`); }
      if (pa > 2 * pb + 20) report.latency_flags.push({ label: k, p95_a: pa, p95_b: pb, n: b.n, note: 'b faster' });
    }
  }

  // ---------------- responses
  const sigs = new Map();
  let duringDisturbance = 0;
  for (const r of reqs) {
    if (!r.sig) continue;
    if (inWindow(r.t)) { duringDisturbance += 1; continue; } // one arm back a moment before the other
    const s = sigs.get(r.sig) || { n: 0, first: r.t, label: r.label }; s.n += 1; sigs.set(r.sig, s);
  }
  const diffs = jsonl('diffs.jsonl');
  report.responses = { compared: reqs.filter((r) => !r.arm).length, differing: reqs.filter((r) => r.sig).length, differing_during_disturbance: duringDisturbance, signatures: [] };
  for (const [sig, s] of [...sigs.entries()].sort((x, y) => y[1].n - x[1].n)) {
    const c = sig.startsWith('transient: ') ? { why: 'differed once, matched when re-asked 3 s later (in-memory data reload timing)', section: 'harness: transient', transient: true } : classify(sig);
    const ex = diffs.find((d) => d.sig === sig.replace(/^transient: /, ''));
    const row = { sig, n: s.n, first: s.first, ...(c ? { expected: c.why, release_notes: c.section } : {}), example: ex ? { a: ex.a.slice(0, 400), b: ex.b.slice(0, 400) } : undefined };
    report.responses.signatures.push(row);
    const total = by[s.label] ? by[s.label].a.n : 0;
    if (c && c.transient && s.n > Math.max(3, total * 0.05)) find('response-diff', `${sig} (x${s.n} of ${total}): too many transient differences to be reload timing`);
    else if (c) expectedSeen.push({ kind: 'response', sig, n: s.n, why: c.why, section: c.section, release_notes_gap: Boolean(c.release_notes_gap) });
    else find('response-diff', sig + ` (x${s.n})`, { example: row.example });
  }

  // ---------------- ledger and parity (from mongo)
  const COLLS = ['entries', 'treatments', 'devicestatus', 'profile', 'food', 'activity'];
  const ledger = jsonl('ledger.jsonl');
  const docs = {};
  for (const arm of ['a', 'b']) {
    const cli = new MongoClient(run.mongo_url[arm], { serverSelectionTimeoutMS: 5000 });
    try { await cli.connect(); } catch (err) { invalid.push(`arm ${arm}: mongo not reachable for parity (${err.message}); run analyze before down`); continue; }
    const db = cli.db(); docs[arm] = {};
    for (const c of COLLS) docs[arm][c] = await db.collection(c).find({}).toArray();
    await cli.close();
  }
  report.ledger = {}; report.parity = {};
  if (docs.a && docs.b) {
    for (const arm of ['a', 'b']) {
      const L = ledger.filter((l) => l.arm === arm);
      const state = new Map(); // coll|key -> last act
      // last action wins; a re-send or an edit means the record should be there
      for (const l of L) state.set(l.coll + '|' + l.key, l.act === 'delete' || l.act === 'softdel' ? l.act : 'present');
      const idx = {}; for (const c of COLLS) { idx[c] = new Map(); for (const d of docs[arm][c]) if (d.soakKey) idx[c].set(d.soakKey, (idx[c].get(d.soakKey) || []).concat([d])); }
      const missing = []; const notDeleted = []; const notSoft = [];
      for (const [k, act] of state) {
        const [c, key] = k.split('|'); const have = idx[c].get(key) || [];
        if (act === 'delete') { if (have.length) notDeleted.push(k); } else if (act === 'softdel') { if (!have.length || have.some((d) => d.isValid !== false)) notSoft.push(k); } else if (!have.length) missing.push(k);
      }
      report.ledger[arm] = { acknowledged_keys: state.size, missing: missing.length, missing_examples: missing.slice(0, 10), delete_not_applied: notDeleted.length, delete_examples: notDeleted.slice(0, 5), softdelete_not_applied: notSoft.length };
      if (missing.length) find('ledger', `arm ${arm}: ${missing.length} acknowledged writes are not in its database`, { examples: missing.slice(0, 10) });
      if (notDeleted.length) find('ledger', `arm ${arm}: ${notDeleted.length} acknowledged deletes left the record in place`, { examples: notDeleted.slice(0, 5) });
      if (notSoft.length) find('ledger', `arm ${arm}: ${notSoft.length} acknowledged v3 deletes not marked isValid=false`, { examples: notSoft.slice(0, 5) });
      report.ledger[arm].state = state;
    }
    // writes one arm acknowledged and the other did not
    const sa = report.ledger.a.state; const sb = report.ledger.b.state;
    const asym = [...new Set([...sa.keys(), ...sb.keys()])].filter((k) => sa.get(k) !== sb.get(k));
    if (asym.length) find('ledger', `${asym.length} writes acknowledged differently by the two arms`, { examples: asym.slice(0, 10).map((k) => k + ' a=' + sa.get(k) + ' b=' + sb.get(k)) });
    delete report.ledger.a.state; delete report.ledger.b.state;

    const normDoc = (d) => {
      const o = {};
      for (const k of Object.keys(d)) {
        if (k === 'srvModified' || k === 'srvCreated') continue;
        if (k === '_id') { const s = String(d._id); if (d.soakKey && s === hexId(d.soakKey)) o._id = 'client:' + s; continue; }
        if (k === 'identifier') { o.identifier = d.soakKey && d.identifier === uuid(d.soakKey) ? d.identifier : '<server>'; continue; }
        o[k] = d[k];
      }
      return stable(o);
    };
    const idForm = (arr) => arr.reduce((m, d) => { const f = d._id && d._id.constructor ? d._id.constructor.name : typeof d._id; m[f] = (m[f] || 0) + 1; return m; }, {});
    for (const c of COLLS) {
      const A = docs.a[c]; const B = docs.b[c];
      const ms = (arr) => { const m = new Map(); for (const d of arr) { const k = normDoc(d); m.set(k, (m.get(k) || 0) + 1); } return m; };
      const ma = ms(A); const mb = ms(B);
      let onlyA = 0; let onlyB = 0; const exA = []; const exB = [];
      for (const [k, n] of ma) { const d = n - (mb.get(k) || 0); if (d > 0) { onlyA += d; if (exA.length < 50) exA.push(JSON.parse(k)); } }
      for (const [k, n] of mb) { const d = n - (ma.get(k) || 0); if (d > 0) { onlyB += d; if (exB.length < 50) exB.push(JSON.parse(k)); } }
      // explain by soakKey: which field differs, or missing/duplicated
      const keyed = (arr) => { const m = new Map(); for (const d of arr) if (d.soakKey) m.set(d.soakKey, (m.get(d.soakKey) || []).concat([JSON.parse(normDoc(d))])); return m; };
      const ka = keyed(A); const kb = keyed(B);
      const kinds = {};
      const addKind = (sig, key) => { kinds[sig] = kinds[sig] || { n: 0, keys: [] }; kinds[sig].n += 1; if (kinds[sig].keys.length < 5) kinds[sig].keys.push(key); };
      for (const key of new Set([...ka.keys(), ...kb.keys()])) {
        const xa = ka.get(key) || []; const xb = kb.get(key) || [];
        if (!xa.length) { addKind(`parity ${c}: soakKey only in B`, key); continue; }
        if (!xb.length) { addKind(`parity ${c}: soakKey only in A`, key); continue; }
        if (xa.length !== xb.length) addKind(`parity ${c}: copies per soakKey ${xa.length} in A, ${xb.length} in B`, key);
        const fa = stable(xa.map(stable).sort()); const fb = stable(xb.map(stable).sort());
        if (fa !== fb && xa.length === xb.length) {
          const fields = new Set();
          xa.forEach((da, i) => { const db = xb[i]; for (const f of new Set([...Object.keys(da), ...Object.keys(db)])) if (stable(da[f]) !== stable(db[f])) fields.add(f + (!(f in da) ? ' (only B)' : !(f in db) ? ' (only A)' : '')); });
          addKind(`parity ${c}: fields differ: ${[...fields].sort().join(', ')}`, key);
        }
      }
      const noKey = { a: A.filter((d) => !d.soakKey).length, b: B.filter((d) => !d.soakKey).length };
      report.parity[c] = { count: { a: A.length, b: B.length }, only_a: onlyA, only_b: onlyB, no_soakKey: noKey, id_form: { a: idForm(A), b: idForm(B) }, kinds };
      for (const [sig, v] of Object.entries(kinds)) {
        // a write whose reply was lost in a disturbance is re-sent, as an uploader would; if the
        // first attempt had reached one arm's server, that arm stores it twice. Only keys whose
        // every acknowledgement fell inside a disturbance window are explained this way.
        const disturbed = v.keys.length === v.n && v.keys.every((key) => { const ls = ledger.filter((l) => l.coll === c && l.key === key); return ls.length && ls.some((l) => inWindow(l.t)); });
        if (disturbed && /copies per soakKey|only in/.test(sig)) { expectedSeen.push({ kind: 'parity', sig, n: v.n, why: 'write re-sent after its reply was lost in a disturbance window: ' + v.keys.join(' '), section: 'harness: disturbance' }); continue; }
        const cl = classify(sig);
        if (cl) expectedSeen.push({ kind: 'parity', sig, n: v.n, why: cl.why, section: cl.section });
        else find('parity', `${sig} (x${v.n})`, { keys: v.keys });
      }
      if ((onlyA || onlyB) && !Object.keys(kinds).length) find('parity', `parity ${c}: ${onlyA} docs only in A, ${onlyB} only in B (no soakKey)`, { a: exA.slice(0, 2), b: exB.slice(0, 2) });
    }
  }

  // ---------------- memory and event loop
  report.memory = {};
  const slope = (pts) => { // least squares, y per hour
    if (pts.length < 3) return null;
    const n = pts.length; const mx = pts.reduce((s, p) => s + p[0], 0) / n; const my = pts.reduce((s, p) => s + p[1], 0) / n;
    const sxx = pts.reduce((s, p) => s + (p[0] - mx) ** 2, 0); const sxy = pts.reduce((s, p) => s + (p[0] - mx) * (p[1] - my), 0);
    return sxx ? sxy / sxx : null;
  };
  for (const arm of ['a', 'b']) {
    const m = jsonl('metrics-' + arm + '.jsonl');
    if (m.length < 3) continue;
    // one process lifetime per pid; the slope uses the longest one (restarts reset memory)
    const byPid = {}; m.forEach((x) => { (byPid[x.pid] = byPid[x.pid] || []).push(x); });
    const life = Object.values(byPid).sort((x, y) => y.length - x.length)[0];
    const t0 = Date.parse(life[0].t); const span = Date.parse(life[life.length - 1].t) - t0;
    const skip = t0 + span * 0.25; const W = Math.max(60000, span / 25); // skip start-up and cache warm-up
    const win = {}; for (const x of life) { const t = Date.parse(x.t); if (t < skip) continue; const w = Math.floor((t - t0) / W); if (!win[w] || x.heapUsed < win[w].heapUsed) win[w] = x; }
    const mins = Object.values(win);
    const hs = slope(mins.map((x) => [(Date.parse(x.t) - t0) / 3600000, x.heapUsed / 1048576]));
    const rs = slope(mins.map((x) => [(Date.parse(x.t) - t0) / 3600000, x.rss / 1048576]));
    const reqSpan = (life[life.length - 1].requests - life[0].requests) || 1;
    const hoursSpan = span / 3600000;
    report.memory[arm] = { processes: Object.keys(byPid).length, samples: life.length, span_min: Math.round(span / 60000),
      heap_mb: { first: +(life[0].heapUsed / 1048576).toFixed(1), last: +(life[life.length - 1].heapUsed / 1048576).toFixed(1), max: +(Math.max(...life.map((x) => x.heapUsed)) / 1048576).toFixed(1) },
      rss_mb: { first: +(life[0].rss / 1048576).toFixed(1), last: +(life[life.length - 1].rss / 1048576).toFixed(1), max: +(Math.max(...life.map((x) => x.rss)) / 1048576).toFixed(1) },
      heap_slope_mb_per_h: hs === null ? null : +hs.toFixed(2), rss_slope_mb_per_h: rs === null ? null : +rs.toFixed(2),
      heap_slope_mb_per_10k_req: hs === null ? null : +(hs * hoursSpan / reqSpan * 10000).toFixed(2), requests: reqSpan,
      lag_ms: { p50_of_p50: pct(life.map((x) => x.lag_p50), 0.5), p99_of_p99: pct(life.map((x) => x.lag_p99), 0.99), max: Math.max(...life.map((x) => x.lag_max)) },
      elu_p95: pct(life.map((x) => x.elu), 0.95), handles_last: life[life.length - 1].handles };
  }
  const minSpan = expected.thresholds.leak_min_span_min;
  if (report.memory.a && report.memory.b && Math.min(report.memory.a.span_min, report.memory.b.span_min) < minSpan) {
    report.memory.leak_check = `not evaluated: a process lifetime shorter than ${minSpan} min`;
  } else if (report.memory.a && report.memory.b) {
    report.memory.leak_check = 'evaluated';
    for (const [x, y] of [['a', 'b'], ['b', 'a']]) {
      const mx = report.memory[x]; const my = report.memory[y];
      // leak: heap minima grow faster than the other arm by a clear margin, per request and per hour
      // leak: over the evaluated span, one arm's heap minima grow more than the other's by a clear margin
      const spanH = Math.min(mx.span_min, my.span_min) * 0.75 / 60;
      const extra = (mx.heap_slope_mb_per_h - my.heap_slope_mb_per_h) * spanH;
      report.memory['growth_diff_mb_' + x + '_minus_' + y] = +extra.toFixed(1);
      const extraRss = (mx.rss_slope_mb_per_h - my.rss_slope_mb_per_h) * spanH;
      report.memory['rss_growth_diff_mb_' + x + '_minus_' + y] = +extraRss.toFixed(1);
      if (extraRss > expected.thresholds.rss_growth_mb) find('memory', `arm ${x}: RSS minima grew ${extraRss.toFixed(1)} MB more than arm ${y}'s over ${(spanH * 60).toFixed(0)} min (${mx.rss_slope_mb_per_h} vs ${my.rss_slope_mb_per_h} MB/h)`);
      if (extra > expected.thresholds.leak_growth_mb) {
        find('memory', `arm ${x}: heap minima grew ${extra.toFixed(1)} MB more than arm ${y}'s over ${(spanH * 60).toFixed(0)} min (${mx.heap_slope_mb_per_h} vs ${my.heap_slope_mb_per_h} MB/h; ${mx.heap_slope_mb_per_10k_req} vs ${my.heap_slope_mb_per_10k_req} MB/10k requests)`);
      }
      if (mx.lag_ms.p99_of_p99 > 2 * my.lag_ms.p99_of_p99 + expected.thresholds.lag_ms) find('event-loop', `arm ${x}: event-loop delay p99 ${mx.lag_ms.p99_of_p99} ms vs ${my.lag_ms.p99_of_p99} ms`);
    }
  }

  // ---------------- socket delivery
  report.socket = {};
  if (traffic) {
    const simStart = Date.parse(traffic.simStart); const simAt = (n) => simStart + n * 300000 + 7000;
    const end = done ? Date.parse(done.t) : Date.now();
    for (const arm of ['a', 'b']) {
      const so = jsonl('socket-' + arm + '.jsonl');
      const seen = new Map(); const trSeen = new Set();
      for (const x of so) if (x.ev === 'dataUpdate') { for (const m of x.sgv || []) if (!seen.has(m)) seen.set(m, Date.parse(x.t)); (x.tr || []).forEach((k) => trSeen.add(k)); }
      const deleted = new Set(ledger.filter((l) => l.arm === arm && l.act === 'delete').map((l) => l.key));
      const acks = ledger.filter((l) => l.arm === arm && l.coll === 'entries' && l.act === 'ack' && /^sgv-/.test(l.key) && !deleted.has(l.key));
      let eligible = 0; let got = 0; const delays = []; const miss = [];
      for (const l of acks) {
        const d = simAt(Number(l.key.slice(4))); const at = Date.parse(l.t);
        if (d < at - 47 * 3600000 || at > end - 60000 || inWindow(l.t)) continue;
        eligible += 1;
        const s = seen.get(d);
        if (s !== undefined) { got += 1; delays.push(Math.max(0, s - at)); } else miss.push(l.key);
      }
      const disc = so.filter((x) => x.ev === 'disconnect' && x.why !== 'io client disconnect' && !inWindow(x.t)).length; // the driver's own close at the end is not a drop
      report.socket[arm] = { dataUpdates: so.filter((x) => x.ev === 'dataUpdate').length, disconnects_outside_disturbance: disc, sgv_eligible: eligible, sgv_delivered: got,
        delay_ms: { p50: pct(delays, 0.5), p95: pct(delays, 0.95), max: delays.length ? Math.max(...delays) : null }, missed_examples: miss.slice(0, 5), treatments_seen: trSeen.size };
      if (eligible && got < eligible) find('socket', `arm ${arm}: ${eligible - got} of ${eligible} acknowledged sgv never arrived in a dataUpdate`, { examples: miss.slice(0, 5) });
      if (disc) find('socket', `arm ${arm}: follower socket disconnected ${disc} times outside disturbance windows`);
    }
  }
  // page loads: what a newly opened web page is sent. Per arm, nothing the arm acknowledged
  // deleting may be in it; between arms, the same load must show the same records.
  report.pageload = {};
  if (traffic && !(traffic.harness >= 2)) report.pageload.note = 'not recorded: run made before page loads were added (harness < 2)';
  else if (traffic) {
    const loads = { a: jsonl('pageload-a.jsonl'), b: jsonl('pageload-b.jsonl') };
    for (const arm of ['a', 'b']) {
      const dels = ledger.filter((l) => l.arm === arm && l.act === 'delete').map((l) => ({ key: l.key, coll: l.coll, t: Date.parse(l.t) }));
      const simStart = Date.parse(traffic.simStart);
      const shown = []; let errors = 0;
      for (const p of loads[arm]) {
        if (p.error) { if (!inWindow(p.t)) errors += 1; continue; }
        const at = Date.parse(p.t); const trs = new Set(p.tr); const dss = new Set(p.ds); const sgvs = new Set(p.sgv);
        for (const d of dels) {
          if (d.t > at - 5000) continue; // allow 5 s after the delete was acknowledged
          const on = d.coll === 'treatments' ? trs.has(d.key) : d.coll === 'devicestatus' ? dss.has(d.key) : sgvs.has(simStart + Number(d.key.split('-')[1]) * 300000 + 7000);
          if (on) shown.push({ key: d.key, coll: d.coll, deleted: new Date(d.t).toISOString(), load: p.t });
        }
      }
      const uniq = [...new Map(shown.map((x) => [x.coll + '|' + x.key, x])).values()];
      report.pageload[arm] = { loads: loads[arm].length, errors, deleted_records_shown: uniq.length, examples: uniq.slice(0, 5) };
      if (loads[arm].length < 2) invalid.push(`arm ${arm}: ${loads[arm].length} page loads recorded`);
      if (errors) find('pageload', `arm ${arm}: ${errors} page loads got no dataUpdate outside disturbance windows`);
      if (uniq.length) find('pageload', `arm ${arm}: ${uniq.length} records it acknowledged deleting were still sent to a newly opened web page`, { examples: uniq.slice(0, 5).map((x) => `${x.coll} ${x.key} deleted ${x.deleted}, shown ${x.load}`) });
    }
    const byN = (arr) => new Map(arr.filter((p) => !p.error).map((p) => [p.n, p]));
    const la = byN(loads.a); const lb = byN(loads.b); let differ = 0; let fresh = 0; const ex = [];
    // a record acknowledged moments before the load may or may not be in that arm's in-memory
    // data yet (the reload is asynchronous); only records older than FRESH_MS must match
    const FRESH_MS = 10000;
    const lastAck = new Map(); for (const l of ledger) { const k = l.coll + '|' + l.key; const t = Date.parse(l.t); if (!(lastAck.get(k) > t)) lastAck.set(k, t); }
    const simStart0 = Date.parse(traffic.simStart);
    const keyOf = (f, x) => f === 'sgv' ? 'entries|sgv-' + Math.round((x - simStart0 - 7000) / 300000) : (f === 'tr' ? 'treatments|' : 'devicestatus|') + x;
    for (const [n, pa] of la) {
      const pb = lb.get(n); if (!pb || inWindow(pa.t)) continue;
      const at = Date.parse(pa.t);
      for (const f of ['sgv', 'tr', 'ds']) {
        const A = new Set(pa[f]); const B = new Set(pb[f]);
        const young = (x) => { const t = lastAck.get(keyOf(f, x)); const y = t !== undefined && t > at - FRESH_MS; if (y) fresh += 1; return y; };
        const oa = [...A].filter((x) => !B.has(x) && !young(x)); const ob = [...B].filter((x) => !A.has(x) && !young(x));
        if (oa.length || ob.length) { differ += 1; if (ex.length < 5) ex.push(`load n=${n} ${f}: only a ${oa.slice(0, 3).join(' ')} | only b ${ob.slice(0, 3).join(' ')}`); }
      }
    }
    report.pageload.differ_between_arms = differ; report.pageload.ignored_just_written = fresh;
    if (differ) find('pageload', `${differ} page-load collections differ between the arms`, { examples: ex });
  }
  report.proxy_drops = {};
  for (const arm of ['a', 'b']) { const l = rd('proxy-' + arm + '.log').split('\n').filter((x) => x.includes('"dropped"')); if (l.length || run.fault.drop_devicestatus) report.proxy_drops[arm] = l.length; }

  report.invalid = invalid; report.findings = findings; report.expected_seen = expectedSeen;
  report.verdict = invalid.length ? 'INVALID' : findings.length ? 'FAIL' : 'PASS';
  fs.writeFileSync(path.join(RUN, 'analysis.json'), JSON.stringify(report, null, 1));
  print(report);
  process.exit(report.verdict === 'PASS' ? 0 : report.verdict === 'FAIL' ? 1 : 2);
})().catch((err) => { console.error(err); process.exit(2); });

function print (r) {
  const L = (s) => console.log(s);
  L(`# rc-soak ${r.run}: ${r.verdict}`);
  L(`a ${r.arms.a.head.slice(0, 8)} (${r.arms.a.version}, tree ${r.arms.a.tree.slice(0, 8)})  b ${r.arms.b.head.slice(0, 8)} (${r.arms.b.version}, tree ${r.arms.b.tree.slice(0, 8)})${r.aa ? '  [A/A control]' : ''}`);
  L(`node ${r.node}, mongo a ${r.mongo.a} b ${r.mongo.b}, AUTH_DEFAULT_ROLES=${r.config}, fault ${JSON.stringify(r.fault)}`);
  if (r.traffic.mode) L(`traffic ${r.traffic.mode}: ${r.traffic.done ? r.traffic.done.ticks_run : '?'}/${r.traffic.ticks} ticks, sim ${r.traffic.simStart} .. ${r.traffic.simEnd}, late ticks ${r.traffic.done ? r.traffic.done.lateTicks : '?'}`);
  L(`disturbances: ${r.disturbances.length ? r.disturbances.map((d) => d.action + '(' + d.arms + ')@' + d.start).join(', ') : 'none'}`);
  for (const a of ['a', 'b']) { const l = r.liveness[a]; L(`liveness ${a}: ${l.samples} samples, ${l.not_ok} not ok; requests ${l.requests} (${l.requests_2xx} 2xx)`); }
  L('\n## http (label: a status / p50 p95 p99 ms | b status / p50 p95 p99 ms)');
  for (const [k, v] of Object.entries(r.http)) L(`${k}: ${JSON.stringify(v.a.status)} ${v.a.p50}/${v.a.p95}/${v.a.p99}${v.a.deprecation ? ' dep' + v.a.deprecation : ''} | ${JSON.stringify(v.b.status)} ${v.b.p50}/${v.b.p95}/${v.b.p99}${v.b.deprecation ? ' dep' + v.b.deprecation : ''}`);
  L(`\n## responses: ${r.responses.differing} of ${r.responses.compared} compared operations differ (${r.responses.differing_during_disturbance} inside disturbance windows, not counted), ${r.responses.signatures.length} signatures`);
  for (const s of r.responses.signatures) L(`- x${s.n} ${s.sig}${s.expected ? '  [expected: ' + s.release_notes + ']' : '  [UNEXPECTED]'}`);
  const gaps = r.expected_seen.filter((e) => e.release_notes_gap);
  if (gaps.length) L(`release-notes gaps (expected by a decision record, not described in release-notes.md): ${gaps.map((e) => e.sig).join('; ')}`);
  L('\n## ledger');
  for (const [a, v] of Object.entries(r.ledger)) L(`${a}: ${v.acknowledged_keys} keys, missing ${v.missing}, delete not applied ${v.delete_not_applied}, soft-delete not applied ${v.softdelete_not_applied}`);
  L('\n## parity (count a/b, only a, only b; kinds)');
  for (const [c, v] of Object.entries(r.parity)) { L(`${c}: ${v.count.a}/${v.count.b}, only a ${v.only_a}, only b ${v.only_b}, _id a ${JSON.stringify(v.id_form.a)} b ${JSON.stringify(v.id_form.b)}`); for (const [k, x] of Object.entries(v.kinds)) L(`  - x${x.n} ${k} e.g. ${x.keys.slice(0, 3).join(' ')}`); }
  L('\n## memory');
  if (r.memory.leak_check) L('leak check: ' + r.memory.leak_check + (r.memory.growth_diff_mb_b_minus_a !== undefined ? `; heap growth b-a ${r.memory.growth_diff_mb_b_minus_a} MB, a-b ${r.memory.growth_diff_mb_a_minus_b} MB (threshold ${expected.thresholds.leak_growth_mb}); RSS growth b-a ${r.memory.rss_growth_diff_mb_b_minus_a} MB (threshold ${expected.thresholds.rss_growth_mb})` : ''));
  for (const [a, m] of Object.entries(r.memory)) if (m.heap_mb) L(`${a}: heap ${m.heap_mb.first}->${m.heap_mb.last} MB (max ${m.heap_mb.max}), slope ${m.heap_slope_mb_per_h} MB/h = ${m.heap_slope_mb_per_10k_req} MB/10k req; rss ${m.rss_mb.first}->${m.rss_mb.last} MB slope ${m.rss_slope_mb_per_h} MB/h; lag p50 ${m.lag_ms.p50_of_p50} p99 ${m.lag_ms.p99_of_p99} max ${m.lag_ms.max} ms; elu p95 ${m.elu_p95}; ${m.processes} process(es)`);
  L('\n## socket');
  for (const [a, s] of Object.entries(r.socket)) L(`${a}: ${s.dataUpdates} dataUpdates, sgv delivered ${s.sgv_delivered}/${s.sgv_eligible}, delay p50 ${s.delay_ms.p50} p95 ${s.delay_ms.p95} max ${s.delay_ms.max} ms, disconnects ${s.disconnects_outside_disturbance}`);
  L('\n## page loads (full dataUpdate sent to a newly opened page)');
  for (const a of ['a', 'b']) if (r.pageload[a]) L(`${a}: ${r.pageload[a].loads} loads, ${r.pageload[a].errors} errors, deleted records shown ${r.pageload[a].deleted_records_shown}`);
  if (r.pageload.differ_between_arms !== undefined) L(`differ between arms: ${r.pageload.differ_between_arms} (records acknowledged under 10 s before a load are not compared: ${r.pageload.ignored_just_written})`);
  if (Object.keys(r.proxy_drops).length) L(`\nproxy silent drops (fault injection): ${JSON.stringify(r.proxy_drops)}`);
  if (r.expected_seen.length) { L('\n## expected differences seen'); for (const e of r.expected_seen) L(`- ${e.kind}: ${e.sig || e.label}${e.n ? ' x' + e.n : ''} -- ${e.section || ''} ${e.why}`); }
  L(`\n## invalid (${r.invalid.length})`); r.invalid.forEach((x) => L('- ' + x));
  L(`\n## findings (${r.findings.length})`); r.findings.forEach((f) => L(`- [${f.kind}] ${f.msg}${f.examples ? ' e.g. ' + JSON.stringify(f.examples).slice(0, 300) : ''}${f.keys ? ' e.g. ' + f.keys.join(' ') : ''}`));
  L(`\nVERDICT ${r.verdict}`);
}
