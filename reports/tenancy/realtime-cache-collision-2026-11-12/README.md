# Reproduced realtime configuration cache collision

Captured 2026-11-12 on actual Node v24.22.1, Linux 6.8.0-147-generic x64, ext4. This targeted diagnostic reproduces the remaining first-campaign cache failure; it is not repaired-source acceptance or capacity. Instrumented core `c32c853f9da8a04cc32badac222cdf9f30bc00a6` retains exact runtime blobs from `d5e2e874659155c952b5b5deb862f12f982ac02e`; probe SHA-256 `df3240a67ec9f3861e7365d886fc6d0a15cda38e74b065f5198ce7b905ce2177`. Remote runner `b2abd06848333aa9e21489883214009454af3980` is separately pinned.

## Witness and controls

The [same-key witness](same-key-witness.json) has identical device/inode/size/nanosecond modification and change times/mode/byte-limit keys before and after an actual same-size in-place write. Independent bytes change from `{"n":1}` to `{"n":2}`, but the cached reader returns 1. Raw reads return the new bytes. This is a reproduced stale read, not an inference from a kernel version or a flaky expectation.

| Probe | Raw in-place stale | Cached in-place stale | Cached atomic replacement stale |
|---|---:|---:|---:|
| [Normal before](normal-before.json.gz), 1000 iterations per mode | 0 | 771 | 0 |
| [Freeze-cache control](control.json.gz), 20 per mode | 0 | 20 | 20 |
| [Restored normal](normal-after.json.gz), 1000 per mode | 0 | 732 | 0 |

Normal cached in-place stale counts equal same-metadata counts. Atomic replacement changes identity and stays current in both normal batches; the deliberate frozen-cache control makes all 20 atomic reads stale and exits 3, demonstrating the detector can fail. Normal probes exit 2 for reproduced in-place stale reads. Both normal batches record zero unchanged full-file reads and zero unexpected parses. No timestamp sleeps, source patches or metadata adjustments occur. These observations do not establish universal filesystem behavior or select a repair.

Owned exact-lock dependency installation passed. The isolated cache suite passed eight cases; the paired cache/admission run reproduced 13 passing and one failing (`RT_PARSE_CHANGE`, returned 1 versus expected 2 at test line 108). Isolated success does not refute the stat-key witness. [Result](result.json.gz) correctly records targeted tests failed and acceptance/capacity not assessed.

[Provenance](provenance.json.gz) records runtime binary hashes, source, filesystem and sanitized environment keys. [Original capture hashes](original-artifacts.json) bind raw private logs; JSON captures are gzip-compressed without modifying their bytes. The probe lives at `tests/fixtures/realtime-cache-stat-probe.js` in the instrumented core.

```bash
node tests/fixtures/realtime-cache-stat-probe.js --iterations 1000 --unchanged 50 --out NEW_PRIVATE_BEFORE_JSON
node tests/fixtures/realtime-cache-stat-probe.js --control freeze-cache --iterations 20 --out NEW_PRIVATE_CONTROL_JSON
node tests/fixtures/realtime-cache-stat-probe.js --iterations 1000 --unchanged 50 --out NEW_PRIVATE_AFTER_JSON
node scripts/test-tiers.js run unit tests/realtime-config-cache.test.js
node scripts/test-tiers.js run unit tests/realtime-config-cache.test.js tests/socket-admission-cache.test.js
```

The remote owner retained checkpoint evidence and independently verified cloud teardown; no application traffic was generated. Local private home is `externals/work/perf-cloud-cache-20261112/cache-diagnostic-20261112-a`. Next boundary: audit actual publication/freshness contracts and writers, choose a mechanism-preserving repair with controls, join all planned repairs, then refreeze comprehensive acceptance. Adding delays to the test alone does not repair this mechanism.
