'use strict';
const NC='/home/bewest/src/rag-nightscout-ecosystem-alignment/externals/nightscout-connect';
const createFetchMachine = require(NC+'/lib/machines/fetch.js');
const { interpret } = require(NC+'/../work/nc-jitter/node_modules/xstate');
const path=require('path');
const axios = require('/home/bewest/src/rag-nightscout-ecosystem-alignment/externals/cgm-remote-monitor-official/node_modules/axios');
const src = require(NC+'/lib/sources/minimedcarelink/index.js');
const log = { debug(){}, error(){}, info(){}, warn(){} };
const impl_real = src({carelinkRegion:'eu',carelinkUsername:'u',carelinkPassword:'p',countryCode:'gb'}, axios, log);

// Real shipping transformer, fed a markers-less payload (as the retired package's
// own recorded CareLink payloads are shaped).
const payload = { medicalDeviceFamily:'PARADIGM', sgs:[{sg:120,datetime:'Oct 17, 2015 09:09:00',kind:'SG'}],
                  lastSG:{sg:120}, lastSGTrend:'UP', lastMedicalDeviceDataUpdateServerTime: Date.now() };

const adapter = {
  align_schedule: impl_real.align_to_glucose,
  dataFromSesssion: () => Promise.resolve(payload),
  transformer: impl_real.transformPayload,
  persister: (d) => { console.log('PERSIST CALLED with', JSON.stringify(d).slice(0,120)); return Promise.resolve(d); }
};
adapter.persister.gap_for = () => Promise.resolve({entries:null,treatments:null,devicestatus:null});

const m = createFetchMachine(adapter, { logger: log, maxRetries: 0, frame_retry_duration: () => 10 });
const svc = interpret(m);
let states=[];
svc.onTransition((s)=>{ states.push(JSON.stringify(s.value)); });
process.on('uncaughtException', (e)=>{ console.log('UNCAUGHT (escaped the state machine):', e.constructor.name+': '+e.message); console.log('states:', states.join(' -> ')); process.exit(0); });
try {
  svc.start();
  svc.send({type:'START'});
  setTimeout(()=>{ console.log('states:', states.join(' -> ')); process.exit(0); }, 400);
} catch (e) {
  console.log('THREW SYNCHRONOUSLY out of interpreter:', e.constructor.name+': '+e.message);
  console.log('states:', states.join(' -> '));
}
