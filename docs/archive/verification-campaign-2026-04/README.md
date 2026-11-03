# Verification campaign, April 2026 (archived)

*What this is: an archive index (contributor-facing). Snapshot of the January–April 2026 AID research
campaign's verification dumps; nothing here is maintained. Moved from the repository root on
2026-11-03; the git history of each file is unchanged (`git log --follow`).*

These files were written by verification agents checking the research reports of the
January–April 2026 campaign (the EXP-series experiments under `docs/60-research/`, the
`tools/cgmencode` and `tools/aid-autoresearch` pipelines). They report which reports' figures
reproduced, which did not, and what was corrected. They are **outside document control**
([DOCUMENT-CONTROL §1](../../00-overview/DOCUMENT-CONTROL.md#1-scope)) and are not published on
the site (`tools/site/exclusions.yaml`, axis `noise`).

Where to start if you need them:

| file | what it is |
|---|---|
| `CAMPAIGN_FINAL_REPORT.md` | the campaign's closing summary (246 reports, 2026-04-22) |
| `VERIFICATION-INDEX.md`, `VERIFICATION-INDEX-APRIL10-FINAL.md`, `PHASE3-VERIFICATION-INDEX.md` | the per-phase indexes of the other files |
| `verify_reports.py`, `verify_reports_deep.py` | the scripts that produced the batch results; they were run from the repository root and resolve `docs/60-research/...` paths relative to it |
| `VERIFICATION_RESULTS_32_REPORTS.json`, `PHASE3-VERIFICATION-DETAILED.json`, `*.csv` | machine-readable results |

The programme that replaced this way of working, with gates, controls and release records, is
described in [`AGENTS.md`](../../../AGENTS.md) and `queue/README.md`.
