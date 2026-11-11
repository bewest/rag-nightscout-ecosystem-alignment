'use strict';

// The forms of the date strings a corpus holds, as shapes only: every digit
// becomes 9 and every letter run outside the ISO markers becomes "A" (month
// and day names). No value leaves the corpus; the output is the shape, the
// field it was seen in and a count.
//
//   node date-forms.cjs <corpus dir> [<corpus dir> ...]
//
// A string is a candidate when it is the value of a field named like a date
// (created_at, timestamp, date, dateString, sysTime, clock, startDate, ...),
// at any depth, in a *_entries/_treatments/_devicestatus/_profile.json file.
const fs = require('node:fs'), path = require('node:path');
const DATEISH = /(^|_)(created_at|timestamp|date|datestring|systime|clock|startdate|enddate|time|deliverat|mills|srvcreated|srvmodified)$/i;
const shapes = new Map();
function shape (text) {
  return text.replace(/[0-9]/g, '9').replace(/(?<![A-Za-z])(?!T(?=9)|Z$|W(?=9))[A-Za-z]+/g, 'A');
}
function visit (value, field, file) {
  if (Array.isArray(value)) { for (const item of value) visit(item, field, file); return; }
  if (value && typeof value === 'object') { for (const [key, v] of Object.entries(value)) visit(v, key, file); return; }
  if (typeof value === 'string' && field && DATEISH.test(field) && /[0-9]/.test(value)) {
    const key = shape(value) + '\t' + field;
    const entry = shapes.get(key) || { count: 0, files: new Set() };
    entry.count++; entry.files.add(file); shapes.set(key, entry);
  }
}
let sets = 0;
for (const dir of process.argv.slice(2)) {
  for (const name of fs.readdirSync(dir).filter(n => /_(entries|treatments|devicestatus|profile)\.json$/.test(n)).sort()) {
    const set = name.replace(/_(entries|treatments|devicestatus|profile)\.json$/, '');
    let data;
    try { data = JSON.parse(fs.readFileSync(path.join(dir, name), 'utf8')); } catch { continue; }
    visit(data, null, set);
  }
  sets += new Set(fs.readdirSync(dir).filter(n => /_entries\.json$/.test(n))).size;
}
const rows = [...shapes].map(([key, v]) => [key, v.count, v.files.size]).sort((a, b) => b[1] - a[1]);
process.stdout.write('DATE_FORMS sets=' + sets + ' shapes=' + new Set(rows.map(r => r[0].split('\t')[0])).size + '\n');
for (const [key, count, files] of rows) process.stdout.write(count + '\t' + files + ' sets\t' + key + '\n');
