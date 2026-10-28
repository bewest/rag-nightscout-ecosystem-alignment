'use strict';
// D22's merge and project floors over seven setting names from the census
// (docs/60-research/tenancy/t30-census-dev-2026-10-27.md §3).
//
// effective = code default -> operator default -> owner value (if the mode
// allows it and the constraint accepts it) -> operator pin.
// Floors are enforced in code; no operator policy can loosen them.

// Hosts a connector driver defines. Synthetic: .test is reserved (RFC 2606).
const DRIVER_HOSTS = ['share1.cgm-driver.test', 'share2.cgm-driver.test', 'share3.cgm-driver.test'];
const SAFE_DEFAULT_ROLES = ['denied', 'readable', 'status-only']; // D22 floor: no anonymous writes
const WV = { off: 0, log: 1, reject: 2 };

function hostOf (url) {
  try { return new URL(url).hostname; } catch (e) { return null; }
}
const roles = (v) => String(v).split(/[\s,]+/).filter(Boolean);

// Code defaults are dev's (lib/settings.js:40, lib/server/env.js:129) where
// they exist; the floors below reject two of them under multi.
const SETTINGS = {
  AUTH_DEFAULT_ROLES: {
    codeDefault: 'readable',
    type: (v) => typeof v === 'string' && roles(v).length > 0,
    floor: (v) => roles(v).every((r) => SAFE_DEFAULT_ROLES.includes(r)) ? null : 'floor: no anonymous writes',
    constraint: (v, c) => roles(v).every((r) => c.allowed.includes(r)),
    constraintFloor: (c) => c.allowed.every((r) => SAFE_DEFAULT_ROLES.includes(r)) ? null : 'floor: allowed list offers an anonymous write role'
  },
  WRITE_VALIDATION: {
    codeDefault: 'off',
    type: (v) => v in WV,
    floor: (v) => WV[v] >= WV.log ? null : 'floor: WRITE_VALIDATION at least log',
    constraint: (v, c) => WV[v] >= WV[c.min], // the owner may tighten, never loosen
    constraintFloor: (c) => WV[c.min] >= WV.log ? null : 'floor: minimum below log'
  },
  CONNECT_SOURCE_ENDPOINT: {
    codeDefault: null,
    type: (v) => typeof v === 'string' && hostOf(v) !== null,
    floor: (v) => DRIVER_HOSTS.includes(hostOf(v)) && new URL(v).protocol === 'https:' ? null : 'floor: connector endpoints only the hosts a driver defines',
    constraint: (v, c) => c.hosts.includes(hostOf(v)),
    constraintFloor: (c) => c.hosts.every((h) => DRIVER_HOSTS.includes(h)) ? null : 'floor: host list beyond the driver'
  },
  API3_AUTOPRUNE_ENTRIES: {
    codeDefault: null, // no pruning
    type: (v) => Number.isInteger(v) && v >= 1,
    floor: () => null, // the confirmation floor is procedural: see needsConfirmation
    constraint: (v, c) => v >= c.min && v <= c.max,
    constraintFloor: () => null,
    needsConfirmation: true
  },
  DISPLAY_UNITS: {
    codeDefault: 'mg/dl',
    type: (v) => v === 'mg/dl' || v === 'mmol',
    floor: () => null,
    constraint: () => true,
    constraintFloor: () => null
  },
  TRUST_PROXY: {
    codeDefault: '',
    type: (v) => typeof v === 'string',
    floor: (v) => /^\d+$/.test(v) || /^\d{1,3}(\.\d{1,3}){3}\/\d{1,2}$/.test(v) ? null : 'floor: TRUST_PROXY must be a hop count or CIDR',
    constraint: () => true,
    constraintFloor: () => null
  },
  DEBUG_LOGGING: {
    codeDefault: false,
    type: (v) => typeof v === 'boolean',
    floor: (v) => v === false ? null : 'floor: DEBUG_LOGGING off under multi',
    constraint: () => true,
    constraintFloor: () => null
  }
};

// The operator's template applied at provisioning. One pinned setting
// (TRUST_PROXY) plus DEBUG_LOGGING pinned to its floor.
function defaultPolicy () {
  return {
    AUTH_DEFAULT_ROLES: { default: 'denied', mode: 'bounded', constraint: { allowed: ['denied', 'readable'] } },
    WRITE_VALIDATION: { default: 'log', mode: 'bounded', constraint: { min: 'log' } },
    CONNECT_SOURCE_ENDPOINT: { default: null, mode: 'bounded', constraint: { hosts: ['share1.cgm-driver.test', 'share2.cgm-driver.test'] } },
    API3_AUTOPRUNE_ENTRIES: { default: null, mode: 'bounded', constraint: { min: 30, max: 3650 } },
    DISPLAY_UNITS: { default: 'mg/dl', mode: 'open', constraint: {} },
    TRUST_PROXY: { default: '1', mode: 'pinned', pin: '1', constraint: {} },
    DEBUG_LOGGING: { default: false, mode: 'pinned', pin: false, constraint: {} }
  };
}

// Owner write. opts.noPolicy / opts.noFloors are CONTROL breaks.
function checkOwnerWrite (key, value, row, opts) {
  const s = SETTINGS[key];
  if (!s) return 'unknown-key';
  if (!s.type(value)) return 'type';
  if (!opts.noFloors) { const f = s.floor(value); if (f) return f; }
  if (!opts.noPolicy) {
    if (!row || row.mode === 'pinned') return 'pinned';
    if (row.mode === 'bounded' && !s.constraint(value, row.constraint)) return 'constraint';
  }
  return null;
}

// Operator policy write (the operator plane).
function checkPolicyWrite (key, row, opts) {
  const s = SETTINGS[key];
  if (!s) return 'unknown-key';
  if (!['open', 'bounded', 'pinned'].includes(row.mode)) return 'mode';
  if (opts.noFloors) return null;
  for (const v of [row.default, row.pin]) {
    if (v === null || v === undefined) continue;
    if (!s.type(v)) return 'type';
    const f = s.floor(v); if (f) return f;
  }
  if (row.mode === 'bounded') { const f = s.constraintFloor(row.constraint || {}); if (f) return f; }
  return null;
}

function effective (policy, owner) {
  const out = {};
  for (const [k, s] of Object.entries(SETTINGS)) {
    const row = policy[k] || {};
    let v = s.codeDefault;
    if (row.default !== undefined && row.default !== null) v = row.default;
    if (row.mode !== 'pinned' && owner && k in owner) {
      if (row.mode === 'open' || s.constraint(owner[k], row.constraint || {})) v = owner[k];
    }
    if (row.mode === 'pinned' && row.pin !== undefined && row.pin !== null) v = row.pin;
    out[k] = v;
  }
  return out;
}

// Floors over the effective set: a tenant whose effective value breaks one
// is refused at provisioning.
function effectiveFloorViolations (eff) {
  const out = {};
  for (const [k, s] of Object.entries(SETTINGS)) {
    if (eff[k] === null || eff[k] === undefined) continue;
    const f = s.floor(eff[k]); if (f) out[k] = f;
  }
  return out;
}

module.exports = { SETTINGS, DRIVER_HOSTS, defaultPolicy, checkOwnerWrite, checkPolicyWrite, effective, effectiveFloorViolations };
