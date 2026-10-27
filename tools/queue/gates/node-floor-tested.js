'use strict';
/*
 * node-floor-tested.js  — RT-NODE-FLOOR-TESTED (BF-59)
 *
 * The lowest Node the server agrees to start on must be a Node some CI test job
 * runs. node-floor-consistency.js checks that every file STATING a floor agrees
 * with engines, and that the Docker base cannot drift below it (BF-58); it does
 * not look at the test matrix, so it passed on a cut tip whose matrix had
 * dropped the exact floor versions. This gate is that missing half.
 *
 * The floor is asked of semver (minVersion of engines.node), not scraped, for
 * the reason node-floor-consistency.js gives. The workflow is read as text: the
 * version must appear quoted on a `node-version` line, which is how every
 * matrix in .github/workflows/main.yml has spelt it since cut 1.
 *
 * Policy (maintainer, 2026-10-22/25): test the floor and the ceiling only, so
 * the newest Node is checked too, as a major on the same lines.
 */

const { show, report } = require('./_gate');
const semver = require('semver');

const REF = process.env.NODE_FLOOR_REF || 'official/dev';
const findings = [];

const pkg = JSON.parse(show(REF, 'package.json') || '{}');
const engines = (pkg.engines || {}).node || '';
const floor = engines && semver.validRange(engines) ? semver.minVersion(engines) : null;
findings.push({
  ok: Boolean(floor),
  text: `${REF} engines.node = "${engines}" -> lowest permitted Node ${floor || 'UNKNOWN'}`,
});

const workflow = show(REF, '.github/workflows/main.yml') || '';
const nodeLines = workflow.split('\n').filter((line) => /node-version/.test(line));
const quoted = (v) => new RegExp(`['"]${v.replace(/\./g, '\\.')}['"]`);

if (floor) {
  const hit = nodeLines.find((line) => quoted(floor.version).test(line));
  findings.push({
    ok: Boolean(hit),
    text: hit
      ? `a node-version line names the floor ${floor.version}: ${hit.trim().slice(0, 120)}`
      : `no node-version line in .github/workflows/main.yml names the floor ${floor.version}; `
        + 'the oldest Node the server starts on is run by no test job (BF-59)',
  });

  // An open-ended range (>=26.12.1) permits every later major, so the newest
  // one cannot be asked of semver offline; the newest major the range NAMES is
  // the one the maintainers have said they support.
  const ceiling = Math.max(...[...engines.matchAll(/(\d+)\.[\dx]+(?:\.[\dx]+)?/g)].map((m) => Number(m[1])));
  const ceilingHit = nodeLines.find((line) => new RegExp(`['"]${ceiling}(\\.\\d+\\.\\d+)?['"]`).test(line));
  findings.push({
    ok: Boolean(ceilingHit),
    text: ceilingHit
      ? `a node-version line names the newest major engines names, ${ceiling}`
      : `no node-version line names Node ${ceiling}, the newest major engines names`,
  });
}

report('node-floor-tested (RT-NODE-FLOOR-TESTED)', findings);
