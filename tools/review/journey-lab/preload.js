'use strict';
// preload.js — loaded into each journey-lab server with NODE_OPTIONS=--require. It only redirects
// Loop remote-command pushes to the lab's fake APNs server (apns-log.js) instead of Apple; the
// build itself is not modified. Same technique as tools/lab/rc-soak/preload.js.
if (process.env.LAB_APNS_PORT) {
  const apn = require(require('path').join(process.cwd(), 'node_modules/@parse/node-apn'));
  const Original = apn.Provider;
  apn.Provider = function LabProvider (options) {
    options.address = 'localhost';
    options.port = Number(process.env.LAB_APNS_PORT);
    options.rejectUnauthorized = false;
    return new Original(options);
  };
}
