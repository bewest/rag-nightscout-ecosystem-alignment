#!/usr/bin/env node
'use strict';
/*
 * alarms.js — P0-A / bf/alarms (#8739), register BF-28 and BF-29.
 *
 * BF-28. `lib/plugins/insulinage.js` compares the reservoir age against
 * `insulinInfo.urgent`, a property that is never assigned anywhere on that
 * object. `age >= undefined` is a NaN comparison and is therefore ALWAYS
 * FALSE, so the URGENT branch is unreachable: an overdue reservoir falls
 * through to the `warn` branch and is reported as a warning forever. The fix
 * compares against `prefs.urgent`, which is what every sibling branch uses.
 *
 * This is an alarm that has never fired in any deployment. There is no
 * historical data that exercises it, so the fixture is built to the boundary:
 * age exactly `prefs.urgent` (72 h by default), which is also the only age at
 * which `sendNotification` can be true, since that arm tests `===` not `>=`.
 *
 * BF-29. An unknown or file-named entry in ENABLE is silently ignored, so an
 * operator who writes `cannulaage` instead of `cage` loses the plugin with no
 * message. The fix says so and names the plugin it thinks was meant.
 *
 * Driven in-process against each worktree's own plugin module: the level is a
 * pure function of the treatment age and the prefs, and routing it through a
 * live server would add a socket, a bundle and a browser to a measurement that
 * needs none of them.
 *
 * NOT COVERED HERE. The third commit's removal of per-request locale from
 * /api/v1/alexa and /api/v1/googlehome. Maintainer ruling 2026-09-17: that is
 * a defect being corrected, not a capability being removed — ctx.language.set
 * and moment.locale are process-global, so one request re-languaged every
 * later request for every other user. No probe measures it; it is a code
 * review question.
 */

const path = require('path');
const { execFileSync } = require('child_process');
const { report } = require(path.resolve(__dirname, '..', '..', 'queue', 'gates', '_gate.js'));

const SENTINEL = '@@NSREVIEW@@';

// Builds a minimal ctx/sbx and asks the plugin for the level at a given age.
const LOADER = `
const wt = process.argv[1];
const ageHours = Number(process.argv[2]);
const moment = require(wt + '/node_modules/moment');
const levels = require(wt + '/lib/levels');
const ctx = {
  levels: levels,
  language: { translate: function (s) { return s; } },
  settings: {},
  moment: moment,
};
const iage = require(wt + '/lib/plugins/insulinage.js')(ctx);
const now = Date.UTC(2026, 0, 15, 12, 0, 0);
const sbx = {
  time: now,
  extendedSettings: { enableAlerts: true },
  data: { insulinchangeTreatments: [ { mills: now - ageHours * 3600 * 1000 } ] },
  notifications: { requestNotify: function () {} },
  properties: {},
};
const info = iage.findLatestTimeChange(sbx);
process.stdout.write('${SENTINEL}' + JSON.stringify({
  age: info.age,
  level: info.level,
  levelName: Object.keys(levels).find(function (k) { return levels[k] === info.level; }) || String(info.level),
  urgentLevel: levels.URGENT,
  warnLevel: levels.WARN,
  hasNotification: !!info.notification,
}) + '${SENTINEL}');
`;

function levelAt(worktree, ageHours) {
  const out = execFileSync(process.execPath, ['-e', LOADER, worktree, String(ageHours)],
    { cwd: worktree, encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] });
  const a = out.indexOf(SENTINEL), b = out.lastIndexOf(SENTINEL);
  if (a < 0 || b <= a) throw new Error(`no payload: ${out.slice(0, 200)}`);
  return JSON.parse(out.slice(a + SENTINEL.length, b));
}

function main() {
  const a = process.argv.slice(2);
  const g = k => { const i = a.indexOf(k); return i >= 0 ? a[i + 1] : null; };
  const baseWt = g('--base-worktree'), candWt = g('--candidate-worktree');
  if (!baseWt || !candWt) { console.error('need --base-worktree and --candidate-worktree'); process.exit(2); }

  const findings = [];
  // 72 h is the default `urgent`; 96 h is well past it. Both must read URGENT.
  for (const age of [72, 96]) {
    const b = levelAt(baseWt, age), c = levelAt(candWt, age);
    findings.push({
      ok: c.level === c.urgentLevel,
      text: `[discriminates] reservoir ${age}h old (urgent=72h): CANDIDATE level ${c.levelName}`,
    });
    findings.push({
      ok: true,
      text: `[discriminates] reservoir ${age}h old: CONTROL BASE level ${b.levelName} — ` +
            (b.level === b.urgentLevel ? 'GREEN' : 'RED (urgent branch unreachable; reported as a warning)'),
    });
    if (b.level === b.urgentLevel) {
      findings.push({ ok: false, text: `[discriminates] ${age}h: UNINFORMATIVE — BASE already reached URGENT` });
    }
  }
  // Invariant: ages below the urgent threshold must NOT become urgent. Without
  // this, a fix that always returned URGENT would pass every arm above.
  for (const [age, want] of [[50, 'WARN'], [45, 'INFO'], [2, 'NONE']]) {
    const b = levelAt(baseWt, age), c = levelAt(candWt, age);
    findings.push({
      ok: c.levelName === want && b.levelName === want,
      text: `[invariant] reservoir ${age}h old stays ${want}: BASE ${b.levelName}, CANDIDATE ${c.levelName}`,
    });
  }
  report('alarms (bf/alarms #8739, BF-28)', findings);
}

main();
