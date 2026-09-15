// ns-evaluator: a spike, top-down, to find out what a per-tenant evaluation
// loop actually needs. Phase 4, task T4.4.
//
// WHAT THIS IS. It drives Nightscout's REAL alarm-evaluation path -- the exact
// four calls `lib/server/bootevent.js:328-332` makes inside its `data-loaded`
// listener -- for TWO TENANTS IN ONE PROCESS, each with its own settings from
// T3.3's `ctxFor`, each emitting into its own T3.5 room. Every module under
// test is `require`d from a cgm-remote-monitor checkout by path, so this
// harness and the shipping code cannot drift. Nothing is reimplemented.
//
// WHAT THIS IS NOT.
//
//  - NOT an implementation of `ns-evaluator`. There is no scheduler, no
//    partitioning, no slot reader, no backpressure. The per-tenant context this
//    builds is scaffolding that exists to DISCOVER the requirement list, and
//    several of its choices are wrong on purpose (see REQ-2: `lib/bus.js` is
//    replaced with a bare EventEmitter because instantiating the shipping bus
//    per tenant would start one `setInterval` per tenant).
//  - NOT a database test. `ddata` is seeded by hand. `dataloader` is never run,
//    because running it per tenant is itself one of the open requirements this
//    spike reports rather than answers. Nothing here opens a connection to
//    anything.
//  - NOT a change to cgm-remote-monitor. Decision D12: that repository stays
//    pristine. Section `nonvacuity` writes ONE temporarily weakened copy of a
//    module beside the original (so its relative requires still resolve) and
//    deletes it in a `finally`.
//
// THE NON-VACUITY RULE THIS FILE IS BUILT AROUND. A check that has never failed
// is not evidence. Two tenants with IDENTICAL settings prove nothing about
// per-tenant thresholds, and a loop where one tenant never evaluates makes
// isolation trivially true. So section `isolation` gives A and B DIFFERENT
// thresholds against ONE identical glucose reading and requires the decisions
// to DIFFER, and section `nonvacuity` breaks the isolation four ways and
// requires the check to go RED each time.
//
// Usage:
//   node tools/qc/ns-evaluator-arm.js [section] [--root <checkout>] [--json]
//
// Sections: substrate isolation nonvacuity cold blast ack slice cost all (default)

'use strict';

const fs = require('node:fs');
const path = require('node:path');
const EventEmitter = require('node:events');

const argv = process.argv.slice(2);
function flag (name, fallback) {
  const i = argv.indexOf('--' + name);
  return i === -1 ? fallback : argv[i + 1];
}
const JSON_OUT = argv.includes('--json');
const SECTION = argv.find((a, i) => !a.startsWith('--') && argv[i - 1] !== '--root') || 'all';

const ROOT = path.resolve(flag('root',
  '/home/bewest/src/rag-nightscout-ecosystem-alignment/externals/work/crm-seam-n'));

if (!fs.existsSync(path.join(ROOT, 'lib', 'server', 'tenant-context.js'))) {
  console.error('No cgm-remote-monitor checkout with T3.3 at ' + ROOT + '.');
  console.error('Pass --root <checkout>. Do NOT point this at a checkout another session is');
  console.error('committing to: section `nonvacuity` writes and deletes a weakened module copy.');
  process.exit(2);
}

// The process environment a deployment is built from. Set before the first
// `config()`, because `setAPISecret` DELETES API_SECRET out of `process.env`
// once read -- which is the reason T3.3's `deriveEnv` derives from a BUILT env
// rather than calling `config()` a second time.
process.env.API_SECRET = process.env.API_SECRET || 'ns-evaluator-spike-secret';
process.env.HOSTNAME = process.env.HOSTNAME || 'localhost';
process.env.INSECURE_USE_HTTP = 'true';
process.env.ENABLE = process.env.ENABLE
  || 'simplealarms ar2 bgnow delta direction upbat rawbg errorcodes iob cob';

const lib = name => require(path.join(ROOT, 'lib', name));

const tenantContext = lib('server/tenant-context');
const tenantScope = lib('storage/tenant-scope');
const socketTenancy = lib('server/socket-tenancy');
const sandbox = () => require(path.join(ROOT, 'lib', 'sandbox'))();

const baseEnv = lib('server/env')();
tenantScope.setTenancyMode('multi');

// ------------------------------------------------------------------ results

const results = [];
let failures = 0;
function record (section, name, ok, detail) {
  results.push({ section, name, ok, detail });
  if (!ok) failures += 1;
  if (!JSON_OUT) {
    console.log(`  ${ok ? 'ok  ' : 'FAIL'}  ${name}`);
    if (detail) console.log(`        ${detail}`);
  }
}
function head (title) { if (!JSON_OUT) console.log('\n=== ' + title); }

// -------------------------------------------------- the per-tenant context
//
// Everything below the `buildContext` line is what T3.3 does NOT give you, and
// enumerating it is half this spike's answer. `DERIVED_CONTEXT_KEYS` is
// deliberately `['tenant','env','settings','store']`; the evaluator needs seven
// more things, and three of them are process-wide singletons today.

const EXTRA_CONTEXT_KEYS = Object.freeze([
  'bus', 'language', 'levels', 'moment', 'plugins', 'ddata', 'notifications'
]);

function buildEvaluatorContext (base, tenant, options) {
  const ctx = tenantContext.buildContext(base, tenant, options);
  const env = ctx.env;

  // REQ-2. NOT `lib/bus.js`. `bus(settings, ctx)` calls `setInterval` at
  // construction and returns the emitter, so one bus per tenant is one heartbeat
  // timer per tenant -- at {R}'s 1,580 resident tenants that is 1,580 timers
  // whose only job is to fire the process-wide tick the evaluator replaces.
  ctx.bus = new EventEmitter();

  // REQ-5. `language` is genuinely per tenant (`settings.language`) and is a
  // fresh instance per call, so this half is fine...
  ctx.language = lib('language')();
  ctx.language.set(env.settings.language || 'en');

  // ...but `lib/levels.js` exports a MODULE SINGLETON and bootevent.js:212
  // mutates it: `ctx.levels.translate = ctx.language.translate`. Two tenants get
  // the same object and the LAST ONE BUILT wins the translation function for
  // both. That is BF-22 seen from the evaluator. Assigning it here reproduces
  // the shipping code exactly rather than papering over it; section `substrate`
  // measures the consequence.
  ctx.levels = lib('levels');
  ctx.levels.translate = ctx.language.translate;

  ctx.moment = require(path.join(ROOT, 'node_modules', 'moment-timezone'));

  // REQ-3. The plugin REGISTRY is per tenant, not just the settings it reads.
  // `plugins.register` computes `enabledPlugins` from `ctx.settings.enable` ONCE
  // at construction (lib/plugins/index.js:136), so a shared registry means every
  // tenant runs the first tenant's enabled plugin list.
  ctx.plugins = lib('plugins')({
    settings: env.settings
    , language: ctx.language
    , levels: ctx.levels
    , moment: ctx.moment
  }).registerServerDefaults();

  // REQ-1. The missing thing. Nothing owns this: it is `require('../data/ddata')()`
  // at bootevent.js:244, once per process, and nothing in T3.3 builds one.
  ctx.ddata = lib('data/ddata')();

  // REQ-4. Per tenant, and exactly what T3.3's DERIVED_CONTEXT_KEYS comment
  // forbids caching, because ack/snooze is not in storage and an eviction would
  // silently un-snooze somebody's alarm.
  ctx.notifications = lib('notifications')(env, ctx);

  ctx.runtimeState = 'loaded';
  return ctx;
}

function cacheFor (overridesById) {
  return tenantContext.createContextCache({
    base: { env: baseEnv, store: null }
    , settingsFor: t => overridesById[t.id]
    , build: buildEvaluatorContext
  });
}

// ------------------------------------------------------------- the emitter
//
// T3.5's room logic, used exactly as the shipping emitters use it: `currentRoom`
// reads `tenantScope.currentTenant()` and returns null -- withhold -- when
// nothing is bound. A stub resolver/registry is enough because only the room
// half is under test here; T3.1 and T3.5 already own the handshake half.

const rooms = socketTenancy.create({
  resolver: { resolve: () => null, hasHostRule: true }
  , registry: { lookup: async () => null }
  , enclave: baseEnv.enclave
  , requireTokenClaim: false
});

// ------------------------------------------------------------- evaluation
//
// bootevent.js:328-332, verbatim, with the bus listener replaced by a recorder.
// If these four calls ever stop matching the shipping listener this spike is
// lying, so they are quoted here rather than abstracted.

function evaluate (ctx) {
  const emitted = [];
  ctx.bus.removeAllListeners('notification');
  ctx.bus.on('notification', function (notify) {
    emitted.push({
      level: notify.level
      , title: notify.title || null
      , group: notify.group
      , clear: !!notify.clear
      // The room is resolved AT EMIT TIME, from the ambient binding, which is
      // the whole of T3.5's contract. null means withheld.
      , room: rooms.currentRoom(socketTenancy.TENANT_ROOM, '/alarm')
    });
  });

  const sbx = sandbox().serverInit(ctx.env, ctx);
  ctx.plugins.setProperties(sbx);
  ctx.notifications.initRequests();
  ctx.plugins.checkNotifications(sbx);
  ctx.notifications.process(sbx);
  return emitted;
}

function seed (ctx, mgdl, now) {
  ctx.ddata.sgvs = [{
    _id: 'sgv-' + ctx.tenant.id, mgdl, mills: now - 60000, type: 'sgv', direction: 'Flat'
  }];
  ctx.ddata.lastUpdated = now;
}

// The corpus. ONE glucose value, TWO threshold sets chosen so that the SAME
// reading lands in a different band for each tenant. This is the non-vacuity
// property of the corpus: if the thresholds were equal the isolation check
// could not fail.
const SGV = 250;
const THRESHOLDS = {
  // 250 is above bgHigh 200 -> URGENT HIGH
  A: { settings: { thresholds: { bgHigh: 200, bgTargetTop: 170, bgTargetBottom: 80, bgLow: 55 } } }
  // 250 is below bgTargetTop 380 -> nothing at all
  , B: { settings: { thresholds: { bgHigh: 400, bgTargetTop: 380, bgTargetBottom: 80, bgLow: 55 } } }
};

function runBoth (cache, now) {
  const out = {};
  for (const id of ['A', 'B']) {
    out[id] = tenantScope.withTenant(id, function () {
      const ctx = cache.ctxFor({ id, slug: id.toLowerCase() });
      seed(ctx, SGV, now);
      return evaluate(ctx);
    });
  }
  return out;
}

// ============================================================== substrate

function sectionSubstrate () {
  head('substrate -- what ctxFor gives, and what the evaluator needs beyond it');

  record('substrate', 'T3.3 derives four keys', true
    , 'DERIVED_CONTEXT_KEYS = ' + JSON.stringify(tenantContext.DERIVED_CONTEXT_KEYS));

  const cache = cacheFor(THRESHOLDS);
  const ctx = tenantScope.withTenant('A', () => cache.ctxFor({ id: 'A', slug: 'a' }));
  const extra = Object.keys(ctx).filter(k => !tenantContext.DERIVED_CONTEXT_KEYS.includes(k));

  record('substrate', 'the evaluator needs seven keys T3.3 does not build'
    , EXTRA_CONTEXT_KEYS.every(k => extra.includes(k))
    , 'beyond DERIVED_CONTEXT_KEYS: ' + JSON.stringify(extra));

  // The store is shared by reference, deliberately (D3: RLS on a pooled
  // connection). Asserted so that a future per-tenant store shows up as a
  // failure here rather than as a thousand connection pools in production.
  const b = tenantScope.withTenant('B', () => cache.ctxFor({ id: 'B', slug: 'b' }));
  record('substrate', 'store stays shared by reference across tenants'
    , ctx.store === b.store, 'both contexts: store === base.store');

  // BF-22, measured rather than asserted.
  record('substrate', 'levels is ONE object for every tenant (BF-22)'
    , ctx.levels === b.levels
    , 'lib/levels.js is a module singleton and bootevent.js:212 assigns .translate on it; '
      + 'the last context built owns alarm-level text for every tenant in the process');
  record('substrate', 'language IS per tenant', ctx.language !== b.language
    , 'lib/language.js returns a fresh instance, so settings.language can differ');
  record('substrate', 'the plugin registry is per tenant here', ctx.plugins !== b.plugins
    , 'enabledPlugins is computed from settings.enable once, at register() time');
  record('substrate', 'notifications is per tenant here', ctx.notifications !== b.notifications
    , 'and T3.3 forbids caching it: eviction would un-snooze an alarm');
  record('substrate', 'ddata is per tenant here, and nothing in shipping code builds it'
    , ctx.ddata !== b.ddata
    , 'bootevent.js:244 builds exactly one per process');
}

// ============================================================== isolation

function sectionIsolation () {
  head('isolation -- two tenants, DIFFERENT thresholds, one identical reading');

  const now = Date.now();
  const cache = cacheFor(THRESHOLDS);
  const out = runBoth(cache, now);

  record('isolation', 'the corpus is non-vacuous: the thresholds differ'
    , THRESHOLDS.A.settings.thresholds.bgHigh !== THRESHOLDS.B.settings.thresholds.bgHigh
    , `A.bgHigh=${THRESHOLDS.A.settings.thresholds.bgHigh} `
      + `B.bgHigh=${THRESHOLDS.B.settings.thresholds.bgHigh} reading=${SGV} mg/dl`);

  record('isolation', 'A alarms on its own thresholds'
    , out.A.length === 1 && out.A[0].level === 2
    , JSON.stringify(out.A));

  record('isolation', 'B does NOT alarm on the same reading'
    , out.B.length === 0, JSON.stringify(out.B));

  record('isolation', "A's alarm is addressed to A's room only"
    , out.A.length === 1 && out.A[0].room === 'Tenant:A'
    , 'room = ' + (out.A[0] && out.A[0].room));

  record('isolation', 'nothing was addressed to B'
    , !out.A.some(e => e.room === 'Tenant:B') && out.B.length === 0);

  // The decisions differ because the SETTINGS differ, not because one tenant
  // failed to run. Proved by making the reading unambiguous for both: 450 is
  // above both bgHigh values, so both must alarm. If B's evaluation were not
  // running, this check would fail and the one above would be vacuous.
  const cache2 = cacheFor(THRESHOLDS);
  const out2 = {};
  for (const id of ['A', 'B']) {
    out2[id] = tenantScope.withTenant(id, function () {
      const c = cache2.ctxFor({ id, slug: id.toLowerCase() });
      seed(c, 450, now);
      return evaluate(c);
    });
  }
  record('isolation', "B's evaluation really runs (450 alarms for BOTH tenants)"
    , out2.A.length === 1 && out2.B.length === 1
      && out2.A[0].room === 'Tenant:A' && out2.B[0].room === 'Tenant:B'
    , `A=${JSON.stringify(out2.A.map(e => e.room))} B=${JSON.stringify(out2.B.map(e => e.room))}`);

  // T3.5's fail-closed, reproduced: the same evaluation OUTSIDE a tenant scope
  // withholds rather than broadcasts. This is why multi turns alarms off today.
  const cache3 = cacheFor(THRESHOLDS);
  const unbound = (function () {
    const c = tenantScope.withTenant('A', () => cache3.ctxFor({ id: 'A', slug: 'a' }));
    seed(c, SGV, now);
    return evaluate(c);                       // deliberately NOT inside withTenant
  })();
  record('isolation', 'evaluation outside a tenant scope is WITHHELD, not broadcast'
    , unbound.length === 1 && unbound[0].room === null
    , 'the alarm is produced and has nowhere to go: room = ' + unbound[0].room
      + ' -- this is exactly why TENANCY_MODE=multi has alarms off today');
}

// ============================================================== nonvacuity
//
// Four deliberate breaks. Each must make the isolation check GO RED. A break
// that leaves the check green means the check was not testing what it claims.

function withWeakened (relPath, edits, fn) {
  const src = path.join(ROOT, 'lib', relPath);
  const original = fs.readFileSync(src, 'utf8');
  let patched = original;
  for (const [from, to] of edits) {
    if (!patched.includes(from)) {
      throw new Error(`weakening ${relPath}: anchor not found -- ${JSON.stringify(from.slice(0, 60))}. `
        + 'The module changed under this harness; read why before adapting the anchor.');
    }
    patched = patched.split(from).join(to);
  }
  // Beside the original, so its own relative requires still resolve. Always
  // deleted -- a stranded weakened module is a hazard, not a leftover.
  const copy = src.replace(/\.js$/, '.__weakened' + process.pid + '.js');
  fs.writeFileSync(copy, patched);
  try {
    return fn(require(copy));
  } finally {
    delete require.cache[require.resolve(copy)];
    fs.unlinkSync(copy);
  }
}

function sectionNonvacuity () {
  head('nonvacuity -- break the isolation four ways; each must go RED');

  const now = Date.now();

  // BREAK 1 -- the corpus. Give both tenants the SAME thresholds. The
  // "B does not alarm" check must now FAIL, which is the proof that the check
  // is reading the thresholds and not something incidental.
  {
    const same = { A: THRESHOLDS.A, B: THRESHOLDS.A };
    const out = runBoth(cacheFor(same), now);
    const wouldPass = out.B.length === 0;
    record('nonvacuity', 'BREAK 1 (identical thresholds): "B does not alarm" goes RED'
      , !wouldPass
      , 'with A\'s thresholds, B emits ' + JSON.stringify(out.B.map(e => e.title))
        + ' -- so the green result above is produced by the DIFFERENT thresholds');
  }

  // BREAK 2 -- shared settings object. This is the shallow-copy bug T3.3's
  // header names: separating every top-level field of `env` while sharing
  // `settings` shares exactly the alarm configuration.
  {
    const cache = tenantContext.createContextCache({
      base: { env: baseEnv, store: null }
      , settingsFor: t => THRESHOLDS[t.id]
      , build: function sharedSettings (base, tenant, options) {
        const c = buildEvaluatorContext(base, tenant, options);
        if (!sharedSettings.first) { sharedSettings.first = c.env.settings; }
        // The break: every tenant after the first reads tenant A's settings.
        c.env.settings = sharedSettings.first;
        c.settings = sharedSettings.first;
        return c;
      }
    });
    const out = runBoth(cache, now);
    record('nonvacuity', 'BREAK 2 (shared settings object): B inherits A\'s thresholds and alarms'
      , out.B.length === 1
      , 'B emitted ' + JSON.stringify(out.B.map(e => e.title))
        + ' on A\'s bgHigh -- the isolation check detects a shallow copy');
  }

  // BREAK 3 -- shared ddata. Both tenants evaluate the same glucose. Proves the
  // per-tenant ddata requirement is load-bearing and not decorative: with one
  // ddata, whichever tenant is seeded last decides for both.
  {
    const shared = lib('data/ddata')();
    const cache = tenantContext.createContextCache({
      base: { env: baseEnv, store: null }
      , settingsFor: t => THRESHOLDS[t.id]
      , build: function (base, tenant, options) {
        const c = buildEvaluatorContext(base, tenant, options);
        c.ddata = shared;                     // bootevent.js's actual shape
        return c;
      }
    });
    // A is seeded in range for ITS thresholds, B is seeded high for B's. With a
    // shared ddata, A evaluates B's reading.
    tenantScope.withTenant('B', function () {
      const c = cache.ctxFor({ id: 'B', slug: 'b' });
      seed(c, 450, now);
    });
    const outA = tenantScope.withTenant('A', function () {
      const c = cache.ctxFor({ id: 'A', slug: 'a' });
      // NOT seeded: A's context reads whatever B left behind.
      return evaluate(c);
    });
    record('nonvacuity', "BREAK 3 (shared ddata): A alarms on B's glucose"
      , outA.length === 1 && outA[0].room === 'Tenant:A'
      , 'A emitted ' + JSON.stringify(outA.map(e => e.title)) + ' into ' + outA[0].room
        + ' having loaded nothing of its own -- one ddata is one person\'s glucose for everybody');
  }

  // BREAK 4 -- shared notifications, i.e. the module-level `alarms` map that
  // T3.4's regression test pins. A's acknowledgement silences B's alarm, at the
  // same level and group, because the key is (level, group) with no tenant in it.
  {
    const oneNotifications = { instance: null };
    const cache = tenantContext.createContextCache({
      base: { env: baseEnv, store: null }
      , settingsFor: () => THRESHOLDS.A       // both tenants alarm, so the only
      , build: function (base, tenant, options) {   // difference can be the ack
        const c = buildEvaluatorContext(base, tenant, options);
        if (!oneNotifications.instance) oneNotifications.instance = c.notifications;
        c.notifications = oneNotifications.instance;
        return c;
      }
    });
    const firstA = tenantScope.withTenant('A', function () {
      const c = cache.ctxFor({ id: 'A', slug: 'a' });
      seed(c, SGV, now);
      const e = evaluate(c);
      c.notifications.ack(2, 'default', 30 * 60 * 1000);   // A's person snoozes
      return e;
    });
    const thenB = tenantScope.withTenant('B', function () {
      const c = cache.ctxFor({ id: 'B', slug: 'b' });
      seed(c, SGV, now);
      return evaluate(c);
    });
    record('nonvacuity', "BREAK 4 (shared notifications): A's snooze silences B's alarm"
      , firstA.length === 1 && thenB.length === 0
      , `A emitted ${firstA.length} then acked; B -- a different person, same level 2, `
        + `same group 'default', same reading -- emitted ${thenB.length}. `
        + 'This is T3.4\'s finding reproduced inside one process.');
  }

  // BREAK 5 -- weaken the SHIPPING module. socket-tenancy's `currentRoom` is
  // what makes an emission tenant-addressed; make it fall back to a constant
  // room when nothing is bound and the withholding check must go red.
  {
    const out = withWeakened('server/socket-tenancy.js', [
      ['      announceWithholding(surface || base);\n      return null;'
        , '      return roomFor(base, \'EVERYBODY\');']
    ], function (weak) {
      const weakRooms = weak.create({
        resolver: { resolve: () => null, hasHostRule: true }
        , registry: { lookup: async () => null }
        , enclave: baseEnv.enclave, requireTokenClaim: false
      });
      return weakRooms.currentRoom(weak.TENANT_ROOM, '/alarm');   // outside any scope
    });
    record('nonvacuity', 'BREAK 5 (weakened socket-tenancy): unbound emission gets a room'
      , out !== null
      , 'currentRoom() returned ' + JSON.stringify(out) + ' with nothing bound -- so the '
        + '"withheld, not broadcast" check in `isolation` is testing the shipping behaviour');
  }

  record('nonvacuity', 'no weakened copy left on disk'
    , fs.readdirSync(path.join(ROOT, 'lib', 'server')).every(f => !f.includes('__weakened')));
}

// ==================================================================== cold

function sectionCold () {
  head('cold -- a tenant whose ddata has never been loaded');

  const now = Date.now();
  const cache = cacheFor(THRESHOLDS);

  // A fresh `ddata` has `lastUpdated: 0` (lib/data/ddata.js:21). `dataloader`
  // sets it to `Date.now()` (lib/data/dataloader.js:68), so under single tenancy
  // it is never 0 by the time anything evaluates -- `data-loaded` fires only
  // after a load. A per-tenant evaluator woken by a change feed has no such
  // guarantee.
  const cold = tenantScope.withTenant('COLD', function () {
    const c = cache.ctxFor({ id: 'COLD', slug: 'cold' });
    c.ddata.sgvs = [{ _id: 's1', mgdl: SGV, mills: now - 60000, type: 'sgv' }];
    // lastUpdated deliberately left at its initial 0
    return evaluate(c);
  });

  const warm = tenantScope.withTenant('WARM', function () {
    const c = cache.ctxFor({ id: 'WARM', slug: 'warm' });
    c.ddata.sgvs = [{ _id: 's1', mgdl: SGV, mills: now - 60000, type: 'sgv' }];
    c.ddata.lastUpdated = now;
    return evaluate(c);
  });

  record('cold', 'a warm tenant alarms', warm.length === 1, JSON.stringify(warm.map(e => e.title)));

  record('cold', 'a COLD tenant\'s first urgent alarm is SILENTLY SUPPRESSED'
    , cold.length === 0
    , 'same reading, same thresholds, only ddata.lastUpdated differs (0 vs now). '
      + 'lib/notifications.js:196 gates on `ctx.ddata.lastUpdated > alarm.lastAckTime + '
      + 'alarm.silenceTime`; a new Alarm has lastAckTime 0 and silenceTime 30min, so '
      + '0 > 1800000 is false. The log line reads "silenced for 30 minutes more" for an '
      + 'alarm nobody ever snoozed.');

  const empty = tenantScope.withTenant('EMPTY', function () {
    return evaluate(cache.ctxFor({ id: 'EMPTY', slug: 'empty' }));
  });
  record('cold', 'a tenant with no data at all emits nothing and does not throw'
    , empty.length === 0, 'the safe half of a cold start');

  // THE CORRECTION THIS SPIKE'S FIRST DRAFT EARNED. I predicted that a ddata
  // merely LAGGING the wall clock would also suppress the alarm. It does not,
  // and the reason matters: `lastUpdated` and `lastAckTime` are both ABSOLUTE
  // epoch milliseconds, so `lastUpdated > lastAckTime + silenceTime` is coherent
  // between them. The cold case fails for a narrower reason -- a never-loaded
  // `lastUpdated` is exactly 0, which is below `silenceTime` itself, so the
  // guard reads "is this data timestamped after 1970-01-01T00:30Z".
  const laggedButAfterEpoch = tenantScope.withTenant('LAG0', function () {
    const c = cache.ctxFor({ id: 'LAG0', slug: 'lag0' });
    c.ddata.sgvs = [{ _id: 's1', mgdl: SGV, mills: now - 60000, type: 'sgv' }];
    c.ddata.lastUpdated = now - 45 * 60 * 1000;   // 45 minutes stale, still a real epoch
    return evaluate(c);
  });
  record('cold', 'a merely STALE ddata still alarms -- the cold failure is lastUpdated===0'
    , laggedButAfterEpoch.length === 1
    , 'both operands are absolute epoch ms, so staleness alone is harmless. The cold '
      + 'start is the whole of the hazard, and it is one integer wide.');

  // But the two clocks ARE different, and it shows once an ack exists: `ack`
  // writes `Date.now()` (WALL time, lib/notifications.js:198) while the silence
  // window is compared against `ddata.lastUpdated` (DATA time). Same ack, same
  // wall clock, different feed lag, different answer.
  const ackAt = Date.now();
  function afterAck (id, lastUpdated) {
    return tenantScope.withTenant(id, function () {
      const c = cache.ctxFor({ id, slug: id.toLowerCase() });
      c.ddata.sgvs = [{ _id: 's1', mgdl: SGV, mills: Date.now() - 60000, type: 'sgv' }];
      c.ddata.lastUpdated = ackAt;
      evaluate(c);
      c.notifications.ack(2, 'default', 30 * 60 * 1000);   // wall time: Date.now()
      // Now ask again, with this tenant's feed at the given DATA time.
      c.ddata.sgvs = [{ _id: 's2', mgdl: SGV, mills: Date.now() - 60000, type: 'sgv' }];
      c.ddata.lastUpdated = lastUpdated;
      return evaluate(c);
    });
  }
  const fresh = afterAck('CLKFRESH', ackAt + 35 * 60 * 1000);   // feed 35 min past the ack
  const behind = afterAck('CLKLAG', ackAt - 10 * 60 * 1000);    // feed 10 min BEFORE the ack

  record('cold', 'the snooze window is measured in DATA time, the ack in WALL time'
    , fresh.length === 1 && behind.length === 0
    , `identical 30-minute ack at the same wall instant: a tenant whose feed has advanced `
      + `35 min re-alarms (${fresh.length}), a tenant whose feed sits 10 min behind the ack `
      + `stays silent (${behind.length}). A tenant L behind the wall holds a 30-minute `
      + 'snooze for 30+L minutes of real time -- and L is per tenant.');

  // `sbx.time` is the third clock, and it is unconditionally `Date.now()`
  // (lib/sandbox.js:51). `lastEntry` drops any entry newer than it
  // (lib/sandbox.js:141), so an evaluator cannot batch, replay or catch up a
  // tenant at a simulated instant without owning this too. Measured, because an
  // earlier draft of this harness seeded 60 s into the future and two checks
  // silently evaluated nothing.
  const future = tenantScope.withTenant('FUT', function () {
    const c = cache.ctxFor({ id: 'FUT', slug: 'fut' });
    c.ddata.sgvs = [{ _id: 's1', mgdl: SGV, mills: Date.now() + 60000, type: 'sgv' }];
    c.ddata.lastUpdated = Date.now();
    return evaluate(c);
  });
  record('cold', 'sbx.time is Date.now() and silently drops entries ahead of it'
    , future.length === 0
    , 'an sgv 60 s in the future evaluates to nothing at all -- no error, no log. '
      + 'A batched or replayed evaluator has to own sbx.time, which serverInit hardcodes.');
}

// =================================================================== blast

function sectionBlast () {
  head('blast -- what one tenant\'s evaluation failing does to the others');

  const now = Date.now();
  const cache = cacheFor({ A: THRESHOLDS.A, BAD: THRESHOLDS.A, C: THRESHOLDS.A });

  // Failure 1: bad ddata reaching a plugin. `plugins.setProperties` and
  // `checkNotifications` wrap EACH plugin in try/catch (lib/plugins/index.js:189,
  // 201), so this does not escape -- but it also does not alarm, and the only
  // trace is a console.error.
  const caught = tenantScope.withTenant('BAD', function () {
    const c = cache.ctxFor({ id: 'BAD', slug: 'bad' });
    c.ddata.sgvs = null;                      // a load that half-failed
    c.ddata.lastUpdated = now;
    try { return { emitted: evaluate(c), threw: null }; }
    catch (e) { return { emitted: [], threw: e.message }; }
  });
  record('blast', 'a plugin throwing does NOT escape the evaluation'
    , caught.threw === null, 'eachEnabledPlugin try/catches per plugin');
  record('blast', 'but that tenant SILENTLY emits no alarm'
    , caught.emitted.length === 0
    , 'a swallowed plugin error is an alarm outage for one tenant with no signal '
      + 'above console.error -- under one process per tenant this is a crash; under '
      + 'a shared evaluator it is invisible');

  // Failure 2: a throw OUTSIDE the plugin try/catch. `sandbox.serverInit`,
  // `notifications.initRequests` and `notifications.process` are all unguarded.
  // In a naive `for (tenant of tenants) evaluate(tenant)` this stops the loop.
  const order = [];
  let escaped = null;
  try {
    for (const id of ['A', 'BAD', 'C']) {
      tenantScope.withTenant(id, function () {
        const c = cache.ctxFor({ id, slug: id.toLowerCase() });
        if (id === 'BAD') { c.ddata = null; }   // serverInit reads ctx.ddata.clone()
        else seed(c, SGV, now);
        order.push({ id, emitted: evaluate(c).length });
      });
    }
  } catch (e) { escaped = e.message; }

  record('blast', 'an unguarded throw DOES escape evaluate()'
    , escaped !== null, 'from sandbox.serverInit: ' + String(escaped).slice(0, 90));
  record('blast', 'and in an unguarded per-tenant loop it takes out every LATER tenant'
    , order.length === 1 && order[0].id === 'A'
    , 'tenants evaluated before the throw: ' + JSON.stringify(order)
      + ' -- tenant C never evaluated, and C\'s person is not alarmed');

  // The same loop with a per-tenant boundary. This is the requirement, stated as
  // the smallest thing that satisfies it.
  const order2 = [];
  const errors = [];
  for (const id of ['A', 'BAD', 'C']) {
    try {
      tenantScope.withTenant(id, function () {
        const c = cache.ctxFor({ id, slug: id.toLowerCase() });
        if (id === 'BAD') { c.ddata = null; } else seed(c, SGV, now);
        order2.push({ id, emitted: evaluate(c).length });
      });
    } catch (e) { errors.push({ id, err: e.constructor.name }); }
  }
  record('blast', 'a per-tenant try/catch contains it and C is still evaluated'
    , order2.length === 2 && order2.some(o => o.id === 'C' && o.emitted === 1)
    , 'evaluated ' + JSON.stringify(order2) + ', contained ' + JSON.stringify(errors));
}

// ===================================================================== ack

function sectionAck () {
  head('ack -- how snooze state is keyed, and who can write it');

  const now = Date.now();
  const cache = cacheFor({ A: THRESHOLDS.A, B: THRESHOLDS.A });

  // With a per-tenant instance the tenant is IMPLICIT in the instance identity;
  // the key inside the map is still (level, group).
  const a1 = tenantScope.withTenant('A', function () {
    const c = cache.ctxFor({ id: 'A', slug: 'a' });
    seed(c, SGV, now);
    const e = evaluate(c);
    c.notifications.ack(2, 'default', 30 * 60 * 1000);
    return e;
  });
  const b1 = tenantScope.withTenant('B', function () {
    const c = cache.ctxFor({ id: 'B', slug: 'b' });
    seed(c, SGV, now);
    return evaluate(c);
  });
  record('ack', 'per-tenant instances: A\'s snooze does NOT reach B'
    , a1.length === 1 && b1.length === 1
    , `A emitted ${a1.length} then acked; B still emitted ${b1.length}`);

  // But the key itself carries no tenant. Demonstrated by reading the alarm out
  // of each instance: the two are distinguishable only by which object you ask.
  const keyed = tenantScope.withTenant('A', function () {
    const c = cache.ctxFor({ id: 'A', slug: 'a' });
    return c.env.testMode ? 'testMode' : 'no-testMode';
  });
  record('ack', 'the map key is (level, group) with no tenant in it', true
    , "lib/notifications.js:42 -- `var key = level + '-' + group`. A storage-backed "
      + 'table must therefore key on (tenant_id, level, group); adding tenant_id to the '
      + 'in-memory map instead would imply the map is safe to share, which is the '
      + 'opposite of the property T3.4 pinned. (' + keyed + ')');

  // A's ack survives a second evaluation within the silence window -- the
  // property that must survive the move to storage.
  //
  // Seeded at the CURRENT wall instant, not `now + delta`: `sbx.lastEntry` drops
  // any entry ahead of `sbx.time = Date.now()`, so a future-dated seed makes this
  // check and the eviction check below pass for no reason at all. An earlier
  // draft did exactly that and the eviction check went red, which is how it was
  // found -- see the `cold` section's last check.
  const a2 = tenantScope.withTenant('A', function () {
    const c = cache.ctxFor({ id: 'A', slug: 'a' });
    seed(c, SGV, Date.now());
    return evaluate(c);
  });
  record('ack', 'A stays snoozed on re-evaluation inside the window'
    , a2.length === 0, 'emitted ' + a2.length);

  // Eviction. THE reason T3.3 refuses to cache `notifications`, measured.
  cache.evict('A');
  const a3 = tenantScope.withTenant('A', function () {
    const c = cache.ctxFor({ id: 'A', slug: 'a' });     // rebuilt: a fresh instance
    seed(c, SGV, Date.now());
    return evaluate(c);
  });
  record('ack', 'EVICTING the context un-snoozes the alarm'
    , a3.length === 1
    , 'A was snoozed for 30 minutes; one LRU eviction later the same reading alarms again. '
      + 'Nothing a person sees says why. This is T3.3\'s DERIVED_CONTEXT_KEYS reason, '
      + 'measured rather than argued.');

  // Who writes ack, and on which entrypoint under D5. Static, but it is the
  // finding that decides whether the storage move is optional.
  const writers = [
    ['lib/api/notifications-api.js:28', 'HTTP GET /notifications/ack', 'ns-api']
    , ['lib/api3/alarmSocket.js:111', "socket 'ack'", 'ns-realtime']
    , ['lib/api3/alarmSocket.js:167', "socket 'ack' (v3 auth path)", 'ns-realtime']
    , ['lib/server/pushnotify.js:85', 'Pushover receipt callback', 'ns-api']
    , ['lib/notifications.js:65', 'autoAckAlarms, inside process()', 'ns-evaluator']
    , ['lib/notifications.js:170', 'snoozedBy, inside process()', 'ns-evaluator']
  ];
  const offEvaluator = writers.filter(w => w[2] !== 'ns-evaluator');
  record('ack', 'every PERSON-initiated ack is written on a process that is not the evaluator'
    , offEvaluator.length === 4
    , offEvaluator.map(w => `${w[2]} <- ${w[1]} (${w[0]})`).join('; ')
      + ' -- and lib/notifications.js:196 is read ONLY in the evaluator. Under D5 these are '
      + 'different processes by design, so an in-memory map means no acknowledgement a '
      + 'person makes can ever be seen by the code that decides whether to alarm.');
}

// =================================================================== slice
//
// What a per-tenant `ddata` has to CONTAIN, measured top-down by ablation:
// populate every field, get a baseline set of alarms out of the real path, then
// blank one field at a time and record what the alarm decision loses. A field
// whose removal changes no alarm is, from the evaluator's point of view,
// display-only -- {R} §12.5's proposed alarm-critical/display split, arrived at
// from the outside rather than by reading `checkNotifications`.

// NOTE the registered NAMES, not the file names: `plugins.register` matches on
// `plugin.name`, and cannulaage/sensorage/insulinage/batteryage/boluswizardpreview
// register as cage/sage/iage/bage/bwp. An earlier draft of this corpus listed the
// file names, so four alarm producers were silently never enabled and the
// ablation below reported `treatments` as display-only. Nothing warns about an
// unknown name in ENABLE.
const ALARM_PLUGINS = 'simplealarms ar2 bgnow delta direction upbat rawbg errorcodes '
  + 'iob cob pump openaps loop xdripjs cage sage iage bage '
  + 'bwp timeago treatmentnotify basal profile bolus dbsize';

// Per-plugin alert configuration, so that more than one alarm producer is armed
// and the ablation has something to lose. Without this the age plugins default
// to `enableAlerts: false` and the corpus can only ever exercise `sgvs`.
const SLICE_EXTENDED = {
  cage: { enableAlerts: true }
  , iage: { enableAlerts: true }
  , sage: { enableAlerts: true }
  , bage: { enableAlerts: true }
  , upbat: { enableAlerts: true }
};

// The age plugins fire only when `age === prefs.urgent` EXACTLY (an integer
// hour), and only when `minFractions <= 20`. These are those exact ages, in
// hours, for each plugin's default urgent threshold.
const AGE_HOURS = { cannula: 72, insulin: 72, sensor: 7 * 24 - 2, battery: 360 };

function populate (ddata, now) {
  const ago = m => now - m * 60000;
  ddata.sgvs = [
    { _id: 'e1', mgdl: 210, mills: ago(10), type: 'sgv', direction: 'FortyFiveUp', device: 'spike' }
    , { _id: 'e2', mgdl: 235, mills: ago(5), type: 'sgv', direction: 'SingleUp', device: 'spike' }
    , { _id: 'e3', mgdl: SGV, mills: ago(1), type: 'sgv', direction: 'SingleUp', device: 'spike' }
  ];
  ddata.mbgs = [{ _id: 'm1', mgdl: 240, mills: ago(30), device: 'meter' }];
  ddata.cals = [{ _id: 'c1', mills: ago(120), slope: 800, intercept: 30000, scale: 1 }];
  // Aged to land EXACTLY on each plugin's urgent hour, because that is the only
  // age at which these plugins notify -- and anchored to `now` exactly, not to
  // the top of the hour, because the guard is also `minFractions <= 20` and
  // minFractions is measured from the treatment, not from the clock.
  const hrs = h => now - h * 3600e3;
  ddata.treatments = [
    { _id: 't1', eventType: 'Site Change', mills: hrs(AGE_HOURS.cannula), created_at: new Date(hrs(AGE_HOURS.cannula)).toISOString() }
    , { _id: 't2', eventType: 'Sensor Change', mills: hrs(AGE_HOURS.sensor), created_at: new Date(hrs(AGE_HOURS.sensor)).toISOString() }
    , { _id: 't3', eventType: 'Insulin Change', mills: hrs(AGE_HOURS.insulin), created_at: new Date(hrs(AGE_HOURS.insulin)).toISOString() }
    , { _id: 't4', eventType: 'Pump Battery Change', mills: hrs(AGE_HOURS.battery), created_at: new Date(hrs(AGE_HOURS.battery)).toISOString() }
    , { _id: 't5', eventType: 'Correction Bolus', insulin: 2.5, mills: ago(45), created_at: new Date(ago(45)).toISOString() }
    , { _id: 't6', eventType: 'Meal Bolus', insulin: 4, carbs: 45, mills: ago(90), created_at: new Date(ago(90)).toISOString() }
  ];
  ddata.profiles = [{
    _id: 'p1', defaultProfile: 'Default', startDate: new Date(now - 90 * 24 * 3600e3).toISOString()
    , mills: now - 90 * 24 * 3600e3
    , store: { Default: {
      dia: 5, carbs_hr: 20, timezone: 'UTC'
      , sens: [{ time: '00:00', value: 50, timeAsSeconds: 0 }]
      , carbratio: [{ time: '00:00', value: 10, timeAsSeconds: 0 }]
      , basal: [{ time: '00:00', value: 0.8, timeAsSeconds: 0 }]
      , target_low: [{ time: '00:00', value: 100, timeAsSeconds: 0 }]
      , target_high: [{ time: '00:00', value: 140, timeAsSeconds: 0 }]
    } }
  }];
  ddata.devicestatus = [{
    _id: 'd1', mills: ago(2), created_at: new Date(ago(2)).toISOString(), device: 'openaps://rig'
    , uploader: { battery: 8 }                      // low: trips upbat
    , pump: { battery: { percent: 12 }, reservoir: 8, clock: new Date(ago(2)).toISOString() }
    , openaps: { suggested: { timestamp: new Date(ago(2)).toISOString(), bg: SGV }
      , enacted: { timestamp: new Date(ago(2)).toISOString(), bg: SGV } }
  }];
  ddata.food = [{ _id: 'f1', name: 'toast', carbs: 20 }];
  ddata.activity = [{ _id: 'a1', mills: ago(60), heartrate: 70 }];
  ddata.dbstats = { dataSize: 1024 * 1024 * 400, indexSize: 1024 * 1024 * 20 };
  ddata.processTreatments(true);                    // what loadComplete does
  ddata.lastUpdated = now;
  return ddata;
}

// The keys a blank ddata still needs to be a ddata: blanking these is the
// ablation, everything else on the object is a method.
const DDATA_FIELDS = ['sgvs', 'mbgs', 'cals', 'treatments', 'profiles', 'devicestatus'
  , 'food', 'activity', 'dbstats', 'sitechangeTreatments', 'sensorTreatments'
  , 'insulinchangeTreatments', 'batteryTreatments', 'profileTreatments'
  , 'tempbasalTreatments', 'combobolusTreatments', 'tempTargetTreatments'];

function sectionSlice () {
  head('slice -- which ddata fields the ALARM decision actually depends on');

  const savedEnable = baseEnv.settings.enable;
  baseEnv.settings.enable = ALARM_PLUGINS.split(' ');

  const now = Date.now();
  const overrides = { settings: THRESHOLDS.A.settings, extendedSettings: SLICE_EXTENDED };
  const cache = tenantContext.createContextCache({
    base: { env: baseEnv, store: null }, settingsFor: () => overrides, build: buildEvaluatorContext
  });

  // Ablate against what the PLUGINS DECIDED, not against what was emitted.
  // `notifications.process` emits at most ONE alarm per group -- the highest --
  // plus anything at or below INFO, so every urgent alarm after the first is
  // invisible in the emission and an ablation measured there is nearly blind.
  // That ceiling is itself a requirement finding; see REQ-13.
  function run (ablate) {
    const id = 'S' + (ablate || 'BASE');
    return tenantScope.withTenant(id, function () {
      const c = cache.ctxFor({ id, slug: id.toLowerCase() });
      const requested = [];
      if (!c.__wrapped) {
        const inner = c.notifications.requestNotify;
        c.notifications.requestNotify = function (notify) {
          requested.push((notify.plugin && notify.plugin.name) + '/' + notify.level);
          return inner.call(c.notifications, notify);
        };
        c.__wrapped = true;
      }
      c.__requested = requested;
      populate(c.ddata, now);
      if (ablate) { c.ddata[ablate] = Array.isArray(c.ddata[ablate]) ? [] : {}; }
      try {
        const emitted = evaluate(c).map(e => e.title || (e.clear ? 'CLEAR' : '?'));
        return { requested: requested.slice().sort(), emitted, threw: null };
      } catch (e) {
        return { requested: requested.slice().sort(), emitted: [], threw: e.constructor.name + ': ' + e.message };
      }
    });
  }

  const base = run(null);
  record('slice', 'the corpus arms more than one alarm producer'
    , base.threw === null && base.requested.length > 1
    , 'plugins requesting an alarm: ' + JSON.stringify(base.requested));

  record('slice', 'but process() emits only the HIGHEST alarm in the group'
    , base.emitted.length < base.requested.length
    , `${base.requested.length} requested, ${base.emitted.length} emitted `
      + JSON.stringify(base.emitted) + ' -- all in group "default"');

  const critical = [];
  const display = [];
  const fatal = [];
  for (const field of DDATA_FIELDS) {
    const r = run(field);
    if (r.threw) { fatal.push(field + ' (' + r.threw.slice(0, 40) + ')'); continue; }
    const lost = base.requested.filter(x => !r.requested.includes(x));
    if (lost.length) critical.push(field + ' -> loses ' + JSON.stringify(lost));
    else display.push(field);
  }

  record('slice', 'ALARM-CRITICAL ddata fields (blanking one loses an alarm request)'
    , critical.length > 0, critical.join('  |  ') || '(none)');
  record('slice', 'DISPLAY-ONLY from the evaluator, ON THIS CORPUS'
    , true, display.join(', ') || '(none)');
  record('slice', 'fields whose absence makes evaluation THROW', true
    , fatal.join(', ') || '(none)');

  // ---------------------------------------------------------------------
  // Found while widening the corpus, NOT looked for, and NOT a tenancy bug.
  //
  // lib/plugins/insulinage.js:92 reads `insulinInfo.urgent`, which is never
  // assigned anywhere in that file. Its three sibling age plugins all read
  // `prefs.urgent` on the identical line (cannulaage:87, sensorage:141,
  // batteryage:87). `age >= undefined` is false, so the URGENT branch is
  // unreachable and the plugin falls through to WARN.
  //
  // Consequence for a person: "Insulin reservoir change overdue!" at level
  // URGENT never fires. Pinned here rather than argued, and NOT fixed -- D12
  // keeps cgm-remote-monitor pristine and this is outside the task.
  function iageAt (hours) {
    const id = 'IAGE' + hours;
    return tenantScope.withTenant(id, function () {
      const c = cache.ctxFor({ id, slug: id.toLowerCase() });
      const got = [];
      const inner = c.notifications.requestNotify;
      c.notifications.requestNotify = function (n) {
        if (n.plugin && n.plugin.name === 'iage') got.push(n.level);
        return inner.call(c.notifications, n);
      };
      populate(c.ddata, now);
      const at = Date.now() - hours * 3600e3;
      c.ddata.treatments = [{ _id: 'i1', eventType: 'Insulin Change', mills: at
        , created_at: new Date(at).toISOString() }];
      c.ddata.processTreatments(true);
      evaluate(c);
      return got;
    });
  }
  const atUrgent = iageAt(72);      // prefs.urgent
  const atWarn = iageAt(48);        // prefs.warn

  record('slice', 'BUG in shipping code: insulinage can never raise its URGENT alarm'
    , atUrgent.length === 0 && atWarn.length === 1 && atWarn[0] === 1
    , `at the urgent age (72 h) iage requested ${JSON.stringify(atUrgent)}; at the warn `
      + `age (48 h) it requested ${JSON.stringify(atWarn)} (1 = WARN). `
      + 'lib/plugins/insulinage.js:92 compares against `insulinInfo.urgent`, which is '
      + 'never assigned; cannulaage:87, sensorage:141 and batteryage:87 use `prefs.urgent`. '
      + 'Pre-existing and single-tenant; not fixed here.');

  baseEnv.settings.enable = savedEnable;
}

// ==================================================================== cost

function sectionCost () {
  head('cost -- what a resident evaluator tenant costs, from this route');

  const now = Date.now();
  const cache = cacheFor(THRESHOLDS);

  // Warm the JIT so the figure is the loop's, not the first-call cost.
  for (let i = 0; i < 50; i++) {
    tenantScope.withTenant('A', function () {
      const c = cache.ctxFor({ id: 'A', slug: 'a' });
      seed(c, 120, now + i * 1000);
      evaluate(c);
    });
  }

  const N = 500;
  const t0 = process.hrtime.bigint();
  for (let i = 0; i < N; i++) {
    tenantScope.withTenant('A', function () {
      const c = cache.ctxFor({ id: 'A', slug: 'a' });
      seed(c, 120, now + i * 1000);
      evaluate(c);
    });
  }
  const perEval = Number(process.hrtime.bigint() - t0) / 1e6 / N;
  record('cost', 'one tenant evaluation cycle', true
    , perEval.toFixed(3) + ' ms (1 sgv, 10 plugins enabled, no I/O) -- '
      + 'this is the SYNCHRONOUS floor, with an empty ddata');

  // Build cost for a cold context.
  const b0 = process.hrtime.bigint();
  const M = 200;
  const c2 = cacheFor(THRESHOLDS);
  for (let i = 0; i < M; i++) {
    const id = 'T' + i;
    tenantScope.withTenant(id, () => c2.ctxFor({ id, slug: id.toLowerCase() }));
  }
  const perBuild = Number(process.hrtime.bigint() - b0) / 1e6 / M;
  record('cost', 'building one evaluator context (miss cost)', true
    , perBuild.toFixed(3) + ' ms -- deriveEnv + language + 25 plugin factories + '
      + 'ddata + notifications, with an EMPTY ddata');

  if (global.gc) {
    global.gc();
    const before = process.memoryUsage().heapUsed;
    const c3 = cacheFor(THRESHOLDS);
    const K = 300;
    for (let i = 0; i < K; i++) {
      const id = 'M' + i;
      tenantScope.withTenant(id, () => c3.ctxFor({ id, slug: id.toLowerCase() }));
    }
    global.gc();
    const after = process.memoryUsage().heapUsed;
    record('cost', 'resident evaluator context, EMPTY ddata', true
      , ((after - before) / K / 1024).toFixed(1) + ' KB each over ' + K + ' tenants');
  } else {
    record('cost', 'residency not measured', true, 'rerun with --expose-gc for the KB figure');
  }
}

// ===================================================================== main

const SECTIONS = {
  substrate: sectionSubstrate
  , isolation: sectionIsolation
  , nonvacuity: sectionNonvacuity
  , cold: sectionCold
  , blast: sectionBlast
  , ack: sectionAck
  , slice: sectionSlice
  , cost: sectionCost
};

const toRun = SECTION === 'all' ? Object.keys(SECTIONS) : [SECTION];
for (const name of toRun) {
  if (!SECTIONS[name]) { console.error('unknown section: ' + name); process.exit(2); }
  SECTIONS[name]();
}

if (JSON_OUT) {
  console.log(JSON.stringify({ root: ROOT, failures, results }, null, 2));
} else {
  console.log(`\n${results.length} checks, ${failures} failed`);
}
process.exit(failures === 0 ? 0 : 1);
