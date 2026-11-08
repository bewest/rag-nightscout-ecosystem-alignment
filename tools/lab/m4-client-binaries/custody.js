'use strict';

// M4's fixed default-client fixture custody. This is not a general Docker runner.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const cp = require('node:child_process');
const assert = require('node:assert/strict');
const LABEL = 'org.nightscout.m4.custody';
const PROFILE = 'm4-cgmsim-oref0-v1';
const SELECTORS={postgres:'postgres:16',mongo:'mongo:8.0.34',vault:'hashicorp/vault@sha256:962a92876e168d68eaaa24b0b8b49bbce1cb63024060a67bba95cd158a366fc2',client:'m4-client-lab:node22-jq'};
const ID = /^[a-f0-9]{64}$/;
const canonical = value => value && typeof value === 'object' ? Array.isArray(value)
  ? value.map(canonical) : Object.fromEntries(Object.keys(value).sort().map(key => [key, canonical(value[key])])) : value;
const digest = value => crypto.createHash('sha256').update(JSON.stringify(canonical(value))).digest('hex');
const same = (a, b) => digest(a) === digest(b);
const endpoints = row => ({ profile: 'stable-network-settings-v1', Ports: row.NetworkSettings.Ports,
  Networks: row.NetworkSettings.Networks, SandboxID: row.NetworkSettings.SandboxID });
function identity (row) {
  assert(row && ID.test(row.Id) && row.Config && row.HostConfig && row.NetworkSettings && Array.isArray(row.Mounts), 'CUSTODY_INSPECT_SHAPE');
  return { id: row.Id, name: row.Name, image: row.Image, created: row.Created,
    config: digest(row.Config), hostConfig: digest(row.HostConfig),
    mounts: row.Mounts.map(m => ({type:m.Type,name:m.Name || null,source:m.Source,destination:m.Destination,rw:m.RW})).sort((a,b)=>a.destination.localeCompare(b.destination)) };
}
function baselineIdentity (row) { return {...identity(row), endpoint: digest(endpoints(row))}; }
function volumeIdentity (row) {
  assert(row && typeof row.Name === 'string' && row.Name && row.Driver && row.CreatedAt, 'CUSTODY_VOLUME_SHAPE');
  return {name:row.Name,driver:row.Driver,created:row.CreatedAt,fingerprint:digest(row)};
}
function create ({ plan, directory, invoke, append, recovery = false } = {}) {
  plan=structuredClone(plan);
  assert(plan && plan.version === 1 && plan.profile === PROFILE && plan.status === 'PARENT_BOUND', 'CUSTODY_PARENT_PLAN_REQUIRED');
  assert(/^[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$/.test(plan.ownerUUID), 'CUSTODY_OWNER');
  assert(plan.dockerExecutable === '/usr/bin/docker' && path.isAbsolute(plan.dockerConfig) &&
    fs.readdirSync(plan.dockerConfig).length === 0, 'CUSTODY_DOCKER_ENDPOINT');
  assert(plan.endpointProfile === 'stable-network-settings-v1', 'CUSTODY_ENDPOINT_PROFILE');
  for (const kind of ['containers','volumes','networks']) assert(Array.isArray(plan.baseline[kind]) && new Set(plan.baseline[kind]).size === plan.baseline[kind].length, 'CUSTODY_BASELINE');
  assert(plan.baseline.containers.length <= 256 && plan.baseline.volumes.length <= 1024 && plan.baseline.networks.length <= 64, 'CUSTODY_BASELINE_CAP');
  assert(Object.keys(plan.images).sort().join(',') === 'client,mongo,postgres,vault' && Object.values(plan.images).every(value => /^sha256:[a-f0-9]{64}$/.test(value)), 'CUSTODY_IMAGE_PINS');
  const prefix = 'm4-' + plan.ownerUUID.replace(/-/g,'').slice(0,12);
  const names = ['postgres','mongo','vault'].map(kind => prefix+'-'+kind).concat(Array.from({length:64},(_,i)=>prefix+'-client-'+String(i).padStart(3,'0')));
  const records = new Map(), volumes = new Map(), used = new Set(), unresolved = new Set(), removing = new Set(); let serial = 0, sequence = 0, initialized = false, fault = false, alreadyClosed = false;
  if(!recovery)fs.mkdirSync(directory, {mode:0o700});
  else assert(fs.lstatSync(directory).isDirectory(),'CUSTODY_RECOVERY_DIRECTORY');
  const receipts=path.join(directory,'receipts');if(!recovery)fs.mkdirSync(receipts,{mode:0o700});
  const ledger = path.join(directory,'custody.jsonl');
  const write = append || (value => {const fd=fs.openSync(ledger,fs.constants.O_WRONLY|fs.constants.O_CREAT|fs.constants.O_APPEND|fs.constants.O_NOFOLLOW,0o600);
    try {const bytes=Buffer.from(JSON.stringify(value)+'\n');assert.equal(fs.writeSync(fd,bytes),bytes.length);fs.fsyncSync(fd);} finally {fs.closeSync(fd);} });
  function save (type, value) {try {write({sequence:++sequence,type,owner:plan.ownerUUID,value});} catch {fault=true;throw new Error('CUSTODY_JOURNAL_FAILED');}}
  const argv = args => [plan.dockerExecutable,'--host','unix:///run/docker.sock','--config',plan.dockerConfig,...args];
  const transport = invoke || ((args, options={}) => {
    const [executable,...rest]=argv(args); const result=cp.spawnSync(executable,rest,{encoding:'utf8',timeout:30000,
      env:{PATH:process.env.PATH,LANG:'C.UTF-8',...options.env},maxBuffer:2*1024*1024});
    if(result.error)throw new Error('CUSTODY_DOCKER_TRANSPORT');
    return {status:result.status,stdout:result.stdout || '',stderr:result.stderr || ''};
  });
  function raw (args, options) {assert(Buffer.byteLength(argv(args).join('\0'))<=131072,'CUSTODY_ARGV_BOUND');return transport(args,options);}
  function run (args, options) {const value=raw(args,options);assert(value.status===0,'CUSTODY_DOCKER_COMMAND');return value.stdout.trim();}
  function inspect (id) {assert(ID.test(id));const rows=JSON.parse(run(['inspect','--type','container',id]));assert(rows.length===1 && rows[0].Id===id,'CUSTODY_RETURNED_ID');return rows[0];}
  function absent (id) {const r=raw(['inspect','--type','container',id]);assert(r.status!==0 && /no such (object|container)/i.test(r.stderr),'CUSTODY_ABSENCE_UNCONFIRMED');}
  function read (args) {
    args=args.slice();
    assert(['info','image','port','exec','ps','volume','network','inspect'].includes(args[0]) &&
      (args[0]!=='image' || args[1]==='inspect') &&
      !(args[0]==='volume' && args[1]!=='ls' && args[1]!=='inspect') &&
      !(args[0]==='network' && args[1]!=='ls' && args[1]!=='inspect'), 'CUSTODY_READ_COMMAND');
    if(args[0]==='image'){
      const selected=args.at(-1),kind=Object.keys(SELECTORS).find(key=>SELECTORS[key]===selected);
      if(kind)args[args.length-1]=plan.images[kind];
      else assert(Object.values(plan.images).includes(selected),'CUSTODY_UNPINNED_IMAGE');
    }
    if(args[0]==='port' || args[0]==='exec'){
      const found=[...records.values()].find(r=>r.id===args[1] || r.name===args[1]);assert(found,'CUSTODY_UNKNOWN_EXEC_TARGET');held(found.id);args[1]=found.id;
    }
    return run(args);
  }
  function initialize () {
    const lines=run(['ps','-a','--no-trunc','--format','{{.ID}} {{.Names}}']).split('\n').filter(Boolean), found=[];
    for(const line of lines){const pair=line.split(' ');assert(pair.length===2 && ID.test(pair[0]),'CUSTODY_INITIAL_INVENTORY');found.push(pair[0]);assert(!names.includes(pair[1]),'CUSTODY_NAME_PREEXISTS');}
    assert(same(found.slice().sort(),plan.baseline.containers.slice().sort()),'CUSTODY_INITIAL_BASELINE');
    save('namespace-absent',{profile:PROFILE,names,baseline:digest(plan.baseline),endpointProfile:plan.endpointProfile});initialized=true;
  }
  function validate (row, spec, name, kind, image) {
    assert(row.State && row.State.Status==='created' && row.State.Running===false && row.State.StartedAt.startsWith('0001-') && row.State.FinishedAt.startsWith('0001-'),'CUSTODY_INITIAL_STOPPED');
    assert(row.Name==='/'+name && row.Image===plan.images[kind] && row.Config.Image===plan.images[kind], 'CUSTODY_NAME_IMAGE');
    assert(same(row.Config.Labels,{...(image.Config.Labels || {}),[LABEL]:plan.ownerUUID,[LABEL+'.kind']:kind}),'CUSTODY_LABEL');
    const expectedEnv=Object.fromEntries((image.Config.Env || []).map(value=>{const i=value.indexOf('=');return [value.slice(0,i),value.slice(i+1)];}));
    Object.assign(expectedEnv,spec.env || {});const actualEnv=Object.fromEntries((row.Config.Env || []).map(value=>{const i=value.indexOf('=');return [value.slice(0,i),value.slice(i+1)];}));
    assert((row.Config.Env || []).length===Object.keys(expectedEnv).length && same(actualEnv,expectedEnv),'CUSTODY_ENV_CONFIG');
    const command=spec.command || image.Config.Cmd || [], entry=image.Config.Entrypoint || [];
    assert(same(row.Config.Cmd || [],command) && same(row.Config.Entrypoint || [],entry),'CUSTODY_ARGV_CONFIG');
    const execution=[...entry,...command];assert(row.Path===execution[0] && same(row.Args || [],execution.slice(1)),'CUSTODY_EXECUTION_ARGV');
    assert(row.Config.User===(spec.user || image.Config.User || '') && row.Config.WorkingDir===(spec.workdir || image.Config.WorkingDir || ''),'CUSTODY_USER_WORKDIR');
    const h=row.HostConfig;assert(h.NetworkMode===(kind==='client'?'host':'bridge') && h.AutoRemove===false && h.Privileged===false &&
      !h.PublishAllPorts && !(h.CapAdd || []).length && !(h.Devices || []).length && !(h.SecurityOpt || []).length,'CUSTODY_HOST_CONFIG');
    assert(same((h.ExtraHosts || []).slice().sort(),(spec.hosts || []).slice().sort()),'CUSTODY_HOST_ALIASES');
    const expectedBinds=spec.mounts || [], destinations=new Set();
    for(const m of expectedBinds){assert(!destinations.has(m.destination));destinations.add(m.destination);
      const actual=row.Mounts.filter(found=>found.Destination===m.destination);assert(actual.length===1 && actual[0].Type==='bind' && actual[0].Source===m.source && actual[0].RW===!m.readOnly,'CUSTODY_MOUNT_CONFIG');}
    const anonymous=row.Mounts.filter(m=>m.Type==='volume');
    assert(row.Mounts.length===expectedBinds.length+anonymous.length && anonymous.length<=4 && anonymous.every(m=>Object.hasOwn(image.Config.Volumes || {},m.Destination)),'CUSTODY_ANONYMOUS_MOUNTS');
    assert(same(Object.keys(h.PortBindings || {}).sort(),(spec.ports || []).slice().sort()),'CUSTODY_PORT_KEYS');
    for(const port of spec.ports || [])assert(h.PortBindings[port].length===1 && h.PortBindings[port][0].HostIp==='127.0.0.1' && h.PortBindings[port][0].HostPort==='','CUSTODY_PORT_BINDING');
  }
  function stage (kind, spec) {
    assert(!recovery && initialized && !fault && ['postgres','mongo','vault','client'].includes(kind),'CUSTODY_NOT_READY');
    assert(unresolved.size===0 && removing.size===0,'CUSTODY_UNRESOLVED_RESOURCE');
    assert(records.size<4 && (kind!=='client' || ![...records.values()].some(r=>r.kind==='client')),'CUSTODY_LIVE_BOUND');
    const name=kind==='client'?names[3+serial++]:prefix+'-'+kind;assert(name && serial<=64 && !used.has(name),'CUSTODY_SERIAL_BOUND');used.add(name);
    const imageRows=JSON.parse(run(['image','inspect',plan.images[kind]]));assert(imageRows.length===1 && imageRows[0].Id===plan.images[kind],'CUSTODY_PINNED_IMAGE');
    const image=imageRows[0],args=['create','--name',name,'--label',LABEL+'='+plan.ownerUUID,'--label',LABEL+'.kind='+kind,'--network',kind==='client'?'host':'bridge'];
    for(const port of spec.ports || [])args.push('-p','127.0.0.1::'+port.split('/')[0]);
    for(const [key,value] of Object.entries(spec.env || {})){assert(/^[A-Z][A-Z0-9_]*$/.test(key) && typeof value==='string');args.push('-e',key);}
    for(const m of spec.mounts || []){assert(path.isAbsolute(m.source) && path.isAbsolute(m.destination) && !/[\n,]/.test(m.source+m.destination) && !m.source.includes('docker.sock'),'CUSTODY_MOUNT_REQUEST');args.push('--mount','type=bind,src='+m.source+',dst='+m.destination+(m.readOnly?',readonly':''));}
    for(const host of spec.hosts || []){assert(/^(one|two|three)\.example\.test:127\.0\.0\.1$/.test(host),'CUSTODY_HOST_ALIAS_REQUEST');args.push('--add-host',host);}
    if(spec.user)args.push('--user',spec.user);if(spec.workdir)args.push('--workdir',spec.workdir);
    if(kind==='mongo')args.push('--ulimit','nofile=64000:64000');
    args.push(plan.images[kind],...(spec.command || []));unresolved.add(name);save('create-intent',{name,kind,argv:digest(args)});
    const id=run(args,{env:spec.env});assert(ID.test(id) && !plan.baseline.containers.includes(id),'CUSTODY_CREATED_ID');
    save('created-uninspected',{name,kind,id});
    const row=inspect(id);validate(row,spec,name,kind,image);const held=identity(row), ownedVolumes=[];
    for(const mount of row.Mounts.filter(m=>m.Type==='volume')){
      assert(!plan.baseline.volumes.includes(mount.Name) && !volumes.has(mount.Name),'CUSTODY_BASELINE_VOLUME');
      const found=JSON.parse(run(['volume','inspect',mount.Name]));assert(found.length===1 && found[0].Name===mount.Name,'CUSTODY_VOLUME_ID');
      const v=volumeIdentity(found[0]);volumes.set(v.name,v);ownedVolumes.push(v);
    }
    const record={name,kind,id,identity:held,volumes:ownedVolumes};save('created-identified',record);records.set(id,record);unresolved.delete(name);return id;
  }
  function receipt (record) {
    const file=path.join(receipts,record.id+'.json'),deadline=Date.now()+8000;
    while(!fs.existsSync(file)){assert(Date.now()<deadline,'CUSTODY_OBSERVER_RECEIPT_TIMEOUT');Atomics.wait(new Int32Array(new SharedArrayBuffer(4)),0,0,10);}
    const fd=fs.openSync(file,fs.constants.O_RDONLY|fs.constants.O_NOFOLLOW);let ack;
    try{assert(fs.fstatSync(fd).size<=4096,'CUSTODY_RECEIPT_BOUND');ack=JSON.parse(fs.readFileSync(fd,'utf8'));}finally{fs.closeSync(fd);}
    assert(ack.owner===plan.ownerUUID && ack.id===record.id && ack.identity===digest(record.identity),'CUSTODY_OBSERVER_RECEIPT');
    save('observer-admitted',{id:record.id,identity:ack.identity});
  }
  function held (id) {assert(!fault && records.has(id),'CUSTODY_UNKNOWN_OR_UNJOURNALED_ID');const r=records.get(id);assert(same(identity(inspect(id)),r.identity),'CUSTODY_IDENTITY_DRIFT');return r;}
  function start (id, attached=false) {const r=held(id);receipt(r);save('start-intent',{id:r.id,attached});if(attached)return argv(['start','--attach',id]);run(['start',id]);held(id);save('started',{id});}
  function finishClient (id, exit) {const r=held(id),row=inspect(id);assert(r.kind==='client' && row.State && row.State.Running===false && row.State.StartedAt && !row.State.StartedAt.startsWith('0001-') &&
    row.State.FinishedAt && !row.State.FinishedAt.startsWith('0001-') && !row.State.Error && Number.isInteger(row.State.ExitCode) && !exit.signal,'CUSTODY_CLIENT_COMPLETION');
    save('client-exited',{id,exit:row.State.ExitCode,transportExit:exit.status});return row.State.ExitCode;}
  function references (name) {const ids=run(['ps','-aq','--no-trunc']).split('\n').filter(Boolean);assert(ids.length<=260 && new Set(ids).size===ids.length && ids.every(id=>ID.test(id)),'CUSTODY_REFERENCE_IDS');
    const refs=[];for(let i=0;i<ids.length;i+=32){const batch=ids.slice(i,i+32),rows=JSON.parse(run(['inspect',...batch]));assert(rows.length===batch.length && new Set(rows.map(r=>r.Id)).size===batch.length && same(rows.map(r=>r.Id).sort(),batch.slice().sort()),'CUSTODY_REFERENCE_EXACT_BATCH');for(const row of rows)if(row.Mounts.some(m=>m.Type==='volume' && m.Name===name))refs.push(row.Id);}return refs;}
  function remove (id) {assert(!fault && records.has(id),'CUSTODY_UNKNOWN_OR_UNJOURNALED_ID');const r=records.get(id);assert(!plan.baseline.containers.includes(id),'CUSTODY_BASELINE_CONTAINER');
    removing.add(id);const current=raw(['inspect','--type','container',id]);
    if(current.status===0){assert(!r.containerAbsent && same(identity(JSON.parse(current.stdout)[0]),r.identity),'CUSTODY_IDENTITY_DRIFT');save('remove-intent',{id});assert(run(['rm','--force',id])===id,'CUSTODY_REMOVE_ID');}
    else assert(/no such (object|container)/i.test(current.stderr),'CUSTODY_ABSENCE_UNCONFIRMED');
    absent(id);save('container-absent',{id});
    for(const v of r.volumes){if(!volumes.has(v.name))continue;const currentVolume=raw(['volume','inspect',v.name]);if(currentVolume.status!==0){assert(recovery && /no such volume/i.test(currentVolume.stderr),'CUSTODY_VOLUME_ABSENCE');volumes.delete(v.name);save('volume-absent',{name:v.name});continue;}const found=JSON.parse(currentVolume.stdout);assert(found.length===1 && same(volumeIdentity(found[0]),v) && !plan.baseline.volumes.includes(v.name),'CUSTODY_VOLUME_DRIFT');assert(references(v.name).length===0,'CUSTODY_VOLUME_REFERENCED');save('volume-remove-intent',{name:v.name});assert(run(['volume','rm',v.name])===v.name,'CUSTODY_VOLUME_REMOVE');const missing=raw(['volume','inspect',v.name]);assert(missing.status!==0 && /no such volume/i.test(missing.stderr),'CUSTODY_VOLUME_ABSENCE');volumes.delete(v.name);save('volume-absent',{name:v.name});}
    records.delete(id);removing.delete(id);return {id,name:r.name,absent:true};}
  function close () {assert(!fault,'CUSTODY_JOURNAL_FAILED');if(alreadyClosed){for(const r of records.values()){absent(r.id);for(const v of r.volumes){const missing=raw(['volume','inspect',v.name]);assert(missing.status!==0 && /no such volume/i.test(missing.stderr),'CUSTODY_VOLUME_ABSENCE');}}return [...records.values()].map(r=>({id:r.id,name:r.name,absent:true}));}const removed=[];for(const id of [...records.keys()].reverse())removed.push(remove(id));assert(records.size===0 && volumes.size===0 && unresolved.size===0,'CUSTODY_UNCLOSED_OR_UNRESOLVED_CREATION');save('closed',{removed:removed.map(r=>r.id),clientSlots:serial});return removed;}
  if(recovery){
    const text=fs.readFileSync(ledger,'utf8');assert(text.endsWith('\n'),'CUSTODY_PARTIAL_JOURNAL');
    for(const line of text.trim().split('\n')){
      const entry=JSON.parse(line);assert(!alreadyClosed && entry.sequence===++sequence && entry.owner===plan.ownerUUID,'CUSTODY_RECOVERY_SEQUENCE');const r=entry.value;
      if(entry.type==='namespace-absent')assert(r.baseline===digest(plan.baseline) && same(r.names,names),'CUSTODY_RECOVERY_BASELINE');
      if(entry.type==='create-intent')unresolved.add(r.name);
      if(entry.type==='created-identified'){
        assert(ID.test(r.id) && !plan.baseline.containers.includes(r.id) && names.includes(r.name) && !records.has(r.id),'CUSTODY_RECOVERY_ID');
        records.set(r.id,r);unresolved.delete(r.name);for(const v of r.volumes){assert(!plan.baseline.volumes.includes(v.name));volumes.set(v.name,v);}
      }
      if(entry.type==='container-absent' && records.has(r.id))records.get(r.id).containerAbsent=true;
      if(entry.type==='volume-absent')volumes.delete(r.name);
      if(entry.type==='closed')alreadyClosed=true;
    }
    if(alreadyClosed)assert(unresolved.size===0 && volumes.size===0 && [...records.values()].every(r=>r.containerAbsent),'CUSTODY_FALSE_CLOSED');
    initialized=true;
  }
  return Object.freeze({initialize,stage,start,finishClient,remove,close,read,argv,identity:()=>({owner:plan.ownerUUID,profile:PROFILE,ledger}),names:Object.freeze({postgres:prefix+'-postgres',mongo:prefix+'-mongo',vault:prefix+'-vault'})});
}
module.exports={create,recover: options=>create({...options,recovery:true}).close(),identity,baselineIdentity,volumeIdentity,digest,PROFILE,LABEL};
