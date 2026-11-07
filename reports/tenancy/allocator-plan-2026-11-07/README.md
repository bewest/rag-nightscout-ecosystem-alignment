# Existing-allocator advisory planner: bounded native evidence

*Retained reproduced prototype measurement, 2026-11-07. App
`df7215ac4abfc2ce16514db584d745429c787e02`, tree
`9255ae114ac54cf804a60f22b5784740241acfca`; PostgreSQL 16.15.
[Observations](observations.json), [exact instrument](instrument.cjs),
[closure](closure.json). The subsequent [tenant-local insertion decision](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#tenant-local-insertion-semantics)
owns target architecture; this remains evidence of a read-only approach, not a
requirement to integrate global-allocator maintenance.*

The source adds `planAllocatorPreservingImport`, which returns a frozen advisory
record with `authorized:false`. It does not insert, authorize restoration or
remove the old identity-bearing import refusal. Unit planner/lifecycle checks
passed in root's focused run; the first root invocation omitted NODE_ENV=test
and stopped at the test safety precheck before any test. The corrected explicit
test invocation passed. Agent-authored floor/setter source controls fail their
intended assertions and pristine restoration passes; their private captures remain.

The native instrument applies the exact entries catalogue/ledger, exports actual
A through lifecycle, deletes A using fixture operator authority, then invokes the
real planner on a separate NOSUPERUSER/NOBYPASSRLS SELECT-only tenant-bound role.
It has table SELECT and sequence SELECT, with no sequence USAGE/UPDATE or table
writes. Covered floor returns advisory true/authorized false. A valid higher-floor
artifact refuses `LIFECYCLE_ALLOCATOR_FLOOR_UNCOVERED`; an owner-applied setter
privilege refuses `LIFECYCLE_ALLOCATOR_ROLE_UNSAFE`; CACHE8 fixture configuration
refuses `LIFECYCLE_ALLOCATOR_SEMANTICS_UNSUPPORTED`. Fresh ordinary plans pass after
each privilege/configuration restoration. Original importer still refuses
`LIFECYCLE_IDENTITY_IMPORT_UNSUPPORTED`.

Every attempt compares all-tenant rows, migration ledger, raw sequence state
including log_cnt, and sequence metadata before/after; the planner changes none.
Private owner mutations are control setup outside those no-effect windows, not
attributed to planner execution. B's current stored row remains exact.

Final child exit0, exact owned container/volume absent, and complete baseline
container/volume inventory unchanged are retained. Root independently verifies
frozen instrument/parent hashes, clean source and current exact resource absence.
Instrument SHA256
`8d4efe741a05a84a33b95d4a0d14b4c5b7f6929ec64073af1dd4993ea7124105`.
Private capability/finite-parent capture:
`externals/work/m6-allocator-planner-native-20261107/`.

Scope is entries-only advisory SQL metadata and ACL proof. Observations can stale
immediately: they are not a restore lease, actor authority, serving fence, runtime
permission audit of all workers, or M6 admission. No full/browser acceptance ran;
coherent application integration still owns that boundary. No source publication,
default change, privileged setter or shared pause is enabled.
