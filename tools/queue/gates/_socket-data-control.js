'use strict';

const definition = {
  file: 'tests/tenant-socket-data-forwarding.integration.test.js',
  flag: 'NS_SOCKET_DATA_FORWARDING_TEST', passes: 4,
  controls: {
    earlyack: ['lib/server/tenant-socket-forwarding.js', 'const response = await transport(envelope);',
      "if (typeof acknowledge === 'function') acknowledge({ result: 'success' });\n      const response = await transport(envelope);",
      'does not publish a success acknowledgement or event before the owned API commit'],
    role: ['lib/server/tenant-socket-forwarding.js',
      'const actor = await authorizeSocket({ tenant, credential: envelope.credential, namespace, event, args });',
      'const actor = { tenant, permissions: { read: true, write: true, write_treatment: true } };',
      'refuses a substituted foreign role credential at current API subject authority without effects or callback']
  }
};
const adaptations = [
  ["const assert = require('node:assert/strict');", `const assert = require('node:assert/strict');
const gateProofs = [];
function gateRecord (proof) {
  gateProofs.push(proof);
  require('node:fs').writeFileSync(process.env.NS_SOCKET_GATE_PROOF, JSON.stringify(gateProofs));
}`],
  [`        const refused = new Promise(resolve => { refusalObserved = resolve; });
        forwarded.emit('dbAdd', pattern.addTreatment(), () => { acknowledged = true; });
        await refused;
        await new Promise(resolve => setImmediate(resolve));
        assert.equal(acknowledged, false, 'foreign role must not gain a client callback');
        assert.deepEqual(await rows(), before); assert.deepEqual(await rows(lab.B), expectedForeign);
        assert.equal(events.length, eventCount);`,
  `        const observation = await new Promise(resolve => {
          refusalObserved = () => resolve('refused');
          forwarded.emit('dbAdd', pattern.addTreatment(), () => { acknowledged = true; resolve('callback'); });
        });
        await new Promise(resolve => setImmediate(resolve));
        const current = await rows(), foreign = await rows(lab.B);
        gateRecord({ kind: 'role', observation, acknowledged, before, current, expectedForeign, foreign,
          eventCount, events: events.length });
        assert.deepEqual(foreign, expectedForeign, 'foreign tenant B stored state unchanged');
        assert.equal(current.length, before.length, 'socket role substitution changed committed tenant A row count');
        assert.deepEqual(current, before);
        assert.equal(events.length, eventCount);
        assert.equal(acknowledged, false, 'foreign role must not gain a client callback');`],
  [`      const pending = send(forwarded, 'dbAdd', pattern.addTreatment()).then(reply => { acknowledged = true; return reply; });`,
  `      let observedCallback;
      const callbackSeen = new Promise(resolve => { observedCallback = resolve; });
      const pending = send(forwarded, 'dbAdd', pattern.addTreatment()).then(reply => {
        acknowledged = true; observedCallback(); return reply;
      });`],
  [`        assert.equal(acknowledged, false, 'client acknowledgement preceded API commit');
        assert.deepEqual(await rows(), [], 'uncommitted write invisible to independent oracle');
        assert.equal(events.length, count, 'intent not emitted before commit');`,
  `        // Wait for an actual callback or a finite no-callback observation interval.
        // A timeout is never the red; the following physical and boolean assertions are.
        await Promise.race([callbackSeen, new Promise(resolve => setTimeout(resolve, 150))]);
        const current = await rows();
        assert.deepEqual(current, [], 'uncommitted write invisible to independent oracle');
        assert.equal(events.length, count, 'intent not emitted before commit');
        gateRecord({ kind: 'earlyack', postWrite, acknowledged, current, eventCount: count, events: events.length });
        assert.equal(acknowledged, false, 'socket success callback observed before API COMMIT with uncommitted stored row');`]
];
function adapt (source) {
  for (const [before, after] of adaptations) {
    if (source.split(before).length !== 2) throw new Error('CONTROL-INVALID: expected exactly one socket oracle boundary');
    source = source.replace(before, after);
  }
  return source;
}
function verify (report, status, control, proofs) {
  if (!control) {
    if (status !== 0 || report.stats.tests !== 4 || report.stats.passes !== 4 ||
        report.stats.failures !== 0 || report.stats.pending !== 0) throw new Error('Unexpected bounded socket cohort result');
    if (!Array.isArray(proofs) || proofs.length !== 2 || !proofs.some(p => p.kind === 'role' && p.observation === 'refused' &&
        p.acknowledged === false && p.current.length === 0 && p.foreign.length === 0) ||
        !proofs.some(p => p.kind === 'earlyack' && p.postWrite === true && p.acknowledged === false &&
          p.current.length === 0 && p.events === p.eventCount)) throw new Error('Missing restored socket physical observations');
    return;
  }
  const failure = report.failures[0], err = failure?.err;
  if (!Object.hasOwn(definition.controls, control) || status !== 1 || report.stats.tests !== 1 ||
      report.stats.failures !== 1 || report.stats.passes !== 0 || report.stats.pending !== 0 ||
      err?.code !== 'ERR_ASSERTION' || !failure.fullTitle?.endsWith(definition.controls[control][3])) {
    throw new Error('CONTROL-INVALID: socket setup/timeout/unrelated case is not semantic evidence');
  }
  if (!Array.isArray(proofs) || proofs.length !== 1) throw new Error('CONTROL-INVALID: socket physical observation missing');
  const proof = proofs[0], exact = (value, expected) => value === expected || value === String(expected);
  const valid = control === 'earlyack'
    ? proof.kind === control && proof.postWrite === true && proof.acknowledged === true &&
      Array.isArray(proof.current) && proof.current.length === 0 && proof.events === proof.eventCount &&
      exact(err.actual, true) && exact(err.expected, false) &&
      err.message?.includes('socket success callback observed before API COMMIT with uncommitted stored row')
    : proof.kind === control && proof.observation === 'callback' && proof.acknowledged === true &&
      Array.isArray(proof.before) && proof.before.length === 0 && Array.isArray(proof.current) && proof.current.length === 1 &&
      typeof proof.current[0]._id === 'string' && typeof proof.current[0].srvModified === 'number' &&
      Array.isArray(proof.foreign) && proof.foreign.length === 0 && proof.events === proof.eventCount + 1 &&
      exact(err.actual, 1) && exact(err.expected, 0) &&
      err.message?.includes('socket role substitution changed committed tenant A row count');
  if (!valid) throw new Error('CONTROL-INVALID: unexpected socket assertion/physical symptom');
  console.log('CONTROL-SEMANTIC: ' + (control === 'earlyack'
    ? 'actual callback before held COMMIT; transactional row reached, independent row/event absent'
    : 'foreign role produced committed tenant A row and event with callback; tenant B unchanged'));
}
function auditChild (output, present = pid => {
  try { process.kill(pid, 0); return true; } catch (error) { if (error.code === 'ESRCH') return false; throw error; }
}) {
  const starts = [...output.matchAll(/Single reference child started: (.+)/g)];
  const stops = [...output.matchAll(/Single reference child cleanup: (.+)/g)];
  if (starts.length !== 1 || stops.length !== 1) throw new Error('Socket reference child lifecycle audit missing/ambiguous');
  const start = JSON.parse(starts[0][1]), stop = JSON.parse(stops[0][1]);
  if (!Number.isSafeInteger(start.pid) || start.pid < 1 || start.mode !== 'single' || stop.pid !== start.pid ||
      stop.code !== 0 || stop.signal !== null || stop.absent !== true || present(start.pid)) {
    throw new Error('Socket reference child lifecycle audit failed');
  }
  return { pid: start.pid, mode: start.mode, exit: stop, independentlyAbsent: true };
}
module.exports = { definition, adapt, adaptations, verify, auditChild };
