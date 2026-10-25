# Nightscout 16.0.0 — testing notes for the release candidate

**Not written yet (2026-10-25).** No 16.0.0 release candidate is named, so there is no call for
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
  - IMPORT_CONFIG on a production install (BF-176), once its fix is merged;
  - AndroidAPS NSClient v1 and the standalone NSClient app: zero temps and cancels within 2 s (BF-09);
  - whatever cut 2 adds, if it ships in 16.0.0: page bundles and the boot sequence, and any
    third-party plugin that hooks into the page.
-->
