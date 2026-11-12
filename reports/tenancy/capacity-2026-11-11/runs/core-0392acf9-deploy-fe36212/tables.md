### Startup (cold deploy; s from `compose up`)

| run | N | load at deploy | api listener / healthy / drained | realtime listener / healthy / drained | evaluator healthy / drained | first served (3 tenants) |
| --- | --- | --- | --- | --- | --- | --- |
| ctl | 1,000 | 2.47 | 1.3 / 5.9 / 28.8 | 3.7 / 6 / 24.7 | 17.3 / 11.8 | 5.7, 6.6, 6.6 |
| r1 | 1,000 | 1.05 | 1.3 / 5.8 / 28.1 | 3.7 / 5.9 / 24.1 | 15 / 11.6 | 5.6, 6.5, 6.5 |
| r2 | 1,000 | 2.64 | 1.3 / 5.8 / 28.8 | 3.7 / 6 / 24.8 | 17.3 / 11.8 | 5.7, 6.5, 6.5 |
| r3 | 1,000 | 2.56 | 1.2 / 5.8 / 29.8 | 3.7 / 5.9 / 25.5 | 17.3 / 11.9 | 5.7, 6.5, 6.5 |

### Idle (no clients): CPU-ms per tenant-minute, memory (anon MiB), DB

| run | N | load (mean of 2 s samples) | api | realtime | evaluator | tenant-admin | postgres | nginx | DB-ms / tenant-min | backends (max) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ctl | 1,000 | 2.5 | 3.63 (721) | 5.3 (187) | 7.86 (370) | 2.9 (46) | 29.58 (13) | 0.01 (10) | 12.63 | 41 |
| r1 | 1,000 | 1.7 | 3.63 (720) | 5.34 (188) | 7.93 (381) | 2.88 (53) | 29.92 (37) | 0.01 (10) | 12.81 | 38 |
| r2 | 1,000 | 1.9 | 3.65 (708) | 5.25 (199) | 7.79 (395) | 2.92 (46) | 29.81 (12) | 0.01 (10) | 12.79 | 41 |
| r3 | 1,000 | 2.1 | 3.62 (714) | 5.33 (191) | 7.85 (379) | 2.89 (47) | 29.72 (12) | 0.01 (10) | 12.7 | 40 |

### Real cadence (k6 + 2 sockets per tenant + probe writes): CPU-ms per tenant-minute, memory (anon MiB), DB

| run | N | load (mean of 2 s samples) | api | realtime | evaluator | tenant-admin | postgres | nginx | DB-ms / tenant-min | backends (max) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ctl | 1,000 | 6.7 | 50.55 (2,512) | 24.76 (292) | 11.68 (379) | 3.61 (45) | 232.09 (123) | 2.39 (38) | 96.31 | 53 |
| r1 | 1,000 | 7.9 | 50.45 (2,512) | 25.46 (314) | 11.82 (381) | 3.56 (66) | 233.23 (123) | 2.32 (38) | 96.56 | 49 |
| r2 | 1,000 | 6.9 | 50.2 (2,510) | 25.76 (286) | 11.4 (380) | 3.59 (46) | 230.36 (125) | 2.33 (38) | 96.21 | 46 |
| r3 | 1,000 | 6.7 | 50.39 (2,517) | 26.02 (313) | 11.68 (379) | 3.51 (65) | 231.82 (123) | 2.33 (38) | 96.35 | 49 |

### HTTP p50 / p95 / p99 ms (k6, real cadence, through nginx)

| run | N | POST v1 entries | GET v1 sgv | GET v1 status | failed rate (max over shapes) | dropped iterations |
| --- | --- | --- | --- | --- | --- | --- |
| ctl | 1,000 | 242 / 514 / 690 | 209 / 482 / 668 | 329 / 622 / 770 | 0 | 0 |
| r1 | 1,000 | 252 / 595 / 833 | 220 / 574 / 832 | 345 / 706 / 977 | 0 | 0 |
| r2 | 1,000 | 237 / 505 / 745 | 198 / 468 / 737 | 316 / 616 / 921 | 0 | 0 |
| r3 | 1,000 | 244 / 517 / 629 | 206 / 480 / 609 | 320 / 616 / 723 | 0 | 0 |

### Latency to frame and to evaluation (probe writes), oracle

| run | N | sockets primed | write→frame p50/p95/p99 ms | frames delivered | write→evaluation p50/p95/p99 ms | not evaluated in 120 s | oracle |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ctl | 1,000 | 2000/2000 in 15 s | 1,027 / 1,119 / 1,152 | 604/604 | 1,023 / 1,995 / 2,375 | 0 | GREEN (6001 = 6001) |
| r1 | 1,000 | 2000/2000 in 14 s | 450 / 1,490 / 1,536 | 604/604 | 1,277 / 1,994 / 2,725 | 0 | GREEN (6001 = 6001) |
| r2 | 1,000 | 2000/2000 in 14.2 s | 1,042 / 1,146 / 1,193 | 604/604 | 972 / 2,002 / 2,466 | 0 | GREEN (6001 = 6001) |
| r3 | 1,000 | 2000/2000 in 14.3 s | 798 / 886 / 946 | 604/604 | 1,102 / 1,740 / 1,869 | 0 | GREEN (6002 = 6002) |

### Full restart (4 roles; edge sampled, then nginx restarted: labelled variant)

| run | N | restart cmd s | edge after role restart | nginx restart at / cmd s | healthy api / realtime / evaluator s (probe saw) | evaluator healthcheck first pass s | first served s (3) | eval gap p50 / p90 / max s | evaluated ≤60 s / ≤300 s / all | stock sockets | stock all-recovered s | retry flood |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ctl | 1,000 | 0.9 | 502,502,502 | 6.9 / 1.2 | 3.3 / 3.3 / 12.8 | not recorded | 8.3, 9.2, 9.2 | 22.5 / 30.6 / 72.6 | 925 / 1000 / 1000 | 2000/2000 | 110.3 | 2000/2000 in 0 s |
| r1 | 1,000 | 1.1 | 401,0,0 | 19.9 / 11.1 | 5.2 / 5.2 / 14.7 | not recorded | 2.6, 39.7, 41.6 | 31 / 72.2 / 74.9 | 865 / 1000 / 1000 | 2000/2000 | 171.8 | 2000/2000 in 0 s |
| r2 | 1,000 | 0.9 | 401,503,0 | 18.8 / 11.3 | 3.1 / 5.1 / 14.7 | not recorded | 2.8, 41, 37.1 | 30.1 / 72.6 / 73.9 | 880 / 1000 / 1000 | 2000/2000 | 149.6 | 2000/2000 in 0 s |
| r3 | 1,000 | 0.9 | 401,401,401 | 7.7 / 1.1 | 3.2 / 3.2 / 12 | not recorded | 2.4, 3.1, 2.8 | 21.6 / 29.8 / 72.7 | 948 / 1000 / 1000 | 2000/2000 | 129.1 | 2000/2000 in 0 s |

### Realtime after the full restart (instrument DIAG, 1 s; times from the restart command)

| run | N | TENANT_WARM_FAILED alerts | failed peak | warm drained line | all startup-ready s | all runtime-healthy s | failed (first / last seen) s | socket refreshes / failures at +60 s | primed at +60 s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ctl | 1,000 | 518 | 255 | ready 992 failed 5 deferred 0 after 107682 ms | 110.8 | 110.8 | 2.5 / 109.8 | 968 / 704 | 135 |
| r1 | 1,000 | 632 | 384 | ready 611 failed 384 deferred 0 after 133448 ms | 172.3 | 172.3 | 2.6 / 171.3 | 113 / 0 | 135 |
| r2 | 1,000 | 627 | 405 | ready 602 failed 394 deferred 0 after 111514 ms | 149.7 | 149.7 | 2.5 / 148.7 | 144 / 0 | 153 |
| r3 | 1,000 | 755 | 546 | ready 447 failed 543 deferred 0 after 88782 ms | 127.8 | 129.8 | 2.5 / 126.8 | 63 / 0 | 124 |

### Alert codes after the full restart, per role (log lines; startup health() causes where instrumented)

| run | N | api log codes | api warm drained | api failed peak (causes) | realtime log codes | realtime warm drained | realtime failed peak (causes) | realtime all ready s | evaluator log codes | realtime /health after |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ctl | 1,000 | TENANT_WARM_FAILED ×7 | ready 1000 failed 0 deferred 0 after 103987 ms | not instrumented | TENANT_WARM_FAILED ×518 | ready 992 failed 5 deferred 0 after 107682 ms | 255 | 110.8 | none | not captured |
| r1 | 1,000 | TENANT_WARM_FAILED ×8; TENANT_COLD_BEYOND_BOUND ×816 | ready 1000 failed 0 deferred 0 after 140113 ms | not instrumented | TENANT_WARM_FAILED ×632; TENANT_COLD_BEYOND_BOUND ×640 | ready 611 failed 384 deferred 0 after 133448 ms | 384 | 172.3 | none | not captured |
| r2 | 1,000 | TENANT_WARM_FAILED ×5 | ready 1000 failed 0 deferred 0 after 116930 ms | not instrumented | TENANT_WARM_FAILED ×627; TENANT_COLD_BEYOND_BOUND ×285 | ready 602 failed 394 deferred 0 after 111514 ms | 405 | 149.7 | none | not captured |
| r3 | 1,000 | TENANT_WARM_FAILED ×6 | ready 1000 failed 0 deferred 0 after 94567 ms | not instrumented | TENANT_WARM_FAILED ×755; TENANT_COLD_BEYOND_BOUND ×71 | ready 447 failed 543 deferred 0 after 88782 ms | 546 | 127.8 | none | not captured |

### Realtime whole-file config reads (instrument; per second of window)

| run | N | phase | readCurrent calls/s | ms per call | readAll calls/s | ms per call | read ms/s | realtime CPU ms/s | share of realtime CPU |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |

### Sockets after the full restart: stock clients, server disconnects, realtime authorize pressure

| run | N | stock recovered (no client retry) | server disconnects after restart (client-seen) | disconnects by 5 s from restart | realtime sockets min after +30 s | authorize in flight (max) | recheckFailures (end) | retry flood |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ctl | 1,000 | 2000/2000 by 110.3 s | not recorded | – | 2,000 | 996 | 0 | 2000/2000 in 0 s |
| r1 | 1,000 | 2000/2000 by 171.8 s | not recorded | – | 908 | 1,072 | 0 | 2000/2000 in 0 s |
| r2 | 1,000 | 2000/2000 by 149.6 s | not recorded | – | 769 | 1,076 | 0 | 2000/2000 in 0 s |
| r3 | 1,000 | 2000/2000 by 129.1 s | not recorded | – | 2,000 | 1,021 | 0 | 2000/2000 in 0 s |
