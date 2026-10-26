'use strict';
// BF-164 lab: when does a record written outside API v3 reach a client that behaves like
// AndroidAPS NSClientV3 in websocket mode?
//
//   node tools/lab/aaps-ws-delivery/aaps-ws-lab.js <crm worktree> <outdir>   (servers from start-servers.sh must be up)
//
// The simulated client (SimAAPS) follows AndroidAPS dev 3905d352dd (4.0.0 line); every choice
// cites the file it comes from (paths under plugins/sync/src/commonMain/kotlin/app/aaps/plugins/
// sync/nsclientV3/ unless stated):
//  C1 ns_use_ws defaults to true (core/keys/.../BooleanKey.kt:250; 3.4.2.6 BooleanKey.kt:101).
//  C2 Storage socket: on connect, emit `subscribe` {accessToken, collections: [devicestatus,
//     entries, profile, treatments, foods, settings]} (ws/NsConnectHandler.kt COLLECTIONS).
//  C3 On a successful subscribe: initialLoadFinished = false, then a catch-up round
//     (NsConnectHandler.onConnectStorage -> NSClientV3Plugin.executeLoop("WS_CONNECT")).
//  C4 A round is STATUS, LAST_MODIFICATION, BG, TREATMENTS, ..., DEVICE_STATUS, DATA_SYNC
//     (NSClientV3Plugin.executeLoop). BG/TREATMENTS run only if lastModified for the collection
//     is newer than the cursor, then page GET /api/v3/<col>/history/<cursor>?limit=500 and set
//     the cursor from the reply's ETag (workers/LoadBgRunner.kt, LoadTreatmentsRunner.kt,
//     LoadLastModificationRunner.kt). LoadDeviceStatusRunner sets initialLoadFinished = true.
//     Cursor floor: max(cursor, now - 100 days) (NSClientV3Plugin.maxAge).
//  C5 A storage-socket create/update frame: if initialLoadFinished, the collection's cursor is
//     SET to the frame document's srvModified (plain set, not max) and the record is processed
//     (ws/NsFrameHandler.kt:105-111; remotemodel/LastModified.kt set()). 3.4.2.6 does the same
//     (services/NSClientV3Service.kt:226-227).
//  C6 While the socket is connected the client does not poll: executeLoop returns early when
//     initialLoadFinished && !needsPolling(), and the 5-minute tick (1 minute when BG is stale)
//     polls only when needsPolling(), i.e. WS off or socket down (NSClientV3Plugin.kt:372-385,
//     409-410, 1185). 3.4.2.6 ticks only with WS off (NSClientV3Plugin.kt:308).
//  C7 On a storage-socket disconnect: initialLoadFinished = false (NsConnectHandler.onDisconnectStorage).
// Not modelled: the first-ever load (date-based search, isFirstLoad); the client here is a
// returning client whose cursor starts one hour back. Profile, food, settings and devicestatus
// loading. The token is a subject with the built-in `readable` role.

const path = require('path');
const fs = require('fs');
const crypto = require('crypto');
const WT = process.argv[2];
const OUT = process.argv[3];
const io = require(path.join(WT, 'node_modules/socket.io-client'));
const [SRC_SECRET, TGT_SECRET] = fs.readFileSync(path.join(OUT, 'secrets'), 'utf8').trim().split('\n');
const sha1 = s => crypto.createHash('sha1').update(s).digest('hex');
const TGT = 'http://127.0.0.1:17316';
const SRC = 'http://127.0.0.1:17317';
const sleep = ms => new Promise(r => setTimeout(r, ms));
const T0 = Date.now();
const t = () => ((Date.now() - T0) / 1000).toFixed(1) + 's';
const log = (...a) => { const line = '[' + t() + '] ' + a.join(' '); console.log(line); fs.appendFileSync(path.join(OUT, 'lab.log'), line + '\n'); };

async function req (base, secret, method, p, body, headers) {
  const h = Object.assign({ 'content-type': 'application/json' }, secret ? { 'api-secret': sha1(secret) } : {}, headers || {});
  const r = await fetch(base + p, { method, headers: h, body: body === undefined ? undefined : JSON.stringify(body) });
  const text = await r.text(); let j; try { j = JSON.parse(text); } catch (e) { /* not JSON */ }
  return { s: r.status, j, etag: r.headers.get('etag') };
}
async function alive (label) {
  const a = (await req(TGT, TGT_SECRET, 'GET', '/api/v1/status.json')).s;
  const b = (await req(SRC, SRC_SECRET, 'GET', '/api/v1/status.json')).s;
  if (a !== 200 || b !== 200) throw new Error('LIVENESS FAILED ' + label + ' target ' + a + ' source ' + b);
  return true;
}

class SimAAPS {
  constructor (accessToken) {
    this.accessToken = accessToken;
    this.cursor = { entries: Date.now() - 3600e3, treatments: Date.now() - 3600e3 };
    this.initialLoadFinished = false;
    this.seen = new Map(); // key -> { via, at }
    this.rounds = 0;
  }
  key (col, doc) { return col + ':' + (doc.bf164 || (col === 'entries' ? 'date=' + doc.date : doc.identifier)); }
  note (col, doc, via) {
    const k = this.key(col, doc);
    if (!this.seen.has(k)) this.seen.set(k, { via, at: Date.now() });
  }
  async jwt () {
    if (!this._jwt) this._jwt = (await req(TGT, null, 'GET', '/api/v2/authorization/request/' + this.accessToken)).j.token;
    return { authorization: 'Bearer ' + this._jwt };
  }
  async round (origin) { // C4
    this.rounds++;
    const H = await this.jwt();
    await req(TGT, null, 'GET', '/api/v3/status', undefined, H);
    const lm = (await req(TGT, null, 'GET', '/api/v3/lastModified', undefined, H)).j.result.collections;
    const fetched = {};
    for (const col of ['entries', 'treatments']) {
      fetched[col] = 0;
      let guard = 0;
      while (guard++ < 20) {
        const lastLoaded = Math.max(this.cursor[col], Date.now() - 100 * 86400e3);
        if (!((lm[col] || 0) > lastLoaded)) break;
        const r = await req(TGT, null, 'GET', `/api/v3/${col}/history/${lastLoaded}?limit=500`, undefined, H);
        const docs = (r.j && r.j.result) || [];
        const etag = r.etag ? Number(r.etag.replace(/[^0-9]/g, '')) : null;
        const stalled = etag !== null && etag <= lastLoaded;
        if (etag !== null) this.cursor[col] = etag;
        docs.forEach(d => this.note(col, d, 'history(' + origin + ')'));
        fetched[col] += docs.length;
        if (!docs.length || stalled) break;
      }
    }
    this.initialLoadFinished = true; // LoadDeviceStatusRunner
    log('  client round', origin, 'fetched', JSON.stringify(fetched), 'cursor', JSON.stringify(this.cursor));
  }
  connect () { // C2, C3, C5, C7
    return new Promise((resolve, reject) => {
      const s = io(TGT + '/storage', { transports: ['websocket'], forceNew: true, reconnection: false });
      this.sock = s;
      s.on('connect', () => s.emit('subscribe', { accessToken: this.accessToken,
        collections: ['devicestatus', 'entries', 'profile', 'treatments', 'foods', 'settings'] }, async a => {
        if (!a || !a.success) return reject(new Error('subscribe refused ' + JSON.stringify(a)));
        log('  client subscribed', JSON.stringify(a.collections));
        this.initialLoadFinished = false;
        await this.round('WS_CONNECT');
        resolve();
      }));
      const onFrame = kind => ev => {
        const col = ev.colName; const doc = ev.doc || {};
        if (this.initialLoadFinished && doc.srvModified && this.cursor[col] !== undefined) this.cursor[col] = doc.srvModified;
        this.note(col, doc, 'ws:' + kind);
      };
      s.on('create', onFrame('create'));
      s.on('update', onFrame('update'));
      s.on('connect_error', reject);
    });
  }
  disconnect () { this.sock.disconnect(); this.initialLoadFinished = false; }
}

async function main () {
  fs.writeFileSync(path.join(OUT, 'lab.log'), '');
  await alive('start');
  const head = require('child_process').execFileSync('git', ['-C', WT, 'log', '-1', '--format=%H %s']).toString().trim();
  const ver = (await req(TGT, TGT_SECRET, 'GET', '/api/v1/status.json')).j.version;
  log('target head', head, 'version', ver, 'node', process.version);

  // the follower's token: a subject with the built-in readable role
  await req(TGT, TGT_SECRET, 'POST', '/api/v2/authorization/subjects', { name: 'bf164-follower', roles: ['readable'] });
  const subj = (await req(TGT, TGT_SECRET, 'GET', '/api/v2/authorization/subjects')).j.find(x => x.name === 'bf164-follower');
  // writers: v3 with an admin subject, the main socket with the secret
  await req(TGT, TGT_SECRET, 'POST', '/api/v2/authorization/subjects', { name: 'bf164-writer', roles: ['admin'] });
  const wsub = (await req(TGT, TGT_SECRET, 'GET', '/api/v2/authorization/subjects')).j.find(x => x.name === 'bf164-writer');
  const wjwt = (await req(TGT, null, 'GET', '/api/v2/authorization/request/' + wsub.accessToken)).j.token;
  const V3 = { authorization: 'Bearer ' + wjwt };
  const main = await new Promise((resolve, reject) => {
    const s = io(TGT, { transports: ['websocket'], forceNew: true });
    s.on('connect', () => s.emit('authorize', { client: 'web', secret: sha1(TGT_SECRET), history: 0 }, () => resolve(s)));
    s.on('connect_error', reject);
  });

  let n = 0;
  const carb = tag => ({ eventType: 'Carb Correction', carbs: 12, created_at: new Date().toISOString(), enteredBy: 'bf164-lab', bf164: tag, notes: tag });
  const writers = {
    v1: async tag => { const r = await req(TGT, TGT_SECRET, 'POST', '/api/v1/treatments/', carb(tag)); return 'v1 POST ' + r.s; },
    socket: tag => new Promise(resolve => main.emit('dbAdd', { collection: 'treatments', data: carb(tag) }, a => resolve('socket dbAdd ack ' + (Array.isArray(a) ? a.length : JSON.stringify(a))))),
    v3treat: async tag => { const b = Object.assign(carb(tag), { date: Date.now(), utcOffset: 0, app: 'bf164-lab', device: 'bf164-lab-' + tag }); const r = await req(TGT, null, 'POST', '/api/v3/treatments', b, V3); return 'v3 POST ' + r.s; },
    v3entry: async tag => { const d = Date.now(); const r = await req(TGT, null, 'POST', '/api/v3/entries', { type: 'sgv', sgv: 101, date: d, dateString: new Date(d).toISOString(), utcOffset: 0, app: 'bf164-lab', device: 'bf164-lab', bf164: tag }, V3); return 'v3 POST ' + r.s; }
  };
  const results = [];
  const client = new SimAAPS(subj.accessToken);
  await client.connect();

  async function waitSeen (key, ms) {
    const until = Date.now() + ms;
    while (Date.now() < until) { if (client.seen.has(key)) return client.seen.get(key); await sleep(200); }
    return client.seen.get(key) || null;
  }
  function record (scenario, path, key, wroteAt, got, extra) {
    const row = { scenario, path, outcome: got ? got.via : 'NOT RECEIVED', latency_s: got ? ((got.at - wroteAt) / 1000).toFixed(2) : null, extra: extra || '' };
    results.push(row); log('RESULT', JSON.stringify(row));
  }

  // ---- control: v3 create while connected
  for (const [col, w] of [['treatments', 'v3treat'], ['entries', 'v3entry']]) {
    const tag = 'ctl-' + col + '-' + (++n); const at = Date.now();
    log('write', w, tag, await writers[w](tag));
    const got = await waitSeen(col + ':' + tag, 10000);
    await alive('control ' + tag);
    record('control: v3 create, socket up', w, tag, at, got);
  }

  // ---- treatments via v1 (careportal posts here too) and the main socket
  for (const p of ['v1', 'socket']) {
    // S1 live + S2 reconnect, no v3 write in between
    let tag = p + '-s1-' + (++n); let at = Date.now();
    log('write', p, tag, await writers[p](tag));
    let got = await waitSeen('treatments:' + tag, 45000);
    await alive('S1 ' + tag);
    record('S1 socket up, wait 45 s', p, tag, at, got);
    client.disconnect(); log('  client disconnected'); await sleep(2000); await client.connect();
    got = await waitSeen('treatments:' + tag, 5000);
    await alive('S2 ' + tag);
    record('S2 then reconnect (no v3 treatment in between)', p, tag, at, got);
    // S3 write, then a v3 treatment (pushed, moves the cursor), then reconnect
    tag = p + '-s3-' + (++n); at = Date.now();
    log('write', p, tag, await writers[p](tag));
    await sleep(1500);
    const vtag = 'v3-after-' + tag;
    log('write v3treat', vtag, await writers.v3treat(vtag));
    const vgot = await waitSeen('treatments:' + vtag, 10000);
    log('  v3 follow-up seen via', vgot && vgot.via, 'cursor now', client.cursor.treatments);
    client.disconnect(); log('  client disconnected'); await sleep(2000); await client.connect();
    got = await waitSeen('treatments:' + tag, 5000);
    await alive('S3 ' + tag);
    const st = (await req(TGT, null, 'GET', '/api/v3/treatments/history/' + (at - 60000) + '?limit=1000', undefined, await client.jwt())).j.result.filter(d => d.bf164 === tag);
    record('S3 then a v3 treatment, then reconnect', p, tag, at, got, 'record in v3 history: ' + st.length + ' srvModified ' + (st[0] && st[0].srvModified));
  }

  // ---- entries via nightscout-connect (source Nightscout -> target in-process ctx.entries.create)
  for (const sc of ['S1S2', 'S3']) {
    const d = Date.now() - 1000;
    const tag = 'connect-' + sc + '-' + (++n);
    const r = await req(SRC, SRC_SECRET, 'POST', '/api/v1/entries/', [{ type: 'sgv', sgv: 123, date: d, dateString: new Date(d).toISOString(), device: 'bf164-src', direction: 'Flat' }]);
    log('write source entry', tag, 'date', d, 'status', r.s);
    const key = 'entries:date=' + d;
    // wait for the connector to copy it into the target (poll the target database through v1)
    let arrivedAt = null;
    for (let i = 0; i < 420 && !arrivedAt; i++) {
      const q = await req(TGT, TGT_SECRET, 'GET', '/api/v1/entries.json?find[date]=' + d + '&count=1');
      if (q.j && q.j.length) arrivedAt = Date.now(); else await sleep(1000);
    }
    await alive('connector ' + tag);
    log('  connector stored it in target after', arrivedAt ? ((arrivedAt - d) / 1000).toFixed(0) + ' s' : 'NEVER (7 min)');
    if (!arrivedAt) { record('connector', 'connector', tag, d, null, 'connector did not write within 7 min'); continue; }
    if (sc === 'S1S2') {
      let got = await waitSeen(key, 45000);
      await alive('S1 ' + tag);
      record('S1 socket up, wait 45 s after the connector wrote', 'connector', tag, arrivedAt, got);
      client.disconnect(); log('  client disconnected'); await sleep(2000); await client.connect();
      got = await waitSeen(key, 5000);
      await alive('S2 ' + tag);
      record('S2 then reconnect (no v3 entry in between)', 'connector', tag, arrivedAt, got);
    } else {
      await sleep(1500);
      const vtag = 'v3-after-' + tag;
      log('write v3entry', vtag, await writers.v3entry(vtag));
      const vgot = await waitSeen('entries:' + vtag, 10000);
      log('  v3 follow-up seen via', vgot && vgot.via, 'cursor now', client.cursor.entries);
      client.disconnect(); log('  client disconnected'); await sleep(2000); await client.connect();
      const got = await waitSeen(key, 5000);
      await alive('S3 ' + tag);
      record('S3 then a v3 entry, then reconnect', 'connector', tag, arrivedAt, got);
    }
  }

  client.disconnect(); main.disconnect();
  fs.writeFileSync(path.join(OUT, 'results.json'), JSON.stringify({ head, version: ver, node: process.version, results }, null, 2));
  log('done');
  process.exit(0);
}
main().catch(e => { log('FATAL', e.stack || e); process.exit(1); });
