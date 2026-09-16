'use strict';
/*
 * doc-branch-count.js  — DOC-SEQUENCING
 *
 * phase0-pr-sequencing-2026-09-15.md states the size of the Phase 0 branch set
 * more than once, and the statements disagree. GT1 and GT3 both found it
 * independently, which is itself the point: two agents read two different
 * sections and each came away with a different number, because rule 6 says
 * agents read SECTIONS, not documents. Whichever section they land in becomes
 * true for them, and a sequencing document is exactly the kind that gets read
 * one section at a time by whoever is about to push.
 *
 * The measured truth (GT1, by `git worktree list` and `git log`): nine
 * cgm-remote-monitor `bf/*` branches lettered A-I, PLUS the unlettered
 * `bf/connect-pin`, PLUS nightscout-connect's `fix/connect-timer-jitter`.
 *
 * FAILS while the document states more than one count in prose.
 */

const fs = require('fs');
const path = require('path');
const { REPO_ROOT, report } = require('./_gate');

const DOC = path.join(REPO_ROOT, 'docs', '30-design', 'remedial', 'phase0-pr-sequencing-2026-09-15.md');
const WORDS = {
  four: 4, five: 5, six: 6, seven: 7, eight: 8, nine: 9, ten: 10, eleven: 11,
};

const lines = fs.readFileSync(DOC, 'utf8').split('\n');
const claims = [];

lines.forEach((line, index) => {
  // "five branches", "the seven Phase 0 branches", "all six other branches",
  // "nine branches deep", "all seven" where branches is the nearby subject.
  const re = /\b(four|five|six|seven|eight|nine|ten|eleven)\b(?:[^.\n]{0,40}?)\bbranch(?:es)?\b/gi;
  for (const match of line.matchAll(re)) {
    claims.push({ n: WORDS[match[1].toLowerCase()], line: index + 1,
                  text: match[0].replace(/\s+/g, ' ').slice(0, 70) });
  }
});

const findings = [];

if (claims.length === 0) {
  // Positive-control failure: the document is supposed to talk about how many
  // branches there are. Finding no statement at all means the pattern stopped
  // matching, not that the document became consistent.
  findings.push({
    ok: false,
    text: 'no branch-count statement matched at all; this gate has stopped reading '
        + 'the document rather than the document having become consistent',
  });
  report('doc-branch-count (DOC-SEQUENCING)', findings);
}

const distinct = [...new Set(claims.map((c) => c.n))].sort((a, b) => a - b);
for (const claim of claims) {
  findings.push({
    ok: distinct.length === 1,
    text: `L${claim.line}: "${claim.text}" -> ${claim.n}`,
  });
}
findings.push({
  ok: distinct.length === 1,
  text: `the document states ${distinct.length} distinct branch counts (${distinct.join(', ')}); `
      + 'measured truth is nine bf/* branches plus bf/connect-pin plus the connect branch',
});

report('doc-branch-count (DOC-SEQUENCING)', findings);
