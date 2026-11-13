const {execFileSync,spawnSync}=require('node:child_process');
const {randomBytes}=require('node:crypto');
const fs=require('node:fs');
const tag=randomBytes(5).toString('hex'), name='ns-registry-review-pg-'+tag;
const env={...process.env, POSTGRES_PASSWORD:randomBytes(24).toString('hex'), POSTGRES_DB:'registry_test'};
const image='postgres@sha256:5db6dac2ef5dcff512f4f00a009c3c332b9f2f28f24277175bf3e4a3d02ef83a';
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
(async()=>{let started=false;try{
 execFileSync('docker',['run','--rm','-d','--name',name,'-p','127.0.0.1::5432','-e','POSTGRES_PASSWORD','-e','POSTGRES_DB',image],{env,stdio:['ignore','pipe','pipe']});started=true;
 for(let i=0;i<120;i++){try{execFileSync('docker',['exec',name,'pg_isready','-U','postgres','-d','registry_test'],{stdio:'ignore'});break;}catch{await sleep(250);}}
 const port=execFileSync('docker',['port',name,'5432/tcp']).toString().trim().split(':').pop();
 const uri=new URL('postgres://postgres@127.0.0.1:'+port+'/registry_test');uri.password=env.POSTGRES_PASSWORD;
 const {Client}=require(process.cwd()+'/node_modules/pg'); let ready=false;
 for(let i=0;i<120;i++){const check=new Client({connectionString:uri.href,connectionTimeoutMillis:500});try{await check.connect();await check.query('SELECT 1');ready=true;break;}catch{await sleep(250);}finally{await check.end().catch(()=>{});}}
 if(!ready)throw new Error('Owned PostgreSQL external TCP readiness expired');
 const tests=process.argv.slice(2);
 const childEnv={...process.env,NS_TEST_POSTGRES_ADMIN_URI:uri.href,NS_VAULT_DOCKER_TEST:'1'};
 const result=spawnSync('node',['node_modules/mocha/bin/mocha.js','--fail-zero','--reporter','dot','--timeout','30000',...tests],{env:childEnv,encoding:'utf8',timeout:300000,maxBuffer:2**24});
 const out=(result.stdout||'')+(result.stderr||'');fs.writeFileSync('/tmp/sharding-native-current.log',out);console.log(out.slice(-5000));if(result.error)console.log(result.error.message);process.exitCode=result.status??1;
}finally{if(started)execFileSync('docker',['rm','-f','-v',name],{stdio:'ignore'});}})();
