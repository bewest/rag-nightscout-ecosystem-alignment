const { MongoClient } = require('mongodb');
(async () => {
  const c = new MongoClient('mongodb://127.0.0.1:27017/nsharness_lens');
  await c.connect();
  const db = c.db('nsharness_lens');
  await db.collection('entries').deleteMany({});
  const now = Date.now();
  const docs = [];
  // 48h of synthetic sgv at 5-min cadence = 576 points; pure sine, no patient data
  for (let i = 0; i < 576; i++) {
    const t = now - i * 5 * 60 * 1000;
    docs.push({ type: 'sgv', sgv: Math.round(120 + 60 * Math.sin(i / 12)), date: t,
      dateString: new Date(t).toISOString(), device: 'synthetic://lens', direction: 'Flat' });
  }
  // a handful of mbg and cal so $exists probes have both sides
  for (let i = 0; i < 5; i++) {
    const t = now - i * 3600 * 1000;
    docs.push({ type: 'mbg', mbg: 100 + i, date: t, dateString: new Date(t).toISOString(), device: 'synthetic://lens' });
  }
  await db.collection('entries').insertMany(docs);
  console.log('seeded', await db.collection('entries').countDocuments({}), 'entries; sgv=',
    await db.collection('entries').countDocuments({type:'sgv'}), 'mbg=', await db.collection('entries').countDocuments({type:'mbg'}));
  await c.close();
})();
