# Nightscout 16.0.0 — testing notes for the release candidate

**Not written yet (2026-11-01, `dev` `f54941b5`).** No 16.0.0 release candidate is named, so there is no call for
testers yet. This file is written when the maintainers name a candidate, in the form of
[15.0.9's testing notes](../cgm-remote-monitor-15.0.9/testing-notes.md): Part 1 in plain language for
people who use a site, Part 2 for people who run a site or write tools that use it. Until then the
runs measured so far are in the
[16.0.0 integration record](../../docs/30-design/remedial/rc-16.0.0-integration-record.md), and what
the release contains is in [contents.md](contents.md).

<!--
  CONTRIBUTOR NOTE, delete when the file is written. The sections this release will need, from
  contents.md as of dev eb72a1d3:

  Part 1 (people who use a site; plain language, no dosing advice, talk to the care team):
  - the Careportal Bolus Wizard and the Bolus Wizard Preview on a site whose profile is in the
    other units from the display (BF-172, BF-173), and choosing a profile other than the active one
    in the Bolus Wizard (BF-174);
  - the opt-in THEME=modern dashboard (#8831), on a phone and a desktop;
  - a snooze chosen on a page that is not signed in (#8816);
  - the glucose distribution report and the Loopalyzer (#8812, #8808).

  Part 2 (people who run a site, or write tools):
  - the Node floor: the server refuses to start outside <NODE_RANGE>, and the message it prints;
  - the legacy Dexcom Share and MiniMed CareLink bridges are removed; leftover bridge settings stop
    the site with a page naming the replacements; Dexcom Share through nightscout-connect;
  - IMPORT_CONFIG on a production install (BF-176, fixed by #8834; a dev Docker image published
    2026-10-25 between 17:15Z and 17:53Z has the crash);
  - MongoDB 5.0 through 8.0 (README), with the edge versions 5.0 and 8.0;
  - notes or treatments with unusual markup: sanitize-html 2.18.1 (#8835) stores one malformed
    textarea-then-image input differently (contents.md, For the release notes);
  - AndroidAPS NSClient v1 and the standalone NSClient app: zero temps and cancels within 2 s (BF-09);
  - whatever cut 2 adds, if it ships in 16.0.0: page bundles and the boot sequence, and any
    third-party plugin that hooks into the page.

  Added 2026-11-01 (session -81, dev f54941b5), Part 2, from #8889 (ID-BATCH reply format and
  ID-STRICT-V1):
  - API v1 batch POSTs (treatments, entries, devicestatus, profile, food, activity) sent with
    `Nightscout-Write-Results: items` (or `?results=items`) answer one result per item sent, in
    order; without it the reply is the array it was before. An uploader that sends a batch with
    one bad item should see that item refused in its slot and the others stored;
  - `WRITE_IDENTIFIER=strict` now applies to API v1 too: an item whose `identifier` is null, not a
    string, empty, over-length or a placeholder is refused with 400 in its slot, the rest of the
    batch is written, and a `Warning: 299` counts the refused items (every item refused: 400).
    With `WRITE_IDENTIFIER` unset or `lenient`, API v1 still drops such an identifier and stores
    the item;
  - under the opt-in, a profile re-send that needs `api:profile:update` is refused 403 in its slot
    rather than failing the batch.
  Nothing to test for #8875 (ST-VIEWS ships unwired) or #8881 (test harness only).
  Added 2026-11-01, Part 2, from #8879/#8890/#8886/#8892 (identity matching, compatibility A/B,
  write-step release 2 and the resend switch):
  - a re-send matched by `identifier` replaces the stored record by default on every collection
    and path, except v1/in-process entries; edits retain their route-specific merge/replace rules;
  - `WRITE_RESEND` defaults to `replace` and supports `merge-except-treatments`, `acknowledge`
    and `refuse`; `WRITE_DELETED_RESEND` defaults to `stay` and supports `revive`. Unset settings
    preserve 16.0.0 behavior. Per-client D20 overrides are not implemented;
  - API v3 and API v1 batch items retain their documented compatibility and opt-in reply behavior;
    no tester-facing call is appropriate until an RC is named.
  The identifier index and Q-IDX retry are implemented in draft PR #8894, stacked on #8892.
  Local tests and focused race gates pass; hosted feature CI has not run yet (only the auto-close
  check completed). The remaining ID-BATCH integration is still local at `4b48e57f`, 17 ahead and
  91 behind `official/dev`; it requires rebase and full verification after the index lands.
  No RC is named, so these are contributor notes, not a call for testers.
-->
