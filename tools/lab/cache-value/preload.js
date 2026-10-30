'use strict';
// Loaded into the Nightscout server with NODE_OPTIONS=--require. Counts bus
// events by wrapping EventEmitter.prototype.emit (only the names below) and
// writes one JSON line per second to $CV_METRICS: cumulative counts and RSS.
const fs = require('fs');
const EventEmitter = require('events');
const out = process.env.CV_METRICS;
if (out) {
  const names = new Set(['data-loaded', 'data-received', 'tick', 'data-update']);
  const counts = { 'data-loaded': 0, 'data-received': 0, tick: 0, 'data-update': 0 };
  const emit = EventEmitter.prototype.emit;
  EventEmitter.prototype.emit = function (name) {
    if (names.has(name)) counts[name] += 1;
    return emit.apply(this, arguments);
  };
  const timer = setInterval(function () {
    const m = process.memoryUsage();
    fs.appendFileSync(out, JSON.stringify({ t: Date.now(), rss: m.rss, heapUsed: m.heapUsed, counts }) + '\n');
  }, 1000);
  timer.unref();
}
