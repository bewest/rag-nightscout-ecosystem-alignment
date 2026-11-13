# Recovery retry incarnation: repaired source review

**Reproduced and independently approved at bounded source scope.** Candidate
`6972e2e7ceb6f0c95c84c6bc107354a0a457a546` is a child of the original
`f1d21ef0d289d1e750cf771406a361ae67b9945d` [source checkpoint](README.md).
The original failed review and passing focused checks retain their attribution.

Independent review found that a new postmaster could be adopted before a later
pool readoption failed. On retry, the lower window reported no restart, so the
cohort could serve with its previous participant incarnation. An old participant
pin could then invalidate current role state. This was a functional stale-pin
failure, not only an inaccurate restart counter.

The repair retains the restart/incarnation obligation across readoption or final
probe failure, until successful cohort publication. Tests use the actual
supervisor/window/cohort modules with recording catalogue, pool and role ports.
Old pins refuse without effects; the current pin reaches four role contexts;
a healthy follow-up does not allocate another incarnation.

Independent replay passed **121 focused checks**, exit zero. The original and
nonsticky mutant each pass one/fail two targeted checks; restoration passes all
three. The unchanged original replay passes on the repaired head. Its old
hardcoded source label is retained; separate replay provenance binds the actual
6972 source rather than relabelling the original capture. Parent verified all
11 reviewer artifact hashes. These overlapping checks are not additive.

This is source approval, not application dev integration, release or native
recovery proof. No database, container or cloud resource was started. Selected
changed-postmaster recovery still requires explicit rebinding and refuses before
cache invalidation/adoption; no uncertain credits are forgiven. Actual selected
safe-refusal behavior must be observed on the later coherent deployment before
claiming it. Automatic resource-epoch transition is not implemented by this fix.

The integration coordinator accepted this source boundary and released the next
restore/resume source join. Full/native acceptance and final prcheck remain one
later coherent campaign. No existing frozen runtime artifact was changed.
Local custody: `externals/work/HANDOFF-recovery-admission-join-2026-11-12.md`.
Independent primary record:
`/tmp/m7-recovery-admission-independent-20261112/repaired-6972/review.private.json`.
