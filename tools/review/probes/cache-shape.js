#!/usr/bin/env node
'use strict';
/*
 * cache-shape.js — P0-B / bf/cache (#8740), register BF-06 and BF-07; and
 * P0-T01 / the quadratics PR (#8733) uses the same shape method.
 *
 * WHY THIS IS A SHAPE ASSERTION AND NOT A RATIO THRESHOLD.
 *
 * The first draft of the plan required "the per-request cost on RC is >= 100x
 * below BASE". Two independent refuters measured that and it is UNREACHABLE ON
 * THE CORRECT BUILD: at the plan's own prescribed windows the request-level
 * ratio is 1.66-1.87x (288 entries), 2.49x (576) and 14.10x (5700); in-handler
 * it is ~27x; only an isolated JSON-clone microbenchmark reaches ~976x, and
 * that never calls getData or getDataRef. A gate stuck red on the correct
 * build gets disabled, which leaves the branch's headline claim ungated — the
 * exact failure the threshold was meant to prevent.
 *
 * The defect is not "slow". It is "cost grows with the size of the retained
 * window when it should not": cache.insertData JSON round-trips the whole
 * retained array, so a read of ten entries pays for forty-eight hours of them.
 * That is a statement about the SHAPE of the cost curve, so the gate asserts
 * the shape:
 *
 *    BASE  cost(dense) / cost(sparse)  >=  GROWTH_MIN   (cost tracks the window)
 *    RC    cost(dense) / cost(sparse)  <=  FLAT_MAX     (cost does not)
 *
 * Both arms are needed. The BASE arm is the control: if BASE does not grow on
 * this machine, the fixture is too small and the RC arm proves nothing.
 *
 * The thresholds are deliberately loose. This is wall-clock on a shared
 * machine; the claim being tested is a difference in kind (grows vs flat), not
 * a coefficient. A tighter bound would be measuring the load average.
 */

const path = require('path');
const http = require('http');
const fs = require('fs');
const crypto = require('crypto');
const { execFileSync } = require('child_process');
const { report } = require(path.resolve(__dirname, '..', '..', 'queue', 'gates', '_gate.js'));

const GROWTH_MIN = 2.5;   // BASE must be at least this much slower when dense
const FLAT_MAX = 1.8;     // RC must be no more than this much slower
const WARMUP = 40, SAMPLES = 200;

// A keep-alive agent, and a retry. Without the agent this probe opened ~480
// sockets in a tight loop and the server answered one with a bare FIN —
// 'socket hang up' — which killed the whole run. The defect under test is a
// per-request cost, so connection reuse is the right shape anyway: it removes
// TCP setup from a measurement that is not about TCP setup.
const AGENT = new http.Agent({ keepAlive: true, maxSockets: 1 });

function get(url, p, sha1) {
  return new Promise((res, rej) => {
    const u = new URL(p, url);
    const t0 = process.hrtime.bigint();
    const r = http.request({ hostname: u.hostname, port: u.port, path: u.pathname + u.search,
      method: 'GET', headers: { 'api-secret': sha1 }, agent: AGENT }, x => {
      x.on('data', () => {});
      x.on('end', () => res(Number(process.hrtime.bigint() - t0) / 1e6));
    });
    r.on('error', rej); r.end();
  });
}

async function getRetry(url, p, sha1) {
  for (let i = 0; i < 3; i++) {
    try { return await get(url, p, sha1); }
    catch (e) { if (i === 2) throw e; await new Promise(r => setTimeout(r, 250)); }
  }
}

const median = a => { const s = a.slice().sort((x, y) => x - y); return s[Math.floor(s.length / 2)]; };

async function costOf(url, sha1) {
  for (let i = 0; i < WARMUP; i++) await getRetry(url, '/api/v1/entries.json?count=10', sha1);
  const s = [];
  for (let i = 0; i < SAMPLES; i++) s.push(await getRetry(url, '/api/v1/entries.json?count=10', sha1));
  return median(s);
}

function reseed(state, url, secret, cadenceSec, root, nsctl) {
  execFileSync('bash', [nsctl, 'reset', state, 'production'],
    { stdio: ['ignore', 'ignore', 'ignore'], env: { ...process.env, NSREVIEW_ROOT: root } });
  const port = require('fs').readFileSync(`${root}/run/${state}.port`, 'utf8').trim();
  execFileSync(process.execPath, [path.join(__dirname, '..', 'seed.js'),
    '--url', `http://127.0.0.1:${port}`, '--secret', secret,
    '--hours', '47', '--cadence-sec', String(cadenceSec),
    '--mongo-db', `nsreview_${state}`, '--no-adversarial'],
    { stdio: ['ignore', 'ignore', 'ignore'] });
  return `http://127.0.0.1:${port}`;
}

(async () => {
  const a = process.argv.slice(2);
  const g = k => { const i = a.indexOf(k); return i >= 0 ? a[i + 1] : null; };
  // NOT the shared BASE by default. This probe RESEEDS and RESTARTS whatever
  // it is pointed at, in production mode — pointing it at BASE silently drops
  // BASE out of the development mode the browser probes require, and the next
  // provenance run then fails for a reason that has nothing to do with any
  // branch. PERFBASE is a dedicated dev-pinned worktree.
  const baseState = g('--base-state') || 'PERFBASE';
  const candState = g('--candidate-state');
  const secret = g('--secret');
  const root = process.env.NSREVIEW_ROOT;
  if (!candState || !secret || !root) {
    console.error('need --candidate-state, --secret and $NSREVIEW_ROOT'); process.exit(2);
  }
  const nsctl = path.join(__dirname, '..', 'nsctl.sh');
  const sha1 = crypto.createHash('sha1').update(secret).digest('hex');
  const findings = [];
  const cost = {};

  // SPARSE first, then DENSE, on the same instance — so the only thing that
  // differs between the two numbers for a build is the size of the retained
  // window, not the port, the process or the machine's mood.
  for (const state of [baseState, candState]) {
    for (const [label, cadence] of [['sparse', 300], ['dense', 30]]) {
      const url = reseed(state, null, secret, cadence, root, nsctl);
      cost[`${state}:${label}`] = await costOf(url, sha1);
    }
  }

  const ratio = s => cost[`${s}:dense`] / cost[`${s}:sparse`];
  const fmt = s => `sparse ${cost[`${s}:sparse`].toFixed(3)}ms -> dense ${cost[`${s}:dense`].toFixed(3)}ms = ${ratio(s).toFixed(2)}x`;

  findings.push({
    ok: ratio(baseState) >= GROWTH_MIN,
    text: `[control] BASE cost GROWS with the retained window (need >= ${GROWTH_MIN}x): ${fmt(baseState)}` +
          (ratio(baseState) >= GROWTH_MIN ? '' : ' — FIXTURE TOO SMALL, the candidate arm below proves nothing'),
  });
  findings.push({
    ok: ratio(candState) <= FLAT_MAX,
    text: `[discriminates] CANDIDATE cost stays FLAT (need <= ${FLAT_MAX}x): ${fmt(candState)}`,
  });
  findings.push({
    ok: true,
    text: `[context] dense-window cost, BASE ${cost[`${baseState}:dense`].toFixed(3)}ms vs CANDIDATE ` +
          `${cost[`${candState}:dense`].toFixed(3)}ms = ${(cost[`${baseState}:dense`] / cost[`${candState}:dense`]).toFixed(2)}x — ` +
          `reported, NOT asserted: a fixed multiple here measured stuck-red on the correct build`,
  });

  report('cache-shape (bf/cache #8740, BF-06/07)', findings);
})().catch(e => { console.error('cache probe failed:', e.message); process.exit(2); });
