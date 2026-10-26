# MongoDB server compatibility matrix: driver 5.9.2 on `dev` and driver 7 on cut 3, servers 3.6 to 8.0

> **Snapshot, 2026-10-25, against `official/dev` `b29f1bf7` (driver `mongodb` 5.9.2) and cut 3 rebased onto 16.0.0, `wip/cut3-onto-16.0.0` `7b636ce6` (driver 7.7.0; local, not pushed), Node 22 (`node:22` container) for the integration tier. Current: the evidence for the maintainer's 2026-10-25 decision that 16.0.0 ships driver 7 and needs MongoDB 4.4 or newer to start. Contributor-facing. Current decisions: [16.0.0 decisions](../../../releases/cgm-remote-monitor-16.0.0/decisions.md) on `records/16.0.0-cuts-2510` (`b071dacfd`); defects: [backfix register](../../30-design/remedial/nightscout-backfix-register.md) BF-182.**

Session f4's mongo-matrix lane. Every figure below is from the lane's raw logs (boot summaries, the
driver-floor output and one integration log per cell), re-read for this note. Scripts:
[`tools/lab/mongo-server-matrix/`](../../../tools/lab/mongo-server-matrix/README.md).

## 1. Decision

**Maintainer, 2026-10-25:** driver 7 ships in 16.0.0 with cut 3. MongoDB 3.6, 4.0 and 4.2 are
dropped and 4.4 or newer is required to start; 5.0 through 8.0 stay the supported range. The BF-182
boot error page stays, worded with the server's version and the driver's minimum only. Recorded by
session -f8 in `releases/cgm-remote-monitor-16.0.0/decisions.md` (`b071dacfd`, on
`records/16.0.0-cuts-2510`, not yet on `main`).

## 2. Servers

Official `mongo` images, one container per server. Version and maximum wire version as the server
reports them in `buildInfo` and `hello`:

| server | 3.6.23 | 4.0.28 | 4.2.24 | 4.4.24 | 5.0.33 | 6.0.28 | 7.0.43 | 8.0.34 |
|---|---|---|---|---|---|---|---|---|
| max wire version | 6 | 7 | 8 | 9 | 13 | 17 | 21 | 25 |

## 3. Driver floors

Each driver's own constants (`lib/cmap/wire_protocol/constants.js`), and a connection attempt per
driver and server (measured):

| driver | `MIN_SUPPORTED_SERVER_VERSION` | `MIN_SUPPORTED_WIRE_VERSION` | connects to | refuses |
|---|---|---|---|---|
| 5.9.2 (`dev`, 15.0.9) | 3.6 | 6 | all eight | none |
| 6.21.0 | 4.2 | 8 | 4.2.24 to 8.0.34 | 3.6.23, 4.0.28 |
| 7.7.0 (cut 3) | 4.4 | 9 | 4.4.24 to 8.0.34 | 3.6.23, 4.0.28, 4.2.24 |

The refusal is a `MongoServerSelectionError` with the text "Server at 127.0.0.1:<port> reports
maximum wire version N, but this version of the Node.js Driver requires at least M (MongoDB X)".
Driver 5.9.2 declares 7.0 as its maximum supported server but connected to 8.0.34 and passed the
integration tier there (§4); this is the lane's reading of the constants, not a support statement.

## 4. The matrix

Boot: `boot.sh`, one server process per cell with a 60 s window, polling `/api/v1/status.json`.
Integration: `node scripts/test-tiers.js run integration` in a `node:22` container on each server's
network namespace (123 test files on `dev`, 127 on cut 3).

| server | `dev` boot | `dev` integration (pass/fail/pending) | cut 3 boot | cut 3 integration |
|---|---|---|---|---|
| 3.6.23 | 200 at 2 s | 1993/0/1 | **500 boot error page at 33 s**, process alive | not run |
| 4.0.28 | 200 at 2 s | 1993/0/1 | **500 boot error page at 32 s**, process alive | not run |
| 4.2.24 | 200 at 2 s | 1993/0/1 | **500 boot error page at 50 s**, process alive | not run |
| 4.4.24 | 200 at 2 s | 1993/0/1 | 200 at 2 s | 2013/0/1 |
| 5.0.33 | 200 at 2 s | 1993/0/1 | 200 at 2 s | 2013/0/1 |
| 6.0.28 | 200 at 2 s | 1993/0/1 | 200 at 2 s | 2013/0/1 |
| 7.0.43 | 200 at 2 s | 1993/0/1 | 200 at 2 s | 2013/0/1 |
| 8.0.34 | 200 at 2 s | 1993/0/1 | 200 at 2 s | 2013/0/1 |

- The one pending test in every cell is "Mixed Valid/Invalid Documents (Section 4.6)".
- `dev` logs no server-version warning on any server, including 3.6 to 4.2, which its README
  already lists as unsupported.
- On cut 3 against 3.6 to 4.2, the boot error page is the BF-182 fix: `7b636ce6` itself, "Stop at boot when the
  MongoDB server is too old for the driver" (the earlier `99fa8b1e` is not its ancestor). The process stays up, serves the "Nightscout - Boot error" page with
  HTTP 500, and does not retry. The log carries one `MongoIncompatibleServerError` naming the server
  address, its MongoDB release and wire version, and the driver's refusal text. On `7b636ce6` the
  message also said "Nightscout supports MongoDB 5.0 through 8.0"; on the later head `8f238fc5` it
  names the wire version and the driver version instead (read from the diff of
  `lib/storage/mongo-storage.js` between the two heads; the matrix was not re-run on `8f238fc5`).
  Without that fix the same servers retry forever with no HTTP server (BF-182).
- Not measured: a site whose data directory's feature-compatibility version lags its server
  version, replica sets, managed services (Atlas and others), and authentication modes other than
  none.

## 5. Implications

- Sites on MongoDB 3.6, 4.0 or 4.2 keep working on `dev` and 15.0.9 and stop at the boot error page on
  16.0.0. The release notes have to say so before the upgrade, and the page has to name the fix,
  which it does.
- 4.4 starts and passes the integration tier on driver 7, but stays outside the documented supported
  range (5.0 to 8.0).
- An announce step before the refusal is possible on `dev`: driver 5.9.2 can read the server version,
  so a persistent admin notice on servers older than 4.4 could name the release in which they stop
  working (the defaults-calendar draft's proposal; see
  [defaults-calendar-2026-10-25](defaults-calendar-2026-10-25.md) §3).

## 6. Reproduce

See [`tools/lab/mongo-server-matrix/README.md`](../../../tools/lab/mongo-server-matrix/README.md).
Run integration cells in containers, not on host-published ports in parallel: the lane's one
host-side run (`dev` on 8.0.34, alongside other cells) had 4 failures, all timeouts or slow hooks,
which the container runs did not show.
