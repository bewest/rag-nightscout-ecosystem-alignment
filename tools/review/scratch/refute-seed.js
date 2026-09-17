const { MongoClient } = require(process.env.NM + '/mongodb');
(async () => {
  const c = new MongoClient('mongodb://127.0.0.1:27055');
  await c.connect();
  const db = c.db('refute_ns');
  await db.collection('entries').deleteMany({});
  const now = Date.now();
  const docs = [];
  for (let i = 0; i < 576; i++) {
    const t = now - i * 5 * 60000;
    docs.push({ type: 'sgv', sgv: Math.round(120 + 40 * Math.sin(i / 12)), date: t,
      dateString: new Date(t).toISOString(), device: 'synthetic://refute', direction: 'Flat' });
  }
  for (let i = 0; i < 5; i++) {
    const t = now - i * 3600000 - 1234;
    docs.push({ type: 'mbg', mbg: 100 + i, date: t, dateString: new Date(t).toISOString(), device: 'synthetic://refute' });
  }
  await db.collection('entries').insertMany(docs);
  console.log('seeded', await db.collection('entries').countDocuments({}),
    'with_mbg', await db.collection('entries').countDocuments({ mbg: { $exists: true } }));
  await c.close();
})();
