'use strict';
// Timings only: acceptance to durable output and to each viewer frame. The
// 120 s deadline is judged by assessor.py (decision deadline-from-acceptance).
const fs = require('node:fs');
const path = require('node:path');
const { stats } = require('./durable-lag.cjs');
const contract = 'clinical-timing-from-acceptance-v2';
const deadlineMs = 120000; // bounds how long the probe keeps polling; assessor.py judges the deadline

function shouldPoll(w) {
  return Number.isFinite(w.acceptedMono) && !w.hardClinical &&
    !(w.lastQueryStartMono >= w.acceptedMono + deadlineMs);
}

// Record the last read that found the output absent; it is a lower bound on
// acceptance-to-output. A read that cannot classify the row supplies no bound.
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
  const negative = Math.max(...[w.lastNegativeMono, w.lastNegativeCheckMono].filter(Number.isFinite));
  return {accepted, acceptedAt:w.acked ?? null, acceptedMono:w.acceptedMono ?? null,
    refused:w.evaluatedAt === -1, observationProblem:w.hardClinical || null,
    requestToAcceptanceMs:accepted ? w.acceptedMono-w.sentMono : null,
    acceptanceToCompletionMs:accepted && durable ? w.sentMono + durable.upperMs - w.acceptedMono : null,
    acceptanceToCompletionLowerMs:accepted && Number.isFinite(negative) ? Math.max(0, negative - w.acceptedMono) : null,
    acceptanceToFrameMs:accepted ? matched.map(f => f.atMono - w.acceptedMono) : [],
    expectedFrames:w.expectedSockets.length, matchedFrames:matched.length, durableObserved:!!durable,
    semanticReady:!!w.semantic?.ready,
    delivered:!!(w.semantic?.ready && durable && new Set(matched.map(f => f.socket)).size === wanted.size)};
}

function summary(witnesses) {
  const timings = witnesses.map(w => w.clinicalTiming);
  return {contract, witnesses:timings.length, accepted:timings.filter(t => t.accepted).length,
    durableObserved:timings.filter(t => t.durableObserved && t.accepted).length,
    delivered:timings.filter(t => t.delivered).length,
    expectedFrames:timings.reduce((n,t) => n+t.expectedFrames,0),
    matchedFrames:timings.reduce((n,t) => n+t.matchedFrames,0),
    acceptanceToCompletionMs:stats(timings.map(t => t.acceptanceToCompletionMs).filter(Number.isFinite)),
    acceptanceToFrameMs:stats(timings.flatMap(t => t.acceptanceToFrameMs)),
    scope:'HTTP 200 acknowledgement to first observed durable clinical output and matched viewer callbacks; signed frame delays include callbacks before acknowledgement'};
}

function checkpoint(directory, witnesses, pending) {
  const rows = witnesses.map(w => {
    const clientObservations = [...(pending.get(w.tenant+':'+w.date)?.clientFrames?.values() || [])];
    const clinicalTiming = assess(w, clientObservations);
    return {tenant:w.tenant,date:w.date,acceptedAt:w.acked,requestToAcceptanceMs:clinicalTiming.requestToAcceptanceMs,
      clientObservations,clinicalTiming};
  });
  const dest = path.join(directory,'clinical-witnesses-partial.json');
  fs.writeFileSync(dest+'.new',JSON.stringify({clinicalTiming:summary(rows),witnesses:rows,partial:true}),{mode:0o600});
  fs.renameSync(dest+'.new',dest);
}

module.exports = {contract, deadlineMs, assess, observe, summary, shouldPoll, checkpoint};
