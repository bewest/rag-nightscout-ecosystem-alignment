# M7 deployment composition discriminators

Captured 2026-11-12 UTC, synthetic local infrastructure only. These are focused
composition measurements, not final image, whole-role, browser or capacity
acceptance. Every failed/partial prototype is kept distinct from a repaired
fresh bootstrap. Private credentials and state remain outside this repository.

## Actual role boundaries

Core `c1c501b645ed2133d20d3577c2d99e427a77ca53`, deployment
`0ba0a46496d34b429cbe5104752d4ab202798873`: infrastructure bootstrap, composed
private admin/feed, API provisioning and private restore-operator commissioning
complete for two synthetic tenants. The API constructor then refuses through
`ACTIVITY_STORE_UNAVAILABLE`. Sanitized inner frames identify the activity
reader's metadata transaction: it joins the existing operation window, but its
identity lacks that window's three read-only metadata grants.

A separately recorded diagnostic intervention grants only USAGE and SELECT on
control schema_migrations, tenant_lifecycle_windows and tenant_lifecycle_operations
to activity_reader and display_reader. Both API processes then listen. The
committed binding repair is `cd219eb`; no RLS/admission guard was relaxed. This
intervened state is not a clean-source bootstrap result.

The actual API lifecycle RPC still returns 503: its legitimate registry cohort
label conflicts with the old response schema's UUID-only list. That is an open
whole-role wire boundary at this capture, owned by the realtime completion lane;
listening is not a successful readiness check. No restore acceptance is claimed.

Earlier core `fae4a925` paired with deploy `c48d6ee` also exposed a separate
composition prerequisite: the D15 validator had default PUBLIC EXECUTE. The
strict issuer refuses that extra function surface. Revoking PUBLIC and granting
EXECUTE only to the selected provisioning writer makes the composed admin
healthy. Binding repair `4696a21` preserves the strict issuer check.

## Cohort and launcher consistency

The launcher excludes its actual operation-control namespace from protected DATA
resources; cohort boot also needs that exact exclusion when activity uses the
same namespace. Pre-repair actual API startup fails, and [the source regression
fails](cohort-before.txt). Core repair `c1c501b6` passes [31 existing cohort/roster
checks](cohort-restored.txt), including a foreign namespace refusal. This is an
exact control-namespace alignment, not an arbitrary namespace allow-list.

## Priming and private custody

The first cold-tenant request returns explicit TENANT_WARMING, then its owned
warm completes. The old priming client treats that 503 as terminal. Client repair
`ef048e5316410bb668a2a0091785ff9470de865e` retries only an idempotent roles GET
with that exact transient code and a deadline. It does not replay mutations or
retry unknown unavailability/authority refusals. [Three actual HTTP checks](primer-http.txt)
cover warm recovery, immediate refusal and a bounded deadline.

That exact client helper was separately mounted into a diagnostic client against
the intervened core/deploy pair above: priming completes for both tenants.
Subjects, owner assignment and management issuance use their real APIs; no raw
subject/credential/session INSERTs seed them. Private files contain DATA and
management tokens, owner subject IDs and integer expiry values for both tenants;
the private operator handoff matches the priming output. No token values are
published. This client/source/grant tuple is not final clean-image acceptance.

## Edge resource budget

[Actual nginx capture](edge.json) against committed deploy `ef048e53` passes all
six admission properties and verifies all owned-resource cleanup. The template
renderer now uses an explicit per-worker connection budget (synthetic default
16,384; configurable 128..32,768) and 65,536 descriptor limits. Slots include
upstream connections. This replaces the old fixed 1,024-slot input, independently
of per-IP concurrency and handshake budgets. The capture uses mock upstreams;
it establishes no viewer count, production budget or application/client result.
