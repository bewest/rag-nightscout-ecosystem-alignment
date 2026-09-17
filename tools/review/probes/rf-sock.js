// Connect to a live NS, capture dataUpdate payloads, report the shape of remove deltas.
const io=require(process.argv[3]+'/node_modules/socket.io-client');
const SEC=require('crypto').createHash('sha1').update(process.env.NS_HARNESS_SECRET||(()=>{throw new Error('set NS_HARNESS_SECRET')})()).digest('hex');
const port=Number(process.argv[2]);
const s=io('http://127.0.0.1:'+port,{transports:['websocket','polling']});
let n=0;
s.on('connect',()=>{ s.emit('authorize',{client:'web',secret:SEC,history:48},()=>{console.log('AUTHORIZED')}); });
s.on('dataUpdate',d=>{
  n++;
  const t=d.treatments||[];
  const acts=t.filter(x=>x.action).map(x=>({_id:x._id,action:x.action}));
  console.log(`#${n} delta=${!!d.delta} treatments=${t.length} actions=${JSON.stringify(acts)} sgvs=${(d.sgvs||[]).length}`);
  if(n>=1 && process.env.DUMPIDS && !d.delta){ console.log('FULLSET_IDS', t.slice(-5).map(x=>x._id).join(',')); console.log('FULLSET_COUNT', t.length); }
});
setTimeout(()=>{console.log('DONE');process.exit(0);}, Number(process.env.WAIT||60000));
