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
 */

const fs = require('fs');
const path = require('path');
const { REPO_ROOT, report } = require('./_gate');

const SQL = path.join(REPO_ROOT, 'externals', 'work', 'crm-seam', 'lib', 'admin', 'platform.sql');

// Which half of the split item is asking. `cred` is D13/D14 plus the
// tenant_members referent; `config` is D15's settings table.
const SUBSETS = { cred: ['inventory', 'D14', 'D13', 'members'], config: ['inventory', 'D15'] };
const arg = (process.argv.slice(2).find((a) => a.startsWith('--subset=')) || '').split('=')[1];
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

if (!fs.existsSync(SQL)) {
  // Not a silent pass. If the seam worktree is gone the gate cannot measure,
  // and "cannot measure" is a failure of the gate, not a pass for the schema.
  console.log(`gate: platform-sql-surface\n  BAD  cannot read ${SQL}; nothing was measured`);
  process.exit(1);
}

const sql = fs.readFileSync(SQL, 'utf8');
const tables = [...sql.matchAll(/CREATE TABLE(?:\s+IF NOT EXISTS)?\s+([\w."]+)/gi)]
  .map((m) => m[1].replace(/"/g, ''));

findings.push({ tag: 'inventory', ok: true, text: `platform.sql declares tables: ${tables.join(', ') || '(none)'}` });

findings.push({
  tag: 'D14',
  ok: /signing[_ ]?key|jwt[_ ]?key|key_id|kid\b/i.test(sql),
  text: 'D14: a per-tenant JWT signing key has somewhere to live',
});

findings.push({
  tag: 'D13',
  ok: tables.some((t) => /secret|credential/i.test(t)) || /root_credential|api_secret_hash/i.test(sql),
  text: "D13: a per-tenant root credential has somewhere to live (no deployment-wide secret exists under TENANCY_MODE=multi)",
});

findings.push({
  tag: 'D15',
  ok: tables.some((t) => /setting|config/i.test(t)),
  text: 'D15: per-tenant configuration has a table, so hosted entrypoints can read '
      + 'config from the database instead of the process environment',
});

const membersBlock = (sql.match(/CREATE TABLE(?:\s+IF NOT EXISTS)?\s+"?tenant_members"?[\s\S]*?;/i) || [''])[0];
findings.push({
  tag: 'members',
  ok: /subject_id[^,]*REFERENCES/i.test(membersBlock)
      || /FOREIGN KEY\s*\(\s*subject_id\s*\)/i.test(membersBlock),
  text: 'tenant_members.subject_id has a declared referent rather than being a bare uuid',
});

report(`platform-sql-surface${arg ? ` (--subset=${arg})` : ''}`, all);
