'use strict';
// D22's merge and the application-level floors, as the hosted processes would
// run them. The database holds the write-time checks (migrations 0002-0006);
// this module holds what only code can know: the code defaults, the process
// environment, and the merged (effective) set.
//
// effective = code default -> operator default -> owner value (if the mode
//             allows it and the constraint accepts it) -> operator pin
//
// `brk` holds CONTROL breaks used by the harness to show a test can go red.

const MMOL_TO_MGDL = 18.01559; // dev lib/constants.json:10

// Code defaults, from dev (lib/settings.js:9-45, lib/server/env.js:121-132).
const CODE_DEFAULTS = {
  SHOW_SECONDS: false,
  DISPLAY_UNITS: 'mg/dl',
  AUTH_DEFAULT_ROLES: ['readable'],
  WRITE_VALIDATION: 'off',
  API3_AUTOPRUNE_DEVICESTATUS: null,
  API3_AUTOPRUNE_ENTRIES: null,
  API3_AUTOPRUNE_FOOD: null,
  API3_AUTOPRUNE_PROFILE: null,
  API3_AUTOPRUNE_SETTINGS: null,
  API3_AUTOPRUNE_TREATMENTS: null,
  BG_HIGH: 260,
  BG_TARGET_TOP: 180,
  BG_TARGET_BOTTOM: 80,
  BG_LOW: 55,
  ALARM_URGENT_HIGH: true,
  ALARM_HIGH: true,
  ALARM_LOW: true,
  ALARM_URGENT_LOW: true,
  API_V3_DATA_WARNINGS: false
};
function codeDefault (key) {
  if (key.startsWith('INTEGRATION_MAX:')) return 0;
  if (key.startsWith('INTEGRATION_HOSTS:')) return null;
  return Object.prototype.hasOwnProperty.call(CODE_DEFAULTS, key) ? CODE_DEFAULTS[key] : null;
}

// ---- the value grammar; must agree with cfg_value_ok / cfg_satisfies (SQL) --

function valueOk (s, v, brk = {}) {
  if (v === null || v === undefined) return false;
  switch (s.value_type) {
    case 'boolean': return typeof v === 'boolean';
    case 'integer': return typeof v === 'number' && Number.isInteger(v);
    case 'enum':
    case 'ordinal': return typeof v === 'string' && s.enum_values.includes(v);
    case 'role_list':
      return Array.isArray(v) && v.length > 0 && v.every((r) => typeof r === 'string' && s.enum_values.includes(r)) &&
        new Set(v).size === v.length;
    case 'host_list':
      return Array.isArray(v) && v.every((h) => typeof h === 'string' &&
        /^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$/.test(h));
    default: return false;
  }
}

function satisfies (s, c, v, brk = {}) {
  if (!c || Object.keys(c).length === 0) return true;
  const pos = (x) => s.enum_values.indexOf(x);
  if ('allowed' in c) {
    if (s.value_type === 'role_list' || s.value_type === 'host_list') {
      if (!v.every((x) => c.allowed.includes(x))) return false;
    } else if (s.value_type === 'enum' || s.value_type === 'ordinal') {
      if (!c.allowed.includes(v)) return false;
    } else return false;
  }
  if ('min' in c) {
    if (s.value_type === 'integer') { if (v < c.min) return false; } else if (s.value_type === 'ordinal') {
      // CONTROL brk.ordinalOffByOne: the kind of drift a second spelling invites
      if (brk.ordinalOffByOne ? pos(v) < pos(c.min) - 1 : pos(v) < pos(c.min)) return false;
    } else return false;
  }
  if ('max' in c) {
    if (s.value_type === 'integer') { if (v > c.max) return false; } else if (s.value_type === 'ordinal') {
      if (pos(v) > pos(c.max)) return false;
    } else return false;
  }
  return true;
}

function accepts (s, c, v, brk) { return valueOk(s, v, brk) && satisfies(s, c, v, brk); }

// ---- the merge ---------------------------------------------------------------

function policyFor (cfg, key) {
  const o = cfg.overrides[key];
  if (o) return { ...o, source: 'override' };
  const d = cfg.deployment[key];
  if (d) return { ...d, source: 'deployment' };
  const s = cfg.catalogue[key];
  return { mode: s.default_mode, default_value: null, constraint_spec: s.default_constraint, pin_value: null, source: 'catalogue' };
}

// cfg = { catalogue: {key: row}, deployment: {key: row}, overrides: {key: row},
//         owner: {key: value}, thresholds: row|null }
function effective (cfg, brk = {}) {
  const values = {};
  const ignoredOwnerValues = [];
  const floorViolations = [];
  for (const [key, s] of Object.entries(cfg.catalogue)) {
    const pol = brk.ignoreOverrides ? policyFor({ ...cfg, overrides: {} }, key) : policyFor(cfg, key);
    let value = codeDefault(key);
    let source = 'code';
    if (pol.default_value !== null && pol.default_value !== undefined) { value = pol.default_value; source = 'operator-default'; }
    const applyPin = () => {
      if (pol.mode === 'pinned' && pol.pin_value !== null && pol.pin_value !== undefined) { value = pol.pin_value; source = 'operator-pin'; }
    };
    if (brk.pinBeforeOwner) applyPin();
    if (Object.prototype.hasOwnProperty.call(cfg.owner, key)) {
      const v = cfg.owner[key];
      let why = null;
      if (!s.owner_settable) why = 'not owner-settable';
      else if (!valueOk(s, v)) why = 'type';
      else if (!brk.skipFloors && !satisfies(s, s.floor, v)) why = 'floor';
      else if (pol.mode === 'pinned' && !brk.pinBeforeOwner) why = 'pinned';
      else if (pol.mode === 'bounded' && !satisfies(s, pol.constraint_spec, v)) why = 'outside constraint';
      if (why) ignoredOwnerValues.push({ key, value: v, why, policy: pol.source });
      else { value = v; source = 'owner'; }
    }
    if (!brk.pinBeforeOwner) applyPin();
    values[key] = { value, source };
    if (!brk.skipFloors && value !== null && value !== undefined && !satisfies(s, s.floor, value)) {
      floorViolations.push({ key, value, source });
    }
  }
  // Alarm thresholds: the owner's row if present (all four, mg/dL), else per key.
  const th = cfg.thresholds;
  const t = th
    ? { bgLow: th.bg_low_mgdl, bgTargetBottom: th.bg_target_bottom_mgdl, bgTargetTop: th.bg_target_top_mgdl, bgHigh: th.bg_high_mgdl, source: 'owner' }
    : { bgLow: values.BG_LOW.value, bgTargetBottom: values.BG_TARGET_BOTTOM.value, bgTargetTop: values.BG_TARGET_TOP.value, bgHigh: values.BG_HIGH.value, source: 'policy' };
  // Refuse, never rewrite (contrast dev's verifyThresholds, BF-67).
  if (!brk.skipThresholdOrder && !(t.bgLow < t.bgTargetBottom && t.bgTargetBottom < t.bgTargetTop && t.bgTargetTop < t.bgHigh)) {
    floorViolations.push({ key: 'thresholds', value: t, source: t.source, why: 'not in order low < bottom < top < high' });
  }
  return { values, thresholds: t, ignoredOwnerValues, floorViolations };
}

// ---- process-level floors (multi only); the database cannot see the env ----

const FALSY = /^(false|off|0|no)$/i;
const TRUTHY = /^(true|on|1|yes)$/i;
const CIDR4 = /^\d{1,3}(\.\d{1,3}){3}\/\d{1,2}$/;
const CIDR6 = /^[0-9a-f:]+\/\d{1,3}$/i;

function processFloors (env, brk = {}) {
  const refuse = [];
  const warn = [];
  const set = (k) => env[k] !== undefined && env[k] !== '';
  if (!brk.noSecretCheck) {
    for (const k of ['API_SECRET', 'API_SECRET_FILE']) if (set(k)) refuse.push(`${k} is set: no deployment-wide secret under multi (D13)`);
  }
  if (!brk.noApi3SecurityCheck && set('API3_SECURITY_ENABLE') && FALSY.test(env.API3_SECURITY_ENABLE)) {
    refuse.push('API3_SECURITY_ENABLE is false: API v3 without a token is refused under multi');
  }
  if (!brk.noTrustProxyCheck) {
    const tp = env.TRUST_PROXY || '';
    const ok = /^\d+$/.test(tp) || (tp !== '' && tp.split(',').map((x) => x.trim()).every((x) => CIDR4.test(x) || CIDR6.test(x)));
    if (!ok) refuse.push('TRUST_PROXY must be a hop count or CIDR list under multi');
  }
  if (!brk.noDebugLoggingCheck && set('DEBUG_LOGGING') && TRUTHY.test(env.DEBUG_LOGGING)) {
    refuse.push('DEBUG_LOGGING writes record payloads to the log; refused under multi');
  }
  if (set('IMPORT_CONFIG')) warn.push('IMPORT_CONFIG is ignored under multi');
  return { refuse, warn };
}

// Floor "app settings stay private": reading an app's settings record by
// identifier needs api:settings:admin, whatever API3_SETTINGS_STRICT_READ_ENABLED says.
function settingsReadByIdPermission (env, mode, brk = {}) {
  if (mode === 'multi' && !brk.honourStrictReadEnv) return 'api:settings:admin';
  const strict = env.API3_SETTINGS_STRICT_READ_ENABLED !== undefined && TRUTHY.test(env.API3_SETTINGS_STRICT_READ_ENABLED);
  return strict ? 'api:settings:admin' : 'api:settings:read';
}

// Write boundary for thresholds: convert mmol/L to mg/dL and return what will
// be stored, for the owner to see (A.3 defence 2).
function thresholdsForStorage (input, units, brk = {}) {
  const keys = ['bgLow', 'bgTargetBottom', 'bgTargetTop', 'bgHigh'];
  const out = { enteredUnits: units };
  for (const k of keys) {
    if (typeof input[k] !== 'number') throw new Error(`thresholds: ${k} is missing; all four are written together`);
    out[k] = units === 'mmol' && !brk.skipConversion ? Math.round(input[k] * MMOL_TO_MGDL) : input[k];
  }
  return out;
}

module.exports = {
  CODE_DEFAULTS, codeDefault, valueOk, satisfies, accepts, policyFor, effective,
  processFloors, settingsReadByIdPermission, thresholdsForStorage, MMOL_TO_MGDL
};
