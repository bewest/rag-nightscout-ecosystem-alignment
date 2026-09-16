'use strict';
/*
 * version-collision.js  — RT-VERSION
 *
 * GT4's sharpest finding as a measurement: origin/dev and all five
 * modernization cut tips carry "version": "15.0.9" in package.json, while dev
 * declares engines.node ">=20.x" and every cut declares "^22.23.2 || ^24.20.0".
 *
 * Two artefacts that will not run on the same Node, claiming the same version
 * string. One of them also deletes two CGM ingestion paths. Given that all 100
 * child PRs in this stack were self-merged with zero human reviews, the version
 * number is the only warning an operator gets before installing, and right now
 * it does not distinguish them. "My 15.0.9 won't start" cannot be triaged.
 *
 * FAILS while any two refs share a version string but disagree on engines.node.
 */

const { show, report } = require('./_gate');

const REFS = [
  'origin/dev',
  'origin/chore/retire-jsdom',
  'origin/chore/build-runtime-separation',
  'origin/chore/compose-mongodb6',
  'origin/chore/mime-exposure-review',
  'origin/chore/nightscout-modernization',
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
