# GHSA-5mrq-gpqw-q5v5 — stored XSS through WebSocket treatment writes

**Already fixed in 15.0.8** and the advisory already says so. The change needed is the severity.

## Metadata changes

| field | now | change to | why |
|---|---|---|---|
| `severity` | **`critical`** | **`high`** | see the arithmetic below |
| `cvss_vector_string` | *(none)* | **`CVSS:4.0/AV:N/AC:L/AT:N/PR:L/UI:A/VC:H/VI:H/VA:N/SC:N/SI:N/SA:N`** = 8.4 | matches GHSA-mjp4, which describes the identical credential theft |
| (optional 3.1) | — | `CVSS:3.1/AV:N/AC:L/PR:L/UI:R/S:C/C:H/I:H/A:N` = 8.7 | |
| `vulnerable_version_range` | `<= 15.0.7` | keep — confirmed | |
| `patched_versions` | `15.0.8` | keep — confirmed | |

## Why `critical` overstates it, and why the obvious answer is wrong

The intuitive correction is the user-interaction metric — the PoC needs a viewer to hover a
tooltip, so `UI:P` looks too generous. **That is not where the overstatement is.** Correcting
`UI:P` → `UI:A` moves 9.3 → **9.2. Still Critical.**

What produces Critical is **`SC:H/SI:H`** — subsequent-system confidentiality and integrity —
and that is a double count. The stolen API secret's entire blast radius **is** the Nightscout
instance, which is the vulnerable system and is already fully counted by `VC:H/VI:H`. There is no
third system. Dropping `SC`/`SI` to `N` gives **8.4, High**, which agrees with the 3.1 score and
with the sibling advisory's own proposed shape.

The computed ladder, for the record: 9.3 as filed / 9.2 with `UI` corrected / 8.5 with `SC`,`SI`
at `N` but `UI:P` / **8.4 recommended** / 6.2 if the escalation were counted *only* as subsequent.

## The escalation must NOT be softened — `VC:H/VI:H` is where it belongs

`lib/client/hashauth.js` stores `sha1(API_SECRET)` in `localStorage` as `apisecrethash`, and that
sha1 **is** the value the `api-secret` header accepts. Same-origin script therefore obtains admin:
all medical data, plus treatment writes, on a screen caregivers watch to decide about insulin.
That is a genuine full compromise of the instance and it is correctly carried by `VC:H/VI:H`.
Reducing to `high` is about not counting it twice, not about doubting it.

## Two additions to the body

> **No remediation of stored data is required after upgrading from 15.0.7.** A payload written by
> an unpatched server does not execute on a patched one — verified by inserting one directly into
> the database and rendering the dashboard tooltip against each release's own `renderer.js`.

> The proof-of-concept uses `onload` on a `data:` GIF. 15.0.8 closes this twice over: `onload` is
> stripped like `onerror`, and `data:` is rejected as a scheme on `img src`.

## Consistency with GHSA-mjp4

Right now one advisory is `critical` with `SC:H/SI:H` and the other is `high` with `SC:N/SI:N`,
**for the identical credential theft by the identical mechanism**. Whatever is decided, the two
should carry the same severity and the same vector shape. That inconsistency is more damaging to
the advisories' credibility than either number on its own.
