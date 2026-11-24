# Reviewing the cgm-remote-monitor programme

*Contributor guide, updated 2026-11-24. This workspace holds the queue, release
records, source comparisons and test harnesses. The application lives in
`externals/cgm-remote-monitor-official`.*

## Choose a review

| If you are reviewing | Start with | What to establish |
|---|---|---|
| The closing single-tenant 16.0.0 candidate | [Release contents](../../releases/cgm-remote-monitor-16.0.0/contents.md) and [testing notes](../../releases/cgm-remote-monitor-16.0.0/testing-notes.md) | Which commit and image were tested, which clients and upgrade paths were exercised, and which observations the releaser still needs. |
| A defect or fix | [Backfix register](../30-design/remedial/nightscout-backfix-register.md) and [reviewer packets](../../reports/reviewer-packets/README.md) | Which versions exhibit the defect, how it was established, where the fix landed and whether it reached a shipping tag. |
| Multitenant support | [Tenancy reading guide](../30-design/tenancy/README.md), [decisions in force](../30-design/tenancy/decisions-in-force.md) and [execution log](../30-design/tenancy/execution-log.md) | Which candidate implements the behaviour and which deployment, workload and failure conditions its evidence covers. This work has its own acceptance criteria. |

The [programme status](PROGRAMME-STATUS.md) connects all three. [Work waiting on a person](NEEDS-A-HUMAN.md)
identifies the recorded reviewer or decision owner.

## Read the evidence

1. Find the item in the [work queue](../../queue/QUEUE.md). Check its gates,
   dependencies and review packet. Use the upstream `official/*` ref for source
   comparisons and the recorded commit for a dated measurement.
2. Check what the gate observes. **Reproduced** means the behaviour was exercised.
   **Read-derived** means the claim came from inspecting source or records. Look
   for a negative control that failed when the property was broken and passed
   when restored. A skipped or uninstrumented check supplies no passing evidence.
3. Compare the result with what the user actually sees. A plausible glucose
   value from the wrong record or a missing alarm can survive a passing build.
   Read changes to expected values alongside the implementation.
4. Locate the result. **Fixed** means on a branch, **merged** means in application
   `dev`, and **released** means in an operator-installable tag. A multitenant
   experiment may qualify a particular path on a local candidate. The
   [delivery dashboard](../30-design/tenancy/multitenant-delivery-dashboard.md)
   gives the milestone criteria.

## Run a bounded check

```bash
make queue-status ID=RT-16-RELEASE
make queue-check
```

Use a separate worktree and disposable test database when exercising application
code. Check the packet's source head, test selection and expected failure
before interpreting a pass. Keep user traces and identifiers out of public
records. The maintainer owns pushes, tags and release publication.

<!-- BEGIN GENERATED: provenance -->

*Generated from `queue/work-queue.yaml` by `tools/queue/emit_views.py`. Manifest `measured_at` **2026-09-27**, against cgm-remote-monitor-official `7000eb18` and this repository at `18cdcce0`. Every state above is a **claim** about what the gates will say &mdash; `make queue-status` is the measurement.*

<!-- END GENERATED: provenance -->
