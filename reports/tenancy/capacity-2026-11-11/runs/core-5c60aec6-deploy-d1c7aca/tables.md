### Startup (cold deploy; s from `compose up`)

| run | N | load at deploy | api listener / healthy / drained | realtime listener / healthy / drained | evaluator healthy / drained | first served (3 tenants) |
| --- | --- | --- | --- | --- | --- | --- |
| b2 | 1,000 | 2.60 | 1.3 / 5.8 / 28.6 | 3.8 / 6 / 28.7 | 15.1 / 11.8 | 5.7, 6.6, 6.6 |
| b3 | 1,000 | 1.12 | 1.2 / 5.8 / 28.1 | 3.7 / 5.9 / 28.2 | 15 / 11.6 | 5.7, 6.6, 6.6 |
| b4 | 1,000 | 2.85 | 1.2 / 5.8 / 28.4 | 3.7 / 6 / 28.5 | 15 / 11.8 | 5.7, 6.8, 6.6 |
| r1 | 3,000 | 2.82 | 1.7 / 5.9 / 96.6 | 3.9 / 6 / 96.7 | 29.6 / 21.9 | 5.7, 6.6, 6.7 |
| x1 | 3,000 | 1.25 | 1.7 / 5.8 / 97.1 | 3.9 / 5.9 / 97.2 | 29.5 / 21.5 | 5.6, 6.5, 6.5 |
| x2 | 3,000 | 2.67 | 1.7 / 5.8 / 96.9 | 3.9 / 5.9 / 97 | 29.6 / 21.7 | 5.7, 6.6, 6.6 |
| x3 | 3,000 | 2.74 | 1.7 / 5.8 / 96 | 3.9 / 6 / 96.2 | 29.6 / 21.7 | 5.7, 6.6, 6.6 |

### Idle (no clients): CPU-ms per tenant-minute, memory (anon MiB), DB

| run | N | load (mean of 2 s samples) | api | realtime | evaluator | tenant-admin | postgres | nginx | DB-ms / tenant-min | backends (max) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| b2 | 1,000 | 1.9 | 3.15 (719) | 5.38 (181) | 7.85 (392) | 2.87 (44) | 28.38 (14) | 0.01 (10) | 12.13 | 47 |
| b3 | 1,000 | 2.3 | 3.18 (716) | 5.41 (163) | 7.89 (411) | 2.87 (44) | 28.43 (39) | 0.01 (10) | 12.22 | 47 |
| b4 | 1,000 | 2.2 | 3.49 (717) | 5.66 (169) | 7.99 (403) | 2.89 (47) | 28.93 (14) | 0.01 (10) | 12.35 | 44 |
| r1 | 3,000 | 4.2 | 2.15 (1,980) | 5.51 (257) | 10.72 (948) | 1.85 (47) | 29.57 (62) | 0 (10) | 13.03 | 44 |
| x1 | 3,000 | 3.6 | 2.46 (1,938) | 5.44 (222) | 10.88 (745) | 1.88 (51) | 28.15 (60) | 0 (12) | 12.54 | 44 |
| x2 | 3,000 | 4.1 | 2.46 (1,922) | 5.61 (218) | 10.93 (748) | 1.88 (49) | 27.92 (61) | 0 (10) | 12.53 | 43 |
| x3 | 3,000 | 4.7 | 2.46 (1,945) | 5.08 (253) | 11.07 (720) | 1.86 (48) | 27.36 (63) | 0 (10) | 12.23 | 44 |

### Real cadence (k6 + 2 sockets per tenant + probe writes): CPU-ms per tenant-minute, memory (anon MiB), DB

| run | N | load (mean of 2 s samples) | api | realtime | evaluator | tenant-admin | postgres | nginx | DB-ms / tenant-min | backends (max) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| b2 | 1,000 | 7.2 | 50.74 (2,512) | 29.73 (284) | 11.9 (379) | 3.64 (47) | 234.21 (125) | 2.37 (38) | 97.46 | 54 |
| b3 | 1,000 | 6.6 | 51.04 (2,509) | 29.77 (288) | 11.8 (379) | 3.64 (46) | 234.24 (123) | 2.36 (39) | 97.48 | 54 |
| b4 | 1,000 | 8 | 52.21 (2,539) | 30.22 (298) | 12.4 (379) | 3.8 (47) | 240.8 (124) | 2.43 (38) | 99.67 | 49 |
| r1 | 3,000 | 16.1 | 89.27 (2,363) | 47.25 (491) | 14.53 (743) | 2.93 (48) | 31.8 (75) | 5.78 (96) | 15.42 | 53 |
| x1 | 3,000 | 8 | 19.18 (3,134) | 8.28 (267) | 12.68 (809) | 2.45 (49) | 89.72 (62) | 0.45 (11) | 37.79 | 53 |
| x2 | 3,000 | 15.8 | 90.93 (2,316) | 47.21 (535) | 14.47 (805) | 2.94 (48) | 36.2 (74) | 6.88 (97) | 17.2 | 52 |
| x3 | 3,000 | 19 | 88.35 (2,282) | 46.55 (532) | 14.84 (823) | 2.97 (48) | 36.75 (134) | 6.58 (97) | 17.85 | 74 |

### HTTP p50 / p95 / p99 ms (k6, real cadence, through nginx)

| run | N | POST v1 entries | GET v1 sgv | GET v1 status | failed rate (max over shapes) | dropped iterations |
| --- | --- | --- | --- | --- | --- | --- |
| b2 | 1,000 | 251 / 561 / 802 | 223 / 542 / 776 | 352 / 678 / 930 | 0 | 0 |
| b3 | 1,000 | 246 / 493 / 604 | 212 / 460 / 595 | 330 / 600 / 728 | 0 | 0 |
| b4 | 1,000 | 268 / 1,044 / 1,566 | 292 / 1,087 / 1,616 | 428 / 1,235 / 1,754 | 0 | 0 |
| r1 | 3,000 | 10,239 / 14,009 / 15,005 | 10,252 / 13,861 / 14,964 | 10,239 / 13,958 / 15,013 | 0.999 | 1,579 |
| x1 | 3,000 | 5,004 / 5,252 / 5,330 | 5,003 / 5,238 / 5,319 | 5,005 / 5,366 / 5,462 | 0.782 | 456 |
| x3 | 3,000 | 10,235 / 13,848 / 14,921 | 10,252 / 13,825 / 14,915 | 10,242 / 13,905 / 14,949 | 1 | 1,590 |

### Latency to frame and to evaluation (probe writes), oracle

| run | N | sockets primed | write→frame p50/p95/p99 ms | frames delivered | write→evaluation p50/p95/p99 ms | not evaluated in 120 s | oracle |
| --- | --- | --- | --- | --- | --- | --- | --- |
| b2 | 1,000 | 2000/2000 in 13.8 s | 604 / 1,570 / 1,684 | 604/604 | 1,470 / 2,010 / 2,095 | 0 | GREEN (6002 = 6002) |
| b3 | 1,000 | 2000/2000 in 14 s | 634 / 756 / 1,628 | 604/604 | 1,301 / 1,921 / 2,042 | 0 | GREEN (6002 = 6002) |
| b4 | 1,000 | 2000/2000 in 14.5 s | 492 / 1,540 / 2,409 | 604/604 | 1,738 / 2,288 / 3,041 | 0 | GREEN (6002 = 6002) |
| r1 | 3,000 | 134/6000 in 300.2 s | – / – / – | 0/616 | – / – / – | 0 | GREEN (33 = 33) |
| x1 | 3,000 | 0/0 in 0 s | – / – / – | 0/0 | 6,497 / 14,613 / 47,085 | 0 | GREEN (3035 = 3035) |
| x2 | 3,000 | 128/6000 in 300.1 s | – / – / – | 0/396 | 5,983 / 5,983 / 5,983 | 0 | – |
| x3 | 3,000 | 138/6000 in 300.1 s | – / – / – | 0/418 | – / – / – | 0 | GREEN (16 = 16) |

### Full restart (4 roles; edge sampled, then nginx restarted: labelled variant)

| run | N | restart cmd s | edge after role restart | nginx restart at / cmd s | healthy api / realtime / evaluator s (probe saw) | evaluator healthcheck first pass s | first served s (3) | eval gap p50 / p90 / max s | evaluated ≤60 s / ≤300 s / all | stock sockets | stock all-recovered s | retry flood |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| b2 | 1,000 | 0.9 | 401,401,0 | 13.2 / 11.2 | 3.2 / 3.2 / 26.1 | not recorded | 2.5, 2.8, 2.8 | 73.3 / 80.1 / 81.4 | 444 / 1000 / 1000 | 2000/2000 | 95 | 2000/2000 in 0 s |
| b3 | 1,000 | 0.8 | 502,502,401 | 9.6 / 11.2 | 3.1 / 2.9 / 13.7 | 13.5 | 5.6, 64.6, 74.9 | 24.4 / 32.8 / 73.7 | 926 / 1000 / 1000 | 1501/2000 | – | 2000/2000 in 6.3 s |
| b4 | 1,000 | 0.9 | 401,0,0 | 17.2 / 11.3 | 3.2 / 3.8 / 13.7 | 13.5 | 2.3, 88.1, 153.8 | 24.2 / 72.3 / 73.6 | 890 / 1000 / 1000 | 2000/2000 | 209.5 | 2000/2000 in 0 s |
| r1 | 3,000 | 10.8 | 401,401,401 | 19 / 11.7 | 10.9 / 14.6 / 34 | 33.8 | 10.9, 10.9, 10.9 | 71.6 / 115.1 / 133.6 | 1028 / 3000 / 3000 | 0/6000 | – | 0/6000 |
| x1 | 3,000 | 0.8 | 503,401,401 | 7.4 / 0.8 | 3.3 / 3.1 / 26.4 | 26.4 | 3.3, 3.6, 3.6 | 54.1 / 79.6 / 86.3 | 1816 / 3000 / 3000 | 0/0 | 8.2 | 0/0 in 0 s |
| x2 | 3,000 | 10.8 | 401,401,401 | 19.8 / 11.7 | 10.9 / 27 / 33.8 | 33.8 | 11, 11, 11 | 70.7 / 114 / 130 | 1077 / 3000 / 3000 | 0/6000 | – | 0/6000 |
| x3 | 3,000 | 10.8 | 401,401,401 | 21.7 / 11.9 | 11.2 / 26.3 / 40.6 | 40.5 | 11.2, 10.8, 10.9 | 96.1 / 181.7 / 209.8 | 556 / 3000 / 3000 | 0/6000 | – | 0/6000 |

### Realtime after the full restart (instrument DIAG, 1 s; times from the restart command)

| run | N | TENANT_WARM_FAILED alerts | failed peak | warm drained line | all startup-ready s | all runtime-healthy s | failed (first / last seen) s | socket refreshes / failures at +60 s | primed at +60 s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| b2 | 1,000 | 29 | 1 | ready 1000 failed 0 deferred 0 after 82227 ms | 83.8 | 95.8 | 19.5 / 46.8 | 312 / 0 | 321 |
| b3 | 1,000 | 0 | 0 | ready 1000 failed 0 deferred 0 after 118782 ms | 120.6 | 149.6 | – / – | 115 / 0 | 149 |
| b4 | 1,000 | 171 | 7 | ready 1000 failed 0 deferred 0 after 191417 ms | 193 | 210 | 17.6 / 181 | 4 / 0 | 0 |
| r1 | 3,000 | 375 | 14 |  | – | – | 55.6 / 421.3 | 13 / 0 | 2 |
| x1 | 3,000 | 0 | 0 |  | – | – | – / – | 0 / 0 | 0 |
| x2 | 3,000 | 370 | 15 |  | – | – | 63 / 421 | 15 / 0 | 5 |
| x3 | 3,000 | 300 | 4 |  | – | – | 120.1 / 421.7 | 21 / 0 | 7 |

### Alert codes after the full restart, per role (log lines; startup health() causes where instrumented)

| run | N | api log codes | api warm drained | api failed peak (causes) | realtime log codes | realtime warm drained | realtime failed peak (causes) | realtime all ready s | evaluator log codes | realtime /health after |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| b2 | 1,000 | TENANT_WARM_FAILED ×4 | ready 1000 failed 0 deferred 0 after 74864 ms | 4 (TENANT_WARM_FAILED:TENANT_WARM_FAILED ×4) | TENANT_WARM_FAILED ×1 | ready 1000 failed 0 deferred 0 after 82227 ms | 1 (TENANT_WARM_FAILED:TENANT_WARM_FAILED ×1) | 83.8 | none | 200 healthy 1000/1000 failed 0 |
| b3 | 1,000 | TENANT_WARM_FAILED ×8 | ready 999 failed 1 deferred 0 after 111510 ms; ready 1000 failed 0 deferred 0 after 115408 ms | 8 (TENANT_WARM_FAILED:TENANT_WARM_FAILED ×8) | none | ready 1000 failed 0 deferred 0 after 118782 ms | 0 | 120.6 | none | 200 healthy 1000/1000 failed 0 |
| b4 | 1,000 | TENANT_WARM_FAILED ×13; TENANT_COLD_BEYOND_BOUND ×1418 | ready 1000 failed 0 deferred 0 after 180874 ms | 13 (TENANT_WARM_FAILED:TENANT_WARM_FAILED ×13) | TENANT_WARM_FAILED ×7; TENANT_COLD_BEYOND_BOUND ×910 | ready 1000 failed 0 deferred 0 after 191417 ms | 7 (TENANT_WARM_FAILED:TENANT_WARM_FAILED ×7) | 193 | none | 200 healthy 1000/1000 failed 0 |
| r1 | 3,000 | TENANT_WARM_FAILED ×94; TENANT_COLD_BEYOND_BOUND ×5550 |  | 89 (TENANT_COLD_BEYOND_BOUND ×2416; TENANT_COLD_BEYOND_BOUND:TENANT_WARM_FAILED ×89; TENANT_WARM_FAILED:TENANT_WARM_FAILED ×89) | TENANT_WARM_FAILED ×14; TENANT_COLD_BEYOND_BOUND ×2905 |  | 14 (TENANT_WARM_FAILED:TENANT_WARM_FAILED ×14; TENANT_COLD_BEYOND_BOUND:TENANT_WARM_FAILED ×14; TENANT_COLD_BEYOND_BOUND ×2861) | – | eval EVALUATOR_NOT_EVALUATED_WITHIN_BOUND ×749 | 200 healthy 74/3000 failed 1 |
| x1 | 3,000 | none |  | 0 | none |  | 0 | – | none | 200 healthy 340/3000 failed 0 |
| x2 | 3,000 | TENANT_WARM_FAILED ×110; TENANT_COLD_BEYOND_BOUND ×5560 |  | 105 (TENANT_COLD_BEYOND_BOUND ×2446; TENANT_COLD_BEYOND_BOUND:TENANT_WARM_FAILED ×105; TENANT_WARM_FAILED:TENANT_WARM_FAILED ×105) | TENANT_WARM_FAILED ×17; TENANT_COLD_BEYOND_BOUND ×2908 |  | 15 (TENANT_WARM_FAILED:TENANT_WARM_FAILED ×16; TENANT_COLD_BEYOND_BOUND:TENANT_WARM_FAILED ×16; TENANT_COLD_BEYOND_BOUND ×2869) | – | eval EVALUATOR_NOT_EVALUATED_WITHIN_BOUND ×722 | 200 healthy 65/3000 failed 2 |
| x3 | 3,000 | TENANT_WARM_FAILED ×37; TENANT_COLD_BEYOND_BOUND ×5295 |  | 36 (TENANT_COLD_BEYOND_BOUND ×2307; TENANT_COLD_BEYOND_BOUND:TENANT_WARM_FAILED ×36; TENANT_WARM_FAILED:TENANT_WARM_FAILED ×36) | TENANT_WARM_FAILED ×4; TENANT_COLD_BEYOND_BOUND ×2878 |  | 4 (TENANT_COLD_BEYOND_BOUND:TENANT_WARM_FAILED ×4; TENANT_WARM_FAILED:TENANT_WARM_FAILED ×4; TENANT_COLD_BEYOND_BOUND ×2810) | – | eval EVALUATOR_NOT_EVALUATED_WITHIN_BOUND ×1403 | 200 healthy 148/3000 failed 0 |

### Realtime whole-file config reads (instrument; per second of window)

| run | N | phase | readCurrent calls/s | ms per call | readAll calls/s | ms per call | read ms/s | realtime CPU ms/s | share of realtime CPU |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| b2 | 1,000 | idle | 4.4 | 0.23 | 1 | 0.55 | 1.5 | 46.1 | 0.034 |
| b2 | 1,000 | load | 51.9 | 0.29 | 1 | 0.33 | 15.6 | 439.4 | 0.035 |
| b3 | 1,000 | idle | 4.5 | 0.23 | 1 | 0.54 | 1.5 | 46.2 | 0.034 |
| b3 | 1,000 | load | 54 | 0.29 | 1 | 0.33 | 16 | 440.2 | 0.036 |
| b4 | 1,000 | idle | 4.4 | 0.23 | 1 | 0.51 | 1.5 | 50.4 | 0.03 |
| b4 | 1,000 | load | 49.1 | 0.3 | 1 | 0.35 | 15.3 | 443.6 | 0.035 |
| r1 | 3,000 | idle | 12 | 0.63 | 1 | 0.78 | 8.4 | 205.8 | 0.041 |
| r1 | 3,000 | load | 184.8 | 1.14 | 1 | 1.17 | 212.3 | 2,314.1 | 0.092 |
| x1 | 3,000 | idle | 12 | 0.64 | 1 | 0.81 | 8.5 | 201.4 | 0.042 |
| x1 | 3,000 | load | 20.1 | 0.82 | 1 | 0.81 | 17.4 | 325.3 | 0.053 |
| x2 | 3,000 | idle | 12 | 0.65 | 1 | 0.78 | 8.6 | 210.4 | 0.041 |
| x2 | 3,000 | load | 184.9 | 1.1 | 0.7 | 1.12 | 203.3 | 2,313.2 | 0.088 |
| x3 | 3,000 | idle | 12 | 0.64 | 1 | 0.66 | 8.3 | 184 | 0.045 |
| x3 | 3,000 | load | 174.2 | 1.13 | 0.8 | 1.12 | 197.4 | 2,274 | 0.087 |

### Sockets after the full restart: stock clients, server disconnects, realtime authorize pressure

| run | N | stock recovered (no client retry) | server disconnects after restart (client-seen) | disconnects by 5 s from restart | realtime sockets min after +30 s | authorize in flight (max) | recheckFailures (end) | retry flood |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| b2 | 1,000 | 2000/2000 by 95 s | not recorded | – | 148 | 1,035 | 0 | 2000/2000 in 0 s |
| b3 | 1,000 | 1501/2000 | not recorded | – | 1,501 | 1,071 | 14 | 2000/2000 in 6.3 s |
| b4 | 1,000 | 2000/2000 by 209.5 s | 0 |  | 1,797 | 1,054 | 0 | 2000/2000 in 0 s |
| r1 | 3,000 | 0/6000 | 0 |  | 433 | 711 | 21 | 0/6000 |
| x1 | 3,000 | 0/0 by 8.2 s | 0 |  | 0 | 0 | 0 | 0/0 in 0 s |
| x2 | 3,000 | 0/6000 | 0 |  | 469 | 731 | 35 | 0/6000 |
| x3 | 3,000 | 0/6000 | 0 |  | 376 | 519 | 807 | 0/6000 |
