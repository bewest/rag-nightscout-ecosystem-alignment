<!-- Draft body, branch bf/profile-temp-cache at a06e75d6 (fix 2a64c500 on dev ca6fcfaf, merged with dev f105f688). Not pushed, no PR opened. This comment is hidden on GitHub. -->
An open Nightscout page could keep showing a temp basal after it had been cancelled or replaced (BF-94). The page's profile code remembered the last temp basal it had looked up, and that memory survived new data. This change resets it whenever the page receives new treatments, and makes it belong to one profile instance instead of the whole module. One commit on `dev` `ca6fcfaf`. The same defect is on 15.0.8 (`92d08342`), and it behaves the same way there.

## What changes for you

*A plain-language summary for people who look at Nightscout to follow their own or a family member's diabetes. Nothing here is medical advice; questions about therapy belong with your care team.*

**What was wrong.** A *temp basal* is a temporary change to the background insulin rate. AID apps such as AndroidAPS and Trio set them all the time. Nightscout shows the current rate in the **BASAL** pill under the glucose number, for example `T: 2.000U` while a temp is running, and draws it as the blue basal line at the top of the chart.

If the page was already open when the app **cancelled a temp basal or cut it short**, the page could keep showing the old rate:

- **After a cancel**, the pill kept showing the cancelled temp's rate, and the chart kept drawing it, **until the time the temp was originally due to end**. For a 30-minute temp cancelled after 10 minutes, that is up to 20 minutes. This happened when the cancelled temp was the only one on the chart. When earlier temps were on the chart, as they usually are for someone using an AID app, the page corrected itself within about 15 seconds.
- **After a temp was cut short and a new one started**, the pill showed the old rate for up to about 15 seconds. When the page held no earlier temps, the chart's basal line showed it as well.

Reloading the page, or opening it on another device, always showed the right rate. The difference was only in a page that stayed open.

This was a display error in Nightscout. **The pump and the AID app had the right rate the whole time**, and Nightscout stored the right data. Nightscout does not control the pump, so nothing was delivered differently. A caregiver watching an open page could have seen a temp basal that was no longer running.

Apps that send a temp basal and then a separate "end" record (OpenAPS-style cancels), and Loop when it sends a new temp without changing the old one, were not affected in our tests.

**What this change does.** The page now forgets the temp basal it remembered each time new treatment data arrives, so the pill and the chart show the same rate a freshly loaded page shows.

**Do you need to do anything?** No. Once your site runs a version with this change, reload any page you keep open (a bedside tablet, for example) so it loads the new code.

## Technical detail

### The defect

`lib/profilefunctions.js:19` (at `ca6fcfaf`) declared `prevBasalTreatment` at module scope. `tempBasalTreatment(time)` returned it whenever `time` fell inside its `[mills, endmills]`, before searching the current list. Only `profile.clear()` reset it, and `clear()` runs when an instance is created. `updateTreatments()` replaced the lists and cleared the `memory-cache` instance, but not this variable.

The server builds a new profile instance on every tick, so it is not affected. The browser keeps one `client.profilefunctions` (`lib/client/index.js:325`) and calls `updateTreatments` on every data update (`:1384`).

Whether the remembered object goes stale depends on how the update reaches the page:

- **A new treatment** is pushed onto `ddata.treatments` (`lib/client/receiveddata.js` `mergeTreatmentUpdate`). `processTreatments(false)` does not clone, so `processDurations` cuts the earlier temp's `duration` on the same object and `updateTreatments` recomputes its `endmills`. The remembered object is the cut one, so the lookup is right. This is the Loop new-temp case and the OpenAPS zero-duration end event.
- **An edited treatment** arrives as a delta with `action: 'update'`, and `mergeTreatmentUpdate` splices in the new object. The remembered object is the old one, with its original `endmills`. AndroidAPS API v3 sends a shortened temp as `PATCH /api/v3/treatments/{identifier}` (`nsclientV3` `nsUpdate`, `core/nssdk` `NightscoutApi.updateTreatment`). Trio re-uploads a temp whose rate or duration changed when it is finalized (`PumpHistoryStorage` sets `isUploadedToNS = false`), and `POST /api/v1/treatments` upserts it by `created_at` and `eventType`.

On each data update, `dataUpdate` computes the plugins' properties (and the pill) before the chart redraws, so the pill reads the remembered object first. The chart's basal sweep (`renderer.js` `getBasalRenderTimes` and `getTempBasal` at one-minute steps) then replaces the remembered object only when it reaches a time served by another temp. `updateClock` redraws at least every 15 seconds. So:

- with earlier temps in the chart window, the next redraw corrects the pill (up to about 15 s);
- with no other temp found by the sweep, the remembered object stays until its original `endmills` has passed.

### The change

```diff
-var prevBasalTreatment = null;
 function init (profileData, ctx) {
   ...
+  var prevBasalTreatment = null;
   ...
   profile.updateTreatments = function updateTreatments (...) {
+    prevBasalTreatment = null;
```

- **Reset in `updateTreatments`.** This is the change that fixes the browser. The remembered treatment belongs to the list it came from, so it is forgotten when the list is replaced, the same moment the `memory-cache` is cleared. Repeated lookups within one list, which is what the code comment's performance note is about (reports call `updateTreatments` once and then `getTempBasal` for every minute of every day), still use it.
- **Per instance.** Module scope also let one instance answer from another instance's list. The third unit test reproduces that on `ca6fcfaf`: a second instance's lookup replaces the first instance's answer. Moving the variable into `init` removes that sharing; it costs nothing, since each instance already has its own cache.

### Measured in a browser

Harness: `tools/lab/bf94-browser/probe.js` in the alignment repo. Chromium (Playwright) against a booted server per tree, MongoDB 7.0.43, Node 22.23.2, a 1.0 U/h profile, mg/dL. For each scenario, temp A (2.0 U/h, 30 min) starts about 10 minutes earlier. A page is opened and shows `T: 2.000U`, then the client's change is sent over REST. The open page is sampled every 2 s for 75 s: the pill text from the DOM, the basal line's value at "now" read from the rendered SVG path, and `getTempBasal(now)`. Then a fresh page in a new browser context (the control) and a reload of the open page. Each scenario ran with and without ten-minute temps over the previous three hours ("history").

| scenario | expected now | `ca6fcfaf` and 15.0.8, open page | this branch, open page | fresh page / reload (all trees) |
|---|---|---|---|---|
| Loop: new temp B (0 U/h), A unchanged | 0 | correct | correct | correct |
| Trio: A re-uploaded shortened + B | 0 | pill `T: 2.000U` for 14 s, with or without history; line 2.0 for 14 s without history | correct | correct |
| AAPS v3: PATCH A shortened, POST B | 0 | pill and line 2.0 for 14 s without history; pill for one sample (0 s) with history | correct | correct |
| Trio cancel: A re-uploaded shortened | 1.0 | pill and line 2.0 for the whole 75 s without history; 6-14 s with history | correct | correct |
| AAPS v3 cancel: PATCH A shortened | 1.0 | as Trio cancel | correct | correct |
| OpenAPS cancel: new zero-duration temp | 1.0 | correct | correct | correct |

15.0.8 and `ca6fcfaf` gave the same results in every scenario. How long a stale cancel persists: with A programmed for 13 minutes and cancelled after about 10, the open page showed `T: 2.000U` until 11 s (dev) and 9 s (15.0.8) after A's original end, then `1.000U`.

In the AAPS v3 rows the PATCH and the POST arrive as two updates. The one sample on this branch that differs from the final value is the page correctly showing 1.0 U/h between them.

### Tests

`tests/profile-temp-cache.test.js`, four tests:

1. a temp shortened (a new object) and a new one started: the lookup returns the new one;
2. a temp shortened with nothing after it: the lookup returns the scheduled basal;
3. two instances: the second instance's lookups do not change the first one's answers;
4. repeated lookups within one list still return the right temp (regression).

On `ca6fcfaf`, tests 1-3 fail (`expected 2 to be 0`, the cancelled temp still returned, `expected 1.5 to be 2`) and test 4 passes. Removing only the reset fails tests 1 and 2. Restoring only the module-scoped variable fails test 3.

Full suite on this branch (MongoDB 7.0.43, Node 22.23.2): 3538 passing, 0 failing, 4 pending. On `ca6fcfaf` it is 3534/0/4; the four extra tests are the new file. After merging `dev` `f105f688` (#8799, documentation only) the branch is `a06e75d6`: full suite 3538/0/4 again (MongoDB 7.0.43, Node 24.15.0).
