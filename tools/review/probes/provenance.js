#!/usr/bin/env node
'use strict';
/*
 * provenance.js — BLOCKING pre-gate for every client-side probe.
 *
 * THE FAILURE THIS EXISTS TO PREVENT, measured 2026-09-17.
 *
 * All review states share one private node_modules, and webpack's production
 * output path is node_modules/.cache/_ns_cache/public/js/bundle.app.js — inside
 * it. So in production mode every state served the BYTE-IDENTICAL bundle
 * (md5 d765fe44541f), and that bundle contained none of bf/food's client code:
 * `hidesAfterUse` appeared 0 times on the branch's own instance. The FOOD
 * instance was serving dev's client while reporting itself as bf/food. Any
 * browser measurement taken then would have compared dev against dev and called
 * it a pass.
 *
 * NODE_ENV=development is the fix, not a preference: webpack-dev-middleware
 * compiles from the worktree's own source and serves from memory, so the
 * shared on-disk cache is never consulted. Measured after switching:
 * BASE 10970598 bytes / hidesAfterUse 0, FOOD 10978530 bytes / hidesAfterUse 2.
 *
 * HOW TOKENS ARE CHOSEN. Never hand-written. A token is admissible only if it
 * measures 0 on BASE and >=1 on the candidate; this gate asserts BOTH, so a
 * token that matches nothing FAILS rather than passing quietly. Dev bundles
 * wrap modules in eval("...") string literals, so every backslash in the source
 * appears doubled in the served bytes — each token is therefore tried in its
 * verbatim form AND its JS-string-escaped form, and a token that matches
 * neither is reported as unusable rather than as absent.
 */

const path = require('path');
const http = require('http');
const crypto = require('crypto');
const { report } = require(path.resolve(__dirname, '..', '..', 'queue', 'gates', '_gate.js'));

// unit -> a token that exists ONLY in that unit's client code.
const TOKENS = {
  'bf/food': ['hidesAfterUse', 'quickpick.selectable'],
  'bf/parms': ['Deliberately NOT decodeURIComponent', 'queryParms'],
  'bf/merge': ['mergeTreatmentUpdate'],
  '#8729': ['chartContainer'],
  'bf3/alarm-no-reading': ['latestMgdlForLog', 'updateChartAfterAlarm'],
  'bf3/quickpick-rebuild': ['rebuildQuickpickChooser'],
};

function get(url) {
  return new Promise((res, rej) => {
    const u = new URL(url);
    const r = http.request({ hostname: u.hostname, port: u.port, path: u.pathname, method: 'GET' },
      x => { const c = []; x.on('data', d => c.push(d)); x.on('end', () => res(Buffer.concat(c).toString())); });
    r.on('error', rej); r.setTimeout(180000, () => rej(new Error('bundle fetch timed out')));
    r.end();
  });
}

const countOf = (hay, needle) => hay.split(needle).length - 1;
// the eval-wrapped form: backslashes doubled, single quotes escaped
const escaped = s => s.replace(/\\/g, '\\\\').replace(/'/g, "\\'");

(async () => {
  const a = process.argv.slice(2);
  const g = k => { const i = a.indexOf(k); return i >= 0 ? a[i + 1] : null; };
  const baseUrl = g('--base'), candUrl = g('--candidate'), unit = g('--unit');
  if (!baseUrl || !candUrl || !unit) {
    console.error('need --base <url> --candidate <url> --unit <name>'); process.exit(2);
  }
  const tokens = TOKENS[unit];
  if (!tokens) { console.error(`no tokens registered for unit ${unit}`); process.exit(2); }

  const bundlePath = '/devbundle/js/bundle.app.js';
  const baseBundle = await get(baseUrl + bundlePath);
  const candBundle = await get(candUrl + bundlePath);
  const findings = [];

  const md5 = s => crypto.createHash('md5').update(s).digest('hex');
  findings.push({
    ok: md5(baseBundle) !== md5(candBundle),
    text: `bundles differ: BASE ${baseBundle.length}B ${md5(baseBundle).slice(0, 12)} vs CANDIDATE ${candBundle.length}B ${md5(candBundle).slice(0, 12)}`,
  });

  let usable = 0;
  for (const tok of tokens) {
    for (const [form, t] of [['verbatim', tok], ['eval-escaped', escaped(tok)]]) {
      const b = countOf(baseBundle, t), c = countOf(candBundle, t);
      if (b === 0 && c === 0) continue;             // this form matches nothing; try the other
      usable += 1;
      findings.push({
        ok: b === 0 && c > 0,
        text: `token ${JSON.stringify(tok)} [${form}]: BASE ${b}, CANDIDATE ${c} — ` +
              (b === 0 && c > 0 ? 'discriminates'
               : b > 0 && c > 0 ? 'present on BOTH, cannot attribute'
               : b > 0 && c === 0 ? 'INVERTED (present on BASE only)'
               : 'matches nothing'),
      });
    }
  }
  if (usable === 0) {
    findings.push({ ok: false, text: `NO USABLE TOKEN for ${unit} — every candidate token matched nothing in either bundle, in either form. The gate cannot vouch for what is being served.` });
  }
  report(`provenance (${unit}) — is the instance serving its own client code?`, findings);
})().catch(e => { console.error('provenance failed:', e.message); process.exit(2); });
