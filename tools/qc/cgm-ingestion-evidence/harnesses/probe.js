const W = '/home/bewest/src/rag-nightscout-ecosystem-alignment/externals/work/crm-bf-reads';
const q = require(W + '/lib/server/query.js');
const cases = [
  ['devicestatus', {find:{'uploader.battery':{$gte:'50'}}}],
  ['devicestatus', {find:{'pump.reservoir':{$lte:'20'}}}],
  ['treatments',   {find:{duration:{$gte:'30'}}}],
  ['treatments',   {find:{insulin:{$gte:'1.5'}}}],
  ['entries',      {find:{sgv:{$gte:'100'}}}],
  ['entries',      {find:{delta:{$gte:'2'}}}],
  ['entries',      {find:{sgv:{$exists:'true'}}}],
];
const strip = o => { const c = JSON.parse(JSON.stringify(o)); delete c.date; delete c.created_at; delete c.startDate; return c; };
console.log('field'.padEnd(34), 'NO collection (legacy)'.padEnd(30), 'WITH collection:');
for (const [coll, params] of cases) {
  const f = Object.keys(params.find)[0];
  const legacy = strip(q(JSON.parse(JSON.stringify(params)), { dateField: coll==='entries'?'date':'created_at' }));
  const typed  = strip(q(JSON.parse(JSON.stringify(params)), { collection: coll, dateField: coll==='entries'?'date':'created_at' }));
  console.log((coll+'.'+f).padEnd(34), JSON.stringify(legacy[f]).padEnd(30), JSON.stringify(typed[f]));
}
