# DRAFT — not sent

*Contributor-facing wrapper; the text below the rule is the outgoing comment.*

| | |
|---|---|
| post to | advisory GHSA-gjhc-pc29-r3m6 on nightscout/cgm-remote-monitor, as a comment to the reporter |
| from | Nightscout Foundation |
| facts as of | 2026-09-22: fix merged to `dev` as #8744 on 2026-09-21; not in any release; 15.0.8 affected; `master` 308 commits behind `dev` |

Paste everything below the rule as-is. Re-measure the commit count on the day it is sent
(`git rev-list --count master..dev` in a current clone) and update the one sentence that quotes it.

---

Thank you for this report — it is a real defect, and a fix has been merged into our development
branch.

We reproduced it on v15.0.7, v15.0.8 and `dev`, against mongod 7.0.43, in both authorization
configurations. Everything below is measured rather than inferred, and two of the items are
corrections to the advisory that we would like your view on before publishing.

**Confirmed.** With `AUTH_DEFAULT_ROLES=denied`, on an instance where `/api/v1/status.json`,
`/entries.json`, `/devicestatus.json` and `/treatments.json` all answer 401 in the same run, an
unauthenticated socket that never sends `authorize` receives the retained device-status window.
In our reproduction that was 576 records carrying the loop suggestion block, pump battery and
reservoir, bolusing and suspended state, `pump.pumpID`, `pump.manufacturer`, `pump.model`,
`uploader.name` and the rig hostname.

**Two things we found that strengthen the report.**

1. It returns *more* than an authorized reader gets. `authorize` trims the initial load to ten
   records per device-and-type, so a legitimate reader's `dataUpdate` carried 20 records where the
   unauthenticated socket got 576.
2. No configuration mitigates it. We tested `AUTH_DEFAULT_ROLES=denied`, `status-only`,
   `AUTHENTICATION_PROMPT_ON_LOAD=true` and `TREATMENTS_AUTH=off`; all still return the data.
   `DEVICESTATUS_DAYS=2`, the only setting that touches this path, doubles it to 1150. There is no
   reverse-proxy workaround either, because the namespace shares the `/socket.io/` endpoint with
   the dashboard's live updates.

**Two corrections we would like to make.**

*The affected range.* The advisory says `>0.8.1`. We grepped each tag: `loadRetro` is absent from
0.8.1, 0.8.2, 0.8.3 and 0.8.4, and first appears in **0.9.0** — which is also the first tag
carrying `DataReceivers` and `authDefaultRoles`, so the handler and the authorization it skips
shipped in the same release. We propose `>= 0.9.0`.

*The configuration sentence.* The report says "This does not require any specific configuration on
the system". That is correct about reachability, and we would like to keep that point, but we
would like to separate it from impact, because the two are very different here:

- On the shipped default `AUTH_DEFAULT_ROLES=readable` — which the README documents as "readable
  by anyone who knows the URL", and which Nightscout itself flags with a persistent admin notice
  every boot — there is **no additional disclosure**. We compared field by field: every record id
  the socket returns is already in the anonymous `GET /api/v1/devicestatus.json` answer, no JSON
  field path exists only on the socket, and the REST route returns more (1730 records against the
  socket's 574). The socket payload is a strict subset of what such a site already publishes.
- On an install that has closed anonymous access, it is a genuine authorization bypass, and that
  is where the severity belongs.

Our reason for drawing that line explicitly is practical rather than defensive: most Nightscout
instances run the `readable` default, and an advisory that reads as "you are exposed" to all of
them produces alarm those operators cannot act on, and costs us credibility for the next report.
We would rather say plainly that the people who need to act are the ones who hardened their
instance — and that the hardening they applied does not help.

We propose scoring it `CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:N/A:N` = **7.5**, stated as scoring
the hardened configuration.

**The fix** was merged into `dev` as nightscout/cgm-remote-monitor#8744 on 2026-09-21. It is
**not yet in a release**, so 15.0.8 is still affected. It gates the handler on the authorization the
file already computes: a socket that authorized keeps its resolved read permission, and one that
never did is resolved through the same `AUTH_DEFAULT_ROLES` defaults the REST surface uses. A
`readable` instance therefore keeps serving anonymous clients exactly as before, and a `denied`
one refuses here as it does everywhere else. It comes with a regression test, and reverting the
change turns that test red with canaried device-status data arriving at a socket the server had
already resolved as unable to read.

**On timing.** We will leave `patched_versions` empty until a release actually carries the fix.
`dev` is unreleased and `master` is 308 commits behind it, so naming a commit or a pull request
would tell operators on 15.0.8 that they have somewhere to upgrade to, and they do not yet.

Please tell us if you disagree with the range correction or with separating reachability from
impact — we would rather settle both with you than publish over you. You will be credited on the
published advisory.
