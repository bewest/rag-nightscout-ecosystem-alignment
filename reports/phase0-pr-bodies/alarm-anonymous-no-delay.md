<!-- Body for bf/alarm-anonymous-no-delay at cd2dfb1f (two commits on origin/dev e3adc91d: 8e295769, cd2dfb1f), 2026-09-26. This comment is hidden on GitHub. -->
**BF-80**: on a site where visitors who are not signed in may see readings (`AUTH_DEFAULT_ROLES=readable`), every web page and app connected to `/alarm` receives alarms straight away again, even when its address is being slowed down after failed logins. Checking a password or token is still slowed down exactly as before. On a site set to `denied`, nothing changes. `8e295769` and `cd2dfb1f`, two commits on `dev` `e3adc91d`.

## What changes for you

*This is a plain-language summary for people who run their own Nightscout site for themselves or a family member. Nightscout is not a medical device, and nothing here is medical advice. Do not rely on a web page or app as your only alarm; check a surprising reading against your meter, and talk to your care team about how you set up alarms.*

Some words used below:

- **Alarm**: the high and low alerts your Nightscout site raises itself, for example "Urgent LOW". The web page receives them over a live connection called `/alarm` and sounds them.
- **Failed-login delay**: when something connects to your site with a wrong API secret or token, your site makes the next attempts from the same internet address wait, a few seconds for each recent failure, adding up. This slows down anyone trying to guess your secret.
- **Address**: the internet address your site sees a device connecting from. Every phone, tablet and computer on the same home Wi-Fi usually shares one address.
- **Signed in**: the web page has your API secret or a token saved (the padlock icon shows you as authenticated).
- **`AUTH_DEFAULT_ROLES`**: the setting that says what someone who is *not* signed in may see. `readable` (the usual setting) lets them see readings and alarms. `denied` lets them see nothing.

**Who is affected:** sites running the development version (`dev`), not the 15.0.8 release. It happens when a device on the same address as the viewer keeps failing to log in, for example an uploader or follower app with an old API secret on the home Wi-Fi.

**What was wrong:** while that address was being slowed down, a web page opening or reconnecting there was also made to wait before it was allowed to receive alarms, whether or not it was signed in. An alarm raised in that time did not reach it. The page only heard it when the site repeated the alarm later: in testing, 38 to 56 seconds late, and longer after many failures. Nothing on the page said that alarms were being held back.

**What this change does:**

- **On a site set to `readable`**, every page connected to `/alarm` now receives alarms straight away, signed in or not, as 15.0.8 does and as a page on any other address does. It starts with what someone not signed in is allowed to see. If it is signed in, its password or token is still checked after the wait, and only then does it gain anything extra (such as being allowed to silence an alarm for everyone).
- **On a site set to `denied`**, nothing changes. A page that is not signed in receives no alarms. A signed-in page on a slowed-down address still receives alarms only once its password or token has been checked, after the wait, so an alarm raised during the wait reaches it only when the site repeats it.

**What does not change:**

- **Guessing is exactly as slow as before.** Every password or token is checked only after the full wait, and a wrong one gains nothing.
- A device on a different address is not affected.
- AndroidAPS already connects to `/alarm` in a way that is not slowed down.
- Your site still shows the "Failed authentication" notice to admins for every failed login.

**Do you need to do anything?** No. If you see "Failed authentication" notices, find the device with the old secret or token and fix it. On a `denied` site, until you do, signed-in devices at the same address can still get alarms late.

## Technical detail

### The defect

`lib/authorization/index.js` `resolve()` waits out `shouldDelayRequest(keys)` **before** it checks the credential (the comment at `:152-158` explains why: answering a correct guess at once would turn the delay into a signal). BF-75's fix admits an `/alarm` socket to the `AlarmReceivers` room only once an entitlement has been resolved, in two places: at connect time with no credential, and on every `subscribe`. Both went through `resolve()`. So a socket connecting while its resolved address is in the delay joined the room after the penalty, missed the first emission, and got the alarm at the next re-emission. On a readable site that was every socket from that address, signed in or not, because even the connect-time admission (which carries no credential and can only ever answer `AUTH_DEFAULT_ROLES`) waited.

### The fix

- `authorization.resolveAnonymous(callback)` (new, `8e295769`) returns `{ shiros: rolesToShiros(defaultRoles), defaults: true }`. That is what `resolve()` returns for no credential, but without consulting the delay list. It neither records nor clears a failure.
- **Connect-time admission** (`cd2dfb1f`) uses `resolveAnonymous` instead of `resolve({ api_secret: null, token: null })`. On `readable` the socket is in the room as soon as it connects; on `denied` the default has no `api:*:read`, so it is not admitted (BF-75 unchanged). The answer is synchronous, so it lands before any message from the socket; `hasSubscribed` is kept as the guard that the default never overwrites an explicit `subscribe`.
- **`subscribe`** (`8e295769`) uses `resolveAnonymous` when `presentsCredential(message)` is false: every one of `secret`, `jwtToken`, `token` and `accessToken` is absent, `null`, `''` or (for consistency with `resolve()`) the string `'null'`. `token` and `accessToken` are counted even though the web path does not read them, so a message is never answered as anonymous because its credential was in an unexpected field. Any value in any of those fields still goes through `resolve()` unchanged.
- `resolve()` is not modified, so HTTP and the main namespace are not modified.

**Room membership after a credentialed `subscribe`.** A `subscribe` can only add to what the admission gave on the same site:

- a credential that resolves gets its own permissions plus the defaults (`resolveAccessToken` concatenates `defaultShiros`), so on `readable` it cannot lose `api:*:read`;
- a credential that fails takes the error path, which changes neither room membership nor ack rights. On `readable` the socket stays in the room with the anonymous default it already had; on `denied` it was never in it.

**Why not change `resolve()` itself?** Skipping the delay in `resolve()` when no credential is presented would be a one-line change. It would also stop anonymous HTTP requests and anonymous main-namespace socket requests from waiting. #8754's `tests/authdelay.test.js` asserts the opposite ("makes a request with no credential from a throttled address wait, as dev does"). With that one-line change applied, that test fails. This PR leaves HTTP and the main namespace as they are.

### What a guesser gets

Nothing new. Every guess carries a credential, and every credential still waits for the full delay before it is checked. An admission or an anonymous subscribe gets `AUTH_DEFAULT_ROLES`, which it would get from any address, and neither shortens nor lengthens the delay. The tests show:

- a wrong secret, and a valid web token, are still held for the full delay before their `subscribe` is answered, on both `readable` and `denied`;
- a wrong secret gains no ack right (its `ack` never reaches the notifications layer; a right-secret socket's does);
- connections that never subscribe and anonymous subscribes from a throttled address leave the next wrong secret there held for the full remaining penalty, and no longer;
- the "Failed authentication" admin notification fires once per failure.

### Measured on a booted server

Measured with each tree's real server, the default failed-login delay and default proxy settings, on Node 22.23.2 and MongoDB 7.0.43. In each case the viewer's address had recent failed logins, the viewer then connected to `/alarm` (and subscribed, except in the "never subscribes" row), and an urgent low was raised shortly after. The probe is kept outside the repository.

Each cell gives the subscribe ack time, then when the viewer got `urgent_alarm`, measured from the upload. "not in 20 s" means it had not arrived within the 20 s window; "none in 120 s" means the window was widened to 120 s and it still had not.

| viewer (readable site) | `v15.0.8` `92d08342` | `dev` `e3adc91d` | `8e295769` | this branch `cd2dfb1f` |
|---|---|---|---|---|
| no failures, not signed in (control) | 2 ms / 13 ms | 2 ms / 13 ms | 1 ms / 13 ms | 2 ms / 13 ms |
| not signed in, `{ secret: null }` | 9999 ms / 12 ms | 9999 ms / not in 20 s | 1 ms / 13 ms | **0 ms / 14 ms** |
| wrong secret | 9999 ms / 11 ms | 10000 ms / not in 20 s | 9999 ms / not in 20 s | 9999 ms, `success:false` / **12 ms** |
| valid web JWT (signed in) | 10000 ms / 9 ms | 10002 ms / 37.7 s | 10000 ms / 37.7 s | 10000 ms / **10 ms** |
| connects, never subscribes | — / 12 ms | — / 49.6 s | — / 10.8 s and 49.6 s (two runs) | — / **11 ms** |

| viewer (denied site) | `v15.0.8` | `dev` `e3adc91d` | `8e295769` | this branch `cd2dfb1f` |
|---|---|---|---|---|
| not signed in, `{ secret: null }` | 10001 ms, `read:false` / **12 ms** (BF-75) | 9999 ms, `read:false` / none | 1 ms, `read:false` / none | 1 ms, `read:false` / **none in 120 s** |
| valid web JWT | 10000 ms / 10 ms | 10002 ms / not in 20 s | 10002 ms / 49.5 s | 10000 ms / 65.8 s |
| connects, never subscribes | — / received (BF-75) | not measured | not measured | — / **none in 120 s** |

On a readable site the wrong-secret and signed-in rows now get the alarm at once because the socket is already in the room through the admission; their `subscribe` acks still wait the full delay. On a denied site the signed-in viewer still gets the alarm only at the next repeat, as before; when that repeat comes depends on the alarm schedule, so the seconds in that row vary between runs. The same denied server delivered that viewer's alarm while the anonymous and never-subscribing viewers received nothing in 120 s. The 15.0.8 column shows alarms arriving at once for everyone because 15.0.8 broadcasts to the whole namespace, which is BF-75.

### Tests

`tests/api3.alarm-socket.anonymous-delay.test.js` uses the api3 fixture, which gains an `authFailDelay` option (default 0, as before). The test runs with a short delay; the scenarios are independent and run side by side, so the file takes about 7 s. 18 cases:

- **No credential, readable**: an anonymous `{ secret: null }` viewer on a throttled address gets an alarm emitted shortly after subscribing within 1 s, with `read:true` and a prompt ack; empty-string credential fields count as none.
- **Connect-time admission**: on a throttled readable address, a socket that never subscribes gets the alarm at once; on a throttled denied address it gets nothing.
- **No credential, denied**: answered promptly with `read:false`, and no alarm arrives.
- **The credential check still waits** (ack at least 80 % of the delay): a wrong secret (readable and denied), `{ secret: null, token: … }`, and a valid web JWT (readable and denied).
- **CHANGED by `cd2dfb1f`**, marked in the file: on a readable site the wrong-secret, ignored-field and valid-JWT viewers used to be asserted to miss the first emission; they now get it at once, through the admission, while their subscribe is still held.
- **Denied, valid JWT**: no alarm until its subscribe resolves, then the next emission arrives.
- **No new permission**: a wrong-secret socket's `ack` does not reach the notifications layer; a right-secret socket's does.
- **Controls**: a signed-in viewer on a different address, and with no failures, is prompt.
- **Wear-down guard**: connections that never subscribe and anonymous subscribes neither clear nor extend the delay.
- The "Failed authentication" admin notification is raised once per failure.

**On `8e295769`**, 4 of 18 fail, each with `alarm not delivered within 1000 ms of emission`: the readable never-subscribes socket, and the wrong-secret, ignored-field and valid-JWT viewers.

**Full suite on `cd2dfb1f`:** 3188 passing, 0 failing, 3 pending, twice (`npm test`, Node 22.23.2, MongoDB 7.0.43, freshly dropped database each time). `tests/api3.alarm-socket.security.test.js` and `tests/api3.alarm-socket.ack.test.js` (BF-75, BF-76): 51 passing.

### Break-its

On `cd2dfb1f`, one change at a time:

| change to the fixed code | result |
|---|---|
| connect-time admission back to `resolve()` (the `8e295769` hunk) | 4 fail: the readable never-subscribes socket and the three CHANGED cases, each `alarm not delivered within 1000 ms of emission` |
| connect-time admission joins the room unconditionally (15.0.8-like) | 3 fail, all on the denied site: never-subscribes, wrong secret and valid JWT each receive an alarm they are not entitled to |
| admission clears the address's delay | 6 fail: every "credential check still waits" case, and the wear-down guard |
| a failed subscribe still wires up `ack` | 1 fails: the no-new-permission case |

The `8e295769` break-its (every message credentialed, every message anonymous, only `secret`/`jwtToken` checked, empty strings counted, default roles ignored, anonymous path records a failure, fixture delay forced to 0) were measured on `8e295769` and were not repeated on this commit.

## Client impact

The following was read, not run.

- **Nightscout web page**: signed in or not, on a readable site it is in the room from the moment it connects. Its `subscribe` is unchanged; when signed in, it gains ack rights once its credential is checked after the wait.
- **AndroidAPS** (`NsConnectHandler.kt:81`) sends `subscribe({ accessToken })`, which goes through `resolveAccessToken` and was never delayed. On a readable site it is now also admitted at connect time without waiting. If `accessToken` is empty, the message counts as anonymous and is answered at once with the default permissions.
- **LoopFollow** uses the main namespace (`authorize` with its token as `secret`), not `/alarm`. It is unchanged.
- **nightguard, LoopCaregiver, xDrip, xdripswift, NightscoutKit** do not use the `/alarm` socket.
- **Nocturne**'s socket.io bridge is its own server.

Not changed, for a later decision:

- The main namespace's `dataUpdate` for a viewer on a throttled address still waits (`verifyAuthorization` goes through `resolve()`). That delays the chart, not alarms.
- On a denied site, a signed-in viewer on a throttled address still waits for its credential check before it receives alarms.
- A socket whose earlier `subscribe` succeeded keeps its room membership and ack rights if a later `subscribe` fails; this predates this PR.
