'use strict';
// This function is also embedded verbatim in the generated k6 workload. Only
// this fixed whitelist enters RAM; no complete status body is exported.
function projection(status) {
  const fail = () => { throw Error('M7_SETTINGS_INVALID'); };
  if (!status || status.status !== 'ok' || !status.settings || !status.extendedSettings) fail();
  const s = status.settings, result = {schema: 1, settings: {}, extendedSettings: {devicestatus: {}}};
  if (!['mg/dl','mmol'].includes(s.units)) fail();
  result.settings.units = s.units;
  if (!Array.isArray(s.enable) || s.enable.length > 128 || s.enable.some(v => typeof v !== 'string' || !/^[a-z][a-z0-9_-]{0,63}$/.test(v))) fail();
  result.settings.enable = s.enable.slice();
  for (const key of ['timeFormat','dayStart','dayEnd','alarmTimeagoWarnMins','alarmTimeagoUrgentMins','focusHours','heartbeat']) {
    if (typeof s[key] !== 'number' || !Number.isFinite(s[key])) fail();
    result.settings[key] = s[key];
  }
  for (const key of ['nightMode','showSeconds','editMode','alarmUrgentHigh','alarmHigh','alarmLow','alarmUrgentLow','alarmTimeagoWarn','alarmTimeagoUrgent','alarmPumpBatteryLow','showClockDelta','showClockLastTime','authenticationPromptOnLoad']) {
    if (typeof s[key] !== 'boolean') fail();
    result.settings[key] = s[key];
  }
  for (const key of ['alarmUrgentHighMins','alarmHighMins','alarmLowMins','alarmUrgentLowMins','alarmUrgentMins','alarmWarnMins']) {
    if (!Array.isArray(s[key]) || s[key].length > 64 || s[key].some(v => typeof v !== 'number' || !Number.isFinite(v))) fail();
    result.settings[key] = s[key].slice();
  }
  result.settings.thresholds = {};
  for (const key of ['bgHigh','bgTargetTop','bgTargetBottom','bgLow']) {
    const value = s.thresholds && s.thresholds[key];
    if (typeof value !== 'number' || !Number.isFinite(value)) fail();
    result.settings.thresholds[key] = value;
  }
  const ds = status.extendedSettings.devicestatus;
  if (!ds || typeof ds.advanced !== 'boolean' || ![1,2].includes(ds.days)) fail();
  result.extendedSettings.devicestatus = {advanced: ds.advanced, days: ds.days};
  const encoded = JSON.stringify(result);
  if (encoded.length > 16384) fail();
  return encoded;
}
const fs = require('node:fs'), path = require('node:path'), crypto = require('node:crypto'), cp = require('node:child_process');
const FILES = ['lib/api/status.js','lib/server/tenant-app/environment.js','lib/server/tenant-app/rest-context.js','lib/settings.js','lib/constants.json','lib/tenant-settings/catalogue.js','lib/tenant-registry/provision.js','lib/tenant-registry/rules.js','lib/tenant-registry/vault-keys.js'];
function sourceFiles(core, commit) {
  // The adopted shared REST context replaced the retired per-tenant module.
  // Keep the historical blob set for sources that still contain that module.
  const present = file => cp.spawnSync('git',['-C',core,'cat-file','-e',commit+':'+file],{stdio:'ignore'}).status === 0;
  if (present('lib/server/tenant-app/rest-context.js')) return FILES;
  if (!present('lib/server/tenant-app/shared-rest-context.js')) throw Error('M7_SETTINGS_SOURCE_LAYOUT_UNREVIEWED');
  return FILES.map(file => file === 'lib/server/tenant-app/rest-context.js' ? 'lib/server/tenant-app/shared-rest-context.js' : file);
}
// Structural diagnostics contain only a fixed classification, never seed values.
// The complete fingerprint below still binds source and provisioning semantics.
function validateSeed(primer, count) {
  const fail = classification => {
    const error = Error('M7_SETTINGS_SEED_INVALID');
    error.seedCode = 'M7_SETTINGS_SEED_' + classification;
    throw error;
  };
  let stat, seed;
  try { stat = fs.lstatSync(primer); } catch { fail('FILE_READ'); }
  if (!stat.isFile() || stat.isSymbolicLink()) fail('FILE_TYPE');
  if (stat.size > 4194304) fail('FILE_SIZE');
  let raw;
  try { raw = fs.readFileSync(primer, 'utf8'); } catch { fail('FILE_READ'); }
  try { seed = JSON.parse(raw); } catch { fail('JSON'); }
  if (!seed || typeof seed !== 'object' || Array.isArray(seed) || seed.version !== 1 || !Array.isArray(seed.seed)) fail('SHAPE');
  if (!Number.isInteger(count) || count < 1 || count > 10000 || seed.seed.length !== count) fail('COUNT');
  const ids = new Set();
  for (const row of seed.seed) {
    if (!row || typeof row !== 'object' || Array.isArray(row) || Object.keys(row).sort().join(',') !== 'hosts,id,issueRootSecret') fail('ROW_KEYS');
    if (typeof row.id !== 'string' || !/^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/.test(row.id)) fail('ID_FORMAT');
    if (ids.has(row.id)) fail('ID_DUPLICATE');
    if (row.issueRootSecret !== true) fail('ROOT_SECRET');
    if (!Array.isArray(row.hosts) || row.hosts.length !== 1 || typeof row.hosts[0] !== 'string' || row.hosts[0].length > 253) fail('HOSTS');
    ids.add(row.id);
  }
  return {schema: 1, tenants: count, status: 'STRUCTURE_VERIFIED'};
}
function expected(core, commit, primer, count) {
  const git = (...args) => cp.execFileSync('git',['-C',core,...args],{encoding:'utf8'}).trim();
  if (!/^[a-f0-9]{40}$/.test(commit) || git('rev-parse','HEAD') !== commit) throw Error('M7_SETTINGS_SOURCE_MISMATCH');
  const blobs = {};
  for (const file of sourceFiles(core, commit)) {
    const blob = git('rev-parse',commit+':'+file);
    if (git('hash-object',path.join(core,file)) !== blob) throw Error('M7_SETTINGS_SOURCE_DIRTY');
    blobs[file] = blob;
  }
  validateSeed(primer, count);
  // Refuse a changed provisioning mechanism until this instrument is reviewed.
  const provision = fs.readFileSync(path.join(core,'lib/tenant-registry/provision.js'),'utf8');
  if (!provision.includes('" (tenant_id, version, values) VALUES ($1, 1, \'{}\'::jsonb)"')) throw Error('M7_SETTINGS_BLANK_PROVISION_UNREVIEWED');
  const environment = require(path.join(core,'lib/server/tenant-app/environment.js'));
  const env = environment();
  const encoded = projection({status:'ok',settings:env.settings.filteredSettings(env.settings),extendedSettings:env.settings.filteredSettings(env.extendedSettings)});
  const purposes = require(path.join(core,'lib/tenant-registry/rules.js')).PURPOSES;
  if (!purposes || Object.keys(purposes).length !== 6) throw Error('M7_KEY_PURPOSE_SCHEMA_UNREVIEWED');
  return {schema:1,sha256:crypto.createHash('sha256').update(encoded).digest('hex'),sourceCommit:commit,sourceBlobs:blobs,
    seedProof:{version:1,tenants:count,blankTenantSettings:true,source:'primer/config.json + pinned provisioning implementation'},
    transit:{schema:1,purposes,keyCountObservation:'UNMEASURED'}};
}
module.exports = {projection,expected,validateSeed,FILES};
if (require.main === module) {
  try { console.log(JSON.stringify(expected(...process.argv.slice(2,5),Number(process.argv[5])))); }
  catch (error) {
    console.error(/^M7_[A-Z_]+$/.test(error.message)?error.message:'M7_SETTINGS_REFUSED');
    if (/^M7_SETTINGS_SEED_[A-Z_]+$/.test(error.seedCode || '')) console.error(error.seedCode);
    process.exitCode=1;
  }
}
