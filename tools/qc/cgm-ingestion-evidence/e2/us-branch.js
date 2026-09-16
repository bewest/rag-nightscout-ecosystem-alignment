'use strict';
// Which URLs does the RETIRED package actually target? No network: a stub adapter
// records every request and rejects it. Rule 0: nothing leaves this machine.
const CRM='/home/bewest/src/rag-nightscout-ecosystem-alignment/externals/cgm-remote-monitor-official';
const axios = require(CRM+'/node_modules/axios');
const seen = [];
axios.defaults.adapter = function stub (config) {
  const base = config.baseURL || '';
  seen.push((config.method||'get').toUpperCase() + ' ' + base + config.url);
  return Promise.reject(Object.assign(new Error('stubbed, no network'), {config, isAxiosError:true}));
};
const carelink = require(CRM+'/node_modules/minimed-connect-to-nightscout/carelink.js');
const client = carelink.Client({ username:'u', password:'p' });
client.fetch(function (err, data) {
  console.log('MMCONNECT_SERVER =', JSON.stringify(process.env.MMCONNECT_SERVER));
  console.log('requests actually attempted:');
  seen.forEach(u => console.log('  ' + u));
  console.log('US-only endpoints reached (j_security_check / login.do / ConnectViewerServlet):',
    seen.some(u => /j_security_check|login\.do|ConnectViewerServlet/.test(u)));
  console.log('err:', String(err).split('\n')[0]);
});
