'use strict';
/*
 * version-collision.js  — RT-VERSION
 *
 * GT4's sharpest finding as a measurement: origin/dev and all five
 * modernization cut tips carry "version": "15.0.9" in package.json, while dev
 * declares engines.node ">=20.x" and every cut declares "^22.23.2 || ^24.20.0".
 *
 * Two artefacts that will not run on the same Node, claiming the same version
 * string. One of them also deletes two CGM ingestion paths. The version number
 * is the first thing an operator checks before installing, and right now it does
 * not distinguish them. "My 15.0.9 won't start" cannot be triaged.
 *
 * FAILS while any two refs share a version string but disagree on engines.node.
 */

const { show, report } = require('./_gate');

// 2026-10-21: reads `official/*`, the remote the maintainer pushes to and this
// checkout fetches; `origin/*` here is an older fetch of the same repository
// (origin/dev was still 4bca2ac2 when dev was 04d435eb). official/master is
// included because the released version is the one an operator reports: a cut
// that still says 15.0.9 collides with the 15.0.9 release, not only with dev.
const REFS = [
  'official/master',
  'official/dev',
  'official/chore/retire-jsdom',
  'official/chore/build-runtime-separation',
  'official/chore/compose-mongodb6',
  'official/chore/mime-exposure-review',
  'official/chore/nightscout-modernization',
];

const seen = [];
for (const ref of REFS) {
  const raw = show(ref, 'package.json');
  if (raw === null) continue;
  const pkg = JSON.parse(raw);
  seen.push({ ref, version: pkg.version, engines: (pkg.engines || {}).node });
}

const findings = [];
const byVersion = new Map();
for (const entry of seen) {
  if (!byVersion.has(entry.version)) byVersion.set(entry.version, []);
  byVersion.get(entry.version).push(entry);
}

for (const [version, group] of byVersion) {
  const floors = new Set(group.map((g) => g.engines));
  if (group.length === 1) {
    findings.push({ ok: true, text: `version ${version}: only ${group[0].ref}` });
    continue;
  }
  if (floors.size === 1) {
    findings.push({
      ok: true,
      text: `version ${version}: ${group.length} refs, all engines.node=${[...floors][0]}`,
    });
  } else {
    findings.push({
      ok: false,
      text: `version ${version} is claimed by ${group.length} refs with ${floors.size} `
          + `different Node floors -> ${group.map((g) => `${g.ref}(${g.engines})`).join(', ')}`,
    });
  }
}

report('version-collision (RT-VERSION)', findings);
