'use strict';
/*
 * nsprobe.js — the shared half of every live-instance review probe.
 *
 * A review probe is a queue gate that happens to need two RUNNING servers. It
 * reuses tools/queue/gates/_gate.js `report()` verbatim so `make queue-status`,
 * vacuity.py and emit_packets.py pick it up with no new machinery.
 *
 * THE META-GATE (plan §5). Every probe must record the measured BASE value AND
 * the measured CANDIDATE value, and must refuse to render a verdict when the
 * control has not been executed. Four of eleven criteria in the first draft of
 * the plan failed because their red state was reasoned about rather than run.
 * So `compare()` measures every arm against BOTH instances and classifies each
 * arm as 'discriminates' or 'invariant' (see below). An arm whose BASE result
 * contradicts its kind is reported as UNINFORMATIVE or UNATTRIBUTABLE — a
 * first-class outcome, not a pass. Such an arm measured nothing about the
 * branch, and shipping it would read as evidence.
 */

const http = require('http');
const crypto = require('crypto');
const path = require('path');
const fs = require('fs');

const { report } = require(path.resolve(__dirname, '..', '..', 'queue', 'gates', '_gate.js'));

function args() {
  const a = process.argv.slice(2);
  const get = (k, d) => { const i = a.indexOf(k); return i >= 0 ? a[i + 1] : d; };
  const o = {
    base: get('--base', process.env.NSREVIEW_BASE_URL),
    candidate: get('--candidate', process.env.NSREVIEW_CANDIDATE_URL),
    secret: get('--secret', process.env.NS_HARNESS_SECRET),
    manifest: get('--manifest', process.env.NSREVIEW_MANIFEST),
  };
  for (const k of ['base', 'candidate', 'secret']) {
    if (!o[k]) { console.error(`nsprobe: missing --${k}`); process.exit(2); }
  }
  o.sha1 = crypto.createHash('sha1').update(o.secret).digest('hex');
  if (o.manifest && fs.existsSync(o.manifest)) {
    o.expect = JSON.parse(fs.readFileSync(o.manifest, 'utf8')).expect || {};
  } else { o.expect = {}; }
  return o;
}

function fetch(base, p, sha1, opts) {
  const u = new URL(p, base);
  return new Promise((res, rej) => {
    const r = http.request({
      hostname: u.hostname, port: u.port, path: u.pathname + u.search,
      method: (opts && opts.method) || 'GET',
      headers: Object.assign({ 'api-secret': sha1 }, (opts && opts.headers) || {}),
    }, x => {
      let b = ''; x.on('data', c => b += c);
      x.on('end', () => res({ code: x.statusCode, body: b, json: safe(b) }));
    });
    r.on('error', rej);
    if (opts && opts.body) r.write(JSON.stringify(opts.body));
    r.end();
  });
}
function safe(b) { try { return JSON.parse(b); } catch { return null; } }

/*
 * compare(name, o, arms)
 *
 * arms: [{ what,
 *          kind: 'discriminates' | 'invariant',   // REQUIRED — see below
 *          measure(url, sha1, o) -> value,        // run against BOTH instances
 *          ok(v) -> bool,                         // the criterion
 *          describe(v) -> string }]
 *
 * TWO KINDS OF ARM, and conflating them is a mistake this helper made on its
 * first run. They have OPPOSITE expectations of BASE:
 *
 *   kind: 'discriminates'  — proves the fix WORKS. BASE must be RED. If BASE
 *       is green the arm measured nothing about the branch, and its pass on
 *       the candidate is not evidence: that is UNINFORMATIVE, and it fails.
 *
 *   kind: 'invariant'      — proves the fix BROKE NOTHING ELSE (an
 *       over-correction guard, an untouched-collection check). BASE must be
 *       GREEN; that is the whole point. A RED base here means the invariant
 *       was already violated before the branch, so the arm cannot attribute
 *       anything to it — which is its own kind of uninformative, and also
 *       fails, for the mirror-image reason.
 *
 * A probe with ONLY invariant arms proves nothing about its branch, so
 * compare() refuses to pass one.
 *
 * Findings per arm:
 *   CANDIDATE — the criterion on the branch. Fails the gate when false.
 *   CONTROL   — the same criterion on BASE. Informational, EXCEPT when it
 *               contradicts `kind`, which fails.
 */
async function compare(name, o, arms) {
  const findings = [];
  let nDiscriminating = 0;
  for (const arm of arms) {
    let bv, cv, berr = null, cerr = null;
    try { bv = await arm.measure(o.base, o.sha1, o); } catch (e) { berr = e.message; }
    try { cv = await arm.measure(o.candidate, o.sha1, o); } catch (e) { cerr = e.message; }

    if (berr || cerr) {
      findings.push({ ok: false, text: `${arm.what}: MEASUREMENT FAILED base=${berr || 'ok'} candidate=${cerr || 'ok'}` });
      continue;
    }

    const d = v => (arm.describe ? arm.describe(v) : JSON.stringify(v));
    const candidateGreen = arm.ok(cv);
    const baseGreen = arm.ok(bv);
    const kind = arm.kind || 'discriminates';
    if (kind === 'discriminates') nDiscriminating += 1;

    findings.push({ ok: candidateGreen, text: `[${kind}] ${arm.what}: CANDIDATE ${d(cv)}` });
    findings.push({ ok: true, text: `[${kind}] ${arm.what}: CONTROL   BASE ${d(bv)} — ${baseGreen ? 'GREEN' : 'RED'}` });

    if (kind === 'discriminates' && baseGreen) {
      findings.push({ ok: false, text: `[${kind}] ${arm.what}: UNINFORMATIVE — BASE already satisfies this criterion, so it measured nothing about the branch` });
    }
    if (kind === 'invariant' && !baseGreen) {
      findings.push({ ok: false, text: `[${kind}] ${arm.what}: UNATTRIBUTABLE — this invariant was ALREADY violated on BASE, so its state cannot be attributed to the branch` });
    }
  }
  if (nDiscriminating === 0) {
    findings.push({ ok: false, text: 'NO DISCRIMINATING ARM — this probe has only invariant guards and proves nothing about its branch' });
  }
  report(name, findings);
}

module.exports = { args, fetch, compare };
