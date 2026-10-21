# Nightscout 15.0.9

15.0.9 is a bug-fix and security release. It brings 100 pull requests (549 commits) merged since
15.0.8. Its main themes:

- closing several security advisories;
- making records consistent between API v1, API v3 and the websocket, which is what AndroidAPS,
  Loop, Trio, xDrip+ and the careportal each use;
- correcting alarms and displays that had never worked as documented;
- stopping several ways a single request could stop the server;
- defining how the server treats the request shapes real clients send, checked against those
  clients and against 15.0.8.

## Highlights

- **Security fixes** for the live-update connection, alarm delivery, API v1 query filters and
  error pages, and for how the admin page stores access tokens.
- **AndroidAPS and the rest of the ecosystem now see the same records.** Careportal and caregiver
  entries reach AndroidAPS. Records AndroidAPS deletes stop counting. Late or edited AndroidAPS
  treatments count in IOB and COB. Two treatments entered at the same moment are kept apart.
- **Alarms**: the insulin-age URGENT level, mmol/L low thresholds, the pump-suspended warning and
  AndroidAPS loop alerts after re-enabling the loop now work as documented.
- **A new `TRUST_PROXY` setting** controls which proxies Nightscout believes when it works out a
  visitor's address. Leaving it unset keeps the 15.0.8 behaviour.
- **nightscout-connect 0.1.0**, the built-in CGM connector, no longer writes CGM account details
  to the log, and it backs off properly after a service outage.
- **Quieter logs by default**, with opt-in debug settings.
- **A test suite more than twice the size**: 3,566 passing tests, against 1,533 on 15.0.8.

## Security

These fixes apply to 15.0.8 and earlier releases. Security advisories for them will be published
separately.

- **The live-update connection checks read permission** before sending recent data, alarms or
  notifications, as the HTTP API already did, so `AUTH_DEFAULT_ROLES=denied` now covers it. Sites
  using the default `readable` role are unaffected. (#8744)
- **Alarm delivery over the alarm socket is limited to clients entitled to read**, and silencing
  an alarm with a token requires the `notifications:*:ack` permission. Among the built-in roles,
  only `admin` has it. (#8745)
- **API v1 accepts a fixed list of query operators.** Any other operator, and the undocumented
  `pipeline` option on the count endpoints, is refused with an HTTP 400 that names it. (#8743)
- **Two shared read routes check per-collection read permission**, and the alarm socket no longer
  logs credentials. (#8751)
- **The admin page no longer stores a subject's access token in readable form when the subject is
  edited.** Copies written by earlier releases stay in the database until those tokens are
  rotated. (#8754)
- **The failed-login delay is applied before the credential check** and is counted per address
  and per credential. Its list is bounded and swept. On a site that sets `TRUST_PROXY`, the address
  it counts cannot be supplied by the visitor. (#8754, with #8763, #8764, #8765)
- **Subject and role records keep only their documented fields** (name, roles or permissions,
  notes, created date). Saving one no longer clears its notes or creation date. (#8754)
- **The "readable by world" admin notice now appears** when role settings, including
  `TREATMENTS_AUTH=off`, make data readable without login. (#8746)
- **Error replies carry only a status and a short message** unless `NODE_ENV=development`. The
  full error is still logged. This includes sites where `NODE_ENV` is unset. (#8793)
- **An unbounded request to two little-used API v1 addresses is refused** before any work starts.
  Before, it could keep the server busy for several seconds. (#8795)
- **A bearer token whose subject was deleted is refused like a wrong token.** Before, it stopped
  the server, and stopped it again after each restart until the token expired (up to 8 hours). API
  v3 now answers such a token with 401 instead of 403. (#8815, @awss1i; fixes #8225)
- **A subject or role without a name is refused**, and one already stored no longer stops the
  server. (#8769; fixes #7110)
- **Loop remote-command errors are shown without internal diagnostics.** (#8583, @NandhaKishorM)

## Changes in behaviour

These are corrections, but each one changes what an operator, an alarm recipient or an API client
sees.

- **Insulin age has an URGENT level.** The `IAGE_URGENT` check (72 h by default) could never be
  true, so the pill stayed at WARN. It now turns URGENT. With `IAGE_ENABLE_ALERTS` on (it is off by
  default), a one-time "Insulin reservoir change overdue!" notification is sent during the hour the
  threshold is reached. The cannula, sensor and battery age alerts already worked this way. (#8739)
- **On mmol/L sites, each `BG_` threshold is read on its own.** A value below 30 is taken as mmol/L
  and converted; 30 or more is taken as mg/dL. Low alarms now fire on sites where only some
  thresholds were set in mmol/L, and each conversion is logged once. (#8766; fixes #7729)
- **`PUMP_WARN_ON_SUSPEND` raises a "Pump Suspended" warning**, and the pump pill takes the
  warning colour while the pump is suspended. (#8767; fixes #5622)
- **AndroidAPS percentage and time-shifted Profile Switches**: basal, ISF and carb ratio on the
  site now show the scaled values AndroidAPS uses. (#8774; fixes #7771)
- **IFTTT Maker events use untranslated level names on every site language.** Applets that were
  renamed to translated names need their original names back. (#8773; fixes #8104)
- **Careportal and caregiver treatments reach AndroidAPS through API v3 history.** AndroidAPS
  applies them according to its own carbs and insulin settings. Records written through API v1,
  the websocket or in-process now appear in v3 history, and v1 records carry `srvModified` and
  `srvCreated`. (#8775; fixes #8244)
- **Records that AndroidAPS deletes (`isValid: false`) stop counting** in v1 reads, IOB, COB, the
  chart and reports. They can still be read with `find[isValid]=false`. A v1 DELETE is still a hard
  delete. (#8775)
- **Late or edited AndroidAPS v3 treatments count in Nightscout's own IOB and COB**, and
  treatments stay in time order. A COB total that was too high can therefore drop. (#8784)
- **API v1 `count`:**
  - A read with `count=0` and a date range returns that range, as before.
  - A read with `count=0` and no date range returns the default number of records instead of the
    whole history.
  - A leading number followed by `?` (as oref0 sends it) is read as the count.

  The first and last of these send `Deprecation` and `Warning` headers. They can be turned off
  with `API_V1_COUNT_ZERO_WINDOW` and `API_V1_COUNT_LEADING_NUMBER` (both default `true`).
  Malformed counts, and a DELETE with `count=0`, get HTTP 400, and nothing is deleted. Saves and
  updates ignore `count`. (#8738, #8748, #8761)
- **`GET /api/v1/entries/<id>` for an unknown id answers `200 []`** instead of a 500. (#8772)
- **An entries POST that matches a stored reading answers with the stored `_id`.** (#8758)
- **`/api/v2/properties`**: `cob.treatmentCOB` is a number, present only beside a current COB from
  the uploader. (#8587)
- **Loop remote commands record the sender's address** as `TRUST_PROXY` resolves it, and it is
  stored on each remote override. (#8764, #8765)
- **Voice endpoints (Alexa, Google Home) ignore the request's locale.** They no longer change the
  language for the rest of the server. (#8739)
- **In query parameters, `_` is no longer turned into a space.** (#8736)

## Fixed

### API and data sync

- A record's own `_id` finds, edits and deletes it through API v1, API v3 and the websocket.
  (#8758)
- Schema-driven query type coercion, and the `$exists` and `$type` operands. (#8737)
- Count endpoint filters, v3 `limit` validation, v3 paging and dotted `fields`. (#8738)
- Numeric date and sgv filters on v1 activity and devicestatus. (#8771)
- Two treatments at the same time are kept apart by client identity or, for v1 writes without
  one, by carbs and insulin. (#8780; thanks to @motinis for #8185)
- API v3 writes to records created through v1 are accepted. (#8776)
- API v3 DELETE reaches records whose identifier is `null`, `""`, `0` or `false`. (#8778
  @AndyLow91, #8783)
- A v1 treatment re-sent with an empty identity is stored once, and the v3 history clock is
  restored after a restart. (#8781, @AndyLow91)
- A v1 list of dates under the date field is read instead of answering 500, so xDrip4iOS bulk
  deletes remove the listed readings. (#8791)
- A merge delete no longer drops an unmatched update. (#8734)
- Deleted documents are no longer resurrected in the runtime cache. (#8567, @bjorkert)

### Alarms and notifications

- AndroidAPS loop and pump alerts come back after an open-ended loop disable is re-enabled.
  (#8568, @lejcey)
- An alarm on a page with no reading no longer throws. (#8755)
- `/pebble` reports its delta in the requested units, uses its own copy of the readings and gives
  its bolus estimate in site units. (#8777; thanks to @dhermanns for #6220)
- Each Loop remote command shuts down its APNs connection when the push settles. (#8770)
- Clock views turn an old reading stale while their data fetch is failing. (#8768; thanks to
  @gth001 for #7036)
- The clock view shows the worried face for low and falling readings. (#8699, @AndyLow91; thanks
  to @robertrub for #8638)

### Display, reports and clock views

- An open page shows a temp basal that AndroidAPS (v3) or Trio shortens or cancels, without a
  reload. (#8800)
- A treatment's BG in the chart tooltip is converted from the units it was saved in. (#8801;
  thanks to @bjornoleh for #5940)
- Clock views opened from the menu keep the page's access token, and a refused clock says so.
  (#8802; thanks to @herzogmedia for #7377)
- The context chart's time window can be dragged all the way back to now. (#8807)
- A drag-moved or split treatment keeps its new time for IOB and COB. (#8760)
- The Day to Day report draws an event with a duration on every day it covers. (#8788, @awss1i;
  thanks to @bjornoleh for #8223)
- The Food Editor's lists scroll by touch on phones. (#8790, @awss1i; thanks to @rickcowan for
  #8192)
- A 48-hour choice in the main chart's hour selector. (#8530, @alanshurafa)
- Filter the treatments report by event type. (#8590, @bjorkert)
- The report page is built once per load. (#8589, @bjorkert)
- Report SGV de-duplication no longer cascades. (#8588, @toniuhlemann)
- Daily Stats estimated A1c is computed from mg/dL. (#8602, @AndyLow91)
- COB comes from the uploading system when it is current. (#8587, @bjorkert)
- Pills and the profile editor work on sites with incomplete data. (#8732, @alias-rahil; thanks
  to @KrawuzlT1 for #7324)
- `chart.update()` is guarded against a zero-height container. (#8729, @wyomarus)
- Profile-switch schedules are preprocessed, and unnamed profiles are preserved. (#8701, #8702,
  @AndyLow91)
- The quick-pick chooser index and the quickpicks API are fixed, and the chooser is rebuilt when
  opened. (#8735, #8756)
- A bare URL parameter is handled, and `%10` slots are read. (#8736)

### Server stability and operations

- A failed treatments query no longer stops the server. (#8697, @AndyLow91; thanks to
  @craigpress for #8675)
- A failed database read on v1 activity or `profile/current` answers 500 instead of stopping the
  server. (#8796)
- Quadratic treatment scans are removed, and the cost of cache clones is reduced. (#8733, #8740)
- Routine logs are off by default. `DEBUG_LOGGING` and `CONNECT_DEBUG` turn detailed logging on.
  (#8726, @AndyLow91; thanks to @TomaszSmart for #8714)
- Credential settings are kept as strings, so Dexcom account names that are phone numbers, and
  credentials with leading zeros or a plus sign, work. (#8741, @vidia; thanks to @fsallstrom for
  #8056 and @JoanoToxo for #8181)
- Deployments with npm 12 work (`allow-remote=root`), and CI covers Node 24 with npm 12. (#8601,
  @AndyLow91; thanks to @tycho40 for #8600)
- The bundled `docker-compose.yml` sets the MongoDB open-file limit to 64000. Alexa answers
  unhandled request types. The boot error page renders without an error object. (#8753)
- The README and `azuredeploy.json` describe the settings the code reads, including every `API3_`
  setting. (#8799)
- The MiniMed deprecation warning names the `CONNECT_` settings that replace `MMCONNECT_`. (#8757)
- iOS Loop push-notification and websocket integration tests. (#8419, @je-l)
- Documentation fixes. (#7338, @jgr-lab)
- The boluswizardpreview tests read one clock. (#8785)

## Deprecated

- **MongoDB 4.4.** It is still tested; support will be removed in a later release. (#8516
  @PieterGit, #8750)
- **The built-in legacy MiniMed (`MMCONNECT_`) and Dexcom bridge (`BRIDGE_`,
  `DEXCOM_BRIDGE_USE_LEGACY`) connections.** They will be removed in a later release. The built-in
  connector (`CONNECT_` settings) replaces both. Since 15.0.8, `BRIDGE_` settings have been handled
  by the connector unless `DEXCOM_BRIDGE_USE_LEGACY=true`.
- **The `count=0` and leading-number `count` forms on API v1.** Both are accepted with a
  deprecation warning.

## Dependencies

- **nightscout-connect 0.1.0**, pinned exactly (#8752, #8759, #8762). Changes since 0.0.13:
  - credential-safe logging, with an opt-in debug logger;
  - listeners are released on stop;
  - a CareLink "no reading" marker is no longer stored as glucose 0;
  - retries back off with jitter and are capped;
  - the reader subject gets read roles, so copying from a Nightscout site with
    `AUTH_DEFAULT_ROLES=denied` works;
  - profile sync no longer stalls;
  - LibreLinkUp v4 authentication;
  - Glooko timezone handling, CGM fallback and pump events.
- **D3** 5.16 → 7.9.0. (#8573)
- **`proxy-addr`** 2.0.7 → 2.0.8, which clears a critical advisory on IPv6-notation `TRUST_PROXY`
  subnets. (#8806)
- **Overrides moved to patched releases**: `qs`, `ajv`, `form-data`, `ip-address`, `fast-uri`,
  `brace-expansion`, and the `axios` inside minimed-connect-to-nightscout. (#8749, #8786, #8794)
- **Dependabot updates**: UUID, jsdom/ws, Babel, Axios, Socket.IO, Express/body-parser,
  ip-address, fast-uri, socket.io-parser, DOMPurify, js-yaml, Mocha, PostCSS and brace-expansion.
  (#8529, #8544, #8550, #8565, #8566, #8571, #8575, #8576, #8577, #8578, #8579, #8581, #8582,
  #8586)
- **Translations from Crowdin.** (#8599, #8603)

## Testing and compatibility

The largest area of change in this release is the test suite. Tests make up 143 of the 314 files
changed and 21,641 of the 30,337 lines added; `lib/` accounts for 5,126. The suite grew from
1,533 passing tests on 15.0.8 to 3,566 in the last full run before release. That run covered
Node 20, 22 and 24 against MongoDB 4.4 and 7.0, with 0 failing.

The compatibility behaviour in this release was decided against what clients actually send:

- **A client survey.** The source of 40 client projects was surveyed: uploaders, AID apps,
  followers, reports and tools.
- **Replay probes.** Thirteen probes sent those clients' request shapes to 15.0.8 and to the
  development version. The `count`, filter and identity handling described above follows from
  those results.
- **A side-by-side soak.** 15.0.8 and the release candidate received the same traffic. Their
  replies were compared against a list of intended differences.

## Upgrade notes

- Node.js 20 or later is required. Node 20, 22 and 24 are tested.
- MongoDB 4.4 is deprecated. MongoDB 5.0 and 6.0 are supported.
- `TRUST_PROXY` unset behaves as 15.0.8 did. Its values are described in the README.
- Access tokens that earlier releases stored in readable form remain in the database until they
  are rotated.

## Known issues

- An alarm threshold entered in mmol/L on a site that is not set to mmol/L is read as mg/dL, so
  a low threshold such as `3.9` never fires. An out-of-range high threshold is replaced, and only
  the server log says so.
- The Bolus Wizard Preview uses the profile's sensitivity and targets unconverted, so where the
  profile's units differ from the display units, its estimate and warning are off by a factor of
  about 18. The careportal's Bolus Wizard has the same unit mix, and its profile picker saves the chosen profile's name with the active
  profile's values. All three are unchanged since 15.0.8.
- A page with no current glucose reading does not present server alarms, including device
  alarms.
- An uploader whose clock runs ahead delays the stale-data warning by about the size of the error.
- While `TRUST_PROXY` is unset, the failed-login delay can be avoided by supplying a forwarded
  address. Nightscout logs this at startup.
- A delete made through API v1 or the websocket (the careportal, Loop, Trio, xDrip+) does not
  reach AndroidAPS.
- Two careportal entries in the same minute with the same amount are stored as one. So are an
  AndroidAPS bolus and carbs recorded in the same millisecond as "Meal Bolus".
- After AndroidAPS takes over a v1 record at the same time and event type, a later re-send of the
  v1 entry can be stored again.
- A record whose identifier was saved as a list cannot be deleted through API v3. A record saved
  with an empty identifier cannot be edited through API v3 by the id it shows.
- The `API3_AUTOPRUNE_*` settings delete records older than the set number of days on each API v3
  write to that collection. A failed prune stops the server. They are off unless set.
- The Day to Day report draws a temporary target that was cancelled early for its full planned
  length.
- Reports → Profiles can omit profiles saved on the report's last day when there are several.
- Reports → Treatments shows the old row after an edit until **Show** is pressed again.
- The careportal can prefill "Entered By" with `undefined`.
- During an AndroidAPS percentage Profile Switch, the basal pill shows ISF and carb ratio
  unrounded.
- For about a minute after a new phone or a reinstalled Loop uploads its settings, a remote
  command can still be sent to the old device.
- `$exists` understands only `true`, `false`, `1` and `0`. Silencing an alarm over the socket has
  no upper bound.
- Crowdin translations made after early September are not included.
- `npm audit` reports these advisories in 15.0.9:
  - `node-forge` GHSA-86w9-cpqp-85rv: the signature check it concerns is not used by Nightscout.
  - `braces` GHSA-vfj7-8cjw-p6xm: a deeply nested pattern on `/times`, `/times/echo` or `/slice`
    fails that request.
  - `compression` GHSA-vc2v-76pw-4v95: fixed in 1.8.2.
  - `follow-redirects` GHSA-q3jh-wrc6-jgq8 and GHSA-8r9p-f939-6h3c: they concern header forms
    that `axios` does not use.

## Thank you

**Code contributors**: @AndyLow91, @bjorkert, @awss1i, @NandhaKishorM, @alias-rahil, @wyomarus,
@vidia, @toniuhlemann, @lejcey, @alanshurafa, @je-l, @PieterGit, @jgr-lab and @bewest. Thanks
also to @sulkaharo for the Crowdin syncs, and to the Crowdin translators.

**Security reporters**, for reporting privately: @code2344, @SelcukCoskun and @SounLabs.

**Reporters whose issues are fixed in this release**: @AgushkaNightscout, @aiwaz, @bjornoleh,
@craigpress, @dhermanns, @fsallstrom, @gardenrobot, @gth001, @herzogmedia, @inventor96,
@JoanoToxo, @KrawuzlT1, @motinis, @mrinnetmaki, @rickcowan, @robertrub, @Stan-Di, @TomaszSmart,
@twiniars and @tycho40.

**Commenters who confirmed, narrowed down or tested those issues**: @Alamo04, @BrianWieder,
@cameronm77, @CHR15714N, @datamystic, @jakobsandberg, @jmkraan74, @marionbarker, @mstry9,
@netphreak0101, @oddst, @PashCracken, @ps2, @psonnera, @raui100, @sdolenc, @sheinapribadi-star,
@stevoh6 and @Tuphal.

**nightscout-connect 0.1.0** includes work from @erikpendragon, @HockeyTrafalgar,
@lukas-slansky, @lsandini and @ryceg.

**Testers**: thanks to the Loop, Trio and AndroidAPS users who ran the development version on
their own sites for weeks before this release.
