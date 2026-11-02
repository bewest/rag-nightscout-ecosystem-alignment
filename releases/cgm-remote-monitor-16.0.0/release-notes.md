# Nightscout 16.0.0 - release notes (DRAFT)

**Draft for maintainer review, 2026-11-02. Not a release announcement.**
The version is decided: 16.0.0. The implementation is merged to development,
but no named RC or v16 release is published. Informal testing is underway.
Private security integration and final release acceptance remain pending.

Nightscout 16 modernizes both the backend and frontend: shared storage and write
contracts, more consistent record identity and re-send handling, refreshed
runtime dependencies and browser bundles, and an optional responsive modern
theme. It also includes reporting, notification and interoperability fixes.
It is **not** an automated-insulin-delivery algorithm upgrade, and it does not
require all connected apps to release together.

Nightscout 16 is designed to preserve interoperability with existing clients
without coordinated client upgrades. New item-result replies are opt-in.
Identity, re-send, deletion and unit-handling fixes have documented behavior
changes; non-default strict/rejection settings need separate client checks.
This is not a guarantee that every future client feature works on older servers.

**Nightscout is not a medical device and nothing here is medical advice.**
These notes complement the generated changelog, which records what merged.
The [technical contents](contents.md) carry the full compatibility and known-defect
record. Final notes must be reconciled against the actual release tree, not
assumed complete from this draft.

## Read this before upgrading

### Runtime and installation changes can stop your site starting

Node must satisfy `^22.23.4 || ^24.22.1 || >=26.12.1`. This does not mean every
version newer than 22.23.4 is accepted: Node 23, 25 and earlier 26 versions are
outside that range. The image uses Node 24.22.1.

MongoDB 5.0 through 8.0 is the supported/tested range. Driver 7 can start on
4.4, but 4.4 is unsupported and untested. MongoDB 3.6, 4.0 and 4.2 no longer
serve data; the boot error page names the version and minimum.
Compose changes its default from MongoDB 5.0.32 to 6.0.27: follow the upstream
[runtime upgrade guide](https://github.com/nightscout/cgm-remote-monitor/blob/61eb37335954ae42c91345a0823bd67331025165/docs/runtime-upgrade.md),
including database upgrade steps and backup/restore, rather than treating it
as an ordinary image-only update.

The legacy built-in Dexcom Share and MiniMed CareLink bridges are removed.
Leftover bridge settings stop the site with a page naming replacements.
Dexcom Share is supported through Nightscout Connect; confirm your source's
replacement and configuration before upgrading.

Source installs need development dependencies to build browser bundles:
`npm ci --include=dev`, then `npm prune --omit=dev --ignore-scripts` after
the build. An initial production-only install no longer builds the browser
code. The provided Docker build handles the build/runtime split; its runtime
image contains no `npm` or `npx`. Third-party page plugins need upgrade testing.

### Some alarms and displayed values change

A page showing `---` can now present device and other non-glucose alarms.
For sites with `PUMP_ENABLE_ALERTS`, pump alarms use Loop's reported severity
and text: "No Insulin", "Pod Expired" and Medtronic "Signal Loss" now alarm,
which they never did. Warn people receiving notifications before upgrading;
verify delivery, acknowledgement, cancellation and alarm settings on your setup.
Do not infer phone delivery from a passing automated test.

The Bolus Wizard Preview and Careportal Bolus Wizard correct mixed display/profile
unit handling, and the calculator uses the profile selected by its caller.
Zero temporary basals, cancels and zero amounts are retained by the corrected
socket duplicate check. Temporary Targets are stored in mg/dL labelled `mg/dl`,
including targets uploaded with mmol/L labels. These fixes can change stored
or displayed results; review the [testing guide](testing-notes.md) for your
units and connected apps. This is not advice about insulin dosing; discuss
questions about therapy with your care team.

### Record identity is clearer, but not identical to 15.0.9

Re-sends recognized by identity normally replace the live stored record:
omitted fields can be removed. Explicit edits and API v1/in-process entries have
path-specific rules. Default `WRITE_DELETED_RESEND=stay` keeps identity-matched
deleted records deleted instead of recreating them.

`WRITE_IDENTIFIER_INDEX=try` attempts a unique identifier index at startup;
existing duplicate identifiers are reported as counts, not automatically deleted.
**Setting `off` does not remove an existing index.** `drop` removes it.
Back up first and rehearse rollback on a disposable deployment.

Operators and app authors should read the
[compatibility boundaries](../../docs/10-domain/nightscout-v16-ecosystem-deep-dive.md#compatibility-without-synchronized-client-releases)
before choosing non-default write settings. There is no single setting that
restores every 15.0.9 behavior.

## Fixes and optional improvements

The merged work fixes report counting and daylight-saving handling, dose-label
rounding, notification/live-update behavior and late or duplicate Pushover
callbacks. The new Statistics Summary/AGP report and glucose-distribution
report additions are described in [contents.md](contents.md).

The glucose pentagon/PGR withholding rules are "implementation guards, not
validated clinical PGR thresholds"; PGR is a research metric and the numerical
checks "do not constitute third-party clinical validation". It is a report
figure, not a treatment recommendation; talk to the care team before acting on it.

`THEME=modern` selects the optional responsive dashboard; existing themes remain.
`SHOW_SECONDS` is optional. Runtime/database/library refreshes and page bundles
modernize internals without making either option mandatory.

## Notes for people running sites and writing apps

Legacy API v1 replies remain the default. Requesting
`Nightscout-Write-Results: items` or `?results=items` opts into an item-results
envelope; an uploader must understand per-item outcomes before using it.
A successful HTTP batch response does not prove every item was stored.

`WRITE_VALIDATION` defaults to `off`; `log` and `reject` are optional.
**Most uploaders lose a refused record without showing an error.**
An unrecognized validation mode reads as `off`. Socket refusal/failure slots
under `reject` are experimental; test uploader retries before enabling rejection.
Unset `WRITE_IDENTIFIER` is not identical to explicit `lenient`; `strict` is
opt-in. API v3 refuses a client body `_id` with 400.

`API3_SETTINGS_STRICT_READ_ENABLED` is optional: an AAPS 4.0 follower using a
read-only token not supplied by AAPS is refused when it is on. Do not enable it
as a prerequisite for upgrading ordinary clients.

`DEBUG_LOGGING=true` includes uploaded records in logs, which can contain health
data. Normal write logs use summaries. Do not publish raw diagnostic logs or tokens.

The image command is `nightscout single`; SIGTERM/SIGINT now stop connections
cleanly. Under `restart: on-failure`, a SIGTERM not originating from `docker stop`
now exits successfully and can leave the container stopped. Custom entrypoints
must not prepend `node` to `nightscout single`. `nightscout serve` is reserved;
this is not a production multitenancy release.

## Known issues and release acceptance still open

Restricted-token browser issue nightscout/cgm-remote-monitor#8829 is
**nonblocking by maintainer decision**. Its reporter reports failure on dev;
neither maintainer reproduced it, and the maintainer reports working DIY and
production/service environments. It remains open for environment-specific
follow-up, not claimed fixed.

BF-72/BF-161 private fixes, their final combined-tree checks and coordinated
release-time disclosure remain pending. Live Pushover/APNs, cohort outcomes,
upgrade/rollback and final-candidate quiet-period acceptance are not closed by
24-48 hours of informal use alone.

The full residual-defect list is in [contents.md](contents.md). Draft proposals
for controller registration, nonresident profiles, APNs background pushes and
new reports are not promised by these notes.

**Before final publication:** reconcile every operator-visible change and
unresolved defect with the tagged tree and verification record; add final
security notices, accepted residual risks, hosting/kernel caveats, backup/rollback
instructions, and maintainer approval. Record the runtime-floor policy waiver.
This draft is useful preparation, not a completed release sign-off.
