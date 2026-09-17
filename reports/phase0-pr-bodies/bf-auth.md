# `bf/auth` — editing a subject wrote its access token into the database in readable form

Two commits on `origin/dev` `a8888f0d`, tip `ce82f0cd`. 3 files, +310/−18, of which one is a new
test file. No `CHANGELOG.md` edit. Merges clean against `dev` and against every other open Phase 0
branch.

> **Needs an explicit yes, not just a review.** Two reasons, and neither is a code-quality
> question: the subject allow-list **removes a field-passthrough capability with no replacement**,
> which is the major-forcing change here; and the credential-exposure fix **cannot undo what
> already happened**, so some sites will need to rotate a token by hand afterwards. That is an
> operator action the code cannot take for them.
>
> **Read the "If you have ever edited a subject" section before merging.**
>
> **The failed-login throttle that used to travel with this branch is now `bf/throttle`**, split
> out so it can merge with the modernization work. Nothing here depends on it.

## What changes for you

**One security problem is fixed, and a second smaller one goes with it. Nothing about how you log
in, and nothing you see on screen, changes. No stored readings or treatments are touched.**

### Editing an access-token holder wrote their token into the database in readable form

Nightscout lets you create *subjects* — named people or devices (a parent's phone, an uploader,
a follower) that each get their own access token, so you can give someone access without giving
them your site's main password.

Your subjects' tokens are **not supposed to be stored**. Nightscout recalculates each one from
scratch every time it loads, so the database only ever needs to hold the subject's name and
roles. That was true when a subject was first created — but **when a subject was edited**
(renaming it, changing its roles, adding a note), the edit saved the whole in-memory record back,
and the recalculated token went with it. From then on the token sat in the database in plain,
readable text.

Why that matters: anyone who can read your database can use that token to reach your data. A
database backup, a screenshot of a database browser, a hosting provider's snapshot, or a support
person you shared a copy with would all contain a working credential.

**After this change**, a subject's token is never written, on create or on edit, and a copy that a
previous edit left behind is dropped from the in-memory record on every load, so it can never be
served or matched against. **The stored row itself is not rewritten by the upgrade.** It is cleaned
up for a given subject the next time that subject is saved through the admin screen, because `save`
now writes only owned fields — so an operator who wants the copies gone can open and re-save each
previously-edited subject. That clears the copy; it does not retire the credential.

---

## If you have ever edited a subject: rotating the exposed tokens

**This is the part the code cannot do for you, and it is the reason this PR needs a moment's
thought rather than a quick merge.**

A Nightscout access token is **deterministic**. It is rebuilt every time from exactly three
things:

1. the subject's internal record id,
2. the subject's name, and
3. your site's secret key.

It is not random and it is not stored as the source of truth. So **fixing the code does not change
anybody's token.** A token that was written into your database by an old edit is still the same
token the fixed code will hand out tomorrow. If that value leaked, upgrading does not retire it.

The fix stops new copies being made, and clears an existing one the next time you save that
subject. **Neither of those retires the credential. Retiring an exposed token is a separate action,
and only you can decide to take it.**

### Your options, from least to most disruptive

| Option | What it retires | What breaks | Good for |
|---|---|---|---|
| **Do nothing** | nothing | nothing | Sites where only you have ever had database access and you are confident no backup or snapshot was shared |
| **Delete and re-create the subject** | that one subject's token | that one person or device must be given a new token | The normal choice — retires exactly the leaked credential |
| **Rotate your site's secret key** (`API_SECRET`) | **every** subject token at once | everyone re-enters their token; anything using the API secret must be updated | A database copy left your control, or you cannot tell which subjects were edited |

**A note on a tempting shortcut that does not work:** *renaming* a subject changes only the short
word at the front of its token. The long part after the dash is derived from the record id and your
secret key, and renaming changes neither. **Renaming is not a rotation.** Delete and re-create
instead — that creates a new record id, which does change the token.

### How to check whether this affects you

Look in your `auth_subjects` collection for any document with an `accessToken`, `accessTokenDigest`
or `digest` field stored on it. If none of your subjects has one, no edit ever saved a token and
there is nothing to rotate. If some do, those are the subjects to re-create.

**Do not paste a token, a digest, or your API secret into an issue, a forum post, a screenshot or a
chat message when asking for help** — those values are the credential itself.

If a token that could reach your data has been exposed and you are unsure what to do, treat it the
way you would a shared password: retire it. Nightscout is not a medical device and this note is not
medical advice; questions about your own data and who can see it are worth raising with your care
team if they are involved in your setup.

---

## Technical detail

Three commits, all on `lib/authorization/`:


**`64db1f35` — derived credentials persisted on update.** `lib/authorization/storage.js` now
carries explicit allow-lists — `SUBJECT_FIELDS = ['name','roles','notes','created_at']` and
`ROLE_FIELDS = ['name','permissions','notes','created_at']` — used by both `create` and `save`, so
a save writes only owned fields. `DERIVED_SUBJECT_FIELDS = ['accessToken','accessTokenDigest',
'digest']` are deleted from each document in `reload()` *before* being re-derived, so a row written
by an older version cannot supply one. `lib/authorization/endpoints.js` adds `notes` to the
`GET /api/v1/subjects` projection.

**`56ed29d2` — a per-request debug print of request-derived values, removed.** Added 2026-09-16.
`lib/authorization/storage.js` printed `console.log('Loading', opts)` on every read of the auth
collections, putting the query options of each subject-list call on stdout. **This line is not
introduced by this branch** — it is on `origin/dev` at `storage.js:84` — and it was taken here
rather than left as a follow-up for two reasons: it sits in a file this branch already rewrites,
and it is the same defect class as the count-path filter leak fixed on `bf/reads`, where a debug
print put request-derived values into the log. One line, removed.

### Two consequences worth stating plainly

- **Third-party admin tools lose unknown fields.** Because `save` now writes an allow-list, any
  field some other tool stored on a subject or role document is dropped on the next edit, silently
  and with no error. No in-tree code stores such a field. *Not reproduced against a real
  third-party tool — read from `ownedFields()` in the diff.* If you use an external Nightscout
  admin tool, test an edit before relying on it.
- **Existing tokens keep working.** `reload()` recomputes `digest`, `accessToken` and
  `accessTokenDigest` from `subject._id`, `subject.name` and the enclave key on every load. Nobody
  is logged out by this upgrade. That is the same property that makes rotation a manual act.

## Evidence

Detailed defect analysis is kept outside this repository and can be shared on request. The one
correction worth recording here: earlier drafts of this note cited **BF-18** for the throttle. That
is an unrelated defect about a driver batch size; the throttle is **BF-30**, and it now travels on
`bf/throttle` rather than here.

## Test evidence

```
TEST=authsubjects npm run test-single    # 8 passing
```

Re-measured 2026-09-16 on `ce82f0cd`.

**`tests/authsubjects.test.js` is in neither `npm run test:unit` nor `npm run test:integration`** —
`test:unit` names 44 files and this is not one of them — so **a green `test:unit` run is not
evidence that this fix works.** Use `npm test`, which is what `main.yml` runs over all of
`./tests/*.test.js`.

**It needs MongoDB.** Pointed at a dead port it fails with `Timeout of 30000ms exceeded` in the
before-all hook, 0 passing. A reviewer without a mongod will see a timeout, not a failing fix.

Checked against unfixed code: the test file copied onto pristine `dev` fails there, so the suite
distinguishes fixed from unfixed.

## Semver

**Major.** The driver is the **subject allow-list**: `save` now writes only owned fields, so a
field some third-party admin tool stored on a subject or role document is dropped on the next edit,
silently and with no error. That is a capability removal with no replacement in the same changeset,
and it is what makes this branch a major rather than a minor.

**Worth weighing against how much it actually narrows.** `dev`'s `save()` is already a `replaceOne`
of a `pick()`ed object, and `GET /subjects` does not serve `notes` — so an admin-UI edit already
destroys `notes` and `created_at` on every save today. This branch's allow-list is
`['name','roles','notes','created_at']`, which is **wider** than what survives now. The genuine
loss is narrower than "fields are dropped" suggests: it is a third-party caller that POSTs a full
document carrying its own custom fields.

If the maintainer wants Phase 0 to land as `15.1.0`, the subject allow-list is one of exactly three
changes that would have to be split out.

**The operator-visible text above belongs in the release notes.** It is not a `CHANGELOG.md`
entry and this branch adds none: `CHANGELOG.md` is a release output generated between releases, and
branches never hand-edit it. Release notes are prepared as release assets in the control-surface
repo.

**What must survive into those release notes, verbatim:** the whole "If you have ever edited a
subject" section, including the rotation options table and the warning that **renaming a subject is
not a rotation**. This is the one branch in Phase 0 whose release note asks the reader to take an
action that only they can take, on a credential that may already have left their control. It must
also keep the instruction not to paste a token, digest or API secret into an issue, forum post,
screenshot or chat when asking for help.

---

## Follow-ups deliberately **not** in this PR

- ~~**`lib/authorization/storage.js` has a second unguarded `console.log` on a request path**,
  same shape as BF-05, different file.~~ **CLOSED 2026-09-16 — it is fixed by this PR**, in commit
  `56ed29d2`, described above. This entry is struck rather than deleted because it stood here while
  the branch was under review and a reader who saw the earlier text should be able to tell that it
  moved into the diff rather than being dropped. It is still present on `origin/dev`
  (`storage.js:84`) and on `bf/reads` (`:82`) until this merges, so the control-surface follow-up
  item FU-RESIDUALS correctly still reports it: that gate reads `origin/dev`, and the repair exists
  only on this branch. **Do not fix it a second time on another branch.**
- **BF-17's `created_at` residual.** `lib/authorization/endpoints.js:44` picks
  `['_id','name','accessToken','roles','notes']`; `notes` was added by this fix, `created_at` was
  not, so the field the allow-list now preserves on write is still not returned on read.
- **`aggregate.js` still passes no collection to `query.js`** — needs `bf/coercion` (#8737) and `bf/reads` (#8738)
  both merged. *Measured 2026-09-15: on the merged tree this gap is already closed —
  see `bf-reads.md`.*
- **The limit rule will be written twice** — `lib/server/count.js` and API v3's `parseLimit` — on
  purpose, so each commit lands alone. *Two readings of one rule is the root cause of this whole
  family of defects*, so leaving it duplicated is a debt with a name. **Correction, measured
  2026-09-15: `lib/server/count.js` does not exist on `origin/dev`** — it is created by `bf/reads`
  (#8738). The duplication does not exist today and is created by merging that PR, not by
  this branch.
- **`plugins.isPluginEnabled` always returns `true`** — `find` returns `undefined`, compared against
  `!== null`. No caller, so no register id.
