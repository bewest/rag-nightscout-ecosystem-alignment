#!/usr/bin/env node
// Summarize cross-validation JSON results into decision metrics
// Usage: node summarize-xval.js <results.json>

const fs = require('fs');
const file = process.argv[2] || '/tmp/xval-results.json';

try {
  const j = JSON.parse(fs.readFileSync(file));
  let e = 0, r = 0, rb = 0, rc = 0;
  j.comparisons.forEach(c => {
    if (c.eventualBG && c.eventualBG.delta === 0) e++;
    if (c.decision && c.decision.rate !== null && c.decision.rate !== undefined) {
      rb++;
      if (Math.abs(c.decision.rate) < 0.001) r++;
      if (Math.abs(c.decision.rate) <= 0.5) rc++;
    }
  });
  console.log('  EventualBG exact:', e + '/' + j.comparisons.length);
  console.log('  Rate exact:', r + '/' + rb, '  Rate ±0.5:', rc + '/' + rb);
  const s = j.summary.curveAggregates;
  Object.keys(s).forEach(k => {
    console.log('  ' + k.toUpperCase(), 'MAE:', s[k].avgMAE, ' corr:', s[k].avgCorrelation);
  });
} catch (err) {
  console.log('  (metrics extraction failed:', err.message + ')');
}
