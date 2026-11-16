'use strict';
// Profile fixture serialized from actual app intake-profile constructor at
// 6a31159242825eba54c0d9d6d6b384ea79fefe0c; no runtime/private brand imported.
const assert=require('node:assert/strict'),{createHash}=require('node:crypto'),oracle=require('./completed-oracle.cjs');
const profile={
  "binding": {
    "protocol": "pgstream-intake-v1",
    "codec": "canonical-maintenance-active-plus2-v1",
    "generationDomain": "positive-int8-complete-pair-max-4611686018427387902-v1",
    "controlReads": {
      "schema_migrations": [
        "name",
        "checksum",
        "applied_at"
      ],
      "tenant_lifecycle_windows": [
        "tenant_id",
        "lock_key",
        "phase",
        "generation",
        "claim_id",
        "artifact_digest"
      ],
      "tenant_lifecycle_operations": [
        "tenant_id",
        "operation_id",
        "generation",
        "finished",
        "owner_pid",
        "owner_birth"
      ]
    },
    "workCatalogueRead": [
      "name",
      "checksum"
    ],
    "policy": "active-or-suspended-metadata-v1",
    "namespace": "synthetic_checkpoint",
    "membershipNamespace": "synthetic_members",
    "lifecycleNamespace": "synthetic_lifecycle",
    "role": "synthetic_intake",
    "consumer": "evaluator-sample",
    "revision": "9007199254740993",
    "members": 2,
    "tenants": [
      "11111111-1111-4111-8111-111111111111",
      "22222222-2222-4222-8222-222222222222"
    ]
  },
  "digest": "8e99991d2a912905cbd913b0311bfe10e42fc5d7fe628be3ed347744034db652",
  "contractDigest": "46b8c4946f85e874de42ef0569075834324ebc227e12ae48d4c6689ae2fe14a6",
  "ownerKey": "4339106612025820569",
  "assignment": {
    "rule": "sha256-modulo-v1",
    "members": 2,
    "revision": "9007199254740993",
    "tenants": [
      "11111111-1111-4111-8111-111111111111",
      "22222222-2222-4222-8222-222222222222"
    ]
  }
};
const selected={kind:'evaluator-work-v2',pair:{core:'1'.repeat(40),deploy:'2'.repeat(40)},imageId:'sha256:'+'3'.repeat(64),instrument:'4'.repeat(64)};
const ns={clock:'synthetic_clock',checkpoint:'synthetic_checkpoint',entries:'synthetic_entries'};
const evaluator={pgstream:{},consumer:'evaluator-sample',postgres:{namespaces:ns},trustedWorker:{activity:'synthetic_lifecycle'},selectedIntake:{profile,workers:['evaluator_0','evaluator_1']}};
const realtime={completedOutput:{namespace:ns.checkpoint,consumer:evaluator.consumer},trustedWorker:{activity:'synthetic_lifecycle'},intakeProfile:profile};
const config=oracle.source(evaluator,realtime,selected),tenant=profile.binding.tenants[0],doc={_id:'synthetic-id',date:123456789,sgv:123},sgv={_id:doc._id,mills:doc.date,mgdl:doc.sgv},witness={tenant,date:doc.date,stamp:'9007199254740993'},observed=[witness.stamp,null,null,null,null,null],map={clock:witness.stamp};
const ordinal=Number(createHash('sha256').update(tenant).digest().readBigUInt64BE(0)%2n);
const row={tenant,stamp:witness.stamp,reader:structuredClone(config.binding),stored:[doc],typed:{version:2,contractDigest:profile.contractDigest,observed,completed:observed,identity:'5'.repeat(64),digest:'6'.repeat(64),revision:'1',generation:'7',enabled:true,arrayBounds:true,bodyMetadataAbsent:true,ownerOrdinal:ordinal,assignmentRevision:profile.binding.revision,installedProfile:{consumer:config.consumer,binding:profile.binding,digest:profile.digest,contractDigest:profile.contractDigest}},state:{kind:'evaluator-work-v2',observed:map,completed:map,output:{tenant,identity:'5'.repeat(64),inputCheckpoint:witness.stamp,outputRevision:1,contentDigest:'6'.repeat(64),restoreGeneration:'7',result:{properties:{bgnow:{mean:123,last:123,mills:doc.date,sgvs:[sgv]}}},rows:[{domain:'entries',doc}],frame:{sgvs:[sgv]}}}};
const clients=[0,1].map(socket=>({socket,connects:1,sgv})),assess=r=>oracle.assess(r,witness,clients,2,config),green=()=>assert.equal(assess(row).ready,true);
green();assert(Object.isFrozen(config)&&Object.isFrozen(config.selection.profile.binding.tenants));assert.equal(oracle.assess(row,witness,clients,2,oracle.prepare(JSON.parse(JSON.stringify(config)))).ready,true);
for(const [name,mutate,code] of [
 ['legacy digest in selected row',r=>r.typed.contractDigest=createHash('sha256').update(JSON.stringify(['evaluator-work-v2',ns.checkpoint,evaluator.consumer])).digest('hex'),'TYPED_STATE'],
 ['stored digest self-oracle',r=>{r.typed.contractDigest='7'.repeat(64);r.typed.installedProfile.contractDigest=r.typed.contractDigest;},'TYPED_STATE'],
 ['installed profile binding',r=>r.typed.installedProfile.binding.role='foreign_intake','TYPED_STATE'],
 ['installed profile digest',r=>r.typed.installedProfile.digest='0'.repeat(64),'TYPED_STATE'],
 ['installed consumer',r=>r.typed.installedProfile.consumer='evaluator-other-completed','TYPED_STATE'],
 ['wrong owner ordinal',r=>r.typed.ownerOrdinal=1-ordinal,'TYPED_STATE'],
 ['wrong assignment revision',r=>r.typed.assignmentRevision='1','TYPED_STATE'],
 ['missing installed profile',r=>delete r.typed.installedProfile,'TYPED_STATE'],
 ['source mismatch',r=>r.reader.pair.core='8'.repeat(40),'READER_MISMATCH'],
 ['profile provenance mismatch',r=>r.reader.selectedProfile.configurationSha256='8'.repeat(64),'READER_MISMATCH'],
 ['unsupported generation',r=>{r.typed.generation='4611686018427387903';r.state.output.restoreGeneration=r.typed.generation;},'TYPED_STATE']
]){const bad=structuredClone(row);mutate(bad);const result=assess(bad);assert.equal(result.ready,false,name);assert.equal(result.code,'M7_COMPLETION_'+code,name);console.log('EXPECTED_RED',name,result.code);green();}
for(const mutate of [e=>delete e.selectedIntake.profile,e=>e.selectedIntake.profile.digest='0'.repeat(64),e=>e.selectedIntake.profile.binding.codec='unrecognized',e=>e.selectedIntake.profile.binding.generationDomain='caller-max']){const bad=structuredClone(evaluator);mutate(bad);assert.throws(()=>oracle.source(bad,realtime,selected),/M7_COMPLETION_/);green();}
assert.throws(()=>oracle.source(evaluator,{...realtime,intakeProfile:undefined},selected),/M7_COMPLETION_/);
let calls=0;const unsafe=structuredClone(evaluator);Object.defineProperty(unsafe.selectedIntake.profile,'assignment',{enumerable:true,get(){calls++;return{owner(){throw Error('MUST_NOT_CALL');}};}});assert.throws(()=>oracle.source(unsafe,realtime,selected),/PLAIN_VALUE/);assert.equal(calls,0);
const changed=structuredClone(config);changed.selection.profile.contractDigest='0'.repeat(64);assert.throws(()=>oracle.prepare(changed),/SELECTED_PROFILE/);
const query=oracle.query(config,[tenant],'synthetic-run');assert(query.includes('LEFT JOIN "synthetic_checkpoint".pgstream_intake_profile p ON p.consumer=c.consumer'));for(const field of ['ownerOrdinal','assignmentRevision','installedProfile'])assert(query.includes("'"+field+"'"));assert(!/\b(UPDATE|INSERT|DELETE|ALTER|CREATE)\b/.test(query));assert.throws(()=>oracle.query(config,['33333333-3333-4333-8333-333333333333'],'synthetic-run'),/SELECTOR/);
console.log('RESTORED_GREEN selected independent profile/config/source/installed row/ordinal/revision; native SQL NOT RUN');
assert.equal(oracle.progressSnapshot([row],config,[tenant]).rows[0].restoreGeneration,'7');
for(const change of [r=>r.typed.ownerOrdinal=1-ordinal,r=>r.typed.installedProfile.digest='0'.repeat(64)]){
 const bad=structuredClone(row);change(bad);assert.throws(()=>oracle.progressSnapshot([bad],config,[tenant]),/TYPED_STATE/);
 assert.equal(oracle.progressSnapshot([row],config,[tenant]).rows[0].writerClock,witness.stamp);
}
console.log('RESTORED_GREEN selected opportunity metadata retains exact installed profile/owner/generation validation; no native collection');
