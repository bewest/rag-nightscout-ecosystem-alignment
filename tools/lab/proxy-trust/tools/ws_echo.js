#!/usr/bin/env node
'use strict';
// ws_echo.js - selftest stand-in for Nightscout behind the AR chain.
// Plain requests get the same one-line echo as the nginx echo backend in
// ar_chain.sh. Upgrade requests get a 101 whose X-Echo header carries the same
// fields, so the selftest can see what the last hop forwarded on an upgrade.
// Node core only: the selftest needs no Nightscout tree.
const http = require('http');
const port = Number(process.env.PORT || 3866);

function echo (req) {
  const h = req.headers;
  return `peer=${req.socket.remoteAddress.replace(/^::ffff:/, '')}|xff=${h['x-forwarded-for'] || ''}` +
    `|xrip=${h['x-real-ip'] || ''}|proto=${h['x-forwarded-proto'] || ''}|host=${h.host || ''}` +
    `|upgrade=${(h.upgrade || '').toLowerCase()}|connection=${(h.connection || '').toLowerCase()}`;
}

const server = http.createServer((req, res) => {
  res.writeHead(200, { 'Content-Type': 'text/plain' });
  res.end(echo(req) + '\n');
});
server.on('upgrade', (req, sock) => {
  sock.write('HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n' +
    `X-Echo: ${echo(req)}\r\n\r\n`);
  setTimeout(() => sock.destroy(), 200);
});
server.listen(port, () => console.log('ws_echo listening', port));
