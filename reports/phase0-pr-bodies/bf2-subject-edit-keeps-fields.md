# `bf2/subject-edit-keeps-fields` — editing an access entry keeps its notes and the date it was created

**DRAFT — for maintainer and security review. Not pushed, not opened.** Branch
`bf2/subject-edit-keeps-fields`, one commit `7103f657` on `bf2/auth-hardening` `29e6430e`
(register BF-47, queue BFQ-47). No `CHANGELOG.md` edit.

---

## What changes for you

*Plain-language summary for people running their own Nightscout site. Nightscout is not a medical
device and none of this is medical advice.*

A few words used below:

- **Subject** — a named person or device on your Nightscout admin page (a parent's phone, an
  uploader, a follower). Each one gets its own **access token**, so you can give someone access
  without giving them your site's main password.
- **Role** — a named set of permissions, such as `readable` or `careportal`, that you give to a
  subject.
- **Notes** — the free-text "Additional Notes, Comments" box in the edit dialog.

### What you lose today

On the current release, when you open a subject on the admin page and save it — for example to
give it another role — Nightscout:

- **wipes that subject's notes** (on 15.0.8 and `dev` the page never loads them, so the notes box
  opens empty and saving writes the empty box back), and
- **replaces the date the subject was created with the date you edited it.**

This happens with no warning and no error. Going back to an older version of Nightscout does not
bring either one back. (Measured on `dev`. The code involved is the same on 15.0.8, but that was
checked by reading it, not by running 15.0.8.)

The `bf2/auth-hardening` branch this builds on already fixes the notes: the page now loads them.
The creation date was still overwritten on every edit.

### What changes

Editing a subject on the admin page keeps its notes and the date it was created. So does editing a
role, and so does any other tool that saves a subject or role without sending those two fields.

You can still clear the notes on purpose: empty the notes box and save.

Removing every role from a subject works the same as before — the subject ends up with no roles.
That case was checked on purpose (see "Why not keep every field" below).

### What does not change

- Nothing you need to set or configure.
- The fields Nightscout stores for a subject are still name, roles, notes and the creation date,
  and for a role name, permissions, notes and the creation date. Any other field a tool sends is
  still not stored. That is the list `bf2/auth-hardening` introduced, and the maintainers decided
  on 2026-09-23 that it is the intended list.
- Creation dates already overwritten by earlier edits cannot be recovered by this change.

---

## Technical

### The defect, measured

Reproduced 2026-09-23 on Node 20.20.0 and MongoDB 7, reading the stored documents straight from
MongoDB. Each entry was created through the API with notes and a fixed `created_at` of
`2020-01-02T03:04:05.000Z`. "admin" means edited in a real browser (system Chrome) through the stock
admin dialog: open the entry, change its roles or permissions, press Save.

| path | `origin/dev` `74fc6619` | `bf2/auth-hardening` `29e6430e` | this branch `7103f657` |
|---|---|---|---|
| subject, admin page | notes → `""`; `created_at` → time of edit; access token written to disk | notes kept; `created_at` → time of edit | both kept |
| subject, PUT with both fields (control) | both kept | both kept | both kept |
| subject, PUT without either field | notes removed; `created_at` → time of edit | notes removed; `created_at` → time of edit | both kept |
| subject, PUT with `notes: ""` | notes `""`; `created_at` → time of edit | notes `""`; `created_at` → time of edit | notes `""`; `created_at` kept |
| role, admin page | both kept | both kept | both kept |
| role, PUT without either field | notes removed; `created_at` → time of edit | notes removed; `created_at` → time of edit | both kept |
| role, PUT with `notes: ""` | notes `""`; `created_at` → time of edit | notes `""`; `created_at` → time of edit | notes `""`; `created_at` kept |

Why each happens:

- `GET /api/v2/authorization/subjects` serves `pick(subject, ['_id','name','accessToken','roles'])`
  on `dev`, and adds `notes` on `bf2/auth-hardening`. It never serves `created_at`.
- `lib/admin_plugins/subjects.js` sends that object back as a form-encoded `PUT`, with the dialog's
  name, roles and notes written over it.
- `storage.save()` does `replaceOne({_id}, doc, {upsert: true})` and, when `created_at` is falsy,
  sets it to now. So a missing `created_at` is not left out; it is replaced with the time of the
  edit.
- `GET /roles` serves whole documents, so the role dialog sends `notes` and `created_at` back and
  keeps them. On the admin page, only the subject editor was affected. The register described both.

### The fix

`lib/authorization/storage.js` `save()` (shared by `saveSubject` and `saveRole`) now reads the stored
`notes` and `created_at` before the replace, and uses them when the request leaves them out:

- `notes` is taken from the stored document only when the request has **no** `notes` key. A present
  key, including `""` or `null`, is written as given, so clearing still works.
- `created_at` is taken from the stored document when the request's value is missing or falsy. If
  there is no stored document (an upsert of a new `_id`), it is set to now, as before.
- The replace, the allow-list and the removal of the derived token fields are unchanged.

**Server, not the admin page.** The replace is what drops the fields, so the fix goes there. It then
covers every caller, not only the admin page. Changing the page (serving `created_at` from `GET` so
the dialog sends it back) would have fixed the page alone, and left a `PUT` without the fields
still losing both.

**Why not keep every field.** Only `notes` and `created_at` are filled in, not `roles`,
`permissions` or `name`. The admin page form-encodes its request with jQuery, and jQuery leaves an
empty list out entirely (`$.param({roles: [], notes: ''})` is `notes=`, measured in the browser).
So the request that removes a subject's last role, or a role's last permission, has no `roles` or
`permissions` field at all. Filling those in from the stored document would silently keep access
the operator had just removed. A test covers this.

**Concurrency.** The read and the replace are two operations. Two edits of the same entry at the
same moment could interleave, which is no worse than the last-write-wins the replace already has.

### Tests

Added to `tests/authsubjects.test.js`, backend only (supertest against the real endpoints and
MongoDB):

| test | on `29e6430e` | on this branch |
|---|---|---|
| keeps notes and `created_at` when a subject is edited on the admin page (form-encoded body built from `GET`) | fails: `created_at` is the time of the edit | passes |
| removes every role when the admin page saves a subject with none | fails on the `created_at` assertion; the roles assertion holds on both | passes |
| keeps notes and `created_at` when a PUT leaves them out | fails: notes `undefined` | passes |
| clears notes when a PUT sends them empty, and still keeps `created_at` | fails: `created_at` is the time of the edit | passes |
| role: keeps notes and `created_at` when left out, clears notes sent empty | fails: notes `undefined` | passes |

Each was checked by breaking the fix:

| break | result |
|---|---|
| remove the call that fills in the stored fields | the same 5 fail, with the same messages as on `29e6430e` |
| treat `notes: ""` as "left out" | the 2 clear-notes tests fail (`expected 'to be cleared' to be ''`) |
| also fill in `roles` from the stored document | "removes every role" fails (`expected [ 'admin' ] to equal []`) |

A browser check outside this repository (the alignment repo's
`tools/review/probes/subject-edit-keeps-fields-browser.js`) runs the admin dialog in Chrome and
reads MongoDB. It passes on this branch, fails on `29e6430e`, and produced the table above.

### Full suite, Node 20.20.0

| build | passing | failing | pending |
|---|---|---|---|
| `bf2/auth-hardening` `29e6430e` | 2462 | 0 | 3 |
| this branch `7103f657` | 2467 | 0 | 3 (the 5 added tests account for the difference) |

### Review points

1. A `PUT` that leaves out `notes` now keeps the stored notes, where it used to remove them. That is
   a change to what the endpoint does. It is the intended fix. Check that no caller relied on
   leaving `notes` out to clear it.
2. A `PUT` can still set `created_at` to any non-empty value. That was already true and is not
   changed here.
3. The fill-in is limited to `notes` and `created_at` on purpose (see "Why not keep every field").
   If a later change adds fields to the allow-list, it has to decide for each one whether leaving it
   out means "unchanged" or "remove it".
