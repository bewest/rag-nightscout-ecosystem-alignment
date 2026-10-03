# Clock menu keeps the page token; the clock says when it is refused

Fixes #7377

## What changes for you

**Who is affected:** sites that require a login to view (`AUTH_DEFAULT_ROLES=denied`), and people who view such a site through a **token link**, an address ending in `?token=…` that the site owner made for a family member, school or caregiver.

**Before:** after you opened Nightscout through a token link, choosing a view from the **Clock** menu (Clock, Color, Simple, or `[+]` to design your own) opened a **blank black page**. Nothing said why. Opening the clock address directly with the token already on it worked.

**Now:**

- The Clock menu entries keep your token, so each clock shows the current reading straight away.
- The clock designer (`[+]`) shows its preview, and its **"Open my clock view!"** link keeps the token too.
- If a clock is opened **without** a token on a site that needs one, it shows a short message instead of a blank page: *Not authorized: open this clock with a token (…?token=…)*.

Nothing changes for sites that allow anonymous viewing, or for anyone signed in on that browser with the API secret.

**Handle token links like passwords.** The token now appears in the clock page's address, as it already does in the main page's address. Anyone who has the full address can view the site with that token's permissions. Don't post clock addresses with tokens publicly, and remember that a browser keeps them in its history.

## Technical detail

On a denied site, the main page reads `?token=` from its own address (`lib/client/index.js`, `browserUtils.queryParms().token`) and authorizes with it. It keeps the token in the address and in memory only. The Clock menu links (`views/index.html`) were plain paths. `views/clockviews/clock.html` looks for a token only in its own `location.search`, or for the API secret hash in `localStorage`. So a clock opened from the menu sent no credentials. `/api/v1/status.js` answered 401. The script's `onload` never fired, so `client.init()` never ran, and nothing was drawn.

Changes:

1. **`lib/client/browser-settings.js`**: `loadForm()` already appends the page's token to the Reports, Profile Editor, Food Editor and Admin Tools links. When `queryParms().token` is set, it now also sets `?token=<encodeURIComponent(token)>` on `#bgclocklink`, `#clockcolorlink`, `#clocklink` and `#clockconfiglink`. The value is percent-decoded first, falling back to the raw value if it is malformed, so it is encoded exactly once. Nothing is added when the address has no token. Nothing is written to `localStorage` or cookies. The API-secret path is unchanged. Only the main page calls `loadAndWireForm()`, so the clock pages are not affected.
2. **`views/clockviews/clock-config.html`**: the configurator's "Open my clock view!" link (`/clock/<face>`) keeps the token the configurator was opened with (clock.html's `token`), both at load and whenever the face changes.
3. **`views/clockviews/clock.html`**: adds `script.onerror` for the status script. A refused script fires `error` and does not expose the HTTP status. So the handler makes one more request to the same URL with `$.ajax` (`dataType: 'text'`) and shows the message only when that request gets a **401**. Other failures still show nothing new. This costs one extra request, and only when the status script fails to load.
4. **`lib/client/clock-client.js`**: new `client.showNotAuthorized()` puts the message in `#authMessage` after `#inner` and hides `#inner`. The `/api/v2/properties` error handler calls it on a 401. A later successful fetch removes the message. The message is plain English: the clock bundle does not load the translation module, so it is not translatable in this change.
5. **`views/clockviews/clock-shared.css`**: styles for `#authMessage`.

Other links from the main page that need auth (checked; not changed):

| link | carries the token? | token viewer with the `readable` role |
|---|---|---|
| Reports (`report`) | yes, already | loads, "Authorized by token", no 401s |
| Profile Editor (`profile`) | yes, already | loads the profile. Its own `<script src="/api/v1/status.js">` has no token and gets a 401, but the page works, because the client fetches `status.json` with the token |
| Food Editor (`food`) | yes, already | loads, no 401s |
| Admin Tools (`admin`) | yes, already | loads; `/api/v2/authorization/subjects` and `/roles` answer 401, as expected for a role without admin rights |

### Tests

`tests/clock-token-link.test.js` (8 tests, in the tree's jsdom fixtures):

- The menu, taken from `views/index.html`, gets the token on all four clock links when the page has one. It is URL-encoded once: `a:b/c?d` becomes `a%3Ab%2Fc%3Fd`, and an already-encoded value is not encoded twice. Without a token, the links stay plain paths.
- `clock-client`: a 401 from `/api/v2/properties` shows the message, and a 500 does not.
- `clock.html`, rendered with EJS and run in jsdom: when the status script is refused, one request is made to read the status. A 401 shows the message, and a 503 does not.

Break-it: reverting the `browser-settings.js` change fails the 3 token-link tests. Reverting the `clock-client.js` change fails the properties 401 test. Reverting the `clock.html` change fails both status-script tests.

Full suite on the merged head (with `dev` `68262e86`): **3560 passing, 0 failing, 4 pending** (Node 22.23.2, MongoDB 7.0.43). That is `dev`'s 3552/0/4 plus the 8 new tests.

### Browser check

Playwright Chromium against booted servers with `AUTH_DEFAULT_ROLES=denied`, a fresh MongoDB 7.0.43 database, a subject with the `readable` role, and one reading of 123 mg/dL. The viewer opened `/?token=…` and clicked each Clock menu entry:

| | `dev` | this branch |
|---|---|---|
| Clock / Color / Simple | blank (status.js 401) | 123 drawn (Color has a green background) |
| `[+]` configurator | blank, and the preview gets 401 | the preview draws 123 after "Add SGV", and its link `/clock/cy10-sg40?token=…` draws 123 |
| `/clock/clock-color` and `/clock/bgclock` opened with no token | blank | the "Not authorized" message |

A side note, not changed here: the configurator's link has `target=”_blank”` with curly quotes, so it is not a real `_blank` target.
