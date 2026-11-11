'use strict';
// Reproduction of BF-232 on the unchanged preview head. Synthetic data only.
const W = process.env.CRM;
const assert = require('node:assert/strict');
const scope = require(W + '/lib/storage/tenant-scope');
const evaluator = require(W + '/lib/data/tenant-projection-evaluator');
const environment = require(W + '/lib/server/tenant-app/environment');
const evaluatorConfig = require(W + '/lib/server/serve/evaluator-config');
const A = '11111111-1111-4111-8111-111111111111';
const source = { EVAL_PG: 'postgres://synthetic:synthetic@127.0.0.1/disposable_test' };
function doc (ext) { return { version: 1, postgres: { connectionEnv: 'EVAL_PG',
  namespaces: Object.fromEntries(['entries', 'treatments', 'devicestatus', 'profile', 'food', 'activity', 'clock', 'checkpoint'].map(k => [k, 'eval_' + k])) },
consumer: 'evaluator-proof', pageSize: 1, maxRows: 10, maxBytes: 100000, maxTenants: 2,
recoveryIntervalMs: 100, timeIntervalMs: 200, tenants: [{ id: A, revision: 'r1', settings: {}, ...(ext ? { extendedSettings: ext } : {}) }] }; }
async function run (env, at) {
  const document = { _id: 'synthetic-stale', type: 'sgv', sgv: 120, date: at - 40 * 60000, utcOffset: 0, srvModified: at - 40 * 60000 };
  const connection = { async query (text, values) { return { rows: JSON.parse(values.at(-1)).map(r => ({ ...r, unsortable: false })) }; } };
  const replay = { async reconcile () { return { checkpoint: 1, rows: [{ domain: 'entries', document }] }; } };
  const v = evaluator({ tenant: A, replay, connection, env, language: require(W + '/lib/language')(),
    dbstats: async () => ({ dataSize: 0, indexSize: 0 }), maxRows: 10, maxBytes: 100000 });
  return scope.withTenant(A, () => v.evaluate({ at }));
}
describe('BF-232 reproduction on the base head', function () {
  let mode; beforeEach(() => { mode = scope.getTenancyMode(); scope.setTenancyMode('multi'); });
  afterEach(() => scope.setTenancyMode(mode));
  it('operator evaluator config with timeago.enableAlerts', function () {
    let outcome;
    try { const t = evaluatorConfig.parse(doc({ timeago: { enableAlerts: true } }), source).tenants.get(A); outcome = 'accepted ext=' + JSON.stringify(t.env.extendedSettings); }
    catch (e) { outcome = 'refused: ' + e.message; }
    console.log('    EVALUATOR_CONFIG', outcome);
  });
  it('preview serving config path (environment as built by preview-config.js:149)', async function () {
    const env = environment({ settings: {}, extendedSettings: { timeago: { enableAlerts: true } } });
    console.log('    TENANT_ENV extendedSettings', JSON.stringify(env.extendedSettings), 'enable has timeago', env.settings.enable.includes('timeago'));
    const at = Date.now();
    const r = await run(env, at);
    console.log('    EMITTED', JSON.stringify(r.emitted.map(n => ({ level: n.level, group: n.group, title: n.title }))));
    console.log('    TIMEAGO status', JSON.stringify(r.properties.timeago && r.properties.timeago.status));
  });
});
describe('BF-232 harness control', function () {
  let mode; beforeEach(() => { mode = scope.getTenancyMode(); scope.setTenancyMode('multi'); });
  afterEach(() => scope.setTenancyMode(mode));
  it('the same evaluator fires when the setting is forced into the environment', async function () {
    const env = environment({ settings: {} });
    env.extendedSettings.timeago = { enableAlerts: true };
    const r = await run(env, Date.now());
    console.log('    CONTROL EMITTED', JSON.stringify(r.emitted.map(n => ({ level: n.level, group: n.group, title: n.title }))));
  });
});
