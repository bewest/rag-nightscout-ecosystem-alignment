<!-- Body for bf/alarm-anonymous-no-delay at 8e295769 (one commit on origin/dev e3adc91d), 2026-09-26. This comment is hidden on GitHub. -->
**BF-80**: a web page that has nobody signed in receives alarms over `/alarm` straight away, even when its address is being slowed down after failed logins. Anything that presents a password or token is still slowed down exactly as before. `8e295769`, one commit on `dev` `e3adc91d`.

## What changes for you

*This is a plain-language summary for people who run their own Nightscout site for themselves or a family member. Nightscout is not a medical device, and nothing here is medical advice. Do not rely on a web page or app as your only alarm; check a surprising reading against your meter, and talk to your care team about how you set up alarms.*

Some words used below:

- **Alarm**: the high and low alerts your Nightscout site raises itself, for example "Urgent LOW". The web page receives them over a live connection called `/alarm` and sounds them.
- **Failed-login delay**: when something connects to your site with a wrong API secret or token, your site makes the next attempts from the same internet address wait: 5 seconds for each recent failure, adding up. This slows down anyone trying to guess your secret.
- **Address**: the internet address your site sees a device connecting from. Every phone, tablet and computer on the same home Wi-Fi usually shares one address.
- **Signed in**: the web page has your API secret or a token saved (the padlock icon shows you as authenticated).
- **`AUTH_DEFAULT_ROLES`**: the setting that says what someone who is *not* signed in may see. `readable` (the usual setting) lets them see readings and alarms. `denied` lets them see nothing.

**Who is affected:** sites running the development version (`dev`), not the 15.0.8 release. It happens when a device on the same address as the viewer keeps failing to log in, for example an uploader or follower app with an old API secret on the home Wi-Fi.

**What was wrong:** while that address was being slowed down, a web page opening or reconnecting there was also made to wait before it was allowed to receive alarms. An alarm that was raised in that time did not reach it. The page only heard it when the site repeated the alarm later. In testing that was 38 to 56 seconds late, and longer after many failures. Nothing on the page said that alarms were being held back.

**What this change does:** a web page that is **not signed in** is no longer made to wait. It gets exactly what someone not signed in is allowed on your site, straight away:

- On a site set to `readable`, it receives alarms at once.
- On a site set to `denied`, it still receives no alarms, as before.

**What does not change:**

- **A signed-in web page on that address still waits.** Your site cannot tell whether a password or token is right without checking it, and it checks it only after the wait, so that a guesser learns nothing. A signed-in page there is admitted after about 10 seconds (after three failures close together) and hears an alarm raised in that time only when it is repeated, as before this change.
- A device on a different address is not affected.
- AndroidAPS already connects to `/alarm` in a way that is not slowed down.
- Your site still shows the "Failed authentication" notice to admins for every failed login.

**Do you need to do anything?** No. If you see "Failed authentication" notices, find the device with the old secret or token and fix it: until you do, signed-in devices at the same address can still get alarms late.

## Technical detail

### The defect

`lib/authorization/index.js` `resolve()` waits out `shouldDelayRequest(keys)` **before** it checks the credential (the comment at `:152-158` explains why: answering a correct guess at once would turn the delay into a signal). BF-75's fix admits an `/alarm` socket to the `AlarmReceivers` room only once `resolve()` has returned an entitlement. So a socket connecting while its resolved address is in the delay joins the room after the penalty, misses the first emission, and gets the alarm at the next re-emission.

On a readable site, the web page with nobody signed in sends `subscribe({ secret: null })`. `hashauth.hash()` is `null` and `client.authorized` is unset, so `jwtToken` is `undefined` and is dropped from the packet (`lib/client/index.js` `subscribeForAlarms`). `resolve()` then takes its `!authAttempted` branch and returns `AUTH_DEFAULT_ROLES`, but only after the wait.

### The fix

- `authorization.resolveAnonymous(callback)` (new) returns `{ shiros: rolesToShiros(defaultRoles), defaults: true }`. That is what `resolve()` returns for no credential, but without consulting the delay list. It neither records nor clears a failure.
- `alarmSocket.subscribe`'s web path uses it when `presentsCredential(message)` is false. That means every one of `secret`, `jwtToken`, `token` and `accessToken` is absent, `null`, `''` or (for consistency with `resolve()`) the string `'null'`. `token` and `accessToken` are counted even though the web path does not read them, so that a message is never answered as anonymous because its credential was in an unexpected field.
- Any value in any of those fields still goes through `resolve()` unchanged.
- `resolve()` is not modified. The connect-time admission (`resolve({ api_secret: null, token: null })`) is not modified. The comment on it is updated, because an anonymous `subscribe` now resolves *before* a deferred connect-time admission. `hasSubscribed` already makes that order safe.

**Why not change `resolve()` itself?** Skipping the delay in `resolve()` when no credential is presented would be a one-line change. It would also stop anonymous HTTP requests and anonymous main-namespace socket requests from waiting. #8754's `tests/authdelay.test.js` asserts the opposite ("makes a request with no credential from a throttled address wait, as dev does"). With that one-line change applied, that test fails (`expected 1 to be above or equal 120`). This PR leaves HTTP and the main namespace as they are.

### What a guesser gets

Nothing new. Every guess carries a credential, and every credential still waits for the full delay, before it is checked. An anonymous subscribe gets `AUTH_DEFAULT_ROLES`, which it would get from any address, and it does not shorten or lengthen anyone else's delay. The tests show:

- a wrong secret is held for the full delay;
- a valid web token is held for the full delay;
- five anonymous subscribes from a throttled address leave the next wrong secret there held for the full remaining penalty, and no longer;
- the "Failed authentication" admin notification fires once per failure.

### Measured on a booted server

Measured with each tree's real server, the default failed-login delay and default proxy settings, on Node 22.23.2 and MongoDB 7.0.43. In each case the viewer's address had recent failed logins, the viewer then connected to `/alarm` and subscribed, and an urgent low was raised shortly after. The probe is kept outside the repository.

The table gives the subscribe ack time, then when the viewer got `urgent_alarm`, measured from the upload. "not in 20 s" means it had not arrived within the 20 s window.

| viewer (readable site) | `v15.0.8` `92d08342` | `dev` `e3adc91d` | this branch `8e295769` |
|---|---|---|---|
| no failures, not signed in (control) | 2 ms / 13 ms | 2 ms / 13 ms | 1 ms / 13 ms |
| not signed in, `{ secret: null }` | 9999 ms / 12 ms | 9999 ms / not in 20 s | **1 ms / 13 ms** |
| wrong secret | 9999 ms / 11 ms | 10000 ms / not in 20 s | 9999 ms / not in 20 s |
| valid web JWT (signed in) | 10000 ms / 9 ms | 10002 ms / 37.7 s | 10000 ms / 37.7 s |
| connects, never subscribes | — / 12 ms | — / 49.6 s | — / 10.8 s and 49.6 s (two runs) |

| viewer (denied site) | `v15.0.8` | `dev` `e3adc91d` | this branch |
|---|---|---|---|
| not signed in, `{ secret: null }` | 10001 ms, `read:false` / **12 ms** (BF-75) | 9999 ms, `read:false` / none | **1 ms, `read:false` / none** |
| valid web JWT | 10000 ms / 10 ms | 10002 ms / not in 20 s | 10002 ms / 49.5 s |

The 15.0.8 column shows alarms arriving at once for everyone. That is because 15.0.8 broadcasts to the whole namespace, which is BF-75. For the rows marked 37.7 s, 49.5 s and 49.6 s, the window was widened to 120 s.

The "never subscribes" row is unchanged by this PR. That path is the connect-time admission, which still waits, so when the alarm arrives depends on when it is repeated. No client in `externals/` connects to `/alarm` without subscribing (see below).

### Tests

`tests/api3.alarm-socket.anonymous-delay.test.js` (new) uses the api3 fixture. The fixture gains an `authFailDelay` option, defaulting to 0 as before. The test uses a 1500 ms delay and three wrong-`Bearer` v3 requests per scenario. The scenarios are independent and run side by side, so the file takes about 5 s. The cases are:

- An anonymous `{ secret: null }` viewer on a throttled readable address gets the alarm emitted 250 ms after subscribing within 1 s, with `read:true` and an ack under 250 ms.
- Empty-string `secret`/`jwtToken`/`token`/`accessToken` are treated as no credential.
- An anonymous viewer on a throttled denied address is answered under 250 ms with `read:false`, and no alarm arrives.
- These viewers are still held (ack ≥ 1200 ms) and miss the first emission:
  - a wrong secret;
  - `{ secret: null, token: … }`;
  - a valid web JWT.
- Controls: a signed-in viewer on a different address, and with no failures, is prompt.
- Anonymous subscribes neither clear nor extend the delay.
- The "Failed authentication" admin notification is raised 23 times (7 × 3 + 2).

**On `e3adc91d`**, 4 of 10 fail:

- `alarm not delivered within 1000 ms of emission` (×2);
- `expected 1497 to be below 250` (denied);
- `expected 2 to be above or equal 1200` (the wear-down guard, red on the parent because the anonymous subscribes themselves waited out the penalty).

**Full suite on `8e295769`:** 3180 passing, 0 failing, 3 pending, twice (`npm test`, Node 22.23.2, MongoDB 7.0.43, fresh database). `e3adc91d` gives 3170/0/3; the difference is the 10 new tests.

### Break-its

| change to the fixed code | result |
|---|---|
| every message treated as credentialed (fix off) | 4 fail: the three fix cases and the wear-down guard |
| every message treated as anonymous | 5 fail: wrong secret, ignored field and valid JWT are no longer held, the wear-down guard fails, and the notification count is off |
| only `secret`/`jwtToken` checked | 1 fails: ignored field |
| empty strings count as a credential | 1 fails: empty strings |
| anonymous answer ignores `AUTH_DEFAULT_ROLES` | 1 fails: denied |
| anonymous path records a failure | 5 fail, including the wear-down guard and the notification count |
| fixture delay forced to 0 | 4 "still held" cases fail (the controls are not vacuous) |

## Client impact

The following was read, not run.

- **Nightscout web page**: when not signed in, it sends `{ secret: null }` and is fixed by this PR. When signed in, it sends `jwtToken` or the secret hash and is unchanged.
- **AndroidAPS** (`NsConnectHandler.kt:81`) sends `subscribe({ accessToken })`, which goes through `resolveAccessToken` and was never delayed. If `accessToken` is empty, the message now counts as anonymous and is answered at once with the default permissions. Before, it got the same permissions after the wait.
- **LoopFollow** uses the main namespace (`authorize` with its token as `secret`), not `/alarm`. It is unchanged.
- **nightguard, LoopCaregiver, xDrip, xdripswift, NightscoutKit** do not use the `/alarm` socket.
- **Nocturne**'s socket.io bridge is its own server.

Not changed, for a later decision:

- The main namespace's `dataUpdate` for an anonymous viewer on a throttled address still waits (`verifyAuthorization` goes through `resolve()`). That delays the chart, not alarms.
- A signed-in viewer on a throttled address still waits (option 2 as decided).
