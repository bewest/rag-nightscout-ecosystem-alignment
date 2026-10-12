#!/usr/bin/env node
'use strict';
/* summary.js — one line per case x query x ask from a hub result file. Usage: node summary.js <result.json> */
const o = require(require('path').resolve(process.argv[2]));
for (const c of o.cases) {
  for (const q of c.queries) {
    console.log(c.id.padEnd(30), q.label.padEnd(8), Object.entries(q.answers).map(([k, v]) => k + '=' + v.key).join('  '));
  }
}
