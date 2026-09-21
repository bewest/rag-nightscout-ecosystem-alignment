# The world-readable warning never fires on the one configuration that is also world-writable

**Base:** `dev` &nbsp;·&nbsp; **Head:** `bf/readable-warning` &nbsp;·&nbsp; **Commit:** `74731433`

## What is wrong

`lib/server/bootevent.js` raises a persistent admin notice when a site is readable by
anonymous visitors:

```js
if (env.settings.authDefaultRoles == 'readable') {
  ctx.adminnotifies.addNotify({ title: "Nightscout readable by world", ... });
}
```

`AUTH_DEFAULT_ROLES` is a **list** of roles, not one role. The deprecated `TREATMENTS_AUTH=off`
is implemented in `lib/server/env.js` by appending to that very string:

```js
if (!readENVTruthy('TREATMENTS_AUTH', true)) {
  env.settings.authDefaultRoles = env.settings.authDefaultRoles || "";
  env.settings.authDefaultRoles += ' careportal';
}
```

So the shipped default resolves to `"readable careportal"`, the whole-string compare fails,
and the notice is never raised.

## Why it matters

`readable careportal` is not a narrower configuration than `readable` — it is a wider one.
The site is world-readable *and* it accepts `POST /api/v1/treatments` from anyone who knows
the URL, with no credential. That is measured below: the record is written to the database.

The warning fails open in exactly the case it exists for. An operator who turned on a
documented convenience setting gets *less* warning than one who changed nothing, and the
silence reads as reassurance.

Both defect fragments — the compare at `bootevent.js:149` and the append in `env.js` — are
unchanged between `v15.0.8` and `dev`, so this reaches everyone on the shipping release.
(The two files are not byte-identical across those refs, but neither of these two fragments
has been touched.)

This is a missing warning, not a privilege escalation. Nothing here grants access that
`TREATMENTS_AUTH=off` did not already grant deliberately.

## Measured

Three arms plus a fourth, one run each, `GET /api/v2/adminnotifies` with an admin credential,
synthetic data only.

### Before — on `dev` @ `59430336`, unmodified

| configuration | resolved `authDefaultRoles` | anon `GET /entries` | anon `POST /treatments` | notice |
|---|---|---|---|---|
| default | `readable` | 200 | 401 | `notifyCount` **1**, "Nightscout readable by world" — positive control |
| `TREATMENTS_AUTH=off` | `readable careportal` | 200 | **200, record stored** | `notifyCount` **0** ← the defect |
| `AUTH_DEFAULT_ROLES=denied` | `denied` | 401 | 401 | `notifyCount` 0, correctly — negative control |
| `denied` + `TREATMENTS_AUTH=off` | `denied careportal` | 401 | 401 | `notifyCount` 0, correctly |

Row 3 is what makes row 2 attributable to the string compare rather than to the notice
machinery being broken generally. The stored record from row 2 was read back out of the
database to confirm the write was real, not just a 200.

### After — same four arms, this branch

| configuration | resolved roles | anon `GET` | anon `POST` | notice |
|---|---|---|---|---|
| default | `readable` | 200 | 401 | `notifyCount` 1, **text unchanged** |
| `TREATMENTS_AUTH=off` | `readable careportal` | 200 | 200 | `notifyCount` **1**, wider text ← fixed |
| `AUTH_DEFAULT_ROLES=denied` | `denied` | 401 | 401 | `notifyCount` 0 ← **still silent** |
| `denied` + `TREATMENTS_AUTH=off` | `denied careportal` | 401 | 401 | `notifyCount` 0 ← **still silent** |

The last two rows matter as much as the second. A fix that made a hardened instance warn
about being world-readable would be worse than the defect, because it trains operators to
ignore the notice.

Access control itself is untouched: the anonymous `POST` still returns 200 on
`TREATMENTS_AUTH=off` after the change. This PR changes what is *said*, not what is *allowed*.

## What changed

**`lib/authorization/defaultroles.js` (new, 26 lines).** One place that reads the setting as
a list. `parse()` is character-for-character the split `lib/authorization/index.js` was
already doing; `has()` answers role membership.

**`lib/authorization/index.js`.** One line, now calling `parse()`. Deliberately *not* a
behaviour change: the split is identical, including the empty-string element a leading
separator produces, so `rolesToShiros` and `permissionGroups` see exactly what they saw
before. The point is that there is one reading of the setting instead of two that can drift.

**`lib/server/bootevent.js`.** The decision moves into `worldReadableNotify(settings)`, a pure
function at module scope that returns the notice or `null`, and `checkSettings` calls it. It
is exported for the test. The condition is now role membership. The empty element never
equals a role name, so `indexOf` needs no special case.

### User-facing text — please review this part specifically

The **plain `readable`** notice is **unchanged**, byte for byte, title and message.

A **second wording** is used when `careportal` is also in the list:

> **Nightscout readable by world and open to treatment entry**
>
> Your Nightscout installation is readable by anyone who knows the web page URL, and it also
> accepts new treatment entries - carbs, insulin, notes and similar - from anyone who knows
> the URL, without a password. This happens when the careportal role is part of
> AUTH_DEFAULT_ROLES, either because you set it there or because the deprecated
> TREATMENTS_AUTH=off setting adds it. If this is not what you intended, please consider
> closing access by following the Nightscout documentation:
> https://nightscout.github.io/nightscout/security/#how-to-turn-off-unauthorized-access

Reasoning, in case you want to word it differently:

- **Why different text at all.** "readable by anyone who knows the web page URL" is true but
  incomplete for this configuration, and the missing half is the more consequential one.
- **Why one notice and not two.** `lib/adminnotifies.js` aggregates by message, so two notices
  would both persist and both stay in the drawer, describing one configuration decision with
  one remediation link.
- **Scope of the claim.** The `careportal` role is exactly `api:treatments:create`. The text
  says "treatment entries", not "writable" — it cannot delete, and it cannot write entries or
  devicestatus.
- **Tone.** `TREATMENTS_AUTH=off` is documented in the README and an operator may have chosen
  it on purpose, so the text names both ways the role can arrive, says "If this is not what
  you intended", and keeps the existing "please consider" phrasing rather than an imperative.
- **Not warned about:** `careportal` **without** `readable`. Measured above: that combination
  returns 401 to the anonymous `POST`, so warning about it would be false. See the related
  item below for why.

## Tests

`tests/bootevent-readable-warning.test.js`, 20 cases, three groups:

1. **The decision**, over `worldReadableNotify` directly: `readable` warns with the original
   text; `readable careportal` warns with the wider text; `denied`, `denied careportal`,
   `careportal` alone, `status-only`, empty, `undefined`, absent settings, and the
   leading-separator `' careportal'` all stay quiet; comma and colon separated lists are read;
   `notreadable` does not match `readable`; a repeated append is tolerated.
2. **Against the string `lib/server/env.js` really produces**, driving `config()` with the
   environment variables set, so the test fails if either half of the pair changes: the append
   in `env.js` or the read in `bootevent.js`.
3. **Through the real `lib/adminnotifies`**, checking the notice object is accepted, counted
   once, and survives the twelve-hour cleanup because it is persistent.

**Ablation.** Restoring the original `== 'readable'` condition inside the same seam (so the
failure cannot be a missing export) turns the suite red **with the original symptom**, not
with noise:

```
1) warns on readable careportal, which is strictly wider:
     AssertionError: expected null to exist
5) warns when TREATMENTS_AUTH=off widens the default:
     AssertionError: expected null to exist
6) reaches the admin notify list for readable careportal:
     AssertionError: expected 0 to be 1
```

7 failing, **13 still passing** — every `denied` / stay-quiet case survives the ablation, which
is what makes the red attributable to this condition and not to the test being broadly brittle.

**Full suite**, `NODE_ENV=test npm test`, same machine, same mongo:

| | passing | pending | failing |
|---|---|---|---|
| `dev` @ `59430336` before | 2311 | 3 | 0 |
| this branch | **2331** | 3 | 0 |

+20, exactly the new cases.

`npx eslint` clean on all three changed library files.

## Related, and deliberately not in this PR

While measuring the above: the `careportal` role is **inert unless reads are already open**.
`lib/api/treatments/index.js:26` applies `ctx.authorization.isPermitted('api:treatments:read')`
to the whole router, before the per-route `api:treatments:create` check, so a site configured
`AUTH_DEFAULT_ROLES="denied careportal"` — an operator asking for anonymous treatment entry
*without* opening reads — gets 401 on the `POST`. Measured, row 4 of both tables above.

That is a separate question with at least three defensible answers (move the read gate to the
read routes; leave it and document that `careportal` implies `readable`; or treat the
combination as a configuration error at boot), and it is a maintainer's call rather than an
obvious patch. It is why this PR does not warn on `denied careportal`: today, truthfully,
there is nothing to warn about. If that behaviour changes, `worldReadableNotify` is the one
place that would need to change with it.

Happy to split the wording into its own commit, or drop the second notice entirely and keep
only the role-membership fix, if you would rather land the smaller change first.
