'use strict';
// One finite host HTTP/stock-socket child. Private nonce/sequence files are an
// instrument protocol, never a product control API. No command is executable
// data: actions dispatch to this fixed table and unknown messages refuse.
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const need=(ok,code)=>{if(!ok)throw Object.assign(Error(code),{code});};
function read(file,max=1048576){const fd=fs.openSync(file,fs.constants.O_RDONLY|fs.constants.O_NOFOLLOW|fs.constants.O_NONBLOCK);try{const s=fs.fstatSync(fd);need(s.isFile()&&s.uid===process.getuid()&&!(s.mode&0o077)&&s.nlink===1&&s.size<=max,'SESSION_PRIVATE_INPUT');const raw=fs.readFileSync(fd);need(raw.length<=max,'SESSION_INPUT_BOUND');return JSON.parse(raw);}finally{fs.closeSync(fd);}}
async function main(specFile,directory){
 const spec=read(specFile);require('./client.cjs').validate(spec);need(/^[a-f0-9]{32}$/.test(spec.nonce)&&path.isAbsolute(directory)&&fs.realpathSync(directory)===directory,'SESSION_CUSTODY');
 need(!process.env.NODE_OPTIONS&&!process.env.LD_PRELOAD&&!Object.keys(process.env).some(k=>/^(PG|VAULT|NS_CONNECTION_BUDGET_)/.test(k)),'SESSION_PRIVILEGED_ENV');
 need(process.version===spec.hostNodeVersion,'SESSION_NODE_IDENTITY');
 const required=['prime.js','connection-budget-files.js'];
 for(const name of required){const file=path.join(spec.sourceRoot,'deploy/multitenant',name);need(crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex')===spec.sourceHelpers[name],'SESSION_SOURCE_HELPER_CHANGED');}
 const F=require(path.join(spec.sourceRoot,'deploy/multitenant/connection-budget-files')),fd=F.directory(directory);
 let privateWriteBytes=0;const persist=(name,value)=>{privateWriteBytes+=Buffer.byteLength(JSON.stringify(value))+1;need(privateWriteBytes<=268435456,'SESSION_PRIVATE_WRITE_BOUND');return F.writeAt(fd,name,value);};
 const http=require('node:http'),budget=require('./http-budget.cjs').install(http);
 const prime=require(path.join(spec.sourceRoot,'deploy/multitenant/prime'));
 const stock=require('socket.io-client/package.json');need(stock.version==='4.8.3','SESSION_STOCK_SOCKET_VERSION');
 const io=require('socket.io-client').io;let client,seq=0,closed=false,clientClosed=false;const deadline=Date.now()+spec.maximumWallMs;
 const sourceConfig=read(spec.primerConfig),config={...sourceConfig,adminOrigin:spec.endpoints.admin.origin,apiOrigin:spec.endpoints['api-2'].origin};
 need(sourceConfig.seed.length===16&&JSON.stringify(sourceConfig.seed.map(x=>x.id))===JSON.stringify(spec.ids),'SESSION_COMPLETE_ROSTER');
 const api={
  async prime(){const a=await prime.provision(config,spec.clientCustody);const b=await prime.prime(config,spec.clientCustody);const rows=read(path.join(spec.clientCustody,'tenants.json')).tenants,roots=read(path.join(spec.clientCustody,'provisioned.json'));spec.credentials=rows.map(x=>({...x,rootHash:crypto.createHash('sha1').update(roots.find(r=>r.id===x.id).rootSecret).digest('hex')}));client=require('./client.cjs').create(spec,{prime,io,persist});return {provisioned:a.tenants,primed:b.tenants,scope:'source-owned HTTP only'};},
  async history(){need(client,'SESSION_NOT_PRIMED');return client.history();},
  async clinical(){need(client,'SESSION_NOT_PRIMED');return client.clinical();},
  async rebind({endpoints}){need(client,'SESSION_NOT_PRIMED');return client.rebind(endpoints);},
  async storm(){need(client,'SESSION_NOT_PRIMED');return client.firstTouchStorm();},
  async connect({tenants}){need(client&&Array.isArray(tenants)&&tenants.length===2&&new Set(tenants).size===2&&tenants.every(x=>spec.ids.includes(x)),'SESSION_SOCKET_ROSTER');const values=[];for(const id of tenants)values.push({tenant:id,...await client.connect(id)});return values;},
  async writes(){need(client,'SESSION_NOT_PRIMED');let accepted=0;for(const id of spec.ids)for(const field of ['entries','devicestatus','treatments','probe']){const r=await client.write(id,field);if(r.status===200||r.status===201)accepted++;}return {attempted:64,accepted};},
  async socketState({tenant}){need(spec.ids.includes(tenant)&&client,'SESSION_TENANT');return client.socketState(tenant);},
  async healthyB({tenant}){need(spec.ids.includes(tenant)&&client,'SESSION_TENANT');const rounds=[];for(let i=0;i<3;i++){rounds.push(await client.healthyB(tenant));if(i!==2)await new Promise(r=>setTimeout(r,1000));}return{...rounds.at(-1),rounds};},
  async isolation({a,b}){need(spec.ids.includes(a)&&spec.ids.includes(b)&&client,'SESSION_TENANT');return client.isolation(a,b);},
  async close(){need(client,'SESSION_NOT_PRIMED');const result=client.close();clientClosed=true;closed=true;return result;}
 };
 persist('session-ready.json',{nonce:spec.nonce,kind:'native-clinical-http-session',source:spec.source,hostNodeVersion:process.version,stockSocketVersion:stock.version});
 try{
  while(!closed&&Date.now()<deadline){const name='phase-'+String(seq+1).padStart(4,'0')+'.json';if(!F.inspect(fd,name)){await new Promise(r=>setTimeout(r,50));continue;}
   const message=F.readAt(fd,name);need(Object.keys(message).sort().join(',')==='action,args,nonce,sequence'&&message.nonce===spec.nonce&&message.sequence===seq+1&&message.sequence<=16&&Object.hasOwn(api,message.action),'SESSION_MESSAGE');seq++;
   const startedMonotonicNs=process.hrtime.bigint().toString();let result;
   try{result={outcome:'OK',value:await api[message.action](message.args)};need(!budget.snapshot().refused,'CLIENT_HTTP_BUDGET');}
   catch(error){result={outcome:'REFUSED',error:/^[A-Z0-9_]{1,100}$/.test(error.code||'')?error.code:'SESSION_PHASE_REFUSED'};closed=true;}
   F.writeAt(fd,'reply-'+String(seq).padStart(4,'0')+'.json',{nonce:spec.nonce,sequence:seq,action:message.action,startedMonotonicNs,finishedMonotonicNs:process.hrtime.bigint().toString(),...result},{exclusive:true});
   if(result.outcome!=='OK')throw Error('SESSION_PHASE_REFUSED');
  }
  need(closed,'SESSION_DEADLINE');
 }finally{try{if(client&&!clientClosed)client.close();}finally{persist('session-budget.json',budget.snapshot());budget.restore();fs.closeSync(fd);}}
}
module.exports={main,read};
if(require.main===module){main(process.argv[2],process.argv[3]).catch(()=>{process.stderr.write('NATIVE_CLINICAL_SESSION_REFUSED\n');process.exitCode=1;});}
