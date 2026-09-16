# C — `bf/auth`: two security fixes in how access tokens are stored and how failed logins are slowed

> **Base: `origin/dev` `a8888f0d`. This is one of NINE INDEPENDENT PRs. There is no stack — no
> Phase 0 branch is based on another, and this one merges cleanly against `origin/dev` and against
> all eight of the others.**
>
> **Needs a maintainer's explicit yes before merge — one of two branches in the set that does
> (the other is `bf/alarms`, A).** Two reasons, and neither is a code-quality question:
> the subject allow-list **removes a field-passthrough capability with no replacement**, which is
> the major-forcing row in this branch; and the credential-exposure fix **cannot undo what already
> happened**, so some sites will need to rotate a token by hand afterwards. That is an operator
> action the code cannot take for them.
>
> **Read the "If you have ever edited a subject" section before merging.**

## What changes for you

**Two security problems are fixed. Nothing about how you log in, and nothing you see on screen,
changes. No stored readings or treatments are touched.**

### 1. Editing an access-token holder wrote their token into the database in readable form

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

**After this change**, a subject's token is never written, on create or on edit, and any copy that
a previous edit left behind is discarded when Nightscout next loads it.

### 2. Anyone could bypass the delay on wrong-password attempts

Nightscout slows down repeated failed access attempts, so that someone cannot guess a token or
API secret by trying millions of values. It decided *who* to slow down using a piece of
information the person connecting can simply make up (the `X-Forwarded-For` header). Changing it
on every attempt reset the delay every time, so the protection could be skipped entirely.

**After this change** the delay is keyed to the actual network connection plus a scrambled,
non-reversible fingerprint of the credential that was tried, so it cannot be sidestepped by
changing a header.

**This will not slow down your normal use**, and that is deliberate: the wait now happens only
*after* an attempt has already failed. Requests that succeed are never delayed, and requests
carrying no credential at all are never delayed. If your site is behind a shared proxy or a CGNAT
address, another person's failed attempts will not make your working app wait.

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

The fix removes the *stored copy* and stops new ones being made. **Retiring an exposed token is a
separate action, and only you can decide to take it.**

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

Two commits, both on `lib/authorization/`:

**`a26ba416` — failed-auth throttle keyed to a spoofable header.** `lib/authorization/delaylist.js`
bucketed failures by the caller-supplied `X-Forwarded-For` value. Replaced with a new
`lib/server/peer-address.js` that reads the socket peer address, combined with a salted digest of
the presented credential. The `sleep` was also moved out of the request path and below both the
`authAttempted` early return and both success paths, so only an attempt that has already failed
waits.

**`64db1f35` — derived credentials persisted on update.** `lib/authorization/storage.js` now
carries explicit allow-lists — `SUBJECT_FIELDS = ['name','roles','notes','created_at']` and
`ROLE_FIELDS = ['name','permissions','notes','created_at']` — used by both `create` and `save`, so
a save writes only owned fields. `DERIVED_SUBJECT_FIELDS = ['accessToken','accessTokenDigest',
'digest']` are deleted from each document in `reload()` *before* being re-derived, so a row written
by an older version cannot supply one. `lib/authorization/endpoints.js` adds `notes` to the
`GET /api/v1/subjects` projection.

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

- Backfix register: `docs/30-design/nightscout-backfix-register.md` — **BF-17** (persisted derived
  credential) and **BF-18** (spoofable throttle key).
- Semver classification: `docs/60-research/gt4-semver-classification-2026-09-15.md`. GT4 classifies
  the throttle change as **minor** (the delay moved to the failure path, so no successful request is
  newly delayed) and the subject allow-list as the **major-forcing** row in this branch, because it
  removes a field-passthrough capability with no replacement.

## Test evidence

**`npm run test:unit` is not evidence that either of these fixes works, and must not be quoted as
though it were.** Measured 2026-09-15 by reading the brace list in this worktree's `package.json`:
`test:unit` names 44 files and **neither `authsubjects` nor `authdelay` is among them**. Both of
this branch's own test files match neither local npm script — they are two of the 52 such files.
An earlier version of this section quoted "unit suite on this branch: 361 passing, 0 failing" as
the branch's test evidence; **that number could have held with both security fixes reverted.** CI
is not blind to this — `main.yml` runs `test-ci` over all of `./tests/*.test.js` — but the local
scripts are.

Run these, from `externals/work/crm-bf-auth`:

```
TEST=authdelay    npm run test-single    # 11 passing, 0 failing, 2 s      (BF-18)
TEST=authsubjects npm run test-single    #  8 passing, 0 failing, 385 ms   (BF-17)
npm test                                 # the whole tree, the only local script that covers both
```

**Reproduced 2026-09-15 in this worktree**, not read from another session's record: 11 passing and
8 passing respectively, both exit 0.

**Both need MongoDB.** Reproduced by repointing `CUSTOMCONNSTR_mongo` at a dead port (`29999`) in a
copy of `my.test.env` — both files then fail with `Timeout of 30000ms exceeded` in the before-all
hook, 0 passing. They are fast only because a mongod is listening on this worktree's port
(`27031`). A reviewer without one will see a timeout, not a failure of the fix. *(The worktree was
not modified; the altered env file was written to a scratch directory.)*

- `tests/authsubjects.test.js` (252 new lines) and `tests/authdelay.test.js` (197 new lines) —
  8 and 11 tests respectively.
- Non-vacuity: GT1 copied this branch's changed test files onto pristine `origin/dev` code and
  confirmed they fail there, so the suite distinguishes fixed from unfixed. **Read from GT1's
  record, not re-run here** — the two runs above are reproductions of the green state only.
- Merges clean against `origin/dev` `a8888f0d` — `git merge-tree --write-tree` re-run 2026-09-15
  18:52, tree `3f4fe6ac6a`.

## Semver

**Major**, and this branch is one of the three rows that makes Phase 0 as a whole a major rather
than a minor. The driver is **not** the throttle change, which GT4 grades **minor** because the
delay moved onto the failure path and no successful request is newly delayed. The driver is the
**subject allow-list**: `save` now writes only owned fields, so a field some third-party admin tool
stored on a subject or role document is dropped on the next edit, silently and with no error. That
is a capability removal with no replacement in the same changeset. Classification from
`docs/60-research/gt4-semver-classification-2026-09-15.md`.

If the maintainer wants Phase 0 to land as `15.1.0`, the subject allow-list is one of exactly three
changes that would have to be split out.

**The operator-visible text above belongs in the release notes.** It is *not* a `CHANGELOG.md`
entry, and this branch correctly adds none — measured, `git diff --name-only a8888f0d..bf/auth`
lists ten files and `CHANGELOG.md` is not among them. **That is the required state, not a gap.**
An earlier version of this section called it a gap and asked for a changelog entry before merge;
that was wrong. Under the maintainer's rule, `CHANGELOG.md` is a **release output** generated by
GitHub tooling between releases, and branches never hand-edit it. Release notes are prepared as
release assets in the control-surface repo.

**What must survive into those release notes, verbatim:** the whole "If you have ever edited a
subject" section, including the rotation options table and the warning that **renaming a subject is
not a rotation**. This is the one branch in Phase 0 whose release note asks the reader to take an
action that only they can take, on a credential that may already have left their control. It must
also keep the instruction not to paste a token, digest or API secret into an issue, forum post,
screenshot or chat when asking for help.

---

## Follow-ups deliberately **not** in this PR

- **`lib/authorization/storage.js` has a second unguarded `console.log` on a request path**, same
  shape as BF-05, different file. It prints `'Loading', opts` on every subject-list call. Line
  number moves per branch — `:84` on `origin/dev`, `:113` on `bf/auth`, `:82` on `bf/reads`. No
  register id allocated.
- **BF-17's `created_at` residual.** `lib/authorization/endpoints.js:44` picks
  `['_id','name','accessToken','roles','notes']`; `notes` was added by this fix, `created_at` was
  not, so the field the allow-list now preserves on write is still not returned on read.
- **`aggregate.js` still passes no collection to `query.js`** — needs D (`bf/coercion`) and E
  (`bf/reads`) both merged. *Measured 2026-09-15: on the merged tree this gap is already closed —
  see `bf-reads.md`.*
- **The limit rule will be written twice** — `lib/server/count.js` and API v3's `parseLimit` — on
  purpose, so each commit lands alone. *Two readings of one rule is the root cause of this whole
  family of defects*, so leaving it duplicated is a debt with a name. **Correction, measured
  2026-09-15: `lib/server/count.js` does not exist on `origin/dev`** — it is created by `bf/reads`
  (E). The duplication does not exist today and is created by landing E, not by this branch.
- **`plugins.isPluginEnabled` always returns `true`** — `find` returns `undefined`, compared against
  `!== null`. No caller, so no register id.
