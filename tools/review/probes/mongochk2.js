const { MongoClient } = require('/home/bewest/src/rag-nightscout-ecosystem-alignment/externals/cgm-remote-monitor-official/node_modules/mongodb');
(async () => {
  const c = new MongoClient('mongodb://127.0.0.1:27018'); await c.connect();
  const col = c.db('probe_readlens').collection('t2');
  await col.deleteMany({});
  await col.insertMany([{n:1,sgv:100},{n:2},{n:3,sgv:120},{n:4},{n:5,sgv:90}]);
  console.log('$exists: NaN ->', (await col.find({sgv:{$exists:NaN}}).project({n:1,_id:0}).toArray()).map(x=>x.n).join(','));
  console.log('$exists: null ->', (await col.find({sgv:{$exists:null}}).project({n:1,_id:0}).toArray()).map(x=>x.n).join(','));

  // tie-heavy sort + skip: does paging repeat/drop?
  const col2 = c.db('probe_readlens').collection('t3');
  await col2.deleteMany({});
  const ts = new Date().toISOString(), d = Date.now();
  const docs = []; for (let i=0;i<400;i++) docs.push({tag:i, created_at: ts, date: d});
  await col2.insertMany(docs);
  const sortNoId = { created_at: -1, date: -1 };
  const sortWithId = { created_at: -1, date: -1, _id: -1 };
  for (const [name, sort] of [['dev (no _id)', sortNoId], ['bf/reads (+_id)', sortWithId]]) {
    const seen = new Set(); let dup = 0;
    for (let skip = 0; skip < 400; skip += 100) {
      const page = await col2.find({}).sort(sort).skip(skip).limit(100).toArray();
      for (const p of page) { if (seen.has(p.tag)) dup++; seen.add(p.tag); }
    }
    console.log(`${name}: distinct=${seen.size}/400 duplicated=${dup} missing=${400-seen.size}`);
  }
  await col.drop(); await col2.drop(); await c.close();
})().catch(e=>{console.error('ERR',e.message);process.exit(1)});
