#!/usr/bin/env node
'use strict';
/*
 * make-records.js — writes cases.json, the one synthetic record set both hubs read.
 *
 * Synthetic only: no real user data, no identifiers. Every _id is a lab label.
 * All times are UTC, relative to T0 = 2026-01-15T00:00:00.000Z.
 *
 * Each case lists its records in ARRIVAL order (the order a client would upload them) and
 * the query times at which each hub is asked what is active. `role` is one of:
 *   case          one of the seven §5 cases
 *   control       a record set where the two hubs are expected to agree (break-it control)
 *   perturbation  one input of a case or control changed, to show the outputs move (non-vacuity)
 * `asks` names what each hub is asked at every query time:
 *   tt          active temporary target
 *   override_tx active override from `Temporary Override` treatments
 *   override_ds active override from Loop devicestatus `override`
 *   profile     active profile name and basal rate
 *
 * Usage: node make-records.js > cases.json
 */
const T0 = Date.parse('2026-01-15T00:00:00.000Z');
const at = (min) => new Date(T0 + min * 60000).toISOString();
const MIN = 60000;

const flat = (v) => [{ time: '00:00', value: v, timeAsSeconds: 0 }];
const hourly = () => Array.from({ length: 24 }, (_, h) => ({
  time: String(h).padStart(2, '0') + ':00', value: Math.round((1.0 + 0.05 * h) * 100) / 100, timeAsSeconds: h * 3600 }));
const store = (basal) => ({
  dia: 5, carbratio: flat(10), sens: flat(50), basal, target_low: flat(100), target_high: flat(120),
  units: 'mg/dl', timezone: 'UTC', carbs_hr: 20, delay: 20 });

// One profile document, loaded first in every case. Default's basal steps every hour
// (1.00 at 00:00, +0.05 per hour) so a schedule read at the wrong hour is visible.
const PROFILE = {
  _id: 'lab-profile-1', defaultProfile: 'Default', startDate: '2026-01-01T00:00:00.000Z',
  created_at: '2026-01-01T00:00:00.000Z', units: 'mg/dl', enteredBy: 'lab',
  store: { Default: store(hourly()), Weekend: store(flat(0.8)), Exercise: store(flat(0.5)) } };

const tx = (id, min, fields) => ({ collection: 'treatments', doc: Object.assign({ _id: id, created_at: at(min), enteredBy: 'lab' }, fields) });
const tt = (id, min, duration, target) => tx(id, min, Object.assign({ eventType: 'Temporary Target', duration, reason: 'Activity', units: 'mg/dl' },
  target ? { targetTop: target, targetBottom: target } : {}));
const ov = (id, min, duration) => tx(id, min, Object.assign({ eventType: 'Temporary Override', reason: 'Running', reasonDisplay: 'Running',
  correctionRange: [140, 160], insulinNeedsScaleFactor: 0.8 }, duration == null ? { durationType: 'indefinite' } : { duration }));
const ps = (id, min, profile, duration) => tx(id, min, { eventType: 'Profile Switch', profile, duration });
const aapsPs = (id, min, percentage, timeshiftMs) => tx(id, min, {
  eventType: 'Profile Switch', profile: 'Default', duration: 0, percentage, timeshift: timeshiftMs,
  profileJson: JSON.stringify(PROFILE.store.Default), enteredBy: 'lab-aaps' });
// Loop devicestatus: `override.timestamp` is the dosing decision's date and `override.duration`
// is the seconds remaining (LoopWorkspace NightscoutServiceKit StoredDosingDecision.swift).
const ds = (id, min, override) => ({ collection: 'devicestatus', doc: Object.assign({
  _id: id, created_at: at(min), device: 'loop://lab-phone',
  loop: { name: 'Loop', version: 'lab', timestamp: at(min) } }, override ? { override: Object.assign({ timestamp: at(min) }, override) } : {}) });
const loopOv = (remainingSec) => Object.assign({ name: 'Running', active: true, multiplier: 0.8,
  currentCorrectionRange: { minValue: 140, maxValue: 160 } }, remainingSec == null ? {} : { duration: remainingSec });
const dsSeries = (prefix, totalSec) => {
  const out = [];
  for (let m = 0; m <= 25; m += 5) out.push(ds(`${prefix}-${m}`, m, loopOv(totalSec == null ? null : totalSec - m * 60)));
  if (totalSec != null) for (let m = 30; m <= 35; m += 5) out.push(ds(`${prefix}-${m}`, m, { name: 'Running', active: false }));
  return out;
};
const q = (...mins) => mins.map((m) => ({ label: `T0+${m}`, t: at(m) }));

const cases = [
  { id: 'c1-tt-cancel', role: 'case', claim: '§5 row 1', asks: ['tt'],
    title: 'Timed temp target (60 min) followed by a cancel at +20 (careportal shape: duration 0)',
    records: [tt('c1-tt', 0, 60, 140), tt('c1-cancel', 20, 0)], queries: q(10, 30, 70) },
  { id: 'c1-ctl', role: 'control', of: 'c1-tt-cancel', asks: ['tt'],
    title: 'Timed temp target (60 min), no cancel',
    records: [tt('c1-tt', 0, 60, 140)], queries: q(10, 30, 70) },
  { id: 'c1-perturb', role: 'perturbation', of: 'c1-tt-cancel', asks: ['tt'],
    title: 'As c1, cancel moved from +20 to +40',
    records: [tt('c1-tt', 0, 60, 140), tt('c1-cancel', 40, 0)], queries: q(10, 30, 70) },

  { id: 'c2-ov-cancel', role: 'case', claim: '§5 row 2', asks: ['override_tx'],
    title: 'Temporary Override (60 min) followed by a stored Temporary Override Cancel at +20',
    records: [ov('c2-ov', 0, 60), tx('c2-cancel', 20, { eventType: 'Temporary Override Cancel' })], queries: q(10, 30, 70) },
  { id: 'c2-ctl', role: 'control', of: 'c2-ov-cancel', asks: ['override_tx'],
    title: 'Temporary Override (60 min) ended the way Loop ends it: same _id re-uploaded with duration 20',
    records: [ov('c2-ov', 0, 60), ov('c2-ov', 0, 20)], queries: q(10, 30, 70) },
  { id: 'c2-perturb', role: 'perturbation', of: 'c2-ov-cancel', asks: ['override_tx'],
    title: 'As c2, override duration 60 changed to 25',
    records: [ov('c2-ov', 0, 25), tx('c2-cancel', 20, { eventType: 'Temporary Override Cancel' })], queries: q(10, 30, 70) },

  { id: 'c3-loop-ds-override', role: 'case', claim: '§5 row 3', asks: ['override_ds'],
    title: 'Loop devicestatus every 5 min: 30-min override (duration = seconds remaining) +0..+25, then active:false at +30, +35',
    records: dsSeries('c3-ds', 1800), queries: q(12, 40, 120) },
  { id: 'c3-ctl', role: 'control', of: 'c3-loop-ds-override', asks: ['override_ds'],
    title: 'Loop devicestatus every 5 min +0..+25: indefinite override (no duration)',
    records: dsSeries('c3c-ds', null), queries: q(12, 27, 120) },
  { id: 'c3-perturb', role: 'perturbation', of: 'c3-loop-ds-override', asks: ['override_ds'],
    title: 'As c3, override length 30 min changed to 60 min (seconds remaining 3600 - elapsed); the active:false rows at +30, +35 dropped',
    records: dsSeries('c3p-ds', 3600).filter((r) => r.doc.override.active), queries: q(12, 40, 120) },
  { id: 'c3-perturb-short', role: 'perturbation', of: 'c3-loop-ds-override', asks: ['override_ds'],
    title: 'One Loop devicestatus at +0 with a 1-min override (duration 60 = seconds remaining)',
    records: [ds('c3s-ds-0', 0, loopOv(60))], queries: q(12, 40, 120) },

  { id: 'c4-ps-timed-after-permanent', role: 'case', claim: '§5 row 4', asks: ['profile'],
    title: 'Permanent switch to Weekend at +0, timed switch to Exercise at +60 for 60 min; queried after it expires',
    records: [ps('c4-ps-perm', 0, 'Weekend', 0), ps('c4-ps-timed', 60, 'Exercise', 60)], queries: q(30, 90, 150) },
  { id: 'c4-ctl', role: 'control', of: 'c4-ps-timed-after-permanent', asks: ['profile'],
    title: 'Permanent switch to Weekend at +0 only',
    records: [ps('c4-ps-perm', 0, 'Weekend', 0)], queries: q(30, 90, 150) },
  { id: 'c4-perturb', role: 'perturbation', of: 'c4-ps-timed-after-permanent', asks: ['profile'],
    title: 'As c4, timed switch duration 60 changed to 120',
    records: [ps('c4-ps-perm', 0, 'Weekend', 0), ps('c4-ps-timed', 60, 'Exercise', 120)], queries: q(30, 90, 150) },

  { id: 'c5-aaps-timeshift-ms', role: 'case', claim: '§5 row 5', asks: ['profile'],
    title: 'AndroidAPS 3.x Profile Switch: percentage 100, timeshift 7200000 (2 h in ms), embedded profileJson',
    records: [aapsPs('c5-ps', 0, 100, 2 * 3600000)], queries: q(300, 600) },
  { id: 'c5-ctl', role: 'control', of: 'c5-aaps-timeshift-ms', asks: ['profile'],
    title: 'As c5 with timeshift 0',
    records: [aapsPs('c5-ps', 0, 100, 0)], queries: q(300, 600) },
  { id: 'c5-perturb', role: 'perturbation', of: 'c5-ctl', asks: ['profile'],
    title: 'As c5-ctl with percentage 200',
    records: [aapsPs('c5-ps', 0, 200, 0)], queries: q(300, 600) },
  { id: 'c5-perturb-hours', role: 'perturbation', of: 'c5-aaps-timeshift-ms', asks: ['profile'],
    title: 'As c5 with timeshift 2 (the value in hours, as AndroidAPS 2.x sent it), percentage 100',
    records: [aapsPs('c5-ps', 0, 100, 2)], queries: q(300, 600) },

  { id: 'c6-tt-same-ms', role: 'case', claim: '§5 row 6', asks: ['tt'],
    title: 'Two temp targets with the same created_at: 60 min @140 arrives first, 30 min @100 second',
    records: [tt('c6-tt-a', 0, 60, 140), tt('c6-tt-b', 0, 30, 100)], queries: q(10, 45) },
  { id: 'c6-ctl', role: 'control', of: 'c6-tt-same-ms', asks: ['tt'],
    title: 'Two temp targets at different times, not overlapping: 60 min @140 at +0, 30 min @100 at +90',
    records: [tt('c6-tt-a', 0, 60, 140), tt('c6-tt-b', 90, 30, 100)], queries: q(10, 45, 100) },
  { id: 'c6-perturb', role: 'perturbation', of: 'c6-tt-same-ms', asks: ['tt'],
    title: 'As c6, arrival order swapped (30 min @100 first)',
    records: [tt('c6-tt-b', 0, 30, 100), tt('c6-tt-a', 0, 60, 140)], queries: q(10, 45) },

  { id: 'c7-ov-backfill', role: 'case', claim: '§12 / LAB item', asks: ['override_tx'],
    title: 'Two indefinite Temporary Overrides, out of order: the +60 one arrives first, the +0 one is backfilled after',
    records: [ov('c7-ov-later', 60, null), ov('c7-ov-earlier', 0, null)], queries: q(30, 90) },
  { id: 'c7-ctl', role: 'control', of: 'c7-ov-backfill', asks: ['override_tx'],
    title: 'Two timed, non-overlapping Temporary Overrides (30 min at +0, 30 min at +60), out of order',
    records: [ov('c7-ov-later', 60, 30), ov('c7-ov-earlier', 0, 30)], queries: q(15, 45, 75) },
  { id: 'c7-perturb', role: 'perturbation', of: 'c7-ov-backfill', asks: ['override_tx'],
    title: 'As c7, arrival in time order (the +0 one first)',
    records: [ov('c7-ov-earlier', 0, null), ov('c7-ov-later', 60, null)], queries: q(30, 90) },
];

process.stdout.write(JSON.stringify({
  note: 'Synthetic records for tools/lab/hub-active-state. No real user data. Generated by make-records.js.',
  t0: new Date(T0).toISOString(), profile: PROFILE, cases }, null, 2) + '\n');
