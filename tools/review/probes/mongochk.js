const { MongoClient } = require('/home/bewest/src/rag-nightscout-ecosystem-alignment/externals/cgm-remote-monitor-official/node_modules/mongodb');
(async () => {
  const c = new MongoClient('mongodb://127.0.0.1:27018');
  await c.connect();
  const db = c.db('probe_readlens');
  const col = db.collection('t');
  await col.deleteMany({});
  await col.insertMany([{n:1, sgv:100},{n:2},{n:3, sgv:120},{n:4},{n:5, sgv:90}]);
  console.log('buildInfo', (await db.admin().serverStatus()).version);
  console.log('limit(0)   ->', (await col.find({}).limit(0).toArray()).length, 'docs (collection has 5)');
  console.log('limit(2)   ->', (await col.find({}).limit(2).toArray()).length);
  console.log('limit(parseInt("abc")=NaN) ->', await (async()=>{try{return (await col.find({}).limit(parseInt('abc')).toArray()).length}catch(e){return 'THROWS: '+e.message}})());
  console.log('limit(parseInt("-3")=-3)   ->', await (async()=>{try{return (await col.find({}).limit(-3).toArray()).length}catch(e){return 'THROWS: '+e.message}})());
  for (const v of [false, 'false', 0, '0', '', true, 'true']) {
    const r = await col.find({sgv:{$exists:v}}).project({n:1,_id:0}).toArray();
    console.log(`$exists: ${JSON.stringify(v)} -> n=`, r.map(x=>x.n).join(','));
  }
  console.log('$gte "1.5" as parseInt->1 vs 1.5:');
  await col.deleteMany({}); await col.insertMany([{n:'a',insulin:1.0},{n:'b',insulin:1.2},{n:'c',insulin:2.0}]);
  console.log('  insulin $gte 1   ->', (await col.find({insulin:{$gte:1}}).toArray()).map(x=>x.n).join(','));
  console.log('  insulin $gte 1.5 ->', (await col.find({insulin:{$gte:1.5}}).toArray()).map(x=>x.n).join(','));
  console.log('  insulin $gte "1.5" (string) ->', (await col.find({insulin:{$gte:'1.5'}}).toArray()).map(x=>x.n).join(',') || '(none)');
  await col.drop(); await c.close();
})().catch(e=>{console.error('ERR', e.message); process.exit(1)});
