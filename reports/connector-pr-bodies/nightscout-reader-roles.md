<!-- DRAFT: not yet opened as a pull request. Branch fix/nightscout-reader-roles, commit dea2bec, based on dev 1946beb. -->

# DRAFT: Give the Nightscout source's reader subject the role Nightscout reads

## Who this affects

This fix is for people who use nightscout-connect to **copy data from one Nightscout site into another**. In the settings, that setup has `CONNECT_SOURCE=nightscout`, a `CONNECT_SOURCE_ENDPOINT` and a `CONNECT_SOURCE_API_SECRET`.

It matters only when the site being copied **from** does not let anonymous visitors read it. That is set by `AUTH_DEFAULT_ROLES=denied` on that site.

- **If the source site is readable without logging in** (`AUTH_DEFAULT_ROLES=readable`, the older default), nothing changes. The connector reads that site anonymously and never uses the code this fix changes.
- **If the source site is locked down** (`AUTH_DEFAULT_ROLES=denied`), copying has never worked. The connector makes an access token for itself on the source site, but that token was created without permission to read. Every attempt to fetch data fails with "Polling frame failed (HTTP 401)", and **no glucose readings, treatments, device status or profiles reach the destination site.**

The connector keeps retrying and never pauses, but nothing gets copied. If you rely on the destination site for glucose data or alarms, it has had no data from this source.

### If you already tried this setup

Upgrading the connector does not repair a token it already created. The connector finds its existing token by name (`nightscout-connect-reader`) and keeps using it. To fix it, do one of these on the **source** Nightscout site:

1. Open the admin tools (Admin Tools → Subjects), edit `nightscout-connect-reader`, and add the role `readable`; or
2. Delete `nightscout-connect-reader`, and the upgraded connector will create it again with the right role.

Adding the `readable` role to the existing subject was tested and fixes reading, with or without this upgrade. Another way to avoid the problem is to create a token with the `readable` role yourself and put it in the source URL as `?token=...`. The connector then uses that token and never creates one of its own.

This is a software fix, not medical advice. If a gap in copied data affected treatment decisions or alarms, talk to your care team.

## What changed

`lib/sources/nightscout.js` creates its reader subject through `POST /api/v2/authorization/subjects` with `role: [ 'readable' ]`. Nightscout reads a subject's roles only from `roles` (plural):

- `lib/authorization/storage.js` `resolveAccessToken`: `storage.rolesToShiros(subject.roles)`
- `lib/authorization/index.js` `authorize`: `subject.roles ? [...subject.roles, ...defaultRoles] : defaultRoles`
- `GET /subjects` returns `pick(subject, ['_id', 'name', 'accessToken', 'roles'])`
- the admin Subjects plugin reads and writes `subject.roles`

On current Nightscout dev the misspelled `role` field is saved to the database but ignored, so the subject has no roles and its token gets only `AUTH_DEFAULT_ROLES`. The auth-hardening subject allow-list (`name, roles, notes, created_at`) drops `role` when the subject is created, so the subject ends up without roles there too. The fix is the same in both cases.

The change is one field name, `role` → `roles`, and a test.

## How this path is reached

`authFromCredentials` first calls `GET /api/v1/verifyauth` anonymously. If `canRead` is true, the source reads anonymously and never creates a subject. That is why the typo cannot be seen on a `readable` site. If `canRead` is false, or the check fails and an API secret is set, `getOrCreateReaderToken` reuses a subject named `nightscout-connect-reader` if one exists, or creates one if not.

## Evidence (run, not read)

Source Nightscout: cgm-remote-monitor dev 74fc6619 on MongoDB 7, with a seeded SGV entry. Destination: a second Nightscout of the same build. Both ran the connector's `forever` sidecar and a direct drive of the source's `authFromCredentials` → `sessionFromAuth` → `dataFromSesssion` with real axios. Node 22.23.2.

| Source `AUTH_DEFAULT_ROLES` | Connector | Subject stored | JWT `permissionGroups` | Reads | Destination |
|---|---|---|---|---|---|
| `denied` | dev 1946beb | `role: ['readable']`, no `roles` | `[[]]` | 401 on `/api/v1/entries.json` | no entries; "Polling frame failed (HTTP 401)" on every poll |
| `denied` | this branch | `roles: ['readable']` | `[["*:*:read"],[]]` | OK | seeded entry arrives |
| `denied`, subject left by dev | this branch | unchanged (no `roles`) | `[[]]` | 401 | none; upgrading alone does not fix it |
| `denied`, subject edited to add `roles` | either | `roles: ['readable']` | `[["*:*:read"],[]]` | OK | — |
| `readable` | dev 1946beb | none created | n/a (anonymous) | OK | seeded entry arrives |
| `readable` | this branch | none created | n/a (anonymous) | OK | seeded entry arrives |

## Test

`test/nightscout-source.test.js` gets a new test, "Nightscout source creates its reader subject with a readable role". It drives the create path (verifyauth `canRead: false`, empty subject list, POST, then re-list) and checks that the posted subject has `roles: ['readable']` and no `role` key.

- On dev 1946beb it fails with `actual undefined`, `expected ['readable']`.
- Two deliberate breaks of the fix also fail it: `roles: ['readonly']` fails the role value check, and sending both `role` and `roles` fails the no-`role` check.

Suite (`npm test`):

| Node | dev 1946beb | this branch |
|---|---|---|
| 20.20.0 | 289/289 | 290/290 |
| 22.23.2 | 289/289 | 290/290 |
| 24.20.0 | 289/289 | 290/290 |

## Not in this change

- The source does not repair an existing `nightscout-connect-reader` subject that has no `roles`. The steps above cover it. Having the source repair it automatically would mean writing to a subject on someone else's site with the admin secret, which is a larger decision.
- Other `role` fields in the tree (`lib/sources/minimedcarelink/index.js`, `test/minimed-logging.test.js`) belong to CareLink's own API and are correct as written.
