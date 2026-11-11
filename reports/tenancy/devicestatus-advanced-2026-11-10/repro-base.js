'use strict';
// Lane E1 reproduction: does devicestatus.advanced change client device-status
// state for the frames a tenant actually sends? Synthetic data only.
// Usage: node repro.js <crm worktree> <postgres admin URI>
const path = require('node:path');
const assert = require('node:assert/strict');
const W = path.resolve(process.argv[2]);
const PG_URI = process.argv[3];
const r = rel => require(path.join(W, rel));
const { EventEmitter } = require('node:events');
const { Client } = r('node_modules/pg');
const scope = r('lib/storage/tenant-scope');
const { encodeDocument } = r('lib/storage/postgres-identity');
const receiveDData = r('lib/client/receiveddata');
const environment = r('lib/server/tenant-app/environment');
const protocolFactory = r('lib/server/realtime/protocol');
const runtimeFactory = r('lib/server/realtime/runtime');
const T = '11111111-1111-4111-8111-111111111111';

const now = Date.now();
const status = (n, minutesAgo) => ({ _id: (n.toString(16)).padStart(24, 'a'), device: 'loop://synthetic-phone',
  created_at: new Date(now - minutesAgo * 60000).toISOString(),
  loop: { timestamp: new Date(now - minutesAgo * 60000).toISOString(), iob: { iob: n / 10 } } });
// Frame 1 store: statuses 1..3; frame 2 store: 1 removed, 4 added (synthetic).
const STORES = [[status(1, 20), status(2, 15), status(3, 10)], [status(2, 15), status(3, 10), status(4, 5)]];

async function main () {
  const pg = new Client({ connectionString: PG_URI }); await pg.connect();
  const server = (await pg.query('SHOW server_version')).rows[0].server_version;
  let store = STORES[0], served = false;
  // Replay bookkeeping is answered here; every jsonb_to_recordset read (the actual
  // projection-read SQL, filter, sort and limit) runs on the real PostgreSQL.
  const connection = { snapshotTransaction: async fn => fn(), async query (text, values) {
    if (text.includes('jsonb_to_recordset')) return pg.query(text, values);
    if (text.startsWith('SELECT checkpoint')) return { rows: [{ checkpoint: '0', contract_digest: '', projection: null }] };
    if (text.startsWith('SELECT last_stamp')) return { rows: [{ last_stamp: '0' }] };
    if (text.startsWith('SELECT count(*)')) return { rows: [{ row_count: String(store.length), document_bytes: '0' }] };
    if (text.startsWith('UPDATE')) return { rowCount: 1, rows: [] };
    if (text.startsWith('SELECT COALESCE(sum(pg_column_size')) return { rows: [{ bytes: 0 }] };
    if (text.startsWith('SELECT domain,id_kind,doc,stamp')) {
      if (values.length > 1 || served) return { rows: [] };
      served = true;
      return { rows: store.map(doc => ({ domain: 'devicestatus', ...encodeDocument(doc), stamp: null })) };
    }
    return { rows: [] };
  } };
  const config = { namespaces: Object.fromEntries(['entries', 'treatments', 'devicestatus', 'profile', 'food', 'activity', 'clock', 'checkpoint'].map(k => [k, 'rt_' + k])),
    consumer: 'realtime-source', pageSize: 50, maxRows: 100, maxBytes: 1000000 };
  const current = { tenant: T, identity: 'synthetic', env: environment({ settings: { enable: ['bgnow', 'loop'] } }) };
  const readCurrent = async t => t === T ? current : null;
  const projection = r('lib/server/realtime/projection')({ config, connection, current });

  // Actual protocol, actual runtime, actual projection; a recording socket.
  const api = { async executeSocketMutation () { throw new Error('no writes'); },
    async authorizeSocket (body) { const read = Object.keys(body.credential).length > 0; return { permissions: { read, write: false, write_treatment: false, ack: false }, collections: [] }; } };
  const protocol = protocolFactory.create({ admission: { resolve: async () => T }, api, readCurrent,
    runtime: () => runtime, maxSockets: 4, domains: ['entries', 'treatments', 'devicestatus'] });
  let schedule;
  const runtime = await runtimeFactory({ tenants: [T], readCurrent, create: () => ({ acquire: ({ at }) => { served = false; return projection.acquire({ at: at || Date.now() }).catch(e => { console.error("ACQUIRE", e); throw e; }); } }),
    fanout: protocol.fanout, recoveryIntervalMs: 100000, schedule: cb => { schedule = cb; return 1; }, cancel: () => {} });
  class Socket extends EventEmitter {
    constructor () { super(); this.request = { headers: { host: 't.test' }, rawHeaders: ['Host', 't.test'], socket: {} }; this.sent = []; this.rooms = new Set(['self']); this.id = 'self'; }
    emit (event, value) { this.sent.push({ event, value: value === undefined ? undefined : JSON.parse(JSON.stringify(value)) }); return true; }
    async receive (event, ...args) { return Promise.all(this.listeners(event).map(fn => fn(...args))); }
    join (n) { this.rooms.add(n); } leave (n) { this.rooms.delete(n); } disconnect () { this.disconnected = true; super.emit('disconnect'); }
  }
  const socket = new Socket(); await protocol.prepare(socket); protocol.bind(socket, '/');
  await new Promise(done => setTimeout(done, 500)); // let the unauthenticated bind settle
  await socket.receive('authorize', { secret: 'synthetic', status: true });
  await new Promise(done => setTimeout(done, 500));
  store = STORES[1]; await schedule();
  const frames = socket.sent.filter(s => s.event === 'dataUpdate').map(s => s.value);
  protocol.close(); await runtime.close(); await pg.end();

  // Client settings each mode serves. Tenant: the status route's projection
  // (status.js:25 with rest-context.js:25) and the realtime status frame.
  const tenantStatusExt = current.env.settings.filteredSettings(current.env.extendedSettings);
  const tenantFrameExt = frames.find(f => f.status).status.extendedSettings;
  // Single site: env.js findExtendedSettings, through plugins.extendedClientSettings and filteredSettings.
  for (const k of Object.keys(process.env)) if (/^(ENABLE|DEVICESTATUS_|CUSTOMCONNSTR_)/.test(k)) delete process.env[k];
  const env = r('lib/server/env')();
  const plugins = r('lib/plugins')({ settings: env.settings, language: r('lib/language')() });
  const singleExt = env.settings.filteredSettings(plugins.extendedClientSettings(env.extendedSettings));

  function replay (ext, sequence) {
    const ddata = { sgvs: [], mbgs: [], treatments: [], food: [], devicestatus: [], processTreatments () {} };
    return sequence.map(frame => { receiveDData(JSON.parse(JSON.stringify(frame)), ddata, { extendedSettings: ext }); return ddata.devicestatus.map(s => s._id); });
  }
  const out = {
    postgres: server,
    frames: frames.map(f => ({ delta: f.delta, devicestatus: f.devicestatus.map(s => s._id) })),
    settings: { tenantStatus: tenantStatusExt.devicestatus ?? null, tenantRealtimeStatus: tenantFrameExt.devicestatus ?? null, single: singleExt.devicestatus ?? null },
    tenantFrames: { tenantSettings: replay(tenantStatusExt, frames), singleSettings: replay(singleExt, frames) },
    // Detection control: the same frames relabelled delta:true (the single-site
    // websocket's incremental shape, websocket.js:122). Shows the harness can see
    // a merge-versus-replace difference when one exists.
    deltaControl: (() => { const d = frames.map(f => ({ ...f, delta: true })); return { tenantSettings: replay(tenantStatusExt, d), singleSettings: replay(singleExt, d) }; })()
  };
  out.verdict = {
    tenantFramesDiffer: JSON.stringify(out.tenantFrames.tenantSettings) !== JSON.stringify(out.tenantFrames.singleSettings),
    deltaControlDiffers: JSON.stringify(out.deltaControl.tenantSettings) !== JSON.stringify(out.deltaControl.singleSettings)
  };
  console.log(JSON.stringify(out, null, 1));
  assert.equal(frames.length, 2, 'two dataUpdate frames: authorized frame, fanout after the store change');
}
scope.setTenancyMode('multi');
main().catch(e => { console.error(e); process.exit(1); });
