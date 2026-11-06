'use strict';
// Deterministic input clock for the oref0 profile script; installed client source is unchanged.
const NativeDate = Date;
const base = Number(process.env.M4_BASE);
if (!Number.isFinite(base)) throw new Error('M4_BASE is required for the profile fixture clock');
global.Date = class extends NativeDate {
  constructor (...args) { super(...(args.length ? args : [base])); }
  static now () { return base; }
};
