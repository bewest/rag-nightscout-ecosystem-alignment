'use strict';
/*
 * node-floor-consistency.js  — RT-1 (cut 1, chore/retire-jsdom)
 *
 * Release-readiness §5 calls cut 1 "trivially revertible: the engines field
 * plus a boot check." GT2 measured that as mechanically true and operationally
 * misleading, and this gate is that measurement standing up.
 *
 * Mechanically true: lib/server/runtime-policy.js DERIVES the accepted range
 * from package.json engines.node, so there is no second hard-coded version in
 * the enforcement path.
 *
 * Operationally misleading: six other files state the floor independently, and
 * a one-field revert leaves every one of them stale and contradicting the
 * thing that is actually enforced. An operator reads those files; process.exit
 * is what happens to them afterwards.
 *
 * Two independent facts are checked, because they fail for different reasons.
 */

const { show, report } = require('./_gate');

const CUT1 = 'origin/chore/retire-jsdom';
const findings = [];

const pkg = JSON.parse(show(CUT1, 'package.json'));
const engines = (pkg.engines || {}).node || '';
// e.g. "^22.23.2 || ^24.20.0" -> major versions [22, 24]
const majors = [...engines.matchAll(/(\d+)\.\d+\.\d+/g)].map((m) => Number(m[1]));
const uniqueMajors = [...new Set(majors)].sort((a, b) => a - b);

findings.push({
  ok: uniqueMajors.length > 0,
  text: `cut 1 engines.node = "${engines}" -> permitted majors ${uniqueMajors.join(', ')}`,
});

// 1. The enforcement path must not hard-code a version of its own. This is the
//    half of the claim that IS true, and it is worth a standing guard: if
//    someone ever inlines a literal here, "revert the engines field" silently
//    stops working.
const policy = show(CUT1, 'lib/server/runtime-policy.js') || '';
findings.push({
  ok: /engines/.test(policy) && !/['"]\^?2[0-9]\.\d+\.\d+['"]/.test(policy),
  text: 'runtime-policy.js derives its range from package.json engines and hard-codes '
      + 'no version of its own (this is what makes the field the single lever)',
});

// 2. Every file that also states a floor must agree with engines. These are the
//    ones a revert would leave behind.
const STATERS = [
  { file: '.nvmrc', extract: (t) => [...t.matchAll(/(\d+)/g)].map((m) => Number(m[1])) },
  { file: 'bin/setup.sh', extract: (t) => [...t.matchAll(/setup_(\d+)\.x/g)].map((m) => Number(m[1])) },
  { file: 'azuredeploy.json', extract: (t) => [...t.matchAll(/WEBSITE_NODE_DEFAULT_VERSION[\s\S]{0,200}?~(\d+)/g)].map((m) => Number(m[1])) },
  { file: 'README.md', extract: (t) => [...t.matchAll(/NODE_DEFAULT_VERSION=~(\d+)/g)].map((m) => Number(m[1])) },
  { file: 'Dockerfile', extract: (t) => [...t.matchAll(/^FROM\s+node:(\d+)/gm)].map((m) => Number(m[1])) },
  // Scoped to lines that mention Node. An unscoped semver regex over a
  // markdown file matches every dependency version in it, which produced a
  // false BAD the first time this gate was run.
  { file: 'docs/meta/architecture-overview.md',
    extract: (t) => t.split('\n')
      .filter((line) => /node/i.test(line))
      .flatMap((line) => [...line.matchAll(/\^?(\d+)\.\d+\.\d+/g)].map((m) => Number(m[1]))) },
];

for (const stater of STATERS) {
  const text = show(CUT1, stater.file);
  if (text === null) {
    findings.push({ ok: true, text: `${stater.file}: absent at this ref, states no floor` });
    continue;
  }
  const stated = [...new Set(stater.extract(text))];
  if (stated.length === 0) {
    findings.push({ ok: true, text: `${stater.file}: states no Node major` });
    continue;
  }
  const strays = stated.filter((v) => !uniqueMajors.includes(v));
  findings.push({
    ok: strays.length === 0,
    text: `${stater.file}: states Node major(s) ${stated.join(', ')}`
        + (strays.length ? ` -- ${strays.join(', ')} not permitted by engines` : ''),
  });
}

// GT2 separately flagged the Dockerfile as "a floating major tag against a
// patch floor": FROM node:22-alpine satisfies the MAJOR but says nothing about
// 22.23.2, so the published image can drift below the floor its own package.json
// enforces and exit(1) on boot. Checked apart from the major-level agreement
// above, because it fails for a different reason and has a different fix.
const dockerfile = show(CUT1, 'Dockerfile') || '';
const fromTag = (dockerfile.match(/^FROM\s+node:([\w.-]+)/m) || [])[1];
const floorFor = (major) => (engines.match(new RegExp(`\\^${major}\\.(\\d+)\\.(\\d+)`)) || []);
if (fromTag) {
  const major = Number(fromTag.split(/[.-]/)[0]);
  const pinnedToPatch = /^\d+\.\d+\.\d+/.test(fromTag);
  const floor = floorFor(major);
  findings.push({
    ok: pinnedToPatch,
    text: `Dockerfile FROM node:${fromTag} is a floating tag; engines requires `
        + `>=${major}.${floor[1] || '?'}.${floor[2] || '?'} within that major, so the `
        + `image can drift below the floor its own package.json enforces and exit(1) on boot`,
  });
}

report('node-floor-consistency (RT-1)', findings);
