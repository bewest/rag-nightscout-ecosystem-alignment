# rc-soak: A/B soak harness for a Nightscout release candidate

*Contributor-facing. Synthetic data only: never point this at a real site. Nothing here is medical advice.*

The harness runs two copies of Nightscout (cgm-remote-monitor) side by side, **arm A** and
**arm B**, each with its own server process and its own MongoDB container, and sends both the
same synthetic traffic at the same moment. It then checks that both arms stayed up, answered
the same way (except where the release notes say they should differ), stored the same records,
and did not grow in memory or slow down. The usual pairing is A = the shipping release, B = the
release candidate.

| file | what it does |
|---|---|
| `lab.sh` | starts and stops everything, runs a proof or a long soak, records every PID it starts |
| `traffic.js` | the synthetic household: CGM uploader, Loop / Trio, AndroidAPS (API v3), followers, a web page over socket.io, edits and deletes |
| `sampler.js` | every 10 s (60 s real-time): is each server alive, answering, and serving the newest reading; RSS, open files, document counts from MongoDB |
| `preload.js` | loaded into each server with `NODE_OPTIONS=--require` (the build is not modified): heap, RSS, event-loop delay every 10 s |
| `proxy.js` | fault injection only: a proxy that silently drops a fraction of devicestatus uploads |
| `fake-apns.js` | a local stand-in for Apple's push service, one per arm, counting the HTTP/2 sessions each server leaves open |
| `analyze.js` | turns a run directory into a verdict: PASS, FAIL (findings) or INVALID |
| `probe-deleted-entry.js` | a one-shot check against one server: is a reading deleted by `_id` still returned by `GET /api/v1/entries.json?count=10`? |
| `expected-diffs.json` | the differences 15.0.9 makes on purpose, each tied to a release-notes section; thresholds |

`traffic.js`, `sampler.js`, `proxy.js` and `analyze.js` adapt the connector soak lab
(`tools/lab/connector-soak/`: writer, sampler, proxy, analyser, disturbances). The request
shapes follow the client surveys in `tools/lab/object-id/probes.js` and
`reports/consumer-impact-15.0.9/lab-results.md`.

## Builds (2026-09-25)

| arm | build | worktree |
|---|---|---|
| A | 15.0.8 = origin/master 92d08342 | `externals/work/crm-6a-soak-a` (the default `ARM_A_DIR`) |
| B, **release candidate** | origin/dev e3adc91d, package version 15.0.9, tree d7383aae: #8758 with the e9dbb1fb fixes, #8568, #8768 (BF-120), #8769 (BF-126), #8419, #8770 (BF-134) | `externals/work/crm-6a-soak-rc` (the default `ARM_B_DIR`) |
| B, earlier | e9dbb1fb (`wip/object-id-crud-fixes-2`) | `externals/work/crm-6a-soak-b2` |
| B, earlier | ab7b22d6 (#8758 head; the control for BF-131) | `externals/work/crm-6a-soak-b` |

Results: `results/proof-2026-09-25.md`.

## Start the 72-hour soak of the release candidate

From the root of the alignment repository, with the two worktrees above present and `npm ci`
done in each:

```sh
export SOAK_STATE=$HOME/rc-soak-state          # anywhere outside a git tree
tools/lab/rc-soak/lab.sh soak --hours 72
```

That is A = 15.0.8 against B = e3adc91d, `AUTH_DEFAULT_ROLES=denied`, one CGM reading every
5 minutes, followers every minute, one Loop remote command every 5 minutes to a fake push
server per arm. It prints the run directory and the PIDs. After 72 hours (or to stop early):

```sh
tools/lab/rc-soak/lab.sh stop    <run>
tools/lab/rc-soak/lab.sh analyze <run>    # before down: it reads both databases
tools/lab/rc-soak/lab.sh down    <run>
```

Expect arm A's open APNs sessions and open files to grow by one per remote command (15.0.8's
leak, fixed in 15.0.9 by #8770); the report lists that under expected differences. Pass: verdict
PASS, `leak check: evaluated`, and arm B's APNs sessions and fds flat. Before starting, confirm
the instrument: `(cd externals/work/crm-6a-soak-a && node ../../../tools/lab/apns-shutdown/probe.js .)`
exits 1, and the same in `crm-6a-soak-rc` exits 0.

## Before the first run

- Two cgm-remote-monitor worktrees with `npm ci` done, by default
  `externals/work/crm-6a-soak-a` (A) and `externals/work/crm-6a-soak-b` (B). Other builds:
  `ARM_A_DIR=... ARM_B_DIR=...`.

  ```sh
  git -C externals/cgm-remote-monitor-official worktree add --detach "$PWD/externals/work/crm-6a-soak-a" 92d08342
  (cd externals/work/crm-6a-soak-a && n exec 22.23.2 npm ci)
  ```
  Give `worktree add` an absolute path: a relative one is taken relative to the `-C` directory.
- Docker with `mongo:7.0.43` (or `MONGO_IMAGE=mongo:4.4`), `n` with node 22.23.2 (or
  `NODE_VER=24.20.0`), `curl`, `ss`, `openssl`.
- Free ports, all bound to 127.0.0.1: MongoDB 27531/27532, Nightscout 17531/17532, proxies
  17533/17534 (only with `--fault-drop`). Each can be moved with `MONGO_PORT_A/B`,
  `NS_PORT_A/B`, `PROXY_PORT_A/B`; a second lab at the same time also needs its own `PFX`
  (container name prefix, default `s6a-soak`).
- `SOAK_STATE` (default `${TMPDIR:-/tmp}/rc-soak`) holds every run directory. Keep it outside
  any git tree: each run's `secrets/` holds its generated `API_SECRET` (mode 700, never printed).

## Run a short proof (foreground)

```sh
tools/lab/rc-soak/lab.sh run --aa --minutes 10 --sim-hours 24     # A/A control: both arms build A
tools/lab/rc-soak/lab.sh run --minutes 50 --sim-hours 72          # A/B, three simulated days
```

`run` starts both arms, sends compressed traffic (here 24 or 72 simulated hours of 5-minute
readings in 10 or 50 real minutes), stops the processes, prints the analysis, and removes the
MongoDB containers (`KEEP=1` keeps them). Simulated time always **ends at the real time**: a
compressed run backfills the past, so no record ever carries a future timestamp.

## Start a long soak (real time, background)

```sh
tools/lab/rc-soak/lab.sh soak --hours 72
```

It prints the run directory and the PIDs of the traffic driver, the sampler and both servers
(also in `<run>/pid-*`). One CGM reading every 5 minutes, follower polls every minute, samples
every 60 seconds. Options for both `run` and `soak`: `--config readable` (default `denied`,
the recommended `AUTH_DEFAULT_ROLES`), `--aa`, and the fault options below.

While it runs:

```sh
tools/lab/rc-soak/lab.sh status  <run>                       # PIDs, containers, last tick
tools/lab/rc-soak/lab.sh analyze <run>                       # interim: INVALID until the traffic has finished, findings so far are real
tools/lab/rc-soak/lab.sh disturb <run> mongo-restart both    # restart both databases
OUTAGE_SEC=60 tools/lab/rc-soak/lab.sh disturb <run> mongo-outage both   # both databases gone for 60 s
tools/lab/rc-soak/lab.sh disturb <run> server-restart both   # restart both servers
```

A disturbance is recorded in `<run>/disturb.jsonl`; the analyser does not count errors inside
that window (plus 90 s), and still requires every acknowledged write to be stored afterwards.
Disturb **both** arms together so the traffic stays identical.

Stop (at the end, or early) and read the result:

```sh
tools/lab/rc-soak/lab.sh stop    <run>   # traffic, sampler, proxies, servers: each by its recorded PID
tools/lab/rc-soak/lab.sh analyze <run>   # needs the MongoDB containers: analyze before down
tools/lab/rc-soak/lab.sh down    <run>   # remove this run's MongoDB containers
```

`stop` only kills a PID whose command line is the expected process (`lib/server/server.js`,
`traffic.js`, `sampler.js`, `proxy.js`); it never kills by name.

### How the APNs traffic reaches the fake server

Neither build has a setting for the APNs host: `lib/server/loop.js` builds `new apn.Provider(options)`
with only the key and `production`, and `@parse/node-apn` 5.2.3 picks Apple's address from
`production`. `preload.js` (loaded with `NODE_OPTIONS=--require`, no build file changed) wraps the
tree's `@parse/node-apn` `Provider` to set `address: 'localhost'`, the fake server's port and
`rejectUnauthorized: false`, exactly as `tools/lab/apns-shutdown/probe.js` and PR #8419's test do.
Every provider is still built, used and shut down (or not) by the build's own code. The fake server
uses the tree's test TLS pair and answers 200 to every push; nothing leaves 127.0.0.1.

The report's "Loop remote commands and APNs" section gives per arm: commands answered 200,
providers built, pushes received, sessions opened and still open at the end of traffic, open fds
and active handles. B leaving more than 2 more sessions open than A, or ending with more than 20
more open fds, is a finding. A leaving sessions open is listed as expected when A is 15.0.8.

## What the traffic does

One tick is 5 simulated minutes. Every value is generated in `traffic.js`, and every record
carries `soakKey`, a lab-only field, so records can be matched between arms without relying on
either build's ids.

| client | shape |
|---|---|
| CGM uploader (xDrip-like) | `POST /api/v1/entries` every tick, with a client `_id` on even ticks; re-sends of the last 3 readings; a fingerstick every 6 h |
| Loop / Trio | devicestatus every tick (Loop shape and openaps shape alternate), with re-sends; Temp Basal, Correction Bolus, Carb Correction, Temporary Override, Temporary Target via v1; the last two treatments re-sent |
| OpenAPS (oref0) | temp basal uploads to `/api/v1/treatments.json`; the latest-treatment lookup `count=1?<hash>` and `count=1?token=…`, plus a plain `count=1` control |
| AndroidAPS | API v3 with a JWT: create Temp Basal / SMB / devicestatus with `identifier`, re-create (dedup), `PUT`, soft `DELETE`; reads with `limit`, `sort$desc`, `date$gte`; `lastModified` |
| followers | LoopFollow (`entries.json?count=288`, `devicestatus.json?count=1`, `treatments.json?find[created_at][$gte]=`, `profile/current`), nightguard (`find[date][$gt]`, `/api/v2/properties`), all with a readable token |
| GluPredKit | `count=0` with two-sided date windows on treatments, `entries/sgv.json` (`dateString`), profile, devicestatus; `count=0` with no window |
| web page | a socket.io client that authorizes with a JWT and records every `dataUpdate`; an editor socket that sends `dbUpdate` and `dbRemove`; every hour of simulated time (and at the end) a "page load": a new socket per arm records the full `dataUpdate` a newly opened page is sent |
| careportal | v1 `PUT` and `DELETE` of treatments by `_id`, v1 `DELETE` of an entry and of a devicestatus, each using the `_id` that arm's own reply gave |
| other followers | `treatments.json?count=50&token=…` (a follower); the same read and `devicestatus.json?count=10` authenticated by header, as an uploader sends them. A v1 treatments or devicestatus read is answered from the in-memory copy only when `count` is its only query parameter, so only the header form exercises that path; an entries read ignores `token` when choosing |
| Loop caregiver | `POST /api/v2/notifications/loop` ("Temporary Override") every tick (`LOOP_EVERY`, default 1). Each arm has its own fake APNs server (`fake-apns.js`, ports `APNS_PORT_A/B`, default 17537/17538): the arm gets `LOOP_APNS_KEY` (a P-256 key generated per run), `LOOP_APNS_KEY_ID`, `LOOP_DEVELOPER_TEAM_ID` and `LOOP_PUSH_SERVER_ENVIRONMENT=development`, the profile carries `loopSettings`, and `preload.js` sends the build's APNs connections to the fake server (below). `--no-apns` turns this off; the command then answers 500 on both arms, which `expected-diffs.json` allows |

## Reading the result

`analyze` prints a report and writes `<run>/analysis.json`. Exit status: 0 PASS, 1 FAIL, 2 INVALID.

**INVALID** means the run does not show what it would need to show; it is never a pass. Any of:
fewer than 5 liveness samples for an arm; fewer than 2 page loads; more than 10% of an arm's samples not alive,
answering and fresh (outside disturbances); no sample in the last 3 minutes of traffic; traffic
did not run every tick; fewer than 50 requests or under 80% answered 2xx; no in-process metrics;
the socket follower never authorized or never received a `dataUpdate`; MongoDB unreachable
for the parity check.

**FAIL** lists findings. Each is a candidate defect until explained:

| check | a finding is |
|---|---|
| liveness | any sample, outside a disturbance, where an arm is not alive, not answering an authenticated status read, or not serving a reading at least as new as the last one it acknowledged |
| http | any 5xx not in the allow list; any request with no HTTP answer outside a disturbance |
| responses | any difference between the arms' normalised replies (ids the server chose, `srvModified`, `srvCreated`, `lastModified` removed; status, `/api/v2/properties` and `/api/v3/lastModified` compared by key set) that `expected-diffs.json` does not tie to a release-notes section. In an A/A run every difference is a finding. A key-set difference is asked again 3 s later; if it then matches it is counted as transient (the server's in-memory copy reloads a moment after a write), and more than 5% transient for one label is a finding. Differences inside a disturbance window are counted, not judged |
| ledger | a write an arm acknowledged (2xx) that is not in that arm's database; a delete it acknowledged that left the record; a v3 delete not marked `isValid: false`; a write one arm acknowledged and the other did not |
| parity | after normalising server-chosen ids and timestamps, any record in one arm's database and not the other's, any `soakKey` stored a different number of times, or any field that differs. One exception, reported under expected differences: a record stored a different number of times whose every acknowledgement fell inside a disturbance window (a request that reached one server just before it stopped, whose reply was lost, and which the driver then re-sent, as an uploader would) |
| memory | over the last 75% of the longest process lifetime, one arm's heap minima (lowest heap per window, so garbage collection timing drops out) grow more than 25 MB beyond the other arm's, or its RSS minima more than 100 MB. Only evaluated when each process lived at least 20 minutes |
| event loop | one arm's event-loop delay p99 more than twice the other's plus 50 ms |
| latency | for a label with at least 50 requests, one arm's p95 more than twice the other's plus 20 ms |
| socket | an acknowledged reading inside the web page's 48-hour window that never arrived in a `dataUpdate`; a follower disconnect outside a disturbance |
| page load | a record the arm acknowledged deleting (more than 5 s earlier) still in the data a newly opened page is sent; the two arms' page loads at the same tick holding different records (a record acknowledged less than 10 s before the load is not compared: the in-memory reload is asynchronous); a page load with no `dataUpdate` |

**PASS** means none of the above. The report also lists the expected differences it saw, each
with its release-notes section, and flags any that are promised only by a decision record and
not described in `releases/cgm-remote-monitor-15.0.9/release-notes.md`.

A long soak passes when `analyze` says PASS at the end, the leak check says `evaluated`, and the
memory lines show no steady growth on B that A does not also show.

## Proving the checks can fail

A check that has never failed is not evidence. Before trusting a PASS from a changed harness:

```sh
tools/lab/rc-soak/lab.sh run --aa --minutes 10 --sim-hours 24                           # must PASS with zero differences
tools/lab/rc-soak/lab.sh run --aa --minutes 10 --sim-hours 24 --fault-drop 0.01         # must FAIL: ledger + parity, devicestatus
tools/lab/rc-soak/lab.sh run --aa --minutes 25 --sim-hours 48 --fault-leak 64           # must FAIL: memory, arm b
```

A one-shot check of a single server, useful as a regression probe:

```sh
node tools/lab/rc-soak/probe-deleted-entry.js http://127.0.0.1:17532 <run>/secrets/api_secret
# exit 0: a reading deleted by _id is gone from entries.json; 1: still returned; 2: could not run
```

The APNs check (arm B leaving push connections open) is proven by swapping the arms, so the
leaking build is B:

```sh
ARM_A_DIR=$PWD/externals/work/crm-6a-soak-rc ARM_B_DIR=$PWD/externals/work/crm-6a-soak-a \
  tools/lab/rc-soak/lab.sh run --minutes 5 --sim-hours 12     # must FAIL with [apns] and [fds] on arm b
```

`--fault-drop RATE` puts `proxy.js` in front of both arms and silently drops RATE of arm B's
devicestatus uploads while answering 200, so only the database checks can see it.
`--fault-leak KB` makes arm B's server keep KB of heap per request. `--fault-arm a` moves either
fault to arm A. The control for both is the plain A/A run: identical builds, zero differences.

## Files in a run directory

`run.json` (builds: head, tree, version; node; MongoDB server version read from the server;
config; fault), `traffic.json` / `done.json` (schedule and end), `requests.jsonl` (one line per
operation: label, per arm status, ms, error, deprecation header, difference signature),
`diffs.jsonl` (first three normalised bodies per signature), `ledger.jsonl` (acknowledged writes
per arm), `socket-<arm>.jsonl`, `samples.jsonl`, `metrics-<arm>.jsonl`, `server-<arm>.log`,
`pageload-<arm>.jsonl`, `disturb.jsonl`, `analysis.json`, `analysis.txt`, `secrets/` (never share).
`diffs-values.jsonl` keeps, for the first 5 occurrences of each key-set difference (status,
`/api/v2/properties`, `/api/v3/lastModified`), the values under each differing top-level key, so
the difference can be read. `DUMP_TICKS=57,60 lab.sh run …` writes both arms' raw replies for
every operation at those ticks to `dump.jsonl` (debugging only; large).

`traffic.json` carries `harness` (currently 5: 2 added page loads, 3 `diffs-values.jsonl`, 4 the
header-authenticated count reads, 5 the fake APNs servers and one Loop remote command per tick);
page loads are only required from harness 2 on. `apns-<arm>.jsonl` holds the fake APNs server's
session counts every 10 s.

`<SOAK_STATE>/current` points at the most recent `up`; with several labs at once, use the run
path `up` prints instead.
