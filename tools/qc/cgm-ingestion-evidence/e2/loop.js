'use strict';
const NC='/home/bewest/src/rag-nightscout-ecosystem-alignment/externals/nightscout-connect';
const CRM='/home/bewest/src/rag-nightscout-ecosystem-alignment/externals/cgm-remote-monitor-official';
const builder = require(NC+'/lib/builder');
const { interpret } = require(NC+'/../work/nc-jitter/node_modules/xstate');
const axios = require(CRM+'/node_modules/axios');
const src = require(process.env.SRC_PATH || (NC+'/lib/sources/minimedcarelink/index.js'));
const log = { debug(){}, error(m,e){ console.log('LOG.ERROR:', m, e && (e.constructor.name+': '+e.message)); }, info(){}, warn(){} };
const impl = src({carelinkRegion:'eu',carelinkUsername:'u',carelinkPassword:'p',countryCode:'gb'}, axios, log);

const WITH_MARKERS = process.env.WITH_MARKERS === '1';
const payload = { medicalDeviceFamily:'PARADIGM',
  sgs:[{sg:120,datetime:'Oct 17, 2015 09:09:00',kind:'SG'}],
  lastSG:{sg:120}, lastSGTrend:'UP',
  lastMedicalDeviceDataUpdateServerTime: Date.now() };
if (WITH_MARKERS) payload.markers = [];

// Replace only the network steps; keep the SHIPPING transform.
impl.authFromCredentials = () => Promise.resolve({token:'t', expires:new Date(Date.now()+3600e3).toISOString()});
impl.sessionFromAuth = (a) => Promise.resolve({...a, isPatient:true, patientUsername:'p'});
impl.dataFromSesssion = () => Promise.resolve(payload);

let persisted = 0;
const known = { entries: new Date(Date.now()-300000), sgvs: null, treatments: new Date(0), devicestatus: new Date(0), profile: null };
const output = function (batch) { persisted++; console.log("PERSISTED batch:", JSON.stringify(batch).slice(0,220)); return Promise.resolve(known); };
output.gap_for = () => Promise.resolve(known);
output.close = () => {};

const make = builder({ output, logger: log, start_jitter_ms: 0, interval_jitter_ms: 0 });
impl.generate_driver(make);
const actor = interpret(make());
const seen = [];
actor.onTransition((s)=>{ const v=JSON.stringify(s.value); if (seen[seen.length-1]!==v) seen.push(v); });
process.on('uncaughtException', (e)=>{ console.log('>>> UNCAUGHT, PROCESS WOULD DIE:', e.constructor.name+': '+e.message); console.log('states:', seen.join(' -> ')); process.exit(0); });
actor.start();
actor.send({type:'START'});
setTimeout(()=>{ console.log('persisted batches:', persisted); console.log('states:', seen.join(' -> ')); process.exit(0); }, 3000);
