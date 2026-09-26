# Journey lab: the real-app track

*Contributor-facing. For testers who can run Loop, Trio or AndroidAPS against a lab site with a
simulated pump and CGM. Synthetic data only: never connect a phone that doses a real person to a
lab site. Never connect a lab app to your real Nightscout. Not medical advice.*

The main lab ([README.md](README.md)) plays the phone with scripted requests copied from each
app's source code. Some checks can only be proven by the real app, because they depend on the app's
own logic, and the lab's emulations of that logic are only as good as our reading of it:

| journey step | why only a real app proves it |
|---|---|
| J1.A2, J1.B3: settings import at onboarding | Loop's and Trio's import code decides; the lab's `connect` step only *predicts* it (`clients.js` `canImport`) |
| J1.B3: AAPS replacing its local profile from the site | AAPS's `NsIncomingDataProcessor` decides; the lab's `accept-check` only predicts it |
| J3.3: a careportal temp target or profile switch reaching AAPS; a temp target reaching Trio | the same: the app's download and accept rules |
| J3.3, J5.4: a Loop remote command arriving on the phone | needs real Apple push (APNs) credentials and a phone; the lab's fake APNs server only shows what would have been sent |
| J2: the app's own IOB/COB versus the site's pills | the lab's numbers are synthetic |
| J1.C: what an app already in use sends when Nightscout is added (Loop's anchors, Trio's 24 h, AAPS's full history) | the lab replays what the code reads as doing; the timing race in Loop is inferred |
| J1.D: what a reinstall imports, and what it silently changes | `restore` emulates each app's import code |

## 1. A lab site the phone can reach

The lab binds every site to 127.0.0.1. For a phone you need the site on your local network over
HTTPS. The apps expect HTTPS, and certificates on phones are strict.

1. Start one site, e.g. `tools/review/journey-lab/lab.sh up loop` (or `trio`, `aaps`, `cp-*`).
2. Put a reverse proxy with a certificate the phone trusts in front of it. For example, Caddy with
   its internal CA:
   ```
   lab.local:8443 {
     tls internal
     reverse_proxy 127.0.0.1:15301
   }
   ```
   Then install Caddy's root certificate on the phone (iOS: install the profile, then Settings →
   General → About → Certificate Trust Settings; Android: Settings → Security → Install certificate).
3. Behind a proxy, Nightscout needs `TRUST_PROXY` set correctly (see the 15.0.9 release notes, "TRUST_PROXY").
   Add it to the site's flags in `lab.sh` for this track.
4. A public tunnel (ngrok, Cloudflare Tunnel) also works. It puts the lab site **on the internet**,
   so use a fresh lab state directory (a new API secret) and take the tunnel down afterwards.

The API secret is in `$LAB_STATE/secret`. Type it into the app; don't paste it anywhere else.

## 2. Apps with simulated devices

| app | simulated CGM | simulated pump | notes |
|---|---|---|---|
| Loop (built from LoopWorkspace) | "Simulator" CGM | "Simulator" pump | onboarding offers to import from Nightscout. Remote commands need your own Apple developer APNs key on the site (`LOOP_APNS_*`), and internet access from the server |
| Trio | Glucose Simulator | Pump Simulator | Settings → Services → Nightscout. "Allow downloads" is off by default: turn it on for J3.3 |
| AndroidAPS 3.4.x | a BG source that works without a sensor (check the AAPS docs for your build) | Virtual Pump | NSClient v3 needs an **admin** token from the site's admin page. For v1, use the secret. Note the "accept profile / temp target / profile switch from NS" settings before starting |
| AndroidAPS 4.0 (dev) | as above | Virtual Pump | accept-profile is off by default. NSClient v1 is gone |

Please check the simulator names against the app version you build; they change between releases.

## 3. What to record

For each check, write down the app and its version (and git sha if built), the lab site and the
candidate sha (`git -C $LAB_RC rev-parse --short HEAD`), what you did, what the app showed, and
what the site showed (`lab.sh status <site>`). Screenshots of the app help. Don't include the API
secret, tokens, or anything from a real person's data.

Checks to run, in order:

1. **J1.A (app first):** empty site → connect → the app sends its settings → `lab.sh status`
   shows the app's profile as newest.
2. **J1.B (site first):** on a `cp-*` site, type a profile into the Profile Editor and save it,
   then connect the app:
   - Loop: does onboarding offer an import?
   - Trio: does the import fail with "Cannot find the Nightscout Profile named "default""?
   - AAPS 3.4: did the phone's profile change?

   Compare each with what the lab's `connect` step predicted.
3. **J3.3:** from the site's careportal:
   - Loop: Temporary Override. Did the phone get it, and did Loop upload its own record?
   - Trio: Temporary Target, with Allow downloads on.
   - AAPS: Temporary Target and Profile Switch, with and without the accept settings.
4. **J1.C (add Nightscout later):**
   - Loop: on a phone that has been looping, add the Nightscout service. Does any history reach the
     site? Is there a profile before you change a setting? The lab predicts no and no.
   - Trio: turn upload on. Is only the last 24 h filled in?
   - AAPS: turn NSClient on. How long does the upload take, and how many records arrive?
5. **J1.A timing (Trio):** finish onboarding. Is there a profile on the site before Trio is closed
   and reopened? The lab predicts not.
6. **J1.D (restore):** reinstall the app against the site. For each app, compare what the
   settings screens show with the lab's `restore` output:
   - Loop: are the insulin model and closed loop left out?
   - Trio: are the top of each target range and the DIA lost?
   - AAPS 3.4: is the profile taken automatically? AAPS 4.0: is it not?
7. **J1.E (CGM first):** point the connector at a real Dexcom Share or LibreLinkUp follower
   account that you own, with **synthetic or your own consented data only**. Then set the app's CGM
   to Nightscout, and check for duplicate readings and a clean gap fill after a signal loss.
8. **J3.6 (Loop):** Profile Editor → Add new → Save → try a remote override. Expect "Could not find
   loopSettings in profile". Then change any setting in Loop and try again: it should work.

Send results to the maintainers as described in [README.md](README.md#reporting). Anything that
differs from the lab's prediction is especially valuable: it means `clients.js` is wrong.
