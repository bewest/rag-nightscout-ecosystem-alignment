# cgm-remote-monitor 16.0.0 — contents

**Current update, 2026-11-03:** `official/dev` `4a482627bfdafb1fef8dcbe0ac6c484811cae563`
is the current 16.0.0 release candidate. Release preparation is **in progress**,
not blocked; the candidate is not tagged or released. Informal cohort/real-rig
testing is underway, with over 24-48 hours reported by the maintainer, not yet a
version-pinned acceptance record. Master protection no longer requires the absent 4.4 check; its two
remaining required lanes are green and review/staging continues. #8829's reporter
reports persistence on dev, but neither maintainer reproduced it and many DIY
and production/service environments work. The maintainer dispositions #8829
**nonblocking** for v16; diagnosis remains follow-up. #8855 now has green checks; new report proposal
#8897 has no checks returned. BF-72/BF-161 remain private pre-tag work.
| Date | Candidate and process status | Evidence and remaining steps |
|---|---|---|
| 2026-11-03 | `official/dev` `61eb37335954ae42c91345a0823bd67331025165` is the current release candidate; release preparation is in progress. No tag or release is published. | Candidate anchor read from refreshed `official/dev`. Existing acceptance record has green integrated CI/CodeQL on this head; private security integration and final-tree checks, live alert checks, pinned cohort/rig/rollback evidence, and staging/review remain pending. No release-level test or cohort result is asserted here. |
| 2026-11-03 | #8899 merged at 22:52:32Z as `official/dev` `4a482627bfdafb1fef8dcbe0ac6c484811cae563` (head `75fb4cdfd8fca37d83dab7d2bc3cc2fed37b45ed`); the D21 CLI naming amendment is in the candidate, not released. | Replaces the unavailable `nightscout serve` namespace with `nightscout multitenant`; enables no roles and preserves `single` and legacy start paths. Reproduced on the PR head: full non-browser `npm run test:all` 6652 passing / 3 pending / 0 failing on Node 22.23.4 and disposable MongoDB 8.0.34; targeted CLI/listener/headless suites 46/0; changed-file ESLint 0 errors, 6 warnings; red no-alias control. Reproduced: merged tree equals the tested PR head (`git diff --exit-code 75fb4cdf 4a482627`). Read-derived: pre-merge test/build/CodeQL checks passed, browser and maintained-MongoDB checks were still pending; merged-head CI and CodeQL were in progress at capture. See [R21](../../docs/30-design/remedial/rc-16.0.0-integration-record.md#r21---d21-cli-profile-naming-on-75fb4cdf-2026-11-03) and R22. Release-level acceptance remains pending. |
| 2026-11-03 | Separate multitenant foundations PR #8898 remains open at remote head `a19b549c`. Local CI fix `04321de0` and current-dev merge `0afdb87f` are integrated on `workspace/multitenant-20261102`, unpushed. No release-candidate merge or operator-visible behavior change is asserted. | Reproduced: eight disabled integration labs caused execution-accounting failures, not lab assertion failures; explicit opt-in pending accounting and its negative control pass. On the combined tree, seven non-browser tiers pass 6711/100 pending/0 failing; focused regressions pass 39; selected enabled PG/Vault/lab checks pass 36. Read-derived review and API read-back: three test-only CodeQL alerts individually dismissed as false positives. Browser and remaining opt-in campaigns are unmeasured; fresh remote CI is pending publication. See the [bounded CI-fix evidence](../../docs/archive/tenancy/multitenant-delivery-roadmap-2026-11-02.md#pr-8898-database-ci-accounting-fix-2026-11-03) and [security disposition](../../docs/archive/tenancy/multitenant-delivery-roadmap-2026-11-02.md#pr-8898-security-check-disposition-2026-11-03). |
| 2026-11-03 | Update at 17:19-08:00: #8898 is published at `0afdb87f83c3b66a5206fa8bd9e5046696bcc2d1`, still open/draft, not merged to the candidate. The [execution phases and subagent plan](../../docs/archive/tenancy/multitenant-delivery-roadmap-2026-11-02.md#execution-phases-and-subagent-plan-2026-11-03) sequences entries compatibility and deployment authority/runtime wiring in parallel, then integrated HTTP, broader REST/client acceptance, realtime and operations. | Read-derived from fresh PR metadata/checks: CodeQL, four database jobs, both no-database jobs, Docker validations and npm install/build pass; browsers and maintained MongoDB remain pending. Reproduced selected queue measurement: ST-PG identity unit gate PASS; integrations skipped, other selected items UNMEASURED. This is a plan and bounded CI follow-up, not milestone promotion, all-REST acceptance, role enablement or a new release gate. No operator-visible change; no new implementation agent dispatched. |
| 2026-11-03 | Execution started from #8898 head `0afdb87f`: two isolated subagent lanes are dispatched for entries/API compatibility and deployment authority/runtime contracts. Each first establishes its smallest reproducible gap, then implements only an established contract; unresolved design decisions stop that slice. | Read-derived fresh `gh pr checks 8898 --repo nightscout/cgm-remote-monitor --json name,state`: aggregate Tests pass, CodeQL, all browser/database/no-database and validation checks are SUCCESS; publication jobs are SKIPPED, not failures. New lane acceptance is UNMEASURED while agents run. SQLite session tasks track ownership/dependencies; the single programme queue and milestone states remain unchanged. No operator-visible change or role enablement. |

See the [current ecosystem/acceptance record](../../docs/10-domain/nightscout-v16-ecosystem-deep-dive.md),
[draft release notes](release-notes.md) and [cohort collection guide](testing-notes.md).
Historical status/measurement sections below retain their dates.

### Update: bounded PG consolidation and race compatibility; independent v1 evaluator replay (2026-11-05)

| Work / state | Evidence and remaining boundary |
|---|---|
| Local cumulative REST `44331668038dca5bc23af24c4125052b9c8e5612` accepts bounded common PG mechanics and index-on race compatibility. | [R46](../../docs/30-design/remedial/rc-16.0.0-integration-record.md#r46---bounded-pg-consolidation-and-identifier-races-on-44331668-2026-11-05): parent full7051/80pending/0failing, default browser684 on application-identical e5796b32, archived common contracts75. Expanded baseline/current ports and real Mongo/PG duplicate races preserve source-specific policy; shared order/projection/precommit and retry controls fail semantically. Initial legacy-ID and UTC fixture failures are preserved; final corrected full campaign passes. No broader portability or milestone claim. |
| Independent local evaluator `0c98ad06f8e01114639d58e1bc0724499af97f1f` adds actual shipping v1 configurator replay in a test-only app. | [R47](../../docs/30-design/remedial/rc-16.0.0-integration-record.md#r47---independent-shipping-v1-evaluator-replay-on-0c98ad06-2026-11-05): agent full6688/3pending/0failing/default browser684, parent audited immutable logs and reproduced archived36 plus write-trigger/closed-service controls. Production source, executable routes and physical subscriber unchanged; no REST join or socket enablement. |
| Four selected bounded gate/control pairs PASS/NON-VACUOUS; independent reviews find no blocking issue. | Consolidation, earlier identity, new index-on race and expanded profile instruments. Complete M1/M2/M3 and wider M0-M6 remain open. Historical release comparison is not rerun or transitively expanded by direct current-backend race evidence. |
| Published #8898 OPEN/draft at R44 bc4ee1a9; #8891 OPEN/draft at R45 dff9a8d4. | Both published heads have successful CI/CodeQL at fresh read-back. New application continuations remain local/unpushed; final prchecks contain current dev. Local `externals/work/HANDOFF-pg-consolidation-integration-20261105.md` indexes heads, controls, logs, draft descriptions and maintainer-only publication commands. |
| Next: runtime characterization of shared frame acquisition and continued compatibility/evaluator coverage. | [Read-derived frame inventory](../../docs/30-design/tenancy/architecture-seams-execution-plan-2026-11-05.md#shared-frame-inventory-and-next-characterization) starts ARCH-DERIVED-FRAME preparation without claiming convergence or snapshot consistency. Remaining helper relocation, settings/clients/side effects, owner identity/ceilings, import/resources, lifecycle and durable M5/M6 retain their gates. SQLite stays deferred. |
| Dashboard and next-gen map validated locally. | Queue validation/generation/check and links pass; selected bounded gates/control pairs remain PASS/NON-VACUOUS. Site-check passes scans/provenance/noindex/robots; headless map verifies R46, independent R47, read-derived frame preparation and incomplete M3 with zero page errors. Render source `75af70098fb4ea9c0204921803ddbd3e4447c4da` is recorded in pages.yaml; no publication or new runtime result follows from rendering. |

### Update: composition and direct identity accepted; independent HTTP profile replay (2026-11-05)

| Work / state | Evidence and remaining boundary |
|---|---|
| Local cumulative REST `bc4ee1a91b84a657012dbb77ee835fdeb78ef707` accepts current-domain composition and imported-identity differential. | [R44](../../docs/30-design/remedial/rc-16.0.0-integration-record.md#r44---explicit-backend-composition-and-imported-identity-on-bc4ee1a9-2026-11-05): parent-reproduced full7035/80pending/0failing, default browser684, archived composition15 and identity15. Actual CLI/refusal and HTTP/storage controls fail semantically, restored gates pass; independent read-derived source review finds no blocking extraction issue. No new query/write/backend policy or full portability claim. |
| Independent local profile `dff9a8d42860be09c7f187f5e3d0527d6eb31d80` extends #8891 with actual API3 writer/no-op replay. | [R45](../../docs/30-design/remedial/rc-16.0.0-integration-record.md#r45---independent-actual-http-profile-writers-on-dff9a8d4-2026-11-05): agent-reproduced full6682/3pending/0failing and default browser684, parent-audited anchored aggregates; parent-reproduced archived30 and actual trigger/closed-service controls. Review reproduced and corrected a closed-notification fixture; final live emission assertions pass. Production source and physical subscriber unchanged; no REST join. |
| Three new/current bounded gate-control pairs are PASS/NON-VACUOUS. | Composition, direct imported-identity and expanded independent profile instruments. Their broader cards and M0-M6 remain incomplete. Historical R42 comparison is not rerun or enlarged by direct current-backend identity coverage. |
| Published #8898 remains OPEN/draft at R42 d4570e58; #8891 OPEN/draft at R43 925c9527. | November 5 fresh read-back: both published heads have successful CI and CodeQL. The new continuations remain local/unpushed; no merge, release, role enablement or RC admission. Local `externals/work/HANDOFF-compose-integration-20261105.md` indexes owned branches, verification, review findings and maintainer publication commands. |
| Next: proven adapter consolidation, continued compatibility and independent profile/shared-frame characterization. | [Current roadmap](../../docs/archive/tenancy/multitenant-delivery-roadmap-2026-11-02.md#accepted-composition-and-direct-identity-continuation-2026-11-05). Owner identity/ceilings, logical no-op admission, remaining REST/client/import/resource/lifecycle and durable M5/M6 gates stay open; SQLite remains deferred. |
| QMS generated views and rich progress page validated. | Queue validation/generation/check, document links, three bounded gates and NON-VACUOUS controls pass. The local site-check and headless map interactions pass with current R44/R45 evidence and planned consolidation preserved. Render source `cdc41a331461d958e2f779ebc97f3ab93219d319` is recorded in pages.yaml; rendering implies no new runtime result. |

### Update: contract and management HTTP accepted; profile independently refreshed (2026-11-05)

| Work / state | Evidence and remaining boundary |
|---|---|
| Local REST `d4570e585d0e12e46386ed26772790b269b2b736` accepts storage-port characterization and separate management HTTP over R41. | [R42](../../docs/30-design/remedial/rc-16.0.0-integration-record.md#r42---storage-contracts-and-separate-management-http-on-d4570e58-2026-11-05): parent full7015/80pending/0failing, restored focused233 and default browser684 on application-identical precursor pass. Real lower/preview/Mongo capabilities and management persistence/current-grant tests have semantic controls. Full-run subscriber guard's Markdown false positive was corrected and real-listener/fail-closed controls verified. No management listener/identity/ceilings or full REST claim. |
| Independent #8891 refresh `925c95278ed04954d1181201da79ae5d6c48c095` is locally accepted for its bounded prototype scope. | [R43](../../docs/30-design/remedial/rc-16.0.0-integration-record.md#r43---independent-nonresident-profile-refresh-on-925c9527-2026-11-05): full6676/3pending/0failing, default browser684 and actual-trigger replay24 pass; timer/write/window/freshness controls red then restored. Physical subscriber retained; logical no-op policy, all writers/cohorts, live stats, runtime cost and placement remain open. Not joined into #8898. |
| Five selected current-source queue gates PASS with five NON-VACUOUS controls. | Updated authority/subject gates plus bounded port, management and independent profile instruments. Each card's broader no-gate acceptance remains open. Current interface/write-contract amendments retain old captures while defining measured capabilities. [Current next work](../../docs/archive/tenancy/multitenant-delivery-roadmap-2026-11-02.md#accepted-contract-management-and-independent-profile-wave-2026-11-05) is backend/domain and error/HTTP composition, then proven consolidation and wider acceptance. |
| [Direct final-head bounded historical capture](../../reports/compat-rest-next-2026-11-05/README.md) accepted in its stated scope. | Parent re-audit reproduces aggregate byte-for-byte; actual final candidate repeated against this campaign's fresh release/dev repeats, dependency provenance and mutation controls. Prior unverified driver prose corrected, old pins/aggregate preserved. Omitted families and historical residuals remain explicit; no transitive old-release-to-PG claim. |
| Final CRM prchecks OK; both source trees clean and local/unpushed. | Published PRs remain #8898 ded254b9 and #8891 744d1968; fresh remote CI is required after maintainer publication. Local `externals/work/HANDOFF-rest-next-20261105.md` indexes lane artifacts, controls, heads and copy/paste commands. No new RC scope, role enablement, milestone promotion, upstream comment/dismissal or SQLite dispatch. |
| Current QMS and progress visualizations validated. | Queue validation/generation/check, links, five bounded gate/control pairs, graph schema, diff checks and site-check pass. Render source `e3f913ba39dfa07c941def9ecf6b38dc2d8531a2` is recorded in pages.yaml. Headless map interaction verifies R42 versus independent R43, new contract/composition/frame nodes and remaining blocked/planned boundaries with no page errors. No new application result is implied by rendering. |

### Update: next bounded REST, storage-contract and profile lanes dispatched (2026-11-05)

| Work / state | Basis and boundary |
|---|---|
| Continued from R41 `94c57f1f` and architecture-plan main `fc8c4010e`. | Fresh remote read-back: #8898 OPEN/draft ded254b9; #8891 OPEN/draft 744d1968; dev 4a482627. Existing R41 remains local/unpushed, not superseded acceptance. Selected integration gates MT-CONFIG-MIN/T30-WIRING PASS; full TEN-LAB and new contract/profile scopes UNMEASURED. |
| Three isolated bounded lanes dispatched. | [Architecture dispatch checkpoint](../../docs/30-design/tenancy/architecture-seams-execution-plan-2026-11-05.md#active-bounded-dispatch-checkpoint): Mongo/PG port-contract characterization, standalone subject-management HTTP factory and independent #8891 refresh/replay. Existing shared composition/error/migration files reserved; no consolidation or SQLite coding. No new application result, role enablement, milestone promotion or RC placement claim. |

### Update: subject administration and compatibility continuation accepted locally (2026-11-05)

| Work / state | Evidence and remaining gate |
|---|---|
| Local `codex/rest-integration-20261105` is clean at `94c57f1f37370215ef25b69691ef63918c876db3`; #8898 remains published at ded254b9. | [R41](../../docs/30-design/remedial/rc-16.0.0-integration-record.md#r41---subject-administration-and-cross-compatibility-on-94c57f1f-2026-11-05) accepts the joined dormant subject mutation/known-role service and strict mixed-version treatment/rename tests. Parent full nonbrowser6944/80pending/0failing, browser684, focused162, migration/HTTP30, affected authority/upgrade8 and archived subject gate13 pass; groups overlap. Parent semantic controls fail as intended; restored focused passes, changed-file lint/tier check and final prcheck pass. Nothing pushed to CRM, merged to dev or released. |
| New archived read-only subject instrument is wired under MT-CONFIG-MIN. | Queue integration PASS and control NON-VACUOUS measure only the bounded service. Separate management HTTP, owner ceilings, full role CRUD, remaining REST side effects/client binaries/import/resources and M0–M6 completion remain open. [Current next packets](../../docs/archive/tenancy/multitenant-delivery-roadmap-2026-11-02.md#accepted-subject-administration-and-compatibility-continuation-2026-11-05) supersede the delivered dispatch packets. |
| [Historical comparison](../../reports/compat-refresh-2026-11-05/README.md) completed at old-release/current-dev/published-PR-single pins. | Parent re-audited immutable results and negative controls. Repeated bounded corpus has no dev/PR-single semantic differences; release changes are separately described. Full-corpus projection residuals, omitted identity/settings families and the later R41 join are outside its pass scope; no transitive historical-to-PG parity claim. |
| Lane handoff recorded locally; no private artifacts staged. | `externals/work/HANDOFF-codex-rest-integration-20261105.md` links subject-admin, cross-compat and historical-compat handoffs, heads, commands, failed hypotheses and publication commands. Synthetic public aggregate has no raw document bodies or database addresses. CodeQL147/148 remain open; no reviewer reply or dismissal. |
| QMS/dashboard and rendered progress map validated. | `make queue-validate`, `make queue`, `make queue-check`, `make docs-links`, `make site-check` and diff checks pass. Plan source commit `e6f8ccea7af19bfc17edcba1f08e60658a2725ed` is recorded in pages.yaml; headless map interaction exposes R41/local acceptance, published R40 and remaining owner/milestone boundaries without page errors. Site publication follows the alignment main push. |

### Update: prioritized REST completion and parallel compatibility (2026-11-05)

| Work / state | Basis and next gate |
|---|---|
| Maintainer prioritizes subject administration and remaining REST/client acceptance, with parallel current and historical compatibility. | [Decision](decisions.md#rest-and-compatibility-priority-2026-11-05) and [bounded priority packets](../../docs/archive/tenancy/multitenant-delivery-roadmap-2026-11-02.md#prioritized-rest-and-compatibility-execution-2026-11-05). Fresh remote read-back remains OPEN/draft ded254b9 against dev 4a482627. Three lanes dispatched from that tree: persisted subject administration, mixed-version Mongo/PG differential tests, and repeated release/dev/PR-single write comparison. New lane acceptance is UNMEASURED at dispatch. |
| Existing M0–M6 dependencies remain; partial compatibility work proceeds while M3/M4 promotion prerequisites are open. | Root `make queue-status` measured ST-PG's selected unit PASS with integrations skipped; TEN-LAB/T30-WIRING UNMEASURED and old-seam T30-SCHEMA-CONFIG FAIL. No milestone, release-readiness or all-client claim follows. Intended RC changes and existing quirks require explicit expected-result bases, never blanket normalization. |
| Hypothetical celld/SQLite seam review remains read-derived and outside implementation scope. | [Architecture assessment](../../docs/30-design/tenancy/single-and-multitenant-architecture.md#hypothetical-third-backend-smell-test) identifies shared handlers/write rules and trusted ports, PG adapter/error-helper duplication and backend-specific isolation/control-plane obligations. No third-backend experiment or adoption. |

### Update: architecture seams and #8891 lanes planned (2026-11-05)

| Work / state | Basis and boundary |
|---|---|
| Maintainer prioritized seam improvements and integration of existing #8891; SQLite/celld experiments deferred at low priority. | [Execution plan](../../docs/30-design/tenancy/architecture-seams-execution-plan-2026-11-05.md) and additive queue cards define contracts/composition first, measured consolidation and refreshed single/nonresident profile next, shared frames then M5 recovery. Active REST/admin/compatibility work continues; coordinator informed through the existing chat. No implementation dispatched by this planning change. |
| Read-derived source review anchors published #8898 `ded254b9` and #8891 `744d1968`; planning incorporates local R41 continuation `94c57f1f`. | Fresh GitHub metadata reports both PRs OPEN/draft; the plan links R41 without recapturing its measurements. New architecture/profile acceptance remains UNMEASURED. No operator-visible change, new RC tag gate, candidate admission, milestone promotion or production role enablement. Lane detail: `externals/work/HANDOFF-architecture-seams-2026-11-05.md` (local). |
| Planning validation: queue schema/fidelity, generation, queue-check, docs-links and whitespace checks pass. | Selected new cards plus MT-RUNTIME-PLAN report UNMEASURED, with explicit no-gate acceptance/control requirements. Application suites, new controls and site-check were not run: no application, runnable gate or rich-page source changed. Initial worktree validation lacked the ignored external fixtures; local read-only fixture links restored them. Initial link checks hit sandbox `spawnSync git EPERM`; the authorized rerun passed. |

### Update: published visualization and PR CodeQL audit (2026-11-04)

| Work / state | Basis and boundary |
|---|---|
| Alignment architecture/visualization changes published on main `cdc5ade5e14fd06d3e60194243575652c9033264`; CI run 41960570913 succeeded. | Read-derived gh-pages read-back: build commit `8d5d98d56a703edb6d494bb41bcbca8baacfee63` names that source and build time `2026-11-05T03:18:41Z`. No application release or milestone promotion. |
| Reviewed current PR CodeQL comments and merge-ref alerts. | [The bounded audit and proposed follow-up](../../docs/archive/tenancy/multitenant-delivery-roadmap-2026-11-02.md#published-rest-checkpoint-codeql-review-2026-11-04) records open production alerts 147 and 148, inherited compatibility constraints, and proposed tenant referrer-header parity. No application patch, dismissal, comment or risk acceptance was performed. Isolated status checks pass 8; the initial mixed boot-fixture invocation fails as recorded there. |
| Audit document checks pass: `make queue-check`, `make docs-links`, `git diff --check`. | Initial sandbox execution prevented the link gate spawning git (`EPERM`); the authorized rerun passes. No rich-page source or generated view changed in this audit, so no new site-build or full application-suite result is claimed. |

### Update: multitenant progress and architecture visualizations reconciled (2026-11-04)

| Work / state | Basis and boundary |
|---|---|
| Maintainer requested current progress visualizations and a single-versus-multitenant architecture/compatibility explanation. | The generated delivery dashboard already carried R40; the interactive next-gen overview still carried the older a19b549c baseline. Its source plan/data are reconciled with published `ded254b9`, the CLI namespace amendment and remaining acceptance. Component progress is distinct from M0–M6 promotion; blocked prerequisite markers retain accepted partial slices. |
| Added [architecture and compatibility diagrams](../../docs/30-design/tenancy/single-and-multitenant-architecture.md). | Read-derived source audit confirms shared single-serving code changed while default Mongo paths were retained. R40 and the separate historical 15.0.9 comparison retain their recorded reproduction provenance; no new application/compatibility campaign was run for this explanation. Full parity, client binary execution and operational gaps remain explicit. |
| Visualization validation: source graph/reference checks, pinned Mermaid parsing and headless-browser interaction/rendering pass. | The page is rendered from plan source commit `a9413e21707fd13f0bdd242af78c7c2dabbbb243`; `pages.yaml` records that provenance. All three architecture diagrams render; map selections expose R40, current blocked gates and provider/configuration work. No new application or historical compatibility result is implied. |
| Published preview [CI](https://github.com/nightscout/cgm-remote-monitor/actions/runs/41956417437) and [CodeQL](https://github.com/nightscout/cgm-remote-monitor/actions/runs/41956417396) both succeeded on `ded254b9`. | Read-derived fresh workflow read-back. This does not enable every opt-in lab or promote a milestone. Selected queue audit still reports T30-SCHEMA-CONFIG's old-seam D15 table predicate FAIL and broader skipped cards UNMEASURED; these are distinguished from accepted new-tree preview evidence. |

### Update: CRM REST continuation published for draft review (2026-11-04)

| Work / state | Evidence and remaining acceptance |
|---|---|
| Maintainer published `ded254b9acf5a94e3a4fd99c85b23e1413fa08b6` to existing [#8898](https://github.com/nightscout/cgm-remote-monitor/pull/8898), still OPEN/draft against dev `4a482627bfdafb1fef8dcbe0ac6c484811cae563`. | Read-derived live PR read-back confirms the tested R40 head, title “Add explicit multitenant REST API preview” and matching prepared description. The continuation is published, not merged to dev or released. R40 remains the immutable local acceptance record; no application tests were rerun for publication bookkeeping. |
| Current-head [CodeQL](https://github.com/nightscout/cgm-remote-monitor/actions/runs/41956417396) succeeded; [CI](https://github.com/nightscout/cgm-remote-monitor/actions/runs/41956417437) remains in progress at read-back. | No completed remote CI result is claimed yet. Full REST administration/side effects, client binary execution, import/resource and production lifecycle criteria remain open; no M0–M6 promotion. Next engineering remains the bounded subject-mutation/known-role assignment packet in the delivery roadmap. |

### Update: alignment records published; CRM continuation awaits publication (2026-11-04)

| Work / state | Evidence and next action |
|---|---|
| Maintainer explicitly authorized merging the REST/QMS continuation to alignment main and pushing main. | Reproduced: main fast-forwarded from `969dbc74ed8a050f80590732be35801073b9a494` to `3f003441c75ae2d4284454f90c94c023e104c899`; GitHub accepted the normal push and local main/origin-main read back at that commit. Queue-check, docs-links and site-check pass on the merged tree. The two pre-existing untracked tenancy drafts remain untouched. |
| CRM `ded254b9acf5a94e3a4fd99c85b23e1413fa08b6` remains local; no CRM push or remote PR edit was performed. | Publish the exact tested commit to existing `workspace/multitenant-20261102`, then update draft #8898 with [the prepared description](../../reports/pr8898-rest-update.draft.md). R40 owns its acceptance figures. Fresh remote CI/CodeQL must cover the continuation before upstream readiness is claimed. |

### Update: derived reads and pinned-pattern integration (2026-11-04)

| Work / state | Evidence and next acceptance |
|---|---|
| Local `codex/rest-integration-20261104` at `ded254b9acf5a94e3a4fd99c85b23e1413fa08b6` joins derived reads, pinned client patterns and independent authority probes. | [R40](../../docs/30-design/remedial/rc-16.0.0-integration-record.md#r40---derived-rest-and-pinned-pattern-cumulative-acceptance-on-ded254b9-2026-11-04) owns parent-reproduced full/browser/focused/migration and semantic control figures. Actual CLI/PG/Vault composition includes derived reads, current revocation, two tenants and restart. Extracted client replay is not client binary execution. |
| Added a read-only archived authority queue instrument with registered controls and reusable owned-service acceptance runner. | `T30-WIRING` has a bounded integration PASS and NON-VACUOUS control; its complete production-runtime no-gate remains. Parent corrected an inherited process summary-exclusion assertion after retaining its failing campaign, and strengthened response-ID consumption. Milestone claims remain unchanged. |
| Reproduced QMS validation passes: queue validation/generation, queue-check, docs-links and site-check. | Selected archived authority integration and NON-VACUOUS controls pass separately. App final prcheck reports OK and contains refreshed official/dev; owned service cleanup is complete. QMS commit remains local for maintainer review. |
| Local/unpushed continuation of existing OPEN/draft #8898; published head remains `ae471ac7`. | [Draft description update](../../reports/pr8898-rest-update.draft.md) and [draft QMS PR body](../../reports/rest-qms-update.draft.md) are prepared, not sent. Main's pre-existing draft files are untouched. Only the maintainer publishes; fresh remote checks must cover a subsequent CRM head. No candidate merge, production lifecycle or operator release-note change. Local handoff: `externals/work/HANDOFF-codex-rest-integration-20261104.md`. |

### Update: published REST head and continuation lanes (2026-11-04)

| Work / state | Evidence and next acceptance |
|---|---|
| Live #8898 is OPEN/draft at `ae471ac790455d6e81781f31b505e3c7b838831b`; it is not merged to `official/dev` or released. | Read-derived live GitHub metadata; this is the R39 accepted cumulative implementation. Prior local-only publication observations below retain their capture-time meaning. Current-head CI and CodeQL succeeded; default CI is not every opt-in provider campaign. |
| Maintainer authorized derived reads, pinned-client replay and independent authority review in parallel, coordinated by isolated integration/QMS lanes. | [Lane ownership and acceptance](../../docs/archive/tenancy/multitenant-delivery-roadmap-2026-11-02.md#rest-continuation-and-qms-reconciliation-2026-11-04). New delivery results are UNMEASURED; already incorporated domain/cherry histories must not be applied twice. No operator-visible default, candidate or milestone change. |
| Reproduced targeted queue status: ST-PG unit gate passes; remaining selected configuration/secrets/runner/resolution/wiring/lab cards are UNMEASURED. | Command: `python3 tools/queue/status.py --id ST-PG --id MT-CONFIG-MIN --id MT-SECRETS-CONTRACT --id MIG-RUNNER --id TEN-RESOLVE --id T30-WIRING --id TEN-LAB`. Integration gates skipped explicitly. Update bounded instruments and evidence without claiming full M1/M2 or M3 promotion. |

### Update: selected REST domains joined; publication checkpoint (2026-11-04)

| Work / state | Evidence and delivery boundary |
|---|---|
| Clean local `workspace/rest-shared-20261104` at `ae471ac790455d6e81781f31b505e3c7b838831b` joins all five implementation lanes. | [R39](../../docs/30-design/remedial/rc-16.0.0-integration-record.md#r39---explicitly-selected-rest-domains-on-ae471ac7-2026-11-04): reproduced actual legacy v1/inherited-v2 data handlers, six API3 collections, safe context/status/discovery and current authority through explicit tenant-domain composition. Default remains entries-only; broader selection requires prepared namespaces and explicit configuration. |
| Cumulative nonbrowser6909/80pending, browser684, focused121, migration23, executable7; four semantic red controls restored green; final prcheck OK. | Parent inspected the committed head and persisted agent measurements. Pending labs and remaining REST rows are incomplete, not programme readiness. Properties/ddata/summary, administration, notifications/assistants, complete route/client replay and operational/realtime work remain. No shipping candidate or operator release-note change. |
| Maintainer requested alignment main consolidation and publication commands for the existing CRM draft. | Alignment records are prepared for main fast-forward. CRM `ae471ac7` descends from the current published `c527fb7e`; use a non-force push to existing `workspace/multitenant-20261102`, updating nightscout/cgm-remote-monitor#8898 rather than opening another PR. Agents do not push. Fresh remote CI/CodeQL and PR-description refresh remain required after maintainer publication. |

### Update: full REST implementation wave dispatched (2026-11-04)

The maintainer requested continued implementation toward a full headless
v1-v3 REST preview. Five code-and-test lanes start from accepted `21145d0d`;
the [REST delivery plan](../../docs/30-design/tenancy/multitenant-rest-api-delivery-plan-2026-11-04.md)
defines their actual route families and compatibility exits. These are active
implementation assignments, not accepted capabilities or new milestone claims.

| Owned branch / package | Deliverable and integration boundary |
|---|---|
| `workspace/rest-shared-20261104` — shared seams and legacy entries | Own shared storage/intent/query injection, version-aware admission, runtime composition, test registrations and actual v1/inherited-v2 entries/helpers. Publish a clean minimal domain-port seam early so independent domains can consume it without shared-file contention. |
| `workspace/rest-treatments-20261104` — treatments | Domain schema/adapter and actual legacy/v3 handlers, preserving same-time records, units, retries and batch outcomes; cross-version HTTP differentials and isolation/current-authority controls. |
| `workspace/rest-device-20261104` — devicestatus/activity | Domain schemas/adapters and existing legacy methods plus v3 devicestatus; no invented v3 activity or legacy devicestatus PUT. Preserve prediction extensions, identity/date rules and latest-read semantics. |
| `workspace/rest-profile-food-20261104` — profile/food | Domain schemas/adapters and actual routes across versions, retaining current-profile ordering/pruning, nested data and quickpick behavior. No owner-configuration conflation. |
| `workspace/rest-context-20261104` — safe context/identity/settings | Version-aware credential extraction coordinated with shared admission, safe status/discovery, settings documents and tenant-local snapshot ports. Derived routes require completed domain reads before admission; no process-global context or secrets exposure. |

Each lane owns implementation, focused real-PG/Mongo HTTP comparisons and
semantic red controls together; cumulative runtime/provider/full/browser/client
acceptance follows clean joins. New results remain UNMEASURED until run.
Subject/role administration and notification/assistant side effects remain
explicit unfinished full-REST work requiring their persisted authority/receipt/
runtime contracts; initial exclusion is not completion. No production trust,
owner/operator role, migration-on-start, global PG backend enablement, push or
change to the shipping 16.0.0 candidate is authorized by this dispatch.

### Update: executable entries CRUD cumulative acceptance (2026-11-04)

| Work / state | Evidence and delivery boundary |
|---|---|
| Local cumulative `workspace/runnable-crud-20261104` at `21145d0d3b396b744618d2e8158bc1b969f8dd0a` joins runnable API, entries CRUD and credential-fidelity histories. | [R38](../../docs/30-design/remedial/rc-16.0.0-integration-record.md#r38---executable-entries-crud-cumulative-acceptance-on-21145d0d-2026-11-04): reproduced full CRUD/history through the actual CLI with real Vault/PG, overlapping two-tenant identifiers, current grants/names, rollback controls and restart persistence. The stale inherited route expectations are corrected; unsupported-route checks remain. |
| Combined acceptance: focused83; executable5; nonbrowser6834/80pending; browser684; affected3489/20pending; final prcheck OK. | Measurements are on the joined head with all three relevant HTTP/process opt-ins enabled; pending labs are not passes and totals overlap. Parent inspected committed changes and persisted logs. Entries-only executable preview is accepted, not all REST, production readiness or M1-M6 completion. |
| Unpublished; no change to shipping candidate or operator release notes. | PR nightscout/cgm-remote-monitor#8898 remains OPEN/draft at `c527fb7e`; `official/dev` remains `4a482627`. Next implementation follows shared seams and domain packages in the [REST delivery plan](../../docs/30-design/tenancy/multitenant-rest-api-delivery-plan-2026-11-04.md); incomplete import/lifecycle/realtime work remains separate. Local reproduction: `externals/work/HANDOFF-runnable-crud-20261104.md`. |

### Update: runnable CLI and entries CRUD implemented (2026-11-04)

| Work / state | Evidence and delivery boundary |
|---|---|
| Runnable explicit `nightscout multitenant api`: local `workspace/runnable-multitenant-20261104` at `93c90520124ff4912d49d37e933ebfe4a5708075`. | [R37](../../docs/30-design/remedial/rc-16.0.0-integration-record.md#r37---runnable-api-and-entries-crud-delivery-lanes-2026-11-04): reproduced actual CLI child-process acceptance with PG/RLS and real Vault, explicit credential-reference configuration, read-only startup checks, isolation/current authority, restart and owned shutdown. No single/Mongo boot or API_SECRET dependency in the multitenant process. Only API preview is enabled, not owner/operator or other roles. |
| API3 entries CRUD/history: local `workspace/entries-crud-20261104` at `f57138f24d90eec0ff78e5bf2aba5edc46c7c165`. | R37 records actual PUT/PATCH/DELETE/history implementation and lane campaigns, including the separately measured **three failing stale inherited route expectations**. The parent-owned cumulative join will update these after retaining the credential-fidelity test history; independent green suites are not cumulative acceptance. |
| Runnable CRUD integration dispatched to new owned `workspace/runnable-crud-20261104`. | Join both implementation histories and fidelity `9e97d073`, prove full CRUD/history through the actual executable with real providers, then run combined regression/browser/control checks. This join remains UNMEASURED. PR nightscout/cgm-remote-monitor#8898 remains draft at `c527fb7e`; candidate `official/dev` remains `4a482627`. No push, merge, all-REST claim or programme milestone promotion; no change to shipping operator release notes. |

### Update: full REST delivery design integrated (2026-11-04)

| Work / state | Evidence and delivery boundary |
|---|---|
| Source-grounded [REST v1-v3 delivery plan](../../docs/30-design/tenancy/multitenant-rest-api-delivery-plan-2026-11-04.md) committed as `34812ac028e47e9afaa6648c1a516f50b6241d4a` and integrated into records. | Read-derived from CRM `c527fb7e`: actual mounted route families, inherited v1 surface under v2, API3 collections/specials and conditional integrations. Shared tenant service/storage ports retain version-specific parsing, credentials, query, batch/retry and response semantics. No application verification or new REST capability is asserted by this design; documentation/source-reference checks pass. |
| Implementation packages have shared-file ownership and collection/domain boundaries across versions, with actual HTTP/client differentials and source controls as exits. | Active runnable CLI and API3 entries CRUD continue independently. Follow-on shared seams and domain adapters can develop in parallel; touching active shared files waits for accepted clean-head integration or explicit ownership agreement. Management/notification/assistant exclusions remain incomplete until implemented or explicitly dispositioned, not proof of all-REST readiness. No new role enablement, push or candidate merge. |

### Update: implementation-first CLI and CRUD dispatch (2026-11-04)

| Work / state | Evidence and delivery boundary |
|---|---|
| Maintainer approved parallel full entries CRUD and runnable `nightscout multitenant api`, replacing interstitial packet chains with code/test/handoff deliverables. | Fresh lanes `workspace/entries-crud-20261104` and `workspace/runnable-multitenant-20261104` start at accepted `c527fb7e`. [Decisions](decisions.md#runnable-preview-and-parallel-crud-delivery-2026-11-04) approve POST-derived tenant CRUD attribution/refusal and explicit config/environment-bound preview API boot. New implementation/CLI acceptance is UNMEASURED; full-programme milestone criteria remain, but do not gate development of the bounded runtime on full CRUD/HA/registry/owner coverage. |
| Test-only operator-prepared fidelity committed locally as `9e97d07338108f3b338f754c3a3466c7da8d29a8`; clean and unpushed. | Agent-reproduced, parent handoff-read: credential HTTP33 passing; source-ID control expected200/got401 and missing-name control expected401/got200 go red; lint/syntax/whitespace/final prcheck pass. Full nonbrowser/browser are explicitly UNMEASURED; validate after joining the implementation lanes, not a separate readiness claim. No supported importer, idempotent multi-store rerun or atomic activation is asserted. |
| Fresh GitHub read observes draft #8898 now published at accepted cumulative `c527fb7e`; maintainer publication, not an agent push. | Its new remote CI/review is not yet asserted here. No new CRUD/runtime implementation has been published, no extra role enabled, and no CRM merge to the 16.0.0 candidate is implied. |

### Update: PATCH packet characterized; implementation remains scoped (2026-11-04)

| Work / state | Evidence and next decision boundary |
|---|---|
| Corrected PATCH characterization on accepted `c527fb7e` passes23; update-permission source control fails as predicted, then restored baseline passes23. No tracked production edits. | [R36](../../docs/30-design/remedial/rc-16.0.0-integration-record.md#r36---entries-patch-characterization-on-c527fb7e-2026-11-04) retains the original fixture-assumption failures and distinguishes actual Mongo reference success, tenant admission405 and PG primitive support. Current-name attribution and explicit unsupported-input status require review before PATCH implementation; preserve shipping read-then-write precondition semantics. No broad mutation-language, client or milestone acceptance. |

### Update: provisioning packet and PATCH characterization follow-up (2026-11-04)

| Work / state | Evidence and next decision boundary |
|---|---|
| Provisioning/runtime-identity packet completed on accepted `c527fb7e`, without tracked source changes. | [R35](../../docs/30-design/remedial/rc-16.0.0-integration-record.md#r35---provisioning-runtime-packet-on-c527fb7e-2026-11-04) records two existing checks, a stale-readiness source control and restored checks. Read-derived inventory finds schema migration CLI and component preparation seams, but no tenant/credential provisioning-import command or multi-store activation ledger. Test-only operator import-seam fidelity is delegated in `workspace/operator-import-fidelity-20261104`; implementation results remain UNMEASURED. Production importer input/rerun/activation policy remains separate. |
| PATCH packet stopped on fixture expectations, not production defects; fixture-only remeasurement authorized. | Allowed inert markup survives shipping purification, and the actual unaddressed API3 subapplication returns404. Correct those characterization assumptions, retain original red evidence and complete the update-permission source control before accepting the packet. No PATCH implementation, path-language broadening, atomic precondition guarantee or changed single/Mongo behavior is authorized. Attribution and representability policy remain explicit implementation decision boundaries. |

### Update: records consolidation and publication assessment (2026-11-04)

| Work / state | Evidence and remaining acceptance |
|---|---|
| Maintainer requested alignment records merged to main, updated todos/completion plan, and assessment of updating existing foundations PR #8898. | Queue notes and generated dashboard are brought through accepted cumulative `c527fb7e`; the [completion checkpoints](../../docs/archive/tenancy/multitenant-delivery-roadmap-2026-11-02.md#completion-checkpoints-and-publication-2026-11-04) define remaining method/import/resource, provisioning/trust/lifecycle, executable gate, client, realtime and operational exits. No M0-M6 promotion. PATCH and provisioning packets continue independently; their new results remain UNMEASURED until reported. |
| Read-derived publication assessment: current local CRM `c527fb7e0d309b7fc567861a41e8f3862e0922df` is a descendant of published PR head `81bc71e634c0c2e60ac4e86cfba2e063501c9192`; a normal fast-forward update of `workspace/multitenant-20261102` can carry the accepted work. | Reproduced git range: eight commits, 26 changed files; source/tests/docs include shared parser/intent seams, accepted search/POST, real-provider fixtures and canonical resolver. R34 carries exact-head local validation; published-head CI/CodeQL are green but do not cover the new head. Preserve draft status and await fresh remote CI/review after maintainer publication. Do not touch the original PR worktree's unrelated dirty dependency test or push a new branch/PR. |
| Alignment main fast-forward is authorized after validation; publication remains maintainer-operated. | Root main and origin/main were both `82826a22`; records branch descends from main. Two pre-existing untracked draft tenancy files remain untouched and must not be staged. No push, serving enablement, operator-visible default change or 16.0.0 candidate merge is performed by this consolidation. |

### Update: next entries and provisioning packets dispatched (2026-11-04)

| Work / state | Evidence and next decision boundary |
|---|---|
| Two independent packets dispatched from accepted cumulative `c527fb7e0d309b7fc567861a41e8f3862e0922df`: entries PATCH characterization in `workspace/entries-patch-packet-20261104`, and provisioning/runtime-identity inventory in `workspace/provisioning-runtime-packet-20261104`. | New packet results are UNMEASURED. The entries lane must establish the actual shipping PATCH contract, smallest tenant/PG gap, paired controls and a bounded implementation proposal. The runtime lane must distinguish existing operator migration/import seams from lab hand-seeding, propose the next provisioning/fidelity slice and name production identity/lifecycle decisions without selecting defaults. Both stop at packet stage; no production implementation follows automatically. |
| M1/M2 remain in progress; complete M3 and preview acceptance remain pending. | Preserve single/Mongo compatibility and separate owner/data/operator authority. No new authenticator, secret-recovery policy, resource bound, registry lifecycle or transport-trust assumption is authorized. No milestone promotion, operator-visible default change, role enablement or push. |

### Update: cumulative canonical/provider/POST acceptance (2026-11-04)

| Work / state | Evidence and remaining acceptance |
|---|---|
| Local cumulative `workspace/canonical-preview-20261104`, `c527fb7e0d309b7fc567861a41e8f3862e0922df`, preserves accepted canonical ingress `468c41dc` and provider/POST `4621d5c4`; clean and unpushed. | [R34](../../docs/30-design/remedial/rc-16.0.0-integration-record.md#r34---cumulative-canonical-provider-post-on-c527fb7e-2026-11-04): agent-reproduced, parent log-read evidence; enabled provider suites 63 passing/0 pending/0 failing, full nonbrowser 6815/80 pending/0 failing, separate browser 684/0/0, three composed source controls red; lint/tier/final prcheck pass. Actual canonical Host selection, disposable public-name rotation, real Vault exchange, PG/RLS POST/read across workers, conflicting selectors, foreign credentials and Host-only trust loss are measured together. |
| Bounded join accepted, not full preview or M1/M2/M3 completion. | Trust uses synthetic test-local loopback provenance; production ingress identity/transport, durable registry allocation/lifecycle/publication, remaining entries/history/import/resource acceptance, wider REST/pinned clients, durable realtime and operations remain open. No production enablement, operator-visible default change or push. Fresh upstream reads keep the 16.0.0 candidate at `official/dev` `4a482627` and foundations PR #8898 OPEN/draft at `81bc71e6`; upstream CI does not cover this local cumulative head. |

### Update: canonical ingress accepted locally; cumulative join dispatched (2026-11-04)

| Work / state | Evidence and next gate |
|---|---|
| Approved opt-in canonical ingress fixed locally on `workspace/canonical-ingress-20261104`, `468c41dcab391f827a5bd1d9a581af9de2f0e10b`; unpushed, not merged to `dev`. | [R33](../../docs/30-design/remedial/rc-16.0.0-integration-record.md#r33---canonical-ingress-on-468c41dc-2026-11-04): agent-reproduced, parent log-read evidence; focused resolver/app 25 passing/0 pending/0 failing, full nonbrowser 6815/73 pending/0 failing, separate browser 684/0/0, four source-ablation controls red; lint/tier/final prcheck pass. Default direct-alias behavior remains; canonical Host alone selects after fresh explicit transport trust, and forwarded public names cannot select or rescue an unknown internal name. No production trust adapter, registry or operator-visible default change. |
| Bounded cumulative join delegated in `workspace/canonical-preview-20261104`: accepted ingress `468c41dc` plus real-provider POST head `4621d5c4`. | Preserve both histories and extend only the existing runtime lab to measure canonical Host with real Vault exchange/PG POST, public-alias rotation, conflicting selectors, unknown canonical refusal and per-request trust loss. Combined-head behavior is UNMEASURED until enabled/full campaigns and composed negative controls pass. Static snapshots do not establish durable registry lifecycle or real production transport provenance. No M1/M2/M3 promotion, role enablement or push. |

### Update: real-provider POST composition accepted locally (2026-11-04)

| Work / state | Evidence and next gate |
|---|---|
| Test-only cumulative `workspace/preview-composition-20261104`, `4621d5c4c349f5b5798fa39873274b3dc02928ee`, preserves both accepted POST `6cad7a42` and runtime `e410b163` histories; clean and unpushed. | [R32](../../docs/30-design/remedial/rc-16.0.0-integration-record.md#r32---real-provider-post-composition-on-4621d5c4-2026-11-04): agent-reproduced, parent log-read evidence; enabled real-provider suites 62 passing/0 pending/0 failing, full nonbrowser 6807/79 pending/0 failing, separate browser 684/0/0, focused 78/0/0; three POST-specific source controls red; lint/tier/final prcheck pass. Actual Vault-authenticated POST/read/replacement, cross-worker current grants, tenant isolation and provider-outage no-write/recovery are measured. No production change or operator-visible default effect. |
| Canonical ingress is not included; no M1/M2/M3 promotion or role enablement. | Join clean accepted ingress after its independent acceptance, then validate the cumulative head. Production provider identity/TLS/HA, registry lifecycle, broader REST/pinned clients, durable realtime and operational preview remain open. Fresh upstream reads still show candidate `official/dev` `4a482627` and OPEN/draft foundations PR #8898 at `81bc71e6`; this local result is not upstream CI. |

### Update: bounded preview write-composition dispatch (2026-11-04)

| Work / state | Evidence and next gate |
|---|---|
| Independent test-only join dispatched: accepted POST `6cad7a42d804d6bb115c9d4eff55fe931b68a7cf` plus real-provider lab `e410b1637038c4a4e5f4675a340c4697398bbcba`, in new lane `workspace/preview-composition-20261104`. | Inputs rechecked clean; combined behavior is UNMEASURED. Extend the existing real Vault/PG lab through the approved trusted entries intent: actual POST/read across workers, same-identifier tenant isolation, replacement semantics, fresh create/update grants and provider-outage refusal without writes. Require explicit enabled campaigns, source-ablation controls and cumulative-head validation; inherited counts are not results for the join. Stop on a production/design mismatch rather than expand the test-only scope. |
| Approved canonical ingress implementation continues independently on POST base `6cad7a42`; its resolver/app-test surface is separate from the composition lab. | Parent joins clean accepted ingress and composition heads only after bounded acceptance. Neither lane enables roles, production listeners or real-data access; neither completes M1/M2/M3. No new release-candidate prerequisite or operator-visible default change. |

### Update: real-provider lab and canonical ingress approval (2026-11-04)

| Work / state | Evidence and next gate |
|---|---|
| Test-only runtime composition committed locally on `workspace/runtime-composition-20261104`, `e410b1637038c4a4e5f4675a340c4697398bbcba`, from search baseline `c10290d2`; clean, unpushed, not merged to `dev`. | [R30](../../docs/30-design/remedial/rc-16.0.0-integration-record.md#r30---real-provider-runtime-lab-on-e410b163-2026-11-04): agent-reproduced, parent log-read evidence; enabled focused 44 passing/0 pending/0 failing, full nonbrowser 6725 passing/132 pending/0 failing, separate browser 684/0/0, tenant-binding source control red, lint/tier/final prcheck pass. Actual HTTP reads/exchange compose real Vault Transit and PostgreSQL/RLS, current-authority revocation and provider outage/recovery. No production runtime/configuration change or operator-visible default effect. |
| Canonical ingress packet completed; maintainer approved rewritten Host plus explicit transport trust, with implementation delegated on accepted POST base `6cad7a42`. | [R31](../../docs/30-design/remedial/rc-16.0.0-integration-record.md#r31---canonical-ingress-packet-on-6cad7a42-2026-11-04) records the reproduced forwarded-alias precedence gap. The [decision](decisions.md#multitenant-ingress-and-post-continuation-2026-11-04) preserves direct aliases and makes internal mode opt-in with unconditional per-request trusted-peer checks; implementation acceptance remains UNMEASURED. Durable allocation/lifecycle, versioned registry publication and production transport provenance stay separate and open. |
| No preview milestone promoted; 16.0.0 candidate process remains separate. | Runtime lab does not include POST `6cad7a42`; join clean accepted runtime, POST and ingress slices and validate the combined head before claiming their integration. Wider REST/pinned clients, durable realtime and operational preview remain open. Fresh upstream reads: `official/dev` remains `4a482627bfdafb1fef8dcbe0ac6c484811cae563`; foundations PR #8898 remains OPEN/draft at `81bc71e634c0c2e60ac4e86cfba2e063501c9192`. No push or role enablement. |

### Update: bounded entries search (2026-11-04)

| Tree / work | Evidence and remaining acceptance |
|---|---|
| Local dormant `workspace/tenant-entries-search-20261104` at `c10290d2b804f86853ce3d92014baaf62d10a745`, extending R26's `81bc71e6`; includes `official/dev` `4a482627`, not merged to `dev`. | Read-derived agent-run [R27](../../docs/30-design/remedial/rc-16.0.0-integration-record.md#r27---dormant-tenant-entries-search-on-c10290d2-2026-11-04): live MongoDB/PG differential 8 passes, actual HTTP search 2 passes, affected 115 passing/16 pending/0 failing, full nonbrowser 6764 passing/88 pending/0 failing, browser 684/0/0. Three source controls fail as intended and are restored; lint/tier/prcheck pass. Supports bounded list/search through shipping handlers with current tenant authority; history/mutations, pinned-client replay, production runtime/provider/import and resource acceptance remain open. No operator-visible default change, role enablement or milestone promotion. |

### Update: preview dispatch and published checkpoint (2026-11-04)

| Work / state | Evidence and next gate |
|---|---|
| nightscout/cgm-remote-monitor#8898 is published at `81bc71e6`, open/draft; local `c10290d2` remains the accepted cumulative search head. | Read-derived current PR checks: tests/build/browsers pass; three new CodeQL fixture alerts were individually dismissed after source review, without exclusions or protocol changes. API read-back confirms dismissal and CodeQL/Tests pass SUCCESS. [Disposition](../../docs/archive/tenancy/multitenant-delivery-roadmap-2026-11-02.md#published-exchange-checkpoint-codeql-disposition-2026-11-04) distinguishes dismissal from a new scan. No merge to dev or release acceptance follows. |
| [Fresh-context M1-M6 preview packets](../../docs/archive/tenancy/multitenant-delivery-roadmap-2026-11-02.md#preview-dispatch-packets-m1-m6-2026-11-04) scope the next six milestones; M0 acceptance remains required within the foundations. | Two isolated agents prepare entries mutation and real-provider/runtime packets from `c10290d2`, stopping before implementation approval. Coordinator owns records/joins/decisions. Later integration, pinned-client, realtime and operational packets are staged behind their acceptance inputs, not dispatched as six competing implementations. Current selected queue measurement: ST-PG unit gate passes; seven other items unmeasured, integration gates skipped. |
| T30-WIRING claim corrected to in-progress; dashboard refreshed through R27. | R25-R27 measure partial credential/exchange/current-authority HTTP implementation, not full production runtime acceptance. M1/M2 criteria remain incomplete; M3/M4/M6 remain dependency-constrained. No milestone promotion, new operator-visible default, OIDC prerequisite or serving-role enablement. |

### Update: dormant entries POST implementation (2026-11-04)

| Work / state | Evidence and next gate |
|---|---|
| Actual tenant entries POST/create/resend fixed locally on `workspace/entries-mutations-20261104`, `6cad7a42d804d6bb115c9d4eff55fe931b68a7cf`; unpushed, not merged/released. | [R29](../../docs/30-design/remedial/rc-16.0.0-integration-record.md#r29---dormant-tenant-entries-post-on-6cad7a42-2026-11-04): agent-reproduced, parent log-read evidence; nonbrowser 6807 passing/73 pending/0 failing, separate browser684, focused78, six source controls red as intended, lint/tier/final prcheck pass. Preserves fresh branch-specific authority, current attribution, parser/purifier, tenant-local configured pruning and Mongo defaults; repairs legitimate hyphen/Unicode extension-key compatibility. |
| Preview acceptance remains incomplete; no operator-visible default change. | Independent real-provider lab is not included in this tree. Combine accepted slices and rerun combined-head validation before claiming runtime/POST integration. Pinned-client/wider REST, durable notifications/recovery and operations acceptance remain separate gates; no milestone promoted. Published foundations PR remains `81bc71e6`, `official/dev` remains `4a482627`. |

### Update: ingress boundary and POST admission (2026-11-04)

| Work / state | Evidence and next gate |
|---|---|
| Durable DNS-friendly internal tenant name is distinct from optional disposable public aliases and stable tenant ID. | Maintainer adopted a provider-neutral authoritative mapping and explicit trusted internal-ingress mode, preserving direct aliases and vendor-private routing. Current resolver's forwarded-alias precedence does not yet implement that mode; the [measured gap and next packet](../../docs/archive/tenancy/multitenant-delivery-roadmap-2026-11-02.md#canonical-internal-hostname-boundary-2026-11-04) are recorded. No production trust, durable registry or Consul integration is asserted. |
| Entries POST packet approved; implementation runs separately from the real-provider composition lab. | [R28](../../docs/30-design/remedial/rc-16.0.0-integration-record.md#r28---entries-post-contract-characterization-on-c10290d2-2026-11-04) records 34 selected characterization passes and a separate four-pass/one-intended-failure POST gap campaign. Decisions select 401 for missing current subject attribution, input-only 400, recognized outages 503 and other internal failures 500; single remains unchanged. Actual PG POST, configured pruning, source controls and full validation remain pending. Registration/schema negotiation can assist future fields but is not implemented or a new prerequisite for legacy clients. No operator-visible default change or milestone promotion. |

### Update: bounded authority lane handoff (2026-11-03)

| Tree / work | Evidence and remaining acceptance |
|---|---|
| Dormant exchange/GET `workspace/tenant-exchange-20261103` at `81bc71e634c0c2e60ac4e86cfba2e063501c9192`, clean and unpushed; not merged to `dev`. | Read-derived agent-run [R26](../../docs/30-design/remedial/rc-16.0.0-integration-record.md#r26---dormant-tenant-exchange-to-get-on-81bc71e6-2026-11-03): focused 85/0/0, nonbrowser 6725 passing/124 pending/0 failing, browser 684/0/0; lint/tier/prcheck and four source controls pass. Preserves measured exchange fields/canonicalization with current name/grants and approved eight-hour policy. Client pins were inspected, not replayed; broader client compatibility, production import/provider/listeners and full REST remain unmeasured. No operator-visible default change or role enablement. |
| `workspace/authority-next-20261103` at `ad0cbdac058789bd806ae49047c7f95a6670332c`, isolated and unpushed; not merged to `dev`. Read-only tenant-scoped PostgreSQL/RLS Shiro authority candidate, preserving anonymous access modes. | Read-derived agent-executed evidence: 26 focused passes, zero pending/failing; current-grant and RLS controls; actual idle database termination leaves the worker alive and its next authorization unavailable. Lint/tier checks pass. See the [authority slice handoff](../../docs/archive/tenancy/multitenant-delivery-roadmap-2026-11-02.md#p2-authority-slice-handoff-2026-11-03) for commands and limits. No coordinator replay, full-suite pass, production verifier/HTTP wiring, in-flight outage acceptance or role enablement; no operator-visible change. |
| `workspace/entries-next-20261103` at `cabb5eecb5a15ee9050f8894299a78ae300ae731`, isolated and unpushed; not merged to `dev`. Dotted inclusion projection for dormant PostgreSQL entries reads. | Read-derived agent-executed evidence: 50 focused PG/Mongo/API3 passes, including nested arrays, missing paths and conditional responses; refusal and array-recursion mutations fail as expected. Lint/tier checks pass. See the [entries slice handoff](../../docs/archive/tenancy/multitenant-delivery-roadmap-2026-11-02.md#p2-entries-projection-slice-handoff-2026-11-03). Full-suite, combined integration and broader REST acceptance remain UNMEASURED; no operator-visible default change or PR-ready claim. |
| Combined `workspace/p2-integration-20261103` at `8b193e187fecaa93b41b5f3ced786a80d3e219f0`, clean and unpushed; includes both bounded slices and current `official/dev` `4a482627`. | Read-derived agent-run [R24](../../docs/30-design/remedial/rc-16.0.0-integration-record.md#r24---combined-p2-dormant-slices-on-8b193e18-2026-11-03): nonbrowser 6713 passing/108 pending/0 failing, browser 684/0/0, explicit PG/HTTP/Vault campaigns and final prcheck pass. Mongo migration opt-in skipped; production verifier, HTTP/listener wiring and provisioning remain UNMEASURED. Not merged to the candidate, no role enablement or full multitenant acceptance. |
| Credential/entries GET continuation `workspace/tenant-auth-http-20261103` at `7eb76c713ace783dc24f412f1242678f1fd23770`, clean and unpushed; extends tested `8b193e18`, not merged to `dev`. | Read-derived agent-run [R25](../../docs/30-design/remedial/rc-16.0.0-integration-record.md#r25---tenant-credentialcurrent-authority-get-on-7eb76c71-2026-11-03): enabled focused 72/0/0, nonbrowser 6718 passing/118 pending/0 failing, browser 684/0/0; lint/tier/prcheck and source controls pass. Actual GET uses verified legacy credential identity and persisted current authority in an explicit synthetic-provider lab; real Vault verification is separately measured. Exchange/client cohorts, wider REST, production provisioning/provider identity/listeners remain unmeasured. No default single behavior change, role enablement or broad compatibility acceptance. |

**2026-11-01 release-preparation follow-up:** the dated
[RC readiness triage](../../docs/10-domain/nightscout-rc-readiness-2026-11-01.md)
records current CI/staging blockers, candidate PR dispositions, issue follow-up
and isolated fix preparation. Historical measurements below keep their original
commit labels; this follow-up does not declare a named RC.

**Current acceptance roadmap (2026-11-01):** scheduled backend storage/identity
integration, dependency modernization and the opt-in modern theme are merged;
do not read historical in-flight tables below as the current merge queue.
The [current scope and hosted test totals](../../docs/10-domain/nightscout-rc-readiness-2026-11-01.md#current-test-totals-and-release-scope)
record 6,323 passing / 3 pending top-level tests, plus separate client-core,
browser and Connect suites (7,660 passing / 3 pending when each suite is counted
once; not a cross-suite identity census). Remaining work is private security
integration and final-tree checks, live alerts, cohort/soak and rollback evidence,
release notes and staging acceptance. Optional draft proposals are not
automatically release blockers.

**Status: in development. Nothing tagged or released.** 16.0.0 is the next release from `dev`
(maintainer, 2026-10-21; queue `RT-VERSION`). Contributor-facing; full technical depth intended.
Measured 2026-10-26 (to 19:10Z) against `official/dev` `47723cda` (the merge of #8605, cut 5) and
`official/master` `c6a0d8ed` (= `v15.0.9`, the shipping release), in
`externals/cgm-remote-monitor-official` after `git fetch official`, with `gh pr view`, `gh run view` and
`gh api` for PR, CI and branch-protection state. Updated at 22:13Z for `dev` `7ad3a67f` (#8854 `c08cbe03`,
then #8084), and on 2026-10-27 for `dev` `8dbb60c2` (#8860): the Identity rows for `dev`, the merge list,
#8854, #8860, the in-flight rows and the CI on `8dbb60c2`; the other figures are still those of `47723cda`.
Updated on 2026-10-28 for `dev` `e1f7ac41` (#8873), and on 2026-10-30 for `dev` `991b0654` (#8865, 02:04:14Z):
the Identity rows for `dev`, the merge list (#8877, #8878, #8865), the in-flight rows for the 16.0.0 scope
the maintainer set on 2026-10-30, Known defects (BF-209, BF-211, BF-212) and the open items; read with
`gh pr view`, `gh run list --commit` and `gh api` at about 02:30Z, and counted in
`externals/cgm-remote-monitor-official` after `git fetch official`. Updated on 2026-10-31 for `dev` `368e6c23`
(#8874, 02:02:52Z): the merge state, the in-flight update below the handoff table, Known defects (BF-215,
BF-216, BF-219 to BF-222) and the testing pointer to R18; read with `gh pr list`, `gh pr checks` and
`gh api .../compare` at about 05:45Z. Updated 2026-11-01 for `dev` `61eb3733` after #8895/#8896 merged;
current callback/CI and identity status is in the rows below.
The fresh write-compatibility result and release-readiness assessment are in the
[compatibility report](../../site/pages/cgm-remote-monitor-16.0.0-write-compatibility.html) and
[release colophon](../../site/pages/cgm-remote-monitor-16.0.0-colophon.html). Other release counts
remain tied to their recorded historical commits.

> Complements the generated changelog. The changelog is authoritative for *what merged*; this file
> records what the release is made of so far, how each figure was measured, and what is unsettled.

BF-72, BF-161 and BF-191 appear by mechanism only: all three are live on 15.0.9, and this repository is public.
The decisions that shape the release are in [decisions.md](decisions.md); the test runs are in the
[16.0.0 integration record](../../docs/30-design/remedial/rc-16.0.0-integration-record.md); the call
for collecting current cohort evidence is [testing-notes.md](testing-notes.md);
a formal named-RC announcement is not yet issued.

## Identity

| | |
|---|---|
| Product | `cgm-remote-monitor` |
| Directory name | `cgm-remote-monitor-16.0.0`; the number is decided (maintainer, 2026-10-21) |
| Tag to be cut | `v16.0.0` and `16.0.0`, both forms, as for `15.0.7` to `15.0.9` |
| Merged part | `official/master..official/dev` |
| Base (shipping) | `c6a0d8ed` = `v15.0.9` (released 2026-10-21) |
| `dev` head | `61eb37335954ae42c91345a0823bd67331025165` (#8896, 2026-11-01 17:52:18Z), after #8895 `bb85d10f` (17:45:01Z) and #8894 `497d08c9` (16:28:25Z). Earlier measured history remains in the dated rows below. |
| CI on current `dev` | Both CI runs 41333672054 / 41333677576 and CodeQL runs 41333672065 / 41333677478 passed on `61eb3733`. The push run published amd64/arm64 development images to `dev_61eb37335954ae42c91345a0823bd67331025165` and `latest_dev`; release-image publication was skipped. No named RC or live acceptance is implied. |
| `dev` head on 2026-10-27 | `eed31dca` (merge of #8856, 2026-10-27 20:09:35Z, by bewest), tree `584623cf`; the merges before it that day: #8868 `88676086` (20:01:50Z), #8859 `94899828` (19:52:21Z), #8866 `b84871d7` (19:42:55Z), #8864 `2dc0c1bc` (16:55:01Z, AndyLow91) and #8860 `8dbb60c2` (00:07:13Z, AndyLow91) |
| Commits on `dev` | 1,145 at `f54941b5` (675 without merges) — `git rev-list --count official/master..official/dev`, `--no-merges`; 999 at `991b0654` (576 without merges), 921 at `eed31dca` |
| First-parent commits on `dev` | 66 at `f54941b5` — `git rev-list --first-parent --count official/master..official/dev`; 54 at `991b0654`, 43 at `eed31dca` |
| Diff on `dev` | 1,031 files, +168260/−20081 at `f54941b5` — `git diff --shortstat official/master official/dev`; 947 files, +144414/−18833 at `991b0654`; 871 files, +131070/−15204 at `eed31dca` |
| Merged on 2026-10-26 | 17 PRs, from `b29f1bf7` to `7ad3a67f`: 611 files, +86276/−3996 — `git diff --shortstat b29f1bf7 official/dev`; the thirteen after `207a8352`: `git rev-list --first-parent --count 207a8352..official/dev` = 13 |
| `package.json` version | `16.0.0` — `git show official/dev:package.json \| grep '"version"'` |
| `engines.node` | `^22.23.4 \|\| ^24.22.1 \|\| >=26.12.1` (AndyLow91's `6a146a4c`, "require Node Brotli security patches"; supersedes the decided `^22.12 \|\| >=24`) |
| Docker base image | `node:24.22.1-alpine` for builder and runtime (`32489dc5`); the runtime stage deletes the image's global `npm` and `npx` (`Dockerfile` on `dev`) |
| Connector pin | `nightscout-connect` exactly `0.1.0`, as in 15.0.9 (`git show official/dev:package.json`) |
| MongoDB | driver `mongodb` `^7.6.0` (cut 3); the README states 5.0 through 8.0 as supported and 4.4 and earlier as unsupported (`README.md:157-158` on `dev`); driver 7 starts on 4.4 and refuses 3.6, 4.0 and 4.2, which get the boot error page (BF-182; decisions). Docker Compose starts `mongo:6.0.27` (`docker-compose.yml:12`; 15.0.9: `mongo:5.0.32`) |
| Web framework | `express` `^5.2.1`, `helmet` `^8.3.0` (cut 5; `package.json` on `dev`); 15.0.9 locks `express` 4.22.2 |
| Staging PR, 2026-10-30 | #8824: open, head `991b0654` (`MERGEABLE`, `BLOCKED`, `REVIEW_REQUIRED`, read 2026-10-30 about 02:30Z). `master`'s protection is unchanged: required checks `Run Tests (22, 6)`, `Run Tests (22, 4.4)` and `Run Tests (24, 6)` and one approving review (`gh api repos/nightscout/cgm-remote-monitor/branches/master/protection`), so #8824 still cannot meet it; the decided change to require only *Tests pass* is still owed ([Open items](#open-items-a-releaser-must-settle)) |
| CI on the 2026-10-28 to 2026-10-30 merges | `e1f7ac41`, `cf3d4b8f`, `d51c7a60` and `991b0654`: the `push` and `pull_request` runs of *CI test and publish Docker image* and CodeQL passed on each (`991b0654`: push 40989520549, `pull_request` 40989526434; `d51c7a60`: 40988048798, 40988055182; `cf3d4b8f`: 40982235609, 40982243569; `e1f7ac41`: 40637431538, 40637440405) — `gh run list --commit <sha>`; job lists and image tags not read |
| Staging PR, 2026-10-27 | #8824 (`dev` → `master`, "new dev branch post 15.0.9 release"): open, head `eed31dca` (`MERGEABLE`, `BLOCKED`, `REVIEW_REQUIRED`, read 2026-10-27 20:25Z); `master`'s required checks are still `Run Tests (22, 6)`, `Run Tests (22, 4.4)` and `Run Tests (24, 6)`, and `dev`'s CI no longer runs `Run Tests (22, 4.4)`, so the maintainer's settings change is still owed |
| CI on the 2026-10-27 merges | `eed31dca`, `88676086` and `94899828`: `push` passed and published `dev_<sha>` and `latest_dev` with no per-architecture tags (#8866's by-digest publishing; Docker Hub 20:20Z, 20:14Z, 20:02Z); `88676086`'s `pull_request` run was cancelled by the next push. `b84871d7` (#8866): `push` run 40571593504 failed *Browser tests (26, webkit)* on the cached-bundle startup test again, so it published nothing (`RT-CI-WEBKIT-REPORTS`); its `pull_request` run passed. The MongoDB 8.0 jobs run on `ubuntu-22.04` since `f6884342` (BF-202) |
| CI on `8dbb60c2` | **red.** `push` run 40424319822: *Browser tests (26, webkit)* (658 passing, 1 failing: "Complete page template startup boots every page from cached bundles and retires the old cache on upgrade", `Uncaught browser errors`, fifteen report-page `entries.json`/`treatments.json` requests "due to access control checks") and *Run Tests (26, 5.0)* (`tests/concurrent-writes.test.js` "all documents have unique _id after concurrent inserts", expected 10, got 9) failed, so *Tests pass* failed and no image was published; `pull_request` run 40424329138: the same WebKit test failed, every other job passed (*Validate Docker image* amd64 and arm64 passed); CodeQL passed on both events (40424319787, 40424329177). #8860's own run 40422840113 on `ad593fce`, the identical tree, passed every job at 23:55Z, before UTC midnight; the merge runs started after 00:07Z. See [Known defects](#known-defects-on-dev-now) — `gh run view <id> --json jobs`, `--log-failed` |
| CI on `7ad3a67f` | `push` run 40410737772 passed every job and published (*Validate Docker image* skipped by design); `pull_request` run 40410745675 and CodeQL (40410737784, 40410745580) passed; on `c08cbe03`, push 40403541566 and `pull_request` 40403553936 passed — `gh run list --commit`, `gh run view <id> --json jobs` |
| CI on `47723cda` | `push` run 40369632641 (16 jobs: 15 passed, *Validate Docker image* skipped) published `dev`'s image at 17:42:36Z (`nightscout/cgm-remote-monitor:latest_dev` and `dev_47723cda…`; Docker Hub reports `latest_dev` updated 17:42:32Z); `pull_request` run 40369639616 passed; CodeQL passed on both events (40369632350, 40369639665) — `gh run view <id> --json jobs`; the 2026-10-26 merges' runs are R14 in the [integration record](../../docs/30-design/remedial/rc-16.0.0-integration-record.md) |
| CI on the 2026-10-25 merges | every `push` and `pull_request` run on `5de8505d`, `fd3792e5`, `eb44a9c2`, `78524be4` and `b29f1bf7` passed on attempt 1 and each push run published an image (integration record R13); `eb72a1d3` and `93f152bd` published, `a20469dc` failed Firefox and skipped publishing (R6, R9, R10) |

## Provenance

Every figure below is labelled. **reproduced**: something was executed and the output observed.
**read-derived**: read from source, a PR body or CI metadata. Commit counts, SHAs, PR states, CI
results and the conflict counts are reproduced with the commands shown. No test suite was run on
`dev` by this session; the runs reported are the PR authors' and peer sessions', read from the PR
bodies (see the integration record). No live site, vendor account or Docker image was run.

## What is merged so far

Merge SHAs: `git log --first-parent --format='%h %ad %an %s' --date=iso official/master..official/dev`;
merge times are `gh pr view <n> --json mergedAt`. The first nineteen merges below were made on
2026-10-25 (#8834, #8835 and #8838 by bewest, the others by AndyLow91), seventeen on 2026-10-26
(#8843, #8848 and #8850 by bewest, the others by AndyLow91) and on 2026-10-27 #8860 and #8864 by AndyLow91, then #8866, #8859, #8868, #8856, #8861, #8863, #8870, #8869 and #8858 by bewest; later #8871, #8872, #8873 (2026-10-28) and, on
2026-10-30, #8877, #8878 and #8865, all by bewest. Register ids refer to the
[backfix register](../../docs/30-design/remedial/nightscout-backfix-register.md).

| PR | merged (UTC) | merge | head | author | register | queue | what |
|---|---|---|---|---|---|---|---|
| #8831 | 10:50:42 | `d7249f48` | `ecdd2af1` | AndyLow91 | — | — | opt-in `THEME=modern` responsive dashboard theme; existing themes unchanged (52 files, +3011/−224) |
| #8825 | 13:12:03 | `dfd659ba` | `b20a710b` | bewest | BF-173 | `BFQ-173` | the Careportal Bolus Wizard converts the profile's targets and sensitivity to the display units |
| #8826 | 13:21:08 | `e2857b89` | `9e3e1cc0` | bewest | BF-174 | `BFQ-174` | the bolus calculator uses the profile the caller names; merged after #8825, as required |
| #8827 | 13:29:41 | `1c70fc8c` | `8d2a3b8c` | bewest | BF-157 | `BFQ-157` | a treatment's glucose bubble reads units spelled `mmol/L` as mmol/L (display position only) |
| #8823 | 13:36:05 | `4c1a5f1a` | `d00576b9` | bewest | — | `RT-1` | `BRIDGE_SERVER=US`/`ous`/URL mapping in the bridge-to-connect compatibility layer (also folded into cut 1; see [Merge state](#merge-state)) |
| #8819 | 13:48:08 | `f09a9382` | `bbca2892` | javier-erro | BF-172 | `BFQ-172` | the Bolus Wizard Preview converts the profile's values to the display units |
| #8797 | 13:57:31 | `ecf32222` | `a4badcc6` | bewest | BF-09 | `BFQ-09` | the socket's 2 s duplicate check keeps a zero temp basal, 100 % temp, cancel, zero bolus or zero carbs |
| #8816 | 14:05:19 | `b1dce5e8` | `fb2c0da2` | awss1i | — | — | a snooze chosen on a page that is not signed in lasts as long as chosen |
| #8812 | 14:25:53 | `bb56989c` | `ba5f7f4b` | cpruijsen | — | — | off-by-one reading count in the glucose distribution report (issue 7659) |
| #8808 | 15:00:27 | `1cae31e1` | `dbd2a7be` | awss1i | — | — | the Loopalyzer keeps BG readings on or close to a 5-minute mark |
| #8828 | 16:29:06 | `eb72a1d3` | `12154df9` | bewest | BF-55, BF-58 | `RT-1` | cut 1: retire jsdom (option C), the enforced Node floor, removal of the legacy Dexcom Share and MiniMed CareLink bridges, version 16.0.0 |
| #8834 | 17:44:48 | `93f152bd` | `f3d73f43` | bewest | BF-176 | `BFQ-176` | `axios` `^0.34.0` and `lodash` `4.18.1` are runtime dependencies: a production install with `IMPORT_CONFIG` boots again |
| #8835 | 17:59:06 | `a20469dc` | `477d5200` | bewest | BF-163 | `BFQ-163` | `compression` 1.8.2, `follow-redirects` 1.16.1, `source-map-js` 1.2.2 (`feb3944c`, `ad458fa0`, `341b843a`) and `sanitize-html` 2.18.1 (`0293d640` the bump, `1eb986ad` `tests/purifier.corpus.test.js` pinning the stored text of 35 inputs), and a merge of `dev` `93f152bd` (`477d5200`) |
| #8838 | 19:42:01 | `2bc298b9` | `039be646` | bewest | BF-158, BF-177 | `RT-CONNECT-TEARDOWN`, `BFQ-158`, `BFQ-177`, `RT-D3-SUITE` | test and CI hygiene, 10 commits (below) |
| #8836 | 20:03:15 | `5de8505d` | `df2f37ab` | AndyLow91 | — | — | "Fix middleware DoS, harden credentials and streamline CI": `body-parser` 1.20.9, the status request's credentials move from the URL to headers, credential redaction in logs, `Referrer-Policy` and `Cache-Control` changes, dependency floors, CI action pins, no `npm` in the runtime image (24 files, +753/−99; below) |
| #8833 | 20:10:15 | `fd3792e5` | `9ac9d534` | AndyLow91 | — | — | "ci: remove temporary Node 22 / MongoDB 4.4 check": the `Run Tests (22, 4.4)` matrix entry and its docs (5 files, +14/−18) |
| #8837 | 21:28:47 | `eb44a9c2` | `af7ba73a` | bewest | — | `RT-2`, `RT-CONNECT-PIN-CUTS` | cut 2: page bundles and the build/runtime split (204 files, +22567/−3291; below) |
| #8839 | 21:57:16 | `78524be4` | `ad8a73e2` | bewest | — | `RT-TEST-TIERS` | the test tier map, its check and inner-loop selection (`test:affected`, `test:smoke`) (15 files, +1001/−11; below) |
| #8840 | 22:41:24 | `b29f1bf7` | `5be6f217` | mixa2010 | — | — | the Loopalyzer keeps 288 five-minute bins on 23- and 25-hour days (issue 8156) (4 files, +565/−69; below) |
| #8542 | 10-26 01:23:04 | `428b20b7` | `31f4bf21` | tim2000s | — | — | the Statistics Summary (AGP) report and modern report charts (33 files, +3125/−646) |
| #8843 | 10-26 05:20:27 | `720e60de` | `7fd2415e` | bewest | BF-185, BF-192 | `RT-CI-DIAGONAL`, `BFQ-185`, `BFQ-192` | CI: the Node × MongoDB diagonal, a no-database job, *Tests pass*, seeded test order; the browser tier runs in CI again (24 files, +437/−156) |
| #8848 | 10-26 06:03:54 | `1f10cd9d` | `952d0f49` | bewest | — | `RT-CI-DIAGONAL` | `dev` and `master` pushes build and publish Docker images again; two order-dependent tests (4 files, +27/−5) |
| #8850 | 10-26 06:22:23 | `207a8352` | `b6c11a93` | bewest | — | — | three more tests that passed only in alphabetical order (4 files, +23/−7) |
| #8841 | 10-26 10:23:14 | `e09bca3b` | `5901961c` | bewest | — | `MOD-WRITE-VALIDATION` | opt-in `WRITE_VALIDATION` (`off`, `log`, `reject`) for Temporary Target writes on API v1 and v3 (11 files, +918/−11; below) |
| #8842 | 10-26 10:33:08 | `85e5108a` | `148db86b` | bewest | BF-92, BF-93, BF-159 (token half), BF-160, BF-180, BF-190 | `BFQ-92`, `BFQ-93`, `BFQ-159`, `BFQ-160`, `BFQ-180`, `BFQ-190` | alarms and live updates reach the page (16 files, +455/−28; below) |
| #8844 | 10-26 10:59:10 | `ad05e140` | `0d54d072` | bewest | BF-179, BF-182 | `RT-REBASE`, `BFQ-179`, `BFQ-182` | cut 3: MongoDB driver 7, selected jQuery UI widgets, native help tooltips, Compose `mongo:6.0.27` (91 files, +10090/−194) |
| #8845 | 10-26 11:34:16 | `900abf7a` | `50219945` | bewest | BF-145, BF-152 (step 1), BF-165, BF-166, BF-167, BF-169, BF-170, BF-186 | the eight `BFQ-` items | record identity and the write contract (25 files, +1314/−107; below) |
| #8847 | 10-26 12:15:29 | `e34efdef` | `35fc8167` | bewest | BF-183 | `RT-5`, `BFQ-183` | cut 4: trusted proxies through one module, `mime-types`, moment-timezone 0.6, csv, semver 7, ESLint 10, webpack 5.110 (135 files, +5981/−1286) |
| #8849 | 10-26 12:43:22 | `3b2e1a68` | `0772cb47` | bewest | BF-46, BF-48, BF-49 (warning), BF-156 | `RT-BOOT-INDEX-AWAIT`, `BFQ-46`, `BFQ-ENV`, `BFQ-156` | boot waits for its indexes (at most 20 s), API v3 auto-prune handles its delete, API v3 and webhook settings read in `env.js` (17 files, +843/−60; below) |
| #8852 | 10-26 13:31:17 | `a911cdb2` | `b471074b` | AndyLow91 | — | — | API v1 profile POST payloads are validated before iteration: malformed entries and binary bodies answer 400, and batches are capped at 10,000 records; addresses CodeQL alerts 134 and 135 (3 files, +67/−10) |
| #8851 | 10-26 14:38:38 | `43050723` | `3bf675dd` | mixa2010 | — | — | `toRoundedStr` rounds on the decimal digits, so dose labels on midpoints round correctly (1.005 U shows as `1.01U`, not `1U`) (2 files, +74/−4) |
| #8730 | 10-26 15:31:40 | `89b7ebdd` | `2b32fe67` | sulkaharo | BF-132 | `RT-PR-8730` | Crowdin translations (33 files, +111/−12); it keeps `dev`'s corrected strings |
| #8555 | 10-26 16:12:41 | `09d0def8` | `371c4642` | samuelpert | — | — | opt-in `SHOW_SECONDS` dashboard clock seconds, a browser setting and an environment variable (13 files, +153/−7); closes issue 8048 |
| #8605 | 10-26 17:32:44 | `47723cda` | `a77cb146` | AndyLow91 | — | `RT-3` | cut 5: Express 5, Helmet 8, Axios 1, EJS 6, entities 8, `mime-types` 3, Swagger UI 5, APNs 8, a native Pushover client, a maintained notification cache, Flot 4 (204 files, +59400/−1515) |
| #8854 | 10-26 21:20:34 | `c08cbe03` | `246313e4` | AndyLow91 | — | `ARCH-8854` | shared persistence and stored-data contracts: the persistence boundary `lib/storage/write-step.js`, socket Temporary Target validation under `reject`, the opt-in `Nightscout-Data-Warnings` header (46 files, +2340/−100; below) |
| #8084 | 10-26 22:13:18 | `7ad3a67f` | `27886bab` | gardenrobot | — | — | Google Fonts replaced by fonts served from the site; the Content-Security-Policy drops the Google font hosts (92 files, +1093/−23); not examined further |
| #8860 | 10-27 00:07:13 | `8dbb60c2` | `ad593fce` | AndyLow91 | — | — | the glucose pentagon (Comprehensive Glucose Pentagon) and its prognostic glycemic risk (PGR) in the Distribution report, for issue 8809 (20 files, +1178/−10; below) |
| #8864 | 10-27 16:55:01 | `2dc0c1bc` | `4ed92673` | AndyLow91 | — | — | the IOB pill keeps the device-reported value through a socket reconnect instead of switching to the treatment-based value |
| #8866 | 10-27 19:42:55 | `b84871d7` | `f6884342` | bewest | BF-201, BF-202 | `RT-CI-FLAKES-8DBB60C2`, `BFQ-201`, `BFQ-202` | CI: three intermittent test fixes, a MongoDB wait that names the runner's kernel, the MongoDB 8.0 jobs on `ubuntu-22.04`, release images published from the tag (a push to `master` publishes nothing), nodemon's watch list; #8867 was folded in and closed |
| #8859 | 10-27 19:52:21 | `94899828` | `87f1aeb8` | bewest | BF-195 | `BFQ-195`, `ID-SIMPLE-MATCH` | the re-send and merge contract: identifier matching, `null` in an update removes the field (Q1b), the profile socket push after its merge write (BF-195), devicestatus `identifier` |
| #8868 | 10-27 20:01:50 | `88676086` | `2ca7dfc8` | bewest | BF-200 | `BFQ-200` | API v2's data-snapshot route answers 400 for a time it cannot parse instead of stopping the server; callback tasks stop a run when a task throws, as `async` did |
| #8856 | 10-27 20:09:35 | `eed31dca` | `6c9af523` | bewest | BF-193 | `BFQ-193` | write paths log a summary of a write, not the record, unless `DEBUG_LOGGING` is on |
| #8861 | 10-27 20:57:07 | `84fac457` | `5310a447` | bewest | — | `ST-FILTER-READS` | the storage filter AST and interface methods; API v1 reads move onto the storage interface |
| #8863 | 10-27 21:00:16 | `9668b179` | `42128f3b` | bewest | — | `ST-WRITES` | API v1, authorization and socket writes go through the storage interface, labelled by source |
| #8870 | 10-27 21:33:44 | `7abe1cf6` | `0955f25b` | bewest | — | `ST-COUNT-ONEPATH` | API v1 count goes only through the storage interface (the pipeline path removed) |
| #8869 | 10-27 22:23:05 | `b8baf24d` | `d9fca2de` | bewest | — | `RT-CI-WEBKIT-REPORTS` | test: page-startup waits for `/report/` on its first controlled visit, and a failure names each browser error's page |
| #8858 | 10-27 22:29:46 | `ca1652d6` | `debf4a14` | bewest | — | — | the API v1 and v3 documents describe what 16.0.0 serves, and a contract test holds them to the routes (includes #8381 by arfaomar); the alignment site's API pages re-rendered from it as current |
| #8871 | 10-27 22:51:12 | `dcf20bfb` | `57f1d37c` | bewest | BF-203 | `BFQ-203` | tooling: a `jsconfig.json` scoped by `exclude`, so an editor stops watching sibling worktrees (1 file, +8) |
| #8872 | 10-27 23:45:05 | `db3b9e4e` | `355b4f14` | bewest | BF-194 | `BFQ-194` | a Temporary Target is stored in mg/dL labelled `mg/dl` on API v1, API v3 and the socket (11 files, +742/−43); owes a release-note line |
| #8873 | 10-28 05:20:32 | `e1f7ac41` | `1c50c29a` | bewest | BF-204, BF-205, BF-206, BF-207 | `BFQ-204`..`BFQ-207` | the data-snapshot route answers a past time from its own query; same-time records ordered by `_id`; an undated device IOB takes its status's time (the AAPS IOB pill golden regenerated); sensor age keeps the newest start within an hour (built by session -65) |
| #8877 | 10-30 00:50:49 | `cf3d4b8f` | `ac5d77fb` | bewest | BF-209, BF-211 | `BFQ-209`, `BFQ-211` | the socket's ±2 s similar treatment match follows client identity: when the write carries `identifier`, the same one is one record and a different one a second record; the exact match is unchanged (BF-209). A delete by query flushes only the cache of the collection it deleted from (BF-211). BF-210 was withdrawn from it before merge as not a defect (maintainer, 2026-10-29) (8 files, +1219/−20) |
| #8878 | 10-30 01:48:51 | `d51c7a60` | `57f333b4` | bewest | BF-212 (first part) | `BFQ-212` | the chart's "Move insulin" and "Move carbs" split no longer copies `syncIdentifier`, `id`, `uuid` or `identifier` onto the moved half (2 files, +21/−4); the rest of BF-212 is open ([Known defects](#known-defects-on-dev-now)) |
| #8865 | 10-30 02:04:14 | `991b0654` | `1b2801f7` | bewest | — | `PLAT-SERVE`, `PLAT-ENTRY` | one executable `nightscout`: the image's `CMD ["nightscout", "single"]`, SIGTERM and SIGINT shutdown on every start path, the healthcheck command, boot profiles, API v3 without API v1's modules, the socket and the cache (ST-V3-DECOUPLE), and `serve` reserved for a multitenant Nightscout (53 files, +2575/−189); supersedes #8862 |
| #8880 | 10-30 16:24:38 | `305a6533` | `0e5c25be` | bewest | BF-213, BF-214, BF-217 | — | the pump alarm follows the severity Loop sends in `reservoir_level_override`, with Loop's text; an override with no reservoir value no longer throws in the pump plugin; a v1 device-status delete by query asks for a reload (5 files, +327) |
| #8874 | 10-31 02:02:52 | `368e6c23` | `83f3d54a` | bewest | BF-218 (test) | `WC-STEP-PATCH` | `write(intent)` release 1: every v1, API v3 and socket write path through one write step, no behaviour change by the write-contract matrix (0 of 1,929 cells outside `cache`), merge revert rehearsed; journey lab (2026-10-30/31) found no difference from `dev` |

### Merged additions, 2026-11-01

These rows extend the historical merge table above without recomputing its
size/count measurements. Only integrated patch evidence is recorded.

| PR | Merged at (UTC) | Merge commit | Register / queue | Scope |
|----|-----------------|--------------|------------------|-------|
| #8895 | 11-01 17:45:01Z | `bb85d10f` | BF-227 / `BFQ-227` | Handled Pushover callbacks for late/duplicate/expired receipts answer 200; known alarm acknowledgment remains once-only and the diagnostic is unchanged. |
| #8896 | 11-01 17:52:18Z | `61eb3733` | `RT-CI-FIXTURES-8896` (no new BF) | Test-only: find the seeded cached/served entry without first-position assumptions; compare successful index states `built`/`present` as equivalent. |

R19/R20 in the integration record separate local focused evidence, the
inconclusive local start-path rerun, and successful hosted checks. The final
#8896 diff and canonical merged files were inspected; no additional
production-code change is claimed. The published development-image manifest
and remaining gates are in the
[current readiness record](../../docs/10-domain/nightscout-rc-readiness-2026-11-01.md).
Latest release is still 15.0.9; BF-227 is fixed on dev, not released. Private
BF-72/BF-161 integration remains blocked, as do unperformed live/cohort gates.

**Historical merge commentary follows:**
Before merging, AndyLow91 merged `dev` into most branches and added commits of his own (read with
`git log` and `git show`):

- #8825: `b20a710b` "resolve profile units at calculation time": `getUnits(spec_profile, time)` takes
  a time, and the calculator reads the profile's units at the record's event time, the time its
  targets and sensitivity are read at; 2 more cases in `tests/careportal.test.js`.
- #8819: `bbca2892`, the same for the Bolus Wizard Preview (`getUnits(undefined, sbx.time)`), which
  answers the review point drafted on 2026-10-21 that `getUnits(sbx.time)` passed a time where it
  takes a profile name; `tests/boluswizardpreview.test.js` +57.
- #8828, after `806ff2f0`: `2c46e35b` (runtime-upgrade guide), `6a146a4c` (the floor above),
  `d49a81f7` (CI resolves the newest Node patch), `32489dc5` (the Docker base image above; `.nvmrc`
  `24.22.1`), the `dev` catch-up merge `43eb6066`, `36fa3121` (keeps a Node 22 × MongoDB 4.4 test
  cell), `76c73056` and `13507b38` (CI) and `12154df9` (a bounded Firefox month-report test).

#8838's ten commits, on `dev` `a20469dc`: `38049fe6` (the redundant connector teardown listener
removed, `RT-CONNECT-TEARDOWN`), `fb0e1217` (BF-158: the count=0 block isolated from records other
files leave, plus the runtime-cache flush found by peer session -b7), `89d19b5b` (BF-177: the test's
time-zone stand-in is a UTC profile; the report is verified correct by running it), `879ab51e` (the
duplicated `BRIDGE_SERVER mapping` block removed, 37 → 22 cases), `e45041c6` (stale Node floor text in
`docs/test-specs`), `f7856a44` (`RT-D3-SUITE`: two treatment-drag clamp browser tests), `29e8a36b` (the
CI edge matrix, 31 → 10 test and browser cells, about 81 runner-minutes less per run), `cab8896f` (the
API3 SEARCH hook's timeout: on an empty database the first insert waits on boot's unawaited index
creation; the product fix is `RT-BOOT-INDEX-AWAIT`), `aa7438ee` (Babel checked against the engines
floors) and `039be646` (MongoDB 5.0 and 8.0 as the CI edges, and the docs).

**#8836** (read from the PR body and `git show`; the runs are AndyLow91's). Six commits
(`git log 2bc298b9..df2f37ab`): `e0872924` (dependency and credential findings), two merges of `dev` (`f09cb431`, `15a84907`),
`be806a57` (privacy for GET authentication), `78aacc15` (CI) and the merge `df2f37ab` ("Merge dev CI
hygiene while preserving the 14-job matrix"). What it changes, by mechanism:

- `body-parser` `^1.20.6` → `^1.20.9` (lock 1.20.6 → 1.20.9): the PR body states that a malformed
  compressed request body can terminate the server, and adds child-process regression probes for it
  and for `compression` 1.8.2 (on `dev` since #8835). **15.0.9 locks `body-parser` 1.20.6 and
  `compression` 1.8.1** (`git show official/master:package-lock.json`), the versions these replace.
- The page's first status request no longer carries the API secret hash or token in its URL: it sends
  them as `api-secret` and `Authorization` headers (`lib/client/index.js`), and `lib/api/status.js`
  reads them there. Query-string credentials are still accepted for existing clients. **15.0.9's
  `lib/client/index.js:58` appends the credential to the status URL.**
- Logs and responses: credential-bearing request URLs and error details are redacted
  (`lib/server/log-privacy.js`, new), CSP reports are sanitised before logging, `Referrer-Policy:
  no-referrer` is set whether or not CSP is on, `Cache-Control: no-store` is set on status responses
  and before redirects and authorization (`lib/middleware/credential-cache.js`), and setup-mode errors
  use the production error handler.
- Dependency floors: `dompurify` 3.4.17, `moment` 2.31.0, `fast-uri` 3.1.9, `ip-address` 10.7.5,
  `serialize-javascript` 7.1.4, `csv-parse` 7.0.3 (development), nyc's nested `uuid` (lock versions on
  `dev`, reproduced). The PR body reports `npm audit` affected-package entries 23 (full) and 16
  (`--omit=dev`) before and two after, both in the one chain with no patched release:
  `@parse/node-apn` → `node-forge` 1.4.0, GHSA-86w9-cpqp-85rv; the body says no remotely reachable path
  was established and keeps APNs as it is (read-derived; not re-run).
- CI: the 20 mutable action references pinned to commit SHAs; superseded `pull_request` runs cancelled;
  publishing waits for every test job; a manual extended mode that never publishes. The runtime Docker
  stage deletes `npm` and `npx`.
- Tests on the PR head (read from the body): Node 24.22.1 against MongoDB 6.0.27, 3474 passing, 3
  skipped, 0 failing, with coverage; 51 focused privacy and header cases on Node 22.23.4 and 24.22.1.

**#8833** removes only the `Run Tests (22, 4.4)` matrix entry and updates `CONTRIBUTING.md`,
`README.md`, `docs/runtime-upgrade.md` and `docs/test-specs/browser-tests.md` (`daee0c9e`, merge
`9ac9d534`). Its body states that `dev` requires only `Run Tests (24, 6)`, and that `master` still
requires `Run Tests (22, 4.4)`, which an administrator must remove before the next release PR into
`master` (read; the protection read above agrees).

**#8837, cut 2, as merged.** After `ee94b148`: AndyLow91's merge of `dev` `fd3792e5` (`2efd78ac`,
"Merge dev security and CI updates into Cut 2"; conflicts in `.github/workflows/main.yml`,
`lib/server/app.js`, `package.json` and `package-lock.json` per the body), `62b1509d` (the env-runner nyc
fix: `--all=false` on the inner nyc and `docs/test-specs/env-runner.md`; author Ben West, the same
patch as the peer session's `bd941200` by `git patch-id`) and AndyLow91's `af7ba73a` ("fix: preserve
Maker delivery across recipient failures": Maker keys are sent in parallel and one key's error no
longer stops the other keys or the later events; each request has a 10 s deadline; the log line names
the event instead of the request URL, which carries the Maker key; 5 files). **15.0.9 logs that URL**
(`lib/plugins/maker.js:111` on `official/master`). Whether `af7ba73a` also closes BF-137 (several
Maker keys: out of order, a failed key not retried) was not checked; `BFQ-137` is unchanged. Tests on
the merged branch (read from the body): Node 24.22.1, MongoDB 8.0.29, 3730 passing, 4 skipped, 0
failing, with coverage; `test:core` 316; Chromium page-startup and credential-bootstrap selection 49
passing; the pruned runtime with `IMPORT_CONFIG` passes. CI on the PR head `af7ba73a`: run 40231697337,
attempt 1, passed. `lib/server/query.js` on `dev` now walks queries with `queryLeaves`
(`lib/utils/query-leaves.js`); `traverse` is no longer in `package.json` (reproduced with `git grep`).

**#8839** (read from the body): `tests/tiers.json` places 317 test files in eight tiers (unit 97,
dom 17, dependency 20, core 26, harness 7, integration 123, stress 1, browser 26). AndyLow91 merged
`dev` `eb44a9c2` into it (`90e2cfde`, "Merge dev and align test tiers with Cut 2") and added `ad8a73e2`
(invalid tier or file selections exit non-zero before any test starts). The tier check and the harness
tier run in the main backend CI jobs. `npm test` and `test-ci` are unchanged.

**#8840** (read from the body; issue 8156). On a 23- or 25-hour day the Loopalyzer built 276 or 300
five-minute bins instead of 288, so every series was rejected and the charts were blank; ranges that
included such a day dropped that day's series. The fix anchors the axis on a 24-hour local day and
bounds per-day slots to 288 (`lib/report_plugins/loopalyzer.js`, `docs/test-specs/loopalyzer-dst.md`,
two test files). Commits: HeartCoreDev's `63ad23be`, AndyLow91's merge of `dev` `a383f0f9` and his
`5be6f217` ("align DST curves with local clock markers"). The body reports 13 of 13 slot tests failing
before the change and 20 of 20 passing after (`TZ=Europe/Berlin`). The PR head's run 40240553524 needed
a maintainer approval on attempt 1 (`action_required`, a fork PR) and passed on attempt 2.

**The 2026-10-26 merges** (read from the PR bodies and `git log <merge>^1..<merge>^2`; the runs are the
authors'):

- **#8841**: `e8125d89`, `6e842c07`, `a2e5fe49` (bewest) and AndyLow91's `5901961c` ("validate effective
  Temporary Target updates"). Rules for every app, checked only when `WRITE_VALIDATION` is `log` or
  `reject`: targets above zero, bottom not above top, `units` `mg/dl` or `mmol` (client spellings
  accepted), each target plausible for its units (above 30 labelled `mmol` is a mg/dL number; below 20
  labelled `mg/dl` is a mmol/L number), durations zero or more. Under `reject` a v1 batch stores its valid
  items and answers 200 with one object per item, the refused ones without `_id` and with a `refused`
  member, plus `Warning: 299`. App-specific limits (AndroidAPS's 72–180 mg/dL) are not applied.
- **#8842**: BF-92 (`5fb199b3`, with BF-190), BF-93 (`91d9a4db`), BF-180 (`bb1ad38e`, the careportal temp
  target converted once and labelled `mg/dl`), BF-159's token half (`72f3cc09`) and BF-160 (`2556b35b`).
  On a page showing `---`, a non-glucose alarm (pump, loop, age, stale data, CGM error codes and the rest
  outside the default group) is now presented when either the page's high or low alarm for its level is
  on; glucose alarms with no reading stay unpresented. The PR body asks reviewers to confirm stale-data
  and CGM-error alarms on a page showing `---`.
- **#8844 (cut 3)**: merged from `0d54d072`, AndyLow91's commit over his own merge of `dev` into cut 3
  (`831c32fc`). Driver 7 with an explicit `batchSize: 1000` on bulk reads, BF-182's boot error page
  (`8f238fc5`), BF-179 (`200c1361`), jQuery UI 1.14.2 widgets and native help tooltips, Compose
  `mongo:6.0.27` (a database major upgrade for an existing Compose deployment).
- **#8845**: BF-145 (`d4566292`), BF-165 (`0d5edc66`), BF-166 (`c62a16c9`, a profile re-sent with its
  `_id` is merged with `$set`, the write contract's Q1 rule; a field sent as `null` is stored as `null`),
  BF-167 (`0edb1db9`, test only), BF-169 (`a1ab22b6`, `539856ef`), BF-170 (`304827fd`, `b899edc1`:
  API v3 create, PUT and PATCH refuse a body `_id` with 400), BF-186 (`b34f6703`), BF-152 step 1
  (`faffe875`, `API3_SETTINGS_STRICT_READ_ENABLED`, off by default), and AndyLow91's `50219945`
  ("Require update permission for profile POST merges").
- **#8847 (cut 4)**: one client-address module (`lib/server/client-ip.js`) for every consumer; with
  `TRUST_PROXY` unset, 15.0.9's resolution (BF-88); BF-183 (`54115e95`); the dependency majors above;
  `npm run lint` without errors and in CI.
- **#8849**: `488def62` (boot waits for collection and index creation, at most 20 s, then warns and
  continues; a first start on an empty database takes about 3 to 4 s longer on MongoDB 8.0), BF-156
  (`a5b569b9`), BF-46 (`1d63df57`), BF-48 (`8e4d30d3`) and BF-49's start-up warning (`8e3717e3`).
- **#8605 (cut 5)**: AndyLow91's head `a77cb146` over his merge of `dev` `09d0def8` (`246f2274`), which
  contains session -f8's catch-up chain (`98d2f9a0`, `574870f8`). Its last commits restore the CORS
  preflight's `200` text `OK` (`ad56423d`), give browser jobs 15 minutes (`f4abce3c`) and set `HOME`
  for the Firefox date probe (`a77cb146`). The body leaves live Pushover emergency delivery,
  acknowledgement and cancellation, alarm de-duplication over its real window, APNs delivery to a phone,
  production hosting, upgrade and rollback, and physical-device accessibility as maintainer-owned
  acceptance work.
- **#8854**: eleven commits by AndyLow91 over `dev` `47723cda`, from `880b7369` to `246313e4`, merged
  after the four outcome-B points ([decisions](decisions.md)), which he agreed to on the PR at 20:32Z. By
  mechanism: the six v1 and internal collection modules, the legacy socket and API v3 go through the
  persistence boundary (`lib/storage/write-step.js`, a wrapper over the driver collection that keeps
  existing replies and validates the effective result of `$set` and `$unset`); it emits a data-free
  `storage-write-committed` event marked internal and unstable, with no consumer; the opt-in Temporary Target
  rules also apply to the socket's add, update and unset, and under `reject` the socket answers a refused
  item with a `refused` slot in input order, as API v1 does; a non-mutating stored-data inspection
  (`lib/storage/read-contract.js`) can add a `Nightscout-Data-Warnings` header to API v3 reads, off unless
  `API_V3_DATA_WARNINGS=true` and called experimental; a read-only diagnostic command
  (`scripts/diagnose-data.js`) and a write-boundary check (`scripts/check-write-boundary.js`); guards for
  malformed cache values, authorization identities and history timestamps; Mocha runs that find zero tests
  fail (`--fail-zero`). Not asked for: `246313e4` adds a `failed` slot on socket treatment arrays under
  `reject` for an item whose write cannot be confirmed (open item 11). The merged tree's client replay is
  R16 in the integration record: 0 differences from `47723cda` in 201 cells.

**#8860**, the glucose pentagon (read from the PR body and `git diff --stat 7ad3a67f 8dbb60c2`; not run by
this programme). The Distribution report gains the Comprehensive Glucose Pentagon's five component values,
a reference polygon, CGM coverage, the reading count and the prognostic glycemic risk (PGR), in both
glucose units, both report themes and print (`lib/report/pentagon.js`, `pentagon-view.js`, `agp-data.js`,
`lib/report_plugins/glucosedistribution.js`). Fixed 70–180 mg/dL thresholds; it reads the original CGM
observations before the report's one-minute filter, time-weights them, collapses exact same-source
duplicates and withholds the score for conflicting simultaneous readings or indistinguishable alternating
streams. The score is withheld below 70 % elapsed coverage, below 16 h 48 min of observed data, or when an
hourly filter excludes part of the day; the PR body calls these "implementation guards, not validated
clinical PGR thresholds", and says the numerical checks "do not constitute third-party clinical
validation" and that independent review of the incomplete-data method and clinical presentation remains
advisable. It adds the Nightscout Reporter licence notices (`docs/third-party/`) and the method in
`docs/test-specs/glucose-pentagon.md`. The PR's CI on `ad593fce` passed every job; the merge's did not
([Identity](#identity), CI on `8dbb60c2`).

**The 2026-10-30 merges** (read from the [register](../../docs/30-design/remedial/nightscout-backfix-register.md)
and the [next-gen plan](../../docs/30-design/platform/next-gen-platform-plan.md) §1a; the runs are the
preparing sessions'):

- **#8877**: BF-209's scope was decided 2026-10-29: in the similar match only, `identifier` decides when
  present, because applying the legacy client-id rule as it is would make an `identifier`-only re-send a
  duplicate; recognising `identifier` at any time waits for ID-FIRST-MATCH. `567f0612` restores the amount
  rule with pins (a carbs-only re-send next to a stored carbs-and-insulin record stays one record) and
  `ac5d77fb` is BF-211. `npm test` 4858 passing, 0 failing, 3 pending; the write-contract matrix against `dev`
  moves `treatments × v3 × ws` as intended, and session -4f's dedupe gate (58 tests, ablations red) measured
  it. Changes which socket treatment uploads are stored as separate records; the plan asks an AndroidAPS
  3.4.2.x v1 cohort to check carbs and boluses.
- **#8878**: `splitRecord` (`lib/client/treatmenttime.js`) drops the four client identity fields beside `_id`
  and `NSCLIENT_ID`; a unit test that is red on `dev` before it; `npm test` 4858 → 4859 passing, 0 failing,
  3 pending; the reproduction probe finds one record per identity. A 16.0.0 backfix by the maintainer's
  ID-Q5 decision (2026-10-29).
- **#8865**: the start forms were measured on images in `tools/lab/image-start-forms` (B8 in the
  [release allocation](../../docs/30-design/platform/release-allocation-2026-10-27.md)): every `docker run`
  form that started a server on `dev` starts the same one; `docker stop` takes 0.13 s and exits 0 instead
  of 10.1 s and 137. `serve` refuses every role until one is multitenant.

None of these merged trees was re-run locally by this programme, except the client replay on `7ad3a67f`
(R16). The merged trees' CI is in
[Identity](#identity) and the integration record (R13, R14).

## Merge state

- **Every cut is on `dev`** (reproduced 2026-10-26 with `git merge-base --is-ancestor <head> official/dev`,
  exit 0 for each, and exit 1 against `official/master`): cut 1 `12154df9` (#8828), cut 2 `af7ba73a`
  (#8837), cut 3 `0d54d072` (#8844), cut 4 `35fc8167` (#8847), cut 5 `a77cb146` (#8605).
- **Session -f8's 2026-10-26 catch-up merges reached `dev` through cut 5, not through cuts 3 and 4.**
  `76b19fb0` (cut 3) and `8bf6c9b2` (cut 4) are not ancestors of #8844's and #8847's merged heads:
  AndyLow91 merged `dev` into cut 3 himself (`831c32fc`) and added `0d54d072`. Cut 5's head `a77cb146`
  contains `98d2f9a0`, which contains both, so all three are in `dev` (`git merge-base --is-ancestor`,
  reproduced).
- **#8823 merged twice, without duplicated code** (reproduced on `eb72a1d3`): one
  `bridgeServerToConnect`, in `lib/server/bridge-connect-compat.js`; the duplicated test block was
  removed by #8838 (`879ab51e`).
- **The 2026-10-30 heads are on `dev`, not on `master`** (reproduced 2026-10-30 with
  `git merge-base --is-ancestor`: exit 0 against `official/dev`, 1 against `official/master`): #8877
  `ac5d77fb`, #8878 `57f333b4`, #8865 `1b2801f7`. #8874's head `4f9fc4cd` is 0 commits behind `dev`
  `991b0654` (`gh api repos/nightscout/cgm-remote-monitor/compare/dev...4f9fc4cd`: `behind_by` 0,
  `ahead_by` 20).
- **#8874 is on `dev`** (2026-10-31): `dev` `368e6c23` is its merge, with CI passing on the push run
  41158171888 and the `pull_request` run 41158177377. `dev` is 1027 commits and 56 first-parent commits
  ahead of `master` `c6a0d8ed` (968 files, +151453/−19743; the integration record's figures).

## Version: 16.0.0, major

Decided by the maintainer on 2026-10-21 (`RT-VERSION` answered). Surfaces touched (versioning policy
§6.2), read from the merged PRs. A ticked box is a surface the merged code touches; an unticked one
marked *owed* has a candidate change whose classification is not recorded yet:

- [x] S1 the HTTP API and the realtime socket contract: #8797 stores records the socket used to drop as
  copies; #8845 makes API v3 refuse a client body `_id` with 400 (BF-170), answers a v1 re-send with its
  stored `_id` (BF-165) and merges a profile re-sent with its `_id` instead of answering 500 (BF-166);
  #8852 answers malformed API v1 profile uploads with 400 and caps them at 10,000 records; #8841 adds
  `refused` slots to v1 batch replies under `WRITE_VALIDATION=reject`, and #8854 the same slots, and a
  `failed` slot, to socket replies under `reject`, and the opt-in `Nightscout-Data-Warnings` header on API v3
  reads; cut 5 moves the routes to
  Express 5 (the query parser keeps `allowPrototypes: true` and sets `arrayLimit: 1000` and
  `parameterLimit: 1000`, `lib/middleware/configure-request.js:8-9`; read-derived: Express 4's extended
  parser used `qs`'s default `arrayLimit` of 20)
- [x] S2 plugin interface, boot sequence or client bundle: cut 2 (#8837) splits the client into page
  bundles and replaces the boot sequence and the client event bus with native code (a third-party
  plugin that hooks into the page is to be tested before upgrading; no plugin was run against it);
  #8849 makes boot wait for its indexes; #8831 adds an opt-in theme
- [x] S3 environment-variable surface: new `THEME=modern` (#8831), `WRITE_VALIDATION` (#8841),
  `API3_SETTINGS_STRICT_READ_ENABLED` (#8845) and `SHOW_SECONDS` (#8555); a start-up warning when
  `SECURE_HSTS_HEADER_INCLUDE_SUBDOMAINS` is set (BF-49); leftover legacy bridge settings stop the site
  with a page naming the replacements (cut 1); `DEBUG_MINIFY` no longer has an effect (cut 2)
- [ ] S4 stored document shape, *owed*: #8845's BF-166 changes what a profile re-sent with its `_id`
  stores (merged with `$set` where it failed before), and #8842's BF-180 changes how a careportal temp
  target on an mmol/L site is stored; neither is classified here
- [x] S5 Node or MongoDB runtime floor, **major**: `lib/server/runtime-policy.js` reads `engines.node`
  and exits at boot outside `^22.23.4 || ^24.22.1 || >=26.12.1`, which stops Node 20, 21, 23 and 25,
  and 22.0–22.23.3, 24.0–24.22.0 and 26.0–26.12.0. Driver 7 (cut 3) refuses MongoDB 3.6, 4.0 and 4.2
  (BF-182's boot error page); the README states 5.0 through 8.0. CI on `dev` (job names of push run
  40369632641): *Run Tests* (22.23.4, 8.0), (26, 5.0), (24, 6), (22, 6); *Tests without a database*
  (22.23.4), (26); *Maintained MongoDB* (26, 8.0.29); browsers on Node 26 × Chromium, Firefox and WebKit
- [x] S6 an ingestion path, **major**: the legacy Dexcom Share bridge and MiniMed CareLink
  (mmconnect) are removed; Dexcom Share data comes in through `nightscout-connect`
- [ ] S7 alarms or notifications, *owed*: #8842 (BF-92) presents device and other non-glucose alarms
  on a page with no reading where none was presented before, which is the policy's question 8
  (MINOR, never waivable, rule R2: at least a minor and a release note); #8816 changes how long a
  snooze lasts on a page that is not signed in; cut 2's `af7ba73a` changes how IFTTT Maker events are
  sent to several keys; cut 5 replaces the Pushover client and the notification cache and moves APNs
  to 8 (live delivery not checked, #8605's body)
- [x] S8 the version string: `16.0.0`
- [x] S9 what the client computes and shows a person: BF-172, BF-173 and BF-174 change the Bolus Wizard
  Preview and the Careportal Bolus Wizard where the profile and display units differ, or where a
  profile other than the active one is chosen; #8812, #8808 and #8840 change report figures; #8851
  changes how dose labels round; #8542 adds the AGP report

Not on the list, and recorded for the release notes: #8836 changes response headers
(`Referrer-Policy`, `Cache-Control`), where the page sends its credentials, and removes `npm` from the
runtime Docker image.

**Classification:** MAJOR, because of S5 and S6 (cut 1) and S5 again (cut 3's MongoDB floor).
**Directory name says:** 16.0.0. **Settled?** Yes, by the maintainer, 2026-10-21.

## In flight for this release

**The 16.0.0 scope, decided by the maintainer on 2026-10-30** ([decisions](decisions.md); next-gen plan §1):
16.0.0 targets every single-tenant item of the [next-gen plan](../../docs/30-design/platform/next-gen-platform-plan.md),
through the entry bar and in priority order. An item joins the merge list when its matrix result is as stated
(0 cells, or named cells), its red controls and ablations pass, a revert has been rehearsed, and it has had time
on `dev` with its cohort check (entry bar, 2026-10-29). An item that misses the bar at the tag rolls to 16.1.0,
or to 17.0.0 if it changes a default. The identity work is the core: it is the substance of the agreement with
the Loop maintainers. Multitenant items may ship dormant, labelled alpha behind `serve`, or not ship. The tag
is gated by the bar and the pre-tag items, not by a date.

**Handoff, 2026-10-31 (read with `git ls-remote` and `gh pr list` at about 03:00Z; plan owner session -49).**
`dev` is `368e6c23` (#8874 merged 2026-10-31 02:02Z). Merge order on `dev` from here: #8883, then #8879 once
slice 4 is rebuilt on it, then the unique-index PR. The cohort window (one window over #8874 and the identity work)
opens when slices 3 and 4 are on `dev`.

| PR / branch | head | state | next step, owner |
|---|---|---|---|
| #8883 v1 treatment writes (BF-219, BF-220, BF-221, BF-222) | `8ae46b72` on GitHub; `789d5d9d` local adds BF-222 (session -7d's fix, cherry-picked; the bundle's new test files 18 passing) | open, base `dev`; write-step port reviewed by session -4f | push `789d5d9d` and update the title and body, then merge **before** #8879's next `dev` merge (they conflict in four files); maintainer |
| #8879 identity (ID-FIRST-MATCH) | `5cdd9577` (slices 1, 2, 5, 5b, 3 + `dev` `368e6c23`) | draft, base `dev` | slice 4 rebuilt with treatments `replaced` on every path (decided 2026-10-30), then 6 and 6a (prepared: `prep/id-first-s6` `47377fa3`, tests red as expected, prediction script); session -4f |
| `feat/id-unique-index` (local) | `b4a4092c` on slice 3 | built and gated (342 predicted cells, MongoDB 5.0 and 8.0) | rebase onto 6a, re-run, open as a draft on #8879; held until then |
| `proto/id-batch-replies` (local) | `7d81e1c1` | prototype + client lab; (ii)–(vi) decided 2026-10-30 | build ID-BATCH on the identity branch after the index, with strict on v1 (ID-STRICT-V1) |
| #8881 ST-HARNESS | `ffa5e6b4` | draft, base `dev` | review; unblocks ST-PG and TEN-RESOLVE |
| #8882 hygiene (DEV-LINT-OVERLAY-REGEX, UI-DRAWER-RESIZE) | `cd42dfce` | open, base `dev` | review and merge (one `dev` merge behind) |
| #8875 ST-VIEWS | `24647c0a` | draft; both views equal to the resident path on 126,092 replayed minutes each | wiring under the multitenant `serve` roles (alpha); one `dev` merge behind |
| #8857 registration | `10fe6725` | draft; product-as-address built | D-REG-FLAG and the upload-role question are the maintainer's |
| BF-72, BF-161 advisory forks | local `0fdf0fd6`, `0873f314` | `dev` `305a6533` merged and re-tested; **not pushed** (forks still `a9da33ff`, `1dce7722`) | push, then merge `dev` `368e6c23` once more before the tag; maintainer |
| #8855 Crowdin | `6a2e84ab` | behind `dev` | update branch, merge; maintainer |
| `master` protection, #8824 | — | protection still requires `Run Tests (22, 4.4)` | the decided settings change (only *Tests pass* and one approval), then #8824; maintainer |
| Release 2 | `proto/v3-unify` `3b7f054a` (local) | Q-A adopted 2026-10-30; Q-U decided; Q9 recorded | write step resolves filter writes to ids; one write shape for v3; session -7d's labs |

**Update, 2026-11-01, ID-RESEND-SWITCH in review** (session -4e): the maintainer opened **#8892** (`WRITE_RESEND=replace|merge-except-treatments|acknowledge|refuse`, `WRITE_DELETED_RESEND=stay|revive`; head `a55c940d`, `dev` `f54941b5` merged in). Gates at `a55c940d` (in the PR body): the write-contract matrix on MongoDB 7.0.43 with `--batch`, 4,916 cells: both settings unset, 0 cells differ from a `f54941b5` pin (the `f54941b5` and `4196dd45` pins differ by 0 cells, so #8881 moves none); `refuse` moves the same 813 cells as at `405c6cee`, none of whose re-sends writes; tiers unit 2077 and integration 3519 (1 pending), 0 failing on Node 22.23.4 and 24.22.1; lint 0 errors. Break-it: 14 of 14 red at `405c6cee`, not re-run after the `dev` merge. Per-client D20 quirks are a seam only (`writeSettings.resendModeFor(env, client)` returns the site setting for every client). Session -d1 has stopped; ID-UNIQUE-INDEX passes to another session on this machine (handoff `externals/work/HANDOFF-d1-2026-11-01.md`), which stacks on `a55c940d` and wires Q-IDX through `resendModeFor`.

**Update, 2026-11-01, after #8892 opened:** hosted CI re-read at 07:21Z: all required checks completed successfully, including Maintained MongoDB and Chromium/Firefox/WebKit. The local unset/refuse matrix arms completed against `f54941b5` and independently show 0 and 813 changed cells outside cache noise. The next critical path is Q-IDX in local `feat/id-unique-index-5a` (`44750011`): prior `npm test` 6035/0/3 and matrix gates predate #8892, so rebase onto the PR head after it lands, make duplicate-key race losers follow `writeSettings.resendModeFor`, add mode-specific race tests/controls, and rerun before opening the index PR. The remaining ID-BATCH work is local `feat/id-batch` (`4b48e57f`), stacked on the index and 91 commits behind current `dev`; rebase and test it after the index. The ID-STRICT-V1 and opt-in per-item reply format are already in #8889.

**Update, 2026-11-01, after Q-IDX validation and #8893 closure:** #8892 remains open and all required hosted checks pass. The canonical ID-UNIQUE-INDEX PR is draft **#8894**, head `2d7411d6`, stacked on #8892. Its base `feat/id-resend-switch` is outside the `pull_request` filters in `main.yml` and CodeQL, so only auto-close has run; retarget it to `dev` after #8892 merges to trigger hosted feature CI. Earlier draft #8893 was closed as superseded. Local validation on #8894's head: `npm test` 6,319 passing / 3 pending; focused identity-race/settings suite 63 passing; test-tier and write-intent gates pass; lint 0 errors and 20 warnings. Treatment mode tests reached the actual duplicate-key path in 24–30 of 30 rounds per mode. Batch-only matrix: all 13 forms (312 cells) compared index off/on under default on MongoDB 5.0.32 and 8.0.29; 33 expected differences (24 `batch-dupkey-mid`, 9 `batch-repeat-identifier`). The same 33 differences appeared for those two forms under `WRITE_VALIDATION=reject` and `WRITE_IDENTIFIER=strict`. The historical 24-cell result was pinned at `982de025`; the current 9 additional cells are from `batch-repeat-identifier`, so keep the pin results distinct. Broader `--batch --no-idf` matrix runs were stopped, not completed. The remaining `feat/id-batch` worktree is clean at `4b48e57f` (17 ahead/91 behind `official/dev`); it still needs rebasing and full verification after #8894 lands. The older `proto/id-batch-replies` worktree (`7d81e1c1`, 1 ahead/119 behind) is prototype-only, not the integration branch.

**Current correction, 2026-11-01:** #8892 merged as `3c773ee5`; #8894 then merged from head `cf978f4` to `dev` as `497d08c94c0a583f056fe487d172a4634fc4a1d4`. All required PR hosted checks passed. The two post-merge CI runs then exposed separate failures: run 41326509441 failed `tests/api.entries.test.js` because the cache-read test assumed its seeded record was `ctx.cache.entries[0]`; run 41326514941 failed D21 in `tests/start-paths.test.js` because equivalent index states were reported as `built` versus `present`. PR #8896 merged both test stabilizations as `61eb37335954ae42c91345a0823bd67331025165`: the entries test finds its fixture by `_id`, and the startup comparison normalizes those equivalent states. All required #8896 checks passed, including MongoDB 5.0/8.0, browsers, Docker and CodeQL; post-merge runs 41333677576 and 41333672054 also succeeded. The focused entries suite passes 32 tests on the pre-#8896 local tree, and the same-seed integration/stress replay passed (3,567 passing / 1 pending; stress 18 passing). No separate test-fix PR is needed. API v1 per-item results and strict-v1 behavior shipped in #8889; #8894 adds the unique index and index-dependent duplicate-key retry, including batch races. The stale local `feat/id-batch` branch should not be rebased wholesale: per-item reply contracts and item-level race behavior are already covered by `tests/api.id-batch-replies.test.js` and `tests/api.batch-race-item-level.test.js` on the merged branch. Carry forward only a specific uncovered case if further review identifies one. The broader `--batch --no-idf` matrix is complete on the merged tree: each off/try lane had 3,443 cells and zero invalid cells, with complete wire capture (929/929 frames, zero unattributed frames or settle-bound hits). Off-versus-try produced the 33 expected batch differences (24 `batch-dupkey-mid`, 9 `batch-repeat-identifier`) on both MongoDB 5.0.32 and 8.0.34; remaining differences were cache-only (15 cells on MongoDB 5, 5 on MongoDB 8). Cross-version comparisons differed only in cache fields (7 cells off, 11 try). A separate fresh v15.0.9-to-merged-dev comparison remains incomplete and unclassified. Merged dev uses `WRITE_IDENTIFIER_INDEX=off` only to allow intentional duplicate-state fixtures; default `try` index startup and races remain separate evidence.

**Final compatibility comparison, 2026-11-01** (supersedes the interim in-progress status above): the fresh comparison is complete and classified in the [compatibility report](../../site/pages/cgm-remote-monitor-16.0.0-write-compatibility.html) and [release colophon](../../site/pages/cgm-remote-monitor-16.0.0-colophon.html). Two runs of each endpoint recorded 4,916 cells; the repeat runs differed only in cache/wire (81 baseline and 19 merged-dev cells). Of 2,803 changed cells, 0 are unexplained and none have the `Defect` verdict. The split is 347 changed before the historical pre-identity dev anchor, 2,107 after it, and 349 in both intervals; 1,886 cells concern identifier format. Six `ws idread-fail` cases are excluded because that injected failure does not exist on 15.0.9. The 2026-10-31 baseline pin differs by 23 batch cells outside cache/wire and is not used for repeatability.

**Update, 2026-11-01** (session -d1, from GitHub): the maintainer merged **#8881** (ST-HARNESS: backend-selectable harness, backend selection, tenant scope; head `993275f3`) as `f54941b5`; `dev` is `f54941b5`. The three open 16.0.0 PRs of the day are merged in the agreed order (#8890, #8889, #8881). Remaining identity work: ID-RESEND-SWITCH (session -4e), ID-UNIQUE-INDEX (session -d1; local `44750011`, `npm test` 6035/0/3 on `dev` `4196dd45`), then the ID-BATCH remainder. Session -81 re-pins the batch-only matrix (312 cells; MongoDB 5.0.32 and 8.0.29; default, reject and strict) on `f54941b5` as the base for the index PR; the `abadc40a` pins are not landed (they predate compatibility A/B).

**Update, 2026-11-01, about 06:05Z** (session -d1, from GitHub): the maintainer merged **#8889** (ID-STRICT-V1, per-item API v1 batch replies behind the `Nightscout-Write-Results` opt-in, the BF-219 test fix and the CodeQL type-confusion fix; head `422796db`) at 06:01Z as `4196dd45`; `dev` is `4196dd45`. CodeQL alert 140 closed as fixed by the patch (no dismissal). Next: #8881, then ID-RESEND-SWITCH, ID-UNIQUE-INDEX and the ID-BATCH remainder.

**Update, 2026-11-01, ST-VIEWS replay re-check on `dev` `1fc6d8be`** (session -81, 02:57–04:42Z; #8875 merged after #8886; the recorded procedure in `tests/lib/views-replay/RESULTS.md`: MongoDB 7.0.43 in a dedicated container, Node 22.23.4): the alarms and properties views, each as-is and with profiles at start, differ from the resident path in 0 minutes of 126,092 each; release 2's noise floor is 0 on all of them. The controls (`run-controls.sh`: tamper, shrunk treatments 4 h and 24 h, device status 0.5 h and 6 h) are red and silent on the same datasets as on the recorded final tree, with the same counts except one: shrunk treatments 4 h on corpus dataset #6, 1156 differing minutes against the recorded 1146 (+10, not traced). Control counts measure sensitivity, not equality. Not run: the properties-specific controls. Outputs kept out of the repository (they carry corpus values).

**Update, 2026-11-01, about 04:30Z** (session -d1, from GitHub): the maintainer merged **#8890** (compatibility cards A and B, B extended, with BF-225 part C and the Q-A `WriteResult.updated` commit; head `145d55d2`) at 04:29Z as `5921d5fd`; `dev` is `5921d5fd`. Gates on `145d55d2` (session -4e, in the PR body): the write-contract matrix on MongoDB 7.0.43 with `--batch`, 4,916 cells, 0 differing from the hashed prediction (the Q-A commit moves 0 cells, and #8875 moved none); tiers unit 2039, dom 205, dependency 368, core 319, harness 80, integration 3266, stress 18, 0 failing on both Node versions; lint 0 errors; the Q-A tests red on `db785fd3` and under break-it (10). With Q-A, a treatment replace also names its record in `WriteResult.updated`. Merge order agreed for the rest (session -d1, 2026-11-01): #8889 (ID-STRICT-V1 and the opt-in header; a `dev` merge and full re-run first, since card A changes what `WRITE_IDENTIFIER` unset means), #8881 (ST-HARNESS, independent), then ID-RESEND-SWITCH, ID-UNIQUE-INDEX (its race retry reads the re-send mode, Q-IDX) and the ID-BATCH remainder. The index branch is local `feat/id-unique-index-5a` `982de025` on `5921d5fd`: the profile, food and activity item-level race retry, its race paths following the table's `replaced` (card B, extended), and race tests that assert `WriteResult.updated`; *later*, at `982de025` (`dev` `5921d5fd` merged in): `npm test` 6008/0/3 (MongoDB 5.0); the write-contract matrix against the `db785fd3` pin (equal to #8890's, which moves 0 cells) on MongoDB 5.0 and 8.0 alike: index off, 0 of 4,916 cells differ outside `cache`; index on against index off with the same flags (`--batch --no-idf`, since the identifier cells seed shared identifiers straight into MongoDB, which the index refuses), 24 cells, all `batch-dupkey-mid` (one record holds the identifier) and `batch-repeat-identifier` (food and activity keep one record; profile stores the second copy without the identifier, the slice 6 copy rule), no status or body cell. The 26 further `v1read`-only cells against the full pin are the `--no-idf` run's shifted clock (reproduced with the index off). It waits for ID-RESEND-SWITCH, then Q-IDX. A finding from the compatibility matrix (release 2 changed hard-delete announcements for numeric and custom `_id`s) was probed by session -81: no stale cache on `dev` `1fc6d8be`, and release 2 removes a base-side drop of a live record from the cache; nothing filed.

**Update, 2026-11-01, about 02:30Z** (session -d1, from GitHub): the maintainer merged **#8886** (`write(intent)` release 2 and the D-EVENT per-write event; head `4b8adfec`) at 02:28Z as `51d38f9f`; `dev` is `51d38f9f`. It fixes BF-226 (autoPrune cache flush without reload). Both releases of the write step and the event are on `dev`, inside the open cohort window. Remaining 16.0.0 code: the compatibility follow-up PR (BF-225 C, compatibility B, A, extended B; session -4e), `WRITE_RESEND`/`WRITE_DELETED_RESEND`, the unique index with `drop` (local `ed5b9fc9`), ID-BATCH (local `4b48e57f`); #8875 (ST-VIEWS, unwired) and #8857, #8881 as drafts. Before the tag: cohort checks, the BF-72 and BF-161 forks brought up to `dev`, `master` protection, release notes.

**Update, 2026-11-01, about 01:35Z** (session -d1, from GitHub): the maintainer merged **#8879** (identity, slices 1–6a with the 2026-10-31 socket decisions; head `2d79d30b`) at 01:26Z as `164e6ae8`, and **#8888** (BF-225 fix B; head `3bb6627f`) at 01:29Z as `5376e6a7`; `dev` is `5376e6a7`. Slices 3 and 4 are on `dev`: **the cohort window for `write(intent)` release 1 and the identity work opens now** (one window over #8874 and the identity landings). **#8886** (release 2 + D-EVENT event) is retargeted to `dev` and out of draft at `4b8adfec` (0 behind, 18 ahead; CI pending at the read). Next: the compatibility follow-up PR (BF-225 C, compatibility B, A, extended B) rebased onto `dev`; then `WRITE_RESEND`; then the unique index (local `ed5b9fc9`, with `drop`) moved onto that head; then ID-BATCH (`4b48e57f`). Still owed before the tag: BF-72 and BF-161 fork refresh, `master` protection, release notes.

**Update, 2026-10-31, late** (session -d1): the maintainer adopted three compatibility decisions for 16.0.0 from the [write compatibility page](../../site/pages/cgm-remote-monitor-16.0.0-write-compatibility.html) ([decisions](decisions.md)): **A** API v3 refuses only a blank or numeric identifier with 400 by default, as 15.0.9 did (corrected the same night: option i); **B** a matched re-send replaces on every collection; **C** `WRITE_RESEND` is built before the tag. BF-225's fix scope is decided (B on `dev`, C on #8879). Order (session -4e's lane): BF-225 fixes; compatibility A then B on `feat/id-compat-restore-ab`, shipped with BF-225 C as one follow-up PR after #8879 merges as it is; then `WRITE_RESEND`; then the unique index's last move onto that head, then ID-BATCH. Release 2 (#8886) re-checks its outcome words after B.

**Update, 2026-10-31, about 22:00Z** (read from GitHub with `gh pr list`, `gh pr checks` and `gh api .../compare/dev...<head>` by session -d1; `dev` `604de1cb`):

| PR | head | base | against `dev` `604de1cb` | CI | state |
|---|---|---|---|---|---|
| #8879 identity, slices 1–6a | `2d79d30b` | `dev` | 0 behind, 21 ahead | 16 passed, 3 skipped | ready for review; merging it opens the cohort window |
| #8886 `write(intent)` release 2 + D-EVENT event | `6b00eb9d` | `feat/id-first-match` (#8879) | 0 behind, 38 ahead | 1 check (PR workflows run for base `dev`) | draft; lab, controls and revert to re-run on this head; retarget to `dev` after #8879 |
| #8875 ST-VIEWS (ships unwired) | `7b4b724c` (later `52d635a0`, a GitHub `dev` merge, CI green) | `dev` | 5 behind, 18 ahead | 16 passed, 3 skipped | draft |
| #8857 registration S0–S2, S5 | `10fe6725` | `dev` | 44 behind, 15 ahead | 16 passed, 3 skipped | draft |
| #8881 ST-HARNESS | `ffa5e6b4` | `dev` | 19 behind, 7 ahead | 16 passed, 3 skipped | draft |
| #8810 AndroidAPS iOS push | `37146a1f` | `dev` | 84 behind, 5 ahead | 16 passed, 3 skipped | review items open |
| #8824 `dev` to `master` | `604de1cb` | `master` | — | — | blocked by `master` protection |

**Historical note:** The pinned 2026-10-31 comparison below predates the merged-16.0.0 result. The fresh comparison is now complete: v15.0.9 and merged dev each have two 4,916-cell runs, with 2,803 classified changes and zero unexplained cells. The retained 2026-10-31 v15.0.9 pin differs from the fresh baseline in 23 batch cells outside cache/wire and is not used as a repeat.

**15.0.9 → #8879 compatibility, measured** (session -4e, at the maintainer's request): write-contract matrix on `v15.0.9` `c6a0d8ed`, `dev` `37b2280f` and #8879 `6960bfb7` (MongoDB 7.0.43, since 15.0.9's driver 5.9.2 predates 8.0; Node 22.23.4; defaults; two runs per tree, 0 flaky): 4,916 cells per tree, 2,947 differ from 15.0.9, 0 unexplained; 376 differ only on `dev`, 2,230 only with #8879, 341 in both; 1,924 of them are identifier-format cases (ID-Q6). The only defect found is BF-225 (3 cells). Results, data and refresh steps: the living page [16.0.0 write compatibility](../../site/pages/cgm-remote-monitor-16.0.0-write-compatibility.html), from `releases/cgm-remote-monitor-16.0.0/compat/` and `tools/qc/compat/`. Anchor drift noted: `lib/client/renderer.js:354` in the slice 4 decision row is the line at `dev` `ca1652d6` (`:240` on 15.0.9); Trio was read at `e41c9db3`; tconnectsync and AndroidAPS anchors have moved a few lines.

**BF-225** (filed by session -4e): a socket re-send of a treatment without an identifier stores a second copy when the stored one has an identifier, on `dev` since #8877 (`cf3d4b8f`), not on 15.0.9; in 16.0.0 (maintainer, 2026-10-31, via -4e). Correction: the v3-then-socket case was documented as intended in #8877; the UUID `_id` cases were not; fix scope decided (B on `dev`, C on #8879; a full revert rejected because it brings back BF-209's lost treatment); being built by -4e. Release-notes line owed (measured by -4e): on 15.0.9 a socket `dbAdd` array of three distinct treatments stored only one; #8877 fixed that. Release-notes line owed for "What you must do" (ID-UNIQUE-INDEX): before rolling back to 15.0.9 or any build before 16.0.0, set `WRITE_IDENTIFIER_INDEX=drop` and restart once (the log lists each index removed), then roll back; if already rolled back, drop `identifier_unique` by hand. A rollback to 15.0.9 ignores the setting, so the left-behind index would refuse a duplicate with a 500 where 15.0.9 stored it.

Local, not pushed: the unique index (moving onto 6a; its retry becomes item-level first), ID-BATCH (session -81, on the index), the one-person profile prototype (`908351d4`). Being reproduced, not filed: an API v3 autoPrune cache lead.

**Update, 2026-10-31, about 20:05Z** (session -d1, from GitHub): the maintainer merged **#8885** ("16.0.0 small backfixes": BF-223, a saved API secret the site refuses blocks a valid `?token=` link; BF-224, a plain-value v1 date filter answered 500) at 19:57Z as `604de1cb`; `dev` is `604de1cb`. **#8879** is out of draft at `2d79d30b` (slices 1–6a with the 2026-10-31 socket decisions; `dev` `604de1cb` merged; 0 behind, 21 ahead; CI 16 passed, 3 skipped) and is next for review; when it merges, slices 3 and 4 are on `dev` and the cohort window opens. The unique index moves onto it next (session -d1), then ID-BATCH (session -81). Write-step release 2 is rebased onto slice 6a (local `c80c16eb`, gates green). A cache lead from the release 2 lab (autoPrune leaving the cache short on `dev`) is being reproduced, not filed.

**Update, 2026-10-31, evening** (session -d1; `dev` still `37b2280f`):

- **ST-VIEWS** (maintainer, [decisions](decisions.md)): #8875 ships in 16.0.0 unwired; the one-person profile with nothing resident is prototyped on a branch (session -81); the tenancy × execution framing goes into the next-gen plan as a design question. The views branch with `dev` `37b2280f` merged is local `feat/views-serve` `7b4b724c` (replay 0 differing minutes on 126,092, `npm test` 5355/0/3); #8875 on GitHub is still `24647c0a`.
- **ST-VIEWS-PROFILE prototype** (session -81, not for 16.0.0 unless it clears the bar): local `proto/views-nonresident` `908351d4` (measured head; `80e1ee30` earlier) on `7b4b724c`, now draft **#8891** (`feat/views-profile` `744d1968` on `dev` `f54941b5`, opened with provisos), an opt-in `views` profile (`NIGHTSCOUT_EXECUTION=nonresident`) with no data loader or cache, triggered by the counts-only write event and the heartbeat; `single` with the opt-in set stays resident (tested). Alarms: 24 of 24 replay runs, 126,092 minutes, 0 differing; every replayed upload fired a write event. Properties: 20 of 24 runs, 0 differing except one synthetic two-uploader timeline (5 of 2,881 minutes, `sensorState.notification` only: the xdripjs plugin's last-state notification is consumed by the alarm pass first; a design question with the maintainer). §7b alarm checks 15 of 15; controls red for the right reason; revert clean; cost not yet measured.
- **ID-UNIQUE-INDEX** on slice 4: local `d0f2f70a`, 342 of 342 predicted cells on MongoDB 5.0 and 8.0, approved by session -4e; being moved onto `5a251213` with a mixed-batch test.

**Update, 2026-10-31, about 17:50Z** (session -d1; `dev` still `37b2280f`):

- **#8879's `dev` merge is ready to push** (session -4e): local `feat/id-first-s4r` `5a251213` = merge `5bf94c8b` (`f5bd2642` + `dev` `37b2280f`) plus a test for the batch-index mapping (`tests/api.entries.batch-deleted-and-taken.test.js`); fast-forwards the PR head; 0 behind `dev`, 13 ahead. The four expected conflicts kept both sides; the matrix (4,604 cells, MongoDB 8.0) moved 0 cells outside `cache` and `wire`; every tier green on Node 22.23.4 and 24.22.1; the merge revert gives `f5bd2642`'s tree. The maintainer has the push commands. The matrix has no cells for BF-219..222 (coverage gap, no BF id).
- **Slice 6 decisions** (maintainer, 2026-10-31; [decisions](decisions.md)): socket treatments replace on an identifier match, as every other path does; the profile rule (a different `startDate` is a new profile without the copied identifier) extends to the socket. Both go in the [compatibility notes for affiliated projects](../../docs/30-design/platform/upstream-asks-controller-authors/socket-paths-compat-notes.md) (draft, unsent). Slice 6 and 6a are being built on `5a251213`.
- **BF-223** (a saved API secret the site refuses blocks a valid `?token=` link; also on `v15.0.9`): ready to push on local `bf/16.0.0-stale-secret-hash` `ecbc9c06` (main page and clock views); the clock bundle allowance moves by 43 gzip bytes, for the maintainer to accept.

**Update, 2026-10-31, about 16:40Z** (GitHub, session -d1): the maintainer merged **#8883** at 16:30Z as `2f50d944`
(head `789d5d9d`: BF-219, BF-220, BF-221, BF-222) and **#8882** at 16:33Z as `37b2280f` (head `32cd90e6`:
DEV-LINT-OVERLAY-REGEX, UI-DRAWER-RESIZE). `dev` is `37b2280f`. Not released. Next on the merge order: #8879, which
needs `dev` `37b2280f` merged in (the four-file conflict with #8883; session -4e), then slices 6 and 6a, then out of draft.

**Update, 2026-10-31, about 16:20Z** (read from GitHub with `gh pr list`, `gh pr checks` and
`gh api .../compare/dev...<head>` by session -d1). `dev` is still `368e6c23`; nothing merged since #8874. Every open
16.0.0 PR is green on every CI job:

| PR | head now | against `dev` `368e6c23` | CI | changed since the 05:45Z table |
|---|---|---|---|---|
| #8883 | `789d5d9d` | 0 behind, 7 ahead | green | none; ready for the maintainer's review, merge first |
| #8879 | `f5bd2642` (draft) | 0 behind, 11 ahead | green | the lint failure is fixed (`f5bd2642`); slices 6 and 6a not yet pushed (local `prep/id-first-s6` `47377fa3`) |
| #8882 | `7a6b0283` | 0 behind, 4 ahead | green | the drawer-resize handler registers at the first open (`2737756d`), so the browser-less test passes; `dev` merged in. Ready for review |
| #8881 | `ffa5e6b4` (draft) | 0 behind, 7 ahead | green | — |
| #8875, #8857 | `24647c0a`, `10fe6725` (drafts) | 25 behind each | green | — |
| #8855 | `6a2e84ab` | — | — | — |

**Historical pre-tag assessment at this table's read:** private branch refresh,
`master` protection and the cohort window were outstanding. **Current correction,
2026-11-01:** BF-72/BF-161 now contain `61eb3733`, but private targeting and
full-suite acceptance remain blocked; protection and live/cohort gates remain.

**Update, 2026-10-31, about 05:45Z** (read from GitHub with `gh pr list`, `gh pr checks` and
`gh api .../compare/dev...<head>` by session -7d; every local branch matches its PR head, and every worktree is clean):

| PR | head now | against `dev` `368e6c23` | CI | changed since the table |
|---|---|---|---|---|
| #8883 | `789d5d9d` (pushed; title names BF-222) | 0 behind, 7 ahead | 13 passed, 2 pending | the push is done; merge before #8879 |
| #8879 | `931e5e60` | 0 behind, 10 ahead | lint fails: `no-useless-assignment` at `lib/storage/write-intent.js:1450` | slice 4 (merge on match, treatments `replaced` on every path) pushed |
| #8882 | `cd42dfce` | 25 behind | 4 failing: the browser-less test of `browser-utils` stops with `window is not defined`, because the drawer-resize listener (`lib/client/browser-utils.js:138`) runs when the module loads | **not ready to merge** until that commit guards for a missing `window` |
| #8881 | `ffa5e6b4` | 0 behind | green | — |
| #8875, #8857 | `24647c0a`, `10fe6725` | 25 behind each | green | — |
| #8855 | `6a2e84ab` | 299 behind | — | — |

Queued, unowned: QC-MATRIX-WIRE-ATTRIBUTION, UI-STALE-SECRET-HASH. BF-222's fix is in #8883 (BFQ-222).
Upstream drafts, unsent: AndroidAPS 410 handling, tconnectsync profile copy
(`docs/30-design/platform/upstream-asks-controller-authors/`).

In flight on 2026-10-30 (read about 02:30Z with `gh pr view` and `gh api .../compare`, and again later on 2026-10-30 for the rows marked *later*; work not yet in a PR
is read from the plan, the [ID-FIRST-MATCH design note](../../docs/30-design/platform/id-first-match-design-note-2026-10-29.md)
and the queue):

| work | branch or PR | head | state | queue |
|---|---|---|---|---|
| `write(intent)` release 1: every v1, API v3 and socket write path through one write step, no behaviour change except BF-165's `_id` in the fallback-key re-send reply | `feat/write-intent`, **#8874** (base `dev`, opened by the maintainer 2026-10-28; *later* 2026-10-30: out of draft at `9919f8ef`) | `9919f8ef` (*later*): `4f9fc4cd` (2026-10-30 02:06Z, a merge of `dev` `991b0654`; 20 commits, 27 files, +7187/−1531 against `dev`) plus one commit adding only cgm-remote-monitor's architecture note `write-intent.md` | slices 1–6 built; slices 4 (API v3) and 6 (socket treatments, devicestatus, profile) released by the maintainer 2026-10-29, slice 6 with its extra dedupe gate. On the push-ready head `e8224807` (17 commits on `dev` `e1f7ac41`, 2026-10-29): the write-contract matrix differs from `dev` in 0 cells, the revert was rehearsed, `npm test` 5106/0/3 against `dev`'s 4759/0/3 (read from the queue). CI on `4f9fc4cd`: `pull_request` run 40990198561 and CodeQL passed. *Later*, measured by session -4f at `4f9fc4cd` against `dev` `991b0654`, run one after the other: `npm test` 5206/0/3 against `dev`'s 4917/0/3 (+289 titles, none removed or renamed); tiers 415 files ok; the write-contract matrix (1,929 cells) differs in 0 cells outside `cache` and in 1 cell in `cache` only, no earlier cell differs (pin `tools/qc/results/write-contract-matrix/dev-991b0654-idfirst.json`); the commit-event copy (360 cells) 0 differing, from an earlier overlapping pair, not re-run. The merge revert was rehearsed at `4f9fc4cd`: the reverted tree equals `dev`'s (`a9ae9536`). The PR body names the merge revert as the supported revert; a commit-by-commit revert conflicts after the `dev` merges and, forced, drops BF-209. Needs the maintainer's review and merge; the cohort check below starts at the merge. First in the entry-bar order; not yet through the bar | `WC-STEP-PATCH` |
| ID-FIRST-MATCH: identifier-first on every collection and path, as slices in the order 1 (no outcome change, with the two additive items), 2 (identifier format), 5 (shared identifiers, BF-212's pick), 3 (stays deleted), 4 (merge on match), 6 (identifier first where it is new), 6a (activity) | **draft #8879** (*later* 2026-10-30, base `feat/write-intent`, head `feat/id-first-match` `521e7583`): slice 1 gated, 4 commits on `9919f8ef`; slices 2, 5, 3, 4, 6, 6a follow as commits; design note 2026-10-29 | — | slice 1's gate: the 456 earlier cells unchanged, and among the new cells only the two additive items' cells, predicted by id before the run (about 24 activity cells), with UUID handling on and off. The rules are decided (D-LOOP-ID rules 1–3, ID-Q1..ID-Q11, 2026-10-29); each slice goes to the bar on its own. Slice 1 moves 0 of 1,929 matrix cells; slices 3 to 6a change outcomes (40, 232, 112 and 33 cells, read from the design note's predictions) | `ID-FIRST-MATCH`, `ID-VALIDATE` |
| the `WRITE_*` settings: `WRITE_RESEND=replace\|merge-except-treatments\|acknowledge\|refuse`, `WRITE_DELETED_RESEND=stay\|revive`, `WRITE_IDENTIFIER=lenient\|strict`, `WRITE_DELETED_EDIT=ignore\|refuse`, `WRITE_IDENTIFIER_INDEX=try\|require\|off\|drop`; default first in each | ID-RESEND-SWITCH: **#8892 merged**; ID-UNIQUE-INDEX: **#8894 merged** | `3c773ee5` / `497d08c9` | #8892 and #8894 hosted checks pass. Unknown values refuse to start. Per-client D20 overrides remain unimplemented. | `ID-RESEND-SWITCH`, `ID-VALIDATE`, `ID-FIRST-MATCH`, `ID-UNIQUE-INDEX` |
| ID-UNIQUE-INDEX: partial unique index per collection, duplicate report and item-level retry-as-resend | #8894 merged as `497d08c9` from `cf978f4` | `497d08c9` | Local gates and required hosted checks passed. `try` reports duplicates and continues without the index; it does not clean records. The completed 3,443-cell `--batch --no-idf` off/try lanes have zero invalid cells on MongoDB 5.0.32 and 8.0.34; each shows the same 33 expected batch differences, with only cache-field noise beyond those. | `ID-UNIQUE-INDEX` |
| ID-BATCH: API v1 per-item replies and strict-ID behavior; index-dependent duplicate-key retry | #8889 and #8894 merged | `4196dd45` / `497d08c9` | #8889 provides the opt-in result format and strict-v1 behavior; #8894 adds the race retry. The old local `feat/id-batch` worktree is not a separate release-critical PR. | `ID-BATCH-RESULTS` |
| the re-send switch (D-LOOP-ID rule 3): site settings plus future per-client D20 overrides | **#8892 merged** | `3c773ee5` | Unset preserves `replace` / `stay`; 0 matrix cells differ outside cache noise. Site modes shipped; per-client overrides remain unimplemented. | `ID-RESEND-SWITCH` |
| SPEC-ID-AMEND: the identity specification and conformance cases (mandatory identifier on registered instances; API v3's refusal of a client `_id`) | alignment repository, branch `spec/id-amend-2026-10-30` (*later* 2026-10-30: an agent of session -49 is building it) | — | spec and conformance only; no site behaviour (plan item) | — |
| controller registration S0, S1, S2, S5, off by default | **draft #8857** | head `5f6c1275`; `BEHIND` current `dev` `497d08c9`; PR checks on this head are green | rebase/resolve against current `dev`, settle D-REG-FLAG (where the catalogue lives), then rerun the entry-bar checks | `HUB-REG-CRM` |
| ST-HARNESS: a backend-selectable test harness | not started | — | plan item, after `write(intent)` | — |
| ST-EVENT and ST-VIEWS, if they clear the bar | ST-VIEWS: **draft #8875** (`a0470a72`, not wired in) | — | ST-EVENT: D-EVENT deferred 2026-10-27, research continuing. ST-VIEWS: wiring is the maintainer's call, with alarm cohort checks; the alarms are safety-relevant. *Later* 2026-10-30: proposed to the maintainer, not decided: use the views only under `serve` (multitenant alpha) and leave `single` on the resident path, deciding a single-tenant switch from evidence. The maintainer asked for that evidence from labs: a time-stepped replay lab (minute by minute over days of the corpus and synthetic fixtures, with acks, snoozes, two uploaders and the lookback edges, a resident-vs-resident noise floor and the drop-query and tamper controls) is being built by an agent of session -49 on local `lab/views-replay` | — |
| multitenant items (tenant configuration, resolution, tenant-scoped credentials, PostgreSQL) | — | — | optional for 16.0.0: they may ship dormant, labelled alpha behind `serve` (which refuses every role today), or not ship | — |
| BF-72 and BF-161 through their private advisory process | private, no public PR | both refreshed fixes contain public dev `61eb3733` | **Current 2026-11-01: BLOCKED.** Combined focused tests passed 402; full-suite MongoDB validation is inconclusive and private PR targeting rejected an invalid base. No merge/publication. Dated older branch evidence below is historical. | `BFQ-72`, `BFQ-161` |
| Crowdin translations | `crowdin_incoming`, **#8855** (sulkaharo) | `6a2e84ab` (updated 2026-10-29 20:31Z): 33 files, +1448/−491 | open; `mergeable` reads `UNKNOWN`; not examined; §1a row 3a, low risk | — |
| `master` protection and the staging PR #8824 | repository settings | #8824 at `991b0654` | `master` still requires `Run Tests (22, 4.4)`, which no workflow on `dev` emits; the decided change (only *Tests pass* and one approval) is owed, then #8824 merges and the tag is cut | `RT-16-RELEASE` |

### Cohort check for `write(intent)` release 1 (#8874)

Owned by session -49 (plan owner) from 2026-10-30; the writer list is session -4f's. Since the maintainer's
2026-10-30 decision it is one window over #8874 and identity landings A, B and C together, opened when B
lands, rather than a week per item. Testers on `dev` report any duplicate or missing treatment, device status or
profile, by the path their uploader writes through, because those are the paths the write step now carries:

| path | writers to cover |
|---|---|
| socket | AndroidAPS 3.4.2.x with the v1 NSClient; the web chart's *Move insulin* and *Move carbs* drag |
| API v3 | AndroidAPS NSClientV3; nightguard |
| REST v1 | Loop, Trio, xDrip+, nightscout-connect, the careportal |
| identity landing B (slices 3, 4) | Loop and Trio re-sending changed doses, overrides and temporary targets; re-sends after a delete |
| identity landing C (6, 6a, index) | activity writers; sites whose start-up log or status page reports duplicate identifiers under `WRITE_IDENTIFIER_INDEX=try` |

One volunteer runs `WRITE_VALIDATION=reject` and compares the treatments in their app with the site. Read from
the clients' code by session -4f ([ID-BATCH design note](../../docs/30-design/platform/id-batch-design-note-2026-10-30.md)),
not reproduced: under `reject`, a refused treatment in a v1 batch keeps its reply slot with a `refused` member
and no `_id`; Loop counts a slot without `_id` as uploaded, and Trio and xDrip+ check only the status, so all
three treat the refused treatment as uploaded and do not re-send it. This is behaviour on `dev` today, not
introduced by #8874.

*Rows as recorded to 2026-10-28* (read 2026-10-26, 19:10Z; #8854, #8856 and #8859 updated at 22:13Z; BF-72, BF-161, the CI test fixes, #8864 and the next-gen drafts on 2026-10-27). Every cut is merged
([Merge state](#merge-state)); #8854 is merged ([What is merged so far](#what-is-merged-so-far)).

| work | branch | head | state | queue |
|---|---|---|---|---|
| Crowdin translations | `crowdin_incoming`, **#8855** (sulkaharo) | — | opened 2026-10-26 18:52Z; not examined | — |
| BF-72: a caller-supplied regular expression can hold the database for minutes | `bf/regex-limits` in the private fork of its draft advisory (fork head `532d7d7a`, on `dev` `b29f1bf7`); locally `adv/r3gv-1600` | `a9da33ff` on `adv/r3gv-1600-dev`: `dev` `9668b179` and then `7abe1cf6` merged into the fork branch (`f64f78c4`, already on the fork); **pushed to the fork by the maintainer 2026-10-27** as `bf/regex-limits` `a9da33ff` | in the fork; no fork PR opened yet. 2026-10-27, after #8861, #8863 and #8870: the conflicts resolved as on the candidate, and the read time limit carried onto #8870's single count path; `npm test` 4776 passing, 0 failing, 3 pending; `test:all` 5104 passing, 0 failing, 3 pending (Node 22.23.4, MongoDB 8.0.34); removing the limit from the count path fails the count test | `BFQ-72` |
| BF-161: a deeply nested pattern on three query endpoints makes that request fail | `bf/entries-pattern-limit` in the private fork of its draft advisory (fork head `0e06a36b`, on `dev` `b29f1bf7`); locally `adv/phrf-1600` | `1dce7722` on `adv/phrf-1600-dev`: `dev` `9668b179` and then `7abe1cf6` merged into the fork branch (`8dcf1537`, already on the fork), no conflicts; **pushed to the fork by the maintainer 2026-10-27** as `bf/entries-pattern-limit` `1dce7722` | in the fork; no fork PR opened yet. 2026-10-27: `npm test` 4714 passing, 0 failing, 3 pending; `test:all` 5042 passing, 0 failing, 3 pending; the fix's test file 48 passing | `BFQ-161` |
| the CI pull request: three intermittent test fixes, the MongoDB wait, image publishing, nodemon | `test/16.0.0-ci-flakes`, **#8866** (into `dev`; #8867 merged into it as `7a96b912` at the maintainer's request, 2026-10-27) | `7a96b912`: `c7857735` (concurrent-writes: Notes one second apart), `bdd569a3` (page-startup: the reports page is ready once its first report has loaded), the maintainer's `dev` merge `ddeeff8c`, `65632082` (the dashboard round trip waits for each page before leaving it), and #8867's `56804908`, `04b1f870`, `5d9f84b5`, `e0cfbd0c` | **merged 2026-10-27 19:42:55Z by bewest as `dev` `b84871d7`** (head `f6884342`, after `f6884342` moved the MongoDB 8.0 jobs to `ubuntu-22.04`; both 8.0 jobs passed on `6.8.0-1064-azure` in run 40569981396). Earlier: `65632082` followed WebKit's `page.goForward: WebKit encountered an internal error` on run 40559261253; #8867 was merged in as `7a96b912` and closed at 19:28:02Z | `RT-CI-FLAKES-8DBB60C2`, `BFQ-201`, `BFQ-202` |
| WebKit's cached-bundle startup test, again | `test/16.0.0-reports-ready`, **#8869** (opened by the maintainer 2026-10-27, base `dev`) | `9a44e16f` on `dev` `eed31dca`: `tests/browser/page-startup.test.js` | **merged 2026-10-27 22:23:05Z by bewest as `dev` `b8baf24d`** (head `d9fca2de`, `dev` merged in). Earlier: the first controlled navigation waits for the reports page's first report, and a failure names the page each browser error came from. Not reproduced locally before or after; the cause is not proven, and the new line is there to name it on the next failure. page-startup 28 passing on WebKit, Chromium and Firefox | `RT-CI-WEBKIT-REPORTS` |
| BF-191: a stored treatment can stop the server process, and keeps doing so after a restart | private, through the maintainer's advisory process | — | open in the register | `BFQ-191` |
| BF-193: write paths log whole records | `bf/16.0.0-log-privacy`, **draft #8856** (the maintainer, base `dev`) | `6b6ad320`: one commit (`8ae43eb4`) and a merge of `dev` `7ad3a67f` | **merged 2026-10-27 20:09:35Z by bewest as `dev` `eed31dca`** (head `6c9af523`; `gh pr view 8856`). Earlier: draft PR opened 2026-10-26. `dev` `7ad3a67f` merged in as `6b6ad320` (session -66, no conflicts; pushed by the maintainer 2026-10-26, hosted CI 16 passed, 0 failed, 2 skipped): `npm test` 4436 passing, 0 failing, 3 pending; `test:all` 4764 passing, 0 failing, 3 pending | `BFQ-193` |
| the re-send and merge contract: `ID-SIMPLE-MATCH`, Q1b (a `null` in an update removes the field), BF-195 (a stale profile pushed over the socket after a re-send) and the devicestatus `identifier` rule, one PR | `bf/16.0.0-null-removes`, **draft #8859** (the maintainer, base `dev`) | `5c6ceabb`: five commits on `dev` `47723cda` and a merge of `dev` `7ad3a67f`: `ID-SIMPLE-MATCH` `8d0f9a22`, Q1b `913d0895`, BF-195 `1bdce62c`, merge `cf2a2a67`, the devicestatus `identifier` rule `fc170a4c` (read from `git log`) | **merged 2026-10-27 19:52:21Z by bewest as `dev` `94899828`** (head `87f1aeb8`, `dev` merged in; `gh pr view 8859`) | `ID-SIMPLE-MATCH`, `WRITE-CONTRACT`, `BFQ-195` |
| the IOB pill switching to the treatment-based value during a reconnect | AndyLow91's branch, **#8864** (base `dev`) | `4ed92673`: `lib/data/ddata.js` and a new `tests/data.reconnect-snapshot.test.js` | **merged 2026-10-27 16:55Z by AndyLow91 as `dev` `2dc0c1bc`** (`gh pr view 8864`); opened 13:02Z; read from the PR body, not run here: the socket's reconnect payload is read from the live `ddata` the loader is rebuilding, so a reconnect during a refresh can carry no device statuses and the pill falls back for that moment; the fix reads from the completed snapshot. The PR reports three new tests failing on the unmodified base, and 4 sensor-age failures under `TZ=Europe/London` that it reproduces on the base too. Display of a dosing-relevant value (cycle priority 2) | — |
| next-gen drafts: storage slices, one executable, `serve api`, registration | *Current 2026-10-28 01:15Z:* #8861 **merged** (`84fac457`) and #8863 **merged** (`9668b179`), both 2026-10-27; #8862 **closed** 2026-10-28 01:12Z as superseded by #8865; #8865 open, base `dev`, head `53ba192a`, on the 16.0.0 merge list (its own row below); #8857 open, draft, `f7a43fed`. *As first recorded:* #8861 (`5310a447`, draft), #8863 (`42128f3b`, on #8861, ready for review, pushed 2026-10-27), #8862 (`b63d9b7f`), #8865 (`1dafe2a5`, on #8863), #8857 (`f7a43fed`) | — | Decided 2026-10-27 (Q12): #8861 and #8863 go into 16.0.0 if they meet the [release allocation](../../docs/30-design/platform/release-allocation-2026-10-27.md) B6 entry bar; items 1, 3, 4 and 5 met on local candidates the same day (`cand/with` `d6ba8e18`: matrix, replay and v1 HTTP differential equal, no measurable latency change, one-commit revert restores `cand/without`'s tree), item 2 (BF-72 and BF-161 re-merged in their private forks) met locally the same day; #8859 and #8856 merged (`dev` `eed31dca`); the final heads re-measured on it: #8863 `npm test` 4700/0/3, `test:all` 5028/0/3, 360-cell matrix equal to `dev`; #8861 `npm test` 4685/0/3 (session -2e). Hosted CI has not run on #8863 (its base is not `dev`) and runs once #8861 merges; merge order #8861, #8863 (with the count commit `079f20ae`); #8856 resolved against the slices on `prep/writes-plus-8856` `699a70c4`. #8861 merged as `84fac457`, #8863 as `9668b179` and #8870 (`ST-COUNT-ONEPATH`) as `7abe1cf6` (dev, 2026-10-27, by the maintainer). It was planned before the tag (maintainer, 2026-10-27): one commit removing API v1 count's fallback paths in `lib/server/aggregate.js` (the constructor pipeline hook and the no-store driver path), unreachable over HTTP, so no client-visible change. #8862 if it merges with time on `dev` before the tag | `ST-FILTER-READS`, `ST-WRITES`, `PLAT-ENTRY`, `PLAT-SERVE`, `HUB-REG-CRM` |
| one executable, the image's start and stop, the boot split for a multitenant Nightscout (PLAT-SERVE, PLAT-ENTRY, ST-V3-DECOUPLE) | `feat/nightscout-serve`, **#8865** (base `dev`; supersedes #8862) | `b01b77c3`: #8862's four commits, the image `CMD nightscout single`, SIGTERM/SIGINT shutdown, the healthcheck certificate fix (`f01d67e6`, CodeQL alert 138 fixed), boot profiles, the API v3 role harness, and `serve` reserved for a multitenant Nightscout with the single-tenant api code as `scripts/headless-test-server.js` | **merged 2026-10-30 02:04:14Z by bewest as `dev` `991b0654`** (head `1b2801f7`). Earlier: **in the 16.0.0 merge list (maintainer, 2026-10-27)**; open, no human review yet. API v3 suites 751/0 under single, 643/0/108 pending under headless; image start forms: every `docker run` form that started a server on `dev` starts the same one, `docker stop` 10.1 s/137 becomes 0.13 s/0 (`tools/lab/image-start-forms`) | `PLAT-SERVE` |
| BF-200: the data-snapshot route's unusable time | `bf/16.0.0-ddata-at-crash`, **#8868** (opened by the maintainer 2026-10-27 19:50:31Z, base `dev`) | `2ca7dfc8`: `434c0157` and `2564e5dc` with `dev` `94899828` merged in; 6 files, +176/−12 against `dev` | **merged 2026-10-27 20:01:50Z by bewest as `dev` `88676086`** (`gh pr view 8868`); ready to push 2026-10-27, not pushed. Red controls re-run by session -ee: the new data test on `dev` 1 passing, 5 failing; the new callback-tasks case with the first commit's helper 8 passing, 1 failing; both on the branch 14 passing. `npm test` 4489 passing, 0 failing, 3 pending and `test:all` 4817 passing, 0 failing, 3 pending (session -2e, Node 22.23.4, MongoDB 7.0) | `BFQ-200` |
| BF-201: nodemon's file watches | **#8866** (added to #8867 at the maintainer's request, 2026-10-27; #8867 merged into #8866 as `7a96b912`) | `5d9f84b5` (prepared as `426d2835` on `dev` `2dc0c1bc`): `package.json` nodemonConfig, the watch test and probe, the M24 addendum | merged with #8866 (`b84871d7`, 2026-10-27 19:42:55Z). nodemon watches `lib`, `views`, `translations`, `webpack` and `package.json`; Linux file watches 1,502 → 385 at `dev` `2dc0c1bc`; the watch test fails at `docs/unlisted.js` with the old configuration; `npm test` 4483 passing, 0 failing, 3 pending (Node 22.23.4, MongoDB 8.0.34); developer tooling only | `BFQ-201` |
| BF-203: an editor's file watches | `tooling/jsconfig-watch-scope`, **#8871** (opened by the maintainer 2026-10-27 22:21:20Z, base `dev`; the start of the next tooling PR) | `f28d40bb`: the maintainer's draft `e737d310` (`jsconfig.json`, 8 lines) with `dev` `7abe1cf6` merged in | **merged 2026-10-27 22:51:12Z by bewest as `dev` `dcf20bfb`** (head `57f1d37c`, `dev` merged in). Earlier: open, CI running: an editor opening `lib/server/app.js` from a checkout inside a larger workspace watches 450,689 → 2,007 files, 1.4 GB → 358 MB (tsserver 5.9.3, started as an editor starts it); `npm test` 4700 passing, 0 failing, 3 pending; developer tooling only | `BFQ-203` |

BF-72's fix, by mechanism: a length cap on every pattern and a time limit on every query whose filter
holds a regular expression, generated ones included; a refusal check for caller-written patterns
only behind `QUERY_REGEX_REFUSE_UNSAFE`, default off. BF-161's fix: a nesting-depth limit checked
before the pattern is parsed or expanded. Both keep the intended uses in the maintainer's public gist
`dbe590ab` working, and each is published with the release that carries it.

**Cut 2, #8837, before its last push** (read from the PR body and `git log`; the runs are the preparing
session's; kept as the record of `ee94b148`; the merged head is in [What is merged so far](#what-is-merged-so-far)). The
branch is a fast-forward of the published `b6e8c7cd`: 26 first-parent commits on top of it, 185
commits ahead of `dev` `a20469dc`. It merges `dev` three times: `04a7968d` (`eb72a1d3`, 9 conflicting
paths), `dd2e0cfd` (`93f152bd`, #8834) and `94242483` (`a20469dc`, #8835). The follow-ups are
`14ba4686` (the narrowed D3 surface gains `bisector`, `curveBasis` and `curveMonotoneX`, which #8831's
modern chart needs; without them the production main page with `THEME=modern` threw while drawing the
trend), `17a9d48a`, `4354fac3`, `1e9ea6f6`, `ba32eca4`, the CI edge commits `a7eb6942`, `bdb6c733` and
`b8ff91cb`, and `ee94b148`, the page-bundle budget (decided, option A). Tests on `ee94b148` (Node 24.22.1,
`TZ=UTC`): `npm test` 3691 / 4 / 0, Chromium 540 / 0, budget 9 / 9. Earlier, on `b8ff91cb` (host zone
America/Los_Angeles): Node 22.23.4, 24.22.1 and 26.12.1 each 3542 / 4 / 4 (the 4: the two budget
cases, the BF-177 test and the API3 hook timeout, both fixed by #8838 since); Firefox 540 / 0.
`queryLeaves` was verified against `traverse` on 50,000 generated and 20 edge queries: 0 differences.

**#8837's CI** (reproduced from GitHub run metadata): run 40225696687 on `ee94b148`, attempts 1 and 2,
failed the required check *Run Tests (24, 6)* and *Maintained MongoDB (26, 8.0.29)*, each 3690 passing,
1 failing: `tests/env-runner.test.js` "Native env runner process contract passes file values through
nyc into a Mocha child" exceeded its 10 s timeout. The case's inner nyc instruments all of `lib/`
(`.nycrc` `all: true`) under `test-ci`'s outer nyc; the local runs, without coverage, did not see it.
The fix reached the branch as `62b1509d` (the same patch as the peer
session's `bd941200`), after AndyLow91's merge of `dev` `fd3792e5` (`2efd78ac`); run 40231697337 on the
merged head `af7ba73a` passed.

**`sanitize-html` 2.18.1 (#8835)** (read from the PR body). The update was bundled into #8835 on the
maintainer's direction (themed PRs). Against 2.17.5, `npm audit` listed four `sanitize-html` advisories
and against 2.18.1 none: GHSA-x3q4-9hxx-gx8m, GHSA-cv27-6wvh-8x7j, GHSA-jxwj-j7wr-gfrw and
GHSA-g8qq-57p8-ggw5 (totals 23 → 22, and 16 → 15 with `--omit=dev`, npm 11.19.1, 17:27:34Z and
17:30:04Z). GHSA-374f-7chj-9948 never applied: its range is `>=2.17.7 <2.18.0`, and `dev` locked 2.17.5.
2.18.1 brings the htmlparser2 12, domhandler 6, domutils 4, domelementtype 3 and dom-serializer 3
majors, all reached only through `sanitize-html`; it declares `node >=22.12.0`, inside the 16.0.0
floor. Of the 35 inputs in `tests/purifier.corpus.test.js`, 34 are stored identically; the one change
is listed under [For the release notes](#for-the-release-notes). The combined head `477d5200` ran
3422 / 3 / 0 (Node 24.22.1, MongoDB 7.0.43, `TZ=UTC`).

## Modernization cuts: handoff

Written for AndyLow91 and the maintainer, who asked on 2026-10-25 for cuts 3–5 to be pushed so the
remaining work could be shared; kept as the record of the handoff. All five cuts are merged (cut 3
#8844, cut 4 #8847 and cut 5 #8605 on 2026-10-26). The "remaining work" lists below were written
against the handoff heads (`76b19fb0`, `8bf6c9b2`, `98d2f9a0`) and are not re-checked on the merged
heads, except where noted.

**Method** (decided 2026-10-12, `RT-PROPAGATION`): `dev` is merged up the stack, `dev` → cut 3 → cut 4
→ cut 5; nothing is rebased, so each push fast-forwards the published branch. Each cut is resolved
against the one below it, so `dev`'s fixes reach cut 4 and cut 5 through cut 3's resolutions. PRs are
stacked: cut 3 to `dev` (#8844), cut 4 as draft #8847 based on `chore/compose-mongodb6`, and #8605's base
is AndyLow91's call (suggested: `chore/mime-exposure-review`, so its diff shows only cut 5). When a
base branch is merged and deleted, GitHub retargets the PR above it.

**Rules every catch-up applied:** version `16.0.0`; `dev`'s `engines`, Node files and CI matrix;
`nightscout-connect` exactly `0.1.0`; `sanitize-html` 2.18.1; `lodash` exactly 4.18.1; lockfile
regenerated by npm, never hand-merged; every new test file given a tier (`tests/tiers.json`); `dev`'s
fixes kept on every security, storage and dosing path, each checked by reverting it and watching its
test fail; with `TRUST_PROXY` unset, 15.0.9's address resolution (BF-88).

| cut | head | fixes folded in | verified (reproduced, Node 24.22.1, `TZ=UTC` unless noted) |
|---|---|---|---|
| 3 | `12d1f645` (#8844) | BF-182 (boot error page when driver 7 refuses the server), BF-179 (production-only install explains itself) | `npm test` 3838 / 0 / 4 on MongoDB 5.0.33, 7.0.43 and 8.0.34 at `8f238fc5`; 3877 / 0 / 4 on 8.0.34 at `12d1f645`; Chromium 579 / 1 and Firefox 580 / 0 at `12d1f645` (the 1: BF-192, from `dev`); the budget moves to 6.8 MB with #8843; MongoDB 4.2.24 gets the boot error page, 4.4.24 connects |
| 4 | `99b6f68b` (#8847) | BF-183 (storage socket stops logging subscription credentials) | `npm test` 3887 / 0 / 4 on 5.0.33 and 8.0.34, and on 8.0.34 in America/Los_Angeles, at `32a3c0ac`; 3921 / 0 / 4 on 5.0.33 at `99b6f68b`; Chromium 591 / 1 (BF-192); `TRUST_PROXY` unset behind a TLS proxy answers 200, and 307-to-itself with cut 4's original default |
| 5 | `506cc41b` (#8605) | — | `npm test` 4045 / 0 / 3 on MongoDB 5.0.33 and 8.0.34, and on 8.0.34 in America/Los_Angeles; Chromium 638 / 1 (BF-192) and Firefox 639 / 0; reverting BF-70's refusal, the operator allowlist, Express 5 query preservation, a Pushover status check or the notification cache's expiry each fails its test; `TRUST_PROXY` unset behind a TLS proxy answers 200, 307-to-itself with the old default |

**2026-10-26: `dev` merged up again** after #8843 (CI diagonal), #8848 (Docker publish) and #8850
(test order isolation): cut 3 `76b19fb0`, cut 4 `8bf6c9b2`, cut 5 `98d2f9a0`, each a fast-forward of its
published head. Only `.github/workflows/main.yml` conflicted (cuts 4 and 5: `dev`'s split jobs, cut 4's
lint step in the no-database job, cut 5's connector step and database-upgrade rehearsal kept, the
replica-set job dropped) and `docs/runtime-upgrade.md` (cut 5). The new CI lanes reproduced locally on
each cut (Node 24.22.1): the no-database tiers in America/Los_Angeles and shuffled, integration and
stress on MongoDB 5.0.33 in America/Los_Angeles and on 8.0.34 shuffled (seed 40226791404), Chromium and
Firefox: cut 3 2014 + 18 integration, 580 browser; cut 4 2031 + 18, 592; cut 5 2038 + 18, 639; all
passing after #8850. The shuffled lane found four order-dependent tests already on `dev`, fixed there by
#8848 and #8850, not by the cuts.

Found by the merges and fixed on the branches: bson 7 `ObjectId`s carry own fields, so cut 2's query
walker walked into them (cut 3, `5aa1e749`); `git` merged `dev`'s alarm-socket body into cut 4's
handler signature, so every access-token alarm subscription would have thrown (cut 4, in the merge
commit; the September rehearsal hit the same); two API sub-apps called a `compileTrust` that `dev`'s
`client-ip.js` does not export, so the server would not boot (cut 4). In cut 5, the merge deleted dev tests
without a conflict where cut 5 had moved them (the profile editor defaults and empty-name tests, the
chart-container height race and six quick-pick tests), all restored; body-parser 2.3.0 failed dev's
HTTP middleware probe under Express 5 (lockfile 2.4.0, floor enforced by the dependency test); dev's
ajv 8 and `mocha.diff` overrides were below cut 5's majors; and the jsdom shim's `atob` recursed once
entities 8 loaded.

**Remaining work, cut 3:** the modern theme's tooltip palette does not style the native tooltip;
`views/index.html` and the service worker still load `css/jquery.tooltips.css`;
`tools/probe-legacy-bridge-transport.js` needs bridge packages `dev` removed; some cut 3 plans describe
September CI; a few small bulk reads added on `dev` have no batch bound.

**Remaining work, cut 4:** the lockfile holds minimizer-webpack-plugin 5.13.0, because 5.13.1 needs
schema-utils ^4.6.0 and npm kept 4.3.3 (postinstall failed); the `terser-webpack-plugin` override no
longer matches anything; the Firefox editor-time probe step lacks `HOME: /root`, and the lint step's
condition was fixed, both to be confirmed in CI; the spring-gap basal selection is an open discrepancy
in `tests/timezone-modernization.test.js`.

**Remaining work, cut 5:** live checks this programme cannot do without real credentials: a
Pushover emergency alarm's send, acknowledgement and cancel (the native client posts the cancel; whether
the old GET was ever accepted is unknown), notification de-duplication and receipts over a real
15-minute window, a Loop APNs remote command to a phone, and IFTTT Maker under Express 5; the CORS
preflight's `200` text `OK` was restored by AndyLow91's `ad56423d` before the merge (#8605's body);
`js-yaml` is declared as a devDependency so webpack-cli 7's optional peer resolves; the
`istanbul-lib-processinfo.uuid` override no longer applies; dev's `TRUST_PROXY` notes still compare
against cut 5's unadopted `395f3207`.

**Across the cuts:** WebKit and the Node 22.23.4 floor were not run locally (CI runs them, but see the
browser row in [Known defects](#known-defects-on-dev-now)); BF-07's `getDataRef` caller in
`lib/api/entries/index.js` has no pinning test (reverting it stays green; filed by session -f4); cut 5's
alarm transports (Pushover native client, notification caches, APNs 8) need a live delivery check,
which this programme cannot do without real credentials; #8843 (CI diagonal) and each cut change
`.github/workflows/main.yml`; #8843 landed first and each cut took its jobs.

## Known defects on `dev` now

| defect | what | exposure | queue |
|---|---|---|---|
| BF-219, BF-220, BF-221: v1 treatment batch replies and PUT announcements | **fixed on `dev` by #8883** (merged 2026-10-31 16:30Z as `2f50d944`; not released). BF-219: a batch with a preBolus answers with more items than were sent, so Loop re-sends it forever. BF-220: a taken `_id` inside a batch answers 5xx after earlier items are stored. BF-221: a v1 PUT reaches open pages 1–57 s late | BF-219 and BF-220 are dosing-relevant (lost or endlessly re-sent treatments); BF-221 is display latency | `BFQ-219`, `BFQ-220`, `BFQ-221` |
| BF-222: API v3 autoPrune leaves pruned records in the cache | **fixed on `dev` by #8883** (merged 2026-10-31 16:30Z as `2f50d944`; still on `v15.0.9`, since #6688; R18) | only where `API3_AUTOPRUNE_<collection>` is shorter than that collection's cache retention; display only | `BFQ-222` |
| BF-215, BF-216: identifier format | **on `dev` now; fixes in #8879** (ID-FIRST-MATCH slice 2, not merged). BF-215: a numeric `identifier`; BF-216: a placeholder `identifier` shared by two apps | BF-216 is dosing-relevant data loss, narrow | `ID-FIRST-MATCH` |
| BF-212, the rest: shared client identity after a chart split | **first part fixed on `dev` 2026-10-30** by #8878 (`d51c7a60`): a new chart split no longer copies the client identity fields. Still open: records split before the fix keep two stored treatments with one identity, and a v1 or in-process re-send of either lands on the older record, so a re-send of the newer one overwrites the older one's amount (API v3 picks the newer record and refuses a re-send of the older one with 400; measured by the extended write-contract matrix). A full re-upload of the original by the client that still holds it writes the moved insulin back, so it is stored and counted twice, with or without identity on the copy. The follow-ups are ID-FIRST-MATCH slice 5 (the P4 pick) and the maintainer's direction that a lossy edit of a controller-claimed record needs a manual confirmation | dosing-relevant data and display, narrow: a chart drag of a record that holds both insulin and carbs; on 15.0.9 and `dev` | `BFQ-212` |
| BF-209: two identical socket treatments within 2 s from different clients stored as one | **fixed on `dev` 2026-10-30** by #8877 (`cf3d4b8f`), for writes that carry `identifier` (scope decided 2026-10-29: in the similar match, `identifier` decides when present); writes without it keep the earlier rule, and recognising `identifier` at any time waits for ID-FIRST-MATCH. Present on 15.0.9. BF-210 (an upload with no amount absorbed by a stored one) was withdrawn 2026-10-29 as intended behaviour | socket writers: AndroidAPS's v1 NSClient (3.4.2.x) and the chart-drag split | `BFQ-209` |
| BF-211: a delete by query empties all three in-memory caches | **fixed on `dev` 2026-10-30** by #8877 (`cf3d4b8f`); present since 14.0.4 and on 15.0.9. Cost, not correctness: the next load re-reads days of data (890 documents and 716,202 bytes after a 3-record delete; 32 documents and 10,289 bytes with the fix, cache-value lab) | sites on transfer-capped MongoDB tiers | `BFQ-211` |
| BF-200: an unusable time on API v2's data-snapshot route stops the server | **fixed on `dev` 2026-10-27** by #8868 (`88676086`); until then: one authenticated read of `/api/v2/ddata/at/:at` with a time the server cannot use makes the data loader throw where nothing catches it, since `26d0908a` replaced `async` with `lib/utils/callback-tasks`; the process exits. v15.0.9 answers 500 and keeps running (checked by session -2e), so this is a regression on `dev` only | every site running `dev` (`2dc0c1bc`) or a `dev` image; not 15.0.9 | `BFQ-200` |
| BF-202: CI's MongoDB 8.0 jobs on Linux 6.19 runners | MongoDB 8.0 refuses to start on Linux 6.19 to 7.0.13 (SERVER-121912); `ubuntu-24.04` image 20261026.354 moved to `7.0.0-1017-azure`, where both 8.0 jobs refused to start on run 40569101512, 8.0.29 included. Mitigated by `f6884342`, merged with #8866 (`b84871d7`): the 8.0 jobs run on `ubuntu-22.04` (Linux 6.8), both passing on run 40569981396 | CI: mitigated on `dev`. Operators running MongoDB 8.0 on such a kernel meet the same MongoDB defect (release-notes line) | `BFQ-202` |
| Firefox legacy-reports wait | `tests/browser/legacy-reports.test.js` "should produce some html" timed out at its fixed 30 s wait (`12154df9`) in one or two Firefox cells of the CI runs on `93f152bd` (`pull_request`) and `a20469dc` (both events), so the push run on `a20469dc` skipped the Docker publish; and once more on #8836's head `df2f37ab` (run 40228187718 attempt 1, *Browser tests (26, firefox)*, 463 passing, 1 failing; attempt 2 passed). Since cut 2 merged (`eb44a9c2`), `dev`'s test uses the progress-aware wait (fails after 15 s with no completed request, 60 s ceiling; `tests/browser/legacy-reports.test.js:136-144`), and *Browser tests (26, firefox)* passed in every push and `pull_request` run on `5de8505d`, `fd3792e5`, `eb44a9c2`, `78524be4` and `b29f1bf7` (one run each, so not yet evidence that the flake is gone) | test only; no register entry filed | `RT-2` (merged) |
| browser tests not running in CI | Since #8839 (`78524be4`), *Browser tests (26, chromium/firefox/webkit)* print no test output and pass: `scripts/test-tiers.js` lists files with `git ls-files`, ignores git's exit status, and inside the Playwright container (step `HOME=/root`) git refuses the checkout as dubious ownership, so the tier has zero files and the runner exits 0 (reproduced by session -5e in a root container over another uid's checkout; job logs read for push runs on `eb44a9c2`, 549 passing, then `78524be4` and `428b20b7`, none, and #8844's run 40253810477, none). Server jobs are unaffected (3820 passing per cell on `428b20b7`) | CI evidence only: no browser test gated `dev` or a PR from 2026-10-25 21:57Z until #8843 merged (2026-10-26 05:20:27Z, `720e60de`); the Chromium job of push run 40369632641 on `47723cda` runs 40 browser test files, 650 passing (job log). The fix (`listTestFiles` throws on git failure, a tier with zero files exits 2, `safe.directory` set system-wide in the browser job) on #8843 as `e767ce4e`, with a harness test that fails on the old runner | `RT-CI-DIAGONAL` (#8843, merged 2026-10-26) |
| dev pushes publish no Docker image | Since #8843 (`720e60de`), `docker-build` needs only `tests-pass`, and its implicit `success()` also sees `docker-build-pr`, which is skipped on pushes, so *Build Docker image* and *Publish to Docker Hub* are skipped: push run 40273692991 on `720e60de` passed every test lane and published nothing (job conclusions read with `gh run view`). The pushes before it (`78524be4`, `b29f1bf7`, `428b20b7`) published, so `dev`'s image stays `428b20b7`'s until the fix lands, and merges of the cuts publish nothing either | no `dev` image from `720e60de`; no release affected. **Fixed** by #8848 (merged 2026-10-26 06:03:54Z as `1f10cd9d`, head `952d0f49`; `864be741`: `!cancelled()` and an explicit `needs.<job>.result == 'success'`): `dev`'s push run 40277667345 built amd64 and arm64 and published to Docker Hub (session -5e, read-derived). #8848 also fixed two order-dependent tests (`c3a42776`, `952d0f49`) | `RT-CI-DIAGONAL` follow-up |
| reports page retained heap over budget | `tests/browser/page-populated.test.js` "initializes populated reports and bounds retained V8 heap" fails on Chromium on `428b20b7`: about 6.20 MB against 4.85 MB (`tools/page-resource-acceptance.js`), 3 of 3 runs (Node 24.22.1) and 2 of 2 (session -f4, Node 22.23.4); about 4.45 MB on `b29f1bf7`, so it arrived with #8542 (AGP reports). Hidden by the row above | a test budget, not an operator-visible failure. Resolved in #8843 (`0a33b7c7`, folded in by the maintainer): the test waits for the page's first report to finish, and the reports ceiling becomes 6,800,000 bytes, measured on `428b20b7`. Since #8542 the reports page draws a report on load; with a report showing, the new code retains about 2 MB less than the old (session -5e's measurement, read-derived) | BF-192, merged 2026-10-26 with #8843 |

Seen in `dev`'s CI on 2026-10-26 and 2026-10-27 (read from the job logs, `gh run view <id> --log-failed`; neither
reproduced locally, no register entry):

| intermittent | run | what |
|---|---|---|
| development watch policy | push run 40350206994 on `89b7ebdd` (#8730) | *Tests without a database (22.23.4)*: 1339 passing, 1 failing, "Development watch policy preserves configured ignores and application watching through two restart cycles" (`tools/probe-development-watch.py`, `assert boots[-1]['value'] == cycle+1`; the test took 8.9 s). *Tests pass* failed, so no image was published from `89b7ebdd`; the `pull_request` run on the same commit passed |
| Firefox job time limit | push run 40356902994 on `09d0def8` (#8555) | *Browser tests (26, firefox)* was cancelled at the job's 10-minute limit, so *Tests pass* failed and no image was published from `09d0def8`. Cut 5's `f4abce3c` raised browser jobs to 15 minutes; Firefox took 8m12s and 10m40s on `47723cda` |
| page-startup reports recovery | `pull_request` run 40273696980 on `720e60de` (#8843) | *Browser tests (26, chromium)*: "Complete page template startup recovers the actual reports page after two failed bundle downloads" exceeded 30 s (172 passing, 2 failing with its `afterEach`); the push run on the same commit passed |
| concurrent-writes `_id` count | push run 40424319822 on `8dbb60c2` (#8860) | *Run Tests (26, 5.0)*: "all documents have unique _id after concurrent inserts", expected 10, got 9. Ten Notes with random times within 10 s; a Note without an `identifier` is matched on its time and event type, so two in the same millisecond are one record (about 1 run in 220). Reproduced with a forced collision (expected 1 to be 10); not reproduced in 30 plain runs. Fix prepared: `RT-CI-FLAKES-8DBB60C2` (R17) |
| WebKit reports-page race | push run 40424319822 and `pull_request` run 40424329138 on `8dbb60c2` | *Browser tests (26, webkit)*: "Complete page template startup boots every page from cached bundles and retires the old cache on upgrade". Push run: fifteen report-page requests "due to access control checks" as uncaught page errors; `pull_request` run: `page.goto: WebKit encountered an internal error` leaving `/report/`. The test leaves the reports page before its deferred first-week report has loaded. Not reproduced locally in CI's image (3 of 3 on `8dbb60c2` and `7ad3a67f`); #8860 does not change what the page fetches. Fix prepared: `RT-CI-FLAKES-8DBB60C2` (R17) |
| repost-with-id find count | reported by peer session -b7 | `tests/api.entries.repost-with-id.test.js` failed once under `TEST_SHUFFLE_SEED=303`; not reproduced or verified here (`TEST-FLAKE-REPOST-FIND-COUNT`) |

**BF-176, the window.** `dev` carried the `IMPORT_CONFIG` boot crash from `eb72a1d3` (16:29:06Z, #8828)
to `93f152bd` (17:44:48Z, #8834). `dev`'s Docker image was published in between, by push run
40211895500 at 17:15:18Z, so a `dev` image pulled from then until the next publish (17:53:31Z, from
`93f152bd`) stops at boot when `IMPORT_CONFIG` is set. No release carried it.

#8831's PR body (read) also reports that `npm run test:dependencies` stops at an existing `npm ls`
error about the `axios` override on `master`, and that nine COB, IAGE and SAGE tests fail in the
Europe/London DST fall-back hour and pass in UTC; neither was measured here.

## Testing so far

The runs are in the
[16.0.0 integration record](../../docs/30-design/remedial/rc-16.0.0-integration-record.md), the same
place and form as the [15.0.9 integration record](../../docs/30-design/remedial/rc-15.0.9-integration-record.md).
No verification record is captured yet: `verification-record.{json,md}` is generated by
`tools/queue/verification-record.py` once, at release time, from the state being cut
([VERIFICATION-RECORDS.md](../VERIFICATION-RECORDS.md)), and is never hand-written, so this directory
has none until then. The items it is captured over are listed in
[verification-selection.txt](verification-selection.txt) (98 queue ids on 2026-10-31, 90 on 2026-10-30; 65 at the
2026-10-27 dry run: every item this file or [decisions.md](decisions.md) names, and the release items), with
the capture command. The 25 added on 2026-10-30 are the items named since the dry run, fourteen of them from
the 2026-10-27 and 2026-10-28 merges.

**R18, 2026-10-30/31** ([integration record](../../docs/30-design/remedial/rc-16.0.0-integration-record.md)):
#8874's write-contract matrix against the `dev` pins (0 cells outside `wire` and `cache`), the cache
catch-up lab round 3 (BF-222) and BF-222's fix (`npm test` 5216/0/3). `dev` `368e6c23`'s CI passed.

**Journey lab, 2026-10-30/31, #8874 `7463e76d` against `dev` `305a6533`** (maintainer in the browser, two tabs per
site, with session -7d checking the database and socket timing; journey lab `tools/review/journey-lab`, MongoDB 7,
Node 22.23.4, development mode; sites loop, aaps (API v3, mmol/L), aaps-v1 (socket) and rep-trio on each head):
careportal carb correction (REST POST); Loop carbs POST, PUT edit and DELETE by `_id`; the web page's edit-mode drag
(socket `dbUpdate`); AndroidAPS temp target start and cancel over v3 and the socket, carbs, and carb delete; the modern
theme on rep-trio. Every step stored once with the same fields on both heads and showed live in both tabs; deletes
reached the page in 13–30 ms on both heads (3/3). Verdict: no difference between #8874 and `dev` in anything seen or
stored. Found along the way, none caused by #8874: BF-221 (a v1 treatment PUT reaches pages up to a minute late),
DEV-LINT-OVERLAY-REGEX, UI-DRAWER-RESIZE and UI-STALE-SECRET-HASH (queue). The lab's AAPS temp-target cancel was
corrected (`2e484bd33`).

**Dry run, 2026-10-27, `dev` `8dbb60c2`** (reproduced; written to a scratch directory, not kept, because a
record is captured once, at the tag). The generator ran on the selection with its default `static` and
`unit` gate kinds: 65 items, 49 PASS, 4 FAIL, 12 UNMEASURED; 157 gates run or marked, 72 passed, 5 failed,
80 are `no-gate` markers. The five failures: BFQ-72's gate (BF-72 still on `dev`; its fix is in the
advisory fork), BFQ-161's freshness gate (the fork branch owes a merge of `dev`), RT-CONNECT-PIN-CUTS
(the gate refuses to report because every ref it reads now pins `nightscout-connect` 0.1.0) and
RT-NODE-FLOOR-TESTED's two gates (they read the old `origin/chore/*` tips). The dry run found four defects
in the generator and the register, fixed on 2026-10-27 before the tag-time capture (VERIFICATION-RECORDS.md,
"Changes"): register statuses `merged` and `released` were not read as claims of a fix, so every merged
entry was listed as not demonstrated; a failing gate added no gap of its own; an item whose `dev` had
moved past its pinned base was reported as unresolved (35 items); a cell holding an escaped `\|` was split
in two (BF-58), and three §1b rows carried a sixth cell (BF-177, BF-179, BF-182). RT-NODE-FLOOR-TESTED now
gates on `official/dev` (merged-upstream; register BF-58 and BF-59 `merged 2026-10-26`), and
RT-CONNECT-PIN-CUTS gates `dev` and `master` with `v15.0.8` as its bad control (BF-65). Five register
entries written against the cut branches before they merged were re-graded by measurement on `8dbb60c2`,
each with a break-it run where one applies: BF-55, BF-65 and BF-88 `merged 2026-10-26`, BF-56 `closed,
did not occur`, BF-64 `closed, superseded`. **Re-run after the fixes** (same selection and kinds): 65
items, 51 PASS, 2 FAIL, 12 UNMEASURED; the two failures are BFQ-72 and BFQ-161, both pre-tag
requirements in the advisory forks.

## Open items a releaser must settle

As of `dev` `47723cda` (2026-10-26), with item 11 from `7ad3a67f`, and items 1 and 12–15, the entry bar and the
repository settings brought to `dev` `991b0654` on 2026-10-30. The decisions already made are in [decisions.md](decisions.md).
Whether cuts 3–5 ship in 16.0.0 is answered: all three are merged into `dev`, so they ship in 16.0.0
unless reverted.

**Required before the tag** (maintainer, 2026-10-26, session -66; queue `RT-16-RELEASE`): (a) a live
Pushover and APNs delivery check (`RT-16-LIVE-ALARMS`); (b) a real-rig soak on `dev` (`RT-16-RIG-SOAK`);
(c) the BF-72 and BF-161 fork fixes merged and published with 16.0.0 (`BFQ-72`, `BFQ-161`).
**November 2 status:** cohort testing is in progress; completion evidence for
these gates is not yet recorded. The earlier "not started" characterization is
superseded, not a reason to restart or discard existing tester observations.
BF-193 is not a pre-tag requirement; its fix shape is decided (debug-gated payload logging through
`DEBUG_LOGGING`, [decisions](decisions.md)) and merged 2026-10-27 as #8856 (`dev` `eed31dca`).
The maintainer's definition of done before the tag (2026-10-27, `RT-16-RELEASE`) adds (d) a short quiet period
on `dev` with the final candidate, days not weeks, and states (b) as cohort confirmations from `dev` users
(AndroidAPS, Loop, Trio, xDrip+, a follower app, an mmol/L site).

**The entry bar** (maintainer, 2026-10-29; scope widened 2026-10-30): every single-tenant item of the next-gen
plan may join the 16.0.0 merge list, in priority order, once its matrix result is as stated, its red controls
and ablations pass, a revert has been rehearsed, and it has had time on `dev` with its cohort check. A miss at
the tag rolls to 16.1.0, or to 17.0.0 if it changes a default. On 2026-10-30 no item in
[In flight](#in-flight-for-this-release) has cleared it; #8874 is first in the order.

**Decisions open, with their owner:**

1. **BF-161 advisory scope is decided; private integration remains blocked.**
   The recorded 2026-10-27 decision is to cover BF-161 and BF-151 together and
   publish once with 16.0.0. Current private targeting/full-suite blockers are
   in [security readiness](../../docs/10-domain/nightscout-rc-readiness-2026-11-01.md#security-integration-blocked-private);
   no merge or publication is claimed. Queue `BFQ-161` is blocked, not awaiting
   a ready-to-review packet.
2. **BF-72 remains private and blocked.** Disclosure-safe test preparation,
   valid private PR targeting and final full-suite integration are outstanding;
   see [security readiness](../../docs/10-domain/nightscout-rc-readiness-2026-11-01.md#security-integration-blocked-private).
   Queue `BFQ-72` does not authorize publication.
3. **BF-95** (maintainer): a notice for readings that arrive dated ahead of the server clock, or the
   status quo. Packet: [bfq-95](../../reports/reviewer-packets/bfq-95.md). 2026-10-25 (maintainer): verify
   `srvModified` first; on `dev` it is a server receipt time on every live path (caveat BF-181).
4. **Dependabot configuration** (maintainer): version updates targeting `dev`, dismissing alerts that
   are fixed on `dev` or not reachable, or releasing more often. Packet:
   [dependabot-config](../../reports/reviewer-packets/dependabot-config.md).
5. **BF-49's alias and dead settings keys** (maintainer; #8849's open items, `BFQ-ENV`): whether
   `SECURE_HSTS_HEADER_INCLUDE_SUBDOMAINS` becomes an alias, and what to do with the five settings keys
   nothing reads.
6. **#8842's open items** (maintainer): on a page with a reading, a non-glucose alarm is still gated by
   the high or low setting on the reading's side; and the reviewers' confirmation of stale-data and
   CGM-error alarms on a page showing `---`.
7. **#8841's open items** (maintainer): a refusal the person can see under `reject`, normalising `units`
   beyond temp targets, the plausibility thresholds (30 mmol/L, 20 mg/dL); and `WRITE_VALIDATION` set to
   any value other than `log` or `reject` reads as `off` with no message (`parseMode`,
   `lib/server/write-validation.js:42-46` on `dev`), so a misspelt `reject` turns checking off silently.
8. **The query-string array limit under Express 5** (maintainer): cut 5 sets `arrayLimit: 1000`
    (`lib/middleware/configure-request.js:8-9`), where 15.0.9's Express 4 parser used `qs`'s default of
    20 (read-derived); no decision on the value is recorded.
9. **A recorded waiver for the MongoDB 3.6–4.2 drop** (maintainer): the versioning policy §5.4 sets
    2 releases and 180 days for a runtime floor that can stop data arriving; MongoDB 4.4 was deprecated
    in 15.0.9, and 3.6, 4.0 and 4.2 stop serving with 16.0.0 (driver 7, decided 2026-10-25). The
    decision is recorded; a waiver of §5.4's window, with its reason for the release notes, is not.
10. **BF-194** (maintainer): API v1 removes `units` from a treatment with no glucose value before
    `WRITE_VALIDATION` runs, so a v1 temp target sent in mmol/L is stored with mmol/L numbers and no
    units and reads as mg/dL, in every mode, on 15.0.9 and `dev` (reproduced, integration record R15):
    keep the units, convert, or refuse. Queue `BFQ-194`. *2026-10-27 (maintainer): survey the clients first, then likely enforce mg/dL at write (convert a target labelled mmol and relabel it); survey running.* *Decided 2026-10-27 (maintainer): convert and always label. Fixed on local `bf/16.0.0-tt-units` `7b74110c`, **merged** to `dev` 2026-10-27 as `db3b9e4e` (#8872): every write path stores a Temporary Target in mg/dL labelled `mg/dl`; gate PASS, npm test and test:all pass. Owes a release-note line.*
11. **#8854's `failed` slot** (maintainer): under `reject`, a socket treatment array answers an item whose
    write cannot be confirmed (a lookup, similar-record match or insert error, such as a duplicate key) with a
    slot without `_id` carrying `failed: {status: 500, message: "Treatment write could not be confirmed"}`,
    where `47723cda` left the item out of the reply (`lib/server/websocket.js:557-563` on `7ad3a67f`;
    read, not measured). API v1 has no equivalent. List it in the 16.0.0 client notes as it is, or agree it
    alongside `refused` (and whether API v1 should match). Queue `ARCH-8854-FAILED`. *Decided 2026-10-27 (maintainer): ship it as it is, described in the client notes as experimental under `reject`; the per-item reply for every path is settled in ID-BATCH.*

12. **Which items clear the entry bar before the tag** (maintainer; 2026-10-30): in order, `write(intent)`
    release 1 (#8874, `WC-STEP-PATCH`), ID-FIRST-MATCH slices 1, 2, 5, 3, 4, 6 and 6a, ID-BATCH
    (`ID-BATCH-RESULTS`), the re-send switch (`ID-RESEND-SWITCH`), ID-UNIQUE-INDEX with
    `WRITE_IDENTIFIER_INDEX`, SPEC-ID-AMEND, #8857, ST-HARNESS, and ST-EVENT or ST-VIEWS if they clear it.
    Each one that changes a default (merge on match on new paths, stays deleted, the index built at boot under
    `try`) needs its own release-notes line and its cohort check.
13. **#8857's flag and rebase** (maintainer and the author): D-REG-FLAG (where the catalogue lives, and the
    flag's form); the branch is 109 commits behind `dev` with conflicts. Off by default either way.
14. **ST-VIEWS' wiring** (maintainer): #8875 computes the page, socket, plugin and alarm views from bounded
    queries; it is not wired in, and the alarms are safety-relevant (execution plan §7b).
15. **Multitenant items as alpha** (maintainer): whether anything ships dormant behind `serve` in 16.0.0, and
    the release notes' alpha wording (Q12a in the release allocation: the alpha label belongs to the
    multitenant bindings only). `serve` refuses every role on `dev` `991b0654`: no role in
    `lib/server/serve/roles.js` is marked `multitenant` (read-derived).

**Found by R15 (reproduced; no register entry):**

- `npm test` and `test-ci` glob `./tests/*.test.js` (310 files) while `tests/tiers.json` maps all 377;
  the 67 outside the glob are the browser tier (40), `tests/client-core/` (26) and one harness fixture
  test. CI runs them through the tier runner; a contributor's local `npm test` skips the 27 non-browser
  files that `npm run test:all` runs.
- After driver 7 refuses MongoDB 4.2, the boot log still prints "Mongo Storage system ready"
  (`lib/server/bootevent.js:208`), though the site serves the boot error page.
- API v3 under `WRITE_VALIDATION=log` logs each bad record twice (`validate` in
  `lib/api3/generic/create/operation.js` and again in `create/insert.js`).
- API v3 refusals under `reject` write no log line; API v1 refusals do.

**Repository settings update, 2026-11-02:** master now requires only
`Run Tests (22, 6)` and `Run Tests (24, 6)` plus one approving review.
The absent 4.4 requirement has been removed; both retained lanes are green on
#8824. The recorded target policy (*Tests pass* plus one review) is not yet the
observed setting. Staging remains blocked; no settings were changed here.

**Historical repository settings** (branch protection read 2026-10-26 with `gh api
repos/nightscout/cgm-remote-monitor/branches/<branch>/protection`: `dev` requires `Run Tests (24, 6)`;
`master` requires `Run Tests (22, 6)`, `Run Tests (22, 4.4)` and `Run Tests (24, 6)` and one approving
review; `enforce_admins` is off on both). No workflow on `dev` emits `Run Tests (22, 4.4)`, so the
staging PR #8824 cannot meet `master`'s protection as it stands. Read again 2026-10-30 at `dev` `991b0654`:
unchanged.

**Decided, settings change owed** (maintainer, 2026-10-26, relayed via session -66; applied by the
maintainer): `master` requires only the *Tests pass* check (job `tests-pass`, `.github/workflows/main.yml:317`
on `dev`, `if: always()`, needing every test job and the pull-request Docker validation) and one
approving review. The decision as relayed names `master`; `dev`'s required check is not part of it. Caveat: *Tests pass* accepts `skipped` as well as `success` from every job it needs
(`main.yml:327-337`), so a test job skipped in full would still let it pass.

**Follow-ups filed 2026-10-25:** `RT-BUNDLE-THEME-SPLIT` (page-bundle budget option B: load the modern
theme's code only when it is chosen; owner Andy Low or the maintainer; not started). `RT-BOOT-INDEX-AWAIT`
merged with #8849.

**Merge order before the tag** (next-gen plan §1a, 2026-10-29; rows 1, 2 and 2a merged 2026-10-30): #8855
(Crowdin), the BF-72 and BF-161 fork branches brought up to `dev` and merged, then the `master` protection fix
and #8824. The entry-bar items (open item 12) join in their own order as each clears the bar.

**Next merges** (a suggestion for the maintainers, not a decision; written 2026-10-26 and 2026-10-27):

1. The follow-ups, each in a themed PR: `RT-JSDOM-REST` (scope B), `ID-SIMPLE-MATCH` with BF-169's
   remaining client work, `RT-BUNDLE-THEME-SPLIT`.
2. BF-72 and BF-161 through their advisory forks, published with the release that carries them; each has
   a merge of `dev` `8dbb60c2` prepared locally (`f64f78c4`, `8dcf1537`; R17), ready to push to its fork.
   *2026-10-30:* the fork heads are `a9da33ff` and `1dce7722` (pushed 2026-10-27, containing `dev`
   `7abe1cf6`); a merge of `dev` `991b0654` and a re-run in each is owed.

**Before the tag:** the three requirements above (the live delivery check, the real-rig soak, BF-72 and BF-161), the other live acceptance checks #8605 leaves to the maintainer (Pushover emergency
delivery, acknowledgement and cancellation; alarm de-duplication over its real window; APNs delivery
to a phone; production hosting, upgrade and rollback; physical-device accessibility), the call for
testers ([testing-notes.md](testing-notes.md)), the tag message and the release notes (written last,
from the list below), a full run on the candidate in the integration record, the verification record
capture, the reconciliation in [releases/README.md](../README.md).

## For the release notes

A draft list of what the release notes must say; the notes themselves are written last, once the
candidate is named.

- (#8865, if merged) Nightscout stops cleanly on SIGTERM and SIGINT on every start path: it closes
  its connections and exits 0, or exits 1 if it is still open after 8 s. In the Docker image,
  `docker stop` takes well under a second instead of 10 s and a forced kill. One case changes
  outcome: a container under `restart: on-failure` that receives SIGTERM from something other than
  `docker stop` used to ignore it and keep running; it now exits 0 and stays stopped. The image's
  command is `nightscout single` (the same server as `node lib/server/server.js`, which still works
  as an explicit command); tooling that matches PID 1's command line sees the new name. `nightscout`
  is a new executable with `single`, `healthcheck`, `version`, `env` and `diagnose data`;
  `nightscout serve` is reserved for a multitenant Nightscout, which is not built yet, so every
  role exits 64.
- (BF-213, if merged) Sites with `PUMP_ENABLE_ALERTS` get pump alarms at the severity Loop assigns to its pump
  status, with Loop's text: "No Insulin", "Pod Expired" and Medtronic "Signal Loss" now alarm, which they never did.
  Candidate note, read from #8865 at `1b2801f7` by session -7d, not run: a custom entrypoint or command that
  puts `node` in front of the image's default command now runs `node nightscout single` and fails to start.

- The Node floor `^22.23.4 || ^24.22.1 || >=26.12.1`, and the message the server prints when it refuses
  to start.
- The legacy Dexcom Share and MiniMed CareLink bridges are removed; leftover bridge settings stop the
  site with a page naming the replacements; Dexcom Share data comes in through `nightscout-connect`.
- MongoDB 4.4 or newer is required to start (cut 3, driver 7): on 3.6, 4.0 or 4.2 the site does not
  serve data and shows a page naming the database server's version and the minimum it needs (BF-182); the
  fix is to upgrade MongoDB. 5.0 through 8.0 are the supported, tested range; 4.4 starts but is untested.
- MongoDB 8.0 itself does not start on Linux kernels 6.19 to 7.0.13, which includes Ubuntu 26.04's Linux 7.0: it
  logs "MongoDB cannot start: Linux kernel versions 6.19 and newer has a known incompatibility" (MongoDB's
  SERVER-121912, not a Nightscout change). On such a host, run MongoDB 5.0 to 7.0, or keep the database on a host
  with an older kernel, until MongoDB supports it (BF-202).
- Production-only installs (`npm ci --omit=dev` or `NODE_ENV=production`) that worked on 15.0.9 do not
  build the client bundle since cut 2 (webpack and Babel are devDependencies). BF-179 (planned for cut 3)
  turns the failure into a message naming the fix (`npm ci --include=dev`, then
  `npm prune --omit=dev --ignore-scripts`); it does not restore the old behaviour. The project's
  Dockerfile and `azure-deploy.sh` install dev dependencies and are not affected.
- Docker Compose starts `mongo:6.0.27` instead of `mongo:5.0.32` (cut 3): for an existing Compose
  deployment this is a database major-version upgrade (`docs/runtime-upgrade.md`).
- Express 5 and Helmet 8 (cut 5), and the query-string array limit (above, open item 8).
- The opt-in `THEME=modern` dashboard (#8831) and the opt-in `SHOW_SECONDS` clock (#8555).
- The opt-in `WRITE_VALIDATION` for Temporary Targets (#8841), what `log` and `reject` do, that most
  uploaders lose a refused record without showing an error, and that an unrecognised value means `off`.
- #8854 under `WRITE_VALIDATION=reject`: the realtime socket checks Temporary Targets too and answers a
  refused one with a `refused` slot in input order, without `_id`, storing the rest of the batch (15.0.9 and
  `47723cda` stored them all); a treatment whose write cannot be confirmed is answered with a `failed` slot
  (open item 11). The `Nightscout-Data-Warnings` header on API v3 reads is experimental and off unless
  `API_V3_DATA_WARNINGS=true`. Nothing changes with `WRITE_VALIDATION` off.
- The opt-in `API3_SETTINGS_STRICT_READ_ENABLED` (#8845, BF-152 step 1), and that an AndroidAPS 4.0
  follower using a read-only token it was not given by AndroidAPS is refused when it is on.
- Record identity (#8845): API v3 refuses a client body `_id` with 400 (BF-170); API v3 PATCH, PUT and
  POST reach a record with an empty stored identifier (BF-145); a v1 re-send is answered with the stored
  `_id` (BF-165); a profile re-sent with its `_id` is merged instead of failing (BF-166).
- A `null` in an update removes the field (write contract Q1b, decided 2026-10-26; with BF-195's fix): what
  is stored changes for a re-send that matches a stored treatment, entry, profile, food or activity record, for
  an API v3 `PATCH` and for a socket `dbUpdate`, where 15.0.9 stores the `null`. A create and a replace (v1 or v3
  `PUT`) still store a `null` as sent. Arrays are replaced whole. The merge is nested: a profile re-sent with
  part of its `store` keeps the named profiles it leaves out; to remove one, send `store: {"<name>": null}` or
  replace the profile with `PUT` (as the profile editor does).
- A device status re-sent with an `identifier` that is already stored is not stored again and does not change
  the stored record (no new `srvModified`); the reply carries the stored `_id`, on API v1 and v3. API v1
  entries and device status match a re-send on `identifier`, as treatments do; an entry whose `identifier`
  matches nothing still matches on its time and type.
- Quieter server logs (BF-193): each write is logged as a summary, not the record. Set `DEBUG_LOGGING=true` to
  see the records clients send; debug logs then contain health data. Log lines change text.
- API v1 profile uploads (#8852): malformed entries and binary bodies answer 400, and a batch is capped at
  10,000 records, as on the other bounded v1 upload routes.
- BF-92 (#8842): a page showing `---` now presents device and other non-glucose alarms (a MINOR change
  under the policy's rule R2, with this note); BF-190, BF-93, BF-180, BF-159's token half and BF-160.
- The first start on an empty database waits for index creation (about 3 to 4 s on MongoDB 8.0), and a
  long index build logs a warning after 20 s and carries on (#8849).
- Dose labels round correctly on midpoints (#8851).
- The Bolus Wizard Preview and Careportal Bolus Wizard unit fixes (BF-172, BF-173) and the profile
  picker (BF-174); BF-09 (the socket's duplicate check keeps zero temps, cancels and zero amounts); #8816's snooze; #8812 and #8808's report figures.
- The glucose pentagon and PGR in the Distribution report (#8860): what the five values and the risk figure
  are, that the report withholds them when too little of the period has readings, and the PR's own caveats
  carried verbatim: the withholding rules are "implementation guards, not validated clinical PGR
  thresholds", PGR is a research metric, and the numerical checks "do not constitute third-party clinical
  validation". It is a report figure, not a treatment recommendation; talk to the care team before acting
  on it.
- One stored-text change from `sanitize-html` 2.18.1 (#8835): a malformed empty
  `<textarea></textarea/>` followed by an image with an event handler is now stored as the image tag
  without its handler (`<img src="x" />`), where 2.17.5 stored nothing (the empty string). The other 34
  corpus inputs are stored identically.
- Cut 2 (merged): page bundles, build and runtime separated (`npm ci` with development
  dependencies, then prune), no late minification, `DEBUG_MINIFY` without effect, the load-failure
  panel, and a third-party plugin that hooks into the page to be tested before upgrading.
- #8836: the page sends its credentials in headers instead of the status URL (query credentials still
  work for other clients); `body-parser` 1.20.9; `Referrer-Policy: no-referrer` and `Cache-Control:
  no-store` where described above; the runtime Docker image has no `npm` or `npx`; the one remaining
  `npm audit` chain (`@parse/node-apn` → `node-forge`), with what it measures.
- #8833: MongoDB 4.4 is no longer tested at all.
- Cut 2's IFTTT Maker change (`af7ba73a`): every key and every event is attempted when one fails; the log
  names the event, not the key.
- #8840: the Loopalyzer on and across daylight-saving days.
- The known issues at the tag.

## What a reviewer must verify before this is relied on

1. That AndyLow91's `b20a710b` and `bbca2892` give the results of the 2026-10-21 reproductions for all
   four unit combinations (BF-172, BF-173); the merged trees were not re-run here.
2. Which advisory is the 1 critical in the 2026-10-25 `npm audit` on both `dev` and the refresh
   branch; this file does not name it.
3. That the PR-body figures recorded here for #8835 to #8840 and the 2026-10-26 merges match a re-run;
   none was re-run by this programme.
4. Whether #8836's `body-parser` and status-URL changes, and cut 2's Maker log line, need a notice for
   15.0.9 operators: 15.0.9 has the same code or versions (above). Recorded here by mechanism only.
5. The S4 and S7 classifications marked *owed* in [Version](#version-1600-major).

---

*Draft, 2026-10-26. Prepared locally; nothing pushed, tagged, merged or published by this programme.
Requires maintainer review before anything here is relied upon.*


## Update — owner authority and local verification, 2026-11-05

| Scope / queue | Recorded result | Remaining boundary |
|---|---|---|
| Maintainer decisions: `MT-CONFIG-MIN`, `MT-IDENTITY-PLAN`, `T30-WIRING`, `MT-SECRETS-CONTRACT` | [Owner authority](../../docs/30-design/tenancy/owner-authority.md) and [decision rows](decisions.md#owner-authority-and-local-verification-2026-11-05) adopt bounded delegation, separate management authentication, human lifetime/freshness limits and the D22 local-verification amendment. | Policy adopted; complete role/ceiling/session/transfer implementation and production interoperability remain open. No candidate admission, listener enablement or release change. |
| Alignment-only prototype on committed instrument `e8c3c01ed`; actual CRM baseline `d4570e58` | [Reproduced measurement](../../docs/60-research/tenancy/owner-authority-local-verification-2026-11-05.md): 16 semantic checks, four non-vacuous controls, 24 cases / 2,880 timed operations. Current Vault-dependent and two local paths compared; same-token revocation across pools, tenant key isolation and settled outages exercised. | Synthetic authorization pipeline only. New ordinary-token operations use zero Vault calls; full HTTP/client performance, production capacity, full ceilings/session issuer and in-flight shutdown races remain UNMEASURED. Local alignment branch only; no CRM source changed. |

Verification: `make queue-validate && make queue`, `make queue-check`,
`make docs-links` and `git diff --check` passed for this lane. The broader
`make queue-status` baseline on main remains failing (for example
`P0-C-REMEDIATE ... 0/1 FAIL`, `T30-SCHEMA-CONFIG ... 0/1 FAIL`);
MT-CONFIG-MIN/MT-SECRETS-CONTRACT/T30-WIRING remain UNMEASURED in that run because
integration gates are skipped. Those existing measurements do not promote this
prototype. CRM full regression and site-check were skipped: no CRM application
source, rich site page or pages.yaml changed.

Lane worktree, anchors, next steps and peer ownership are in the machine-local,
untracked handoff at `externals/work/HANDOFF-owner-authority-2026-11-05.md`.
That local path is a maintainer reference and is excluded from the published site.


## Update — owner authority application integration, 2026-11-05

| Scope / queue | Measured current result | Remaining boundary |
|---|---|---|
| `T30-WIRING`, `MT-SECRETS-CONTRACT`: new-format API verification | [R48](../../docs/30-design/remedial/rc-16.0.0-integration-record.md#r48---local-public-token-verification-through-actual-api-on-3d5eac19-2026-11-05) accepts local CRM `3d5eac196256e447859373beadf7abf2efbfb2ce`: explicit API executable/config and shared handlers use the application verifier and one current PG snapshot. Full nonbrowser7058/80pending/0fail; browser684/0/0; full process16; archived new-format7 and four semantic red controls. Final prcheck OK. | Fixed locally, not merged/released or published by this lane. Separate coordinator incorporated the source correction into its frame-integration branch; that cumulative tree needs its own acceptance. No parent failure is waived by this branch's passing run. |
| Owner authority/QMS | [Adopted contract](../../docs/30-design/tenancy/owner-authority.md), current D22/plan corrections and historical census/schema provenance are reconciled. The lab imports application code; no standalone verifier duplicate remains. Actual revocation and Vault/PG outage behavior are recorded in R48. | New-format state remains operator-provisioned; automatic legacy issuance migration, complete human/refresh sessions, proposed-grant ceilings, production provider/key distribution and M5 streams remain open. Legacy8h exchange/single behavior preserved. No RC admission, listener exposure or milestone promotion. |

This application acceptance supersedes the earlier prototype-only readiness boundary;
the earlier immutable prototype measurement remains evidence for its own instrument.
Queue/links/site checks for the joined QMS branch are recorded in the local handoff.
The #8898 coordinator owns final queue/dashboard/next-gen-map reconciliation and
maintainer-operated publication of the combined branch.

### Update — frame acquisition and concurrent-read characterization (2026-11-05)

| Lane | Tree and measured status | Remaining boundary |
|---|---|---|
| Cumulative REST frame / owner-authority join | `codex/frame-integration-20261105` at `1c55098a3d4bcf3d871bcd345f159ce444d6e458`; [R49](../../docs/30-design/remedial/rc-16.0.0-integration-record.md#r49---cumulative-frame-acquisition-and-concurrent-read-characterization-on-1c55098a-2026-11-05) records final full/browser and archived14 acquisition/4 concurrency positives, six semantic controls and test-fixture red/green correction. R48 source and evidence preserved. | Existing bounds/frame/statistics/identity policies remain explicit; actual PG HTTP can combine old entries/new treatments across an atomic writer commit. Shared extraction and stronger consistency remain open. |
| Independent evaluator frame | `codex/evaluator-frame-20261105` at `5173864da1835da7aecf1f73121b28463f6a6a70`; [R50](../../docs/30-design/remedial/rc-16.0.0-integration-record.md#r50---independent-evaluator-frame-characterization-on-5173864d-2026-11-05) records full6690/3pending/0failure, browser684, parent archived38 and two semantic controls. | Actual A/B acquisition then real-trigger B/B, callback-error retention/recovery and no late fake-provider delivery. No DB cancellation/internal-handoff guarantee, logical subscriber change, REST join or multitenant evaluator admission. |
| Owner authority | Adopted contract and R48 optional data-token verification incorporated; owner gate registered with actual-HTTP signature control. | Full human issuer/refresh, individual-setting catalogue, proposed-grant/delegation ceilings, production provider/key operations remain incomplete. |
| Dashboard and next-gen map | Source/dashboard regeneration, queue validation/check and document links pass. Map rendered from `3a27f5cd9eb8834e01c779d5fb862f19525ed6dd`; pages.yaml pins it. Site-check passes with zero warnings/unresolved links; headless Chromium card selection, all track toggles, keyboard dependency highlighting and decision/background selection pass with zero page errors (external HTTP(S) blocked). | Runtime characterization remains in progress; no M0-M6 promotion, RC admission, publication or agent push. |

Machine-local lane detail: `externals/work/HANDOFF-frame-integration-20261105.md`.
The earlier predecessor full run failed fixture setup; it is recorded in R49 and
superseded only by the final cumulative measurement. Published drafts remain at
their separately captured remote heads until the maintainer publishes this work.


### Update — next lanes and capacity hold (2026-11-05)

| Scope | Recorded source and status | Acceptance boundary |
|---|---|---|
| Frozen accepted baseline | REST `1c55098a`, R49 full7076/80pending/0failure and browser684; independent profile `5173864d`, R50 full6690/3pending/0failure and browser684. | Existing measured scope retained; new lane candidates do not replace these heads. No fresh runtime or remote-CI result is produced by this records-only upkeep. |
| NEXT A — private acquisition | Separate CRM `e5fe0b5e`: bounded14/4 plus semantic controls and browser684; alignment cache-control `334dc571` **NOT JOINED**. | Full exit7/ENOSPC/NUL/truncated campaign remains **UNACCEPTED** with individual failures unclassified. Final prcheck/evaluator adaptation **NOT RUN**. |
| NEXT B — settings | Separate `0a4a7d59`: focused12/predicate/projection controls; only product change is global PG sort cap4→5. | Full/browser/cross-binding/sort-cap controls/prcheck **PENDING capacity**. No broader settings/query/resource acceptance. |
| NEXT C — owner enforcement | Accepted R48 baseline retained; new proposed-grant/ceiling enforcement has no accepted head. | **UNMEASURED**, source preparation/runtime acceptance on HOLD; no issuer/refresh or full catalogue completion. |
| NEXT D — replica history | [Immutable measurement](../../reports/tenancy/rest-replica-history-characterization-2026-11-05.md) at `2a6eaf73`: five actual HTTP characterization cases demonstrate the **FAILED exclusive-history guarantee**. Latest test/cleanup candidate `714f6c8b` supersedes `d93b7fca`. | Equal raw timestamps across successive process writes omit a later row from history despite addressed GET success. Same-process+1/restart+2/foreign unchanged are bounded controls. Corrected controls/cleanup/full/browser/prcheck remain PENDING; no clock fix or replica acceptance. |
| Capacity and ownership | Reproduced root snapshot453G/431G/0available; /home96G available. All new DB/full/browser campaigns on global HOLD. Separately inventoried3779 unattached anonymous volumes await user approval; no deletion. | Own cleanup cannot reconstruct orphan ownership. No peer/global deletion, milestone promotion, queue-state/gate-reference change or new numbered acceptance allocation. Central joins and runner/gate cleanup have separate owners. |

Lane figures are **read-derived** from the local handoffs and immutable replica
capture; the accepted baseline remains in R49/R50. The [dated continuation](../../docs/archive/tenancy/multitenant-delivery-roadmap-2026-11-02.md#next-lanes-and-shared-capacity-hold-2026-11-05)
owns sequencing and limits. Unique timestamp allocation alone is read-derived
insufficient for commit ordering; a same-data-commit/fencing design is still under
investigation. No production clock fix, operator-visible runtime change, release
admission or push was made by this upkeep.

Machine-local untracked references: `externals/work/HANDOFF-next-lanes-20261105.md`,
`externals/work/HANDOFF-private-acquisition-extraction-20261105.md`,
`externals/work/HANDOFF-settings-differential-20261105.md`,
`externals/work/HANDOFF-rest-replicas-20261105.md`.


### Update — accepted settings and serialized recovery (2026-11-06)

| Scope | Reproduced evidence, independently read from owned logs | Remaining work |
|---|---|---|
| R51 settings `33870764` | Root integration FF exact tested tree; full7089/80pending/0failure, browser684, tier503files/8tiers, final prcheckOK. Parent archived12/three semantic controls/restored12. | Only global PG sort cap4→5 product change. Six-key refusal, regex/dotted PG500 limits, performance/client/replica scope remain explicit. No milestone promotion. |
| Failure and correction | Earlier0a full Vault duplicate-mount400; ordered pair12+setupfailure. Fixture-only unique owned mount/cleanup correction gives25/0 and final full acceptance. | Failed campaign not accepted or classified ENOSPC. R49/R50 historical captures unchanged; independent profile not joined. |
| Bounded cleanup | Authorized inventory3779deleted/0errors/no outside-inventory loss; smoke4realcases/sixvolumesabsent; gate audit15containers/25volumesabsent/private0700/0600. B75recordedvolumes absent,219preserved remain. | Unknown40nested volumes preserved; no complete leak-freedom claim. Canonical new all flags await future combined execution. |
| Next serial lanes | B released; A fresh full active; D/C/clock queued. | A/C/D/clock unaccepted. D history gap unfixed; adopted clock proof/source preparation and contention/latency unmeasured. Root owns cumulative joins/acceptance. |

[R51 and serial continuation](../../docs/archive/tenancy/multitenant-delivery-roadmap-2026-11-02.md#accepted-settings-differential-and-serial-recovery-2026-11-06)
links the adopted proof plan and scope. Local evidence: `HANDOFF-settings-verification-20261106.md`
and `HANDOFF-cleanup-settings-runtime-20261106.md`; raw Docker identifiers remain local.
No operator runtime deployment, release admission, candidate CI or application push claimed.


### Update — native acquisition acceptance and pending B+A composition (2026-11-06)

| Scope | Reproduced evidence independently read from owned logs | Remaining boundary |
|---|---|---|
| R52 native REST `e5fe0b5e` | Fresh full7080/80pending/0failure; same-head prior browser684; final prcheckOK. Acquisition14/concurrency4 +six semantic controls/restored14/4; caller4/reused-target2fail/restored4. |26-line private allocation helper only; callers retain policy/lifecycle. No atomic revision, common snapshot, full consistency or milestone promotion. |
| Root incorporation `c7778436` | B338+A incorporated; tier504files/8tiers passes. R51/R49/R50 remain unchanged captures. | **Combined full PENDING**, not accepted. No application push. |
| Independent profile preparation `2ee8b493` | Source-only descendant of5173864d; identical helper blob, views-only integration, evaluateCycle retained. | New runtime38/controls/full/browser/prcheck **UNMEASURED**; separate lane, no REST join. |
| Ownership and next slots | A finished; D/clock lower proof active, HTTP/full/bench pending, Cqueued. A outer3containers/5recordedvolumes verified absent. | Nested old fixtures unaudited/unknown volumes preserved; no new leak-freedom claim. D history gap unfixed, no production clock fix. |

[R52 continuation](../../docs/archive/tenancy/multitenant-delivery-roadmap-2026-11-02.md#accepted-private-acquisition-and-pending-composition-2026-11-06)
and the R52 integration record retain exact native acceptance commands/limits.
Local evidence: `HANDOFF-private-acquisition-extraction-20261105.md` and its
home recovery logs/audits. Original incomplete ENOSPC campaign remains preserved.


### Update — selected owner policy acceptance and pending B+A+C full (2026-11-06)

| Scope | Reproduced evidence independently read from captured logs | Remaining boundary |
|---|---|---|
| R53 native17f9a457 | Full7127/80pending/0failure/browser684/finalprcheckOK; actual22/affected26/static32. Parent archived22, four0/1semantic guards with persisted effects, restored22. | Explicit ownerPolicy transaction REST37 only; R48readers unchanged. No listener/full owner completion. |
| Root4a15802c | B+A+C incorporated; tier506files/8tiers PASS. R51/R52 captures unchanged. | **Combined fullPENDING**, not accepted; clock/profile2ee not joined. |
| Fixture correction and cleanup | Prior3106 affected25/1 retained;17f migration003+004/prior3checksums correction gives26. Native full18containers/26volumereferences and browser3/5 verified absent; parentgate6/6 absent/private0700/0600. | No global leak-freedom claim, unknown resources untouched. No guard weakening or policy change after3106. |
| Clock readiness | Sanitized lower8+controls; all-domain oldSQL42703/corrected9. Corrected DHTTP retry active. | HTTP/full/bench acceptance pending; no clock joined/default enabled. New correctness flags source registered, future combined runtime unmeasured; benchmark off. |

[R53 continuation](../../docs/archive/tenancy/multitenant-delivery-roadmap-2026-11-02.md#accepted-selected-owner-policy-and-pending-composition-2026-11-06)
and [public C record](../../reports/owner-subject-policy-acceptance-2026-11-06.md)
retain exact scope. Human issuer/refresh, full wildcard/default catalogue,
existing-grant clamping, DELETE policy and production listener remain unimplemented.
No M0–M6 promotion or application push.


### Update — cumulative B+A+C acceptance (2026-11-06)

| Scope | Reproduced evidence independently read and hash-verified | Remaining boundary |
|---|---|---|
| R54 local35903069 | B338+A e5+C17f combined full7144/80pending/0failure, browser684, settings12, fresh finalprcheckOK; currentdev4a contained/sourceclean, changedJS0errors/0warnings. | R51–R53 native/R49–R50 historical captures unchanged; no milestone promotion/default enablement. |
| Final normalization fix | Test-only unused-binding cleanup after4a158 preserves normalized comparison fields. | No product scope change; earlier sandboxDNSprcheckfailure preserved, finalsuccessfulretry accepted. |
| Successful campaign cleanup | Captured3/5+18/26+3/5 containers/volumes absent;219preserved present, private0700/0600 audit. | Bounded successful recorded resources only, no globalleakfreedom/unknownownership cleanup. |
| Open work | Clock and independent profile2ee not joined. Existing ownerREST37/caller-specific acquisition limits retained. | Humanissuerrefresh/fullcatalogue/existinggrantclamping/productionlistener, commonrevision/strongersnapshot, clockHTTP/full/bench acceptance pending. No newDresult allocated. |

[Public cumulative capture](../../reports/tenancy/serial-cumulative-acceptance-2026-11-06.md)
and [R54 continuation](../../docs/archive/tenancy/multitenant-delivery-roadmap-2026-11-02.md#accepted-cumulative-settings-acquisition-and-owner-policy-2026-11-06)
retain exact commands/hashes/limits. No application push, RC/deployment admission or
new policy decision is made by this measurement.


### Update — independent profile acceptance and focused clock repair (2026-11-06)

| Scope | Reproduced capture, independently read/hash-verified | Remaining boundary |
|---|---|---|
| R55 independentPROFILE2ee | Full6690/3pending/0failure/browser684, archive38/http-clinical-retention each0/1semantic/restored38/finalprcheckOK. All22artifact lengths/hash verified;11containers/20volumes recorded absent across7serialcampaigns. | Separate accepted REST359 and PROFILE2ee, no merge/runtime-role/subscriber/notification promotion. Fourthdeclaredv1closed2eeUNMEASURED/prior517historical. R50–R54 immutable. |
| Focused clock repair3532/117 | Actual7passing/1benchmarkpending; negative0/2(primaryECONNRESET/lostHTTP, secondary strict workerexit1); restored1/503/same-workerGET200/POST201/strict0. Raw3/source5/preparer/monitor hashes verified;6containers/9volumes absent per capture. | Focused branch evidence only, not clockready/fullacceptance. Clock unjoined/default-off; assembledsingle/Mongo/full/browser/prcheck/broadercontrols/performance UNMEASURED. Original fatal diagnostic retained. |

[Canonical profile report](../../reports/private-acquisition-profile-2026-11-06/README.md),
[artifact index](../../reports/private-acquisition-profile-2026-11-06/artifact-index.json)
and [focused recovery record](../../reports/tenancy/tenant-clock-http-fixed-recovery-2026-11-06.md)
retain exact scopes. No new numbered clock acceptance, milestone/RC promotion,
production enablement or application push; no policy decision changed.

Local continuation and next frozen clock batch: `externals/work/HANDOFF-serial-verification-20261106.md` (local, untracked).


### Update — frozen-head B4a controls stopped on instrument mismatch (2026-11-06)

| Scope | Reproduced captured evidence | Remaining boundary |
|---|---|---|
| Frozen `65bb8456`, R57 partial | 11/12 positive instruments; 27 semantic controls; 8/12 restored instruments. | Authority control invalid before Mocha: expected source boundary missing. B4a incomplete; B5 acceptance prerequisite unsatisfied. Missing controls/restores and subject-admin UNMEASURED. |
| Ownership and limits | Runtime released after stop; recorded gate-owned mounts audited absent. Prior captures preserved. | Older fixture anonymous volumes preserved; no global leak-freedom claim. No gate/app repair, queue ref moves, promotion, default enablement or push. |

[Partial report](../../reports/tenancy/gate-controls-65bb8456-2026-11-06.md) and [machine capture](../../reports/tenancy/gate-controls-65bb8456-2026-11-06.json). Lane detail: `externals/work/HANDOFF-codex-b4a-20261106.md` (local). No maintainer policy decision changed. Root coordinator owns disposition and queue ref moves.


### Update — frozen-head B4a continuation complete (2026-11-06)

| Scope | Reproduced evidence | Remaining boundary |
|---|---|---|
| Frozen65bb, R58, authority instrument3845 | Combined12positive instruments/32semantic controls/12restored positives; original R57 unchanged. Ten continuation runs supply missing measurements. | Profile absent/excluded. B5 joined-head full/browser/corpus acceptance separate. Root owns queue refs. |
| Runtime and cleanup | Slot released; diagnosed owned mounts audited absent; source clean. | Older fixture anonymous volumes preserved; no global leak-freedom or mutated-authority-effects count. No application repair, promotion, default enablement or push. |

[Continuation report](../../reports/tenancy/gate-controls-65bb8456-continuation-2026-11-06.md) and [machine capture](../../reports/tenancy/gate-controls-65bb8456-continuation-2026-11-06.json). Lane detail: `externals/work/HANDOFF-codex-b4a-20261106.md` (local). No maintainer policy decision changed.


### Update — completion batches adopted (2026-11-06)

| Scope | Decision and current work | Acceptance boundary |
|---|---|---|
| Multitenant completion schedule | Maintainer approved [larger completion batches](../../docs/30-design/tenancy/multitenant-integration-batching-plan-2026-11-06.md#5-current-completion-schedule-adopted-2026-11-06): A data/control/clients (M0–M4), B durable runtime (M5), C synthetic operations (M6). | Targeted checks during implementation, then comprehensive labs/V&V and final regression on each frozen completion candidate; existing milestone criteria remain mandatory. |
| Early uncertainty reduction | Stamp/recovery, actual-client differences, owner authority/lifecycle and populated restore/resource proofs remain bounded experiments before dependent assumptions expand. | No new provider, authenticator, retention rule or numeric limit selected. Missing implementation, measurement and decisions remain distinct. |
| Parallel delivery | Independent implementation, fixtures and test preparation proceed concurrently; isolated runtime overlap depends on measured capacity/ownership. | The local full/browser/corpus slot is a resource constraint. Final-tree evidence, exact-head controls, approved differences and failed-capture preservation remain required; no milestone/default/release promotion. |

This records the maintainer's execution decision, not a new application measurement.
No application or operator-visible runtime behavior changed in this records-only
lane. Lane detail: `externals/work/HANDOFF-codex-completion-batches-20261106.md`
(local, untracked). B4a/B5/M4 source and evidence remain on their respective lanes
until the coordinator joins them; their acceptance figures are not recaptured here.


### Update — completion-batch incorporation and early proofs (2026-11-06)

| Scope | Reproduced source evidence | Remaining boundary |
|---|---|---|
| Batch A local candidate `863c8a2b` | Corpus inventory correction, typed role table and M4 identity/literal-slash repairs incorporated; selected source checks 201 passing; tier registry 512 files / 8 tiers; inventory 34 suites. | Actual-client rerun and exact-head comprehensive acceptance remain UNMEASURED. Owner/session, import/resource and remaining milestone criteria stay open. |
| M5 research `25c8441a` | Coordinator independently ran the isolated file-backed recovery prototype: 8 passing / 0 failing / 0 skipped. | No production consumer/DDL. PostgreSQL recovery, RLS and concurrent replay UNMEASURED; projection/bootstrap and checkpoint bookkeeping authority remain decisions. |
| Coordination records | Instrument repair and immutable R57/R58 records combined with the approved A–C completion schedule; queue-check and document links pass. | No queue-ref moves, milestone promotion, default enablement, application-ready claim or push. |

[Source-check capture](../../reports/tenancy/completion-batch-source-checks-2026-11-06.md)
owns commands and limits. Local detail:
`externals/work/HANDOFF-codex-completion-coordination-20261106.md` (untracked).
Owner-clamping and populated-import proofs continue independently; production
decisions are deferred, research continuing.


### Update — actual M4 clients, bounded measurement (2026-11-06)

| Scope | Reproduced measurement | Remaining boundary |
|---|---|---|
| `M4-CLIENT-LAB`, archived CRM `35903069` | Actual cgmsim, oref0 and connector programs executed with synthetic data against single-site Mongo and the explicit two-tenant PostgreSQL preview. The [dated evidence](../../reports/m4-client-binaries/2026-11-06/README.md) holds versions, captures, classifications and controls. | Default compatibility gate is not met. Unapproved stored-identity and lookup differences remain; no application repair or milestone promotion. |
| Local lane | Isolated branch `codex/m4-client-lab-20261106`; paused main/index snapshot preserved. | Lane detail: `externals/work/HANDOFF-codex-m4-20261106.md` (local, untracked). No push; B5 full/browser/corpus acceptance remains separate. |

This measurement changes no release placement, operator-visible behavior or policy decision.


### Update — combined Batch A actual clients (2026-11-06)

| Scope | Reproduced capture | Remaining boundary |
|---|---|---|
| `M4-CLIENT-LAB`, archived `863c8a2b` | One combined actual-client campaign on committed instrument `c724b38aa`: 106/106 checks, 21 cells per stack. Identity preservation and header lookup now match. [Immutable report](../../reports/m4-client-binaries/2026-11-06-batch-a/README.md). | One unexplained legacy 401 envelope difference; gate-not-met. Root's dedicated compatibility repair and revised-freeze affected-client measurement precede B5 acceptance. No waiver or promotion. |

Root owns the next integration-record allocation after combining B4a and Batch A records;
M4 reserves no R59. Local ownership/transfer: `externals/work/HANDOFF-codex-m4-20261106.md`.


### Update — bounded M4 lab locally accepted on revised freeze (2026-11-06)

| Scope | Reproduced capture | Remaining boundary |
|---|---|---|
| `M4-CLIENT-LAB`, archived `c0e8ad3c` | Actual registered default gate 82/82 checks, 19 cells per stack, zero differences/missing cells, exit 0. Focused oref0 positive/restored 68 each; oracle six semantic failures; planted reply one unexplained. [Immutable accepted capture](../../reports/m4-client-binaries/2026-11-06-revised-freeze/README.md). | Local ready-to-push proposal only until root integrates instrument/records and retires exact archived draft. B5 comprehensive acceptance and broader M4 milestone limits stay separate. |

The 863 combined capture and earlier failed/provenance controls remain unchanged. No classifier
waiver, application push or M0–M6 promotion was made by this lane. Root owns the next R record
allocation and publication. Local transfer: `externals/work/HANDOFF-codex-m4-20261106.md`.


### Update — B7 design direction adopted (2026-11-06)

| Scope | Decision and evidence | Remaining boundary |
|---|---|---|
| B7 / `MT-RUNTIME-PLAN` | Maintainer adopted the [durable delivery design direction](decisions.md#b7-durable-multitenant-delivery-2026-11-06), with scalability/performance experiments informing implementation. The [contract](../../docs/30-design/tenancy/durable-event-delivery-contract-2026-11-06.md#11-maintainer-acceptance-and-experiments) defines correctness and capacity questions. This is a decision record, not a new runtime measurement. | Distributed recovery and capacity remain UNMEASURED; queue state stays in-progress/no-gate. No operator-visible behavior, default, milestone or release admission changes. Batching-plan and queue edits remain with their active session owners. |


### Update — coherent compatibility batch accepted; M0 promoted (2026-11-06)

| Scope | Measured disposition | Remaining boundary |
|---|---|---|
| Final application `d89a44e1` | [R60](../../docs/30-design/remedial/rc-16.0.0-integration-record.md#r60---coherent-ci-client-batch-and-m0-foundations-2026-11-06) accepts the corrected corpus/final prcheck, actual-client gate and product-identical full/browser/foundation captures. | Every campaign retains its actual executed head; failed corpus capture and original safety guard preserved. Performance benchmark pending, not passed. |
| M0 foundations | Promoted against the existing isolation, binding, rollback, reuse, paired-control and schema/startup criteria. | D21 lab preview only; no default, production role or release enabled. M1–M6 retain their own criteria. |
| `M4-CLIENT-LAB` | Bounded measurement complete and canonically integrated; direct default gate and meaningful oracle/classifier controls accepted. | Broader M4/v3/mobile/onboarding/connector criteria remain open. |
| B7 and later implementation | Existing maintainer approval reconciled from its separate decision branch; dormant replay, owner-clamping acceptance and populated recovery labs continue independently. | Earlier draft wording was stale documentation. These later source branches are not included in this compatibility candidate or admitted to runtime. |

The [final acceptance capsule](../../reports/tenancy/batch-a-acceptance-d89a44e1-2026-11-06.md)
and [client capture](../../reports/m4-client-binaries/2026-11-06-revised-freeze/README.md)
own figures and limits. Publication and remote checks follow separately.
Lane detail: `externals/work/HANDOFF-codex-completion-coordination-20261106.md` (local, untracked).


### Update — accepted batch published and remote verification complete (2026-11-06)

| Scope | Reproduced publication/read-back | Remaining boundary |
|---|---|---|
| Draft #8898 | Normal fast-forward to exact accepted `d89a44e1`; description refreshed with R60 scope and successful [CI](https://github.com/nightscout/cgm-remote-monitor/actions/runs/42296422151)/[CodeQL](https://github.com/nightscout/cgm-remote-monitor/actions/runs/42296422116) links. | Draft remains open; no merge to dev, release/tag or serving-default change. |
| Remote verification | [R61](../../docs/30-design/remedial/rc-16.0.0-integration-record.md#r61---published-batch-remote-ci-and-codeql-verification-2026-11-06) records 15 successful CI jobs, three expected release-publication skips and CodeQL success on d89. | Benchmark remains pending; remote green does not close M1–M6 or enable later dormant code. |
| Alignment records | Accepted main `ed18a7bce` published; CI and site build/check/publication passed. Paused M4 draft was retired only after exact archive verification and takeover-owner confirmation. | Both November draft correspondence files preserved. Later owner/replay/operations work proceeds in a separate integration lane. |

The [publication snapshot](../../reports/tenancy/batch-a-publication-d89a44e1-2026-11-06.json)
owns exact remote job state. The connector lacked PR metadata-write permission;
the verified author CLI applied the prepared description while retaining draft
state. No comments, reviews or correspondence were sent.

### Update — tenancy navigation and visualization reconciliation (2026-11-06)

| Scope | Disposition | Evidence / limit |
|---|---|---|
| Published #8898 | Read-derived GitHub metadata: OPEN/draft at `d89a44e182e771ef84aa99190ec166e6ff0d9772`, based on dev `4a482627bfdafb1fef8dcbe0ac6c484811cae563`. | [CI run](https://github.com/nightscout/cgm-remote-monitor/actions/runs/42296422151) and [CodeQL](https://github.com/nightscout/cgm-remote-monitor/actions/runs/42296422116) completed successfully at read-back. The opt-in PostgreSQL/MongoDB/Vault corpus and aggregate Tests pass jobs succeeded; publication jobs were skipped. No merge or release. |
| Current documents | Reconciled next-gen map and delivery-roadmap summary to existing R60 acceptance: M0 promoted, bounded client lab complete, clock joined, benchmark pending; M1–M6 remain open. | No application campaign rerun or new promotion. Independent R55 profile and later dormant branches retain separate scope. Architecture diagrams remain pinned to their stated historical source. |
| Reader path | Added [tenancy reading guide](../../docs/30-design/tenancy/README.md), linked from programme status/roadmap. | Classifies current coordination, decision owners, specialist contracts and retained evidence. Superseded platform checkpoints are retrievable through a pinned history row; older roadmap checkpoints are collapsed with anchors preserved. Larger decision/evidence documents retain unique content pending full-cluster consolidation. |

Reproduced documentation verification: queue-check, docs-links, site-check and
map interaction checks pass; the new guide's broken-link control fails on the
missing target and passes after restoration. Map interactions expose R60, blocked
M3 dependencies, adopted B7 and M0 foundation acceptance without page errors.
The separate default `make queue-status` audit on the unchanged starting tree
reports PASS=198 / FAIL=43 / UNMEASURED=124; integration gates are skipped there.
Those wider gate failures are not repaired or represented as green by this
documentation reconciliation. No application campaign was rerun.

### Update — bounded owner reader and recovery batch accepted (2026-11-06)

| Scope | Reproduced acceptance | Remaining boundary |
|---|---|---|
| Local candidate `83582e87` | [R62](../../docs/30-design/remedial/rc-16.0.0-integration-record.md#r62---bounded-owner-reader-replay-and-populated-recovery-batch-2026-11-06) accepts the joined optional subject-reader policy, persisted current-row replay and populated PG recovery lab. | Unselected defaults; no owner/realtime/evaluator role or production recovery enabled. M1–M6 remain open. |
| Comprehensive application V&V | Fresh `87133959` full 7226/99pending/0failure, browser 684/0/0, 35-suite corpus 460/1benchmarkpending/0failure, actual default clients 82/82 and affected pooler 9+4. | Complete path identity permits reuse on the source-control-runner-only 835 descendant; final prcheck ran on 835. Actual execution heads remain explicit. |
| Meaningful early proofs | Archived native selected-reader intersection and persisted typed-replay controls go red and restore; original focused restore/oracle failures are preserved beside their bounded repairs. | No every-transition/external exactly-once, selected root-client parity, performance, key/provider or full lifecycle claim. |

The [comprehensive capsule](../../reports/tenancy/control-recovery-acceptance-87133959-2026-11-06.md),
[archived controls](../../reports/control-recovery-gates/2026-11-06/README.md)
and [runner-only continuation](../../reports/tenancy/control-recovery-runner-continuation-83582e87-2026-11-06.md)
own actual measurements and limits. Publication and remote CI are recorded after execution.
Lane detail: `externals/work/HANDOFF-codex-completion-coordination-20261106.md` (local, untracked).

### Update — selected subject client compatibility measured (2026-11-06)

| Scope | Reproduced result | Compatibility disposition |
|---|---|---|
| Explicit selected subject reader | [R63](../../docs/30-design/remedial/rc-16.0.0-integration-record.md#r63---selected-subject-actual-client-compatibility-boundary-2026-11-06): three actual oref0 token-upload workflows match reference response summaries/exits/stored values; current-ceiling tightening refuses next upload with no effects. | Bounded subject-token evidence; raw reply-field and broader workflow parity remain unmeasured. Source stays dormant. |
| Root-client boundary | Actual cgmsim root upload gets 503/no effects under selected mode, versus 200 unselected. | Root exclusion is intentional; 503 mapping needs disposition. Universal selected-mode no-impact condition is not met; default behavior remains accepted and unchanged. |
| Sensitive control | Ceiling-intersection ablation returns 200 and changes stored state; fresh restoration passes. | Separate targeted experiment on871, not a new full campaign on835 or a milestone promotion. |

The [selected-client capsule](../../reports/selected-owner-clients/2026-11-06/README.md)
preserves precise scope and independently audited cleanup. No activation decision is inferred.

### Update — control recovery publication verified and clock workload captured (2026-11-06)

| Scope | Reproduced result | Boundary |
|---|---|---|
| Published #8898 `83582e87` | [R64](../../docs/30-design/remedial/rc-16.0.0-integration-record.md#r64---published-control-recovery-batch-remote-verification-2026-11-06): [CI](https://github.com/nightscout/cgm-remote-monitor/actions/runs/42303661682) and [CodeQL](https://github.com/nightscout/cgm-remote-monitor/actions/runs/42303661681) passed; all 15 CI jobs succeeded, three release-image jobs skipped. Draft description read back with current-head links. | No dev merge/release/default activation. R62 execution/reuse and R63 selected-client limits remain. |
| Alignment `74d273225` | [CI/site](https://github.com/bewest/rag-nightscout-ecosystem-alignment/actions/runs/42303565719) passed. | Peer main ancestry preserved; no competing source or publication changes. |
| Small native clock workload | [R65](../../docs/30-design/remedial/rc-16.0.0-integration-record.md#r65---bounded-tenant-clock-http-descriptive-workload-2026-11-06): four fresh cohorts, 40 HTTP201 requests each, zero errors/retries; p95 18.2–23.1 ms and throughput 303–339 successful requests/s in these short observations. | Descriptive only; no approved budget, steady-state/causal comparison or final independent stored-count oracle. Earlier pending corpus captures remain unchanged; no milestone promotion. |

The [publication snapshot](../../reports/tenancy/control-recovery-publication-83582e87-2026-11-06.json)
and [workload capsule](../../reports/tenancy/2026-11-06-clock-http-workload/README.md)
own measurements and limitations. Next socket/evaluator composition proceeds in a
separate source batch; no later code is included by these successful checks.

### Update — next joined socket evaluator proof exposes ordering gap (2026-11-06)

| Scope | Reproduced outcome | Next boundary |
|---|---|---|
| Unpublished joined `1990f453` | [R66](../../docs/30-design/remedial/rc-16.0.0-integration-record.md#r66---joined-socket-evaluator-native-attempt-and-ordering-gap-2026-11-06): one native invocation 9/0/2; evaluator7 pass, socket2/2. | Batch not accepted. Rollback green is vacuous after pre-write refusal; held-commit timeout is not semantic evidence. |
| Socket ordering | PG refuses canonical unsorted bounded dedup; required insertion-order column is absent in these domain schemas. | Optional successor capability and mixed-version/populated characterization prepared separately. No arbitrary sort or silently weakened query contract. |
| Ongoing implementation | Evaluator controls and explicit headless owner-listener composition continue. | Published835 and its green CI/CodeQL remain unchanged; no broad milestone promotion. |

[Failed attempt capsule](../../reports/tenancy/socket-evaluator-native-attempt-1990f453-2026-11-06.md)
retains exact evidence and independently verified cleanup. No whole acceptance
campaign was spent on this head after its targeted prediction failed.

### Update — recovered clinical projection controls measured (2026-11-06)

| Scope | Reproduced native evidence | Remaining gate |
|---|---|---|
| Dormant evaluator constructor on1990 | [R67](../../docs/30-design/remedial/rc-16.0.0-integration-record.md#r67---bounded-recovered-clinical-projection-native-controls-2026-11-06): typed-key removal gives111vs222; skipped bootstrap loses stored123; both explicit assertions red, fresh restoration7/0/0. | Bounded clinical recovery only, without full1990 acceptance or M5 promotion. |
| Independent inputs and instrument | Physical row/type/value checks precede clinical assertions; consistent scratch-only optional-chain assertion keeps expected123. | Live role scheduling, socket delivery, ack/notification/provider and performance remain. |
| Larger implementation batch | Headless-owner composition and socket capability work continue independently. | Published835 remains fully green; known socket failure and prototype migration limits are preserved. |

The [native capsule](../../reports/projection-evaluator-gates/2026-11-06/README.md)
retains reports, hashes and exact resource absence. No additional broad campaign
was spent on this bounded control slot.

### Update — fresh schema socket DATA prototype measured (2026-11-06)

| Scope | Reproduced evidence | Boundary |
|---|---|---|
| Optional successor catalogues | [R68](../../docs/30-design/remedial/rc-16.0.0-integration-record.md#r68---fresh-schema-socket-data-prototype-native-controls-2026-11-06): matrix3 passes, including atomic populated refusal and old-catalogue MIG_UNKNOWN. | Old application binary not executed; startup consequence inferred. No transparent populated upgrade/downgrade or rollout adopted. |
| Corrected single/Mongo reference | Fixture-only12919 passes4native cases, including multiple-match stored identity and reached commit/abort boundaries. | Original0d628 wrong-mode reference failure retained; no actual Android binary claim. |
| Meaningful native controls | Early callback while uncommitted; substituted role commits A-row; each exact assertion red, restored4green. | Dormant fresh-schema DATA component only; final joined V&V still required. |

[Prototype capsule](../../reports/tenancy/socket-order-prototype-native-2026-11-06.md)
and [native controls](../../reports/tenancy/socket-data-controls-12919f55-2026-11-06/README.md)
own source attribution, proof/observation changes, raw hashes and resource absence.

### Update — multitenant records reconciled to published #8898 `83582e87` (2026-11-06)

| Scope | Reproduced read-back (2026-11-06 23:41 UTC, `gh` and `git`) | Disposition |
|---|---|---|
| Draft #8898 | Head `83582e876dd193f4448f44c28e379fb5464a26c7` on `workspace/multitenant-20261102`, base `dev`, open, draft, mergeable; contains `official/dev 4a482627`; 172 commits and 245 files over dev (193 new, 52 modified, 0 deleted). 15 CI jobs passed, including the opt-in corpus job and three browser engines; CodeQL passed; 3 release-image jobs skipped by condition. 3 review events (CodeQL), 0 issue comments, 0 human reviews. | Matches R62 (accepted) and R64 (verified). Not merged, not released; no default or production role enabled. Placement stays as decided 2026-10-30: dormant and alpha behind `nightscout multitenant`, or deferred. |
| Documents re-pinned to `83582e87` | [Architecture comparison](../../docs/30-design/tenancy/single-and-multitenant-architecture.md) (every source link re-verified at the head; the write-clock anchor moved from line 62 to 64; a table of every dormant module the PR holds, with its governing record), [next-gen plan](../../docs/30-design/platform/next-gen-platform-plan.md) and its data file, [delivery roadmap](../../docs/archive/tenancy/multitenant-delivery-roadmap-2026-11-02.md) current-acceptance paragraph, [tenancy reading guide](../../docs/30-design/tenancy/README.md), [batching plan](../../docs/30-design/tenancy/multitenant-integration-batching-plan-2026-11-06.md) (live read-back row, B1/B2 closure, R62–R64 in §5), [programme status](../../docs/00-overview/PROGRAMME-STATUS.md) (D1–D23, the preview named), [NEEDS-A-HUMAN](../../docs/00-overview/NEEDS-A-HUMAN.md) (what waits on a person for the preview). | Read-derived reconciliation; no application campaign rerun and no milestone promoted. R40–R43 citations are retained as history where pages cite them. |
| Queue | Item notes for `ST-PG`, `TEN-LAB`, `T30-WIRING` and `T30-TENANT-ADMIN` lead with the R62/R64 state. Gate `--ref` values are unchanged: owner-reader and durable-replay already pin `87133959` (R62); the other multitenant gates keep their native capture pins. | Replay of those gates on the frozen head (batching plan rule 6) is UNMEASURED: at the time of this update the runtime slot held the event-payload lane's focused run, so no gate campaign was started. |

Lane detail for the open source lanes stays in their local handoffs
(`externals/work/HANDOFF-*-20261106.md`, untracked).

### Update — headless owner and final-floor controls, compatible reader removal (2026-11-06)

| Scope | Reproduced outcome | Remaining boundary |
|---|---|---|
| Headless owner | [R70](../../docs/30-design/remedial/rc-16.0.0-integration-record.md#r70---headless-owner-native-wire-and-authority-controls-2026-11-06): actual4cd owner9, current-snapshot and listener physical red controls, fresh strict restoration9. Original Host-fixture and lifecycle-classifier failures preserved. | Operator-provisioned management credentials only; no human issuer/refresh or M2 promotion. |
| Final-floor event | [R71](../../docs/30-design/remedial/rc-16.0.0-integration-record.md#r71---transaction-final-floor-postgresql-component-control-2026-11-06): actual1acb core6, omitted final argument semantic red, fresh6. Independent physical rows/floor/precommit/foreign oracles. | Physical-marker component, no all-intent or M5/M6 claim; scoped core identity on e2 verified. |
| Local completion candidate | `e2a760bc326fca5ecf255f35a88bec229f13fb43` joins final-floor payload, fixes two real source-gate registrations after socket extraction, and removes reader clamping per maintainer. Full unit2304; corpus inventory39 retained. Writer owner-policy fences and existing credentials remain. | Fresh default clients, affected pooler, full/browser/whole-corpus and final prcheck underway; published draft #8898 remains835 until acceptance/publication. |
| Active instruments | Withdrawn reader-clamp gate/controls and executable selected-client lab retired. R62/R63 immutable captures retained, with a historical navigation stub and hash-matched published source snapshot. New bounded owner gate registered. | No default enablement, release admission or milestone-state promotion. |

Lane ownership and runtime phase: `externals/work/HANDOFF-codex-completion-coordination-20261106.md` (local, untracked). The final-floor source snapshot is preserved beside its public measurement; raw credential/state traces remain private.


### Update — tenancy execution journals consolidated and archived (2026-11-06)

| Scope | Disposition | Evidence and limits |
|---|---|---|
| Current reading path | [Tenancy decisions](../../docs/30-design/tenancy/multitenancy-decisions.md) preserves D1–D23 and their qualifications; the [delivery roadmap](../../docs/30-design/tenancy/multitenant-delivery-roadmap.md) preserves journeys, boundaries and promotion criteria. | Read-derived reorganization, not a new architecture decision, application campaign or milestone promotion. Later amendments retain their existing contract/release homes. |
| Retention | The complete decision/execution and delivery journals are in the [thematic archive](../../docs/archive/tenancy/README.md), with original headings, failed experiments, controls and measured-source boundaries retained. | [Preservation record](../../reports/tenancy/tenancy-journal-consolidation-2026-11-06.json): source prose and headings preserved; changes to retained bodies are Markdown-link destinations plus an explicit archive notice. Git retains intermediate revisions. |
| References and generated views | Reading guide, inbound references, queue evidence and platform-map sources distinguish current rules from archived evidence. Dashboard slice evidence now names its own document and heading, so new captures do not extend an archived journal. | Reproduced queue validation/generation/check and affected decision/specification gates pass. Dashboard tests cover local report references, broken paths/anchors, stale output and nonlocal refusal. Link controls reject both a restored dead active-plan reference and a broken archive link, then pass after exact restoration. |
| Claude continuation | Fresh backup/upgrade source continuation delivered local `f4e0548793f0c472233984b1ae2667eeba8da0e0`, with ACL prewrite refusal, rollback-target preflight, contract documentation and an opt-in native suite. | Read-derived handoff/source review: source-only unit/control evidence belongs to the continuation lane; original Claude worktree preserved. Native PostgreSQL and assembled-tree operational acceptance remain UNMEASURED. Integration/runtime ownership stays with the existing coordinator; no application push or role enablement. |

Backup/upgrade lane detail: `externals/work/HANDOFF-codex-backup-upgrade-continuation-20261106.md` (local, untracked).

Reproduced validation for the consolidation: five dashboard tests pass; all 224
references with heading fragments into the migrated documents resolve with the
site's GitHub-compatible slugifier. The affected T30-AUTH, registration, records
and authority gates pass; removing each current specification pointer produces
its expected failure and exact restoration passes. The separate default
queue-status baseline remains PASS=198 / FAIL=43 / UNMEASURED=124, with integration
gates skipped; this documentation work does not make those wider gates green.

Consolidation lane detail: `externals/work/HANDOFF-tenancy-journal-archive-2026-11-06.md` (local, untracked).

### Update — completion-focused orchestration applied (2026-11-06)

| Scope | Applied adjustment | Boundary |
|---|---|---|
| Durable guidance | Agent contract, tenancy completion plan, reading guide and handoff/evidence skills now use whole capabilities or explicit criterion closure as the unit of delegation. | Focused implementation checks and meaningful controls remain. Comprehensive acceptance belongs to the coherent frozen candidate; existing milestone and safety/authorization/compatibility requirements are unchanged. |
| Ongoing chats/subagents | Direction delivered to the active integration coordinator, M2 configuration implementation and backup/upgrade proof chats, with propagation to their subagents. | Valid in-flight checks may finish. The next handoff reports capability/criterion verdict, remaining blocker and next join, with immutable evidence linked; setup-only failures do not become product or milestone results. |
| Recordkeeping | The existing completion-batch decision was updated in place; each lane maintains one evolving handoff and each coherent acceptance batch its programme record. | Substantive failures, decisions and ownership transfers still receive prompt records. No new application measurement, milestone promotion or role enablement follows from this guidance change. |

Validation: queue-check (including document links) and both edited skills' validators pass. Application suites and site rebuild were skipped because no application, rich-page source or page manifest changed.

### Update — admitted entries and owner configuration completion batch (2026-11-06)

| Scope | Accepted result | Boundary |
|---|---|---|
| Coherent application candidate | [R72](../../docs/30-design/remedial/rc-16.0.0-integration-record.md#r72---admitted-entries-and-owner-configuration-completion-batch-2026-11-06) accepts74d7b3fc on current dev: full, browser, all40 enabled suites and final prcheck pass. Actual client/pooler/native7015 captures retain exact product/input-identity reuse. | Test-only settle expectations align with adopted nullable metadata; original failed full and earlier fixture/product failures remain. |
| Milestones | M1 and M2 promoted under their adopted cells, then M3 and M4 on their own cumulative evidence. M0 retained. | M1 resource bounds deferred C; M4 headless actual/source-pattern scope, no all-client claim. M5/M6 remain open; no dev merge/tag/default/production enablement. |
| Operational continuation | Representative original-tenant backup/upgrade native proof is recorded separately; restore-versus-clone decision adopted and linked. | Broader catalogue/durable backup/key destruction/cloning/native operational acceptance remains unmeasured. C application source is not joined to74d7. |
| Publication | Draft #8898 is OPEN at accepted `74d7b3fc`; body matches R72 and reader-clamp removal. Alignment promotions/map published at `586f8c83`. | Exact-head [application CI](https://github.com/nightscout/cgm-remote-monitor/actions/runs/42330725615), [CodeQL](https://github.com/nightscout/cgm-remote-monitor/actions/runs/42330725633) and [alignment CI](https://github.com/bewest/rag-nightscout-ecosystem-alignment/actions/runs/42331010678) pass. Fifteen app test/build jobs succeed; three release-image jobs skip. No dev merge or operator release. |

One evolving coordination handoff: `externals/work/HANDOFF-codex-completion-coordination-20261106.md` (local, untracked).

### Update — first-preview ownership scope and M5/M6 clarity (2026-11-06)

| Scope | Current direction | Acceptance boundary |
|---|---|---|
| Ownership | [Operator-assisted changes](decisions.md#preview-operator-assisted-ownership) suffice for the first preview; self-service co-owner/transfer follows later. | Current authority, tenant isolation, concurrent last-owner protection, audit and no automatic secret reveal remain required. Implementation acceptance is UNMEASURED. |
| Current reading path | [M5/M6 decision list](../../docs/30-design/tenancy/m5-m6-decision-list.md) separates settled policy, human questions and measurements; the roadmap supplies explicit acceptance families. | Older packets retain alternatives/evidence. No new milestone claim, application measurement or production/default enablement. |
| Execution | Existing M5 lane continues adopted bounded snapshot reconciliation and actual evaluator recovery; M6 synthetic preparation may proceed in parallel. | Native capability acceptance precedes coherent integration acceptance. Alarm/session/deletion policies remain explicit questions; operating limits follow agreed workloads and measurements. |

Validation: queue-check, docs-links, Markdown heading/explicit-anchor targets and whitespace checks pass. The isolated lane initially lacked external fixture paths; exposing the existing paths by symlink resolved that preflight failure. Application suites and site rebuild were skipped: no application, rich-page source or page manifest changed.

### Update — shared optional OIDC direction (2026-11-06)

| Scope | Adopted direction | Acceptance boundary |
|---|---|---|
| Human authentication | [Shared OIDC](decisions.md#shared-oidc-provider-renewal) for single/multitenant, provider-backed renewal first, equivalent optional support and separate authority adapters. Single-tenant enablement prefers `ENABLE=oidc`. | Current credentials/default behavior preserved. Identity alone grants neither root nor owner access. Login/renewal implementation and parity are UNMEASURED; logout/idle/outage/transport contracts remain explicit work. |
| Execution | Existing M5 runtime lane continues independently; owner/auth contracts and current decision list reflect the adopted direction. | No M5/M6 promotion, browser UI requirement or production/default enablement follows. No new application test result is asserted. |

Validation: queue-check, docs-links, Markdown fragment targets using site-compatible HTML/heading parsing, and whitespace checks pass. Application suites and site rebuild were skipped because only prose changed; the OIDC direction is not implementation acceptance.

Tenant-wide alarm suppression was also adopted during this review: [decision](decisions.md#tenant-wide-alarm-suppression). Preserve original expiry across restart and ignore active-window repeats. M5 can implement durable state under the existing D23/API boundary; native persisted/restart acceptance and historical retention remain separate, with no indefinite post-expiry deduplication claim.

### Update — durable notification retry responsibility (2026-11-06)

| Scope | Adopted direction | Acceptance boundary |
|---|---|---|
| Notification handoff | [Persist tenant-bound request intent before dispatch and retry the same identity](decisions.md#durable-notification-requests-and-retries), preserving normal suppression/dedup and single-tenant behavior. | Persisted intent, attempt, adapter acceptance and device delivery remain distinct. Ambiguous sends can repeat external notifications; clinical write deduplication is not external-effect deduplication. |
| Joined M5 testing | The roadmap/B7/current decision list require actual notification-consumer effects: ordinary alarm, snooze/repeat window, restart, ambiguous response, tenant/config/current-authority refusal, failed cycle and shutdown. | Component/synthetic-provider evidence motivates the policy; no joined/native/live-provider result or M5 promotion is asserted here. Uploader corpus acceptance is not notification acceptance. |
| Execution | Existing lifecycle, durable alarm and handoff capability owners continue under root source review and native grants. | No provider choice, exactly-once external guarantee, retry cadence/capacity or default/production enablement follows. |

Validation: queue-check, docs-links, changed Markdown fragment targets and whitespace checks pass. Application/site suites were skipped for this prose-only update. The joined consumer matrix must select actual browser alarm/ack, notification cache and controlled adapter contracts; mobile pattern replay and live provider/device delivery retain explicit limits.

### Update — first-preview deletion ceremony (2026-11-06)

| Scope | Adopted direction | Acceptance boundary |
|---|---|---|
| Deletion | [Explicit request, operator confirmation and cancellation before execution; no mandatory wait](decisions.md#preview-deletion-confirmation). Existing post-deletion key/artifact retention remains 30 days. | Current authority and verified artifact required; owner interface cannot execute deletion. Prove confirmation binding, cancellation/execution race, no effect after cancellation and interruption rollback. Native acceptance remains UNMEASURED. |
| Execution | M5 runtime integration/acceptance continues independently; C can prepare this lifecycle contract while waiting for the final M5 schema inventory. | No M5/M6 promotion or actual tenant deletion is performed by this decision update. Earlier 14-day proposal is not a preview requirement. |

Validation: queue-check, docs-links, changed Markdown fragment targets and whitespace checks pass. Application/site suites were skipped for this prose-only policy update. No actual deletion or lifecycle acceptance was run.


### Update — durable runtime and bounded SQL operations acceptance (2026-11-07)

| Scope | Recorded state | Acceptance and remaining boundary |
|---|---|---|
| Assembled application | Local `codex/m5-m6-joined-completion-20261107` at `f0fac99a2fccee259c9a76eba0123058bf288d96` | **Reproduced:** [R73](../../docs/30-design/remedial/rc-16.0.0-integration-record.md#r73-durable-runtime-operations-batch) accepts the full suite, entire default browser, entire enabled45-suite corpus and unchanged-source final upstream check. Exact figures, source comparisons, failed initial run and causal controls live in R73. No application source or test followed final prcheck. |
| M5 milestone | **Functional reference on one host promoted**; M0–M4 R72 scope retained | Durable current-state/evaluator recovery, current socket authority and DATA compatibility, original alarm suppression and actual same-identity notification consumers pass the joined criterion bar. The current reference polls consistent snapshots; no LISTEN latency, multi-node lease, every-transition history, live provider/device or all-client claim. |
| M6 operations | Bounded populated SQL recovery/upgrade/rollback and synthetic lifecycle accepted | Separate actual-source [SQL record](../../reports/tenancy/m6-ops-2026-11-07/postgres/README.md). M6 remains blocked on complete identity/owner/lifecycle/trust, same-ID tenant restore, recoverable/destroyed keys, operating envelope and final preview admission. Fresh deployment restoration does not establish a live shared allocator fence. |
| Gates and controls | Recorded PG, joined-role and SQL evidence gates wired to their broader parent cards | Existing app git objects and, for roles, lock-matched installed BSON dependencies are prerequisites. Gates do not start services. Each new gate rejects its authored physical corruption; wider explicit no-gate markers remain. No performance budget is inferred from functional passes. |
| Publication | **Published** to existing open draft #8898 at `f0fac99a2fccee259c9a76eba0123058bf288d96`; alignment acceptance published at `4440e4d723aa0182008bc97cd4f2052bb3bd5b87` | Direct maintainer approval covered both normal fast-forward pushes and the reviewed draft PR update. Remote CI and approved cleanup are recorded in the publication update below. This is not a dev merge, tag/operator release or production/default enablement. |
| Operator-visible effect | None enabled by this record | Existing single-tenant/Mongo behavior is preserved. Experimental multitenant roles and controlled consumers require explicit selection; no provider or real-data/identity admission is selected here. |

The first failed full attempt left19 known unreferenced synthetic test volumes.
After separate explicit maintainer approval, exact ownership/metadata/reference
revalidation and guarded removal verified all 19 absent with non-target resources
unchanged. Later verified acceptance runs had preserved them as baseline; the
original failed cleanup remains recorded. Local lane ownership and exact captures: `externals/work/HANDOFF-codex-completion-coordination-20261106.md`.

Validation: application acceptance is reproduced in R73. Queue validation and generation, queue-check, docs-links, the three selected recorded gates and their break-it controls pass. The combined next-generation render/source provenance, new local fragment targets and site-check pass: zero build warnings or unresolved links, with noindex on all 1,771 HTML pages. Initial sandbox queue/link checks stopped at Node child-Git EPERM; unchanged host reruns pass. The visualization lane ran no application tests or source changes after final prcheck.


### Update — R73 publication and approved cleanup (2026-11-07)

| Scope | Measured result | Remaining boundary |
|---|---|---|
| Publication | **Reproduced:** normal application fast-forward to `f0fac99a2fccee259c9a76eba0123058bf288d96` and alignment main to `4440e4d723aa0182008bc97cd4f2052bb3bd5b87`; exact remote hashes read back. **Read-derived:** [#8898](https://github.com/nightscout/cgm-remote-monitor/pull/8898) remains open/draft with base `dev`, and the reviewed title/body were updated. | No dev merge, tag, release or default/production enablement. |
| Remote CI | **Read-derived:** [application CI](https://github.com/nightscout/cgm-remote-monitor/actions/runs/42391789349) attempt2 completed successfully on exact f0: all 15 test/build jobs succeeded, including three browser engines and enabled corpus; three image-publication jobs skipped. [CodeQL](https://github.com/nightscout/cgm-remote-monitor/actions/runs/42391789369) and [alignment CI/site](https://github.com/bewest/rag-nightscout-ecosystem-alignment/actions/runs/42391800519) succeeded. | Attempt1 failed its maintained-MongoDB warning-count assertion and aggregate job. Attempt2 was observed externally under the shared GitHub actor; initiation is unestablished. Both attempts retained in the [snapshot](../../reports/tenancy/r73-publication-2026-11-07.json). No application patch or coordinator rerun. |
| Approved residual cleanup | **Reproduced:** all 19 explicitly approved synthetic volumes removed and absent; non-target volumes, containers and networks unchanged. Exact current metadata/original ownership matched and all 159 container mount sets were inspected. | Original failed e882 cleanup/acceptance captures remain false and immutable. Initial approved attempt stopped before deletion at `PREDELETE_BASELINE_CHANGED`; saved mount objects differed only by array order. Reviewed full-object canonical ordering passed metadata/reference/missing-target/mount-field controls and fresh equality before the successful second attempt. |
| M6 continuation | **Reproduced:** [R74](../../docs/30-design/remedial/rc-16.0.0-integration-record.md#r74-same-id-allocator-discriminator-and-remote-publication-readback) records seven actual SQL discriminator groups, intended clock/allocator reds, fresh restorations and exact owned-resource absence after a finite run on unchanged f0. | Same-ID identity-bearing restore remains `OPEN/UNSUPPORTED`; next prototype must preserve the shared allocator and cover every admitted writer/serving path. No global fence, B outage or IdP-outage policy adopted. Initial setup failure and later unrelated baseline restart retained. |

Local exact cleanup captures and current ownership are recorded in
`externals/work/HANDOFF-m5-publication-m6-continuation-20261107.md`.

Validation: queue-check, docs-links and whitespace checks pass for this completed record batch. Application acceptance suites and site rendering were skipped because application/rich-page sources did not change.


### Update — human sessions and simplest tenant restore proof (2026-11-07)

| Scope | Recorded result | Remaining boundary |
|---|---|---|
| Session policy | Maintainer adopted [existing access/current authority, provider-dependent renewal refusal and next-operation local logout](decisions.md#human-session-outage-and-logout). | Provider logout propagation/activity/transport/concurrency and human implementation remain open; no new refresh system. |
| Restore direction | [Allocator preservation first; conditional preview pause](decisions.md#allocator-preserving-restore-first). A pause's deadline cannot authorize unsafe reopening. | Prefer narrower A exclusion and equivalent logical representation before shared interruption; no deterministic outage budget adopted. |
| Bounded native proof | **Reproduced:** [allocator-preserving entries restore](../../reports/tenancy/allocator-preserving-restore-2026-11-07/README.md) on published f0 source preserves original A ordinals and exact prior B rows while B writes during restore. Interrupted A rolls back without undoing B. Physical floor/foreign-corruption controls fail as intended; fresh ordinary restoration passes. A separate fresh-ordinal logical proposal also preserves synthetic document values/relative order. | Controlled A quiescence only; product import guard unchanged. No complete lifecycle/fence, history/cursor/client, full catalogue, production, timing budget or M6 admission claim. |
| Architecture comparison | [Counters and restore options](../../docs/30-design/tenancy/counter-and-restore-options.md) distinguishes tenant-local transactional history from shared insertion identity and compares Kubernetes/etcd, CDC, logical restore and generation-switch options. | Source-derived analysis; no replacement allocator/cursor/schema adopted. |

Local ownership and exact private captures:
`externals/work/HANDOFF-session-restore-policy-20261107.md`.


### Update — tenant-local insertion simplification and consumed proof (2026-11-07)

| Scope | Recorded result | Next boundary / owner |
|---|---|---|
| Adopted contract | [Per-tenant/collection ordering only](decisions.md#tenant-local-insertion-semantics); private ordinal has no examined public identity consumer. Shared OIDC policy reconciles to its canonical main row, preserving original lane commits. | Preserve public IDs/documents/history and actual relative-order consumers. |
| Consumer impact | **Reproduced:** real profile reader changes only when relative duplicate-match order changes; renumbering with order intact is equivalent, explicit date-sorted entries unchanged. [R77](../../docs/30-design/remedial/rc-16.0.0-integration-record.md#r77---tenant-local-insertion-direction-and-consumed-native-proof-2026-11-07). | Released AndroidAPS v1 source path traced; no mobile binary/HTTP journey or all-client claim. |
| Tenant-local implementation | Local original-source branch `codex/tenant-local-insertion-20261107`, head07f8c27d. **Reproduced:** all five populated conversions preserve rows and remove sequences; A exact restore/rollback retains old B state while B commits; entries held-A lock does not block B, actual profile choice remains identical. [Proof](../../reports/tenancy/tenant-local-insertion-2026-11-07/README.md). | Coordinator joins runner-compatible migration, effective grants/readiness, counter lifecycle/backup inventory and A-scoped restore authority. No catalogue/default change or application push. |
| Residual fault boundary | **Reproduced:** deliberate direct own-counter corruption damages A ordering; independent oracle detects it, rollback restores all rows/counters and B stays exact. Inherited unsafe ordinal grant refuses. | Shared pool/DB and privileged all-tenant workers remain separate; no Byzantine-tolerance or numeric recovery/capacity budget claimed. |
| Verification | Root source tests4 pass, prior planner/lifecycle45 pass; native semantic controls/restorations and exact cleanup recorded under their own heads. Failed context fixture retained. | Full/browser/enabled-corpus/prcheck/whole-M6 acceptance waits for coherent source integration; no repeated leaf-wide campaign. |

Local evolving ownership and exact private captures:
`externals/work/HANDOFF-session-restore-policy-20261107.md`.

### Update — M6 operation lifetime uncertainty proof (2026-11-07)

| Scope | Measured result / claimed state | Next boundary |
|---|---|---|
| Local source | Unpublished prototype `6a245c09f652f020dc07f774aa0f2fe8e22e973f`; **reproduced: 95 focused source tests pass** | Optional core adapters are not a complete CLI/cohort fence. Root owns durable operator phase/claim/drain, exact schema/role/census and complete actual consumer wiring. Full/browser/enabled-corpus/final-prcheck remain deferred until coherent freeze. |
| Native uncertainty proof | [R75](../../docs/30-design/remedial/rc-16.0.0-integration-record.md#r75-operation-lifetime-early-proof-and-cache-parameter-mismatch) retains both failed runs and seven completed component groups, source-specific bypasses/restorations and a separate narrow cache diagnostic. | SQL lease absence does not establish callback completion: a real killed lease leaves pending operation count 1 while the body is open, and must refuse restoration. No orphan-clearance timeout or override policy adopted. |
| Refuted cache prediction | Same retained backend/OID, changed relfilenode and actual next 109 after ALTER CACHE 1; setval-only CACHE 8 remains actual next 2. | Current metadata alone is not a history/connection proof. No ALTER-based restore/global fence/B outage is selected. Supported allocator conditions, above-floor refusal and actual import/current-B fidelity remain unmeasured. |
| Programme state | M6 blocked; same-ID identity-bearing import remains OPEN/UNSUPPORTED | Published f0/R73/M5 one-host functional acceptance and completed publication/cleanup receipts remain unchanged. No real-data/identity/default/production admission. |
| Derived-output follow-up | [Decision-preparation packet](../../docs/30-design/tenancy/derived-output-boundary-2026-11-07.md) reviewed against unchanged current calculation bodies and linked to ARCH-DERIVED-FRAME | Characterization precedes a publication-service decision. No result materialization, transport or ownership architecture selected. |

Current owned worktrees, exact captures, original failure symptoms and next owner:
`externals/work/HANDOFF-m6-restore-fence-20261107.md`. No active native resources
or reusable grant remain after the recorded closure. Queue validation/generation, queue-check, docs-links and whitespace checks pass
for this coherent document/queue batch; no application-source readiness is inferred.


### Update — M6 admission continuation and adopted outage direction (2026-11-07)

| Scope | Result / claimed state | Next boundary |
|---|---|---|
| Original history integration | Original guidance and architecture commits remain in the evidence branch ancestry; original outage-policy commit `a5aef2b149d84f4a5ab65da814004b7067bfbf7f` merged normally. | Local and unpushed; retain original commits when integrating this branch. |
| Human access policy | Maintainer adopted the [existing-access outage policy](decisions.md#oidc-provider-outage-existing-access). | Policy adoption only; shared OIDC implementation and outage acceptance remain unmeasured. |
| Operation-window source | Original lane commits joined at local `f0590be387e077842dabee3ce4e1804719000138`: schema/role/ledger admission, backend-owned durable operations and fail-closed lifetime relation/function privilege census. **Reproduced: 177 affected source/protocol tests pass** on that joined head; catalog doubles do not establish native SQL, grants or RLS enforcement. Native [R75](../../docs/30-design/remedial/rc-16.0.0-integration-record.md#r75-operation-lifetime-early-proof-and-cache-parameter-mismatch) remains attributed to its earlier source. | Source admission is integrated; CLI/cohort selection, operator drain and native schema/privilege/allocator admission remain open. Same-ID identity-bearing import stays unsupported. |
| Derived-output characterization | **Reproduced:** the [bounded f0 characterization](../../reports/tenancy/derived-output-2026-11-07/README.md) passed ordinary, six intended negative controls/restorations and two reseeded campaigns. Root independently verified physical resource/child absence and exact inventory/selected baseline identity restoration. | Selected current evaluator/API properties agree under the tested contexts; realtime retains its raw frame contract. Checkpoint alone is an invalid result identity. Full role/browser/provider equivalence, capacity and a publication service remain unmeasured. Original suspended-grant preflight refusal remains preserved; explicit human messaging authorization enabled the renewed single-use run. |

Current exact branch heads, local packets, runtime ownership and next integration boundary:
`externals/work/HANDOFF-m6-restore-fence-20261107.md`. No operator-visible behavior,
default, deployment or milestone promotion changes in this update.

### Update — restore history compatibility and documentation backlog (2026-11-07)

| Scope | Result | Remaining boundary |
|---|---|---|
| Older same-ID snapshot | [Reproduced source protocol](../../reports/tenancy/restore-history-continuity-2026-11-07/README.md): restoring old clock/document metadata can skip history and retain stale client rows; floor preservation alone does not supply updates/deletions. Root replay agrees. | Maintainer selected [ordinary forward updates/deletions](decisions.md#restore-history-forward-correction). Implementation and acceptance continue; joined guard refuses full clock-bearing import before SQL until that capability is admitted. |
| Alignment documentation | MT-DOC-DEPLOY, MT-DOC-REALTIME and MT-DOC-SQL queued with separate acceptance criteria and linked from the tenancy reading guide. | Scenarios/diagrams, component communication and SQL/migration design documentation remain pending and UNMEASURED. |
| Joined implementation | Original migration/readiness/controller/lifecycle histories joined locally; focused checks continue before a coherent final campaign. | No new application push, PR acceptance, production/default enablement or M6 promotion claimed. |

### Update — coherent operation-window acceptance and tenant-local startup requirement (2026-11-07)

| Scope | Result / claimed state | Next boundary |
|---|---|---|
| Native operation-window capability | **Reproduced:** the [complete c23 native matrix](../../reports/tenancy/operation-window-acceptance-2026-11-07/c23-native-accepted/README.md) passed all 21 criteria on frozen local application `c23cf1f35d819738842041babc0aef2dbde96c21`. Actual separate roles, ordinary restore, forward history, B progress, rollback, participant restart refusal, COMMIT/invalidation acknowledgement loss and unresolved-orphan protections passed. Independent exact inventory/selected-metadata and physical closure passed. | The [earlier b029 17-criterion pass](../../reports/tenancy/operation-window-acceptance-2026-11-07/b029-native-accepted/README.md) remains separately attributed. No combined-attempt count, original failed-run blocker attribution, released operator feature or whole-M6 admission is claimed. |
| Statistics-cache evidence | **Reproduced:** the [PostgreSQL primitive counterfactual](../../reports/tenancy/operation-control-metadata-2026-11-07/activity-cache-counterfactual/README.md) distinguishes retired and new actors under a transaction-cached activity view. The original targeted same-client refresh commit joined b029 before the successful matrix. | The primitive/model proof does not establish the cause of an earlier CRM failure. [Incomplete native diagnostics](../../reports/tenancy/operation-window-acceptance-2026-11-07/28c-native-diagnostic/README.md) remain unchanged. |
| Restore observations | **Reproduced:** [existing-operation observations](../../reports/tenancy/operation-window-acceptance-2026-11-07/b029-native-accepted/README.md#existing-operation-timing-observations) record eight synthetic restore/fault samples and existing B HTTP operations without adding workload. | Private inspection and deliberate waits are included; these are not capacity, SLO or earliest-recovery measurements. |
| Shared-role restart coupling | **Reproduced:** the adopted [tenant-local startup admission](decisions.md#tenant-local-startup-admission) passed actual fresh API/realtime/evaluator restarts after rollback, DATA acknowledgement uncertainty and unresolved-orphan refusal in the [c23 matrix](../../reports/tenancy/operation-window-acceptance-2026-11-07/c23-native-accepted/README.md). Fresh B HTTP/realtime/evaluator progress preserved A's unavailable state and recovery protections. Unsafe-clock API startup refused before serving. | This closes the stated same-host shared-role restart criterion. Arbitrary direct SQL writers, multi-host topology, orphan clearance, production/default and real identity/data admission remain outside this proof. |
| Initial maintenance claim | **Reproduced:** the [controlled PostgreSQL experiment](../../reports/tenancy/operation-window-acceptance-2026-11-07/a1-bounded-mechanisms/README.md) reproduced registration-reference contention and validated a narrower claim while preserving advisory and competing-maintenance exclusion. The minimal original repair joined c23 and passed the complete controller matrix. | The earlier incomplete a1 run's specific blocker remains unidentified. No global pause, automatic retry, role/schema relaxation or arbitrary-writer exclusion follows from this result. |
| Default-browser acceptance | **Reproduced:** [all 684 browser tests](../../reports/tenancy/operation-window-acceptance-2026-11-07/c23-browser-accepted/README.md) passed on exact c23 with zero failures/pending, using the installed stock default browser and fresh private assets. Independent declared baseline/process/resource closure passed. The earlier [isolated proof](../../reports/tenancy/operation-window-acceptance-2026-11-07/a1-bounded-mechanisms/README.md) retains its narrower scope. | The initial incorrect nested phase was refused before services/browser execution and independently closed; its corrected command passed without a product change. Cold Compose UI/restore remains a separate capability. |
| Compose foreground | **Reproduced PASS:** the [exact ed2 image](../../reports/tenancy/operation-window-acceptance-2026-11-07/ed2-build-accepted.json) and [whole cold run](../../reports/tenancy/operation-window-acceptance-2026-11-07/ed2-cold-accepted.json) passed UI/main+alarm sockets and actual restore/public-ID preservation, B commit/row preservation, correction/deletion history, synthetic-client convergence and controller reactivation. Original cleanup and independent complete configuration/inventory/stable-endpoint/process closure passed; full endpoint equality false is retained. | The original bounded demo HTTP repair joined ed2 after [isolated exact-image Host measurement](../../reports/tenancy/operation-window-acceptance-2026-11-07/c23-compose/39f4-host-transport.json). [Earlier cold failures, exact recovery and component scopes](../../reports/tenancy/operation-window-acceptance-2026-11-07/c23-compose/README.md) remain unchanged. This closes the stated local synthetic cold capability; source is not released. |
| Actual pinned client compatibility | **Reproduced PASS:** [one complete ed2 cgmsim/oref0 campaign](../../reports/tenancy/operation-window-acceptance-2026-11-07/ed2-clients-accepted.json) passed every stored-outcome check with zero differing, unexplained or missing cells. Exact repository/runtime classifier closure was reviewed and pinned before granting. Main/post/independent phases and automatic after-reap terminal physical verification passed inside the same original cleanup deadline. | [Earlier metadata, clock and classifier-closure stops](../../reports/tenancy/operation-window-acceptance-2026-11-07/39f4-clients/README.md) retain their actual attribution and limits. The new [mount-order measurement](../../reports/tenancy/operation-window-acceptance-2026-11-07/m4-mount-order-measured-2026-11-08.json) supports the prospective instrument correction without identifying the original missing field evidence. Scope is the two pinned clients on synthetic data; broader client/milestone admission remains separate. |
| Broad acceptance | **Reproduced PASS:** the [final ed2 seven-tier full](../../reports/tenancy/operation-window-acceptance-2026-11-07/ed2-full-accepted/README.md) passed 7806 tests/174 pending/zero failures in one complete run. Actual third-step exact inventory/selected-metadata/observed-birth closure and automatic after-CLI-reap terminal retained-birth closure passed inside the same original cleanup deadline. [Earlier c23 full/browser and 39 focused/corpus evidence](../../reports/tenancy/operation-window-acceptance-2026-11-07/README.md) retains its exact attribution. | Cold and pinned-client acceptance are also closed on ed2. The [source-owner last prcheck](../../reports/tenancy/operation-window-acceptance-2026-11-07/ed2-final-prcheck.json) passed after this full handback, with fresh official/dev and unchanged clean source. Earlier failed campaigns remain preserved. The accepted ed2 source is now on existing [draft PR8898](https://github.com/nightscout/cgm-remote-monitor/pull/8898), with updated acceptance metadata and independent readback. Original alignment records/guides are published at a16e3dbf; [publication and successful alignment CI](../../reports/tenancy/operation-window-acceptance-2026-11-07/published-ed2-2026-11-08.json) are measured. No dev merge, release, default/production enablement or whole-M6 admission. |
| Structural documentation | The deployment, realtime and SQL guides are complete and published on alignment main. **Reproduced:** their declared `node tools/queue/gates/doc-links.js` static gate passed. [Deployment and rig guide](../../docs/30-design/tenancy/deployment-and-rig-testing.md), [evaluator/realtime guide](../../docs/30-design/tenancy/evaluator-realtime-communication.md), [SQL/migration guide](../../docs/30-design/tenancy/sql-and-migration-architecture.md). | Structural documentation closure only. Source citations retain their inspected attribution; runtime, capacity and M6 acceptance remain separately measured. |

The completed acceptance lane retains immutable captures, source attribution and
physical closure in `externals/work/HANDOFF-m6-acceptance-continuation-20261107.md`
(local). Its work is transferred and the chat archived after helper/resource closure.
Programme coordination and the next ownership boundary are in
`externals/work/HANDOFF-multitenant-coordination-20261107.md` (local);
the original lane commits are preserved by normal integration.

### Update, 2026-11-07 — optional shared OIDC source lane, next batch

| Capability | Measured state | Remaining boundary / owner |
|---|---|---|
| Shared optional human login and sessions (`MT-IDENTITY-PLAN`) | **Fixed on local original branch, frozen for bounded acceptance; not merged or released.** `codex/shared-oidc-sessions-20261107` at `eadf41f889e48ab6762724e62d4e6c85d50fb654` implements common OIDC/session flow, adopted asymmetric access with current accepted keys, distinct Mongo aggregate/PostgreSQL adapters and consumed browser/HTTP/stream paths. **Reproduced:** 194 explicit-file source checks pass; independent crypto/config source audit is clear within its scope. [Capability evidence and limits](../../reports/tenancy/shared-oidc-sessions-2026-11-07/README.md). Earlier reserved HTTPS18 is historical nonconforming opaque-prototype transport evidence, not signed-policy acceptance. | Actual signed native DB/Vault/HTTPS/browser acceptance remains **UNMEASURED**, pending the sole lead's finite owned reservation. The individual owner/OIDC chats are archived and have relinquished ownership. Sole combined source owner `01a1b969-6e93-7893-8f22-da9fda5ac478` is **READY/HOLD** at independently read clean local head `96fd87ff578b29a3bc21c96bbc7c5ec09d84a785`, after normally joining accepted ed2 and repairing its affected historical test model with semantic controls. Fresh next-capability lead `01a1ba7c-ceba-7bc1-8508-912d098ab7fe` owns readiness review and future finite native admission; the completed prior acceptance lead is archived. No runtime grant exists. Remaining native owner-consumer, credential replay, authority-race and browser/session families are explicit capability work for parallel lanes. The original EADF source and crypto measurements above retain their actual attribution; combined native acceptance remains unmeasured. Current Compose candidate unchanged; no M6 or production admission. Evolving combined handoff: `externals/work/HANDOFF-owner-oidc-combined-20261107.md` (local). |


### Update — alignment decision readiness and deployment grooming (2026-11-08)

| Scope | Recorded result | Remaining boundary |
|---|---|---|
| Current reading path and map | **Read-derived reconciliation:** dashboard, roadmap, decision index and platform map now link the published ed2 reference and preserve c23 native/browser and 39f4 corpus attribution. Deployment guides distinguish tenancy, storage, computation, processes and host placement, with shared fault domains and evidence-to-decision tables. | M0–M5 scope retained; M6 blocked. Functional reference acceptance can inform bounded design choices; production trust, workloads/limits and topology-specific recovery still require acceptance. Local OIDC/owner source has no new native acceptance. |
| Retention | Full batching dispatch/execution journal retained in the [tenancy archive](../../docs/archive/tenancy/README.md); active successor keeps current coordination and acceptance boundaries. Platform's October execution table remains retrievable at its pinned public revision. | No captured application measurements rewritten or combined; current documents link each fact's canonical home. |
| Verification | **Reproduced:** archive preservation comparison, queue-check/docs-links, dead-link and stale-dashboard controls with restored success; rendered map/site-check and targeted Mermaid parsing pass. [Grooming record](../../reports/tenancy/alignment-grooming-2026-11-08.json) records exact source, checks and evidence limits. | Fresh queue-status reports existing failures and skipped/UNMEASURED gates; documentation checks do not make them green. No application campaign, policy adoption, release or default/production change. |

Local lane handoff: `externals/work/HANDOFF-alignment-groom-20261108.md`.


### Update — production dependency and operational prior-art map (2026-11-08)

| Scope | Recorded result | Remaining boundary |
|---|---|---|
| Preview-to-production path | **Read-derived:** the [production critical path](../../docs/30-design/tenancy/production-critical-path.md) links current milestone/authority/trust requirements to observable closure, dependency order and conditional HA deferrals. The fixed-cohort first production scope is a recommendation for review; M6, release and per-deployment admission remain distinct. | No topology/SLO choice, numeric limit, new policy, milestone promotion or production admission adopted. Existing source and acceptance owners retain their work. |
| Prior art | Tracked local HEAD inspection of node-multienv, roles gateway and gateway-www identifies reusable provisioning/reconcile states, routing/authority decomposition and consent/invitation journeys. Exact source pins and code links live in the guide. No private environment, customer data or operational logs were used; the pre-existing WWW invitations edit was excluded. | Source reading supplies design input, not runtime or security acceptance. Existing provider experience still needs aggregate workloads, incident shapes and recovery/support objectives before it supplies acceptance thresholds. |
| Evidence | Existing ed2/c23/39f4 acceptance keeps its executed source attribution; current PR metadata was independently re-read as the same open draft. Coherent documentation review found no material sequencing or scope mismatch. | No application/native/full/browser/client campaign was run for this analysis. Documentation/link/diagram validation is separate from application readiness. |

Local lane handoff: `externals/work/HANDOFF-production-path-20261108.md`.


### Update — portable topology and public-name policy clarification (2026-11-08)

| Scope | Recorded result | Remaining boundary |
|---|---|---|
| Deployment and public access target | Maintainer clarified ordinary Kubernetes portability, logical ingress, public/private name lifetimes, explicit OIDC/anonymous/group-policy controls, potential schedule semantics and load-herd measurement. The [public requirements and proposed bindings](../../docs/30-design/tenancy/deployment-bindings-and-public-names.md) separate packaging from distributed application ownership. | One-Pod/private-IPC composition is a candidate to measure, not an adopted resource layout. Public-name/group/schedule contracts need explicit semantics and accepted feature scope. No cluster, new provider, policy engine, application role or milestone was admitted. |
| Evidence | **Read-derived:** existing fixed-cohort source and official Kubernetes resource semantics inform the design and equivalence tests. Public requirements are recorded in [release decisions](decisions.md#deployment-portability-and-public-name-requirements-2026-11-08). | No application or cluster campaign was run. Operating limits and mitigations require workload-based measurement. |

### Update — PostgreSQL ownership and component API boundaries (2026-11-08)

| Scope | Recorded result | Remaining boundary |
|---|---|---|
| Supported writers | Maintainer adopted [exclusive application ownership of PostgreSQL](decisions.md#exclusive-application-postgres-ownership). The supported roster includes internal components and controlled maintenance tools; external direct writers have undefined behavior. Current architecture and production guidance link that contract. | Supported internal participants retain authorization, tenant isolation, canonical write and lifecycle obligations. No new application behavior, privilege or runtime acceptance. |
| Database design | **Read-derived:** the [SQL/database page](../../docs/30-design/tenancy/sql-and-migration-architecture.md#component-ownership-and-internal-application-apis) adds a component ownership table and command-versus-storage diagram. Cross-owner commands use application interfaces; admitted reads and owned transactional persistence retain direct storage access. | Existing socket/notification/control protocols keep their evidence attribution. Further internal APIs require their own implementation and acceptance. |
| Kubernetes smell test | **Read-derived:** request-scoped API and static serving are replaceable-replica candidates; realtime, evaluator/notification and lifecycle roles retain connection, producer or maintenance ownership. The database guide links the existing transport/replica assessment. | Kubernetes execution/autoscaling and performance remain UNMEASURED. Every serving replica must participate in restore; generic load balancing does not implement complete-cohort control or browser fanout. |
| Documentation verification | **Reproduced:** queue-check, docs-links and the focused MT-DOC-SQL queue-status gate pass; all four SQL-page Mermaid blocks parse with the pinned parser after correcting existing sequence-label semicolons. | Broad queue-status exits with FAIL, skipped and UNMEASURED items in the isolated worktree/sandbox; it is not a programme acceptance verdict. No application campaign, rich-site build or cluster execution was run. |

Local lane handoff: `externals/work/HANDOFF-postgres-ownership-20261108.md`.


### Update — API scaling and endpoint mechanism assessment (2026-11-08)

| Scope | Recorded finding | Remaining boundary |
|---|---|---|
| Request API vs runtime ownership | **Read-derived:** the current cohort contract explicitly admits declared API replicas; fresh API request frames and external authority do not require one API instance. The [transport/scaling assessment](../../docs/30-design/tenancy/deployment-bindings-and-public-names.md#configurable-transports-and-independently-scaled-api) separates API membership/invalidation from evaluator producer and realtime fanout ownership. | Fixed-roster API concurrency, all-instance invalidation and replacement need their actual acceptance. Dynamic membership is separate. No replica campaign or scaling admission claimed. |
| Endpoint configuration | Current private IPC is HTTP/JSON over configured Unix sockets. A typed Unix/network endpoint adapter can preserve payload semantics, with remote service trust and transport-parity acceptance. Source inspection of node-multienv shows local socket-listener and remote-URL mechanisms, not uniformly interchangeable clients. | Proposed endpoint variable/schema and network transport are not implemented or selected by this assessment. Service-level API routing cannot replace per-instance maintenance endpoints or all-viewer realtime delivery. |

### Update — published database visual review and Mermaid publication gate (2026-11-08)

| Scope | Recorded result | Remaining boundary |
|---|---|---|
| Database visual review | **Read-derived:** the [visual database and component ownership page](../../site/pages/multitenant-database-design.html) renders the canonical SQL guide's storage ownership matrix, table-family grid and diagrams. Commands, lifecycle control, logical bindings and declared foreign keys have separate views; existing upgrade/restore sequences retain their temporal semantics. Home and tenancy reading paths link the review. | The living page records its SQL source revision and renders static SVG with the pinned Mermaid runtime. It adds no policy, application implementation or runtime admission. |
| Mermaid correctness | **Reproduced:** original evaluator/realtime sequence-label semicolons cause pinned parser failures; corrected labels parse. Publication now checks the actual staged Markdown before committing a site build, respecting exclusions and refusing a missing/empty source tree. | Syntax checks do not establish readability. The database page was visually inspected; the separately authored topology grids retain their own record below. No blanket diagram conversion or invented lifecycle state model. |
| Verification | **Reproduced:** joined tracked and staged Mermaid parser checks, site-check, queue-check and docs-links pass. Browser review covers desktop ownership/command views, narrow-screen reflow, static SVG presence and expandable restore details; a discovered SVG-label CSS collision was corrected. | [Verification record](../../reports/tenancy/database-site-review-2026-11-08.json) attributes the checked inputs and limits. Publication/readback is recorded in the local handoff; no application/native/cluster campaign was run. |

Local lane handoff: `externals/work/HANDOFF-database-site-20261108.md`.


### Update — queued endpoint/API capabilities and grid topology (2026-11-08)

| Scope | Recorded result | Remaining boundary |
|---|---|---|
| Implementation queue | Added MT-ENDPOINT-TRANSPORT and dependent MT-API-FIXED-ROSTER as not-started source capabilities. [Plan](../../docs/30-design/tenancy/selectable-endpoints-and-api-scaling-plan.md) defines implementation joins, acceptance oracles, meaningful planned controls and coherent final verification. | Runtime instruments/implementation are not yet authored: queue gates explicitly say no-gate/UNMEASURED, not green documentation substitutes. No application branch created or runtime dispatched. |
| Topology and cohesion | [Aligned zone diagrams](../../docs/30-design/tenancy/runtime-topology.md) distinguish accepted one-host source from proposed network/API target, service vs instance destinations, singleton evaluator and backing-store authority. | Platform lifecycle/discovery/identity may be reused; no custom membership product or evaluator scheduler. Kubernetes proof, cluster bindings and Jsonnet deferred. Predictable bounded work may remain singleton where headroom/restart needs permit; evaluator logical ownership remains separate from resource sizing. No new runtime/topology/production acceptance. |
| Planning validation | Queue schema/generated views, queue-check, docs-links, diagram parsing/SVG-PNG validation and site-check pass; the new-guide dead-link control failed as intended and restored green. Focused status reports both new runtime capabilities UNMEASURED. These checks apply only to documentation/figures. | Focused queue-vacuity encounters duplicate controls in the unchanged pre-existing registry before reporting zero distinct gates for these no-gate items. No new runnable gate or control was added; no runtime vacuity acceptance claimed. |
| Joined documentation boundary | The PostgreSQL/component-ownership update joined by ordinary merge, retaining original history. Plan and grid guide link the canonical collective-ownership and cross-component command boundaries. | Scoped internal persistence/reads remain supported; no generic SQL API or stronger external-writer fence is introduced. |


### Update — REST cohesion, recovery participation and activity-policy reconciliation (2026-11-08)

| Scope | Reconciled record | Remaining boundary |
|---|---|---|
| Component placement | **Read-derived:** [REST/worker map](../../docs/30-design/tenancy/runtime-topology.md#logical-rest-cohesion-and-worker-placement) distinguishes logical modules, HTTP audiences/listeners and deployment processes. Owner REST may co-locate with API under the existing contract; vcpool/evaluator are background roles, and the inspected restore tool executes privately outside ordinary API serving. Proposed grid labels no longer imply every REST module requires a separate deployment. | No process merge, new REST operation, service decomposition or application behavior selected by this documentation reconciliation. Accepted one-host figure keeps its actual composition. |
| Tenant admission | [Activity/admission review](../../docs/30-design/tenancy/tenant-admission-and-activity.md) separates proposed operator resource policy from claim-bound maintenance safety, observed health and current authority. APIs honor common admission/drain/invalidation without each owning restore orchestration. | The user raised operator inactivity as a design question; no inactive/pause/suspend schema, capability default or transition authority is adopted. Existing pause/suspend definitions stand. Restore completion must be considered separately from operator eligibility in the proposed acceptance cases. |
| Queue and decision index | Reconciled current TEN-RESOLVE and T30-TENANT-ADMIN gaps against later bounded acceptance; retained native gate pins and historical scope. MT-API-FIXED-ROSTER links generic admission obligations; the decision index now exposes the unresolved activity-policy topic. | Claimed states unchanged; runtime/activity implementation remains unmeasured. No new parent prerequisite, milestone promotion, release or production admission. |
| Deployment/map assumptions | Linked the deployment guide and platform map to the selected endpoint/API scaling plan and adopted application database-ownership contract. | Fixed-roster API scaling is separate from evaluator replication; stronger raw-writer fencing is required only for an additional unsupported writer model. Historical captures unchanged. |


### Update — unified REST component and separate replica placement (2026-11-08)

| Scope | Recorded change | Boundary |
|---|---|---|
| REST component | [Current component contract](../../docs/30-design/tenancy/tenant-admission-and-activity.md#one-logical-api-does-not-require-one-listener-or-process) and D5 clarify one stateless REST APIs component containing version-specific v1/v2/v3 adapters. Endpoint/scaling/binding plans retain equivalent configured routes across replicas. | Read-derived source composition supports the architecture; no runtime or route-acceptance promotion. Transient request/pool/cache state still requires maintenance participation. |
| Figures and historical guidance | Topology plates show one REST component and separately named replicas A/B. Accepted one-host plate retains the measured process composition. Older interface/deployable snapshots link the current contract; a separate v1-role option is historical, not the selected direction. | Existing version-specific compatibility, owner/DATA audiences, private orchestration and worker ownership remain. Captured evidence unchanged. |
| Coordination | Database visual-review source, SQL/component diagrams, platform map references, generated pages/source pins and current-guides-first navigation join by ordinary merge with original source/render history. Both lanes use the same logical REST component boundary. | Queue IDs/states, source/instrument attribution, existing route coverage and unmeasured scaling/cluster boundaries remain. |

Local lane handoffs: `externals/work/HANDOFF-unified-rest-component-20261108.md` and `externals/work/HANDOFF-database-clarifications-20261108.md`.


### Update — plan restructuring, deploy repository and disposable harness (2026-11-09)

| Scope | Recorded result | Remaining boundary |
|---|---|---|
| PR #8898 state | **Read from GitHub 2026-11-09:** head `ed2ced00`, open draft, mergeable, updated 2026-11-08. Checks: 16 success, 3 skipped, 1 failure (CodeQL: one new high alert on the private IPC dispatch in `lib/server/realtime/ipc.js`, a bounded own-property lookup; a second critical alert on the token lookup in `lib/authorization/storage.js` is on code byte-identical to `official/dev` and is not this PR's). | `MT-M6A-JOIN` clears the new alert; the pre-existing one is a dev question. NEEDS-A-HUMAN had quoted the earlier `83582e87` all-green head and is corrected. |
| Decisions | Four rows in [decisions.md](decisions.md#plan-restructuring-and-process-simplification-2026-11-09): deployment tree lives in `nightscout-deploy`; Vault via Vault Agent sidecar plus a core `tokenFile` read; native acceptance through a disposable harness, grant/reservation ceremony retired; M6 split into M6a–M6d and M7, umbrella queue items closed as superseded. | Read-derived planning; no application behaviour changed. |
| Queue and dashboard | 13 items closed as superseded (ST-PG, MT-CONFIG-MIN, MT-SECRETS-CONTRACT, MT-RUNTIME-PLAN, T30-WIRING, T30-TENANT-ADMIN, MT-IDENTITY-PLAN, TEN-RESOLVE, MIG-RUNNER, T30-RESEARCH, T30-AUTH, T30-SCHEMA-CONFIG, T32-REM), each with its gates and evidence retained and a note naming the successor. 12 capability items added, one gate each: MT-OIDC-NATIVE, MT-M6A-JOIN (M6a); MT-OWNERSHIP-OPS, MT-KEY-RETENTION (M6b); MT-VAULT-TOKEN-FILE, DEPLOY-VAULT-AGENT, DEPLOY-IDP-PROFILE, DEPLOY-TRUST-PROBES (M6c); MT-CONNECTOR-SYNC (M6d); MT-ENVELOPE, MT-ANDROID-LAB, DEPLOY-K8S-BINDING (M7). Dashboard generator validates the new milestone set. | New gates are `no-gate`/UNMEASURED until their instruments land; the first runnable one is the OIDC recorded-evidence gate. ARCH-SEAM-*, ST-VIEWS-PROFILE and ARCH-DERIVED-FRAME are untouched: they are bounded slices with their own owners. |
| Verification | `make queue-validate && make queue`, `make queue-check`, `make docs-links` as reported in the final session message. | Documentation checks only. |


### Update — owner/OIDC nine-stage native matrix run through the disposable harness (2026-11-09)

| Scope | Recorded result | Remaining boundary |
|---|---|---|
| MT-OIDC-NATIVE | **Reproduced:** harness branch `codex/oidc-native-harness-20261109` head `3b09131e` (= candidate `c0a67b69` + Vault probe status fix `2151cc5b` + harness `tests/native/oidc-matrix/`). All nine stages PASS on postgres 16.15, mongo 7.0.43, Vault 2.2.1 (versions read from containers), families complete, zero leftover schemas/collections/mounts after every stage. Three authored mutants executed red then restored green (single eight-hour exchange, browser CSRF, consumer current-authority bypass). Gate `tools/queue/gates/oidc-native-recorded.js` passes on the record (13 checked, 0 failing) and fails on the missing-stage fixture. [Report](../../reports/tenancy/oidc-native-2026-11-09/README.md). | Branch is local. Full/default-browser/enabled-corpus/prcheck on this branch and the join to #8898 are `MT-M6A-JOIN`. Real identity-provider interop is synthetic only. 17 of 20 authored mutants not yet executed (`run.sh --control`). |
| Grant ceremony retired | The driver's reservation flag, grant JSON, lead chat ID, attestation hashes, 60-second freshness and 726-file source pin are removed; the harness records `git rev-parse HEAD`, requires a clean tree, starts containers by digest with a unique project name and removes them in a trap. | Prep-directory offline test suites that tested the retired grant interface were not carried. |
| Findings for the source owner | (1) Vault 2.x returns 200 with metadata on Transit key creation; the probe expected 204. Test-instrument fix on the candidate branch, review requested. (2) The retired driver never passed the `consume` callback required by the vault probe's sixth check, so the prepared matrix could not have gone green as written. (3) The settings-reader fixture lacked SELECT on the migration ledger (fixture fix in the harness). | No application code changed; no oracle failed on candidate behaviour. |

Local lane handoff: `externals/work/HANDOFF-oidc-native-harness-20261109.md`.


### Update — M6c Vault Agent sidecar and core tokenFile (2026-11-09)

| Scope | Recorded result | Remaining boundary |
|---|---|---|
| MT-VAULT-TOKEN-FILE | **Reproduced:** `codex/vault-token-file-20261109` head `0c547958` on ed2: `tenant.vault` takes exactly one of `tokenEnv` or `tokenFile`; sink read per call, trimmed, bounded; any failure is SECRETS_PROVIDER_UNAVAILABLE with no env fallback. Unit family 5 passing; ablations load-time cache 2 failing, env fallback 1 failing, restored 5; `test:affected` on mongo:7 unit 191 / harness 27 / integration 24 passing, 0 failing. | Only one `getToken` site exists at ed2; the three on the owner/OIDC branch get the same shape at `MT-M6A-JOIN`. Branch local. |
| DEPLOY-VAULT-AGENT | **Reproduced:** nightscout-deploy `cda38265`, overlay `bindings/compose/vault-agent/` (Agent at the imported Vault digest, AppRole auto-auth, sink `/run/ns-vault/token` read-only into the four roles, bootstrap step, wrapper). Compose smoke on port 18090 with a 2-minute TTL: renewal observed twice past TTL; Agent stopped with env tokens still present gives 503 on both tenants (fails closed, no fallback); secret-id reissue recovers in 4 s; imported restore demo passes through the overlay. Imported tree byte-identical to ed2. [Report](../../reports/tenancy/vault-agent-2026-11-09/README.md). | Finding: without `renew-self` the Agent silently re-authenticates each TTL instead of renewing; the role now grants `renew-self` and `lookup-self`. UNMEASURED: re-auth after `token_max_ttl`, seal/unseal, Kubernetes auth method. Open for the maintainer: one AppRole for the cohort vs one Agent per tenant ([decision index](../../docs/30-design/tenancy/m5-m6-decision-list.md#human-policy-review)). |

Local lane handoff: `externals/work/HANDOFF-vault-agent-20261109.md`.


### Update — M6a joined candidate for draft #8898 (2026-11-09)

| Scope | Recorded result | Remaining boundary |
|---|---|---|
| MT-M6A-JOIN | **Reproduced:** `codex/m6a-join-20261109` head `74036ba6`, a fast-forward of `workspace/multitenant-20261102` from `ed2ced00` (40 commits, 143 files). Joins the OIDC harness and tokenFile branches, then repairs every regression the OIDC candidate brought: D23 socket delegation via a `beforeWrite` hook (`521c35e0`); `human_session` family admitted to the lifecycle catalogue following `access` (`cc1789bd`); two date-pinned test time bombs (`463e2806`, `2c289a0c`); OIDC browser discovery opt-in by a page-server hint (`861a5d11`); owner capability test expectations and grants (`74036ba6`). Each repair has a red control. Final: OIDC matrix 9/9 with 3/3 controls; `test:all` 0 failing; browser 686/0; multitenant corpus 537/1 pending/0 (ed2: 537/1/0); write-intent and write-boundary clean; prcheck exit 0 against official/dev `4a482627`. [Report](../../reports/tenancy/m6a-join-2026-11-09/README.md). | Push awaits two maintainer decisions (opt-in browser discovery; permitted owner DELETE). UNMEASURED: CodeQL on the IPC Map change, Compose runtime with the new grants, end-to-end single-process OIDC with a real provider. `deploy/multitenant/config.js` now diverges from the nightscout-deploy mirror (owner_writer grants). |



### Update — #8898 pushed at the M6a joined candidate (2026-11-09)

| Scope | Recorded result | Remaining boundary |
|---|---|---|
| MT-M6A-JOIN | **Pushed by the maintainer:** `workspace/multitenant-20261102` = `74036ba6` (read from `official` after the push); PR #8898 still draft. Decisions [oidc-browser-discovery-opt-in](decisions.md#oidc-browser-discovery-opt-in) and [owner-may-revoke-subjects](decisions.md#owner-may-revoke-subjects) taken before the push. | CI read once: tests (four Node/MongoDB pairs), no-database, npm 12, Docker amd64/arm64 green; browser, maintained-MongoDB and multitenant-corpus jobs still running at that read. |
| CodeQL on `74036ba6` | **Measured (failed):** three open alerts on the PR merge ref. 155: dynamic method call on the IPC dispatch (the Map change closed 153 and the same call was flagged again). 150: a token from query or body reaches the subject lookup, where a non-string value throws; the code matches `official/dev`, but the alert appears only on this PR. 154: rate limiting on a native test fixture. | Follow-up `0fc5abf9` (local, unpushed): the subject lookup returns no subject for a non-string token (new test red without the guard, `accessToken.split is not a function`, green with it); the IPC dispatch requires a function. Focused suites green, prcheck OK. 154 follows the dismissal precedent for test fixtures (alerts 141–149, 152). Effect on CodeQL is UNMEASURED until CI runs. |
| Single-site OIDC direction | Recorded as [single-site-oidc-identity-list](decisions.md#single-site-oidc-identity-list); queued as `MT-OIDC-SINGLE-PROVISION`. | Not started. |


### Update — shared internal service contracts and private listeners (2026-11-09)

| Scope | Recorded result | Remaining boundary |
|---|---|---|
| Internal service API | **Fixed on local branch** `codex/internal-service-api-20261109`, `dc795bd1515f11808a8d0732f2be9925cb2ffcd1`, on the `0fc5abf9` candidate. Shared transport, three service contracts with request/response schemas, named clients and application documentation. Private contracts retain separate listeners from public routers. UDS remains supported; HTTP permits explicitly configured DNS/link-local/private origins and listener addresses with deployment-owned network trust. No bearer protocol. | Source integration owner joins the original lane history into the existing #8898 candidate under `MT-M6A-JOIN`. Communicating processes require coordinated upgrade for service/version headers. No public route/default enablement, publication, dev merge or release. |
| Focused evidence | **Reproduced:** 204 passing / 5 pending, no failures; existing UDS custody/replacement fixture passes; changed-code lint has no errors; tier inventory passes. Persisted schema, service-ownership and public-listener ablations detect their intended semantic failures, restored checks pass. [Evidence and commands](../../reports/tenancy/internal-service-api-2026-11-09/README.md). | Full joined database/browser/enabled-corpus/native/client acceptance and remote CodeQL remain UNMEASURED for this change. Local HTTP behavior does not establish Kubernetes or multi-host lifecycle admission. Existing authorization, tenant operation-window and restore identity gates remain. |

Local lane detail: `externals/work/HANDOFF-internal-service-api-2026-11-09.md`.


### Update — joined candidate dc795bd1 for #8898: CodeQL guards and internal service API (2026-11-10)

| Scope | Recorded result | Remaining boundary |
|---|---|---|
| MT-M6A-JOIN | **Reproduced** on `codex/m6a-join-20261109` head `dc795bd1` (= `74036ba6` + `0fc5abf9` CodeQL guards + `dc795bd1` [internal service contracts](decisions.md#internal-service-contracts)): unit 3072, dom 205, dependency 368/2 pending, core 319, harness 99, integration 3618/534 pending, stress 18, browser 686, multitenant corpus 537/1 pending, all 0 failing; OIDC matrix 9/9 with 3/3 controls and gate 13 checked/0 failing; write-intent and write-boundary clean; ESLint 0 errors; prcheck OK. New break-it: skipping response-schema validation in the listener returns 200 instead of 503, and in the named client gives "Missing expected rejection."; both green on restore. [Evidence](../../reports/tenancy/m6a-join-2026-11-09/dc795bd1-acceptance/) | Push of `dc795bd1` to `workspace/multitenant-20261102` is the maintainer's. UNMEASURED: CodeQL on the new head; internal HTTP endpoints beyond loopback (Compose, Kubernetes, multi-host); a mixed-version process pair (peers refuse missing service/version headers, so upgrade is coordinated). |


### Update — #8898 at dc795bd1; M6b, single-site OIDC provisioning, listener composition and connector sync lanes (2026-11-10)

| Scope | Recorded result | Remaining boundary |
|---|---|---|
| MT-M6A-JOIN | **Pushed by the maintainer:** `workspace/multitenant-20261102` = `dc795bd1` (read from `official`). Every CI job on that head is green, CodeQL included: alert 155 fixed, 154 dismissed (used in tests). | Alert 150 remains open at `lib/authorization/storage.js:395` (the `accessToken.length` loop); fix `7b30a6f2` iterates a typed candidate list and adds a keyed-enclave test that a valid token inside an array matches (red with the array path removed, `TypeError: Cannot read properties of null (reading 'name')`; unit tier 3072/0). Joins under MT-M6B-JOIN. |
| MT-VAULT-TOKEN-FILE | `0c547958` is an ancestor of the pushed `dc795bd1`; state moved to in-flight-upstream. | Ships with the #8898 bundle. |
| MT-CONNECTOR-SYNC | **Reproduced (Docker lab):** nightscout-connect `04102f9d`, unchanged, pulled tenant entries with a read-only reader credential; destination equals the tenant store read directly (30, 35, 38); oracle ablations red then green; credential deletion and post-issue role removal both refuse with zero new rows; second tenant untouched; 16 checks, 0 failing. [Evidence](../../reports/tenancy/connector-sync-2026-11-10/README.md) | UNMEASURED: other collections, long-running cadence, token refresh, owner-surface revocation, real ingress, the lock-pinned connector commit `b394411a`. |
| MT-ENDPOINT-TRANSPORT (listener composition) | **Reproduced in lane** `d69b873a` on `692bd507`: several contracts on one listener from a fixed route table; duplicate route/service refused before bind; foreign co-resident service 503; per-operation media type, size and deadline that only tighten; lifecycle status/invalidation callable for a suspended tenant while its application calls refuse and the other tenant proceeds. Affected tier 4240/164 pending/0; five ablations red then green. Separated processes over a Docker Compose network (HTTP and a shared UDS) preserved revocation, suspension, per-participant invalidation and drain; blanket-window control exits 1. No internal path, header or schema change. [Evidence](../../reports/tenancy/listener-composition-2026-11-10/README.md) | The Compose run used production transport and lifecycle handlers with synthetic authority; real api/realtime/evaluator roles over Compose need in-tree provisioning (UNMEASURED). Production wiring of a shared component listener needs a configuration shape (maintainer). Finding: on shutdown `close()` drops in-flight connections before handlers finish (consistent with the no-retry contract). |
| MT-KEY-RETENTION | **Reproduced in lane** `ed46cc43`: deletion refuses an export missing a key reference; 30-day retention record (lifecycle migration 0005); restore inside the window succeeds, after the window or after destroy refuses; operator destroy with exact intent, Vault key confirmed gone, other tenant's keys kept. Unit 31, native 6, four ablations red then green. Also repaired: on `dc795bd1` the ceremony ledger check admitted two of six lifecycle tables, so every ceremony call refused on a fully migrated namespace (reproduced natively; never released). [Evidence](../../reports/tenancy/key-retention-2026-11-10/README.md) | Early destroy is refused by design; export-file expiry is not automated. Whether the ledger defect gets a register entry is the maintainer's call. |
| MT-OWNERSHIP-OPS | **Reproduced in lane** `6ee8fb04`: private `ownership-operations` contract (list, add, transfer, recover) with an expected-owner check, in-transaction operator authority and a separate operator database identity (authorization migration 0006). Race: one transfer applied, the other refused, both audited; foreign authority has no effect; 12 ablations. Unit 3078/0, related corpus suites 280/0. [Evidence](../../reports/tenancy/ownership-ops-2026-11-10/README.md) | Not yet started by the admin role; no operator identity in deploy config. Read-derived: subject removal can delete the last owner's subject; legacy subject-admin writers do not serialize with ownership changes. |
| MT-OIDC-SINGLE-PROVISION | **Reproduced in lane** `4b81f59d`: config inline or `_FILE`; single-site local Ed25519 signer, Vault optional for single-site and refused in multitenant; principals read the bound subject's current roles; identity list keyed on issuer + subject or issuer-verified email; fallback roles for unlisted people. test:all and integration 0 failing; OIDC matrix 9/9 with three controls; seven lane controls red then green. [Evidence](../../reports/tenancy/oidc-single-provision-2026-11-10/README.md) | **Decision needed:** the list is authoritative at each start (removes list-managed people taken off it; admin-UI edits to those subjects last until restart) versus add-only. UNMEASURED: real provider interoperability (email only in userinfo), concurrent starts. |
| MT-M6B-JOIN | Frozen candidate `3545236d` on `codex/m6b-join-20261110`: `dc795bd1` + the five lanes above + repairs `665119fb` (ownership paths pinned in the public-port isolation test, which failed 2 on the first merge) and `3545236d` (provisioning test registered in the integration tier). Focused 213 passing; tier check ok (614 files); lint 0 errors. | Full acceptance campaign in progress; push is the maintainer's after it. |

Lane detail: `externals/work/HANDOFF-{listener-composition,key-retention,ownership-ops,oidc-single-provision,connector-sync}-20261110.md`.


### Update — maintainer decisions on the M6b candidate; acceptance repair (2026-11-10)

| Scope | Recorded result | Remaining boundary |
|---|---|---|
| MT-OIDC-SINGLE-PROVISION | Maintainer chose the authoritative list: [single-site-oidc-list-authoritative](decisions.md#single-site-oidc-list-authoritative). | — |
| BF-228 | The deletion-ceremony ledger defect found by MT-KEY-RETENTION is filed as [BF-228](../../docs/30-design/remedial/nightscout-backfix-register.md) in the pre-release findings (preview branch only; fixed on the lane, joined). | Reaches #8898 with the M6b candidate push. |
| MT-M6B-JOIN | **Measured, stopped:** acceptance on `3545236d` gave unit 3106, dom 205, dependency 368/2, core 319, harness 99, stress 18, browser 686, all 0 failing; integration 3624/547 pending/**2 failing**, both in `tests/human-session-provision.test.js`. Cause: `lib/server/env.js` removes `API_SECRET` from `process.env` once read (the BF-27 mechanism), so in the shared integration-tier process the file booted after `tests/headless-test-server.test.js` with no secret and never connected. Repair `b70ad83f` sets a fresh secret before boot (tier order: 30 passing with it, 11 passing / 2 failing without it). [Stopped run](../../reports/tenancy/m6b-join-2026-11-10/3545236d-acceptance/README.md) | Full campaign re-running on `b70ad83f`; the corpus, OIDC matrix, lane native instruments and prcheck were not reached on `3545236d`. |


### Update — M6b joined candidate b70ad83f accepted for #8898 (2026-11-10)

| Scope | Recorded result | Remaining boundary |
|---|---|---|
| MT-M6B-JOIN | **Reproduced** on frozen head `b70ad83f` (`dc795bd1` + CodeQL 150, listener composition, key retention, ownership operations, single-site OIDC provisioning, three join repairs): unit 3106, dom 205, dependency 368/2 pending, core 319, harness 99, integration 3643/547 pending, stress 18, browser 686, multitenant corpus 550/1 pending over 49 suites, all 0 failing; OIDC matrix 9/9 with 3/3 controls, gate 13 checked/0 failing; key-retention native 6, ownership family 20, internal-api Compose pass and its blanket-window control exit 1; test:tiers ok (614 files); write-intent and write-boundary clean; lint 0 errors; prcheck OK. [Evidence](../../reports/tenancy/m6b-join-2026-11-10/b70ad83f-acceptance/README.md) | Push of `b70ad83f` to `workspace/multitenant-20261102` (fast-forward, 12 non-merge commits) is the maintainer's. UNMEASURED: CI and CodeQL on the pushed head; lane unit ablations repeated on the joined head; real role processes over Compose; ownership in a serving role and its deploy grants; production key custodian and Vault policy. |


### Update — runtime topology, private API composition and evaluator inspection (2026-11-10)

| Scope | Reconciled result | Remaining boundary |
|---|---|---|
| Current topology | [Runtime guide](../../docs/30-design/tenancy/runtime-topology.md) and three grid plates distinguish historical ed2/c23 reference, current dc795bd1 contracts/listeners, and proposed private-listener/fixed-roster target. Historical accepted artwork and measurements remain unchanged. Application and lifecycle are both private API purposes; UDS/TCP is binding. | No application code, new network deployment or accepted replica topology was created. Direct HTTPS is not implemented by the current adapter; direct JSON calls retain existing authority. Gateway status/header projection is an optional adapter, with roles-gateway prior art. |
| Work needed | [Work plan](../../docs/30-design/tenancy/selectable-endpoints-and-api-scaling-plan.md) assigns explicit module/method/path registration and per-operation lifetimes, operational interfaces, remote binding and fixed-roster proof. MT-ENDPOINT-TRANSPORT is in-progress for existing code plus remaining work; its gates stay UNMEASURED. | Preserve public/private separation, current credentials, response completion, lifecycle access during maintenance and exact-instance census/pinning. API scaling, workload ownership, observability and deployment acceptance are distinct criteria. |
| Evaluator/other workers | Planned read-only evaluator inspection reports configured assignment versus observed membership/eligibility/workload; standalone covers all configured tenants and multiple ordinals divide hash assignment. Existing MT-EVALUATOR-PARTITION owns payload/schema and transition controls. Notification attempts, connectors, realtime and maintenance have different ownership units. | No ring API exists yet. Measure stable coverage, observed conflicts, progress and bounded-overlap/idempotent effects; do not infer exactly-once commits, equal load or a common ring for every role. |
| Verification | [Artifact evidence and control](../../reports/tenancy/runtime-topology-reconciliation-2026-11-10.md): three SVGs fresh; deliberately stale content exits red; current output green; generator compilation/whitespace and generated queue views pass. Freshness is included in queue-check. | Whole-repository links retain six baseline failures to another lane's untracked deploy-companion note. Local site build/check and remaining integration details are recorded in `externals/work/HANDOFF-runtime-topology-2026-11-10.md`. No runtime campaign or milestone promotion. |


### Update — realtime sharding and evaluator/realtime composition proposal (2026-11-10)

| Scope | Concrete proposal | Remaining boundary |
|---|---|---|
| Realtime scale/recovery | [Single current plan](../../docs/30-design/tenancy/realtime-sharding-plan.md) proposes stable logical tenant shards, shared edge/alarm placement generations, actual owner incarnations, checkpoint continuity, cohort subset coverage and controlled moves/rollback. MT-REALTIME-SHARDING is the bounded M7 capability; MT-SCALE-UNBOUND consumes its correctness work for horizontal measurements. | Proposal only; no application branch, sharding code, selected shard count/hash, automatic partition takeover or capacity result. Existing single-realtime acceptance retains its source. |
| Composition | Keep evaluator scheduling/intent and realtime connection/subscription/delivery responsibilities explicit; permit co-hosted processes or a measured composed-process profile. Existing launcher source accepts composed roles and requires separate checkpoints. Shared input/view work must be measured before assuming merging processes removes it. | No requirement for separate deployments, identical evaluator/realtime pools, new network hop, broker or authentication redesign. Composition and independent-pool trade-offs are in the plan. |
| Safety/compatibility criteria | The plan specifies wrong-owner/polling refusal, warmup, held-response drain, old-owner exclusion, unknown-live refusal, late/uncertain alarm outcomes, empty/suspended assignments, rollback and full maintenance census. Existing alarm acceptance remains handoff, not device receipt or event replay. | Native experiments and semantic controls remain UNMEASURED. Durable viewer replay and single-hot-tenant connection sharding require separately chosen contracts. No operator release/default or milestone promotion. |


### Update — #8898 at b70ad83f: CI and CodeQL green (2026-11-10)

| Scope | Recorded result | Remaining boundary |
|---|---|---|
| MT-M6B-JOIN | **Pushed by the maintainer:** PR #8898 head `b70ad83f` (read from GitHub). All 16 CI jobs green: four Node/MongoDB test pairs, two no-database, maintained MongoDB 8.0.29, browser chromium/firefox/webkit, npm 12, Docker amd64/arm64, the multitenant opt-in corpus, and CodeQL. No open code-scanning alerts on the PR; alert 150 fixed by `7b30a6f2`. `MT-M6B-JOIN`, `MT-KEY-RETENTION`, `MT-OWNERSHIP-OPS` and `MT-OIDC-SINGLE-PROVISION` move to in-flight-upstream. | Draft; review, taking it out of draft and merge are the maintainer's. Listener composition shipped; `MT-ENDPOINT-TRANSPORT` keeps real-role deployment and the shared-listener configuration shape. Coordinator handoff: `externals/work/HANDOFF-m6b-join-20261110.md` (local). |

### Update — M6b follow-ups and ownership in the admin role, on lane branches (2026-11-10)

| Scope | Recorded result | Remaining boundary |
|---|---|---|
| MT-OWNER-LAST-GUARD (BF-229) | **Reproduced and fixed on `codex/m6b-followups-20261110` `65657a62`** (base `b70ad83f`): owner revocation could remove the last usable owner. PostgreSQL 16: 23/2 on `b70ad83f`, 25/0 with the fix; four ablations. Legacy-writer question settled by [root-may-edit-owner-subjects](decisions.md#root-may-edit-owner-subjects). [Evidence](../../reports/tenancy/m6b-followups-2026-11-10/README.md). | Join into the next #8898 candidate. Export-artifact expiry (D-B) is with the maintainer. |
| MT-ADMIN-ROLE-OWNERSHIP | **Ownership operations composed into the multitenant `admin` role on `codex/ownership-role-20261110` `1376c294`** (base `b70ad83f`): native suite through `nightscout multitenant admin` on PostgreSQL 16, 11/0; unit `tests/admin-role.test.js` 9/0; unit tier 3116 passing; eight controls red then restored. `ownership_operator` identity with five table grants derived from `lib/tenant-ownership/postgres.js` (commit `e6f6e248`, to port to nightscout-deploy). [Evidence](../../reports/tenancy/ownership-role-2026-11-10/README.md). | Join into the next #8898 candidate; deploy-repo overlay port. Read-derived inputs for the maintainer: admin's default bind collides with the plane rule (exit 78 unless `ADMIN_HOSTNAME` is set); the restore cohort census refuses while the admin role holds connections; ownership changes are not fenced during export/restore/deletion. |

### Update — 2026-11-10 decision batch joined and accepted for #8898, not pushed

| Scope | Recorded result | Remaining boundary |
|---|---|---|
| MT-BATCH-JOIN-1110 | **Accepted candidate `16a1fc2d`** on `codex/batch-join-20261110`, a fast-forward of #8898 `b70ad83f` by 37 commits. Lanes: root admin parity `165c13bf` (with BF-229 `65657a62`), admin lifecycle `66655756` (with ownership role `1376c294` and BF-230), internal listener `78ecba76`, pause/suspend `07981b55`, export expiry `701eba6f`, consumer revision and repeat clock `956d0940` (BF-231), tenant extended settings `2f1ae027` (BF-232). Seven join repairs. Migrations: lifecycle 0006 artifact removal, 0007 activity; authorization 0007 role administration. Full campaign on frozen `3cd1c487`: unit 3167, dom 205, dependency 368/2, core 319, harness 99, integration 3643/593, stress 18, browser 686, corpus 596/1 (54 suites), OIDC matrix 9/9 with three controls, Compose instrument and controls as recorded; all 0 failing. Delta on `16a1fc2d` (BF-232, `environment.js` only, production bundle byte-identical): unit 3176 and the other tiers re-run, 18 environment-reaching corpus suites 160/1; prcheck OK. [Acceptance](../../reports/tenancy/batch-join-2026-11-10/16a1fc2d-acceptance/README.md). | Push is the maintainer's; CI on the pushed head is unmeasured. Follow-ups: activity selections and grants in the deploy demo, export-expiry `removeArtifact` production wiring, the deploy tree's final copy to nightscout-deploy, and `devicestatus.advanced` parity (read-derived). |

### Update — #8898 at 16a1fc2d: CI green; next lanes (2026-11-10)

| item | state | evidence |
|---|---|---|
| #8898 head `16a1fc2d` (2026-11-10 batch, pushed by the maintainer) | CI: 17 pass, 3 skipped, none pending (read 2026-11-11 02:20Z and 02:27Z). The ten batch items move to `in-flight-upstream`. | `reports/tenancy/batch-join-2026-11-10/16a1fc2d-acceptance/README.md` |
| Correction to that acceptance record's UNMEASURED list | API ingest refusal and socket disconnect under suspend **are** wired in core at `16a1fc2d` when a role has an `activity` block (`preview-api.js:123-131`, `preview-realtime.js:38-44`); what is unwired is the in-tree Compose plan, which grants and configures no activity reader. | lane E2 reading, `docs/30-design/tenancy/sql-and-migration-architecture.md` |
| `devicestatus.advanced` for a tenant | Measured, client-state difference **not reproduced**: tenant frames are always full (`delta:false`), for which merge and replace agree. A tenant's status reports `devicestatus: null` where a single site reports `{advanced:true, days:1}`; whether to report it for display parity is an open maintainer question. | `reports/tenancy/devicestatus-advanced-2026-11-10/README.md` |
| SQL guide and database design page | Refreshed against `16a1fc2d` (activity, key retention and export removal, restore census, `ownership_operator`). | `docs/30-design/tenancy/sql-and-migration-architecture.md` |
| Archiving of four dispatch-era plans | Not done: two are live evidence for in-progress items; two can move once the queue and release-record links are rewritten with them. | lane E2 report |
| Decisions | [pool-primitive-shared](decisions.md#pool-primitive-shared), [vcpool-egress-capacity](decisions.md#vcpool-egress-capacity), [8898-continue-adding](decisions.md#8898-continue-adding), [tanka-binding-parallel](decisions.md#tanka-binding-parallel), [bench-first-on-workstation](decisions.md#bench-first-on-workstation) | this file's sibling |
| Lanes | Started: `DEPLOY-TREE-HOME` (fixture shrink), `MT-POOL-PRIMITIVE`, `MT-BENCH-BASELINE`, `DEPLOY-K8S-BINDING`, connector outbound gaps. Queued: `MT-CONNECTOR-REVERSE` after the pool primitive. | `queue/work-queue.yaml` |

### Update — next #8898 batch: lane branches ready to join (2026-11-10)

| branch (base `16a1fc2d`) | head | what | focused evidence |
|---|---|---|---|
| `codex/deploy-fixture-20261110` | `f3dc10c8` | `deploy/multitenant` reduced to the five modules core tests load; operators pointed at nightscout-deploy (synced to `16a1fc2d` on `deploy/compose-sync-20261110` `085d88ad`) | unit 3176, fixture suites 28 + 19 integration, removal control red; `reports/tenancy/deploy-fixture-2026-11-10/README.md` |
| `codex/devicestatus-advanced-20261110` | `0df0e66f` | [tenant-devicestatus-status-parity](decisions.md#tenant-devicestatus-status-parity): status route and realtime status frame report `{advanced:true, days:1}`, operator override honoured | unit 3178, multitenant integration 44, default-removal control red; `reports/tenancy/devicestatus-advanced-2026-11-10/README.md` §7 |

Not joined; full acceptance runs on the frozen join with the other lanes in progress (pool primitive, connector).

### Update — M6d outbound sync measured; evaluator partition and Kubernetes smoke (2026-11-10, late)

| item | state | evidence |
|---|---|---|
| Outbound Nightscout-to-Nightscout sync from a tenant (`16a1fc2d`) | 3 of 3 full runs `37 checks, 0 failing`: entries, treatments, devicestatus and profiles match through nightscout-connect 0.1.0 (embedded, as cgm-remote-monitor ships it) and the lock pin; revoke, delete, pause and suspend refuse as designed and the withheld rows arrive afterwards; tenant B untouched. No server defect. Token expiry not measurable without a code change (lifetime fixed at 28800 s, `lib/secrets/component.js:222`). | `reports/tenancy/connector-sync-out-2026-11-10/README.md` |
| nightscout-connect behaviour (connector, not core) | Reproduced: recovery after any refusal takes 14–26 min (doubling backoff on the 5-min cadence); refusals log only `Polling frame failed (HTTP 401|423)`; no credential re-exchange on refusal (read-derived). | same |
| `workspace.lock.json` connector pin | Stale: the pin `b394411a` is `v0.0.13`, older than the released `v0.1.0` that core depends on. On the pin: crash without a source secret, `forever` stops after 5 min, collection setting ignored, source token and destination secret printed to stdout. 0.1.0 embedded did not print the token and stayed up 110 min. The lock file has an uncommitted peer edit; the pin move waits for its owner. | same |
| Evaluator partition (`codex/evaluator-partition-20261110` `cb1b751d`) | Content-identity freshness and table-held count: overlap 26 requests, 26 distinct keys, 0 duplicates; 2→3 switch with no restarts, unowned gap ≤ 200 ms; crash restart unowned ≤ 1.5 s; unit 3219; lab 22/22; connector lab 24/24. Hygiene follow-up in progress. | `reports/tenancy/evaluator-partition-2026-11-10/README.md` |
| Kubernetes binding on kind (nightscout-deploy main, local) | 17 of 23 equivalence rows smoked; cohort held to one replica offline ([cohort-pod-not-scaled](decisions.md#cohort-pod-not-scaled)); restore operator has no Kubernetes counterpart yet. | `reports/tenancy/k8s-binding-2026-11-10/README.md` |
| Compose baseline bench | Numbers under concurrent load at 1/10/50 tenants; 100 and 200 do not start; idle PostgreSQL 899% CPU at 10 tenants. Perf lanes started ([cost-proportional-to-activity](decisions.md#cost-proportional-to-activity)). | `reports/tenancy/bench-baseline-2026-11-10/README.md` |
| nightscout-connect follow-ups | Filed nightscout/nightscout-connect#85 (slow recovery after a refused poll, thin refusal logging, no re-exchange on a data 401), from the outbound sync record; the lock pin moved from `v0.0.13` `b394411a` to `v0.1.0` `4dde1ecd` (`0046cb2a3`). | `reports/tenancy/connector-sync-out-2026-11-10/README.md` |

### Update — 2026-11-11 batch joined and accepted for #8898 at 0392acf9, not pushed

| item | state | evidence |
|---|---|---|
| Batch `codex/batch-join-20261111` (base `16a1fc2d`) | Joined: deploy fixture, devicestatus status parity, pool primitive, reverse connector, evaluator partition and hygiene, perf-db (fence epoch, bounded warm, pool configuration, serve-then-warm readiness, admission epoch, lazy domains, complete write clock), perf-realtime (publish on change, BF-233 fix, parking, change-stamp function, incremental view), perf-evaluator (on change, consumers on change, gap alert), eval-cost (C, D, E, B, A with insertion-ordinal total order). Integration: evaluator signature switched to the clock pair with one batch read per pass; root_writer control-schema reads; change-stamp grants. Frozen `2f1acc71`, final `0392acf9` (two test-only acceptance fixes). | `reports/tenancy/batch-join-2026-11-11/0392acf9-acceptance/README.md` |
| Acceptance | unit 3315 (1 pending), dom 205, dependency 368 (2 pending), core 319, harness 99, integration 3643 (703 pending), stress 18, browser 686; corpus 65 suites 706 passing, 1 pending; OIDC 9/9 with three red controls; Compose final and deadline pass with both controls red; 0 failing in every tier. Partition lab 23/23, connector-reverse 25/25. 13 h traces identical to base on 6 runs; read lab 5,976/5,976 equal, every order difference on a tie. prcheck OK (contains `official/dev` `4a482627`). | same |
| Idle evaluator cost after the clock switch (N=100) | 24.4 → 1.24 DB-ms and 240 → 1.8 queries per tenant-minute. | same |
| BF-233 | fixed on the batch head (realtime closes the transport on shutdown; stock clients 2000/2000 at 1,000 tenants × 2). | `reports/tenancy/perf-realtime-2026-11-10/README.md` |
| Still to do | nightscout-deploy sync to this head (change-stamp catalogue and grants, api `UPDATE(last_stamp,last_delete_stamp)`, function owner USAGE on the clock schema, healthcheck `start_period`, Kubernetes startupProbe); quiet-host capacity campaign at 1k and 3k tenants; CI on the pushed head. | same |

### Update 2026-11-12: M7 batch planned (capacity findings to fixes)

The 2026-11-11 capacity campaign ([record](../../reports/tenancy/capacity-2026-11-11/README.md)) met 1,000 tenants and did not meet the 3,000 gate on `5c60aec6`+`d1c7aca`. All the planned changes, M7 included, are gathered into one batch, all based on `workspace/capacity-fixes-20261111` at `5c60aec6`. The lanes run in parallel and join to one frozen head. Full acceptance runs on that head, then the 3,000/5,000/10,000-tenant capacity campaign on a quiet machine.

| lane | queue item(s) | branch | decision(s) |
|---|---|---|---|
| authorization cost (profile first) | `MT-AUTHZ-COST` | `workspace/authz-cost-20261112` | [authorize-cost-first](decisions.md#authorize-cost-first) |
| api replicas behind one service address | `MT-ENDPOINT-TRANSPORT`, `MT-API-FIXED-ROSTER` | `workspace/api-replicas-20261112` | [cohort-pod-not-scaled](decisions.md#cohort-pod-not-scaled) and the [scaling plan](../../docs/30-design/tenancy/selectable-endpoints-and-api-scaling-plan.md) |
| realtime: no socket cap, disconnect codes, config stat cache | `MT-REALTIME-SOCKET-CAP` | `workspace/realtime-cap-20261112` | [realtime-no-socket-cap](decisions.md#realtime-no-socket-cap) |
| tenant registry: gaps before default, then live add | `MT-TENANT-REGISTRY`, `MT-TENANT-LIVE-ADD` | `workspace/tenant-registry-20261112` | [tenant-registry](decisions.md#tenant-registry), [tenant-live-add](decisions.md#tenant-live-add) |
| D6 stage 2: slot reader + NOTIFY (stamp scan grows with N) | `MT-D6-SLOT-READER` | `workspace/d6-slot-20261112` | [D6](../../docs/30-design/tenancy/multitenancy-decisions.md#d6) |
| capacity fixes (already done) | `MT-CAPACITY-FIXES` | `workspace/capacity-fixes-20261111` `5c60aec6`; deploy `deploy/capacity-fixes-20261111` `d1c7aca` | [tenant-registry](decisions.md#tenant-registry) |

Second wave, after the api replicas and realtime lanes: `MT-REALTIME-SHARDING`. Its unadopted design points (shard count and hash, alarm replay, takeover) come to the maintainer first. Then `MT-SCALE-UNBOUND` measures the batch. nightscout-deploy follows every lane in one binding branch. Not pushed: #8898 is at `0392acf9` locally (push commands handed over 2026-11-11).

### Update — D6 maintainer answers recovered (2026-11-11)

| Scope | Recorded result | Remaining boundary |
|---|---|---|
| `MT-D6-SLOT-READER` decisions | Recorded [paged outage backstop](decisions.md#d6-paged-backstop), [SQL-polling reader transport](decisions.md#d6-sql-reader-transport), and [pause/suspend control-path requirement](decisions.md#d6-activity-control-path) from the maintainer's recovered Claude answers. The queue notes link to these decisions. | Design only; no runtime change or acceptance. Implement the reader and consumer wake/recovery path, bound and alert on degraded paging, preserve tenant isolation and existing pause/suspend upload semantics, and measure idle-tenant activity transitions, reader outage/recovery and per-call cost with negative controls. Reader placement and identity remain design/review work. Local handoff: `externals/work/HANDOFF-d6-decisions-2026-11-11.md`. |

### Update — first M7 local join and focused configuration-cost repairs (2026-11-11)

| Scope | Recorded result | Remaining boundary |
|---|---|---|
| First M7 join | Core `codex/m7-join-20261111` `65ea9e37` incorporates API replica configuration/client, realtime socket/cause/deadline/cache work, and the D6 no-trigger control, plus measured unchanged-roster and admission-file cache repairs. **Reproduced:** 132 focused checks and 4 disposable-PG synthetic-census checks pass; tier inventory, no-trigger, changed-code lint and whitespace checks pass. [Evidence](../../reports/tenancy/m7-join-2026-11-11/README.md). | Local only, not pushed; incomplete candidate. Actual serving API replica authority/maintenance/B continuity, full-stack reconnect, edge controls, authorization cost, registry completion/live addition, D6 implementation and deployment binding remain open. Full/default-browser/enabled-corpus/capacity and final prcheck intentionally wait for the coherent candidate. Local evolving handoff: `externals/work/HANDOFF-m7-join-2026-11-11.md`. |
| D6 native proof | **Reproduced:** dedicated EXECUTE-only reader login through a fixed-slot SECURITY DEFINER prototype; ordinary FORCE RLS reads retain tenant isolation. Independent coordinator rerun: 36 SQL cases, 22 assertions pass. SQL target 1 still decodes a complete 5,000-insert transaction (5,003 messages); an outer LIMIT does not hard-bound decode. [Proof](../../reports/tenancy/d6-native-discriminators-2026-11-11/README.md), [joined-source capture](../../reports/tenancy/m7-join-2026-11-11/d6-native-root.json). | Prototype SQL behavior only. Shipping reader, runtime body/owner/publication pinning, notification/advance crash ordering, actual resource bounds, bounded consumer scheduling/activity recovery and deployment remain open. No RLS or restore-authority change. |

### Update — joined M7 implementation and deployment composition (2026-11-12)

| Capability | Recorded local result | Remaining integration boundary |
|---|---|---|
| Registry, durable connectors and live addition | Fixed on the local joined branch: durable connector definitions, provision-retry completion, registry-backed UI resolution, and D6 SQL reader/control-feed recovery. [Registry and connector evidence](../../reports/tenancy/registry-connector-2026-11-12/README.md), [live-add/feed evidence](../../reports/tenancy/live-add-and-config-feed-2026-11-12/README.md), [UI evidence](../../reports/tenancy/ui-registry-2026-11-12/README.md). BF-234 and BF-235 retain their mechanisms and scopes in the register. | Coherent joined deployment and full acceptance remain unmeasured. Canonical glucose and threshold persistence remains mg/dL; BF-235 concerns the persisted display preference. |
| API authority and request cost | Core join `623181b7c07586f72cffcaaec716983863cdf28c` includes actual replica authority/maintenance fences, private management-session issuance, bounded shared lifetime sessions, and local signature-proof reuse with fresh authority checks. [Management issuance](../../reports/tenancy/management-sessions-2026-11-12/report.md), [lifetime sessions](../../reports/tenancy/operation-lifetime-2026-11-12/report.md), [signature proof](../../reports/tenancy/access-signature-proof-2026-11-12/report.md). | These are focused source proofs, not a joined capacity verdict. Legacy DATA credential traffic retains its Vault path; signature-proof gains cannot be attributed to that profile. Opt-in source diagnostics are joined. Broader decision caching and cross-socket sharing remain [deferred research](decisions.md#authorize-cost-first), preserving fresh authority checks. |
| Deployment composition | Current binding `dcc4a70bafd4edf31c5cab4bf3099883bd7e37f9` pins core `2d0ae0354a38b4a88f43bc2ae5ec60c085058f64`. It joins the exact-probe realtime oracle and bounded private failure capture; source identity and explicit-core package checks pass. | Core has subsequently advanced by the test-only version-inventory repair below. Join the pending per-replica readiness fixture and update SOURCE once, then build a new exact paired image. The prior image is not exported as final. |
| Controlled realtime moves | Controlled ownership, warm-before-route admission and maintenance census are implemented locally. [Earlier exact-source native proofs](../../reports/tenancy/realtime-sharding-2026-11-12/README.md) retain their scopes. The [later publisher failure and controls](../../reports/tenancy/realtime-publisher-failure-2026-11-12/original-and-controls/README.md) preserve the unclassified native failure; the [final awaited-tail controls](../../reports/tenancy/realtime-publisher-failure-2026-11-12/final-tail-controls/README.md) qualify the correlation/observation repair at source c10. | Final-pair native movement remains UNMEASURED. Unrelated clinical events remain observed and cannot satisfy or invalidate the dedicated probe; exact probe delivery and ownership/session/maintenance assertions remain strict. No uncertain-owner takeover or missed-alarm replay is claimed. |
| Frozen core acceptance | Core is now `ff5156b984424f1ef34bcef22d5bfa0071354cfa`. Earlier [first](../../reports/tenancy/m7-core-acceptance-2026-11-12/first-unit-campaign/README.md), [second](../../reports/tenancy/m7-core-acceptance-2026-11-12/second-unit-campaign/README.md) and [cancelled C](../../reports/tenancy/m7-core-acceptance-2026-11-12/cancelled-before-tests-c/README.md) campaigns retain their failed/NOT_RUN outcomes. [Core D](../../reports/tenancy/core-d-acceptance-2026-11-12/README.md) stopped at unit: 3562 passing, one pending, one failure; seven later tiers and the unfiltered corpus did not run. The [existing version-assertion repair](../../reports/tenancy/m7-unit-repairs-2026-11-12/evaluator-contract-version/README.md) passes sixteen focused checks; original and descriptor-downgrade controls fail as intended. It changes no production code. | Join planned native-readiness repairs before the next comprehensive campaign. Current inventory was measured on 2d: 706 files/eight tiers, 86 enabled suites/47 with own containers; ff changes only the existing test assertion. Full/browser/enabled-corpus and final prcheck remain open. Historical clinical, identity/client and Vault Agent proofs retain their exact source/environment attribution; no fresh execution is inferred. |
| Bounded source diagnostics | The opt-in pool/lifetime/auth timing capability is joined at core `d5e2e874659155c952b5b5deb862f12f982ac02e`. [Immutable source proof](../../reports/tenancy/m7-diagnostics-2026-11-12/report.md) includes native held-client/SQL/drain and logging-failure controls. Coordinator overlap checks pass after the diagnostics/sharding merge; the complete tier inventory is current. | Diagnostics remain off by default. Missing observations and direct-client pool occupancy are unmeasured; inclusive histograms do not establish causal ordering. The [profile provenance seam](../../reports/tenancy/m7-profile-provenance-2026-11-12/README.md) records explicit ON/OFF selection, safe settings fingerprints and bounded private logs; actual capacity remains unmeasured. |
| Fresh-host preparation | **Reproduced:** the first fresh-image diagnostic stopped before building because pool sizing eagerly loaded API dependencies. The shared error type is now dependency-free at core `a50130e67e8a8e066ce866535aeb8b627a068904`; clean preparation without `node_modules` and focused serving/error-identity checks pass, with a red dependency control. [Evidence](../../reports/tenancy/m7-fresh-image-preparation-2026-11-12/README.md). | The diagnostic binding `9799c51b61a9870bfc1257212fa19f4fb3f85ae3` pins the repair. The later [fresh-image diagnostic E](../../reports/tenancy/m7-core-acceptance-2026-11-12/fresh-image-diagnostic-e/README.md) passes on its exact D5/bc7 source pair with two tenants/two APIs/one realtime worker. It is not comprehensive or capacity acceptance. |
| Source-paired acceptance records | The [receipt validator](../../reports/tenancy/m7-receipt-validator-2026-11-12/README.md), [profile provenance](../../reports/tenancy/m7-profile-provenance-2026-11-12/README.md) and [idle-safety support](../../reports/tenancy/evaluator-idle-safety-2026-11-12/README.md) distinguish quiet safety from successful work. Instrument `52c76f7500312bc3ce8006f3783444b04489bdf53cd1f764417f77cf8333ba1d` has 37 files, capabilities4/profile3. Root focused checks pass 77 instrument/profile/control and 51 receipt tests. | A capacity receipt additionally needs an independently pinned, recomputed CURRENT strict-v2 native TIME witness with exact image/source/instrument attribution. A quiet observation, future timer or historical v1 proof cannot substitute. Actual final receipt/expectation and promotion remain open. |
| Capacity instrument and remote handoff | [Actual default-profile projection](../../reports/tenancy/baseline-time-applicability-2026-11-12/README.md) establishes why normal quiet data need not execute TIME within the unchanged idle period. The [first final-pair capture](../../reports/tenancy/evaluator-idle-safety-2026-11-12/native-2d0-dcc4-first-only/README.md) passes short functional idle safety with zero TIME completions and `timeWitness:false`; it is not a pilot or work proof. Subsequent [stock/restore continuity fails](../../reports/tenancy/api-readiness-continuity-2026-11-12/original/README.md) with three typed B warming responses; cause remains unclassified because request/upstream-stage timing was absent. | No retry/reset or later clinical/TIME/realtime-move/export ran on that pair. The [source-only cold-replica control](../../reports/tenancy/api-readiness-continuity-2026-11-12/cold-precondition/README.md) reproduces why global readiness is insufficient. Add explicit every-API/tenant readiness before strict continuity, preserving zero permitted errors during measurement. After acceptance, transfer the exact tested image with verified archive/ID/labels, then run matched baseline 500→750→1000 (API1/RT1/EV1/Vault SERVER). Independent component, live-add and real-IdP source lanes remain isolated. |

This is one evolving local batch, not pushed or fully accepted. Full/browser/enabled-corpus and final prcheck wait for the repaired coherent source and binding. Component adapter, incremental commissioning and real-IdP source work continue in independent lanes; their integration and capacity claims wait for the coherent acceptance boundary. Local ownership, exact resources and next steps remain in `externals/work/HANDOFF-m7-join-2026-11-11.md`.


### Update — M7 native qualification and corpus fixture closure (2026-11-12)

| Capability | Measured outcome and evidence | Remaining boundary / owner |
|---|---|---|
| Paired native correctness | **Reproduced:** [ff515/cf5 native qualification](../../reports/tenancy/m7-paired-qualification-2026-11-12/final-ff515-cf5-ready/README.md) passes exact API×tenant readiness, stock/socket/restore continuity, settings authority, clinical membership handoff and controlled realtime ownership movement. The [original process records](../../reports/tenancy/m7-paired-qualification-2026-11-12/final-ff515-cf5-ready-exit-records/README.md) retain actual outer exit codes; uncaptured settings-child codes remain null. | Earlier cold-readiness and publisher failures remain recorded. This functional scope establishes neither capacity nor automatic uncertain-owner failover/replay. |
| Current labeled native image | **Reproduced:** [761/315 minimal qualification](../../reports/tenancy/m7-paired-qualification-2026-11-12/primary-761-315-source/README.md) passes fresh readiness, clinical 2→3 membership and image export; [strict TIME](../../reports/tenancy/evaluator-trusted-scheduling-2026-11-12/native-761e8f-31565-source/README.md) records successful work for each selected owner. [Docker-input equality](../../reports/tenancy/m7-unit-repairs-2026-11-12/feed-opt-in-accounting/runtime-input-comparison.json) supports narrow reuse of unchanged older criteria at their actual executed sources. | No old execution is relabeled. A further source pin requires honest primary image/source custody and strict TIME support. Coordinator owns receipt assembly. |
| Comprehensive source acceptance | **Reproduced:** [Core G](../../reports/tenancy/core-g-acceptance-2026-11-12/README.md) passes all eight default tiers on core `761e8f19373c4fbbd6fc888b51b35c9b2eb677a1`, deployment `31565abe437ea84214aa0068f75de1246c06e45e`, alignment `502b46b05bc9a581d2c371f18f7e0e71852f0578` and remote harness `7209cb29020543a82412cd69d2751ca939cf4318`. Its full selected 86-suite corpus reports 838 passing, one pending and one failure. **Overall acceptance fails.** [E/F](../../reports/tenancy/m7-core-acceptance-2026-11-12/core-e-f-failures/README.md) separately retain interrupted Mongo-fixture and execution-accounting failures. | The unsafe-output-file fixture expected CLI exit64 and observed0. Original target-file mode was not captured. The [focused real PostgreSQL/Vault/CLI proof](../../reports/tenancy/m7-unit-repairs-2026-11-12/admin-secrets-permissions/README.md) separately reproduces the mode precondition failure and passes after explicit chmod and a mode assertion; the runtime permission guard is unchanged. No successful counts from another campaign can close this failure. |
| Repaired source freeze | Core `9db0ce94f072c8f34aab889f0181afa4269a6758` incorporates only the three-line permission-fixture repair; deployment `d76ef17878edb610cdeae75aeef9c07f94b60753` advances SOURCE metadata. [Root source closure](../../reports/tenancy/m7-unit-repairs-2026-11-12/fixture-source-closure/README.md) verifies sixteen unchanged Docker inputs/modes, the unchanged binding tree, five-file identity, two package checks and the current tier inventory. | Fresh primary labels/image/TIME support and final comprehensive acceptance remain open. The source comparison approves narrow older clinical and synthetic identity/client proof reuse with original attribution and limits. |
| Pending applicability | **Read-derived, corroborated by G logs:** default integration's 836 pending entries comprise 834 deferred functional bodies, one separately enabled HTTP performance benchmark and one preexisting mixed-validity timeout skip. The corpus's single pending case is that optional benchmark, guarded by `NS_TENANT_COMMIT_CLOCK_BENCHMARK=1`; the corpus runner separately enables its functional cases. | The benchmark is unrun, and the legacy mixed-validity behavior remains unmeasured. Pending cases never count as passes. Final policy must pin the exact names, flags and actual campaign counts. |
| Parallel measurement sequence | The repaired candidate starts a fresh complete source/browser/corpus campaign. [Maintainer direction](decisions.md#m7-parallel-unaccepted-measurement) overlaps it with matched 500→750→1000 observation on an independent remote rig under an explicit unaccepted authorization. | Source and transport owners implement the narrow admission/output scope; actual current image/TIME support remains required. Coordinator later qualifies the immutable data against actual same-candidate acceptance and final prcheck, without rewriting the initial unaccepted status. API1/RT1/EV1, Vault SERVER, diagnostics OFF and the exact qualified image remain fixed. Failed levels remain useful; production M7, Android, real-provider, HA and component-scale claims stay open. |
| Parallel later work | Component-profile runtime, live-add deployment and real Authentik/HTTPS preparation remain isolated, with their own focused evidence and boundaries. Architecture documentation reconciliation also remains an independent branch. | Join these after the immediate baseline boundary; none silently changes the frozen workload, image or receipt policy. The [local evolving handoff](../../externals/work/HANDOFF-m7-join-2026-11-11.md) records owners and retained resources. |


### Update — joined application accepted; matched baseline preparation (2026-11-12)

| Boundary | Recorded result | What remains |
|---|---|---|
| Coherent application acceptance | **Locally accepted:** core9db/deploymentd76/image293. [Reviewed policy and receipt](../../reports/tenancy/m7-joined-acceptance-2026-11-12/9db-d76-293/README.md) validate29 mandatory criteria and four semantic control triplets. [Core H](../../reports/tenancy/core-h-acceptance-2026-11-12/README.md) passes all eight tiers and selected86-suite corpus839 passing/1 optional benchmark pending/0 failures. Final prcheck returned0 with core unchanged and fresh official/dev contained. | No dev merge, push, operator release or production M7 promotion. Explicit pending applicability, older proof environments and the legacy mixed-validity coverage gap remain recorded. |
| Current native image/work | [Primary9db/d76 qualification](../../reports/tenancy/m7-paired-qualification-2026-11-12/primary-9db-d76-guard/README.md) passes readiness/clinical handoff/export. The [first expired-episode TIME observation](../../reports/tenancy/evaluator-trusted-scheduling-2026-11-12/native-9db-d76-guard-unmeasured/README.md) remains UNMEASURED. The [separate fresh-ingestion episode](../../reports/tenancy/evaluator-trusted-scheduling-2026-11-12/native-9db-d76-fresh-ingestion/README.md) yields38 successful TIME/min19 per owner/0 failures with actual collector0. Exact image archive SHA4eb4 is independently verified. | Build/clinical5d7/52 and TIMEdf181/638 provenance stay distinct. No unchanged stock/restore/realtime/client/clinical-timeline campaign was replayed. Local owned qualification containers are stopped and retained with data/images/networks. |
| First baseline setup | [Attempt A](../../reports/tenancy/m7-baseline-2026-11-12/attempt-a-image-store/README.md) correctly refuses remote image ID910 versus qualified config ID293 after verifying the same archive; application startup/load did not run. The archive itself binds OCI manifest910 to config293. | This is an image-store identity-form compatibility failure, not measured500-tenant performance. Fresh-rig classic-store pinning preserves the exact-ID guard; broader containerd/Kubernetes identity support remains separate qualification. |
| Next matched baseline | Remote owner launches a new accepted-mode500→750→1000 attempt with the genuine approved receipt, same image/archive/source and reviewed fresh-rig bootstrap7b. A's original pending authorization/result are immutable. The existing instrument captures SQL rates/times by database role, CPU/RSS by service, stored-count oracles and recovery. | [Attempt B](../../reports/tenancy/m7-baseline-2026-11-12/attempt-b-startup-progress/README.md) verifies classic storage and loaded image293, then stops during500-tenant evaluator readiness before idle/load/recovery. The actual adapter returns1; raw failed rows were not retained, so the exact historical predicate remains unknown. Controller/watchdog cleanup is verified. Capacity stays UNMEASURED. A focused collector correction and bounded diagnostics are being prepared before another paid run; application source acceptance remains unchanged. |
| Remaining independent capabilities | Component-profile runtime, deployment live-add, real Authentik/HTTPS, Android, lifecycle/keys/recovery/soak, component capacity and Kubernetes equivalence remain separately owned. Real-IdP negative probes are source-ready on their isolated branch; its actual remote runner/provider/browser execution is unmeasured. | Keep these source histories isolated until their next coherent integration boundary. Local443/IPAM conflicts do not authorize stopping peers or changing tested origins. The [evolving handoff](../../externals/work/HANDOFF-m7-join-2026-11-11.md) retains exact branches/resources and owners. |
