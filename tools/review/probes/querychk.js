const root = process.argv[2];
const q = require(root + '/lib/server/query');
const qs = require(root + '/node_modules/qs');
const cases = [
  ['treatments', 'find[insulin][$gte]=1.5'],
  ['treatments', 'find[carbs][$gte]=7.5'],
  ['treatments', 'find[isValid][$eq]=false'],
  ['treatments', 'find[notes][$exists]=false'],
  ['entries',    'find[sgv][$exists]=false'],
  ['entries',    'find[sgv][$type]=2'],
  ['entries',    'find[device][$regex]=^xDrip'],
  ['devicestatus','find[openaps.iob.iob][$gte]=0.5'],
];
// mirror what lib/server/<col>.js passes, per branch
const optsFor = {
  treatments: root.includes('coercion')
    ? { collection:'treatments', walker: { notes: q.parseRegEx, eventType: q.parseRegEx, enteredBy: q.parseRegEx } }
    : { walker: { insulin: parseInt, carbs: parseInt, glucose: parseInt, notes: q.parseRegEx, eventType: q.parseRegEx, enteredBy: q.parseRegEx } },
  entries: root.includes('coercion')
    ? { collection:'entries', useEpoch:true }
    : { walker: { date: parseInt, sgv: parseInt, filtered: parseInt, unfiltered: parseInt, rssi: parseInt, noise: parseInt, mbg: parseInt }, useEpoch:true },
  devicestatus: root.includes('coercion')
    ? { collection:'devicestatus', dateField:'created_at' }
    : { dateField:'created_at' },
};
for (const [col, s] of cases) {
  const params = qs.parse(s);
  const out = q(params, Object.assign({}, optsFor[col]));
  const shown = JSON.parse(JSON.stringify(out, (k,v)=> v instanceof RegExp ? 'RegExp('+v+')' : v));
  delete shown.date; delete shown.created_at;
  console.log(`${root.split('/').pop().padEnd(16)} ${col}?${s}`.padEnd(70), '->', JSON.stringify(shown));
}
