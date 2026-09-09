**Nightscout: modernization review and proposed next steps**

Date: 9 September 2026. Status: draft for maintainer discussion.

This document consolidates Andy Low and Ben West's discussion about the next stage of Nightscout development, together with source checks and candidate approaches. Andy's immediate priority is a joint review of `chore/nightscout-modernization`. Once Andy and Ben are satisfied with that baseline, they can agree a firm, sequenced implementation plan. The framework and deployment recommendations below remain proposals.

**1. First gate: review and accept the modernization baseline**

Review [cgm-remote-monitor #8605](https://github.com/nightscout/cgm-remote-monitor/pull/8605) before committing to the next architecture. Establish a recorded source revision, dependency policy and regression baseline that later work can build on.

At the 9 September status check, #8605 was open and draft at `ee2a0b9ee83b26f811da8a096d6ebdb31e85780a`, targeting `dev`. GitHub reported successful completed test/security/build checks, two skipped publishing jobs, and **merge conflicts**. The current `dev` head was `a8888f0d9facb8a9bb54c2ab15333f3f241b45bf`, incorporating [#8726](https://github.com/nightscout/cgm-remote-monitor/pull/8726). This status check is not a completed integration review. Recheck these moving references when the review starts.

The [modernization plan](https://github.com/nightscout/cgm-remote-monitor/blob/ee2a0b9ee83b26f811da8a096d6ebdb31e85780a/docs/plans/nightscout-modernization.md#L28) already specifies merge and release gates. Use its [completion evidence](https://github.com/nightscout/cgm-remote-monitor/blob/ee2a0b9ee83b26f811da8a096d6ebdb31e85780a/docs/test-specs/modernization-completion.md), security follow-up and tracker reconciliation as review inputs.

The proposed joint review should:

1. Refresh against current `dev`, resolve integration conflicts and review the resulting changes, including connector pins and accepted logging/lifecycle fixes.
2. Review dependency upgrades, deliberate retentions, runtime/database support, migration documentation and compatibility decisions. A stable baseline means reviewed, supportable dependencies with explicit exceptions; it does not require every package's newest major version. The [M28 decision](https://github.com/nightscout/cgm-remote-monitor/blob/ee2a0b9ee83b26f811da8a096d6ebdb31e85780a/docs/plans/browser-widget-decision.md#L1), for example, deliberately retains selected jQuery/UI and upgrades Flot while preserving existing browser constraints.
3. Validate the actual proposed merge: relevant focused tests, backend tests, separate client-core and dependency suites, browser journeys, clean production/development builds, CodeQL and Docker checks across the supported matrix. Keep quarantined tests and validation limitations visible.
4. Review whole-application measurements: production dependencies and image size, server heap/RSS under repeated workloads, and browser transfer/startup/navigation costs. Separate development tooling growth from deployed costs and avoid adding historical slice savings together.
5. Complete maintainer-owned deployment, upgrade/rollback, applicable live vendor/hosting checks, and physical-device Safari/VoiceOver acceptance. Automated browser tests do not establish those manual passes.
6. Record both maintainers' review, remaining exceptions, integration decision and accepted baseline SHA. Distinguish branch acceptance, merge and release. Revalidate the final merge against the current target.

The next roadmap becomes firm after this gate. Preparatory discussion and small evidence-gathering experiments can continue, but this document does not authorize a UI rewrite or automatic merge of #8605.

**2. Direction emerging from the discussion**

| Topic | Discussion direction | Still to decide |
| --- | --- | --- |
| Modernization | Andy proposes reviewing the integration branch together first | Accepted revision, resolved issues and merge/release readiness |
| Connect ownership | Bringing Connect into the main repository has broad support | Import baseline, PR transition and ownership |
| XState | Existing connector orchestration is valuable | Scope of new machines, typing and upgrade sequence |
| Reports | Ben identifies a strong modernization opportunity | User tasks, retained information and delivery boundaries |
| Statistics | Move report calculations behind a server API | Numerical definitions, schema and provenance |
| UI | Svelte is acceptable for consideration; reusable Web Components interest Ben | Framework, browser policy and component contracts |
| Charts/interactions | Sulka suggested interact.js and SVG.js | Whether either solves a specific requirement better than the baseline |
| PDF | Andy explicitly supports export for sharing with clinicians | Renderer, output quality and resource budget |
| Vendor browser sessions | Browser execution may help some vendor access flows | Provider-specific need, user interaction and optional deployment |
| Ecosystem tests | Share vendor scenarios where practical | First fixtures, runner contracts and maintainers |

Reports being hard to find and operate is a useful hypothesis from the discussion. Check it with representative users and tasks before finalising navigation. Preserve the information people value while improving access and controls.

**3. Bring Connect in-tree with clear PR ownership**

After baseline acceptance, propose a focused source-and-tests import into a modular area of `cgm-remote-monitor`. Preserve configuration, driver/orchestration/output boundaries, contributor history, debugging tools and regression coverage. Independent Connect distribution is not a requirement expressed in this discussion.

Inventory outstanding upstream work before selecting the import. The inspected modernization [dependency declaration](https://github.com/nightscout/cgm-remote-monitor/blob/ee2a0b9ee83b26f811da8a096d6ebdb31e85780a/package.json#L123) pins connector commit `51b6e6e0f035fed8c7a26881620974a18c98b4b3`. The logging change in merged cgm-remote-monitor #8726 pins `234d47c85510a77f07b3be0d2c026dd0272715d6`, while [connector #67](https://github.com/nightscout/nightscout-connect/pull/67) remained open at this check. A commit-pinned dependency can be consumed before its upstream PR merges, but the import still needs to reconcile all accepted fixes. Recheck the resolved lockfile when refreshing the integration branch.

Agree a cutover: identify where new fixes should target, reconcile in-flight PRs, transfer relevant issues and document the old repository's status. Keep urgent fixes releasable during the transition. Subsequent vendor additions, XState migration and report work should be reviewable separately from the import. Include Connect's native test runner in Nightscout CI rather than assuming the backend suite discovers it.

**4. Use XState selectively for workflows**

XState and a UI framework have different responsibilities. The proposal is to retain XState for connector authentication, token refresh, polling, retries and shutdown, and consider typed machines where asynchronous transitions need coordination.

| Behaviour | Proposed implementation |
| --- | --- |
| Auth/refresh/poll/retry/shutdown | Explicit connector machines and lifecycle tests |
| Vendor challenge requiring user action | States for waiting, completion, expiry, cancellation and recovery |
| Complex save or request/retry/cancel flow | A small machine when justified by the transition behaviour |
| Selected tab, input text, expanded section | Local component state |
| Statistics, conversions and normalization | Pure tested domain functions |
| Persisted treatment/profile data | Existing storage and API contracts |

Track connection state and data freshness separately. A connected session can still have stale data. Keep external-data validation at runtime boundaries; TypeScript does not validate vendor responses.

Preserve existing v4 behaviour during the import. Evaluate a pinned stable v5 toolchain for new typed experiments and migrate existing machines in a separate change: the [XState migration guide](https://stately.ai/docs/migration) documents behavioural/API differences. State-machine concepts being durable does not make library upgrades automatic. Type checking needs explicit configuration, and test APIs must match the installed major version.

Test observable outcomes with injectable HTTP, clocks and persistence: no overlapping polls, bounded retries, no cursor advance after failed persistence, cancellation and shutdown without later unintended writes. Cover already-issued writes explicitly. Model traversal alone cannot prove that the model is correct.

**5. Make reports the first proposed UI delivery**

The leading recommendation is **Svelte 5 and TypeScript**, starting inside the existing Nightscout application and APIs. SvelteKit would be a separate routing/rendering/deployment decision. [Nocturne's app and shared packages](https://github.com/nightscout/nocturne/blob/80b494084475bc1b02597c3a303bab170f109b0a/src/Web/packages/app/package.json#L1) provide concrete Svelte reuse candidates, but their dependencies and application assumptions need testing.

Dashboard and reports already have separate page entries. Their dependency overlap remains relevant: the [shared entry](https://github.com/nightscout/cgm-remote-monitor/blob/ee2a0b9ee83b26f811da8a096d6ebdb31e85780a/bundle/bundle.source.js#L14) loads jQuery UI and D3, and the [reports entry](https://github.com/nightscout/cgm-remote-monitor/blob/ee2a0b9ee83b26f811da8a096d6ebdb31e85780a/bundle/bundle.reports.source.js#L3) adds Flot. Give replacement reports explicit dependencies and measure everything their page loads. Aim for shared controls/chart foundations, load report-specific features on demand, and retire replaced Flot/widgets after parity.

Start with Daily Stats: find Reports from the dashboard, select dates, see units/timezone, load results, inspect tables/charts, export, change filters and recover from failures. Preserve reading counts, range proportions, extrema, average, deviation, quartiles and labelled estimates. Then use an hourly percentile report to test more demanding chart reuse. Inventory other reports, including treatment/profile and Loop-specific information, before promising full replacement.

Agree browser support before rollout. The [current target file](https://github.com/nightscout/cgm-remote-monitor/blob/ee2a0b9ee83b26f811da8a096d6ebdb31e85780a/.browserslistrc#L1) includes old iOS versions; it records intended targets, not proven feature support. Nocturne's Tailwind 4 components bring a [Safari 16.4 minimum](https://tailwindcss.com/docs/compatibility). Any raised minimum or temporary dual UI needs an explicit transition, owner and retirement condition.

Acceptance includes both units, timezone/DST cases, empty/stale results, translated errors, information density, non-colour cues, contrast, zoom/reflow, keyboard/touch and physical screen-reader checks. Test stale request completion, repeated navigation and cleanup. Keep rollback available during acceptance.

**6. Provide standard Web Components for selected views**

Ben's embedding goal should become a concrete test. [Svelte can compile components into custom elements](https://svelte.dev/docs/svelte/custom-elements), so propose a public view such as `<nightscout-daily-stats>` that works in Nightscout and on a plain HTML page. Hosts load a built module; they need no Svelte build pipeline, although the module includes its runtime.

Define a small public interface: attributes for simple settings, properties for structured results, DOM events and documented theme variables. Keep ordinary internal controls as Svelte components. The host/controller supplies an authorized report snapshot; the view must not depend on Nightscout globals or duplicate statistical calculations.

Test two independent instances, updates, removal/reinsertion, conflicting host styles, accessible interaction and bundle size. Svelte's custom-element lifecycle, shadow-root styling and context boundaries need explicit checks, especially for Nocturne components. Define registration/version behaviour. Remote fetching/authentication is a separate contract: embedding does not bypass cross-origin rules or protect secrets from the host page.

Lit is a focused alternative if Svelte's custom-element integration creates substantial friction; Vue is another credible incremental UI option. Compare a bounded equivalent slice when needed, without funding several complete rewrites.

**7. Choose chart and interaction dependencies by demonstrated need**

| Tool | Role | Initial proposal |
| --- | --- | --- |
| Svelte and custom-element exports | Rendering and reusable view interface | First reporting implementation |
| Selected D3 modules | Scales, shapes and chart interactions | Reuse existing knowledge; measure the resulting bundle |
| interact.js | Dragging, resizing and multi-touch gestures | Evaluate for a defined interaction |
| SVG.js | SVG creation, manipulation and animation | Evaluate for specialised drawing requirements |

[interact.js](https://interactjs.io/docs/) supplies interaction events; application code still owns behaviour, visuals and keyboard alternatives. [SVG.js](https://svgjs.dev/docs/3.2/) supplies drawing operations. Neither selects the UI architecture or supplies Nightscout's complete report semantics. Start with declarative SVG and relevant [D3 modules](https://d3js.org/what-is-d3), or a proven compatible chart component. Give each renderer clear DOM ownership. Avoid accumulating overlapping stacks without a retirement plan.

**8. Make statistics reproducible and reusable through an API**

The inspected [Daily Stats plugin](https://github.com/nightscout/cgm-remote-monitor/blob/ee2a0b9ee83b26f811da8a096d6ebdb31e85780a/lib/report_plugins/dailystats.js#L42) mixes calculations and DOM/plotting. Some [math helpers are already isolated](https://github.com/nightscout/cgm-remote-monitor/blob/ee2a0b9ee83b26f811da8a096d6ebdb31e85780a/lib/report/statistics.js#L32), but filtering/grouping remains in the browser. Extract a pure calculation pipeline used by the existing Node server, then expose documented, authorized, bounded endpoints.

The [v2 summary endpoint](https://github.com/nightscout/cgm-remote-monitor/blob/ee2a0b9ee83b26f811da8a096d6ebdb31e85780a/lib/api2/summary/index.js#L113) serves recent in-memory data and current state, not historical daily report aggregates. Build on the existing API/storage infrastructure. Ben's [statistics API proposal](https://github.com/bewest/rag-nightscout-ecosystem-alignment/blob/80ce5f638ad921e78ba160361834c27b7c0c0e56/docs/sdqctl-proposals/statistics-api-proposal.md) is a starting point; agree the daily subset first rather than implementing every proposed endpoint.

Specify date-window inclusivity, timezone/DST, valid-reading filters, sorting/deduplication, target boundaries, missingness, units/rounding, percentile algorithm and deviation definition. Current range percentages count retained samples; they are not time-weighted durations. Some statistics use rounded display-unit values while estimates use original mg/dL. Preserve characterised behaviour during extraction and review intentional numerical changes separately.

Return chart-independent numeric JSON with effective inputs, schema/calculation version and data revision or fingerprint. A fingerprint identifies inputs; exact later replay also requires retaining or supplying them. Changed historical data can legitimately change results for the same dates. Permission checks must cover underlying data, and caching must account for settings and data changes.

Use frozen expected results from existing report pipelines plus independent numerical examples. Cover both units, unequal daily sample counts, empty middle days, repeat runs, duplicates, threshold boundaries and DST. Comparing the API only with its own calculation function would miss shared errors. Keep detailed plot data available where aggregates cannot meet the information need.

**9. Include PDF export while controlling runtime cost**

PDF export is an explicit desired outcome: a person can share a self-contained, dated report with a clinician for review and filing. The document records exported data and context; the clinician's review and interpretation belong to their workflow.

Use the same calculated snapshot for the web view, embed and PDF. New readings arriving during export must not silently change the selected result. Include title, optional user-confirmed identity/reference, dates, timezone, units, thresholds, reading counts/coverage, labelled estimates and generation time. Provide searchable text, legible charts, grayscale cues, sensible A4/Letter pagination, repeated headings and accessible reading order. Keep technical provenance in metadata or a compact appendix and omit credential-bearing links.

The first candidate is a **client-side PDF module loaded only on export**. [Client PDF libraries exist](https://pdfmake.github.io/docs/0.3/getting-started/client-side/); the exact renderer remains undecided. Measure deployed assets, cold export download/fonts, generation time, peak client memory and responsiveness on supported older devices. Lazy loading reduces initial load cost but does not eliminate asset bytes or export memory.

Browser print is a fallback: [window.print() opens a dialog](https://developer.mozilla.org/en-US/docs/Web/API/Window/print), not a guaranteed direct PDF download. A server PDF library without a browser engine is an alternative if client output fails acceptance. Server browser rendering adds browser/process costs and is outside the proposed default PDF path. An optional external renderer would need its own justification and operating model.

Inspect rendered PDFs and extracted text as well as API/screen/PDF number agreement, long periods, empty days and translated labels. The first reporting delivery should include successful download and clear failure/retry behaviour. Sending the file remains a user action.

**10. Treat vendor browser automation separately from PDF rendering**

Ben clarified that browsers may also be needed for vendor login, CAPTCHA or other access friction. Evaluate each provider's actual flow. His [July connector triage](https://github.com/bewest/rag-nightscout-ecosystem-alignment/blob/80ce5f638ad921e78ba160361834c27b7c0c0e56/docs/10-domain/nightscout-connect-connector-triage-2026-07-07.md) already discussed a Puppeteer Glooko approach and preferred investigating HTTP login first. That historical analysis is not proof that a particular provider needs a browser today.

Prefer reliable user-authorized HTTP integrations where available. If browser execution is necessary, propose an opt-in worker with separate installation/image packaging, bounded sessions/memory/retries and clear unavailable-worker behaviour. A disabled feature flag does not remove bundled browser bytes. The worker can share the main repository and release ownership without making every Nightscout installation carry it. Keep vendor sessions isolated from any PDF renderer.

A browser does not guarantee unattended challenge completion. Design waiting-for-user, completion/resume, expiry, timeout and cancellation explicitly. This is a useful XState application. Require an end-to-end provider trial and measured costs; test challenge and failure transitions with controlled fixtures. Keep browser-dependent providers separate from the initial source import.

**11. Share vendor testing across the ecosystem**

Build on the [cross-project testing proposal](https://github.com/bewest/rag-nightscout-ecosystem-alignment/blob/80ce5f638ad921e78ba160361834c27b7c0c0e56/docs/sdqctl-proposals/cross-project-testing-plan.md): share sanitised/synthetic HTTP scenarios and expected normalized records/lifecycle outcomes. Each project supplies its native runner. Node and C# can exercise the same fake service without adopting the same UI framework or state-machine library.

Start with one vendor's authentication and data page; extend to refresh, rate limits, timeouts, pagination, duplicates, missing fields, regional hosts, patient selection and persistence failures. Use deterministic time and independent output assertions. Nocturne's existing harnesses are useful scenario sources, not directly importable Node tests. Hardware simulators offer related testing principles, with different transports. Recorded fixtures protect known behaviours; live vendor drift remains a separate validation concern.

**12. Turn the accepted baseline into a firm roadmap**

After joint modernization acceptance, propose these bounded work packages:

| Work package | Reviewable output | Dependency |
| --- | --- | --- |
| Decisions and user tasks | Short proposed ADRs for ownership, browser support, XState scope, report/API/component contracts and resource budgets | Accepted modernization baseline |
| Connect import | Source/tests/config compatibility and PR/issue cutover | Reviewed connector baseline |
| Statistics extraction | Daily calculation module with independent parity evidence | Agreed numerical contract |
| Statistics API | Documented daily endpoint, authorization and resource tests | Extracted module |
| First report and embed | Svelte Daily Stats flow and plain-HTML reuse proof | API; fixture-based prototyping may overlap |
| PDF export | Same snapshot, verified document quality and measured cost | Report contract and renderer trial |
| Shared vendor fixtures | First language-neutral scenario and native runners | Driver/test contract; independent of UI choice |
| Further reports/providers | Percentile report, additional vendors or optional browser worker | Evidence from the relevant first slice |

Every task should state its source SHA, owner, scope, dependencies, test commands, observable acceptance, reviewer and rollback. Land shared contracts before dependent changes. Coordinate ownership to avoid conflicting agent edits; assess throughput by reviewed integrations and regressions rather than code volume. Convert supported choices into ADRs after maintainer agreement.

**Source scope and relationship to existing work**

This is a discussion synthesis, not a new protocol audit or a completed modernization review. Its placement follows the workspace's [proposal/research guidance](https://github.com/bewest/rag-nightscout-ecosystem-alignment/blob/80ce5f638ad921e78ba160361834c27b7c0c0e56/docs/README.md). Existing domain and decision documents remain authoritative for their stated scope.

The main inspected snapshots were modernization `ee2a0b9…`, alignment docs `80ce5f6…`, connector logging `234d47c…` and Nocturne `80b4940…`; links above pin code evidence. The [July Connect architecture review](https://github.com/bewest/rag-nightscout-ecosystem-alignment/blob/80ce5f638ad921e78ba160361834c27b7c0c0e56/docs/10-domain/nightscout-connect-architecture-review-2026-07-07.md) is a useful starting point whose remaining gaps need refreshing. January frontend/reporting comparisons need similar care: for example, the reporting inventory says built-in reports lack estimated A1c, while inspected Daily Stats calculates it. Nocturne package reuse and candidate frameworks have not been benchmarked here.

| Date | Revision |
| --- | --- |
| 2026-09-09 | Consolidated discussion, source checks and proposed review gate; library and implementation choices remain open for maintainer agreement |
