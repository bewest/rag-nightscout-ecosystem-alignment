'use strict';
// Discovery-only accounting. Record before HTTP; an interrupted open ledger is
// incomplete evidence, never proof of no writes. No credentials or payloads.
function create({ids,runId,persist}) {
  const check=(ok)=>{if(!ok)throw Error('M7_PROBE_ACCOUNTING_INVALID');};
  check(Array.isArray(ids)&&ids.length>0&&ids.length<=10000&&new Set(ids).size===ids.length&&ids.every(id=>typeof id==='string'&&/^[a-zA-Z0-9-]{1,64}$/.test(id)));
  check(typeof runId==='string'&&/^[a-z0-9-]{1,120}$/.test(runId)&&typeof persist==='function');
  const roster=new Set(ids),rows=Object.create(null),pending=new Map();let admissionsClosed=false,attempts=0;
  const snapshot=()=>({version:2,kind:'m7-discovery-probe-accounting',runId,roster:[...ids],admissionsClosed,attempts,byTenant:JSON.parse(JSON.stringify(rows))});
  const save=()=>persist(snapshot());
  save();
  return {
    begin(tenant) {
      check(!admissionsClosed&&roster.has(tenant)&&attempts<100000);
      const row=rows[tenant]||=( {attempts:0,accepted:0,uncertain:0,refused:0,pending:0} );
      const token=++attempts;row.attempts++;row.pending++;pending.set(token,tenant);save();return token;
    },
    settle(token,status) {
      check(pending.has(token)&&Number.isInteger(status)&&(status===0||(status>=100&&status<=599)));
      const row=rows[pending.get(token)];pending.delete(token);row.pending--;
      row[status===200?'accepted':status===0||status>=500?'uncertain':'refused']++;save();
    },
    close() {check(!admissionsClosed);admissionsClosed=true;save();},
    snapshot
  };
}
module.exports={create};
