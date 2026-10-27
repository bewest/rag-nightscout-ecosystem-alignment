'use strict';
// HTTP differential for ST-READS: the same API v1 GET requests against dev's
// tree and the branch, each over an identical freshly seeded database; every
// response compared on status, content type and body.
// Usage: node tools/seam/v1-http-differential.js <devTree> <branchTree> <mongo uri (no db)> [outDir]
const path = require('path');
const fs = require('fs');
const { execFileSync } = require('child_process');
const [devTree, branchTree, MONGO, outDirArg] = process.argv.slice(2);
const outDir = outDirArg || __dirname;
const { MongoClient, ObjectId } = require(path.join(branchTree, 'node_modules/mongodb'));

const NOW = Date.now();
const iso = t => new Date(t).toISOString();
const oid = i => new ObjectId(('0'.repeat(24) + i.toString(16)).slice(-24));

function seed () {
  const entries = [], treatments = [], devicestatus = [], activity = [], profile = [], food = [];
  for (let i = 1; i <= 60; i++) {
    const t = NOW - i * 300000;
    const e = { _id: oid(i), type: ['sgv', 'mbg', 'cal'][i % 3], date: t, dateString: iso(t), device: ['xDrip-DexcomG6', 'Loop', '', 'loop\nDexcom'][i % 4] };
    if (i % 3 === 0 || i % 3 === 1) e.sgv = 40 + (i * 13) % 300;
    if (i % 11 === 0) e.sgv = String(e.sgv);         // cross-type
    if (i % 3 === 1) e.mbg = 100 + i;
    if (i % 7 === 0) e.noise = null;
    if (i % 13 === 0) e.isValid = false;
    if (i % 17 === 0) e._id = oid(i).toHexString();   // string _id twin form
    entries.push(e);
    const tr = { _id: oid(1000 + i), eventType: ['Meal Bolus', 'Temp Basal', 'Note', 'Correction Bolus', 'meal\nbolus'][i % 5], created_at: iso(t), enteredBy: ['Loop', 'Trio', 'xdrip', ''][i % 4] };
    if (i % 2) tr.carbs = i % 40; if (i % 3) tr.insulin = (i % 5) / 2;
    if (i % 5 === 0) tr.notes = ['a\nb', 'axb', 'hello'][i % 3];
    if (i % 4 === 0) tr.syncIdentifier = ['', null, 'abc', ['x']][i % 4 === 0 ? (i / 4) % 4 : 0];
    if (i % 19 === 0) tr.isValid = false;
    if (i % 23 === 0) tr.carbs = '15';
    treatments.push(tr);
    devicestatus.push({ _id: oid(2000 + i), device: ['loop://iPhone', 'openaps://rig', 'xdrip'][i % 3], created_at: iso(t), uploaderBattery: i % 100, pump: i % 2 ? { battery: { percent: i } } : undefined, isValid: i % 29 === 0 ? false : undefined });
    if (i <= 12) activity.push({ _id: oid(3000 + i), created_at: iso(t), steps: i * 10, heartrate: i % 2 ? 60 + i : undefined });
    if (i <= 8) profile.push({ _id: oid(4000 + i), defaultProfile: 'Default', startDate: iso(t - i * 86400000), created_at: iso(t), units: i % 2 ? 'mg/dl' : 'mmol', store: { Default: { dia: 3 } }, isValid: i === 8 ? false : undefined });
    if (i <= 10) food.push({ _id: oid(5000 + i), type: i % 3 ? 'food' : 'quickpick', name: 'f' + i, carbs: i, hidden: [false, 'false', true, 'true', undefined][i % 5], position: i % 4, category: 'c' + (i % 2) });
  }
  // Drop undefined keys by hand: a JSON round trip would lose the ObjectIds.
  const clean = a => a.map(d => { const o = {}; for (const [k, v] of Object.entries(d)) if (v !== undefined) o[k] = v; return o; });
  return { entries: clean(entries), treatments: clean(treatments), devicestatus: clean(devicestatus), activity: clean(activity), profile: clean(profile), food: clean(food) };
}

const enc = s => s;
const FINDS = [
  '', 'count=5', 'count=0', 'count=abc', 'count=-1', 'count=1%3Ftoken%3Dx', 'count=100',
  'find[type]=sgv', 'find[type][$eq]=mbg', 'find[type][$ne]=sgv&count=50',
  'find[sgv][$gte]=100&count=50', 'find[sgv][$gte]=100&find[sgv][$lte]=200&count=50',
  'find[sgv][$type]=2&count=50', 'find[sgv][$type]=string&count=50', 'find[sgv][$type]=number&count=50',
  'find[sgv][$type][]=2&find[sgv][$type][]=1&count=50', 'find[sgv][$type]=nope',
  'find[mbg][$exists]=true&count=50', 'find[mbg][$exists]=false&count=50', 'find[mbg][$exists]=&count=50',
  'find[mbg][$exists]=yes&count=50', 'find[mbg][$exists]=0&count=50', 'find[noise][$exists]=true&count=50',
  'find[device][$regex]=Loop&count=50', 'find[device][$regex]=loop&find[device][$options]=i&count=50',
  'find[device][$regex]=loop.Dexcom&find[device][$options]=s&count=50', 'find[device][$regex]=x&find[device][$options]=g',
  'find[device][$options]=i', 'find[device][$regex][]=x', 'find[device][$regex]=' + 'a'.repeat(200),
  'find[sgv][$in][]=100&find[sgv][$in][]=120&count=50', 'find[sgv][$in]=5', 'find[type][$nin][]=sgv&count=50', 'find[sgv][$nin]=1',
  'find[$or][0][type]=sgv&find[$or][1][type]=mbg&count=50', 'find[$or]=x', 'find[$or][]=', 'find[$and][0][sgv]=100',
  'find[$and][0][type]=sgv&find[$and][1][sgv][$gte]=100&count=50',
  'find[a-b]=1', 'find[a.0.b]=1', 'find[pump.battery.percent][$gte]=10&count=50', 'find[sgv][$eq][x]=1', 'find[sgv][$gte]=',
  'find[isValid]=false&count=50', 'find[_id]=' + oid(5).toHexString(), 'find[_id]=' + oid(17).toHexString(), 'find[_id]=nothex',
  'find[date][$gte]=' + (NOW - 3600000) + '&count=50', 'find[dateString][$gte]=' + iso(NOW - 3600000) + '&count=50',
  'find[created_at][$gte]=' + iso(NOW - 7200000) + '&count=50', 'find[created_at][$gte]=2026-99-05T00:00:00Z',
  'find[eventType]=/Bolus/&count=50', 'find[eventType]=/bolus/i&count=50', 'find[eventType]=/meal.bolus/g&count=50',
  'find[eventType]=/meal.bolus/s&count=50', 'find[notes]=/a.b/g&count=50', 'find[enteredBy]=/^$/&count=50',
  'find[eventType][$in][]=Note&find[eventType][$in][]=Meal Bolus&count=50', 'find[carbs][$gte]=10&count=50',
  'find[insulin][$gt]=0&count=50', 'find[syncIdentifier][$type]=array', 'find[syncIdentifier][$in][]=&count=50',
  'find[$where]=1', 'find[device][$elemMatch][x]=1', 'find[sgv][$not][$gt]=1', 'find[$expr][$eq][]=1',
  'find[startDate][$gte]=2000-01-01&count=50', 'find[units]=mmol', 'find[steps][$gte]=50',
  'sort[date]=1&count=10', 'sort[sgv]=-1&count=10&find[sgv][$exists]=true',
  'pipeline[0][$match][x]=1'
];
function urls () {
  const u = [];
  for (const base of ['/api/v1/entries.json', '/api/v1/entries/sgv.json', '/api/v1/treatments.json', '/api/v1/devicestatus.json',
    '/api/v1/activity.json', '/api/v1/profiles.json', '/api/v1/count/entries/where', '/api/v1/count/treatments/where',
    '/api/v1/count/devicestatus/where']) {
    for (const f of FINDS) u.push(base + (f ? '?' + enc(f) : ''));
  }
  u.push('/api/v1/profile.json', '/api/v1/profile.json?count=2', '/api/v1/profile.json?count=0', '/api/v1/profile.json?count=abc',
    '/api/v1/profile/current', '/api/v1/food.json', '/api/v1/food/quickpicks.json', '/api/v1/food/regular.json',
    '/api/v1/entries/current.json', '/api/v1/entries/' + oid(4).toHexString() + '.json', '/api/v1/entries/' + oid(17).toHexString() + '.json',
    '/api/v1/entries/' + oid(13).toHexString() + '.json', '/api/v1/entries/mbg.json?count=5');
  const day = iso(NOW).slice(0, 10);
  for (const p of ['/api/v1/times/' + day, '/api/v1/times/' + day + '/T{00..23}', '/api/v1/times/20{25..26}/T0',
    '/api/v1/slice/entries/dateString/sgv/' + day, '/api/v1/slice/treatments/created_at/' + day.slice(0, 7),
    '/api/v1/slice/devicestatus/created_at/' + day, '/api/v1/slice/entries/device/sgv/Loop', '/api/v1/slice/entries/device/sgv/loop.Dexcom',
    '/api/v1/times/' + day + '/' + 'x'.repeat(200), '/api/v1/slice/entries/$where/x/y']) {
    u.push(p + '.json', p + '.json?count=3&find[sgv][$gte]=100', p + '.json?find[sgv][$type]=2');
  }
  return u;
}

(async function main () {
  const client = await MongoClient.connect(MONGO);
  const data = seed();
  const reqs = urls();
  const reqFile = path.join(outDir, 'httpdiff-requests.json');
  fs.writeFileSync(reqFile, JSON.stringify(reqs));
  const results = {};
  for (const [name, tree] of [['dev', devTree], ['branch', branchTree]]) {
    const db = 'httpdiff_' + name + '_' + process.pid;
    for (const [c, docs] of Object.entries(data)) await client.db(db).collection(c).insertMany(docs.map(d => ({ ...d })));
    const out = path.join(outDir, 'httpdiff-' + name + '.json');
    execFileSync(process.execPath, [path.join(__dirname, 'v1-http-differential-child.js'), tree, MONGO + '/' + db, reqFile, out],
      { stdio: ['ignore', 'ignore', 'inherit'], cwd: tree, timeout: 600000 });
    results[name] = JSON.parse(fs.readFileSync(out, 'utf8'));
    await client.db(db).dropDatabase();
  }
  await client.close();
  const byStatus = {};
  let same = 0, differ = 0, docs = 0;
  const diffs = [];
  // Express's default error page carries a stack trace, whose file paths and
  // line numbers name the tree, not the answer: compare its first line only.
  const norm = r => r && r.type === 'text/html' && typeof r.text === 'string'
    ? Object.assign({}, r, { text: r.text.replace(/^[\s\S]*?<pre>/, '').split('<br>')[0] }) : r;
  let htmlNormalised = 0;
  for (const u of reqs) {
    if (results.dev[u] && results.dev[u].type === 'text/html') htmlNormalised++;
    const a = JSON.stringify(norm(results.dev[u])), b = JSON.stringify(norm(results.branch[u]));
    const s = results.dev[u] && results.dev[u].status;
    byStatus[s] = (byStatus[s] || 0) + 1;
    if (Array.isArray(results.dev[u] && results.dev[u].body)) docs += results.dev[u].body.length;
    if (a === b) same++; else { differ++; diffs.push({ u, a: a && a.slice(0, 300), b: b && b.slice(0, 300) }); }
  }
  console.log(`HTTP differential: ${reqs.length} GET requests, dev tree vs branch tree, identical seeded databases`);
  console.log(`  identical responses (status, content type, body): ${same}/${reqs.length}`);
  console.log(`  DIFFERING: ${differ}`);
  console.log(`  (${htmlNormalised} Express HTML error pages compared on their first line; their stacks name the tree)`);
  console.log(`  dev status mix: ${JSON.stringify(byStatus)}; documents returned in array bodies: ${docs}`);
  for (const d of diffs.slice(0, 10)) console.log(`\n  ${d.u}\n    dev    ${d.a}\n    branch ${d.b}`);
  process.exit(differ ? 1 : 0);
})().catch(e => { console.error(e); process.exit(2); });
