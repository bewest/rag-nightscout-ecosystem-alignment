# <Product> <version> — release notes (DRAFT)

<!--
  TEMPLATE. Copy the whole _template directory, rename it, then delete every
  HTML comment as you fill the section in. A comment left in the file means
  that section was not written.

  AUDIENCE: a person managing their own or a family member's diabetes. Not a
  contributor. Plain language, every term defined at first use, every
  safety-relevant caveat preserved VERBATIM from the contributor-facing text.
  Never simplify algorithm or alarm behaviour in a way that could mislead
  someone relying on it. No individualised insulin dosing advice.
  The rules are docs/30-design/semver-and-release-versioning-policy-2026-09-15.md
  section 5.6; section 3.3 is the worked example of failing them.
-->

**Status: DRAFT for maintainer review. Nothing has been merged, tagged or released.**
<!-- If the number is unsettled, keep the next line. If it is settled, delete it. -->
**The version number is not settled — see [About the version number](#about-the-version-number).**
**Nightscout is not a medical device and nothing here is medical advice.**

> **These notes complement the generated changelog; they do not replace it.** The changelog
> lists what merged. These notes say what you will **notice**, what you must **do**, what to
> **check afterwards**, and what is still **broken**. If the two disagree, the changelog is
> right about *what changed* and these notes are right about *what it means for you* — and
> the disagreement itself is worth reporting.

<!-- One or two sentences: what kind of release this is, and whether a normally
     cautious operator should take it now or wait. Say plainly if something in
     it will change what their site does without being asked. -->

---

## Read this first: <N> things will happen that you did not ask for

<!--
  THE MOST IMPORTANT SECTION. Every behaviour change from the tag message's
  "operator-visible" list that the operator did not request goes here, at the
  top, before anything they might want.

  An alarm that STARTS FIRING, a request that STOPS WORKING, a number that
  CHANGES, data that LOOKS slower to arrive — all of these go above the fold.
  If this release has none, delete the section and say so: "Nothing in this
  release changes what your site does without being asked."

  For each one, use this shape:
-->

### 1. <What happens, in the operator's words — not the code's>

**The short version:** <one sentence a tired person reads at 3 a.m.>

**Who gets what.** <If different groups get different things — everyone sees a
pill, only some receive a notification — use a table. Conflating them is the
most common way these notes mislead.>

| | Who it reaches | What it is |
|---|---|---|
| <the quiet change> | <who> | <what, including whether it makes a sound> |
| <the loud change> | <who, and the exact setting that decides it> | <what> |

**When.** <The threshold, the default value, and the setting name that changes it.>

**Does it repeat?** <Answer this explicitly for anything that alerts. "It fires
once and does not repeat" and "it will keep nagging you" are different promises
and an operator will plan around whichever one you write. If it fires once, say
what to watch instead.>

**What you must do.** <Concrete steps, or "nothing". If a new alert can reach a
phone, say to warn the people holding the phones — in this community that is
often a parent, a partner or a school nurse who was not told the site was
upgraded. If there is an opt-out, name the exact setting and say what it does
NOT switch off.>

<!-- Where the change could touch a therapy decision, close the item like this: -->
**Nothing about your insulin, your pump or your therapy has changed.** Only what
Nightscout tells you. This is not medical advice. **If you are unsure what is right
for you, that is a question for your care team.**

---

## What is fixed

<!-- The ordinary bug fixes: things that were supposed to work and did not.
     Lead with the ones a person would have NOTICED being broken.

     If a fix makes stored or displayed data change — a chart that was empty
     filling in, a number that was wrong becoming right — it is NOT an ordinary
     fix and it belongs above the fold, with the contributor-facing caveat
     carried over word for word. The model is bf/coercion's: "earlier results
     may have under- or over-reported delivered therapy." Do not paraphrase a
     sentence like that into something softer. -->

---

## What you must do

<!-- A numbered list an operator can work through, in order. Every item names
     the exact setting, address or button. "Review your configuration" is not
     an instruction. If the answer is genuinely nothing, say "Nothing." and
     then say what to watch anyway.

     Anything with a DEADLINE — a deprecation window, a setting that must be
     added before a later release — states the deadline and the version that
     will enforce it, by number. Not "a future release". Policy section 5.3. -->

---

## What to check afterwards

<!-- How the operator tells "working" from "broken" AFTER upgrading. This is
     the section that gets skipped and the one that prevents a support thread.

     Cover, where they apply: what a normal result looks like now; how long to
     wait before worrying; which of their own alarms may fire as a consequence
     of the change rather than a problem; and what to look at instead if a
     signal they used to rely on has gone quiet. -->

---

## Known issues, and things this release does not fix

<!-- Name them so nothing surprises anyone later, including defects that are
     not new. For each: what an operator would see, whether it can stop data
     arriving, and what to do if it happens.

     Anything whose real-world frequency is unknown says so. Do not imply a
     measurement that was not made. If the honest statement is "this has not
     been checked against a real account", write that. -->

---

## About the version number

<!-- If the number is settled, say what it is and why it is not higher or lower,
     citing docs/30-design/semver-and-release-versioning-policy-2026-09-15.md.

     If it is NOT settled, say so plainly, say what the disagreement is, and say
     whether it changes anything the operator receives — usually it does not,
     and saying so stops the uncertainty reading as risk. Never invent a number
     to avoid the paragraph. -->

---

*Draft, <date>. Prepared locally; nothing has been pushed, tagged, merged or published.
Requires maintainer review before publication. Nightscout is not a medical device, and
nothing in these notes is medical advice or guidance about insulin dosing. If anything
here affects decisions about your therapy, discuss it with your care team.*
