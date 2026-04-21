#!/usr/bin/env node
'use strict';

// Standalone probe that takes a JSON dump of a Nightscout `profile` mongo
// collection and prints what the Profile Editor + Reporting > Profiles UIs
// would render. Lets a user with the "only the 1969 Default record visible"
// symptom diagnose whether the issue is data (nothing was written) vs
// presentation (data is there but UI filters hide it).
//
// Usage:
//   mongoexport --uri "$NS_MONGO_URI" --collection profile --jsonArray > profiles.json
//   mongoexport --uri "$NS_MONGO_URI" --collection treatments \
//     --query '{"eventType":"Profile Switch"}' --jsonArray > switches.json
//   node tools/aaps/dropdown-logic-probe.js profiles.json switches.json
//
// Deliberately has no NS dependencies so it can be run by a confused user
// against a JSON dump without checking out c-r-m.

const fs = require('fs');

function loadJson(p) {
  if (!p) return [];
  return JSON.parse(fs.readFileSync(p, 'utf8'));
}

function pickDate(p) {
  // matches lib/data/ddata.js / profilefunctions.js mills resolution
  if (p.mills) return Number(p.mills);
  if (p.date) return Number(p.date);
  if (p.startDate) return Date.parse(p.startDate);
  if (p.created_at) return Date.parse(p.created_at);
  return 0;
}

function nameOf(p) {
  return p.defaultProfile || (p.store ? Object.keys(p.store)[0] : '<unnamed>');
}

function main() {
  const profilesPath = process.argv[2];
  const switchesPath = process.argv[3];
  if (!profilesPath) {
    console.error('usage: dropdown-logic-probe.js <profiles.json> [switches.json]');
    process.exit(2);
  }

  const profiles = loadJson(profilesPath);
  const switches = loadJson(switchesPath);

  // ---- Profile Editor "Database records" dropdown ----
  // Source: lib/profile/profileeditor.js:89 — GET /api/v1/profile.json?count=20
  // Renders one entry per result, label = `Valid from: <new Date(startDate).toLocaleString()>`.
  const editorRecords = profiles
    .slice()
    .sort((x, y) => pickDate(y) - pickDate(x))
    .slice(0, 20);

  console.log('=== Profile Editor "Database records" dropdown ===');
  console.log(`(${editorRecords.length} of ${profiles.length} profile docs shown; UI shows up to 20)`);
  editorRecords.forEach((p, i) => {
    const ts = pickDate(p);
    console.log(
      `  [${i}] _id=${p._id} startDate=${new Date(ts).toISOString()} ` +
      `defaultProfile=${nameOf(p)} store-keys=${p.store ? Object.keys(p.store).join(',') : '(none)'}`
    );
  });

  // ---- Profile Editor "Stored profiles" dropdown ----
  // Source: lib/profilefunctions.js:404 (filter `!name.includes('@@@@@')`)
  // and the in-memory store assembled from latest profile doc + all switch profileJsons.
  const latest = editorRecords[0];
  const storedNames = latest && latest.store ? Object.keys(latest.store) : [];
  console.log('\n=== Profile Editor "Stored profiles" dropdown ===');
  console.log('(names from latest profile-store doc; @@@@@ entries filtered out)');
  storedNames.filter(n => !n.includes('@@@@@')).forEach(n => console.log(`  - ${n}`));

  // ---- Reporting > Profiles columns ----
  // Source: lib/profilefunctions.js:272-287 — every profile-switch treatment with
  // profileJson is injected into the in-memory store as `<name>@@@@@<mills>`.
  console.log('\n=== Reporting > Profiles columns (one per profile-switch treatment) ===');
  console.log(`(${switches.length} profile-switch treatments; each becomes a column)`);
  switches.slice(0, 30).forEach((t, i) => {
    const ts = t.mills || (t.created_at ? Date.parse(t.created_at) : 0);
    const baseName = t.profile || (t.profileJson ? '<from-json>' : '<unknown>');
    const colKey = `${baseName}@@@@@${ts}`;
    console.log(`  [${i}] ${colKey}  enteredBy=${t.enteredBy || '?'}`);
  });
  if (switches.length > 30) console.log(`  ... +${switches.length - 30} more`);

  // ---- Diagnosis hints ----
  console.log('\n=== Diagnosis ===');
  if (profiles.length === 0) {
    console.log('  ⚠  No profile-store documents at all. AAPS never POSTed/emitted profile-store.');
    console.log('     Most likely: AAPS LongNonKey.LocalProfileLastChange == 0 (initial-import edge case)');
    console.log('     or NSClient socket/REST never authenticated. Check AAPS NSClient log.');
  } else if (profiles.length === 1) {
    console.log('  ⚠  Exactly 1 profile-store document. Edits in AAPS Local Profile are NOT reaching');
    console.log('     this collection. Profile Editor will only show this one record.');
    console.log('     Distinct from the V1 race c-r-m PR fixed (race produced 2 docs, not 0 edits).');
    if (switches.length > 1) {
      console.log('     But ' + switches.length + ' profile-switches exist → AAPS IS talking to NS,');
      console.log('     just not via the profile-store sync. Check AAPS DataSyncSelector logs.');
    }
  } else {
    console.log(`  ✓ ${profiles.length} profile-store documents present. Profile Editor should show`);
    console.log(`    up to 20 of them in "Database records". If user only sees 1, the problem is`);
    console.log(`    UI-side (browser cache, count param, REST 401, etc), not data-side.`);
  }
}

main();
