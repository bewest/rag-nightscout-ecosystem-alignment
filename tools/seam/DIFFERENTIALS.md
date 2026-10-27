# Storage-interface differentials

*Contributor-facing.* Three checks used to gate ST-FILTER and ST-READS (next-gen plan §5.1, queue item
`ST-FILTER-READS`). Each one takes a cgm-remote-monitor worktree and a MongoDB URI, and treats a live
`mongod` as the authority. Install `mingo` first with `npm ci` in this directory; it is never added to
cgm-remote-monitor's `package.json`.

| script | compares | measured on `feat/storage-filter` (2026-10-26) |
|---|---|---|
| `filter-differential.js <crm> <uri> [n] [seed]` | a MongoDB query document against `toMongo(fromMongo(f))` from `lib/storage/filter.js`, as result sets on `mongod`, plus refusals: wherever `mongod` refuses `f`, the bridge must refuse too. A `mingo` arm is reported separately as an oracle check. | `50172510`: 5,467/5,467 (seed 20261026) and 11,467/11,467 (seed 777), 0 unexpected rejections or acceptances |
| `v1-read-differential.js <crm> <uri> [n] [seed]` | for real API v1 query strings, the document dev's driver path sends (`query.js` and each module's wrappers, entries' pattern routes, the treatment fallback key) against the branch's interface path (`lib/server/storage-reads.js`), as returned ids in order or the same `mongod` error | `b752971c`: 2,954/2,954, 860 of them the same `mongod` error, 28,998 documents compared |
| `v1-http-differential.js <dev tree> <branch tree> <uri> [outDir]` | 700 API v1 GET requests answered by two trees over identically seeded databases: status, content type and body (Express's HTML 500 page compared on its first line, since its stack trace names file paths) | `b752971c` against dev `7ad3a67f`: 700/700 identical (550 × 200, 61 × 400, 89 × 500) |

`probe-mongod.js <crm> <uri>` prints how `mongod` answers the edge shapes the filter tree pins (`$exists`
operands, regex flags as js-bson sends them, `$options` letters).

**Non-vacuity.** Two first runs were vacuous and were caught only by reading the outcome mix:
681 of 700 HTTP requests were 404s because the harness mounted the API at the wrong path, and the
read differential dated its documents from a fixed clock, so `query.js`'s default date window
excluded most of them. Read the status mix and the document count before reading "0 mismatches".
The older `roundtrip.js` (a `mingo`-only round trip) passed 4,000/4,000 on the September `filter.js`,
which `filter-differential.js` fails on 60 of 4,000; use it only alongside the `mongod` check.
