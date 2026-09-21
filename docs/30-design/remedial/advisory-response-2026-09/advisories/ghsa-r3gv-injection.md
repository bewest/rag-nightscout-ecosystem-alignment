# GHSA-r3gv-x7fw-j2v5 — NoSQL operator injection in `find[...]`

Register **BF-04**, **BF-70** (both fixed and merged to `dev` as PR #8743), **BF-71**, **BF-72**.

**Of the three proof-of-concepts, one stands, one is fixed, and one is not a privilege boundary.**
This advisory needs the most editing of the five.

## Metadata changes

| field | now | change to | why |
|---|---|---|---|
| package name | **`cgm-remote-monitor`** | **`nightscout`** | `registry.npmjs.org/cgm-remote-monitor` returns `{"error":"Not found"}`. This advisory currently names a coordinate that matches nothing anywhere. The repo's `package.json` says `"name": "nightscout"` |
| `severity` / `cvss` | `high`, `AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:N/A:L` = 8.2 | see below | the vector was scored for the combined claim; two thirds of that claim did not survive measurement |
| `vulnerable_version_range` | `<= 15.0.8` | **keep** | correct: `$where` still executes on 15.0.8, measured |
| `patched_versions` | *(blank)* | **leave blank until a release ships** | the fix is merged to `dev` (PR #8743) and `dev` is unreleased |

## What each PoC actually did, measured

| PoC | claim | measured |
|---|---|---|
| **(B) `$where`** | server-side JavaScript execution | **stands.** Executes anonymously on **v15.0.8**. Refused with HTTP 400 on `dev` since PR #8743 |
| **(A) `find[dateString][$ne]=x`** — the advisory's "primary evidence", a full-history PHI dump | date-window bypass → full history | **not a privilege boundary.** The allowlisted, documented `find[date][$gte]=0` returns the *identical* records under the *identical* authorization, and every form is **401 under `AUTH_DEFAULT_ROLES=denied`**. The full-history read is what the shipped `readable` default *means*, not something this code path grants. The date window is a paging convenience whose own source comment reads `// TODO: discuss/consensus on right value/ENV?` — it was never an access control. Filed as **BF-71**, `low` |
| **(C) `$regex`** | blind exfiltration of free-text PII | **real, but it is an availability defect, not the extraction described.** `$regex` on a field is in API v1's accept set *by design*; it reaches mongod with no anchoring, length or complexity bound. Measured against 20 000 seeded entries on mongod 7.0.43: control **22 ms**, three nested-quantifier patterns **60 s / 65 s / 71 s**, stable across two runs. One unauthenticated request, no token, on the shipped default. Filed as **BF-72** |

## Recommended severity

Score the two surviving items separately rather than carrying one 8.2 for a merged claim:

* **`$where` — server-side JavaScript on the database.** `CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:N/A:L`
  = **8.2**, unchanged, scored on the shipped `readable` default. Fixed on `dev`.
* **`$regex` — unauthenticated database CPU exhaustion.** An availability finding:
  `CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:H` = **7.5**. Not a data-exposure finding; the
  collections the scan reaches are already readable on that default. **Not fixed** — the
  allowlist admits `$regex` deliberately.

Keeping one 8.2 is defensible if the advisory is edited to rest it on `$where` alone. What is
not defensible is leaving the text calling the date-window PoC the primary evidence.

## Text to change

**The "Figure 5 is the primary evidence" framing must go.** Figure 5 shows an anonymous
full-history dump on a stock install — which is what `AUTH_DEFAULT_ROLES=readable` does, and
what the product warns about at every boot. Presenting it as the headline makes the whole
advisory easier to dismiss, which would be a shame, because `$where` and `$regex` are real.

**Remediation item 3** — *"Do not compile raw user input into `RegExp` … an attacker can supply
an arbitrary regular expression"* — should be **kept and promoted**, because it is the item that
survived. Items 1 and 2 are done. Items 4 and 5 are now disputed on measurement: item 4 (apply
the date window even when the field is an operator object) is a consistency fix rather than a
security one, and item 5 (change the default to `denied`) is a product decision with a large
compatibility cost that this advisory does not by itself justify.

**Add** what PR #8743 actually did, so a reader knows the state:

> Server-side JavaScript is now refused with HTTP 400 (`$where`, `$function`, `$accumulator`),
> and API v1 gained an operator allowlist: `$eq $ne $gt $gte $lt $lte $in $nin $exists $regex`
> (`$options`) on a field, `$and`/`$or` at the top level, plus `$type`. `$regex` remains
> deliberately accepted, so the availability finding is open.

## Note

There is **no private fork** for this advisory, and the `$where` fix is already merged to a
public branch, so the disclosure question for this one is largely moot.
