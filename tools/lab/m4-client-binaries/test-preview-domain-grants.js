'use strict';
// Offline source/recording protocol only; no PostgreSQL, client binary, socket,
// build, Docker or server execution. Select the exact application source explicitly.
const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const fs = require('node:fs');
const vm = require('node:vm');
const { createRequire } = require('node:module');
const grants = require('./preview-domain-grants');
const source = process.env.NS_M4_FIXTURE_SOURCE;
if (!source) throw new Error('NS_M4_FIXTURE_SOURCE must name the selected application source');
const load = file => require(path.join(source, file));
const builder = load('lib/tenant-lifecycle/tenant-insertion-sql');
const readiness = load('lib/storage/postgres-insertion-readiness');
const domainCatalogue = load('lib/server/serve/postgres-domains');
const options = { logical: 'entries', namespace: 'preview_data', role: 'preview_app' };

// Authored SQL-shaped metadata is a recording fixture, not database evidence.
function metadata (namespace, domain, statements) {
  const binding = "tenant_id=NULLIF(current_setting('app.current_tenant_id',true),'')::uuid";
  const policy = [{ command: '*', permissive: true, roles: ['0'], using: binding, check: binding }];
  const structure = { clinical_secured: true, counter_secured: true, independent: true, same_owner: true, owns: false,
    plain_ordinal: true, counter_columns: [{name:'tenant_id',type:'uuid',required:true,identity:'',generated:''},
      {name:'last_ordinal',type:'bigint',required:true,identity:'',generated:''}],
    body: builder.effectiveFunctionBody({namespace,domain}), definer:false, volatility:'v', config:['search_path=pg_catalog'],
    language:'plpgsql',trigger_function:true,triggers:[{name:'tenant_insertion_allocate',enabled:'O',type:23,internal:false,function:true,args:0,conditional:false}],
    counter_policies:policy,clinical_policies:policy,unique_order:true,counter_primary:true,no_sequence:true,
    counter_checks:[{expression:'last_ordinal>=0',validated:true}],ordinal_checks:[{expression:'insertion_ordinal>0',validated:true}]};
  const acl = { owns:false,elevated:false,creates:false,clinical_reads:false,clinical_writes:false,clinical_inputs:false,
    explicit_ordinal:false,clinical_extra:false,clinical_mutates:false,counter_reads:false,counter_writes:false,
    counter_extra:false,counter_deletes:false,counter_mutates:false,executes:false };
  const table = namespace + '.' + domain;
  for (const sql of statements) {
    if (sql === `GRANT SELECT, INSERT, UPDATE, DELETE ON ${table} TO preview_app`) Object.assign(acl,{clinical_reads:true,clinical_writes:true,clinical_inputs:true,explicit_ordinal:true,clinical_mutates:true});
    else if (sql === `GRANT SELECT, UPDATE, DELETE ON ${table} TO preview_app`) Object.assign(acl,{clinical_reads:true,clinical_writes:true,clinical_mutates:true});
    else if (sql === `REVOKE INSERT ON "${namespace}"."${domain}" FROM "preview_app"`) Object.assign(acl,{clinical_inputs:false,explicit_ordinal:false});
    else if (sql === `REVOKE INSERT (insertion_ordinal) ON "${namespace}"."${domain}" FROM "preview_app"`) acl.explicit_ordinal=false;
    else if (sql === `GRANT INSERT (tenant_id,id_kind,doc) ON "${namespace}"."${domain}" TO "preview_app"`) acl.clinical_inputs=true;
    else if (sql === `GRANT EXECUTE ON FUNCTION "${namespace}"."allocate_tenant_insertion_ordinal"() TO "preview_app"`) acl.executes=true;
    else if (sql === `GRANT SELECT ON "${namespace}"."tenant_insertion_ordinal" TO "preview_app"`) acl.counter_reads=true;
    else if (sql === `GRANT INSERT (tenant_id,last_ordinal), UPDATE (last_ordinal) ON "${namespace}"."tenant_insertion_ordinal" TO "preview_app"`) Object.assign(acl,{counter_writes:true,counter_mutates:true});
    else if (sql === `GRANT USAGE ON ALL SEQUENCES IN SCHEMA ${namespace} TO preview_app`) { /* legacy grant cannot supply counter authority */ }
    else if (sql === builder.build({namespace,domain}).verifyGrants('preview_app')) { /* actual SQL verified by native runner; source oracle below is independent */ }
    else throw new Error('Unexpected fixture grant statement: ' + sql);
  }
  return {acl,connection:{async query(sql){
    if(sql.includes('tenant-insertion-structure'))return {rows:[structure]};
    if(sql.includes('tenant-insertion-effective-acl'))return {rows:[acl]};
    throw new Error('Unexpected readiness query');
  }}};
}

test('selected counter catalogue uses exact serving builder without explicit ordinal or sequence grants', async () => {
  for(const logical of ['entries','food']) {
    const namespace='preview_'+logical,catalogue=domainCatalogue.get(logical).catalogue;
    const actual=grants({load,catalogue,logical,namespace,role:'preview_app'}),selected=builder.build({namespace,domain:logical});
    assert.deepEqual(actual,[`GRANT SELECT, UPDATE, DELETE ON ${namespace}.${logical} TO preview_app`,...selected.servingGrants('preview_app'),selected.verifyGrants('preview_app')]);
    assert.equal(actual.some(sql=>/^GRANT.*SEQUENCES/.test(sql)),false);
    assert.equal(actual.some(sql=>/^GRANT INSERT \(tenant_id,id_kind,doc,insertion_ordinal\)/.test(sql)),false);
    await readiness.metadata(metadata(namespace,logical,actual).connection,{namespace,domain:logical});
  }
});

test('old broad grants refuse actual selected readiness; repaired grants restore admission and missing counter rights still refuse', async () => {
  const catalogue=domainCatalogue.get('entries').catalogue;
  const old=[`GRANT SELECT, INSERT, UPDATE, DELETE ON preview_data.entries TO preview_app`,'GRANT USAGE ON ALL SEQUENCES IN SCHEMA preview_data TO preview_app'];
  await assert.rejects(readiness.metadata(metadata('preview_data','entries',old).connection,{namespace:'preview_data',domain:'entries'}),{code:'TENANT_INSERTION_ADMISSION_REFUSED'});
  const repaired=grants({load,catalogue,...options});
  await readiness.metadata(metadata('preview_data','entries',repaired).connection,{namespace:'preview_data',domain:'entries'});
  const noCounter=repaired.filter(sql=>!sql.startsWith('GRANT INSERT (tenant_id,last_ordinal)'));
  await assert.rejects(readiness.metadata(metadata('preview_data','entries',noCounter).connection,{namespace:'preview_data',domain:'entries'}),{code:'TENANT_INSERTION_ADMISSION_REFUSED'});
  const unsafe=metadata('preview_data','entries',repaired);unsafe.acl.explicit_ordinal=true;
  await assert.rejects(readiness.metadata(unsafe.connection,{namespace:'preview_data',domain:'entries'}),{code:'TENANT_INSERTION_ADMISSION_REFUSED'});
  await readiness.metadata(metadata('preview_data','entries',repaired).connection,{namespace:'preview_data',domain:'entries'});
});

test('legacy catalogue retains original grants without loading newer helper; malformed catalogues never fall back', () => {
  const current=domainCatalogue.get('entries').catalogue;
  const legacy={...current,migrations:current.migrations.filter(file=>!file.operation)};
  const oldLoad=file=>{assert.equal(file,'lib/migrations/catalogue');return load(file);};
  assert.deepEqual(grants({load:oldLoad,catalogue:legacy,...options}),[
    'GRANT SELECT, INSERT, UPDATE, DELETE ON preview_data.entries TO preview_app',
    'GRANT USAGE ON ALL SEQUENCES IN SCHEMA preview_data TO preview_app']);
  const bad=structuredClone(current);bad.migrations.at(-1).checksum='0'.repeat(64);
  assert.throws(()=>grants({load,catalogue:bad,...options}),/checksum/i);
  assert.throws(()=>grants({load,catalogue:current,...options,logical:'food'}),/domain mismatch/);
});

test('actual lab bootstrap consumes selected grant helper, rather than retaining legacy SQL beside it', async () => {
  const filename=path.join(__dirname,'lab.js'),local=createRequire(filename),script=fs.readFileSync(filename,'utf8');
  const calls=[],stop=new Error('stop after domain grant application');let current;
  const admin={async connect(){},async query(sql){
    if(sql.startsWith('GRANT SELECT ON ALL TABLES IN SCHEMA preview_auth'))throw stop;
    calls.push(sql);return {rows:[]};
  }};
  const cp={execFileSync(cmd,args){
    if(cmd!=='docker')throw new Error('unexpected subprocess');
    if(args[0]==='port')return '127.0.0.1:12345';
    if(args[0]==='run'||args[0]==='exec')return '';
    throw new Error('unexpected Docker protocol');
  },spawn(){throw new Error('server execution forbidden');},spawnSync(){throw new Error('subprocess forbidden');}};
  const sandbox={module:{exports:{}},__dirname,__filename:filename,URL,console,process:{env:{}},require(name){
    if(name==='node:child_process')return cp;
    if(name===path.join(source,'node_modules/pg'))return {Client:class{constructor(){return admin;}}};
    if(name===path.join(source,'lib/migrations/postgres'))return {run:async()=>{}};
    return local(name);
  }};
  vm.runInNewContext(script,sandbox,{filename});
  await assert.rejects(sandbox.module.exports.Lab.prototype.openPreview.call({opt:{worktree:source},custody:{names:{postgres:'synthetic_pg',vault:'synthetic_vault'},stage:()=> 'a'.repeat(64),start:()=>{}},containers:[],state:'/unused'}),error=>error===stop);
  for(const logical of ['entries','food']){
    current=logical==='entries'?'preview_data':'preview_food';
    const expected=grants({load,catalogue:domainCatalogue.get(logical).catalogue,logical,namespace:current,role:'preview_app'});
    const domainCalls=calls.filter(sql=>sql.includes(`ON ${current}.${logical} TO preview_app`) ||
      sql.includes(`"${current}"."${logical}"`) || sql.includes(`"${current}"."tenant_insertion_ordinal"`) || sql.includes(`"${current}"."allocate_tenant_insertion_ordinal"`));
    await readiness.metadata(metadata(current,logical,domainCalls).connection,{namespace:current,domain:logical});
    assert(expected.every(sql=>calls.includes(sql)),'ACTUAL_LAB_USES_SELECTED_SERVING_GRANTS');
  }
});
