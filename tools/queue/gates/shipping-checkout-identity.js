'use strict';
/*
 * shipping-checkout-identity.js  — DOC-LAYOUT
 *
 * Decision D12 says cgm-remote-monitor stays pristine and this repository holds
 * tooling, docs, evidence and QC. Every brief therefore names a "shipping
 * checkout" that must not be modified. GT1 measured that the named directory is
 * the wrong one, and it is wrong in the way that matters most: it is not empty
 * or missing, it is a PLAUSIBLE DECOY. `externals/cgm-remote-monitor` is a real
 * cgm-remote-monitor checkout with real history — from 2014, on a different
 * fork — so an agent that cd's into it, greps it and reports what it finds gets
 * confident, coherent, wrong answers, and nothing errors.
 *
 * This gate measures the identity of both directories rather than trusting any
 * document's claim about them. It is deliberately not a grep for a sentence,
 * because the sentence will be reworded and the fact will not.
 */

const fs = require('fs');
const path = require('path');
const { REPO_ROOT, git, report } = require('./_gate');

const DECOY = path.join(REPO_ROOT, 'externals', 'cgm-remote-monitor');
const REAL = path.join(REPO_ROOT, 'externals', 'cgm-remote-monitor-official');
const findings = [];

function identity(dir) {
  if (!fs.existsSync(dir)) return null;
  try {
    return {
      origin: git(['remote', 'get-url', 'origin'], dir),
      head: git(['log', '-1', '--format=%h %ad %s', '--date=short'], dir),
      worktrees: git(['worktree', 'list'], dir).split('\n').filter(Boolean).length,
      hasDev: (() => {
        try { git(['rev-parse', '--verify', 'origin/dev'], dir); return true; }
        catch (e) { return false; }
      })(),
    };
  } catch (e) {
    return null;
  }
}

const decoy = identity(DECOY);
const real = identity(REAL);

if (!real) {
  findings.push({ ok: false, text: `${REAL} is not a readable git checkout; nothing measured` });
  report('shipping-checkout-identity (DOC-LAYOUT)', findings);
}

findings.push({
  ok: /nightscout\/cgm-remote-monitor/.test(real.origin),
  text: `externals/cgm-remote-monitor-official origin = ${real.origin}`,
});
findings.push({
  ok: real.hasDev,
  text: `externals/cgm-remote-monitor-official has origin/dev and ${real.worktrees} worktree(s) `
      + '-- this is the checkout the programme\'s branches actually live in',
});

if (decoy) {
  // The decoy's existence is the finding. It is not an error that the directory
  // is there; it is an error that anything calls it the shipping checkout.
  findings.push({
    ok: false,
    text: `externals/cgm-remote-monitor EXISTS and is a decoy: origin = ${decoy.origin}, `
        + `HEAD = ${decoy.head}, ${decoy.worktrees} worktree(s), origin/dev `
        + `${decoy.hasDev ? 'present' : 'ABSENT'}. It holds none of this programme's work, `
        + 'and any document or brief naming it the pristine shipping checkout sends an '
        + 'agent somewhere that answers questions plausibly and wrongly.',
  });
} else {
  findings.push({ ok: true, text: 'externals/cgm-remote-monitor does not exist; no decoy to confuse a reader' });
}

report('shipping-checkout-identity (DOC-LAYOUT)', findings);
