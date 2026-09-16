// Measure what filter the count/<storage>/where path actually builds.
// Stubs ctx.store.collection so aggregate()'s pipeline is captured verbatim.
const path = require('path');
const ROOT = process.argv[2];
const MOD  = process.argv[3];   // devicestatus | entries | treatments
const FIND = JSON.parse(process.argv[4]);
const FIND_SNAPSHOT = JSON.stringify(FIND);

let captured = null;
const fakeCollection = {
  aggregate: (pipeline) => { captured = pipeline; return { toArray: async () => [{_id:null,count:0}] }; },
  find: () => ({ sort: () => ({ limit: () => ({ toArray: async () => [] }) }) })
};
const ctx = {
  store: { collection: () => fakeCollection },
  bus: { emit: () => {} },
  moment: require(path.join(ROOT,'node_modules','moment'))
};
const env = { activity_collection: 'activity', devicestatus_collection: 'devicestatus' };

const storage = require(path.join(ROOT,'lib','server',MOD+'.js'));
const api = storage(env.devicestatus_collection || MOD, ctx, env);

if (typeof api.aggregate !== 'function') { console.log('NO_AGGREGATE on '+MOD); process.exit(3); }

api.aggregate({ find: FIND }, function (err) {
  if (err) { console.log('ERR', err.message); process.exit(4); }
  const match = captured[0].$match;
  console.log('MODULE   :', MOD);
  console.log('INPUT    :', FIND_SNAPSHOT);
  console.log('$match   :', JSON.stringify(match));
  for (const k of Object.keys(JSON.parse(FIND_SNAPSHOT))) {
    const v = match[k];
    console.log('  field', k, '->', JSON.stringify(v), ' types:',
      JSON.stringify(v && typeof v === 'object' ? Object.fromEntries(Object.entries(v).map(([a,b])=>[a,typeof b])) : typeof v));
  }
});
