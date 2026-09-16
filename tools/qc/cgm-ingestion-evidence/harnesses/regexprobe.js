const {MongoClient}=require('/home/bewest/src/rag-nightscout-ecosystem-alignment/externals/work/crm-bf-reads/node_modules/mongodb');
(async()=>{
 const c=new MongoClient('mongodb://127.0.0.1:27032',{serverSelectionTimeoutMS:1500});
 await c.connect(); const col=c.db('bf32_exists_probe_scratch').collection('p2');
 await col.deleteMany({}); await col.insertMany([{_id:1,notes:'abc'},{_id:2,notes:'xyz'},{_id:3}]);
 for (const [label,q] of [['regex NaN',{notes:{$regex:NaN}}],['regex "ab"',{notes:{$regex:'ab'}}]]) {
   try{ console.log(label,'->',JSON.stringify((await col.find(q).project({_id:1}).toArray()).map(d=>d._id))); }
   catch(e){ console.log(label,'-> ERROR:',e.message.slice(0,80)); }
 }
 await col.drop(); await c.close();
})();
