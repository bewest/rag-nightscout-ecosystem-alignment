# `_template` — how to cut a new release directory

**This directory is a template, not a release.** Nothing in it describes anything real.

The *convention* — why these files live in this repository rather than in the shipping
repositories, who each file is written for, and what happens at release time — is in
[`../README.md`](../README.md). Read that first. This file is only the mechanics.

## Cutting a new one

```sh
cp -r releases/_template releases/<product>-<version>
```

Then, in the new directory:

1. Delete `README.md` — this file does not belong in a release directory.
2. Fill in `contents.md` **first**. It is where the measuring happens, and the other two
   files are written from it. Writing the notes first tends to produce confident prose
   about things nobody checked.
3. Write `tag-message.txt` from `contents.md`. Contributor-facing; terse is fine.
4. Write `release-notes.md` last, from the tag message's numbered list of
   operator-visible changes. **Every item on that list needs a line in the notes.**
5. Delete every `<!-- comment -->` and `<placeholder>` as you go. A comment or an angle
   bracket left in a file means that section was not written — that is the intended
   signal, so do not delete them wholesale at the end.

## The three files must agree

They are written for three different readers and they describe one release, so they drift.
Before the directory is considered done, check across all three:

- the count of operator-visible changes is the same in `tag-message.txt` and
  `release-notes.md`, and the numbering matches `contents.md`;
- the version number appears the same everywhere, **including the directory name** — and
  if it is not settled, all three say it is not settled;
- no caveat is softened between `contents.md` and `release-notes.md`. Carry the
  safety-relevant sentences across **verbatim**;
- every register entry named in `contents.md` that produces a visible change has a line in
  the notes, and every "known issue" in the notes is traceable to an entry or is explicitly
  labelled as not having one.

## Things that are easy to get wrong

- **Do not hand-edit `CHANGELOG.md` in the shipping repository.** It is generated. That
  rule is why this directory exists.
- **Do not allocate a `BF-` id.** The register is allocated centrally and moves hourly
  across sessions. Describe the defect; let the register owner number it.
- **Do not invent a version number** to avoid writing "this is not settled". The
  unsettled ones have named placeholders in [`../README.md`](../README.md); they are
  names, not versions.
- **Do not create a directory for a release whose number the maintainer has not chosen.**
  Use the placeholder name from that table, or wait.
- **Label every figure `reproduced` or `read-derived`.** An unlabelled figure is treated
  as unlabelled, not as reproduced.

---

*Template, 2026-09-15. Drafts only; nothing in `releases/` has been pushed, tagged, merged
or published.*
