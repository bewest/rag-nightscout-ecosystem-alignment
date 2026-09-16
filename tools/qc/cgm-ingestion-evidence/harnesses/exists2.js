const {MongoClient}=require('/home/bewest/src/rag-nightscout-ecosystem-alignment/externals/work/crm-bf-reads/node_modules/mongodb');
(async()=>{
 for (const port of [27044,27033,27032,27031,27023,27018,27019]) {
  let c;
  try{
   c=new MongoClient(`mongodb://127.0.0.1:${port}`,{serverSelectionTimeoutMS:1200});
   await c.connect();
   const db=c.db('bf32_exists_probe_scratch');
   const v=(await db.admin().serverStatus()).version;
   const col=db.collection('probe');
   await col.deleteMany({}); await col.insertMany([{_id:1,sgv:100},{_id:2}]);
   const out={};
   for (const [label,op] of [['true',true],['false',false],['"true"',"true"],['"false"',"false"],['NaN',NaN],['0',0],['""',""]])
     out[label]=(await col.find({sgv:{$exists:op}}).project({_id:1}).toArray()).map(d=>d._id);
   console.log('port',port,'mongod',v,JSON.stringify(out));
   await col.drop(); await c.close();
  }catch(e){ if(c) try{await c.close()}catch(_){}; console.error('port',port,'skip:',e.message.slice(0,40)); }
 }
})();
