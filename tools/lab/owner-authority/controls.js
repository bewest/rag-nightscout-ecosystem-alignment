'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const source = fs.readFileSync(path.join(__dirname, 'local-token.js'), 'utf8');
const controls = [
  ['signature', '!verify(null, Buffer.from(parts[0] + \'.\' + parts[1]), key.publicKey, signature)',
    'false', 'tampered signature refuses before PostgreSQL'],
  ['audience', 'claims.aud !== audience || ', '', 'signed wrong issuer/audience/purpose/tenant and invalid times refuse'],
  ['session', '!state.sessionActive || ', '', 'individual session revocation refuses across pools'],
  ['stale-authority', 'const state = await snapshot(claims);',
    'const state = cached || (cached = await snapshot(claims));',
    'same earlier tokens lose grants on the next operation across both pools']
];
const results = [];
for (const [name, before, after, symptom] of controls) {
  const scratch = fs.mkdtempSync(path.join(os.tmpdir(), 'ns-owner-control-'));
  try {
    assert.equal(source.split(before).length, 2, 'control anchor must occur exactly once');
    let mutant = source.replace(before, after);
    if (name === 'stale-authority') mutant = mutant.replace('return async function authorize', 'let cached;\n  return async function authorize');
    const modulePath = path.join(scratch, 'local-token.js');
    fs.writeFileSync(modulePath, mutant);
    const run = spawnSync(process.execPath, [path.join(__dirname, 'harness.js')], {
      env: { ...process.env, OWNER_AUTH_MODULE: modulePath, OWNER_AUTH_CONTROL: name, OWNER_AUTH_OUT: '' },
      encoding: 'utf8', timeout: 120000, maxBuffer: 1024 * 1024
    });
    assert.equal(run.status, 1, 'mutated implementation must fail');
    assert.ok(run.stderr.includes('CHECK_FAILED: ' + symptom + ' [ERR_ASSERTION]'),
      'control must fail the intended assertion, not setup: ' + run.stderr);
    results.push({ control: name, nonVacuous: true, symptom });
    console.log(JSON.stringify(results[results.length - 1]));
  } finally { fs.rmSync(scratch, { recursive: true, force: true }); }
}
if (process.env.OWNER_AUTH_CONTROLS_OUT) fs.writeFileSync(process.env.OWNER_AUTH_CONTROLS_OUT, JSON.stringify(results, null, 2) + '\n');
