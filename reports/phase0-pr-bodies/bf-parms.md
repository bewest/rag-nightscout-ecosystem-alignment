# I — `bf/parms`: a bare flag in the URL stopped the page loading at all

> **Base: `origin/dev` `a8888f0d`. This is one of NINE INDEPENDENT PRs. There is no stack — no
> Phase 0 branch is based on another, and this one merges cleanly against `origin/dev` and against
> all eight of the others.**
>
> **One behaviour change to note in the release notes: Nightscout no longer turns an underscore in
> a web address into a space.** It is a fix, and it is the only thing here that could make a saved
> link behave differently. See §3.

## What changes for you

**Three fixes to how Nightscout reads your web address and how it fills in translated messages.
The first one is the reason to ship this: certain perfectly ordinary links made the page fail to
load at all, showing nothing but the loading message. No stored data is touched.**

### 1. A link with a setting but no value stopped the page loading

Nightscout reads settings out of the end of its own web address — the part after the `?`, for
example `?token=…` or `?mute=true`. It assumed **every** setting in that part had a value after an
`=` sign. Anything that did not made it fail before it had drawn anything:

- `?debug` — a setting with no value
- `?token=abc&` — an address ending in a stray `&`, which is easy to produce when copying a link
- `?a=1&&b=2` — a doubled `&`
- `?` on its own

**This mattered far more than it looks, because of where it happens.** Reading the address is the
*very first thing* Nightscout's page does. When it failed there, nothing else ran: no chart, no
connection to the server, no data, nothing on screen but the loading message. Following the
instruction "add `?mute=true` to your URL" as `?mute` did it. A trailing `&` did it.

A setting with no value now reads as empty, which is exactly how the two places that read these
settings already treat "not supplied". **A correctly formed address is read exactly as it was
before** — that is asserted as its own test.

### 2. Translated messages with ten or more inserted values came out wrong

When Nightscout builds a message in your language it inserts values into numbered slots — `%1`,
`%2`, and so on. It filled them in from `%1` upwards, and `%1` is the beginning of `%10`, so
filling `%1` first chewed into `%10` and left a stray `0` behind:

```
'%1|%9|%10|%11'   was   one|nine|one0|one1
                  now   one|nine|TEN|ELEVEN
```

**Nothing is wrong in any translation today**, because no shipped translation file uses more than
three slots. This is a trap set for the next translator who writes a tenth — it would produce a
plausible-looking wrong message, and it would look like *the translation file* was at fault rather
than Nightscout. Filling the slots from the highest number down fixes it.

### 3. Nightscout stopped turning `_` into a space — check any saved links

When reading the address, Nightscout replaced both `+` and `_` with a space. **The `+` is
correct** — in a web address, `+` genuinely means a space. **The `_` is not correct in any
encoding**, and it corrupted every access token belonging to a subject whose name contains an
underscore:

```
issued by Nightscout    mom_phone-89e148acdbbb4709
after the URL was read  mom phone-89e148acdbbb4709
```

**This was not breaking anyone's access, and the PR does not claim it was.** Measured against a
live instance: both spellings authenticate and **both return HTTP 200**, because Nightscout matches
a token on its last `-`-separated part — the 16-character code — and ignores the shortened name in
front of it. The corruption landed entirely in the part nothing reads.

**What it means for you:** nothing, in almost every case. The one thing worth checking after
upgrading is **a bookmarked or saved report link whose text you had adjusted to work around the old
behaviour** — for instance a name typed with a space because an underscore came out as a space
anyway. Those render differently now. Access tokens themselves keep working either way.

Nightscout is not a medical device and this note is not medical advice. Take questions about your
therapy to your care team.

---

## Technical detail

Three commits, 4 files, +156/−5. They are in this order deliberately: the crash first, then two
things the audit around it turned up.

| commit | register | what |
|---|---|---|
| `522c6ffb` | **BF-37** | `queryParms()` guards a valueless parameter and an empty segment |
| `c9a7a21c` | **BF-38** | `lib/language.js` substitutes `%n` backwards |
| `eb0bc918` | **BF-39** | `queryParms()` stops replacing `_` with a space |

> The PR sequencing document previously had the last two commits and their register entries
> transposed. **Corrected 2026-09-15** by `git log origin/dev..bf/parms`; the table above is the
> measured order.

**BF-37 (medium–high).** `lib/client/browser-utils.js` `queryParms()` split the query string on
`&` and then read `[1]` of each segment's split on `=` without checking one existed, so any
segment with no value produced `undefined.replace(...)`. It is called from `client.init`'s **second
statement** — `lib/client/index.js:52`, four lines in, the first statement being the `require` on
`:50` — `var token = client.browserUtils.queryParms().token;`, so the throw happens before anything
is wired up. (Commit `522c6ffb`'s subject says "on the first line of init". That is the loose
reading; the measured one is four lines in. The subject is left alone rather than rewritten,
because three documents and two queue gates quote these SHAs.) It is also called from `playAlarm`,
which is the worse place to throw, though `init` gets there first. A valueless parameter now reads
as `''`, which is what both existing callers already treat as absence
(`queryParms().token || clientToken`, `queryParms().mute !== 'true'`).

**BF-38 (latent).** `translate()` looped forwards over `%1 … %n` replacing each globally, so the
`%1` pass rewrote the `%1` inside `%10`. Same class as sorting a `position` stored as text, where
`'10'` lands between `'1'` and `'2'`: a prefix relationship that behaves until you reach ten.
Substituting backwards consumes `%11` and `%10` before `%1` can reach them.

**BF-39 (no live effect, and the entry says so).** The replacement was `/[_\+]/g → ' '`. The
underscore half corrupts tokens, as above. It is **a corruption that happens to be absorbed** — the
same shape as the food quick-pick filter working only by an accident of transport. Two ends
disagree and a third thing hides it. The corruption is real, the leniency is real, and nobody chose
the pairing. Removing `_` can only make values more faithful: the two parameters this function is
ever asked for are an access token and `mute`.

### Two things deliberately **not** changed, stated rather than implied

- **No `decodeURIComponent`.** It throws on a malformed percent sequence, and this function is
  called from the opening lines of `client.init` — which is exactly the throw BF-37 exists to fix.
  Neither caller needs percent decoding. A correct-looking decoder here would reinstate BF-37 in a
  new costume.
- **The second-`=` truncation stays.** `item.split('=')[1]` still drops anything after a second
  `=`. A token cannot contain one — the subject name is `\w` only and the digest is hex — so there
  is nothing to fix and something to record.

**How these were found.** By auditing the eslint suppressions that **BF-35** and **BF-36** turned
up under. The suppression on the `queryParms` line covered a useless `\+` escape inside a character
class — a correct answer to the question the linter asked, on a line that had a different problem.
The `language.js` suppression covered a useless `\%` escape and a non-literal `RegExp`, both
genuine; the ordering was not something either question would have asked about. Both useless
escapes are fixed and only the `RegExp` half of the second suppression remains. **Three of the five
defects found in this audit sat under a suppression that was itself correct.**

## Evidence

- Backfix register `docs/30-design/remedial/nightscout-backfix-register.md` — **BF-37** (medium–high,
  fixed), **BF-38** (fixed, latent), **BF-39** (fixed, no live effect). BF-39's section carries the
  live-instance probe: subject created through `/api/v2/authorization/subjects`, token read back,
  both spellings authorised, both 200.
- Semver classification `docs/60-research/modernization/gt4-semver-classification-2026-09-15.md`, row 5.
- PR sequencing `docs/30-design/remedial/phase0-pr-sequencing-2026-09-15.md`, branch **I**.

## Test evidence

**`tests/browser-utils.queryparms.test.js` — the test for BF-37, the crash — matches NEITHER local
npm script.** Re-measured 2026-09-16 by expanding both brace lists with `shopt -s nullglob`:
`test:unit` resolves to **44** files and `test:integration` to **89** in both trees, leaving **52**
uncovered on `origin/dev` and **53** in this worktree — the extra one being this branch's own new
test file. The earlier figure of 52 was the `origin/dev` baseline attributed to this worktree.

**A clean `npm run test:unit` on this branch is not evidence that BF-37's fix works** — though it
*is* evidence for BF-38, because `tests/language.test.js` is inside the unit brace list. CI is not
blind to either: `main.yml` runs `test-ci` over all of `./tests/*.test.js`.

Run these, from `externals/work/crm-bf-parms`:

```
TEST=browser-utils.queryparms npm run test-single   # 6 passing, 0 failing, 5 ms, NO database   (BF-37, BF-39)
TEST=language npm run test-single                   # 17 passing, 0 failing, 37 ms, NO database (BF-38)
npm test                                            # the whole tree, the only local script covering both
```

All figures **measured 2026-09-15** in this worktree. Neither needs a database.

**The test was checked by putting the bug back.**

| ablation | result |
|---|---|
| restore the `queryParms` shipped shape — guard removed **and** `_` back in the character class | **1 passing / 5 failing**: three `TypeError: Cannot read properties of undefined (reading 'replace')`, and two asserting `mom phone-89e1…` against `mom_phone-89e1…` |
| reverse the `language.js` loop direction back to forwards | **16 passing / 1 failing**: `expected 'one|nine|one0|one1' to be 'one|nine|TEN|ELEVEN'` |

Both reproduce exactly the production errors quoted in the register entries, and the 3-and-2 split
matches the two entries' separate ablation claims (BF-37 three, BF-39 two). The worktree was
restored to a clean tree afterwards.

- Merges clean against `origin/dev` `a8888f0d` — `git merge-tree --write-tree` re-run 2026-09-15,
  and clean against all eight other Phase 0 branches.

## Semver

**Patch**, with one judgement call. Nothing on the wire changes, no API response changes shape, no
environment variable is added or removed, no default flips; the fixes address an unambiguous crash
and an unambiguous mis-substitution. The ⚖ is §3: `queryParms` no longer turns `_` into a space, so
a bookmarked link relying on that decoding renders differently. The old decoding was applied
inconsistently and the server never agreed with it, which is why this stays a patch — but it
**belongs in the release notes**. Classification from
`docs/60-research/modernization/gt4-semver-classification-2026-09-15.md` rows 5 and §3.3, with the open question
recorded there as "if bookmarked report URLs count as a surface, minor".

**The operator-visible text above belongs in the release notes.** It is *not* a `CHANGELOG.md`
entry and this branch adds none: under the maintainer's rule, `CHANGELOG.md` is a **release
output** generated by GitHub tooling between releases, and branches never hand-edit it. The "What
changes for you" section is written to be usable verbatim as the release-note source text, and §3
is the paragraph that must not be dropped.

---

## Follow-ups deliberately **not** in this PR

- **`queryParms` truncates a value at a second `=`.** Recorded rather than fixed, because no value
  either caller reads can contain one. If a third caller ever appears, this becomes live.
- **`playAlarm` also calls `queryParms`**, and a throw there is worse than a throw in `init`. This
  PR removes the only known way for it to throw; it does not add error handling around the call.
- **`lib/client/index.js` `dataUpdate` has no `try`/`catch`** — the same shape as the `bf/merge`
  (H) follow-up. A throw from any client update handler still abandons the rest of that update.
- **`plugins.isPluginEnabled` always returns `true`** — `find` returns `undefined`, compared
  against `!== null`. No caller, so no register id.
