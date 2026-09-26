'use strict';
/*
 * BF-121 (#8185) re-send harness: does a change to the treatment match key
 * keep every client's re-sends and edits working, and which same-time entries
 * does it keep apart?
 *
 * Usage:
 *   node same-time-resend-shapes.js <port> <mongodb uri> <label>=<tree> [<label>=<tree> ...]
 *   e.g. node same-time-resend-shapes.js 17902 mongodb://127.0.0.1:27901/r121 \
 *          off=externals/work/crm-r2-121-base fix=externals/work/crm-r2-fix-121
 *
 * For each tree: boots its lib/server/server.js against the given database
 * (dropped first; API_SECRET set, AUTH_DEFAULT_ROLES=denied), writes each
 * shape at its own hour through the client's real path (v1 POST/PUT, v3 POST,
 * socket dbAdd), and reads the stored documents back with the driver. The
 * server is started in its own process group and killed by its PID.
 * Then prints one table: a row per shape, a column per tree.
 *
 * The shapes are synthetic records in each client's upload shape (read from
 * the client sources, see the brief/register BF-121); no client was run.
 *
 * Outcome words:
 *   deduped    a re-send left the expected number of records
 *   updated    a re-send with changed values left one record with the new values
 *   kept 2     two distinct entries at the same time are two records
 *   MERGED     fewer records than distinct entries (one entry lost)
 *   DUPLICATE  a re-send or edit added a record
 *   STALE      a re-sent edit left the old values
 *
 * Exit status: 0 when every tree answered every write and stayed live,
 * 2 otherwise, 3 on a harness error. It does not judge the outcomes: read the
 * table. No data leaves the machine.
 */
const path = require('path');
const crypto = require('crypto');
const { spawn } = require('child_process');

const port = Number(process.argv[2] || 17902);
const mongoUri = process.argv[3] || 'mongodb://127.0.0.1:27901/r121_resend';
const trees = process.argv.slice(4).map((a) => {
  const i = a.indexOf('=');
  return { label: a.slice(0, i), root: path.resolve(a.slice(i + 1)) };
});
if (trees.length === 0) { console.error('give at least one <label>=<tree>'); process.exit(3); }

const BASE = `http://127.0.0.1:${port}`;
const iso = (ms) => new Date(ms).toISOString();
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const uuid = () => crypto.randomUUID();
const hex24 = () => crypto.randomBytes(12).toString('hex');

function harness (root) {
  const req = (m) => require(path.join(root, 'node_modules', m));
  const { MongoClient } = req('mongodb');
  const ioClient = req('socket.io-client');
  const SECRET = 'probe-secret-' + crypto.randomBytes(6).toString('hex');
  const HASH = crypto.createHash('sha1').update(SECRET).digest('hex');
  const h = { server: null, ok: true, root };

  h.http = async function (method, p, body, headers) {
    const r = await fetch(BASE + p, {
      method,
      headers: Object.assign({ 'content-type': 'application/json', 'api-secret': HASH }, headers || {}),
      body: body === undefined ? undefined : JSON.stringify(body)
    });
    let json = null; try { json = await r.json(); } catch (e) { /* not json */ }
    return { status: r.status, json };
  };
  h.check = function (r) {
    if (!(r.status >= 200 && r.status < 300)) { h.ok = false; console.log('  write answered', r.status, JSON.stringify(r.json)); }
    return r;
  };
  h.boot = async function () {
    const db = await MongoClient.connect(mongoUri);
    await db.db().dropDatabase();
    await db.close();
    h.server = spawn(process.execPath, ['lib/server/server.js'], {
      cwd: root, detached: true, stdio: ['ignore', 'ignore', 'ignore'],
      env: Object.assign({}, process.env, {
        MONGODB_URI: mongoUri, PORT: String(port), HOSTNAME: '127.0.0.1', INSECURE_USE_HTTP: 'true',
        NODE_ENV: 'production', API_SECRET: SECRET, AUTH_DEFAULT_ROLES: 'denied',
        ENABLE: 'careportal', DISPLAY_UNITS: 'mg/dl'
      })
    });
    for (let i = 0; i < 120; i++) {
      try { const r = await h.http('GET', '/api/v1/status.json'); if (r.status === 200) return; } catch (e) { /* booting */ }
      await sleep(500);
    }
    throw new Error('server did not answer on ' + BASE);
  };
  h.stop = function () {
    if (h.server && h.server.pid) { try { process.kill(-h.server.pid, 'SIGTERM'); } catch (e) { /* gone */ } }
  };
  h.v3Token = async function () {
    const name = 'probe' + Date.now();
    const c = await h.http('POST', '/api/v2/authorization/subjects', { name, roles: ['admin'] });
    if (c.status !== 200) throw new Error('subject create ' + c.status);
    for (let i = 0; i < 20; i++) {
      const l = await h.http('GET', '/api/v2/authorization/subjects');
      const s = (l.json || []).find((x) => x.name === name);
      if (s && s.accessToken) {
        const j = await h.http('GET', '/api/v2/authorization/request/' + s.accessToken);
        if (j.status === 200 && j.json && j.json.token) return j.json.token;
      }
      await sleep(250);
    }
    throw new Error('no access token');
  };
  h.socketAdd = function (docs) {
    return new Promise((resolve, reject) => {
      const s = ioClient(BASE, { transports: ['websocket'], reconnection: false });
      const timer = setTimeout(() => { s.close(); reject(new Error('socket timeout')); }, 10000);
      s.on('connect', () => {
        s.emit('authorize', { client: 'probe', secret: HASH, history: 1 }, (auth) => {
          if (!auth || !auth.write_treatment) { clearTimeout(timer); s.close(); return reject(new Error('socket not authorized')); }
          (async () => {
            const replies = [];
            for (const d of docs) replies.push(await new Promise((r) => s.emit('dbAdd', { collection: 'treatments', data: d }, r)));
            clearTimeout(timer); s.close(); resolve(replies);
          })().catch(reject);
        });
      });
      s.on('connect_error', (e) => { clearTimeout(timer); reject(e); });
    });
  };
  h.stored = async function (t0, t1) {
    const db = await MongoClient.connect(mongoUri);
    const docs = await db.db().collection('treatments').find({ created_at: { $gte: iso(t0), $lt: iso(t1) } }).toArray();
    await db.close();
    return docs;
  };
  return h;
}

// kind: 'resend' (want = records after the re-send; value = expected final
// values) or 'distinct' (want = entries that should be kept apart).
function shapes () {
  const list = [];
  const add = (id, client, kind, want, run, value, note) => list.push({ id, client, kind, want, run, value, note });
  const loopCarb = (ms, carbs, sid) => ({ eventType: 'Carb Correction', created_at: iso(ms), carbs, absorptionTime: 180, enteredBy: 'loop://iPhone', syncIdentifier: sid });

  add('I8185', 'Loop (issue #8185): 16 g then 4 g, same time, own syncIdentifiers', 'distinct', 2, async (h, ms) => {
    h.check(await h.http('POST', '/api/v1/treatments', [loopCarb(ms, 16, uuid())]));
    h.check(await h.http('POST', '/api/v1/treatments', [loopCarb(ms, 4, uuid())]));
  });
  add('R01', 'Loop: batch of two re-POSTed identically after a failure', 'resend', 2, async (h, ms) => {
    const batch = [loopCarb(ms, 16, uuid()), loopCarb(ms + 60e3, 4, uuid())];
    h.check(await h.http('POST', '/api/v1/treatments', batch));
    h.check(await h.http('POST', '/api/v1/treatments', batch));
  });
  add('R02', 'Loop: in-progress dose re-POSTed, same syncIdentifier, new amount', 'resend', 1, async (h, ms) => {
    const d = { eventType: 'Correction Bolus', created_at: iso(ms), insulin: 1.0, duration: 0.5, syncIdentifier: uuid(), enteredBy: 'loop://iPhone' };
    h.check(await h.http('POST', '/api/v1/treatments', [d]));
    h.check(await h.http('POST', '/api/v1/treatments', [Object.assign({}, d, { insulin: 2.5 })]));
  }, { insulin: 2.5 });
  add('R03', 'Trio: carbs with id, identical retry', 'resend', 1, async (h, ms) => {
    const d = { eventType: 'Carb Correction', created_at: iso(ms), carbs: 30, id: uuid(), enteredBy: 'Trio' };
    h.check(await h.http('POST', '/api/v1/treatments.json', [d]));
    h.check(await h.http('POST', '/api/v1/treatments.json', [d]));
  });
  add('R04', 'Trio: pump event re-POSTed, same id, changed amount', 'resend', 1, async (h, ms) => {
    const d = { eventType: 'Bolus', created_at: iso(ms), insulin: 1.2, id: uuid(), enteredBy: 'Trio' };
    h.check(await h.http('POST', '/api/v1/treatments.json', [d]));
    h.check(await h.http('POST', '/api/v1/treatments.json', [Object.assign({}, d, { insulin: 1.5 })]));
  }, { insulin: 1.5 });
  add('R05', 'Trio: fat/protein entries sharing one id at other times, re-sent', 'resend', 3, async (h, ms) => {
    const id = uuid();
    const fpu = [0, 1, 2].map((k) => ({ eventType: 'Carb Correction', created_at: iso(ms + k * 20 * 60e3), carbs: 5, id, enteredBy: 'Trio' }));
    h.check(await h.http('POST', '/api/v1/treatments.json', fpu));
    h.check(await h.http('POST', '/api/v1/treatments.json', fpu));
  });
  add('R06', 'Trio: temp target without id, re-sent', 'resend', 1, async (h, ms) => {
    const d = { eventType: 'Temporary Target', created_at: iso(ms), duration: 60, targetTop: 140, targetBottom: 140, units: 'mg/dl', enteredBy: 'Trio' };
    h.check(await h.http('POST', '/api/v1/treatments.json', [d]));
    h.check(await h.http('POST', '/api/v1/treatments.json', [d]));
  });
  add('R07', 'Trio: temp target without id re-sent with a changed duration', 'resend', 1, async (h, ms) => {
    const d = { eventType: 'Temporary Target', created_at: iso(ms), duration: 60, targetTop: 140, targetBottom: 140, units: 'mg/dl', enteredBy: 'Trio' };
    h.check(await h.http('POST', '/api/v1/treatments.json', [d]));
    h.check(await h.http('POST', '/api/v1/treatments.json', [Object.assign({}, d, { duration: 20 })]));
  }, { duration: 20 });
  add('R08', 'Trio: pump suspend / sensor start without id, re-sent', 'resend', 2, async (h, ms) => {
    const d = [{ eventType: 'Suspend Pump', created_at: iso(ms), enteredBy: 'Trio' }, { eventType: 'Sensor Start', created_at: iso(ms), enteredBy: 'Trio' }];
    h.check(await h.http('POST', '/api/v1/treatments.json', d));
    h.check(await h.http('POST', '/api/v1/treatments.json', d));
  });
  add('R09', 'xDrip+: PUT with _id, re-sent with a new amount', 'resend', 1, async (h, ms) => {
    const d = { _id: hex24(), eventType: 'Bolus', created_at: iso(ms), insulin: 2, uuid: uuid(), enteredBy: 'xdrip' };
    h.check(await h.http('PUT', '/api/v1/treatments', d));
    h.check(await h.http('PUT', '/api/v1/treatments', Object.assign({}, d, { insulin: 3 })));
  }, { insulin: 3 });
  add('R10', 'xdripswift: POST eventTime ms, no id, retry', 'resend', 1, async (h, ms) => {
    const d = { eventType: 'Carbs', eventTime: iso(ms + 123), carbs: 12, enteredBy: 'xDrip4iOS' };
    h.check(await h.http('POST', '/api/v1/treatments', [d]));
    h.check(await h.http('POST', '/api/v1/treatments', [d]));
  });
  add('R11', 'careportal: double-submit, minute precision, no identity', 'resend', 1, async (h, ms) => {
    const d = { eventType: 'Meal Bolus', eventTime: iso(ms), carbs: '20', insulin: '1.5', enteredBy: 'careportal' };
    h.check(await h.http('POST', '/api/v1/treatments', d));
    h.check(await h.http('POST', '/api/v1/treatments', d));
  });
  add('R12', 'oref0: no identity, re-send differs only in notes', 'resend', 1, async (h, ms) => {
    const d = { eventType: 'Correction Bolus', created_at: iso(ms), insulin: 0.4, enteredBy: 'openaps://medtronic', notes: 'first' };
    h.check(await h.http('POST', '/api/v1/treatments.json', [d]));
    h.check(await h.http('POST', '/api/v1/treatments.json', [Object.assign({}, d, { notes: 'second' })]));
  }, { notes: 'second' });
  add('R13', 'tconnectsync: pump_event_id only (not a key), identical retry', 'resend', 1, async (h, ms) => {
    const d = { eventType: 'Combo Bolus', created_at: iso(ms), carbs: 0, insulin: 2.0, notes: '', enteredBy: 'Pump (tconnectsync)', pump_event_id: '1234' };
    h.check(await h.http('POST', '/api/v1/treatments', d));
    h.check(await h.http('POST', '/api/v1/treatments', d));
  });
  add('R14', 'nightscout-connect (REST output): no identity, identical retry', 'resend', 1, async (h, ms) => {
    const d = { eventType: 'Meal Bolus', created_at: iso(ms), carbs: 25, insulin: 2, enteredBy: 'nightscout-connect' };
    h.check(await h.http('POST', '/api/v1/treatments', [d]));
    h.check(await h.http('POST', '/api/v1/treatments', [d]));
  });
  add('R15', 'AAPS v3: POST without identifier or device, identical retry', 'resend', 1, async (h, ms) => {
    const d = { eventType: 'Carb Correction', date: ms, utcOffset: 0, app: 'AAPS', carbs: 20, isValid: true };
    h.check(await h.http('POST', '/api/v3/treatments', d, h.v3));
    h.check(await h.http('POST', '/api/v3/treatments', d, h.v3));
  });
  add('R16', 'AAPS v3: edit after a lost id (20 g, then 30 g re-POSTed without identifier)', 'resend', 1, async (h, ms) => {
    const d = { eventType: 'Carb Correction', date: ms, utcOffset: 0, app: 'AAPS', carbs: 20, isValid: true };
    h.check(await h.http('POST', '/api/v3/treatments', d, h.v3));
    h.check(await h.http('POST', '/api/v3/treatments', Object.assign({}, d, { carbs: 30 }), h.v3));
  }, { carbs: 30 });
  add('R17', 'socket dbAdd: re-send with the same NSCLIENT_ID', 'resend', 1, async (h, ms) => {
    const d = { eventType: 'Carb Correction', created_at: iso(ms), carbs: 20, NSCLIENT_ID: String(ms) };
    await h.socketAdd([d, d]);
  });
  add('R18', 'socket dbAdd: edit re-sent after a lost ack, no identity (20 g then 30 g)', 'resend', 1, async (h, ms) => {
    const d = { eventType: 'Carb Correction', created_at: iso(ms), carbs: 20 };
    await h.socketAdd([d, Object.assign({}, d, { carbs: 30 })]);
  }, { carbs: 30 }, 'known issue: the socket key has no amounts under option 3');
  add('R19', 'Loop: carb edit by PUT with _id', 'resend', 1, async (h, ms) => {
    const r = h.check(await h.http('POST', '/api/v1/treatments', [loopCarb(ms, 16, uuid())]));
    const doc = Array.isArray(r.json) ? r.json[0] : r.json;
    h.check(await h.http('PUT', '/api/v1/treatments', Object.assign({}, doc, { carbs: 18 })));
  }, { carbs: 18 });
  add('R20', 'record stored before the upgrade (no identity), re-sent after it', 'resend', 1, async (h, ms) => {
    // Written straight to the collection as API v1 stored it on 15.0.8.
    const { MongoClient } = require(path.join(h.root, 'node_modules', 'mongodb'));
    const db = await MongoClient.connect(mongoUri);
    await db.db().collection('treatments').insertOne({ eventType: 'Meal Bolus', created_at: iso(ms), carbs: 20, insulin: 1.5, enteredBy: 'careportal', utcOffset: 0 });
    await db.close();
    h.check(await h.http('POST', '/api/v1/treatments', { eventType: 'Meal Bolus', created_at: iso(ms), carbs: '20', insulin: '1.5', enteredBy: 'careportal' }));
  });

  add('R21', 'v1 record edited by AAPS v3 PATCH (by its _id), then re-sent through v1 without identity', 'resend', 1, async (h, ms) => {
    const d = { eventType: 'Carb Correction', created_at: iso(ms), carbs: 20, enteredBy: 'careportal' };
    const r = h.check(await h.http('POST', '/api/v1/treatments', [d]));
    const id = String((Array.isArray(r.json) ? r.json[0] : r.json)._id);
    h.check(await h.http('PATCH', '/api/v3/treatments/' + id, { notes: 'edited in AAPS' }, h.v3));
    h.check(await h.http('POST', '/api/v1/treatments', [d]));
  });
  // A v3 PUT of a v1 record (which would store an identifier on it) is refused
  // on e3adc91d with 400 "Field date cannot be modified by the client", with or
  // without `date` in the body, as is the v3 POST in O1; so no v3 path measured
  // here gives a v1 record an identifier. No corpus client sends a v3 PUT.
  add('O1', 'observation: v1 record, AAPS v3 POST at the same created_at and eventType (v3 status), then the v1 record re-sent', 'status', 0, async (h, ms) => {
    const d = { eventType: 'Carb Correction', created_at: iso(ms), carbs: 20, enteredBy: 'careportal' };
    h.check(await h.http('POST', '/api/v1/treatments', [d]));
    const r = await h.http('POST', '/api/v3/treatments', { eventType: 'Carb Correction', date: ms, utcOffset: 0, app: 'AAPS', carbs: 15, isValid: true }, h.v3);
    h.check(await h.http('POST', '/api/v1/treatments', [d]));
    return 'v3 ' + r.status + (r.status >= 400 ? ' ' + JSON.stringify((r.json || {}).message || '') : '');
  }, null, 'v3 fallback dedup onto a v1 record is BF-136 (not changed here)');
  add('O2', 'observation: as O1 with the same carbs (20 g) in the v3 POST', 'status', 0, async (h, ms) => {
    const d = { eventType: 'Carb Correction', created_at: iso(ms), carbs: 20, enteredBy: 'careportal' };
    h.check(await h.http('POST', '/api/v1/treatments', [d]));
    const r = await h.http('POST', '/api/v3/treatments', { eventType: 'Carb Correction', date: ms, utcOffset: 0, app: 'AAPS', carbs: 20, isValid: true }, h.v3);
    h.check(await h.http('POST', '/api/v1/treatments', [d]));
    return 'v3 ' + r.status + (r.status >= 400 ? ' ' + JSON.stringify((r.json || {}).message || '') : '');
  }, null, 'v3 fallback dedup onto a v1 record is BF-136 (not changed here)');
  add('D01', 'tconnectsync: bolus 2 U + extended 1 U, same second, both Combo Bolus, no id', 'distinct', 2, async (h, ms) => {
    h.check(await h.http('POST', '/api/v1/treatments', { eventType: 'Combo Bolus', created_at: iso(ms), carbs: 0, insulin: 2.0, enteredBy: 'Pump (tconnectsync)', pump_event_id: '11' }));
    h.check(await h.http('POST', '/api/v1/treatments', { eventType: 'Combo Bolus', created_at: iso(ms), carbs: 0, insulin: 1.0, duration: 60, enteredBy: 'Pump (tconnectsync)', pump_event_id: '12' }));
  });
  add('D02', 'AAPS v3: bolus + carbs in the same ms, both Meal Bolus, no identifier', 'distinct', 2, async (h, ms) => {
    h.check(await h.http('POST', '/api/v3/treatments', { eventType: 'Meal Bolus', date: ms, utcOffset: 0, app: 'AAPS', insulin: 3, isValid: true }, h.v3));
    h.check(await h.http('POST', '/api/v3/treatments', { eventType: 'Meal Bolus', date: ms, utcOffset: 0, app: 'AAPS', carbs: 40, isValid: true }, h.v3));
  }, null, 'known issue: API v3 key unchanged under option 3');
  add('D03', 'careportal: two entries, same minute, same amount', 'distinct', 2, async (h, ms) => {
    const d = { eventType: 'Meal Bolus', eventTime: iso(ms), carbs: '20', enteredBy: 'careportal' };
    h.check(await h.http('POST', '/api/v1/treatments', d));
    h.check(await h.http('POST', '/api/v1/treatments', d));
  }, null, 'indistinguishable from a double-submit in every design');
  add('D04', 'careportal then Loop entry, same second, same eventType', 'distinct', 2, async (h, ms) => {
    h.check(await h.http('POST', '/api/v1/treatments', { eventType: 'Carb Correction', created_at: iso(ms), carbs: 20, enteredBy: 'careportal' }));
    h.check(await h.http('POST', '/api/v1/treatments', [loopCarb(ms, 20, uuid())]));
  });
  add('D05', 'careportal: same minute, different carbs (the careportal half of #8185)', 'distinct', 2, async (h, ms) => {
    h.check(await h.http('POST', '/api/v1/treatments', { eventType: 'Meal Bolus', eventTime: iso(ms), carbs: '20', enteredBy: 'careportal' }));
    h.check(await h.http('POST', '/api/v1/treatments', { eventType: 'Meal Bolus', eventTime: iso(ms), carbs: '15', enteredBy: 'careportal' }));
  });
  return list;
}

function judge (shape, docs) {
  const n = docs.length;
  if (shape.kind === 'distinct') return n >= shape.want ? 'kept ' + n : 'MERGED (' + n + ')';
  if (n > shape.want) return 'DUPLICATE (' + n + ')';
  if (n < shape.want) return 'MERGED (' + n + ')';
  if (shape.value) {
    const ok = Object.keys(shape.value).every((k) => docs.some((d) => d[k] === shape.value[k]));
    return ok ? 'updated' : 'STALE';
  }
  return 'deduped';
}

async function runTree (tree) {
  const h = harness(tree.root);
  const out = {};
  try {
    await h.boot();
    h.v3 = { authorization: 'Bearer ' + await h.v3Token() };
    const t = Date.parse('2026-09-26T00:00:00.000Z');
    let i = 0;
    for (const s of shapes()) {
      const ms = t + (i++) * 3600e3;
      const said = await s.run(h, ms);
      await sleep(250);
      const docs = await h.stored(ms - 1000, ms + 3000e3);
      out[s.id] = s.kind === 'status' ? said + '; stored ' + docs.length + ' (carbs ' + docs.map((x) => x.carbs).join('+') + (docs.some((x) => x.identifier) ? ', one has identifier' : '') + ')' : judge(s, docs);
    }
    const live = await h.http('GET', '/api/v1/status.json');
    out.live = live.status === 200 && h.ok;
  } finally {
    h.stop();
    await sleep(1000);
  }
  return out;
}

async function main () {
  const results = [];
  for (const tree of trees) results.push(await runTree(tree));
  const cols = trees.map((t) => t.label);
  console.log('| shape | client and sequence | ' + cols.join(' | ') + ' | note |');
  console.log('|---|---|' + cols.map(() => '---').join('|') + '|---|');
  for (const s of shapes()) {
    console.log(`| ${s.id} | ${s.client} | ${results.map((r) => r[s.id]).join(' | ')} | ${s.note || ''} |`);
  }
  console.log('liveness and all writes 2xx: ' + trees.map((t, k) => t.label + '=' + results[k].live).join(' '));
  return results.every((r) => r.live) ? 0 : 2;
}

main().then((code) => process.exit(code)).catch((e) => { console.error('harness error:', e.stack || e.message); process.exit(3); });
