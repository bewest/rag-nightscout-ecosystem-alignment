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

// Overridable so the gate can measure a PREPARED branch before a human pushes it.
// Defaults to the published ref, so CI keeps measuring what operators would get.
const CUT1 = process.env.NODE_FLOOR_REF || 'origin/chore/retire-jsdom';
const findings = [];

const semver = require('semver');
const pkg = JSON.parse(show(CUT1, 'package.json'));
const engines = (pkg.engines || {}).node || '';

// ASK SEMVER, DO NOT PATTERN-MATCH THE RANGE. This used to scrape
// /(\d+)\.\d+\.\d+/ out of the string, which worked only for the
// patch-precision range it was written against: given "^22.12 || >=24" it found
// NO majors, called every downstream file a stray, and reported 6 failures on a
// correct manifest. A range is a predicate; the only reliable way to ask which
// majors it permits is to test versions against it.
function majorPermitted (major) {
  return semver.satisfies(`${major}.0.0`, engines) ||
         semver.satisfies(`${major}.99.99`, engines);
}
const uniqueMajors = [];
for (let major = 8; major <= 40; major += 1) if (majorPermitted(major)) uniqueMajors.push(major);
const openEnded = majorPermitted(40);

findings.push({
  ok: uniqueMajors.length > 0,
  text: `cut 1 engines.node = "${engines}" -> permitted majors `
      + (openEnded ? `${uniqueMajors[0]}+ (open-ended: ${uniqueMajors.slice(0, 4).join(', ')}, ...)`
                   : uniqueMajors.join(', ')),
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
  const strays = stated.filter((v) => !majorPermitted(v));
  findings.push({
    ok: strays.length === 0,
    text: `${stater.file}: states Node major(s) ${stated.join(', ')}`
        + (strays.length ? ` -- ${strays.join(', ')} not permitted by engines` : ''),
  });
}

// THE DOCKERFILE / FLOOR COMPATIBILITY CHECK, REWRITTEN 2026-09-21.
//
// This used to assert the Dockerfile was pinned to an exact PATCH, which encoded the old
// `^22.23.2 || ^24.20.0` floor instead of testing it. That floor was measured to be
// unjustified and was loosened to `^22.12 || >=24` on the maintainer's decision, and
// docs/runtime-upgrade.md has always said the image should track "the official major tag".
// A floating major tag and a MINOR floor are compatible -- node:22-alpine only ever moves
// forward within 22.x, so it cannot fall below 22.12. A floating major tag and a PATCH
// floor are not: node:22-alpine is v22.22.0 and a container built from it exited 1 at boot
// against ^22.23.2, reproduced inside the image on 2026-09-21.
//
// So the property worth gating is the incompatibility itself, and it is checkable without
// a network call or a docker daemon: if the image tracks a major by floating tag, engines
// must not demand a patch level inside that major.
const dockerfile = show(CUT1, 'Dockerfile') || '';
const fromTag = (dockerfile.match(/^FROM\s+node:([\w.-]+)/m) || [])[1];
if (fromTag) {
  const major = Number(fromTag.split(/[.-]/)[0]);
  const floating = !/^\d+\.\d+/.test(fromTag);            // node:22-alpine, not node:22.12.0-alpine
  const patchFloor = new RegExp(`\\^${major}\\.\\d+\\.\\d+`).test(engines);
  findings.push({
    ok: !(floating && patchFloor),
    text: floating && patchFloor
      ? `Dockerfile FROM node:${fromTag} tracks major ${major} by FLOATING tag while engines `
        + `"${engines}" demands a patch level inside that major. Those cannot both hold: the `
        + `tag resolves to whatever the latest ${major}.x is, and if the floor is ahead of it `
        + `the image exits 1 at boot. Measured 2026-09-21 against the previous floor -- `
        + `node:22-alpine is v22.22.0 and refused ^22.23.2 inside the image. Either pin the `
        + `tag to a patch or state the floor at minor precision`
      : floating
        ? `Dockerfile FROM node:${fromTag} floats within major ${major} and engines `
          + `"${engines}" states no patch floor inside it -- compatible, and it is the `
          + `strategy docs/runtime-upgrade.md describes`
        : `Dockerfile FROM node:${fromTag} is pinned to a patch, so no drift is possible`,
  });
}

report('node-floor-consistency (RT-1)', findings);
