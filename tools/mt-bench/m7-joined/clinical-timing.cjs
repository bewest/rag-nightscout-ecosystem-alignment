'use strict';
const fs = require('node:fs');
const path = require('node:path');
const { stats } = require('./durable-lag.cjs');
const contract = 'clinical-deadline-from-acceptance-v1';
const deadlineMs = 120000;

// Poll the accepted write until its first positive read or one SQL snapshot
// started at/after the deadline. A missing or failed read supplies no bound.
function shouldPoll(w) {
  return Number.isFinite(w.acceptedMono) && !w.hardClinical &&
    !(w.lastQueryStartMono >= w.acceptedMono + deadlineMs);
}

function observe(w, result, start) {
  w.semantic = result;
  if (result.ready) return;
  const pending = ['M7_COMPLETION_PENDING','M7_COMPLETION_OUTPUT_CLOCK','M7_COMPLETION_FRAME',
    'M7_COMPLETION_BG_NOW','M7_COMPLETION_STORED'];
  if (pending.includes(result.code) ||
      result.code === 'M7_COMPLETION_CLIENT' && result.clientFailure === 'M7_CLIENT_COUNT') {
    w.lastNegativeCheckMono = start;
  } else if (!['M7_COMPLETION_READER_MISMATCH','M7_COMPLETION_BINDING','M7_COMPLETION_TYPED_STATE',
               'M7_COMPLETION_CLOCK','M7_COMPLETION_STATE'].includes(result.code)) {
    w.hardClinical = result.clientFailure || result.code;
  }
}

function assess(w, frames) {
  const accepted = Number.isFinite(w.acceptedMono);
  const durable = w.durableObservation;
  const wanted = new Set(w.expectedSockets);
  const matched = frames.filter(f => durable && wanted.has(f.socket) && f.sgv._id === durable.storedId &&
    f.sgv.mills === w.date && Number.isFinite(durable.storedSgv) && f.sgv.mgdl === durable.storedSgv &&
    Number.isSafeInteger(f.connects) && f.connects > 0 && typeof f.transportId === 'string' && f.transportId.length &&
    Number.isFinite(f.atMono) && f.atMono >= w.sentMono);
  const acceptanceToCompletionMs = accepted && durable ? w.sentMono + durable.upperMs - w.acceptedMono : null;
  // The last checked absence bounds how late the durable output could have
  // been from below. A slow SQL response alone supplies only an upper bound.
  const negative = w.lastNegativeMono;
  const acceptanceToCompletionLowerMs = accepted && Number.isFinite(negative) ?
    Math.max(0, negative - w.acceptedMono) : null;
  const acceptanceToFrameMs = accepted ? matched.map(f => f.atMono - w.acceptedMono) : [];
  let verdict = 'UNMEASURED', code = 'M7_CLINICAL_OBSERVATION_INCOMPLETE';
  if (w.evaluatedAt === -1) { verdict = 'FAIL'; code = 'M7_CLINICAL_WRITE_REFUSED'; }
  else if (!accepted) code = 'M7_CLINICAL_ACCEPTANCE_UNMEASURED';
  else if (w.hardClinical) { verdict = 'FAIL'; code = w.hardClinical; }
  else if (acceptanceToCompletionLowerMs >= deadlineMs || acceptanceToFrameMs.some(ms => ms >= deadlineMs) ||
           w.lastNegativeCheckMono - w.acceptedMono >= deadlineMs) {
    verdict = 'FAIL'; code = 'M7_COMPLETION_DEADLINE';
  } else if (acceptanceToCompletionMs >= deadlineMs) {
    code = 'M7_CLINICAL_DEADLINE_UNRESOLVED';
  } else if (w.semantic?.ready && durable && new Set(matched.map(f => f.socket)).size === wanted.size) {
    verdict = 'PASS'; code = null;
  }
  return {verdict, code, accepted, acceptedAt:w.acked ?? null, requestToAcceptanceMs:accepted ? w.acceptedMono-w.sentMono : null,
    acceptanceToCompletionMs, acceptanceToCompletionLowerMs, acceptanceToFrameMs,
    expectedFrames:w.expectedSockets.length, matchedFrames:matched.length, durableObserved:!!durable,
    semanticReady:!!w.semantic?.ready, acceptedMono:w.acceptedMono ?? null};
}

function summary(witnesses) {
  const timings = witnesses.map(w => w.clinicalTiming);
  return {contract, deadlineMs, witnesses:timings.length, accepted:timings.filter(t => t.accepted).length,
    deadlineMisses:timings.filter(t => t.code === 'M7_COMPLETION_DEADLINE').length,
    durableObserved:timings.filter(t => t.durableObserved && t.accepted).length,
    expectedFrames:timings.reduce((n,t) => n+t.expectedFrames,0),
    matchedFrames:timings.reduce((n,t) => n+t.matchedFrames,0),
    acceptanceToCompletionMs:stats(timings.map(t => t.acceptanceToCompletionMs).filter(Number.isFinite)),
    acceptanceToFrameMs:stats(timings.flatMap(t => t.acceptanceToFrameMs)),
    coverage:Object.fromEntries(['PASS','FAIL','UNMEASURED'].map(k => [k,timings.filter(t => t.verdict===k).length])),
    scope:'HTTP 200 acknowledgement to first observed durable clinical output and matched viewer callbacks; signed frame delays include callbacks before acknowledgement'};
}

function checkpoint(directory, witnesses, pending) {
  const rows = witnesses.map(w => {
    const frames = [...(pending.get(w.tenant+':'+w.date)?.clientFrames?.values() || [])];
    const clinicalTiming = assess(w,frames);
    return {tenant:w.tenant,date:w.date,acceptedAt:w.acked,requestToAcceptanceMs:clinicalTiming.requestToAcceptanceMs,clinicalTiming};
  });
  const clinicalTiming = summary(rows);
  const dest = path.join(directory,'clinical-witnesses-partial.json');
  fs.writeFileSync(dest+'.new',JSON.stringify({clinicalTiming,witnesses:rows,partial:true,
    verdict:clinicalTiming.coverage.FAIL ? 'FAIL' : 'UNMEASURED'}),{mode:0o600});
  fs.renameSync(dest+'.new',dest);
}

module.exports = {contract, deadlineMs, assess, observe, summary, shouldPoll, checkpoint};
