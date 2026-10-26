// docdiff.js — operation-level diff of cgm-remote-monitor's v1 and v3 documents against Nocturne's
// "nightscout" document (its v1-v3 surface, served at /openapi/nightscout.json).
//
// Usage: node docdiff.js <js-yaml module dir> <crm api-v1.yaml> <crm api-v3.yaml> <nocturne nightscout.json>
// Prints JSON: {rows: [...]} with one row per operation key (see ops.js for the normalisation).
const fs = require('fs');
const path = require('path');
const {joinServer, normPath, crmKeys, matches} = require('./ops');
const [yamlDir, v1File, v3File, nocFile] = process.argv.slice(2);
const yaml = require(path.resolve(yamlDir));
const METHODS = ['get', 'post', 'put', 'patch', 'delete'];

function resolver (doc) {
  return function deref (s, depth = 0) {
    while (s && s.$ref && depth++ < 20) s = s.$ref.split('/').slice(1).reduce((o, k) => o && o[k], doc);
    return s || {};
  };
}
function schemeKinds (doc, sec) {
  const schemes = (doc.components || {}).securitySchemes || {};
  const out = new Set();
  for (const req of sec || []) {
    for (const name of Object.keys(req)) {
      const s = schemes[name] || {};
      if (s.type === 'apiKey') out.add(s.in + ':' + String(s.name).toLowerCase());
      else if (s.type === 'http') out.add('http:' + String(s.scheme).toLowerCase());
      else out.add('other:' + name);
    }
    if (!Object.keys(req).length) out.add('none');
  }
  return [...out].sort();
}
function bodyShape (doc, content) {
  if (!content) return null;
  const deref = resolver(doc);
  const ct = content['application/json'] ? 'application/json' : Object.keys(content)[0];
  let s = deref((content[ct] || {}).schema);
  if (s.allOf) s = Object.assign({}, ...s.allOf.map(x => deref(x)), {properties: Object.assign({}, ...s.allOf.map(x => deref(x).properties || {}))});
  const t = Array.isArray(s.type) ? s.type.filter(x => x !== 'null').join('|') : s.type;
  if (t === 'array' || s.items) {
    const it = deref(s.items);
    return {kind: 'array', itemKeys: Object.keys(it.properties || {}).sort()};
  }
  if (s.properties || t === 'object') return {kind: 'object', keys: Object.keys(s.properties || {}).sort()};
  return {kind: t || (Object.keys(s).length ? 'schema' : 'unspecified')};
}
function extract (doc, defaultServer, side) {
  const ops = {};
  const deref = resolver(doc);
  for (const [p, item] of Object.entries(doc.paths)) {
    const server = (item.servers && item.servers[0].url) || defaultServer;
    const full = joinServer(server, p);
    const keys = side === 'crm' ? crmKeys(full) : [normPath(full)];
    for (const m of METHODS) {
      const op = item[m]; if (!op) continue;
      const params = [...(item.parameters || []), ...(op.parameters || [])].map(x => deref(x));
      const responses = Object.keys(op.responses || {}).sort();
      const ok = responses.find(c => /^2/.test(c));
      const okResp = ok ? deref(op.responses[ok]) : null;
      const info = {
        paths: [full],
        query: params.filter(x => x.in === 'query').map(x => x.name).sort(),
        headers: params.filter(x => x.in === 'header').map(x => x.name.toLowerCase()).sort(),
        security: schemeKinds(doc, op.security !== undefined ? op.security : doc.security),
        responses,
        shape: okResp ? bodyShape(doc, okResp.content) : null,
      };
      for (const k of keys) {
        const key = m.toUpperCase() + ' ' + k;
        if (ops[key]) { ops[key].paths.push(full); for (const f of ['query', 'headers', 'responses']) ops[key][f] = [...new Set([...ops[key][f], ...info[f]])].sort(); }
        else ops[key] = JSON.parse(JSON.stringify(info));
      }
    }
  }
  return ops;
}
const v1 = yaml.load(fs.readFileSync(v1File, 'utf8'));
const v3 = yaml.load(fs.readFileSync(v3File, 'utf8'));
const noc = JSON.parse(fs.readFileSync(nocFile, 'utf8'));
const crm = Object.assign(extract(v1, v1.servers[0].url, 'crm'), extract(v3, v3.servers[0].url, 'crm'));
const nocOps = extract(noc, '/', 'noc');

// join: exact key first; else a literal on one side to the one template on the other (ops.js step 7)
const pair = {}; // crm key -> [noc keys]
const nocTaken = new Set();
for (const k of Object.keys(nocOps)) if (crm[k]) { (pair[k] = pair[k] || []).push(k); nocTaken.add(k); }
for (const k of Object.keys(nocOps)) {
  if (nocTaken.has(k)) continue;
  const [m, p] = k.split(' ');
  // only where crm's side is the template: a Nocturne literal joins the crm template that covers it
  const cand = Object.keys(crm).filter(c => c.startsWith(m + ' ') && matches(c.slice(m.length + 1), p) &&
    c.slice(m.length + 1).split('/').every((s, i) => s === '{}' || s === p.split('/')[i]));
  if (cand.length === 1) { (pair[cand[0]] = pair[cand[0]] || []).push(k); nocTaken.add(k); }
}
const diffSet = (a, b) => ({onlyCrm: a.filter(x => !b.includes(x)), onlyNoc: b.filter(x => !a.includes(x))});
function compareOps (c, n) {
  const d = [];
  const q = diffSet(c.query, n.query);
  if (q.onlyCrm.length || q.onlyNoc.length) d.push({aspect: 'query parameters', ...q});
  const s = diffSet(c.security, n.security);
  if (s.onlyCrm.length || s.onlyNoc.length) d.push({aspect: 'auth schemes', ...s});
  const r = diffSet(c.responses, n.responses);
  if (r.onlyCrm.length || r.onlyNoc.length) d.push({aspect: 'response codes', ...r});
  const cs = c.shape || {kind: 'none'}, ns = n.shape || {kind: 'none'};
  if (cs.kind !== ns.kind) d.push({aspect: '2xx body kind', crm: cs.kind, noc: ns.kind});
  else if (cs.kind === 'object') { const k = diffSet(cs.keys, ns.keys); if (k.onlyCrm.length || k.onlyNoc.length) d.push({aspect: '2xx body keys', ...k}); }
  else if (cs.kind === 'array') { const k = diffSet(cs.itemKeys, ns.itemKeys); if (k.onlyCrm.length || k.onlyNoc.length) d.push({aspect: '2xx item keys', ...k}); }
  return d;
}
const inScope = k => /^[A-Z]+ \/api\/(v1|v3|versions)(\/|$)/.test(k);
const rows = [];
for (const [k, c] of Object.entries(crm)) {
  const nk = pair[k] || [];
  if (!nk.length) { rows.push({key: k, class: 'only-crm', crm: c}); continue; }
  for (const n of nk) {
    const diffs = compareOps(c, nocOps[n]);
    rows.push({key: k, nocKey: n === k ? undefined : n, class: diffs.length ? 'differs' : 'same', crm: c, noc: nocOps[n], diffs});
  }
}
for (const [k, n] of Object.entries(nocOps)) if (!nocTaken.has(k)) rows.push({key: k, class: inScope(k) ? 'only-noc' : 'only-noc-outside-crm-docs', noc: n});
rows.sort((a, b) => (a.key.split(' ')[1] + a.key).localeCompare(b.key.split(' ')[1] + b.key));
console.log(JSON.stringify({normalisation: 'ops.js', rows}, null, 1));
