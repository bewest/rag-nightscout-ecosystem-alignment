'use strict';

// Compare two trace.cjs outputs line by line. Equivalent only when every cycle
// has the same instant, kind, full-output hash and alarm set.
//
//   node compare.cjs <base trace> <candidate trace>
const fs = require('node:fs');
const [a, b] = process.argv.slice(2).map(file => fs.readFileSync(file, 'utf8').trimEnd().split('\n'));
let differing = 0, first = null;
// The alarm set is everything after the third space (titles contain spaces).
const alarms = line => line.split(' ').slice(3).join(' ');
const alarmTransitions = lines => lines.filter((line, i) => !i || alarms(line) !== alarms(lines[i - 1])).length;
for (let i = 0; i < Math.max(a.length, b.length); i++) {
  if (a[i] !== b[i]) { differing++; if (!first) first = { line: i + 1, base: a[i] || '(none)', candidate: b[i] || '(none)' }; }
}
const verdict = !differing && a.length === b.length ? 'IDENTICAL' : 'DIFFERENT';
process.stdout.write(verdict + ' cycles base=' + a.length + ' candidate=' + b.length + ' differing=' + differing +
  ' alarmTransitions base=' + alarmTransitions(a) + ' candidate=' + alarmTransitions(b) +
  (first ? '\n  first difference at line ' + first.line + '\n  base      ' + first.base + '\n  candidate ' + first.candidate : '') + '\n');
process.exitCode = verdict === 'IDENTICAL' ? 0 : 1;
