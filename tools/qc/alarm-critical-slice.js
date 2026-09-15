// What does Nightscout's alarm evaluation path actually READ?
//
// THE QUESTION. `lib/server/bootevent.js:327-333` is the whole alarm producer:
//
//     var sbx = require('../sandbox')().serverInit(env, ctx);
//     ctx.plugins.setProperties(sbx);
//     ctx.notifications.initRequests();
//     ctx.plugins.checkNotifications(sbx);
//     ctx.notifications.process(sbx);
//
// It runs once per load cycle, over ONE process-wide `ctx.ddata`, outside any
// request -- which is why `TENANCY_MODE=multi` withholds alarms today (T3.5).
// A per-tenant evaluator (D5, phase 4) needs a per-tenant `ddata` to evaluate
// against, and nobody owns that yet. {R} §12.5 PROPOSES splitting `ddata` into
// an alarm-critical slice and a display slice, and estimates the alarm slice at
// 50.6 KB -- but that figure came from reading eighteen plugins, not from
// running them. This measures it.
//
// METHOD, in three parts, because a read is not a dependency.
//
//   1. INVENTORY (Proxy). `ctx.ddata` is wrapped in a Proxy, and the object
//      `ddata.clone()` returns -- which is what `sbx.data` actually is -- is
//      wrapped in a second one. Every `get` of a string key on either is
//      recorded, with the key and a count. Two logs, because they are two
//      different objects with two different lifetimes: L1 is what the sandbox
//      and `lib/notifications.js` read off the LIVE ddata; L2 is what the
//      eighteen plugins read off the per-cycle CLONE.
//
//   2. DEPENDENCY (knockout). For every field in the union of L1 and L2, the
//      whole cycle is re-run with that one field neutralised (array -> [],
//      object -> {}, number -> 0) and the emitted notification set is compared
//      with the baseline. Two comparisons:
//        - DECISION signature: {level, group, plugin, eventName} per emission.
//          A field whose knockout changes this is ALARM-CRITICAL.
//        - FULL signature: decision plus title and message text. A field whose
//          knockout changes only this is DISPLAY-ONLY.
//        - Neither changes: READ BUT INERT for this scenario.
//      Every trial gets a FRESH ctx and a fresh `lib/notifications.js` instance,
//      because that module holds ack/snooze state that would otherwise silence
//      the second trial of a pair and fake a dependency.
//
//   3. SIZE. JSON-serialised UTF-8 bytes per field, for the same dataset, so
//      "the alarm-critical slice" has a number next to it.
//
// FOUR SCENARIOS, because an evaluation that fires nothing may touch far less
// than one that fires: quiet, urgent-low, warn-high, stale-data, plus a
// predicted-low (ar2) arm. Reported per scenario and unioned.
//
// NON-VACUITY. Three self-checks run before the measurement is believed
// (`--selfcheck`, included in the default run):
//   V1 instrument-blind: run the cycle with the clone proxy removed and confirm
//      L2 comes back EMPTY. If it does not, the "reads" are coming from
//      somewhere other than the instrument.
//   V2 corpus-live: confirm the scenarios do not all produce the same emission
//      set, and do not all produce the same read set. If they do, "the
//      alarm-critical slice" is just "everything" and the split is not real.
//   V3 knockout-live: confirm at least one field's knockout silences an alarm
//      AND at least one field's knockout changes nothing. A knockout pass in
//      which every field matters, or none does, is not evidence.
//
// WHAT THIS INSTRUMENT CANNOT SEE -- stated, not hidden:
//
//   a. A value already destructured into a local. `var sgvs = sbx.data.sgvs`
//      is recorded ONCE; every subsequent element access is invisible. So the
//      inventory is at TOP-LEVEL FIELD granularity and says nothing about how
//      much of an array was consumed. The knockout in part 2 is what recovers
//      the dependency, and it does not depend on the Proxy at all.
//   b. `ddata`'s own methods. `clone`, `processTreatments`, `recentDeviceStatus`
//      and the rest close over the `ddata` local inside `lib/data/ddata.js`'s
//      `init()`, NOT over `this`. Their internal reads bypass the Proxy
//      entirely. That is why `clone()` does not show up as eleven field reads
//      on L1 -- and it is also why L2 exists.
//   c. Anything inside `sbx.data.profile`. `sandbox.js:60-62` replaces the
//      cloned `profiles` array with a `profilefunctions` object built from
//      `ctx.ddata.profiles`. Reads of that object are invisible; what IS
//      visible is that `serverInit` reads `ddata.profiles`,
//      `ddata.profileTreatments`, `ddata.tempbasalTreatments` and
//      `ddata.combobolusTreatments` off the live ddata, unconditionally, on
//      every single cycle.
//   d. State that is not `ddata`: `ctx.cache`, storage, `env.settings`, and the
//      ack/snooze map inside `lib/notifications.js`. Settings are already
//      per-tenant (T3.3 `deriveEnv`); ack/snooze is T3.4 and still per-process.
//   e. The database. Nothing here talks to Mongo or Postgres.
//   f. `webhook`, which is enabled in a real server boot and makes an outbound
//      HTTP call. It is left out of the enable list on purpose; it reads the
//      same last-SGV the others do.
//
// Usage:
//   node tools/qc/alarm-critical-slice.js [--json] [--root <server checkout>]
//                                         [--verbose]

'use strict';

const path = require('node:path');
const fs = require('node:fs');
const { EventEmitter } = require('node:events');

const argv = process.argv.slice(2);
const flag = (n) => argv.includes(n);
const opt = (n, d) => {
  const i = argv.indexOf(n);
  return i >= 0 && argv[i + 1] ? argv[i + 1] : d;
};

const WORKTREE = opt('--root', process.env.NS_ROOT
  || '/home/bewest/src/rag-nightscout-ecosystem-alignment/externals/work/crm-seam-m');

if (!fs.existsSync(path.join(WORKTREE, 'lib/server/bootevent.js'))) {
  console.error('No cgm-remote-monitor checkout at ' + WORKTREE + '.');
  console.error('Pass --root <checkout>, or set NS_ROOT. The published numbers were');
  console.error('taken at cgm-remote-monitor 29749d92 (seam/t3-k, T3.5), which can be');
  console.error('restored with:  git worktree add --detach <dir> 29749d92');
  process.exit(2);
}
const AS_JSON = flag('--json');
// Quiet by default: the cycle runs a few hundred times and each run logs.
const QUIET = !flag('--verbose') || AS_JSON;

const req = (p) => require(path.join(WORKTREE, p));

// `lib/language.js` reads './translations/en/en.json' relative to the PROCESS
// cwd, not to its own module path, so the harness has to stand in the server
// checkout. Nothing is written there; see D12.
process.chdir(WORKTREE);

// The shipping modules log every emission and every snooze decision to the
// console, and this harness runs the cycle a few hundred times. QUIET silences
// them so the measurement is readable; the emissions are captured off the bus,
// not scraped from stdout, so nothing measured is lost.
const REAL_CONSOLE = { log: console.log, info: console.info, warn: console.warn, error: console.error };
function hush () {
  if (!QUIET) return;
  console.log = console.info = console.warn = console.error = function () {};
}
function unhush () {
  Object.assign(console, REAL_CONSOLE);
}

// ---------------------------------------------------------------- environment
//
// One env for the whole run. The alarm configuration is set through the same
// process.env that a real deployment uses, so `lib/settings.js` builds
// `settings.enable`, `settings.alarmTypes` and `settings.thresholds` by its own
// rules rather than by ours. The enable list is the shipped alarm set minus
// `webhook` (see limit (f)).
// NOTE, because it cost a measurement pass: `settings.enable` is matched against
// `plugin.name`, which is NOT the file name. `boluswizardpreview.js` registers as
// `bwp`, and `cannulaage`/`sensorage`/`insulinage`/`batteryage` register as
// `cage`/`sage`/`iage`/`bage`. A list written from file names silently enables
// thirteen of the eighteen alarm plugins and the run still looks healthy --
// including the only plugin that reads the profile to decide an alarm.
const ALARM_PLUGINS = [
  'bgnow', 'delta', 'direction', 'rawbg', 'upbat', 'ar2', 'simplealarms',
  'errorcodes', 'iob', 'cob', 'careportal', 'pump', 'openaps', 'xdripjs',
  'loop', 'bwp', 'cage', 'sage', 'iage', 'bage',
  'treatmentnotify', 'timeago', 'basal', 'dbsize',
  'runtimestate', 'devicestatus', 'profile', 'bolus'
];

Object.assign(process.env, {
  API_SECRET: 'alarmslicealarmslice123',
  NODE_ENV: 'test',
  ENABLE: ALARM_PLUGINS.join(' '),
  ALARM_TYPES: 'simple predict',
  ALARM_HIGH: 'on',
  ALARM_URGENT_HIGH: 'on',
  ALARM_LOW: 'on',
  ALARM_URGENT_LOW: 'on',
  ALARM_TIMEAGO_WARN: 'on',
  ALARM_TIMEAGO_URGENT: 'on',
  TIMEAGO_ENABLE_ALERTS: 'true',
  CAGE_ENABLE_ALERTS: 'true',
  SAGE_ENABLE_ALERTS: 'true',
  IAGE_ENABLE_ALERTS: 'true',
  BAGE_ENABLE_ALERTS: 'true',
  UPBAT_ENABLE_ALERTS: 'true'
});

const env = req('lib/server/env.js')();
env.testMode = true;

const language = req('lib/language.js')(fs);
const levels = req('lib/levels.js');

// ------------------------------------------------------------------- fixtures
//
// Sizes follow {R}'s fixture so the numbers are comparable with its 2,652 KB
// resident figure: 576 entries (48 h at 5 min), 600 treatments, 576
// devicestatus. Ids are DISTINCT -- {R} §1 is the record of what identical ids
// did to a previous harness.
const MIN = 60 * 1000;
const NOW = Date.UTC(2026, 8, 15, 12, 0, 0);

function oid (n) {
  return ('00000000000000000000000' + n.toString(16)).slice(-24);
}

function buildEntries (n, shape) {
  const out = [];
  for (let i = n - 1; i >= 0; i--) {
    const mills = NOW - i * 5 * MIN;
    out.push({
      _id: oid(1000 + i), mills, date: mills, type: 'sgv',
      device: 'share2', direction: 'Flat',
      sgv: shape(i, mills), mgdl: shape(i, mills),
      filtered: 150000, unfiltered: 152000, rssi: 100, noise: 1
    });
  }
  return out.sort((a, b) => a.mills - b.mills);
}

// `treatmentnotify.js:66-77` requests a URGENT-level SNOOZE whenever the newest
// treatment is under 10 minutes old, and `notifications.process` honours it, so
// a fixture whose newest treatment is 4 minutes old withholds every alarm and
// measures nothing. `newestAgoMins` is therefore a fixture parameter, not a
// constant, and the `recentTreatment` scenario exists to exercise the other
// side of it deliberately.
// Each device-age plugin has its OWN urgent threshold, and each fires only when
// the age in whole hours EQUALS it and the minutes past the hour are <= 20. One
// shared offset therefore fires at most one of the four, which is how the first
// version of `deviceAged` came back with three of the derived arrays looking
// inert when they are nothing of the sort.
//   cage 72 h (cannulaage.js:20) · iage 72 h (insulinage.js:19)
//   sage 166 h = 7 d - 2 h (sensorage.js:20) · bage 360 h (batteryage.js:19)
const CHANGE_EVENT_URGENT_HOURS = {
  'Site Change': 72, 'Sensor Start': 166, 'Insulin Change': 72, 'Pump Battery Change': 360
};
const CHANGE_EVENTS = Object.keys(CHANGE_EVENT_URGENT_HOURS);

function buildTreatments (n, newestAgoMins, ageHours) {
  const kinds = [
    { eventType: 'Meal Bolus', insulin: 2.5, carbs: 30 },
    { eventType: 'Correction Bolus', insulin: 1.2 },
    { eventType: 'Temp Basal', absolute: 0.8, duration: 30 },
    { eventType: 'Site Change' },
    { eventType: 'Sensor Start' },
    { eventType: 'Insulin Change' },
    { eventType: 'Pump Battery Change' },
    { eventType: 'Profile Switch', profile: 'Default', duration: 0 },
    { eventType: 'Temporary Target', targetTop: 120, targetBottom: 100, duration: 60 },
    { eventType: 'Combo Bolus', insulin: 1, relative: 1, duration: 60 }
  ];
  const out = [];
  for (let i = 0; i < n; i++) {
    const k = kinds[i % kinds.length];
    let mills = NOW - newestAgoMins * MIN - (n - 1 - i) * 4 * MIN;
    // The four device-age plugins alarm on how long ago the newest change event
    // of their type was. Pushing those events back without moving the boluses is
    // what exercises `sitechangeTreatments` and its three siblings.
    if (ageHours && ageHours[k.eventType]) {
      mills = NOW - (ageHours[k.eventType] * 60 + 10) * MIN;
    }
    out.push(Object.assign({
      _id: oid(5000 + i), mills, created_at: new Date(mills).toISOString(),
      enteredBy: 'harness', glucose: 120, glucoseType: 'Sensor', units: 'mg/dl',
      notes: 'seeded treatment ' + i
    }, k));
  }
  return out;
}

// `iobOverride` drives `lib/plugins/iob.js`, which prefers a devicestatus-reported
// IOB over one calculated from treatments. It is a scenario parameter because
// `boluswizardpreview.highSnoozedByIOB` can SNOOZE a high alarm when IOB covers
// it -- the one path in the shipped set where the profile and devicestatus decide
// whether somebody is woken up, rather than what the message says.
function buildDeviceStatus (n, iobOverride) {
  const out = [];
  for (let i = 0; i < n; i++) {
    const mills = NOW - (n - i) * 5 * MIN;
    out.push({
      _id: oid(9000 + i), mills, created_at: new Date(mills).toISOString(),
      device: 'openaps://rig', uploader: { battery: 84, batteryVoltage: 3900 },
      pump: {
        clock: new Date(mills).toISOString(), battery: { percent: 61, voltage: 1.44 },
        reservoir: 92.5, status: { status: 'normal', bolusing: false, suspended: false },
        iob: { bolusiob: iobOverride === undefined ? 0.4 : iobOverride, timestamp: new Date(mills).toISOString() }
      },
      openaps: {
        iob: { iob: iobOverride === undefined ? 0.9 : iobOverride, activity: 0.01, bolusinsulin: 0.4, basaliob: 0.5, timestamp: new Date(mills).toISOString() },
        suggested: { timestamp: new Date(mills).toISOString(), bg: 120, temp: 'absolute', rate: 0.75, duration: 30, reason: 'seeded', COB: 12, IOB: 0.9, eventualBG: 115 },
        enacted: { timestamp: new Date(mills).toISOString(), bg: 120, rate: 0.75, duration: 30, received: true, reason: 'seeded', COB: 12, IOB: 0.9 }
      }
    });
  }
  return out;
}

const PROFILE_DOC = {
  _id: oid(1), mills: NOW - 30 * 24 * 60 * MIN,
  startDate: new Date(NOW - 30 * 24 * 60 * MIN).toISOString(),
  defaultProfile: 'Default', units: 'mg/dl',
  store: {
    Default: {
      dia: 5, carbs_hr: 30, delay: 20, timezone: 'UTC',
      carbratio: [{ time: '00:00', timeAsSeconds: 0, value: 10 }],
      sens: [{ time: '00:00', timeAsSeconds: 0, value: 50 }],
      basal: [{ time: '00:00', timeAsSeconds: 0, value: 0.85 },
        { time: '06:00', timeAsSeconds: 21600, value: 1.05 },
        { time: '12:00', timeAsSeconds: 43200, value: 0.95 }],
      target_low: [{ time: '00:00', timeAsSeconds: 0, value: 100 }],
      target_high: [{ time: '00:00', timeAsSeconds: 0, value: 120 }],
      units: 'mg/dl'
    }
  }
};

// Each scenario returns the raw collections and, in `now`, the evaluation
// instant. `shape(i)` gives the mgdl of the entry i buckets back from the end.
const SCENARIOS = {
  quiet: {
    label: 'no alarm (steady 110 mg/dl, fresh data)',
    now: NOW + MIN,
    shape: () => 110
  },
  urgentLow: {
    label: 'urgent low (last SGV 48 mg/dl, below bgLow 55)',
    now: NOW + MIN,
    shape: (i) => (i === 0 ? 48 : Math.max(48, 110 - (6 - Math.min(i, 6)) * 10))
  },
  warnHigh: {
    label: 'warn high (last SGV 205 mg/dl, above bgTargetTop 180)',
    now: NOW + MIN,
    shape: (i) => (i === 0 ? 205 : Math.min(205, 150 + (6 - Math.min(i, 6)) * 9))
  },
  stale: {
    label: 'stale data (last SGV 45 min old, timeago urgent)',
    now: NOW + 45 * MIN,
    shape: () => 110
  },
  predictedLow: {
    label: 'predicted low (falling fast, ar2 forecast crosses bgLow)',
    now: NOW + MIN,
    shape: (i) => Math.min(260, 95 + i * 22)
  },
  highCoveredByIob: {
    label: 'high 205 mg/dl with 3.0 U IOB (boluswizardpreview snoozes the high)',
    now: NOW + MIN,
    iob: 3.0,
    shape: (i) => (i === 0 ? 205 : Math.min(205, 150 + (6 - Math.min(i, 6)) * 9))
  },
  deviceAged: {
    // `cannulaage.js:113` fires only when the age in WHOLE HOURS equals the
    // urgent threshold exactly (72 h) AND the minutes past that hour are <= 20.
    // 72 h + 11 min satisfies both; a fixture off by an hour measures nothing,
    // which is how the first version of this scenario came back silent.
    label: 'device age (each change event at its own urgent threshold: cage/sage/iage/bage)',
    now: NOW + MIN,
    ageHours: CHANGE_EVENT_URGENT_HOURS,
    shape: () => 110
  },
  insulinAgedWarn: {
    // `insulinage.js:92` compares against `insulinInfo.urgent`, which is never
    // assigned, where its three siblings compare against `prefs.urgent`. So iage
    // cannot reach URGENT at all and degrades to WARN at exactly 48 h. This
    // scenario is what makes `insulinchangeTreatments` observable as
    // alarm-critical, and V7 below asserts the defect rather than describing it.
    label: 'insulin reservoir 48 h old (iage WARN -- its URGENT branch is unreachable)',
    now: NOW + MIN,
    ageHours: { 'Insulin Change': 48 },
    shape: () => 110
  },
  recentTreatment: {
    label: 'urgent low WITH a treatment 4 min ago (treatmentnotify snoozes it)',
    now: NOW + MIN,
    treatmentAgoMins: 4,
    shape: (i) => (i === 0 ? 48 : Math.max(48, 110 - (6 - Math.min(i, 6)) * 10))
  }
};

function seedData (scenario) {
  return {
    sgvs: buildEntries(576, scenario.shape),
    mbgs: [{ _id: oid(300), mills: NOW - 120 * MIN, mgdl: 118, device: 'meter' }],
    cals: [{ _id: oid(400), mills: NOW - 720 * MIN, slope: 895, intercept: 30000, scale: 1 }],
    treatments: buildTreatments(600,
      scenario.treatmentAgoMins === undefined ? 25 : scenario.treatmentAgoMins,
      scenario.ageHours || null),
    devicestatus: buildDeviceStatus(576, scenario.iob),
    profiles: [JSON.parse(JSON.stringify(PROFILE_DOC))],
    food: [{ _id: oid(700), name: 'apple', carbs: 20, portion: 1, unit: 'g' }],
    activity: [{ _id: oid(800), mills: NOW - 60 * MIN, heartrate: 72, steps: 400 }],
    dbstats: { dataSize: 1024 * 1024 * 40, indexSize: 1024 * 1024 * 6 },
    lastUpdated: NOW,
    lastProfileFromSwitch: null
  };
}

// ------------------------------------------------------------- instrumentation
//
// A Proxy, not accessor instrumentation, for two reasons: `ddata` gains fields
// at runtime (`processTreatments` adds seven), so a fixed set of accessors
// would miss exactly the derived fields this is trying to inventory; and a
// Proxy leaves the shipping module byte-for-byte untouched, which D12 requires.
// Its cost is limit (a) above.
function recordingProxy (target, log) {
  return new Proxy(target, {
    get (t, k, r) {
      if (typeof k === 'string') log.set(k, (log.get(k) || 0) + 1);
      return Reflect.get(t, k, r);
    },
    ownKeys (t) {
      log.set('<ownKeys>', (log.get('<ownKeys>') || 0) + 1);
      return Reflect.ownKeys(t);
    },
    has (t, k) {
      if (typeof k === 'string') log.set(k, (log.get(k) || 0) + 1);
      return Reflect.has(t, k);
    }
  });
}

// ------------------------------------------------------------------ the cycle
//
// Reproduces `bootevent.js:327-333` exactly, with a fresh ctx so that the
// ack/snooze map in `lib/notifications.js` cannot carry between trials.
function runCycle (scenarioKey, mutate, options) {
  options = options || {};
  const scenario = SCENARIOS[scenarioKey];
  const bus = new EventEmitter();
  const emitted = [];
  bus.on('notification', (n) => emitted.push(n));

  const ctx = {
    language, levels, settings: env.settings, bus, runtimeState: 'loaded',
    moment: req('node_modules/moment-timezone')
  };

  const ddata = req('lib/data/ddata.js')();
  Object.assign(ddata, seedData(scenario));
  ddata.processTreatments(false);           // what dataloader.js does before the cycle
  if (mutate) mutate(ddata);

  const liveLog = new Map();
  const cloneLog = new Map();

  ctx.ddata = options.blindLive ? ddata : recordingProxy(ddata, liveLog);

  if (!options.blindClone) {
    const rawClone = ddata.clone;
    ddata.clone = function instrumentedClone () {
      return recordingProxy(rawClone.call(ddata), cloneLog);
    };
  }

  ctx.notifications = req('lib/notifications.js')(env, ctx);

  // `notifications.process` emits at most ONE alarm per group -- the highest.
  // So a field that changes a MASKED alarm leaves the emitted set untouched and
  // would score INERT, even though a per-tenant evaluator that got it wrong
  // would emit a different alarm the moment the masking one went away. Record
  // what was REQUESTED as well as what was emitted, and classify on both.
  // The wrap has to happen before `serverInit`, because `sandbox.js:35` copies
  // the function REFERENCES into the sandbox with `pick`.
  const requested = [];
  const snoozed = [];
  const realRequestNotify = ctx.notifications.requestNotify;
  const realRequestSnooze = ctx.notifications.requestSnooze;
  ctx.notifications.requestNotify = function (n) { requested.push(n); return realRequestNotify(n); };
  ctx.notifications.requestSnooze = function (s2) { snoozed.push(s2); return realRequestSnooze(s2); };

  ctx.plugins = req('lib/plugins/index.js')(ctx).registerServerDefaults();

  // Freeze the clock so `sbx.time` is the scenario's instant, not wall time.
  const realNow = Date.now;
  Date.now = () => scenario.now;
  let sbx;
  let evalMs = 0;
  let phases = null;
  try {
    const t0 = process.hrtime.bigint();
    sbx = req('lib/sandbox.js')().serverInit(env, ctx);
    const t1 = process.hrtime.bigint();
    if (options.perPlugin) {
      ctx.plugins.eachEnabledPlugin(function (pl) {
        if (!pl.setProperties) return;
        const a = process.hrtime.bigint();
        try { pl.setProperties(sbx.withExtendedSettings(pl)); } catch (e) { /* as shipped */ }
        options.perPlugin[pl.name + '.setProperties'] =
          (options.perPlugin[pl.name + '.setProperties'] || 0) + Number(process.hrtime.bigint() - a) / 1e6;
      });
    } else {
      ctx.plugins.setProperties(sbx);
    }
    const t2 = process.hrtime.bigint();
    ctx.notifications.initRequests();
    if (options.perPlugin) {
      ctx.plugins.eachEnabledPlugin(function (pl) {
        if (!pl.checkNotifications) return;
        const a = process.hrtime.bigint();
        try { pl.checkNotifications(sbx.withExtendedSettings(pl)); } catch (e) { /* as shipped */ }
        options.perPlugin[pl.name + '.checkNotifications'] =
          (options.perPlugin[pl.name + '.checkNotifications'] || 0) + Number(process.hrtime.bigint() - a) / 1e6;
      });
    } else {
      ctx.plugins.checkNotifications(sbx);
    }
    const t3 = process.hrtime.bigint();
    ctx.notifications.process(sbx);
    const t4 = process.hrtime.bigint();
    evalMs = Number(t4 - t0) / 1e6;
    phases = {
      serverInit: Number(t1 - t0) / 1e6,
      setProperties: Number(t2 - t1) / 1e6,
      checkNotifications: Number(t3 - t2) / 1e6,
      process: Number(t4 - t3) / 1e6
    };
  } finally {
    Date.now = realNow;
    bus.emit('teardown');
  }

  return { emitted, requested, snoozed, liveLog, cloneLog, ddata, sbx, evalMs, phases };
}

// Three signatures, coarsest first, because "an alarm fired" and "a
// notification was emitted" are not the same event and only the first one wakes
// somebody up.
//
//   alarmSig  -- WARN and URGENT emissions only. THIS is the alarm decision.
//   notifySig -- every emission, INFO notifications and All-Clears included.
//   fullSig   -- notifySig plus title and message text.
//
// A field is ALARM-CRITICAL if knocking it out moves alarmSig; NOTIFY-ONLY if it
// moves only notifySig; DISPLAY if it moves only the text.
function requestedAlarmSig (requested) {
  return requested.filter((n) => n.level >= levels.WARN).map((n) => [
    n.level, n.group || 'default',
    n.plugin ? n.plugin.name : '<none>', n.eventName || ''
  ].join('|')).sort().join('\n');
}

function alarmSig (emitted) {
  return emitted.filter((n) => !n.clear && n.level >= levels.WARN).map((n) => [
    n.level, n.group || 'default',
    n.plugin ? n.plugin.name : '<none>', n.eventName || ''
  ].join('|')).sort().join('\n');
}

function decisionSig (emitted) {
  return emitted.map((n) => [
    n.level, n.group || 'default',
    n.plugin ? n.plugin.name : (n.clear ? '<clear>' : '<none>'),
    n.eventName || ''
  ].join('|')).sort().join('\n');
}

function fullSig (emitted) {
  return emitted.map((n) => [
    n.level, n.group || 'default',
    n.plugin ? n.plugin.name : (n.clear ? '<clear>' : '<none>'),
    n.eventName || '', n.title || '', n.message || ''
  ].join('|')).sort().join('\n');
}

// ------------------------------------------------------------------- knockout
//
// Neutralise one field and see whether the decision moves. "Neutralise" means
// the empty value of the field's own type: a per-tenant evaluator that did not
// materialise this field would see exactly that.
function neutralise (ddata, key) {
  const v = ddata[key];
  if (Array.isArray(v)) return () => { ddata[key] = []; };
  if (typeof v === 'number') return () => { ddata[key] = 0; };
  if (typeof v === 'string') return () => { ddata[key] = ''; };
  if (v && typeof v === 'object') return () => { ddata[key] = {}; };
  return () => { ddata[key] = undefined; };
}

function byteSize (v) {
  if (v === undefined) return 0;
  try { return Buffer.byteLength(JSON.stringify(v), 'utf8'); } catch (e) { return -1; }
}

function analyseScenario (key) {
  const base = runCycle(key, null, {});
  const baseAlarm = alarmSig(base.emitted);
  const baseRequested = requestedAlarmSig(base.requested);
  const baseDecision = decisionSig(base.emitted);
  const baseFull = fullSig(base.emitted);

  const readLive = [...base.liveLog.keys()].filter((k) => k !== '<ownKeys>');
  const readClone = [...base.cloneLog.keys()].filter((k) => k !== '<ownKeys>');

  // Everything on ddata, whether or not it was read, so that a field the Proxy
  // reports as UNREAD still gets a knockout -- that is the control arm.
  const allFields = Object.keys(base.ddata)
    .filter((k) => typeof base.ddata[k] !== 'function');

  const fields = {};
  for (const f of allFields) {
    const trial = runCycle(key, (dd) => neutralise(dd, f)(), {});
    const a = alarmSig(trial.emitted);
    const rq = requestedAlarmSig(trial.requested);
    const d = decisionSig(trial.emitted);
    const t = fullSig(trial.emitted);
    fields[f] = {
      readLive: base.liveLog.has(f) ? base.liveLog.get(f) : 0,
      readClone: base.cloneLog.has(f) ? base.cloneLog.get(f) : 0,
      bytes: byteSize(base.ddata[f]),
      alarmChanged: a !== baseAlarm,
      requestedChanged: rq !== baseRequested,
      notifyChanged: d !== baseDecision,
      textChanged: t !== baseFull,
      alarmAfter: a,
      verdict: a !== baseAlarm ? 'CRITICAL'
        : (rq !== baseRequested ? 'MASKED'
          : (d !== baseDecision ? 'NOTIFY'
            : (t !== baseFull ? 'DISPLAY' : 'INERT')))
    };
  }

  return {
    key,
    label: SCENARIOS[key].label,
    emitted: base.emitted.map((n) => ({
      level: n.level,
      levelName: levels.toDisplay(n.level),
      group: n.group || 'default',
      plugin: n.plugin ? n.plugin.name : (n.clear ? '<clear>' : '<none>'),
      eventName: n.eventName || null,
      title: n.title || null
    })),
    alarmSig: baseAlarm,
    requestedAlarmSig: baseRequested,
    requestedAll: base.requested.map((n) => ({
      level: n.level, levelName: levels.toDisplay(n.level),
      group: n.group || 'default',
      plugin: n.plugin ? n.plugin.name : '<none>', eventName: n.eventName || null,
      title: n.title || null })),
    snoozes: base.snoozed.map((s2) => ({ level: s2.level, title: s2.title, lengthMills: s2.lengthMills })),
    decisionSig: baseDecision,
    readLive, readClone,
    fields,
    totalBytes: byteSize(JSON.parse(JSON.stringify(
      Object.fromEntries(allFields.map((f) => [f, base.ddata[f]])))))
  };
}

// ---------------------------------------------------------------- depth probe
//
// A whole-field knockout says "sgvs matters" and prices it at the whole 48-hour
// array. That is the wrong price for a per-tenant evaluator, which would
// materialise a WINDOW, not a history. So: for each field in the slice, shrink
// it to its newest n elements and find the smallest n at which every scenario
// still produces the same requested-alarm set and the same emitted-alarm set.
// That n, and its bytes, is what the evaluator has to fetch.
//
// `treatments` is re-derived after truncation (`processTreatments`) because the
// seven derived arrays are a function of it, and an evaluator holding the last n
// treatments would derive them from those n.
const DEPTHS = [0, 1, 2, 3, 4, 6, 8, 12, 16, 24, 32, 48, 64, 96, 144, 288, 576, 600];

function depthProbe (sliceFields, results) {
  const baseline = {};
  for (const k of Object.keys(SCENARIOS)) {
    baseline[k] = { a: results[k].alarmSig, r: results[k].requestedAlarmSig };
  }

  const out = {};
  for (const f of sliceFields) {
    // A scalar has no tail. Probing it would silently report "0 is enough",
    // which is how V6b caught this function the first time it ran.
    const shape = runCycle('urgentLow', null, {}).ddata[f];
    if (!Array.isArray(shape)) {
      out[f] = { minimalTail: 'scalar', bytesAtMinimal: byteSize(shape),
        bytesWhole: byteSize(shape), length: null };
      continue;
    }
    let minimal = null;
    for (const n of DEPTHS) {
      let ok = true;
      for (const k of Object.keys(SCENARIOS)) {
        const trial = runCycle(k, (dd) => {
          if (!Array.isArray(dd[f])) return;
          // `[].slice(-0)` is `slice(0)` -- the WHOLE array. Depth 0 has to be
          // spelled out, or it is a no-op that passes every comparison.
          dd[f] = n === 0 ? [] : dd[f].slice(-n);
          if (f === 'treatments') dd.processTreatments(false);
        }, {});
        if (alarmSig(trial.emitted) !== baseline[k].a
          || requestedAlarmSig(trial.requested) !== baseline[k].r) { ok = false; break; }
      }
      if (ok) { minimal = n; break; }
    }
    // size that tail, on the urgentLow fixture
    const arr = shape;
    out[f] = {
      minimalTail: minimal,
      bytesAtMinimal: minimal === null ? byteSize(arr)
        : (minimal === 0 ? 2 : byteSize(arr.slice(-minimal))),
      bytesWhole: byteSize(arr),
      length: arr.length
    };
  }
  return out;
}

// ------------------------------------------------- the conservative window
//
// The depth probe's minimal tail is an EMPIRICAL MINIMUM over this fixture and
// these nine scenarios. It is a lower bound, not an engineering window, and the
// clearest example is `treatments`: the probe says 8 because in this fixture IOB
// comes from `devicestatus.openaps.iob` (`lib/plugins/iob.js` prefers it). A site
// with no device-reported IOB computes IOB and COB from treatments over the
// profile's DIA, so the safe window is DIA-bounded, not 8.
//
// So the report carries a second number, derived from the CODE's own constants
// rather than from the fixture. Each entry names the constant it comes from.
const CONSERVATIVE_WINDOW = {
  // bgnow buckets over the last ~15 min; timeago's urgent threshold is 30 min;
  // ar2 forecasts from the last two buckets. 60 min at 5 min spacing = 12.
  sgvs: { n: 12, why: 'bgnow 15 min buckets / timeago 30 min urgent -- 60 min of 5 min readings' },
  // DIA window for iob/cob when no device reports IOB. profile dia = 5 h; this
  // fixture is 4 min spacing, so 5 h = 75 documents.
  treatments: { n: 75, why: 'profile DIA 5 h of treatments, for iob/cob when devicestatus has none' },
  // dataloader.js already fetches the newest of each device/type; 10 covers the
  // per-device fan-out in recentDeviceStatus.
  devicestatus: { n: 10, why: 'newest per device/type -- dataloader already fetches these as count:1' },
  sitechangeTreatments: { n: 1, why: 'cannulaage reads the newest only' },
  sensorTreatments: { n: 1, why: 'sensorage reads the newest only' },
  insulinchangeTreatments: { n: 1, why: 'insulinage reads the newest only' },
  batteryTreatments: { n: 1, why: 'batteryage reads the newest only' },
  profiles: { n: 1, why: 'the active profile document' }
};

function conservativeSize (results) {
  const probe = runCycle('urgentLow', null, { blindLive: true, blindClone: true });
  let total = byteSize(probe.ddata.lastUpdated);
  const rows = [{ field: 'lastUpdated', n: 'scalar', bytes: byteSize(probe.ddata.lastUpdated),
    why: 'notifications.js:60 gates every emission on it' }];
  for (const [f, spec] of Object.entries(CONSERVATIVE_WINDOW)) {
    const arr = probe.ddata[f];
    const b = Array.isArray(arr) ? byteSize(arr.slice(-spec.n)) : byteSize(arr);
    total += b;
    rows.push({ field: f, n: spec.n, bytes: b, why: spec.why });
  }
  return { total, rows };
}

// ----------------------------------------------------------------------- bench
//
// The cost question behind the size question: what does ONE evaluation cost, and
// how much of that does the windowed slice remove? Times exactly the five lines
// at `bootevent.js:327-333` -- `serverInit` (which includes `ddata.clone()` and
// the profile deep clone), `setProperties`, `initRequests`, `checkNotifications`
// and `process`. Seeding, `processTreatments` and ctx construction sit outside
// the timer, because a per-tenant evaluator would not repeat them per wake.
//
// The instrumentation Proxies are OFF for this, or the measurement would be of
// the harness.
// The same timing, but against the conservative window rather than the
// empirically minimal one -- that is the number a phase-4 evaluator would plan
// against.
function benchWindow (spec, iterations) {
  const windowIt = (dd) => {
    for (const f of Object.keys(dd)) {
      if (typeof dd[f] === 'function' || !Array.isArray(dd[f])) continue;
      dd[f] = spec[f] ? dd[f].slice(-spec[f].n) : [];
    }
  };
  const xs = [];
  let sig = null;
  for (let i = 0; i < iterations; i++) {
    const r = runCycle('urgentLow', windowIt, { blindLive: true, blindClone: true });
    xs.push(r.evalMs);
    sig = alarmSig(r.emitted);
  }
  xs.sort((a, b) => a - b);
  return { p50: xs[Math.floor(xs.length / 2)], p95: xs[Math.floor(xs.length * 0.95)],
    n: iterations, alarmSig: sig };
}

function bench (depth, iterations) {
  const windowIt = (dd) => {
    for (const [f, d] of Object.entries(depth)) {
      if (typeof d.minimalTail === 'number' && Array.isArray(dd[f])) {
        dd[f] = d.minimalTail === 0 ? [] : dd[f].slice(-d.minimalTail);
      }
    }
    // Everything NOT in the slice goes away entirely: that is the point.
    for (const f of Object.keys(dd)) {
      if (typeof dd[f] === 'function' || f in depth) continue;
      if (Array.isArray(dd[f])) dd[f] = [];
    }
  };
  const med = (xs) => xs.slice().sort((a, b) => a - b)[Math.floor(xs.length / 2)];
  const p95 = (xs) => xs.slice().sort((a, b) => a - b)[Math.floor(xs.length * 0.95)];

  const out = {};
  for (const arm of ['full', 'windowed']) {
    const xs = [];
    for (let i = 0; i < iterations; i++) {
      const r = runCycle('urgentLow', arm === 'windowed' ? windowIt : null,
        { blindLive: true, blindClone: true });
      xs.push(r.evalMs);
    }
    out[arm] = { p50: med(xs), p95: p95(xs), n: iterations };
  }
  // and confirm the windowed arm still reaches the same verdict
  const w = runCycle('urgentLow', windowIt, { blindLive: true, blindClone: true });
  out.windowedAlarmSig = alarmSig(w.emitted);
  return out;
}

// ----------------------------------------------------------------- self-checks
function selfChecks (results, depth) {
  const checks = [];

  // V1 -- instrument-blind. Remove the clone Proxy; the plugin read log must be
  // empty. If it is not, the log is not coming from the instrument.
  const blind = runCycle('urgentLow', null, { blindClone: true, blindLive: true });
  checks.push({
    id: 'V1',
    name: 'instrument-blind: no proxy => no reads recorded',
    pass: blind.cloneLog.size === 0 && blind.liveLog.size === 0,
    detail: `cloneLog=${blind.cloneLog.size} liveLog=${blind.liveLog.size} ` +
            `(emissions still ${blind.emitted.length}, so the cycle ran)`
  });
  checks.push({
    id: 'V1b',
    name: 'instrument-blind: the cycle itself is unaffected by instrumentation',
    pass: decisionSig(blind.emitted) === results.urgentLow.decisionSig,
    detail: 'uninstrumented decision signature equals instrumented one'
  });

  // V2 -- corpus-live. The scenarios must not all be the same, in either axis.
  const decisions = new Set(Object.values(results).map((r) => r.alarmSig));
  const readSets = new Set(Object.values(results)
    .map((r) => [...new Set(r.readClone)].sort().join(',')));
  const criticalSets = new Set(Object.values(results).map((r) =>
    Object.keys(r.fields).filter((f) => r.fields[f].verdict === 'CRITICAL').sort().join(',')));
  checks.push({
    id: 'V2a',
    name: 'corpus-live: scenarios produce different emission sets',
    pass: decisions.size > 1,
    detail: `${decisions.size} distinct ALARM signatures across ${Object.keys(results).length} scenarios`
  });
  checks.push({
    id: 'V2b',
    name: 'corpus-live: scenarios differ in what they read or in what is critical',
    pass: readSets.size > 1 || criticalSets.size > 1,
    detail: `${readSets.size} distinct read sets, ${criticalSets.size} distinct critical sets`
  });

  // V3 -- knockout-live. At least one field must matter and at least one must not.
  const all = [];
  for (const r of Object.values(results)) {
    for (const [f, v] of Object.entries(r.fields)) all.push([r.key, f, v.verdict]);
  }
  const anyCritical = all.filter((x) => x[2] === 'CRITICAL');
  const anyInert = all.filter((x) => x[2] === 'INERT');
  checks.push({
    id: 'V3a',
    name: 'knockout-live: removing some field silences/changes an alarm',
    pass: anyCritical.length > 0,
    detail: anyCritical.length + ' critical (field,scenario) pairs, e.g. ' +
            (anyCritical[0] ? anyCritical[0].slice(0, 2).join('/') : '-')
  });
  checks.push({
    id: 'V3b',
    name: 'knockout-live: removing some field changes nothing (so it is not "everything")',
    pass: anyInert.length > 0,
    detail: anyInert.length + ' inert (field,scenario) pairs, e.g. ' +
            (anyInert[0] ? anyInert[0].slice(0, 2).join('/') : '-')
  });

  // V3c -- the read/dependency distinction is real: some field is READ but INERT.
  const readButInert = all.filter(([k, f, v]) =>
    v === 'INERT' && (results[k].fields[f].readClone > 0 || results[k].fields[f].readLive > 0));
  checks.push({
    id: 'V3c',
    name: 'a read is not a dependency: some field is read but inert',
    pass: readButInert.length > 0,
    detail: readButInert.length + ' read-but-inert pairs, e.g. ' +
            (readButInert[0] ? readButInert[0].slice(0, 2).join('/') : '-')
  });

  // V4 -- the snooze arm. `urgentLow` and `recentTreatment` differ ONLY in how
  // old the newest treatment is. If the first fires an alarm and the second does
  // not, then `ddata.treatments` decides whether somebody is woken up, and the
  // read/dependency split is not an artifact of message text.
  checks.push({
    id: 'V4',
    name: 'treatments can withhold an alarm: same BG, treatment 4 min ago vs 25 min ago',
    pass: results.urgentLow.alarmSig !== '' && results.recentTreatment.alarmSig === '',
    detail: `urgentLow alarms=${JSON.stringify(results.urgentLow.alarmSig)} ; ` +
            `recentTreatment alarms=${JSON.stringify(results.recentTreatment.alarmSig)}`
  });

  // V5 -- a named critical field really silences a named alarm. Not a count: the
  // specific claim, checked.
  const ulSgv = results.urgentLow.fields.sgvs;
  checks.push({
    id: 'V5a',
    name: 'knock out sgvs in urgentLow => the urgent-low alarm stops firing',
    pass: !!ulSgv && ulSgv.alarmChanged && ulSgv.alarmAfter === '',
    detail: ulSgv ? `alarmSig after knockout = ${JSON.stringify(ulSgv.alarmAfter)}` : 'missing'
  });
  const stDs = results.stale.fields.devicestatus;
  checks.push({
    id: 'V5b',
    name: 'knock out devicestatus in stale => the timeago alarm is unchanged (display only)',
    pass: !!stDs && !stDs.alarmChanged && stDs.textChanged,
    detail: stDs ? `alarmChanged=${stDs.alarmChanged} textChanged=${stDs.textChanged} ` +
                   `bytes=${stDs.bytes}` : 'missing'
  });

  // V6 -- the depth probe must actually bite. If every field's minimal tail is
  // the whole array, the window is not a window and the slice is priced wrong.
  // If any field's minimal tail is 0, the knockout that called it critical and
  // the probe that calls it dispensable disagree, and that has to be reported
  // rather than averaged.
  if (depth) {
    const entries = Object.entries(depth);
    const arrays = entries.filter(([, d]) => d.length !== null);
    const shrank = arrays.filter(([, d]) => d.minimalTail !== null
      && d.minimalTail < d.length);
    const zero = arrays.filter(([, d]) => d.minimalTail === 0);
    const unbounded = arrays.filter(([, d]) => d.minimalTail === null);
    checks.push({
      id: 'V6a',
      name: 'depth probe bites: some slice field needs less than its whole array',
      pass: shrank.length > 0,
      detail: entries.map(([f, d]) =>
        `${f}: ${d.minimalTail}/${d.length}`).join('  ')
    });
    checks.push({
      id: 'V6b',
      name: 'depth probe and knockout agree: no slice field has a minimal tail of 0',
      pass: zero.length === 0,
      detail: zero.length === 0 ? 'none' : ('DISAGREEMENT on ' + zero.map((z) => z[0]).join(','))
    });
    checks.push({
      id: 'V6c',
      name: 'depth probe terminated: every slice field found a sufficient tail',
      pass: unbounded.length === 0,
      detail: unbounded.length === 0 ? 'all bounded'
        : ('no sufficient tail within DEPTHS for ' + unbounded.map((z) => z[0]).join(','))
    });
  }

  // V7 -- an upstream defect, carried as a check so it cannot rot into prose.
  // `lib/plugins/insulinage.js:92` reads `insulinInfo.urgent` (never assigned)
  // where cannulaage:87, sensorage:141 and batteryage:87 all read `prefs.urgent`.
  // `age >= undefined` is always false, so iage's URGENT branch is dead code and
  // "Insulin reservoir change overdue!" can never be emitted. Evidence: at the
  // very threshold that fires cage/sage/bage at URGENT, iage emits nothing; at
  // its WARN threshold it emits WARN.
  const agedUrgent = results.deviceAged.alarmSig;
  const agedWarn = results.insulinAgedWarn.alarmSig;
  checks.push({
    id: 'V7',
    name: 'insulinage URGENT branch is unreachable (upstream defect, NOT fixed here)',
    pass: !agedUrgent.includes('|iage|') && agedWarn.includes('|iage|')
      && agedWarn.startsWith(String(levels.WARN) + '|'),
    detail: `at each plugin's urgent threshold: ${JSON.stringify(agedUrgent)} ` +
            `(cage/sage/bage URGENT, no iage) ; at iage's warn threshold: ` +
            `${JSON.stringify(agedWarn)}`
  });

  return checks;
}

// ---------------------------------------------------------------------- report
function main () {
  const results = {};
  hush();
  try {
    for (const k of Object.keys(SCENARIOS)) results[k] = analyseScenario(k);
  } finally { unhush(); }

  // Union across scenarios: a field critical in ANY scenario is in the slice.
  const allFields = [...new Set(Object.values(results)
    .flatMap((r) => Object.keys(r.fields)))].sort();
  const union = {};
  for (const f of allFields) {
    const per = Object.values(results).map((r) => r.fields[f]).filter(Boolean);
    const rank = { CRITICAL: 4, MASKED: 3, NOTIFY: 2, DISPLAY: 1, INERT: 0 };
    const worst = per.reduce((a, p) => (rank[p.verdict] > rank[a] ? p.verdict : a), 'INERT');
    union[f] = {
      verdict: worst,
      read: per.some((p) => p.readLive > 0 || p.readClone > 0),
      bytes: Math.max(...per.map((p) => p.bytes)),
      criticalIn: Object.values(results)
        .filter((r) => r.fields[f] && r.fields[f].verdict === 'CRITICAL').map((r) => r.key)
    };
  }

  const critBytes = allFields.filter((f) => union[f].verdict === 'CRITICAL')
    .reduce((a, f) => a + Math.max(0, union[f].bytes), 0);
  const notifyBytes = allFields.filter((f) => union[f].verdict === 'NOTIFY')
    .reduce((a, f) => a + Math.max(0, union[f].bytes), 0);
  const dispBytes = allFields.filter((f) => union[f].verdict === 'DISPLAY')
    .reduce((a, f) => a + Math.max(0, union[f].bytes), 0);
  const inertBytes = allFields.filter((f) => union[f].verdict === 'INERT')
    .reduce((a, f) => a + Math.max(0, union[f].bytes), 0);
  const maskedBytes = allFields.filter((f) => union[f].verdict === 'MASKED')
    .reduce((a, f) => a + Math.max(0, union[f].bytes), 0);

  const sliceFields = allFields.filter((f) => ['CRITICAL', 'MASKED'].includes(union[f].verdict));

  hush();
  let depth, checks;
  try {
    depth = depthProbe(sliceFields, results);
    checks = selfChecks(results, depth);
    bench.result = bench(depth, 60);
    bench.conservative = conservativeSize(results);
    bench.conservativeArm = benchWindow(CONSERVATIVE_WINDOW, 60);
  } finally { unhush(); }

  const windowedBytes = sliceFields.reduce((a, f) =>
    a + Math.max(0, depth[f] ? depth[f].bytesAtMinimal : union[f].bytes), 0);

  const summary = {
    worktree: WORKTREE,
    node: process.version,
    fixture: { sgvs: 576, treatments: 600, devicestatus: 576, profiles: 1 },
    enabled: env.settings.enable,
    thresholds: env.settings.thresholds,
    scenarios: results,
    union,
    depth,
    windowedBytes,
    bench: bench.result,
    conservative: bench.conservative,
    conservativeArm: bench.conservativeArm,
    totals: {
      criticalBytes: critBytes, maskedBytes, notifyBytes, displayBytes: dispBytes, inertBytes: inertBytes,
      allBytes: critBytes + maskedBytes + notifyBytes + dispBytes + inertBytes,
      criticalFields: allFields.filter((f) => union[f].verdict === 'CRITICAL'),
      maskedFields: allFields.filter((f) => union[f].verdict === 'MASKED'),
      sliceFields,
      notifyFields: allFields.filter((f) => union[f].verdict === 'NOTIFY'),
      displayFields: allFields.filter((f) => union[f].verdict === 'DISPLAY'),
      inertFields: allFields.filter((f) => union[f].verdict === 'INERT')
    },
    checks
  };

  if (AS_JSON) {
    process.stdout.write(JSON.stringify(summary, null, 2) + '\n');
    return checks.every((c) => c.pass) ? 0 : 1;
  }

  const kb = (b) => (b / 1024).toFixed(1) + ' KB';
  const out = [];
  out.push('');
  out.push('=== ALARM-CRITICAL SLICE ===================================================');
  out.push('worktree: ' + WORKTREE + '   node: ' + process.version);
  out.push('fixture: 576 sgvs, 600 treatments, 576 devicestatus, 1 profile, distinct _ids');
  out.push('enabled plugins (' + env.settings.enable.length + '): ' + env.settings.enable.join(' '));
  out.push('');

  for (const r of Object.values(results)) {
    out.push('--- ' + r.key + ': ' + r.label);
    out.push('    emitted: ' + (r.emitted.length === 0 ? '(nothing)' : ''));
    for (const e of r.emitted) {
      out.push('      [' + e.levelName + '] ' + e.plugin + ' group=' + e.group +
        ' event=' + e.eventName + ' title=' + JSON.stringify(e.title));
    }
    const pick = (v) => Object.keys(r.fields).filter((f) => r.fields[f].verdict === v);
    const crit = pick('CRITICAL'), noti = pick('NOTIFY'), disp = pick('DISPLAY'), inert = pick('INERT');
    out.push('    alarm signature (WARN/URGENT only): ' +
      (r.alarmSig ? JSON.stringify(r.alarmSig) : '(no alarm)'));
    out.push('    read off live ddata : ' + r.readLive.join(' '));
    out.push('    read off sbx.data   : ' + r.readClone.join(' '));
    const masked = pick('MASKED');
    out.push('    requested alarms (before highest-wins + snooze): ' +
      (r.requestedAlarmSig ? JSON.stringify(r.requestedAlarmSig) : '(none)'));
    if (r.snoozes.length) out.push('    snoozes requested: ' + JSON.stringify(r.snoozes));
    out.push('    ALARM-CRITICAL (' + crit.length + '): ' + (crit.join(' ') || '-'));
    out.push('    MASKED-ALARM   (' + masked.length + '): ' + (masked.join(' ') || '-'));
    out.push('    NOTIFY-ONLY    (' + noti.length + '): ' + (noti.join(' ') || '-'));
    out.push('    DISPLAY-ONLY   (' + disp.length + '): ' + (disp.join(' ') || '-'));
    out.push('    INERT          (' + inert.length + '): ' + (inert.join(' ') || '-'));
    out.push('');
  }

  out.push('--- UNION across scenarios -------------------------------------------------');
  out.push('  field                      read  bytes      verdict   critical in');
  for (const f of allFields) {
    const u = union[f];
    out.push('  ' + f.padEnd(26) + (u.read ? ' yes ' : ' no  ') +
      String(u.bytes).padStart(9) + '  ' + u.verdict.padEnd(9) + ' ' +
      (u.criticalIn.join(',') || '-'));
  }
  out.push('');
  const whole = critBytes + maskedBytes + notifyBytes + dispBytes + inertBytes;
  out.push('  ALARM-CRITICAL slice : ' + summary.totals.criticalFields.length +
    ' fields, ' + kb(critBytes));
  out.push('  MASKED-ALARM         : ' +
    allFields.filter((f) => union[f].verdict === 'MASKED').length + ' fields, ' + kb(maskedBytes));
  out.push('  NOTIFY-ONLY          : ' + summary.totals.notifyFields.length +
    ' fields, ' + kb(notifyBytes));
  out.push('  DISPLAY-ONLY         : ' + summary.totals.displayFields.length +
    ' fields, ' + kb(dispBytes));
  out.push('  INERT                : ' + summary.totals.inertFields.length +
    ' fields, ' + kb(inertBytes));
  out.push('  whole ddata          : ' + allFields.length + ' fields, ' + kb(whole));
  out.push('  critical+masked/whole: ' +
    (100 * (critBytes + maskedBytes) / whole).toFixed(1) + ' % (whole fields)');
  out.push('');
  out.push('--- DEPTH PROBE: how much of each slice field the alarm actually needs ------');
  out.push('  field                  minimal tail / length     bytes@tail   bytes whole');
  for (const f of sliceFields) {
    const d = depth[f];
    out.push('  ' + f.padEnd(22) + String(d.minimalTail).padStart(8) + ' / ' +
      String(d.length).padStart(4) + '        ' + String(d.bytesAtMinimal).padStart(8) +
      '     ' + String(d.bytesWhole).padStart(9));
  }
  out.push('');
  out.push('  >>> WINDOWED ALARM-CRITICAL SLICE: ' + windowedBytes + ' bytes (' +
    kb(windowedBytes) + ') against ' + kb(whole) + ' for the whole of ddata' +
    '  = ' + (100 * windowedBytes / whole).toFixed(2) + ' %');
  out.push('');
  out.push('--- COST OF ONE EVALUATION (bootevent.js:327-333 only) ----------------------');
  out.push('  full ddata      p50 ' + bench.result.full.p50.toFixed(3) + ' ms   p95 ' +
    bench.result.full.p95.toFixed(3) + ' ms   (n=' + bench.result.full.n + ')');
  out.push('  windowed slice  p50 ' + bench.result.windowed.p50.toFixed(3) + ' ms   p95 ' +
    bench.result.windowed.p95.toFixed(3) + ' ms   (n=' + bench.result.windowed.n + ')');
  out.push('  speedup         ' + (bench.result.full.p50 / bench.result.windowed.p50).toFixed(1) + '×');
  out.push('  windowed arm still emits: ' + JSON.stringify(bench.result.windowedAlarmSig));
  out.push('');
  out.push('--- CONSERVATIVE WINDOW (from the code\'s constants, not the fixture) -------');
  for (const r of bench.conservative.rows) {
    out.push('  ' + r.field.padEnd(24) + String(r.n).padStart(7) + '  ' +
      String(r.bytes).padStart(7) + ' B   ' + r.why);
  }
  out.push('  >>> CONSERVATIVE ALARM SLICE: ' + bench.conservative.total + ' bytes (' +
    kb(bench.conservative.total) + ')');
  out.push('  cost at that window: p50 ' + bench.conservativeArm.p50.toFixed(3) + ' ms   p95 ' +
    bench.conservativeArm.p95.toFixed(3) + ' ms   emits ' +
    JSON.stringify(bench.conservativeArm.alarmSig));
  out.push('');
  out.push('--- NON-VACUITY ------------------------------------------------------------');
  for (const c of checks) {
    out.push('  [' + (c.pass ? 'PASS' : 'FAIL') + '] ' + c.id + ' ' + c.name);
    out.push('         ' + c.detail);
  }
  out.push('');
  console.log(out.join('\n'));
  return checks.every((c) => c.pass) ? 0 : 1;
}

if (require.main === module) {
  process.exitCode = main();
}

module.exports = { runCycle, analyseScenario, SCENARIOS };
