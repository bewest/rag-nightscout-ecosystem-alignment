'use strict';
// Private offline scoring inputs only. k6 stderr and summary check names can contain request URLs.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const readline = require('node:readline');
const { pipeline } = require('node:stream/promises');

const UUID = /^[a-f\d]{8}(?:-[a-f\d]{4}){3}-[a-f\d]{12}$/i;
const domains = ['entries', 'devicestatus', 'treatments'];
const maxBytes = {'k6.log': 64 * 1024 ** 2, 'k6-summary.json': 4 * 1024 ** 2};
const counters = /^(?:writes_(?:ok|refused|uncertain)(?:_documents)?(?:\{kind:(?:entries|devicestatus|treatments|profile)\})?|m7_looping_(?:documents|requests)\{request_shape:(?:ds_(?:loop|loop_extra|trio_enacted|trio_suggested|aaps|cgm_battery)|tx_(?:loop_v1|trio_v1|aaps_v3)|profile_loop_v1)\})$/;

function need(condition, code) {
  if (!condition) throw Error('K8S_WRITER_PUBLICATION_' + code);
}

function directory(parent, name) {
  const target = path.join(parent, name);
  try { fs.mkdirSync(target, {mode: 0o700}); }
  catch (err) { if (err.code !== 'EEXIST') throw err; }
  need(fs.lstatSync(target).isDirectory(), 'DIRECTORY');
  return target;
}

function checkedInput(root, name, bytes) {
  const target = path.join(root, name);
  const stat = fs.lstatSync(target);
  need(stat.isFile() && stat.size === bytes && bytes > 0 && bytes <= maxBytes[name], 'INPUT');
  return target;
}

async function* acceptedLines(input, runId, counts) {
  const source = fs.createReadStream(input);
  const lines = readline.createInterface({input: source, crlfDelay: Infinity});
  // Propagate disk I/O errors to the iterator too.
  source.on('error', error => lines.emit('error', error));
  try {
    for await (const line of lines) {
      if (!line.includes('m7-input-accepted')) continue;
      const match = /\bmsg=("(?:[^"\\]|\\.)*")/.exec(line);
      const msg = match ? JSON.parse(match[1]) : JSON.parse(line).msg;
      need(typeof msg === 'string', 'ACCEPTED_EVENT');
      const row = JSON.parse(msg);
      need(row?.event === 'm7-input-accepted' && row.run === runId && UUID.test(row.tenant) &&
           domains.includes(row.domain) && typeof row.key === 'string' &&
           (/^-?\d{1,16}$/.test(row.key) ||
            /^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,6})?(?:Z|[+-]\d\d:\d\d)$/.test(row.key)) &&
           Number.isSafeInteger(row.acceptedAtMs) && Number.isSafeInteger(row.requestToAcceptanceMs) &&
           row.requestToAcceptanceMs >= 0, 'ACCEPTED_EVENT');
      const accepted = {event: row.event, run: runId, tenant: row.tenant, domain: row.domain,
                        key: row.key, requestToAcceptanceMs: row.requestToAcceptanceMs, acceptedAtMs: row.acceptedAtMs};
      counts[row.domain]++;
      yield JSON.stringify({msg: JSON.stringify(accepted)}) + '\n';
    }
  } finally { lines.close(); source.destroy(); }
}

const shapes = /^(?:r_(?:sgv|devicestatus|status|treatments)|w_(?:sgv|devicestatus|treatments_v3))$/;
const labels = new Map(Object.entries({
  scenario: shapes, shape: shapes, http_shape: shapes, expected_response: /^(?:true|false)$/,
  driver_phase: /^(?:steady|drain)$/, status: /^(?:0|[1-5][0-9]{2})$/,
  category: /^(?:http_expected|http_refused|http_unexpected|timeout|transport)$/,
  outcome: /^(?:accepted|refused|uncertain)$/
}));
const performance = /^(?:m7_http_(?:attempts|completed|write_outcome)|m7_driver_(?:started|finished)|http_req_duration|http_reqs|scenario_(?:request_attempts|http_responses|transport_failures)|dropped_iterations|iterations)(?:\{([^{}]*)\})?$/;

function retainMetric(name) {
  if (counters.test(name)) return true;
  const match = performance.exec(name);
  if (!match) return false;
  if (!match[1]) return true;
  return match[1].split(',').every(tag => {
    const [key, value, ...extra] = tag.split(':');
    return extra.length === 0 && value !== undefined && labels.get(key)?.test(value);
  });
}

function writeSummary(input, dest) {
  const metrics = JSON.parse(fs.readFileSync(input, 'utf8'))?.metrics;
  need(metrics && typeof metrics === 'object' && !Array.isArray(metrics), 'COUNTER');
  const retained = {};
  for (const [name, row] of Object.entries(metrics)) {
    if (!retainMetric(name)) continue;
    const values = row?.values || row;
    need(values && typeof values === 'object' && !Array.isArray(values), 'COUNTER');
    const numeric = Object.fromEntries(Object.entries(values).filter(([key, value]) =>
      /^(?:count|rate|min|max|avg|med|p\((?:90|95|99)\))$/.test(key) && Number.isFinite(value)));
    if (numeric.count !== undefined) need(Number.isSafeInteger(numeric.count) && numeric.count >= 0, 'COUNTER');
    retained[name] = numeric;
  }
  need(Number.isSafeInteger(retained.writes_ok?.count) && Number.isSafeInteger(retained.writes_uncertain?.count), 'COUNTER');
  fs.writeFileSync(dest, JSON.stringify({metrics: retained}) + '\n', {mode: 0o600});
  return retained;
}

async function describe(file) {
  const digest = crypto.createHash('sha256');
  let bytes = 0;
  for await (const chunk of fs.createReadStream(file)) { digest.update(chunk); bytes += chunk.length; }
  return {bytes, sha256: digest.digest('hex')};
}

async function publish(root, runId, podUid, destination, meta) {
  need(/^[a-z0-9-]{1,100}$/.test(runId) && UUID.test(podUid) && meta?.runId === runId &&
       meta.kind === 'm7-native-artifacts-v1' && Number.isInteger(meta.exitCode) &&
       meta.exitCode >= 0 && meta.exitCode <= 255 && path.isAbsolute(destination), 'IDENTITY');
  const attempt = directory(directory(destination, runId), podUid);
  const stage = fs.mkdtempSync(path.join(attempt, '.publishing-'));
  const target = path.join(attempt, 'writer');
  const files = {};
  const problems = {};
  const accepted = Object.fromEntries(domains.map(domain => [domain, 0]));
  let metrics;
  try {
    for (const name of Object.keys(maxBytes)) {
      const dest = path.join(stage, name);
      try {
        const input = checkedInput(root, name, meta.files?.[name]?.bytes);
        if (name === 'k6.log') {
          await pipeline(acceptedLines(input, runId, accepted), fs.createWriteStream(dest, {mode: 0o600, flags: 'wx'}));
        } else metrics = writeSummary(input, dest);
        files[name] = await describe(dest);
      } catch (err) {
        // A broken input must never appear complete; diagnostics cannot include untrusted raw input.
        if (!['ENOENT', 'SyntaxError'].includes(err.code || err.name) && !/^K8S_WRITER_PUBLICATION_/.test(err.message)) throw err;
        fs.rmSync(dest, {force: true});
        problems[name] = 'invalid-or-missing';
      }
    }
    if (files['k6.log'] && metrics && domains.some(domain => {
      const count = metrics['writes_ok{kind:' + domain + '}']?.count;
      return count !== undefined && count !== accepted[domain];
    })) problems['k6.log'] = 'accepted-request-count-mismatch';
    const status = meta.exitCode === 0 && Object.keys(problems).length === 0 ? 'complete' : 'partial';
    const record = {version: 1, kind: 'm7-writer-publication', runId, podUid, status, exitCode: meta.exitCode, files, problems};
    const serialized = JSON.stringify(record, null, 2) + '\n';
    fs.writeFileSync(path.join(stage, 'publication.json'), serialized, {mode: 0o600});
    // One immutable commit point. Concurrent/retried identical publications converge.
    try { fs.renameSync(stage, target); }
    catch (err) {
      if (!['EEXIST','ENOTEMPTY'].includes(err.code)) throw err;
      need(fs.lstatSync(target).isDirectory() && fs.readFileSync(path.join(target, 'publication.json'), 'utf8') === serialized, 'CONFLICT');
      for (const [name, expected] of Object.entries(files)) {
        need((await describe(path.join(target, name))).sha256 === expected.sha256, 'CONFLICT');
      }
    }
    return record;
  } finally { fs.rmSync(stage, {recursive: true, force: true}); }
}

module.exports = {publish};
