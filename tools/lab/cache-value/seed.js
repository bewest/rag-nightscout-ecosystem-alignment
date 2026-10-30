'use strict';
// seed.js <mongodb-uri> <now-ms>: drop the database and load the synthetic history
// (entries 50 h, devicestatus 26 h, every 5 min; a treatment every 2 h for 62 h).
const C = require('./common');
C.seed(process.argv[2], +process.argv[3]).then(n => { console.log(JSON.stringify(n)); }).catch(e => { console.error(e); process.exit(1); });
