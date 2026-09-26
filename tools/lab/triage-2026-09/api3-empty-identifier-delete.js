'use strict';
/*
 * BF-140 probe: can API v3 delete a record that API v1 stored with an
 * `identifier` of null or "" (PR #8778)?
 *
 * Usage:
 *   node api3-empty-identifier-delete.js <cgm-remote-monitor tree with node_modules> <port> <mongodb uri>
 *   e.g. node api3-empty-identifier-delete.js ~/crm 17940 mongodb://127.0.0.1:27971/p140_test
 *
 * Boots the tree's lib/server/server.js against the given MongoDB database
 * (which it drops first) with API_SECRET set and AUTH_DEFAULT_ROLES=denied,
 * creates an admin subject for a v3 token and writes synthetic records only.
 * The server is started in its own process group and killed by its PID.
 *
 * Arms, for each stored identifier shape (absent = control, null, ""):
 *   get     v3 GET /treatments/<_id>: the status and whether the identifier
 *           it returns is the _id.
 *   soft    v3 DELETE /treatments/<_id>: the status, the stored isValid, and
 *           whether v1 GET /api/v1/treatments still lists the record.
 *   perm    v3 DELETE /treatments/<_id>?permanent=true: the status and
 *           whether the record is still stored.
 *   entry   the same soft DELETE for an entry v1 stored with that identifier.
 * Direct-insert shapes (not writable through v1 treatments, which refuses a
 * non-string identifier): identifier [null], [""], ["", "other"], 0, false.
 * For each: the identifier v3 GET shows (the _id, or the stored value), soft
 * DELETE, permanent DELETE of a second copy, and PATCH by the _id. Printed
 * only (BF-142: the falsy ones, which GET shows as the _id, should delete;
 * arrays, which GET shows as stored, are kept out of the _id fallback).
 * Non-string shapes through v1 entries and devicestatus: 0, false, [null],
 * [""], with the same columns. Printed only.
 * Bystanders: records with identifier null, "", 0, false, [null], [""],
 * ["", "other"] under other _ids are untouched by a DELETE of another
 * record. Printed only.
 * Other users of the id lookup (printed only): PATCH and PUT by the _id of a
 * v1 record whose identifier is null, "" or 0 (they use identifyingFilter,
 * whose _id fallback needs the identifier absent).
 * Re-send: the same v1 treatment POSTed twice with each shape; how many are
 * stored. Printed only.
 * Guard: a record with its own identifier "own-<n>" whose _id is asked for is
 * NOT deleted through the _id on trees with #8758 (15.0.8 deletes it).
 * Printed only.
 * Consequence: COB from /api/v2/properties/cob with one 30 g entry of each
 * shape, before and after its v3 soft DELETE.
 *
 * Exit status: 0 when every null/"" arm deletes, 1 when any is refused, 2 when
 * a control (identifier absent) answers otherwise, 3 on a harness error.
 * No data leaves the machine.
 */
const path = require('path');
const crypto = require('crypto');
const { spawn } = require('child_process');

const root = path.resolve(process.argv[2] || '.');
const port = Number(process.argv[3] || 17940);
const mongoUri = process.argv[4] || 'mongodb://127.0.0.1:27971/p140_test';
const { MongoClient, ObjectId } = require(path.join(root, 'node_modules', 'mongodb'));

const SECRET = 'probe-secret-' + crypto.randomBytes(6).toString('hex');
const HASH = crypto.createHash('sha1').update(SECRET).digest('hex');
const BASE = `http://127.0.0.1:${port}`;
let server;

async function http (method, p, body, headers) {
  const r = await fetch(BASE + p, {
    method,
    headers: Object.assign({ 'content-type': 'application/json', 'api-secret': HASH }, headers || {}),
    body: body === undefined ? undefined : JSON.stringify(body)
  });
  let json = null; try { json = await r.json(); } catch (e) { /* not json */ }
  return { status: r.status, json };
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function boot () {
  const db = await MongoClient.connect(mongoUri);
  await db.db().dropDatabase();
  await db.close();
  server = spawn(process.execPath, ['lib/server/server.js'], {
    cwd: root, detached: true, stdio: ['ignore', 'ignore', 'ignore'],
    env: Object.assign({}, process.env, {
      MONGODB_URI: mongoUri, PORT: String(port), HOSTNAME: '127.0.0.1', INSECURE_USE_HTTP: 'true',
      NODE_ENV: 'production', API_SECRET: SECRET, AUTH_DEFAULT_ROLES: 'denied',
      ENABLE: 'careportal iob cob', DISPLAY_UNITS: 'mg/dl'
    })
  });
  for (let i = 0; i < 120; i++) {
    try { const r = await http('GET', '/api/v1/status.json'); if (r.status === 200) return; } catch (e) { /* booting */ }
    await sleep(500);
  }
  throw new Error('server did not answer on ' + BASE);
}

async function v3Token () {
  const name = 'probe' + Date.now();
  const c = await http('POST', '/api/v2/authorization/subjects', { name, roles: ['admin'] });
  if (c.status !== 200) throw new Error('subject create ' + c.status);
  for (let i = 0; i < 20; i++) {
    const l = await http('GET', '/api/v2/authorization/subjects');
    const s = (l.json || []).find((x) => x.name === name);
    if (s && s.accessToken) {
      const j = await http('GET', '/api/v2/authorization/request/' + s.accessToken);
      if (j.status === 200 && j.json && j.json.token) return j.json.token;
    }
    await sleep(250);
  }
  throw new Error('no v3 token');
}

const SHAPES = [['absent', undefined], ['null', null], ['empty', '']];

async function main () {
  await boot();
  const v3 = { authorization: 'Bearer ' + (await v3Token()) };
  const db = await MongoClient.connect(mongoUri);
  const tcol = db.db().collection('treatments');
  const ecol = db.db().collection('entries');
  const now = Date.now();
  let slot = 0;
  const nextT = () => now - 3 * 3600 * 1000 + (slot++) * 60000;
  const iso = (ms) => new Date(ms).toISOString();
  let failed = 0, controlsFailed = 0;

  const v1Treatment = async (T, shape, g) => {
    const body = { eventType: 'Carb Correction', created_at: iso(T), carbs: g || 10, enteredBy: 'probe' };
    if (shape[1] !== undefined) body.identifier = shape[1];
    const r = await http('POST', '/api/v1/treatments', body);
    if (r.status !== 200) throw new Error('v1 create ' + shape[0] + ' ' + r.status);
    return tcol.findOne({ created_at: iso(T) });
  };
  const v1Lists = async (T) => {
    const r = await http('GET', '/api/v1/treatments.json?count=1000');
    if (!Array.isArray(r.json)) throw new Error('v1 list ' + r.status);
    return r.json.filter((x) => x.created_at === iso(T)).length;
  };
  const verdict = (shape, ok) => {
    if (shape === 'absent') { if (!ok) controlsFailed++; return ok ? 'ok  ' : 'CTRL'; }
    if (!ok) failed++;
    return ok ? 'ok  ' : 'FAIL';
  };

  console.log('stored shapes (v1 POST /api/v1/treatments), v3 addressed by the stored _id');
  for (const shape of SHAPES) {
    // get + soft
    {
      const T = nextT(); const d = await v1Treatment(T, shape);
      const stored = Object.prototype.hasOwnProperty.call(d, 'identifier') ? JSON.stringify(d.identifier) : 'absent';
      const g = await http('GET', '/api/v3/treatments/' + d._id, undefined, v3);
      const doc = g.json && (g.json.result || g.json);
      const gid = doc && doc.identifier;
      const before = await v1Lists(T);
      const s = await http('DELETE', '/api/v3/treatments/' + d._id, undefined, v3);
      const after = await tcol.findOne({ _id: d._id });
      const listed = await v1Lists(T);
      console.log(`  ${verdict(shape[0], s.status === 200)} ${shape[0].padEnd(6)} stored identifier ${stored.padEnd(6)} _id ${typeof d._id === 'string' ? 'string' : 'ObjectId'}`
        + ` | GET ${g.status} identifier ${gid === String(d._id) ? '= _id' : JSON.stringify(gid)}`
        + ` | soft DELETE ${s.status} isValid ${after && after.isValid} | v1 lists ${before} -> ${listed}`);
    }
    // perm
    {
      const T = nextT(); const d = await v1Treatment(T, shape);
      const p = await http('DELETE', '/api/v3/treatments/' + d._id + '?permanent=true', undefined, v3);
      const left = await tcol.countDocuments({ _id: d._id });
      console.log(`  ${verdict(shape[0], p.status === 200)} ${shape[0].padEnd(6)} permanent DELETE ${p.status} | stored after ${left}`);
    }
    // entry
    {
      const T = nextT();
      const body = { type: 'sgv', sgv: 100 + slot, date: T, dateString: iso(T), device: 'probe' };
      if (shape[1] !== undefined) body.identifier = shape[1];
      const c = await http('POST', '/api/v1/entries', [body]);
      const e = await ecol.findOne({ date: T });
      if (!e) { console.log(`  ??   ${shape[0].padEnd(6)} entry: v1 POST ${c.status}, nothing stored`); continue; }
      const stored = Object.prototype.hasOwnProperty.call(e, 'identifier') ? JSON.stringify(e.identifier) : 'absent';
      const s = await http('DELETE', '/api/v3/entries/' + e._id, undefined, v3);
      const after = await ecol.findOne({ _id: e._id });
      console.log(`  ${verdict(shape[0], s.status === 200)} ${shape[0].padEnd(6)} entry stored identifier ${stored.padEnd(6)} | soft DELETE ${s.status} isValid ${after && after.isValid}`);
    }
  }

  const gidOf = (g, _id) => {
    const doc = g.json && (g.json.result || g.json);
    if (!doc) return '-';
    return doc.identifier === String(_id) ? '= _id' : JSON.stringify(doc.identifier);
  };
  // soft DELETE, then permanent DELETE and PATCH on two more copies of the shape
  const arms = async (colName, col, seed) => {
    const a = await seed(); const b = await seed(); const c = await seed();
    const g = await http('GET', `/api/v3/${colName}/${a}`, undefined, v3);
    const s = await http('DELETE', `/api/v3/${colName}/${a}`, undefined, v3);
    const sa = await col.findOne({ _id: a });
    const p = await http('DELETE', `/api/v3/${colName}/${b}?permanent=true`, undefined, v3);
    const pb = await col.countDocuments({ _id: b });
    const pa = await http('PATCH', `/api/v3/${colName}/${c}`, { notes: 'patched' }, v3);
    return `GET ${g.status} identifier ${gidOf(g, a).padEnd(12)} | soft DELETE ${s.status} isValid ${sa && sa.isValid}`
      + ` | permanent DELETE ${p.status} stored ${pb} | PATCH ${pa.status}`;
  };

  console.log('direct-insert shapes (printed only)');
  for (const [name, value] of [['[null]', [null]], ['[""]', ['']], ['["","other"]', ['', 'other']], ['0', 0], ['false', false]]) {
    const seed = async () => {
      const T = nextT(); const _id = new ObjectId();
      await tcol.insertOne({ _id, eventType: 'Note', created_at: iso(T), notes: 'probe', identifier: value });
      return _id;
    };
    console.log(`  ..   treatments   ${name.padEnd(14)} ${await arms('treatments', tcol, seed)}`);
  }

  console.log('non-string shapes through v1 entries and devicestatus (printed only)');
  for (const [name, value] of [['0', 0], ['false', false], ['[null]', [null]], ['[""]', ['']]]) {
    for (const [colName, col, mk] of [
      ['entries', ecol, (T) => [{ type: 'sgv', sgv: 120, date: T, dateString: iso(T), device: 'probe', identifier: value }]],
      ['devicestatus', db.db().collection('devicestatus'), (T) => ({ device: 'probe', created_at: iso(T), identifier: value })]
    ]) {
      let status = null;
      const seed = async () => {
        const T = nextT();
        const c = await http('POST', '/api/v1/' + colName, mk(T));
        status = c.status;
        const d = await col.findOne(colName === 'entries' ? { date: T } : { created_at: iso(T) });
        if (!d) throw new Error(`${colName} ${name}: v1 POST ${c.status}, not stored`);
        return d._id;
      };
      const line = await arms(colName, col, seed);
      const stored = await col.findOne({ device: 'probe', identifier: value });
      console.log(`  ..   ${colName.padEnd(12)} ${name.padEnd(14)} v1 POST ${status} stored ${JSON.stringify(stored && stored.identifier)} | ${line}`);
    }
  }

  console.log('bystanders: a DELETE of another record leaves these untouched (printed only)');
  {
    const target = new ObjectId();
    await tcol.insertOne({ _id: target, eventType: 'Note', created_at: iso(nextT()), notes: 'probe', identifier: null });
    const values = [null, '', 0, false, [null], [''], ['', 'other']];
    const ids = [];
    for (const value of values) {
      const _id = new ObjectId(); ids.push(_id);
      await tcol.insertOne({ _id, eventType: 'Note', created_at: iso(nextT()), notes: 'bystander', identifier: value });
    }
    const s = await http('DELETE', '/api/v3/treatments/' + target, undefined, v3);
    const p = await http('DELETE', '/api/v3/treatments/' + target + '?permanent=true', undefined, v3);
    const touched = await tcol.countDocuments({ _id: { $in: ids }, isValid: false });
    const left = await tcol.countDocuments({ _id: { $in: ids } });
    console.log(`  ${touched === 0 && left === ids.length ? 'ok  ' : 'FAIL'} soft ${s.status} permanent ${p.status} | bystanders marked ${touched}, stored ${left}/${ids.length}`);
  }

  console.log('other users: PATCH and PUT by the _id of a v1 record with identifier null, "" or 0 (printed only)');
  for (const [name, value, colName, col] of [['null', null, 'treatments', tcol], ['empty', '', 'treatments', tcol], ['0', 0, 'entries', ecol]]) {
    const T = nextT();
    let _id;
    if (colName === 'treatments') {
      await http('POST', '/api/v1/treatments', { eventType: 'Note', created_at: iso(T), notes: 'probe', enteredBy: 'probe', identifier: value });
      _id = (await tcol.findOne({ created_at: iso(T) }))._id;
    } else {
      await http('POST', '/api/v1/entries', [{ type: 'sgv', sgv: 130, date: T, dateString: iso(T), device: 'probe', identifier: value }]);
      _id = (await ecol.findOne({ date: T }))._id;
    }
    const g = await http('GET', `/api/v3/${colName}/${_id}`, undefined, v3);
    const gid = gidOf(g, _id);
    const pa = await http('PATCH', `/api/v3/${colName}/${_id}`, { notes: 'patched' }, v3);
    const body = colName === 'treatments'
      ? { eventType: 'Note', created_at: iso(T), notes: 'put', enteredBy: 'probe', app: 'probe' }
      : { type: 'sgv', sgv: 131, date: T, dateString: iso(T), device: 'probe', app: 'probe' };
    const pu = await http('PUT', `/api/v3/${colName}/${_id}`, body, v3);
    const copies = await col.countDocuments(colName === 'treatments' ? { created_at: iso(T) } : { date: T });
    const puMsg = pu.status >= 400 && pu.json && pu.json.message ? ` (${pu.json.message})` : '';
    console.log(`  ..   ${colName.padEnd(12)} ${name.padEnd(6)} GET ${g.status} identifier ${gid} | PATCH ${pa.status} | PUT ${pu.status}${puMsg} | stored copies after ${copies}`);
  }

  console.log('guard: a record with its own identifier is not deleted by its _id (15.0.8 deletes it; #8758 changed that)');
  {
    const T = nextT(); const _id = new ObjectId();
    await tcol.insertOne({ _id, eventType: 'Note', created_at: iso(T), notes: 'probe', identifier: 'own-' + slot });
    const s = await http('DELETE', '/api/v3/treatments/' + _id, undefined, v3);
    const p = await http('DELETE', '/api/v3/treatments/' + _id + '?permanent=true', undefined, v3);
    const after = await tcol.findOne({ _id });
    const ok = s.status === 404 && p.status === 404 && after && after.isValid !== false;
    console.log(`  ${ok ? 'ok  ' : 'old '} soft ${s.status} permanent ${p.status} still stored and valid: ${!!(after && after.isValid !== false)}`);
  }

  console.log('re-send: the same v1 treatment POSTed twice (printed only; BF-121 keys a write without identity on identifier null)');
  for (const shape of SHAPES) {
    const T = nextT();
    const body = { eventType: 'Carb Correction', created_at: iso(T), carbs: 12, enteredBy: 'probe' };
    if (shape[1] !== undefined) body.identifier = shape[1];
    const a = await http('POST', '/api/v1/treatments', body);
    const b = await http('POST', '/api/v1/treatments', Object.assign({}, body));
    console.log(`  ..   ${shape[0].padEnd(6)} POST ${a.status}, ${b.status} | stored ${await tcol.countDocuments({ created_at: iso(T) })}`);
  }

  console.log('consequence: COB with one 30 g entry, before and after its v3 soft DELETE');
  {
    const prof = { defaultProfile: 'Default', startDate: iso(now - 86400000), mills: now - 86400000, units: 'mg/dl',
      store: { Default: { dia: 3, carbratio: [{ time: '00:00', value: 10 }], carbs_hr: 30, delay: 20,
        sens: [{ time: '00:00', value: 50 }], basal: [{ time: '00:00', value: 1 }],
        target_low: [{ time: '00:00', value: 100 }], target_high: [{ time: '00:00', value: 120 }], timezone: 'UTC', units: 'mg/dl' } } };
    const pr = await http('POST', '/api/v1/profile', prof);
    if (pr.status !== 200) throw new Error('profile ' + pr.status);
    const cob = async () => {
      await sleep(1500);
      const r = await http('GET', '/api/v2/properties/cob');
      return r.json && r.json.cob ? Math.round((r.json.cob.cob || 0) * 10) / 10 : null;
    };
    for (const shape of SHAPES) {
      await tcol.deleteMany({});
      await http('DELETE', '/api/v1/treatments/?find[created_at][$gte]=2000-01-01');
      const T = now - 10 * 60000;
      const body = { eventType: 'Carb Correction', created_at: iso(T), carbs: 30, enteredBy: 'probe' };
      if (shape[1] !== undefined) body.identifier = shape[1];
      await http('POST', '/api/v1/treatments', body);
      const d = await tcol.findOne({ created_at: iso(T) });
      const c0 = await cob();
      const s = await http('DELETE', '/api/v3/treatments/' + d._id, undefined, v3);
      const c1 = await cob();
      console.log(`  ${shape[0].padEnd(6)} COB ${c0} -> soft DELETE ${s.status} -> COB ${c1}`);
    }
  }

  await db.close();
  return controlsFailed ? 2 : (failed ? 1 : 0);
}

main().then((code) => {
  console.log(code === 0 ? 'RESULT: every null/"" record deletes through v3' : code === 1 ? 'RESULT: v3 DELETE refuses a null/"" record' : 'RESULT: a control answered otherwise');
  try { process.kill(-server.pid, 'SIGKILL'); } catch (e) { /* gone */ }
  process.exit(code);
}, (err) => {
  console.error('harness error:', err && err.stack || err);
  try { if (server) process.kill(-server.pid, 'SIGKILL'); } catch (e) { /* gone */ }
  process.exit(3);
});
