### Startup (cold deploy; s from `compose up`)

| run | N | load at deploy | api listener / healthy / drained | realtime listener / healthy / drained | evaluator healthy / drained | first served (3 tenants) |
| --- | --- | --- | --- | --- | --- | --- |
| b1 | 1,000 | 1.03 | 1.3 / 5.8 / 30.5 | 3.7 / 5.9 / 30.6 | 15 / 11.6 | 5.7, 6.6, 6.6 |

### Idle (no clients): CPU-ms per tenant-minute, memory (anon MiB), DB

| run | N | load (mean of 2 s samples) | api | realtime | evaluator | tenant-admin | postgres | nginx | DB-ms / tenant-min | backends (max) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| b1 | 1,000 | 2.1 | 3.27 (721) | 5.45 (178) | 8.06 (552) | 2.96 (44) | 28.47 (12) | 0.01 (10) | 12.24 | 48 |

### Real cadence (k6 + 2 sockets per tenant + probe writes): CPU-ms per tenant-minute, memory (anon MiB), DB

| run | N | load (mean of 2 s samples) | api | realtime | evaluator | tenant-admin | postgres | nginx | DB-ms / tenant-min | backends (max) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| b1 | 1,000 | 6.7 | 50.65 (2,518) | 28.47 (295) | 11.91 (391) | 3.69 (45) | 233.02 (125) | 2.36 (38) | 96.92 | 56 |

### HTTP p50 / p95 / p99 ms (k6, real cadence, through nginx)

| run | N | POST v1 entries | GET v1 sgv | GET v1 status | failed rate (max over shapes) | dropped iterations |
| --- | --- | --- | --- | --- | --- | --- |
| b1 | 1,000 | 246 / 559 / 759 | 217 / 544 / 727 | 344 / 677 / 879 | 0 | 0 |

### Latency to frame and to evaluation (probe writes), oracle

| run | N | sockets primed | write→frame p50/p95/p99 ms | frames delivered | write→evaluation p50/p95/p99 ms | not evaluated in 120 s | oracle |
| --- | --- | --- | --- | --- | --- | --- | --- |
| b1 | 1,000 | 2000/2000 in 14.1 s | 1,056 / 1,159 / 1,195 | 604/604 | 1,308 / 2,234 / 2,437 | 0 | GREEN (6002 = 6002) |

### Full restart (4 roles; edge sampled, then nginx restarted: labelled variant)

| run | N | restart cmd s | edge after role restart | nginx restart at / cmd s | healthy api / realtime / evaluator s (probe saw) | evaluator healthcheck first pass s | first served s (3) | eval gap p50 / p90 / max s | evaluated ≤60 s / ≤300 s / all | stock sockets | stock all-recovered s | retry flood |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| b1 | 1,000 | 0.9 | 502,401,0 | 13.9 / 11.3 | 3.1 / 3.1 / 25.2 | not recorded | 3.8, 4.2, 4.2 | 72.4 / 79.1 / 80.4 | 471 / 1000 / 1000 | 2000/2000 | 96.3 | 2000/2000 in 0 s |

### Realtime after the full restart (instrument DIAG, 1 s; times from the restart command)

| run | N | TENANT_WARM_FAILED alerts | failed peak | warm drained line | all startup-ready s | all runtime-healthy s | failed (first / last seen) s | socket refreshes / failures at +60 s | primed at +60 s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| b1 | 1,000 | 85 | 3 | ready 998 failed 2 deferred 0 after 81235 ms | 96.7 | 96.7 | 17.6 / 95.6 | 279 / 0 | 300 |

### Alert codes after the full restart, per role (log lines; startup health() causes where instrumented)

| run | N | api log codes | api warm drained | api failed peak (causes) | realtime log codes | realtime warm drained | realtime failed peak (causes) | realtime all ready s | evaluator log codes | realtime /health after |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| b1 | 1,000 | TENANT_WARM_FAILED ×6 | ready 998 failed 2 deferred 0 after 72595 ms; ready 999 failed 1 deferred 0 after 88319 ms; ready 1000 failed 0 deferred 0 after 90617 ms | 6 (TENANT_WARM_FAILED:TENANT_WARM_FAILED ×6) | TENANT_WARM_FAILED ×6 | ready 998 failed 2 deferred 0 after 81235 ms | 3 (TENANT_WARM_FAILED:TENANT_WARM_FAILED ×3) | 96.7 | none | 200 healthy 1000/1000 failed 0 |

### Realtime whole-file config reads (instrument; per second of window)

| run | N | phase | readCurrent calls/s | ms per call | readAll calls/s | ms per call | read ms/s | realtime CPU ms/s | share of realtime CPU |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| b1 | 1,000 | idle | 4.4 | 0.22 | 1 | 0.56 | 1.6 | 46.3 | 0.034 |
| b1 | 1,000 | load | 51.9 | 0.29 | 1 | 0.33 | 15.5 | 418.9 | 0.037 |

### Sockets after the full restart: stock clients, server disconnects, realtime authorize pressure

| run | N | stock recovered (no client retry) | server disconnects after restart (client-seen) | disconnects by 5 s from restart | realtime sockets min after +30 s | authorize in flight (max) | recheckFailures (end) | retry flood |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| b1 | 1,000 | 2000/2000 by 96.3 s | not recorded | – | 119 | 999 | 0 | 2000/2000 in 0 s |
