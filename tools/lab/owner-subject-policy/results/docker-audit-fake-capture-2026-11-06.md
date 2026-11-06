# Nested Docker audit — fake-backend capture, 2026-11-06

Source: `37242d950e79972fa512db8ff72fa1a049ad6d87`, additive lab files only.
Application source remains `3106f14d5b718e27e2a179e2d637f0d06c0642c8`.
No Docker service was started; C remains on coordinator HOLD. This capture does
not establish Docker runtime cleanup or application acceptance.

The shim records only returned full container IDs, Mount volume names and removal
state in a caller-provided private directory. Augmented removal uses the resolved
full IDs, avoiding a name-reuse race. Initial ID ownership is recorded before
inspection, and unsuccessful compensation retains/reports unresolved ownership.
Named volumes are preserved by Docker's `rm --volumes` contract; there is no direct
volume delete or global enumeration. Unsupported or mixed ownership commands pass
through unchanged, so the shim is not an arbitrary Docker permission boundary.

Root executed actual source copied with `git show` into owned home-backed scratch;
its subprocess backend was a fake executable. The test backend models successful
create, name reuse after inspection, inspect failure, compensation failure and
failed create. It does not execute Docker.

| Reproduced check | Passing | Semantic failures |
|---|---:|---:|
| [Positive](37242d950-docker-fake-positive.tap) | 9 | 0 |
| [Remove all-target ownership guard](37242d950-docker-fake-ownership.tap) | 7 | 2 |
| [Revert removal to mutable original names](37242d950-docker-fake-immutable_id.tap) | 7 | 2 |
| [Suppress unresolved compensation identity](37242d950-docker-fake-compensation.tap) | 8 | 1 |
| [Fresh restored source](37242d950-docker-fake-restored.tap) | 9 | 0 |

[Machine summary](37242d950-docker-fake-summary.json) names the exact source and
records. Each mutation ran separately in scratch, and failures were assertions,
not process setup. Default-sandbox subprocess execution initially returned EPERM;
those attempted process checks were invalid setup. The captured runs used approved
child-process execution. Initial read-only review found the mutable-name race and
missing failure ownership record; the captured source corrects both. Actual revised
source review is separate from these measurements.

Nonzero create/run without a returned ID cannot prove partial-resource ownership;
no leak-free claim applies to that case. Foreground/short-lived run and unsupported
CLI combinations are not general transparency proof. Successful detached test
services are the supported creation path. Actual runtime smoke, real volume
absence and reuse during the C application campaigns remain UNMEASURED.

Independent corrected-source review at exact37242d950 found no further actionable
finding within this bounded helper and separately reproduced 9 passing fake cases.
Atomic replacement does not establish crash-durable or transactional multi-command
auditing. Raw negative TAP assertion formatting includes trailing whitespace;
`git diff --check` reports it in the three negative `.tap` files. Captured bytes
remain unchanged. Source, Markdown and JSON diff-check passes.
