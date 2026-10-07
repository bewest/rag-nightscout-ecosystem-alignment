'use strict';
/*
 * platform-sql-surface.js  — T30-SCHEMA-CRED and T30-SCHEMA-CONFIG
 *
 * SPLIT 2026-09-16. T30-SCHEMA became two items when D17 row 1 settled the
 * device credential path independently of the human-identity question, so this
 * gate takes `--subset=cred` or `--subset=config` and measures only that half.
 * With no argument it measures all four, which is what it did before the split.
 * An unknown subset name is a failure, not an empty pass — an empty finding
 * list is VACUOUS and _gate.js already exits 1 on it, but naming the typo is
 * cheaper for the reader than reading "examined nothing".
 *
 * T3.0 is the credential and configuration rework that decisions D13, D14 and
 * D15 require, and it AMENDS T3.1, T3.2 and T3.3, all three of which are
 * currently marked DONE-EXCEPT. This gate turns GT3's grep of the admin schema
 * into a machine check, so that "T3.0 is not done" stops being a sentence
 * somebody has to remember and becomes something the queue can say.
 *
 * What D13/D14/D15 require the platform schema to carry, and what GT3 measured
 * it carrying today (two tables, tenants and tenant_members, and nothing else):
 *
 *   D14  a PER-TENANT JWT signing key. Tenant resolution runs BEFORE any
 *        credential is examined, so the right key is known at verify time and
 *        cross-tenant token reuse becomes a SIGNATURE failure rather than a
 *        claim-check failure. That is what structurally kills BF-25's bug class,
 *        and it needs a column to live in.
 *   D13  each tenant's own root credential, stored with its config, because
 *        there is NO deployment-wide secret under TENANCY_MODE=multi.
 *   D15  per-tenant configuration read from the database by hosted entrypoints,
 *        since env-sourced config must not reach the multi path.
 *
 * Also checks tenant_members.subject_id has a referent. GT3 measured it as
 * `uuid NOT NULL` with no foreign key, which is a tenancy boundary enforced by
 * hope.
 *
 * FAILS today, by design. It is the specification for both halves.
 *
 * TIGHTENED 2026-10-07 (T30-SCHEMA-CRED). The first form matched the whole
 * file, comments included, and judged D13 by a TABLE NAME — so a comment
 * mentioning a signing key, or a table called `tenant_secret` with no columns
 * worth the name, turned it green, and removing a column could not turn it
 * red. It now strips `--` comments and parses each CREATE TABLE into columns
 * and constraints, and the `cred` subset asks column-level questions:
 *   D13  a tenant-scoped secret table whose `kind` CHECK admits 'root', and
 *        'subject-salt' (the subject-token root, §C.3 of the config-surface
 *        document), holding `material bytea` and a `key_ref` naming the KEK
 *        — ciphertext and the key that wrapped it, never a text credential
 *   D14  the same table admits 'jwt', or a column is named for a signing key
 *   subjects  a tenant-scoped subject table keyed (tenant_id, subject_id text)
 *   members   tenant_members.subject_id references something, and its type
 *             equals the referenced column's type
 *   rls  every table carrying tenant_id except `tenants` has ENABLE and FORCE
 *        ROW LEVEL SECURITY and a policy whose USING and WITH CHECK are the
 *        predicate every other tenant table carries
 * It still measures that the schema CAN hold these, never that anything reads
 * them — T30-WIRING owns that.
 *
 * WHICH platform.sql. By default the crm-seam working tree, as before.
 * `--ref <ref>` reads lib/admin/platform.sql out of the cgm-remote-monitor
 * object database (every crm-* worktree shares it), and `--sql <file>` reads a
 * file — the form a control uses on a deliberately broken copy.
 */

const fs = require('fs');
const path = require('path');
const { REPO_ROOT, show, report } = require('./_gate');

function argValue (flag) {
  const eq = process.argv.slice(2).find((a) => a.startsWith(flag + '='));
  if (eq) return eq.slice(flag.length + 1);
  const at = process.argv.indexOf(flag);
  return at > -1 && process.argv[at + 1] ? process.argv[at + 1] : null;
}

// Which half of the split item is asking. `cred` is D13/D14, the subject
// store, the tenant_members referent and RLS on all of it; `config` is D15's
// settings table.
const SUBSETS = {
  cred: ['inventory', 'D14', 'D13', 'subjects', 'members', 'rls'],
  config: ['inventory', 'D15'],
};
const arg = argValue('--subset');
if (arg && !SUBSETS[arg]) {
  console.log(`gate: platform-sql-surface\n  BAD  unknown --subset=${arg}; expected cred or config`);
  process.exit(1);
}
const wanted = arg ? SUBSETS[arg] : null;
const want = (tag) => !wanted || wanted.includes(tag);

const all = [];
const findings = {
  push(f) { if (want(f.tag)) all.push(f); },
};

const REF = argValue('--ref');
const SQLFILE = argValue('--sql');
const SQL = path.join(REPO_ROOT, 'externals', 'work', 'crm-seam', 'lib', 'admin', 'platform.sql');
const source = REF ? `${REF}:lib/admin/platform.sql` : (SQLFILE || SQL);

let raw = null;
if (REF) raw = show(REF, 'lib/admin/platform.sql');
else { try { raw = fs.readFileSync(SQLFILE || SQL, 'utf8'); } catch (e) { raw = null; } }
if (raw === null) {
  // Not a silent pass. If the seam worktree is gone the gate cannot measure,
  // and "cannot measure" is a failure of the gate, not a pass for the schema.
  console.log(`gate: platform-sql-surface\n  BAD  cannot read ${source}; nothing was measured`);
  process.exit(1);
}

// Comments out first: a comment that mentions a signing key is not one.
const sql = raw.replace(/--[^\n]*/g, '');
const norm = (x) => x.replace(/\s+/g, ' ').trim();

// Split a parenthesised list at depth-0 commas.
function splitTop (text) {
  const out = []; let depth = 0; let cur = '';
  for (const ch of text) {
    if (ch === '(') depth += 1;
    if (ch === ')') depth -= 1;
    if (ch === ',' && depth === 0) { out.push(cur); cur = ''; } else cur += ch;
  }
  if (cur.trim()) out.push(cur);
  return out.map(norm).filter(Boolean);
}

const tables = {};
for (const m of sql.matchAll(/CREATE TABLE(?:\s+IF NOT EXISTS)?\s+"?(\w+)"?\s*\(([\s\S]*?)\)\s*;/gi)) {
  const columns = {}; const constraints = [];
  for (const item of splitTop(m[2])) {
    if (/^(CONSTRAINT|PRIMARY KEY|UNIQUE|CHECK|FOREIGN KEY|EXCLUDE)\b/i.test(item)) constraints.push(item);
    else {
      const c = item.match(/^"?(\w+)"?\s+(\w+(?:\s*\[\])?)(.*)$/);
      if (c) columns[c[1]] = { type: c[2].toLowerCase(), rest: c[3] };
    }
  }
  tables[m[1]] = { columns, constraints };
}
const names = Object.keys(tables);
findings.push({ tag: 'inventory', ok: true, text: `${source} declares tables: ${names.join(', ') || '(none)'}` });

// --- the secret table: tenant-scoped, with a `kind` CHECK listing its kinds
const kindsOf = (t) => {
  const col = t.columns.kind;
  const checks = [col ? col.rest : ''].concat(t.constraints.filter((c) => /\bkind\b/i.test(c)));
  return new Set(checks.flatMap((c) => [...c.matchAll(/'([^']+)'/g)].map((k) => k[1])));
};
const tenantScoped = names.filter((n) => tables[n].columns.tenant_id && n !== 'tenants');
const secretTables = tenantScoped.filter((n) => kindsOf(tables[n]).size > 0);
const admits = (kind) => secretTables.filter((n) => kindsOf(tables[n]).has(kind));
const wrapped = secretTables.filter((n) => {
  const c = tables[n].columns;
  return c.material && c.material.type === 'bytea' && c.key_ref;
});

findings.push({
  tag: 'D14',
  ok: admits('jwt').length > 0 || names.some((n) => Object.keys(tables[n].columns).some((c) => /signing_key|jwt_key/.test(c))),
  text: `D14: a per-tenant JWT signing key has somewhere to live (a tenant-scoped kind CHECK admitting 'jwt': `
      + `${admits('jwt').join(', ') || 'none'})`,
});
findings.push({
  tag: 'D13',
  ok: admits('root').length > 0,
  text: `D13: a per-tenant root credential has somewhere to live, so none is deployment-wide under `
      + `TENANCY_MODE=multi (a tenant-scoped kind CHECK admitting 'root': ${admits('root').join(', ') || 'none'})`,
});
findings.push({
  tag: 'D13',
  ok: admits('subject-salt').length > 0,
  text: `D13 (§C.3): subject access tokens have a per-tenant root of their own, not the root credential `
      + `(kind 'subject-salt': ${admits('subject-salt').join(', ') || 'none'})`,
});
findings.push({
  tag: 'D13',
  ok: secretTables.length > 0 && wrapped.length === secretTables.length,
  text: `D13: secret material is stored as ciphertext with the key that wrapped it named — material bytea `
      + `and key_ref on every secret table (${secretTables.map((n) => `${n}: ${wrapped.includes(n) ? 'yes' : 'NO'}`).join(', ') || 'no secret table'})`,
});

// --- the subject store
const subjectTables = tenantScoped.filter((n) => {
  const t = tables[n];
  return t.columns.subject_id && t.columns.subject_id.type === 'text'
    && t.constraints.some((c) => /^PRIMARY KEY\s*\(\s*tenant_id\s*,\s*subject_id\s*\)$/i.test(c));
});
findings.push({
  tag: 'subjects',
  ok: subjectTables.length > 0,
  text: `device/uploader subjects are stored per tenant, keyed (tenant_id, subject_id text): `
      + `${subjectTables.join(', ') || 'none'}`,
});

// --- tenant_members.subject_id: a referent, of the same type
const members = tables.tenant_members;
let refText = 'tenant_members not declared';
let membersOk = false;
if (members && members.columns.subject_id) {
  const own = members.columns.subject_id;
  let target = null;
  const inline = own.rest.match(/REFERENCES\s+"?(\w+)"?\s*\(\s*(\w+)\s*\)/i);
  if (inline) target = { table: inline[1], column: inline[2] };
  for (const c of members.constraints) {
    const fk = c.match(/FOREIGN KEY\s*\(([^)]*)\)\s*REFERENCES\s+"?(\w+)"?\s*\(([^)]*)\)/i);
    if (!fk) continue;
    const from = fk[1].split(',').map(norm); const to = fk[3].split(',').map(norm);
    const at = from.indexOf('subject_id');
    if (at > -1) target = { table: fk[2], column: to[at], composite: from.length > 1 ? fk[1] : null };
  }
  if (!target) refText = `tenant_members.subject_id is ${own.type} and references nothing`;
  else {
    const t = tables[target.table];
    const ttype = t && t.columns[target.column] ? t.columns[target.column].type : null;
    membersOk = ttype === own.type;
    refText = `tenant_members.subject_id (${own.type}) references ${target.table}.${target.column} `
      + `(${ttype || 'not declared'})${target.composite ? ` via (${norm(target.composite)})` : ''}`;
  }
}
findings.push({ tag: 'members', ok: membersOk, text: `tenant_members.subject_id has a declared referent of its own type: ${refText}` });

// --- RLS on every tenant-scoped table
const PREDICATE = "tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid";
const flat = norm(sql);
const rlsBad = tenantScoped.filter((n) => {
  const enable = new RegExp(`ALTER TABLE "?${n}"? ENABLE ROW LEVEL SECURITY`, 'i').test(flat);
  const force = new RegExp(`ALTER TABLE "?${n}"? FORCE ROW LEVEL SECURITY`, 'i').test(flat);
  const pol = flat.match(new RegExp(`CREATE POLICY \\w+ ON "?${n}"? USING \\((.*?)\\) WITH CHECK \\((.*?)\\);`, 'i'));
  return !(enable && force && pol && norm(pol[1]) === PREDICATE && norm(pol[2]) === PREDICATE);
});
findings.push({
  tag: 'rls',
  ok: tenantScoped.length > 0 && rlsBad.length === 0,
  text: `every tenant-scoped table (${tenantScoped.join(', ') || 'none'}) has ENABLE + FORCE ROW LEVEL `
      + `SECURITY and the shared isolation policy${rlsBad.length ? ` — NOT: ${rlsBad.join(', ')}` : ''}`,
});

findings.push({
  tag: 'D15',
  ok: names.some((t) => /setting|config/i.test(t)),
  text: 'D15: per-tenant configuration has a table, so hosted entrypoints can read '
      + 'config from the database instead of the process environment',
});

report(`platform-sql-surface${arg ? ` (--subset=${arg})` : ''}`, all);
