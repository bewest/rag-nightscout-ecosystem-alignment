const { MongoClient } = require(process.env.NM + '/mongodb');
(async () => {
  const c = new MongoClient('mongodb://127.0.0.1:27055'); await c.connect();
  const db = c.db(process.env.DB);
  await db.collection('entries').deleteMany({});
  const n = Number(process.env.N); const now = Date.now(); const docs = [];
  for (let i = 0; i < n; i++) { const t = now - i*300000;
    docs.push({type:'sgv',sgv:Math.round(120+40*Math.sin(i/12)),date:t,dateString:new Date(t).toISOString(),
      device:'synthetic://refute',direction:'Flat',filtered:123456,unfiltered:123456,rssi:100,noise:1,utcOffset:0}); }
  await db.collection('entries').insertMany(docs);
  console.log(process.env.DB, 'n=', await db.collection('entries').countDocuments({}));
  await c.close();
})();
