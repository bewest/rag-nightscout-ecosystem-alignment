const {MongoClient}=require('/home/bewest/src/rag-nightscout-ecosystem-alignment/externals/work/crm-bf-reads/node_modules/mongodb');
(async()=>{
 for (const port of [27017,27033,27032]) {
  let c;
  try{
   c=new MongoClient(`mongodb://127.0.0.1:${port}`,{serverSelectionTimeoutMS:1500});
   await c.connect();
   const db=c.db('bf32_exists_probe_scratch');
   const col=db.collection('probe');
   await col.deleteMany({});
   await col.insertMany([{_id:1,sgv:100},{_id:2}]);
   const out={};
   for (const [label,op] of [['true(bool)',true],['false(bool)',false],['"true"',"true"],['"false"',"false"],['NaN',NaN],['0',0],['""',""],['1',1]]) {
     try{ out[label]=(await col.find({sgv:{$exists:op}}).project({_id:1}).toArray()).map(d=>d._id); }
     catch(e){ out[label]='ERROR: '+e.message.slice(0,60); }
   }
   console.log('port',port,'serverVersion?',(await db.admin().serverStatus()).version);
   console.log(JSON.stringify(out,null,1));
   await col.drop();
   await c.close();
   return;
  }catch(e){ if(c) try{await c.close()}catch(_){}; console.error('port',port,'skip:',e.message.slice(0,50)); }
 }
})();
