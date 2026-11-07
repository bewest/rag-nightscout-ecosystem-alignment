# Batch A comprehensive acceptance

Reproduced on `74d7b3fc25c7e3c496c438847c95e89ec7fe6061`; official/dev
`4a482627bfdafb1fef8dcbe0ac6c484811cae563` remains included. Final prcheck passed,
head unchanged and clean. Runtime released; every phase's exact owned resources
and child processes independently verified absent, unknown baseline preserved.

| measurement | actual result |
|---|---:|
| affected resend/payload/clock source files with actual private Mongo | 46 passing, zero pending/failing |
| full nonbrowser | 7,320 passing, 132 pending, zero failing |
| browser, 41 files | 684 passing, zero pending/failing |
| all 40 enabled multitenant suites | 495 passing, one benchmark pending, zero failing |
| source / inventory | 527 files / eight tiers; 40 suites / 23 owning containers |
| lint | zero errors, 29 warnings |

G1/G2 and whitespace passed. Performance remains unmeasured. Counts overlap and
must not be summed. The full suite's ordinary opt-out pending cases are distinct
from the required enabled-corpus run.

Actual default cgmsim/oref0 gate (82 checks, 19 paired cells, zero differences),
fresh affected pooler proof (nine connection/RLS plus four typed identity and
embedded real controls), and M1/M2 semantic native captures executed on `7015fbae`.
They retain that attribution: complete tracked comparison to `74d7b3fc` changes
only one existing assertion file, with 1,777 other tracked blobs identical;
product, dependency inputs, fixtures and relevant instruments are unchanged.
No accepted native/client/pooler campaign was replayed for the test-only change.

The original `7015fbae` full run is preserved: three strict settle-event expected
objects omitted adopted `tenant: null` and `stamp: null`. The root's two-line
TEST-ONLY repair retains exact equality and all existing WriteResult, frozen,
no-write and stored-state assertions. The repaired full passed. One later audit
setup stop omitted the existing runner-manifest argument; exact IDs/images/volumes
were independently matched and the unchanged audit helper's supported manifest
allowlist completed cleanup. No product change or test rerun followed that stop.

This is bounded Batch A acceptance, not release or a claim of complete M0-M6
operational readiness. Root owns programme records, promotion and publication.
