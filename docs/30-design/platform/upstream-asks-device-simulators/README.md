# Device simulators and app rigs: requests to their projects

*What this is: an outreach draft (contributor-facing). Read after the [device-simulators
record](../../../60-research/programme/device-simulators-2026-10-17.md); leads to each row's draft
message. Status: drafts; each row's status column says whether it was sent. **Living**: drafted
outgoing messages, kept current until each is sent or dropped. Facts checked 2026-10-17 against the repositories' heads, releases and open pull requests
through the GitHub API, at this repository's `9c198f93`. Evidence:
[device-simulators record](../../../60-research/programme/device-simulators-2026-10-17.md) (§3 how the
pieces join, §6 the missing joins) and the three deep dives in `docs/10-domain/`. Each project's maintainers decide what to do with an
ask.*

## How to use these drafts

- **Send in your own words.** LoopWorkspace's and Trio's CONTRIBUTING both say they "do not accept
  pull requests that are largely AI-generated or submitted without careful engineering judgment",
  and that they "welcome thoughtful use of tooling, but contributions need to be intentionally
  designed"; the rule is about who verifies and owns a change, and both projects' own commits name
  coding agents ([agents in the ecosystem §2](../agent-trust-boundaries-2026-10-18.md#2-develop)).
  These drafts are messages, not pull requests, but read and rewrite each one before it goes out,
  and author any resulting PR yourself.
- **Use the channel each project names.** Quoted in the table. LoopKit/pod and LoopKit/LoopWorkspace
  have GitHub issues turned off.
- **Push this repository first.** The evidence links point at
  `github.com/bewest/rag-nightscout-ecosystem-alignment/blob/main/…`, which shows `d9167f59` until the
  device-simulator commits are pushed.
- **Re-check before sending.** Each row's "already in flight" column was true on 2026-10-17. If a
  project has since merged or answered, change the ask or drop it.
- When a message is sent, record the date and link in the status column; when it is answered,
  record the answer.

## The asks

| # | to | channel (the project's own words) | ask | already in flight (2026-10-17) | draft | status |
|---|---|---|---|---|---|---|
| 1 | LoopKit/g7sim | GitHub issue (issues on; no CONTRIBUTING; LoopKit norms) | run the existing 33 tests in CI; four README corrections | nothing filed (only #1, closed 2026-10-10) | [g7sim-ci-and-readme](g7sim-ci-and-readme.body.md) | draft |
| 2 | LoopKit/g7sim | GitHub issue | emulator strictness (client proofs, display signature) and anomaly controls (frame faults, a clock) | nothing filed | [g7sim-fidelity](g7sim-fidelity.body.md) | draft |
| 3 | Loop developers | [Loop Zulip](https://loop.zulipchat.com/) ("reach out to the contributor core on Loop Zulipchat", LoopWorkspace CONTRIBUTING `ae75603c`) | the Simulator rig's path to `dev` (G7SensorKit #89, OmnipodKit #188, LoopWorkspace #454); pod fidelity (reservoir draw, faulted commands), since pod has issues off | LoopWorkspace #454 open since 2026-06-04 | [loop-zulip](loop-zulip.body.md) | draft |
| 4 | loopandlearn/OmnipodKit | GitHub issue, feature-request template ("indicate which OSAID app you are using") | bring #188 (ImpossiBLE detection) to `dev` | #188 merged to `next-dev` 2026-10-12; no PR to `dev` | [omnipodkit-188-to-dev](omnipodkit-188-to-dev.body.md) | draft |
| 5 | nightscout/Trio | comment on PR #1548; Trio Discord first for anything larger ("discuss it with the community first", Trio CONTRIBUTING) | include G7SensorKit #89 (Simulator bridge) in the branch #1548 pins | #1548 open; its G7SensorKit branch has `7da3b69` but not #89 | [trio-1548-comment](trio-1548-comment.body.md) | draft |
| 6 | mickeyl/ImpossiBLE | comment on PR #6 (issues on; no CONTRIBUTING) | review of PRs #2–#6, with who depends on them | #2–#6 open, no maintainer comment; latest tag 3.1.0 is g7sim's pin | [impossible-review](impossible-review.body.md) | draft |
| 7 | jwoglom/trio-test-harness | GitHub issue (issues on; none filed) | a licence | none | [tth-licence](tth-licence.body.md) | draft |
| 8 | jwoglom/trio-test-harness | GitHub issue | a lab-Nightscout option, external simulators, run status semantics, a stale "private repo" comment | none | [tth-nightscout-and-sims](tth-nightscout-and-sims.body.md) | draft |
| 9 | G7 implementations: xDrip first | [xDrip Discussions](https://github.com/NightscoutFoundation/xDrip/discussions) ("discuss your ideas with project maintainers using Discussions prior to implementation", xDrip CONTRIBUTING); then pointers to G7SensorKit, g7sim, xdripswift, xdrip-js, Juggluco | one shared fixed-randomness EC-JPAKE transcript every G7 implementation's tests replay | no activity in any of the six | [g7-shared-transcript](g7-shared-transcript.body.md) | draft |

Not asked, on purpose: faketandem (nothing missing for these joins); CI for G7SensorKit, because
LoopWorkspace's CircleCI already runs `G7SensorKitTests` at the commit it pins, and is green on
`next-dev` (`1561bff0`), which pins the direct connection; and the census's own corrections (made in
this repository).

## Order

Asks 1, 2, 6 and 7 stand alone. Ask 3 is the one conversation the rest of the Loop-side joins depend
on, so send it before 4 and 5. Ask 8 is more useful once 7 is answered. Ask 9 is a proposal, not a
request for work, and can go at any time.
