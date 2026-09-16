# A — `bf/alarms`: an urgent insulin-age alarm that could never fire, and two delivery defects

> **Base: `origin/dev` `a8888f0d`. This is one of NINE INDEPENDENT PRs. There is no stack — no
> Phase 0 branch is based on another, and this one merges cleanly against `origin/dev` and against
> all eight of the others.**
>
> **Needs a maintainer's explicit yes before merge — one of two branches in the set that does
> (the other is `bf/auth`, C).** This branch makes an alarm start firing that has never fired in
> any deployment, **and it removes a capability with no replacement** (per-request locale on the
> Alexa and Google Home endpoints). Both are the intended end state, but they are decisions, not
> typo fixes, and neither can be undone by an operator's configuration.

## What changes for you

**If you use the Insulin Age plugin with alerts turned on, you will start getting an URGENT
alarm you have never received before.**

Nightscout lets you set an age — by default 72 hours — after which your insulin reservoir is
"urgently" overdue for a change. Because of a one-word mistake in the code, that urgent alarm
has **never** been sent, in any release, to anyone. You may have set that threshold years ago
and never seen it honoured. After this change it works as documented.

Two things follow from that, and both are worth knowing before you upgrade:

- **There is no grace period.** If your reservoir is already past the threshold when you
  upgrade, the urgent alarm fires. That is deliberate. It is explained under
  "Why no grace period" below.
- **The severity of what you already saw was also wrong.** Past the threshold the plugin was
  reporting the lower "warning" level for as long as the reservoir stayed overdue — not only
  during the hour the urgent notification would have fired. So this is not just a missing
  alarm; it is a level that was understated the whole time.

This alarm only reaches you if you have already turned Insulin Age alerts on
(`IAGE_ENABLE_ALERTS`). If you have not, nothing about your alarms changes.

**Two smaller changes in the same branch:**

- **A plugin name in `ENABLE` that Nightscout does not recognise is no longer silently
  ignored.** If you wrote `insulinage` where Nightscout expects `iage`, the plugin simply did
  not load and nothing told you. You now get a suggestion in the server log naming the plugin
  it thinks you meant. **Your existing settings are not changed and nothing is renamed for
  you** — this only adds a message.
- **Voice assistant replies (Alexa, Google Home) are now always in your Nightscout's
  configured language.** Previously a request could be answered in the language that request
  asked for. That sounds like a feature, and it was removed on purpose: see the plain warning
  below, because this one is a capability removal.

> **Read this if you use Alexa or Google Home with Nightscout.** Before this change, a single
> voice request that named a language **re-pointed the language for the whole Nightscout
> process** — not just for that one answer. Every later page render, every later alarm text
> and every later voice reply used that language until something changed it back. So one
> request in French could leave your alarms in French. The fix removes per-request language
> handling entirely: replies now always use your server's configured language. **If you
> relied on asking in a second language, that no longer works.** There is no replacement in
> this changeset.

Nightscout is not a medical device and none of this is medical advice. If a change in when you
are alerted about insulin or site age affects how you manage your therapy, talk it through with
your care team.

## Technical detail

**BF-28 — `insulinage`'s urgent branch is unreachable.**

```
lib/plugins/insulinage.js:92    if (insulinInfo.age >= insulinInfo.urgent) {
lib/plugins/insulinage.js:93      sendNotification = insulinInfo.age === prefs.urgent;
```

`urgent` is assigned on `prefs` (`:19`, `sbx.extendedSettings.urgent || 72`) and never on
`insulinInfo`. Line 92 evaluates `age >= undefined`, which is always `false`. Line 93, one line
below, reads `prefs.urgent` correctly. All three sibling age plugins — `cannulaage`,
`sensorage`, `batteryage` — use `prefs.urgent` on both lines. The fix is that one identifier.

*Measured through the real sandbox at four ages*: at 72 h the plugin requested nothing before
and the URGENT overdue notification after. At 80 h, and at every age past the threshold, it
reported level **WARN** rather than URGENT — so the register entry understated the defect. The
severity was wrong for the whole time the reservoir stayed overdue, not only at the boundary.

**Why no grace period**, argued from evidence rather than taste:

- the notification is already gated on the operator having set `IAGE_ENABLE_ALERTS`;
- the README documents `IAGE_URGENT` as issuing exactly this warning;
- `cannulaage` has always fired on the identical default of 72, so the behaviour is not novel
  to the product, only to this plugin;
- a grace keyed on "the threshold was set explicitly" would leave the most exposed operators —
  the ones who enabled alerts and trusted the default — exactly where the bug left them.

**BF-29 — an unrecognised `ENABLE` entry is silently ignored.** Matching is against
`plugin.name` (`bwp`, `cage`, `iage`, `sage`, `bage`, `basal` — six aliases, not five), not
against the file name. `ENABLE=insulinage` loads nothing and says nothing. The branch adds a
suggestion based on edit distance. *Known limitation, measured*: the suggester is silent on a
stock settings string — `food`, `bridge`, `delta`, `devicestatus` and `cors` produce no
suggestion — while all six file-name aliases and near-misses such as `pushove` do. It helps the
case it was built for and does not chatter on correct configuration.

**BF-31 — a voice request re-languages the whole process.** `ctx.language.set(locale)` and
`moment.locale()` are process-global. `POST /api/v1/alexa` and `POST /api/v1/googlehome`
called them per request. **Measured**, and this corrected the register entry: the original
claim that "this is how alarm text reaches a push notification" does **not** hold — the alarm
catalogue is loaded once at boot. The leak is real but it is a shared-state defect, not an
alarm-text one, and the entry has been refiled accordingly.

## Evidence

- `docs/60-research/bf28-29-31-alarm-delivery-2026-09-15.md`
- Register entries **BF-28**, **BF-29**, **BF-31** in
  `docs/30-design/nightscout-backfix-register.md`

## Test evidence

- 3 commits: `8714093b` (BF-28), `99e46a52` (BF-29), `5dcf783f` (BF-31).
- 8 files, +400/-22, including `tests/insulinage.test.js` (+35) and `tests/plugins.test.js`
  (+119).
- `git merge-tree --write-tree --messages origin/dev bf/alarms` — **clean** against
  `origin/dev` `a8888f0d`, re-confirmed 2026-09-15.
- Trial-merges clean against all eight other Phase 0 branches (full 36-pair matrix, re-run
  2026-09-15; the matrix tool was positive-controlled against a known-conflicting pair, so the
  clean result is not vacuous).
- **Run the whole tree, not `npm run test:unit`.** `test:unit` is a brace list covering 44 of
  the 159 files in `tests/`; CI runs `npm run test-ci`, which is `./tests/*.test.js`. Several
  Phase 0 evidence files are outside the local unit list.
- *Known environmental note*: `crm-bf-alarms`' `node_modules` is missing
  `.cache/_ns_cache/public/js/bundle.app.js`, which fails `careportal`'s before-all hook
  locally. `npm run bundle` fixes it. It is not a defect in this branch.

## Semver

**Major**, and this branch is one of the three rows that makes Phase 0 as a whole a major
rather than a minor. The driver is not the alarm — it is the **removal of per-request locale
handling from two HTTP endpoints** with no replacement in the same changeset. Classification
from `docs/60-research/gt4-semver-classification-2026-09-15.md`.

If the maintainer wants Phase 0 to land as `15.1.0`, the Alexa/Google Home locale removal is
one of exactly three changes that would have to be split out.

**The operator-visible text above belongs in the release notes.** It is *not* a `CHANGELOG.md`
entry and this branch adds none: under the maintainer's rule, `CHANGELOG.md` is a **release
output** generated by GitHub tooling between releases, and branches never hand-edit it. Release
notes are prepared as release assets in the control-surface repo, and the "What changes for you"
section above is written to be usable verbatim as that source text. **Three paragraphs must not be
dropped:** the no-grace-period warning, the note that the severity you already saw was understated,
and the Alexa/Google Home block — that last one is a capability removal with no replacement, and it
is the only part of this branch that takes something away from an operator who was relying on it.

---

## Follow-ups deliberately **not** in this PR

- **The alexa `switch` has no `default`.** An unrecognised `request.type` calls neither
  `res.json()` nor `next()`, so the request hangs until the client times out. Low
  reachability. It sits beside the `ctx.language.set(locale)` line this branch already
  changes, so **it should land with this branch** rather than on its own — flagged here so the
  reviewer can ask for it now if they want it.
- **`plugins.isPluginEnabled` always returns `true`** — `find` returns `undefined`, compared
  against `!== null`. No caller today, so no register id was allocated, but it is what the next
  instrument will reach for.
- **`lib/authorization/storage.js` has a second unguarded `console.log` on a request path**,
  same shape as BF-05, different file. Line `:84` on `origin/dev` (it is `:82` on `bf/reads`
  and `:113` on `bf/auth` — the line number moves with the branch, so grep for
  `console.log('Loading'` rather than trusting the number).
- **Audit suppressions outside `lib/`.** `lib/` is now fully audited;
  the client bundle and `tests/` are not.
