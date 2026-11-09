'use strict';
// Reads a recorded summary.json written by the disposable owner/OIDC native
// harness (cgm-remote-monitor tests/native/oidc-matrix/run.sh). No services,
// no fresh execution: this gate measures that the record is complete.
//   node tools/queue/gates/oidc-native-recorded.js [path/to/summary.json]
// Exits non-zero unless sourceCommit is a 40-hex sha, every one of the nine
// stage ids is present exactly once with verdict PASS and every family of that
// stage recorded true, and at least two mutant controls went red then green.
const fs = require('node:fs'), path = require('node:path'), { REPO_ROOT, report } = require('./_gate');
const STAGES = {
  'vault-single': ['vaultSingle'], 'vault-multi': ['vaultMulti'], 'mongo-sessions': ['mongoNativeSessions'], 'pg-sessions': ['postgresNativeSessions'],
  'mongo-http': ['mongoSignedHttps', 'singleBrowserLifecycle', 'defaultOffSingle', 'singleLegacyCompatibility'],
  'owner-consumer': ['ownerCreateRoleIssueRevoke', 'settingsVersionHistoryRollback', 'httpPresentation', 'evaluatorCycle', 'clinicalImmutability', 'tenantBImmutability', 'dataCredentialReplay', 'pinnedClientReplay', 'dataRevocation', 'foreignTenantRefusal'],
  'owner-authority': ['shiroGrammar', 'projectContainment', 'operatorContainment', 'delegationContainment', 'actorRevocation', 'policyWaiter', 'actorWaiter', 'roleWaiter', 'heldThroughCommit', 'auditRefusal', 'commitRefusal'],
  'owner-browser': ['ownerCookieMutations', 'ownerBearerParity', 'ownerCsrfOrigin', 'ownerSensitiveFreshness', 'ownerCurrentAuthority', 'ownerSessionLogout', 'ownerBrowserMutations', 'ownerBrowserTabsBackReload', 'ownerBrowserBearerParity', 'ownerBrowserLogout'],
  'owner-compatibility': ['defaultOffMulti', 'legacyApiSecret', 'legacySubject', 'legacyEightHourExchange', 'anonymousReadClamp', 'planeSeparation']
};
const file = process.argv[2] ? path.resolve(process.argv[2]) : path.join(REPO_ROOT, 'reports/tenancy/oidc-native-2026-11-09/summary.json');
const findings = [];
try {
  const summary = JSON.parse(fs.readFileSync(file, 'utf8'));
  findings.push({ ok: /^[0-9a-f]{40}$/.test(summary.sourceCommit || ''), text: 'sourceCommit is a 40-hex sha: ' + (summary.sourceCommit || '(missing)') });
  const stages = Array.isArray(summary.stages) ? summary.stages : [];
  for (const [id, families] of Object.entries(STAGES)) {
    const rows = stages.filter(stage => stage && stage.id === id);
    const row = rows[0];
    const ok = rows.length === 1 && row.verdict === 'PASS' && row.families && families.every(name => row.families[name] === true) && Number.isFinite(row.durationMs);
    findings.push({ ok, text: id + ': ' + (rows.length !== 1 ? rows.length + ' records' : row.verdict + ' ' + row.durationMs + 'ms, families ' +
      families.filter(name => row.families?.[name] === true).length + '/' + families.length) });
  }
  const extra = stages.filter(stage => !STAGES[stage?.id]).map(stage => stage?.id);
  findings.push({ ok: extra.length === 0, text: 'no unknown stage ids' + (extra.length ? ': ' + extra.join(',') : '') });
  const controls = Array.isArray(summary.controls) ? summary.controls : [];
  const good = controls.filter(control => control && control.red?.verdict === 'FAIL' && control.restored?.verdict === 'PASS' && /^[0-9a-f]{64}$/.test(control.mutantSha256 || ''));
  findings.push({ ok: good.length >= 2, text: 'mutant controls red-then-green: ' + good.length + ' of ' + controls.length + (good.length ? ' (' + good.map(control => control.group + ':' + control.id).join(', ') + ')' : '') });
  const images = summary.images || {};
  findings.push({ ok: ['postgres', 'mongo', 'vault'].every(name => Array.isArray(images[name]?.repoDigests) && images[name].repoDigests.some(ref => /@sha256:[0-9a-f]{64}$/.test(ref))),
    text: 'postgres, mongo and vault images recorded by digest' });
} catch (error) { findings.push({ ok: false, text: 'cannot read summary: ' + error.message }); }
report('oidc-native RECORDED-EVIDENCE (no fresh native execution): ' + path.relative(REPO_ROOT, file), findings);
