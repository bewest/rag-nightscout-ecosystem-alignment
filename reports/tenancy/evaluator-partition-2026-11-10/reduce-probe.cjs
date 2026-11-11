// Synthetic probe of the shipping notification producer reducer (lib/tenant-notifications/producer-state.js).
// Run: CRM_ROOT=<cgm-remote-monitor worktree> node reduce-probe.cjs 2>/dev/null | grep -v -E "EMITTING|level"
// Counts new non-clear alarm effects (each becomes a new dedup key, hence a new delivery request).
const root = process.env.CRM_ROOT;
const { reduce } = require(root + '/lib/tenant-notifications/producer-state');
const limits = { maxRows: 100, maxBytes: 1 << 20, maxPayloadBytes: 65536 };
const req = [{ kind: 'notify', level: 2, title: 'Urgent HIGH', message: 'synthetic', group: 'default', plugin: { name: 'simplealarms' }, eventName: 'high' }];
// Identical content in every arm. contentDigest is read by the producer from 2026-11-10 (option b);
// at 1792063a the field is ignored and the tuple carried runtimeId and outputRevision.
const contentDigest = require('node:crypto').createHash('sha256').update('synthetic-identical-content').digest('hex');
const cyc = (runtimeId, rev, now) => ({ identity: 'id1', runtimeId, outputRevision: rev, inputCheckpoint: 1, contentDigest, eligible: true, result: { now, requested: req } });
function run (label, seq) {
  let prev = null, revision = 0, emitted = 0; const log = [];
  for (const [rt, rev, at] of seq) {
    revision++;
    const before = new Set((prev?.effects || []).map(e => e.origin));
    const r = reduce({ previous: prev, cycle: cyc(rt, rev, at), acks: [], at, revision, repeatMs: 60000, ...limits });
    const fresh = r.state.effects.filter(e => !before.has(e.origin) && !e.payload.clear).length;
    emitted += fresh; log.push(rt + '@' + (at - 1e12) / 1000 + 's:+' + fresh);
    prev = r.state;
  }
  console.log(label, 'new alarm effects', emitted, log.join(' '));
}
const t = 1e12;
// one owner, same output revision polled every second for 10 s: repeat clock only
run('single owner, 10 polls', Array.from({ length: 10 }, (_, i) => ['A', 1, t + i * 1000]));
// two runtimes alternating on identical content, every second for 10 s
run('two owners alternating', Array.from({ length: 10 }, (_, i) => [i % 2 ? 'B' : 'A', 1, t + i * 1000]));
// handover: A for 3 s, then B only
run('handover A->B', Array.from({ length: 6 }, (_, i) => [i < 3 ? 'A' : 'B', 1, t + i * 1000]));
// control: the same alternation with one runtime id (A/A) is the single-owner result
run('control: alternating slots, one runtime id', Array.from({ length: 10 }, (_, i) => [i % 2 ? 'A' : 'A', 1, t + i * 1000]));
// two runtimes that happen to share an output revision number still differ by runtime id
run('two owners, revision numbers differ', Array.from({ length: 10 }, (_, i) => [i % 2 ? 'B' : 'A', i % 2 ? 7 : 1, t + i * 1000]));
