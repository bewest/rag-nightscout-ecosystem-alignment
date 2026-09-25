'use strict';
/*
 * bf113-idforms-guard.js  — BF-113
 *
 * #8758's lib/server/object-id-forms.js says idForms(id) takes an ObjectId or
 * a 24-hex string and that "anything else throws, as `new ObjectId(id)` does".
 * The mongodb 5.9 driver also accepts any 12-character string as 12 raw
 * bytes, so idForms('abcdefghijkl') returns [ObjectId('6162…6c'), '6162…6c',
 * 'abcdefghijkl'] instead of throwing. profile.save and the food, activity and
 * profile remove() reach idForms with a non-hex id without an isHexId guard.
 *
 * HOW IT MEASURES. `git show` the ref's object-id-forms.js into a scratch
 * directory, borrow node_modules by symlink from the official checkout, and
 * call it.
 *
 *   control  idForms(<24-hex>) must return [ObjectId, hex]. If it does not,
 *            the harness is broken and the result means nothing.
 *   ref      idForms('abcdefghijkl') must throw, or return only forms that
 *            name the string as given. Three forms is BF-113.
 *
 * Reads only. Default ref official/bf/object-id-crud (#8758); pass --ref to
 * measure another. A ref without the helper is reported, not passed.
 */

const fs = require('fs');
const os = require('os');
const path = require('path');
const { CRM, show, report } = require('./_gate');

const REF = process.argv.includes('--ref')
  ? process.argv[process.argv.indexOf('--ref') + 1] : 'official/bf/object-id-crud';
const findings = [];

const src = show(REF, 'lib/server/object-id-forms.js');
if (src === null) {
  findings.push({ ok: false, text: `${REF}: lib/server/object-id-forms.js does not exist. NOTHING WAS MEASURED.` });
  report('bf113-idforms-guard (BF-113)', findings);
}

const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'queue-bf113-'));
let forms;
try {
  fs.mkdirSync(path.join(dir, 'lib', 'server'), { recursive: true });
  fs.writeFileSync(path.join(dir, 'lib', 'server', 'object-id-forms.js'), src);
  fs.symlinkSync(path.join(CRM, 'node_modules'), path.join(dir, 'node_modules'));
  forms = require(path.join(dir, 'lib', 'server', 'object-id-forms.js'));
} catch (e) {
  fs.rmSync(dir, { recursive: true, force: true });
  findings.push({ ok: false, text: `${REF}: harness failed (${e.message.split('\n')[0]}). NOTHING WAS MEASURED.` });
  report('bf113-idforms-guard (BF-113)', findings);
}

const HEX = '5f0c1a2b3c4d5e6f70818293';
let control;
try {
  const f = forms.idForms(HEX);
  control = f.length === 2 && f[0].toHexString() === HEX && f[1] === HEX ? 'ok' : 'forms ' + f.map(String).join(',');
} catch (e) {
  control = 'threw ' + e.message;
}
findings.push({ ok: control === 'ok',
  text: `CONTROL ${REF}: idForms(<24-hex>) -> ${control === 'ok' ? '[ObjectId, hex]' : control} (must be [ObjectId, hex], or the harness is broken)` });

let twelve;
try {
  twelve = forms.idForms('abcdefghijkl').map(String);
} catch (e) {
  twelve = null;
}
findings.push({ ok: twelve === null,
  text: twelve === null
    ? `${REF}: idForms('abcdefghijkl') throws, as its comment says`
    : `BF-113 PRESENT at ${REF}: idForms('abcdefghijkl') -> [${twelve.join(', ')}]; a 12-character id is read as 12 raw bytes and callers without an isHexId guard widen to those forms` });

fs.rmSync(dir, { recursive: true, force: true });
report('bf113-idforms-guard (BF-113)', findings);
