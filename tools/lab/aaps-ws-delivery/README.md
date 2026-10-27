# aaps-ws-delivery lab (BF-164)

When does a record written outside API v3 reach a client that behaves like AndroidAPS NSClientV3 in
websocket mode? Built for the
[AndroidAPS websocket delivery note](../../../docs/60-research/remedial/aaps-websocket-delivery-lab-2026-10-25.md)
and register BF-164.

> Contributor-facing. Synthetic data only. Two lab servers on 127.0.0.1, each with its own database;
> never point it at a real site.

## Run it

```sh
# MongoDB on 127.0.0.1:27316 (any version the tree supports), and an installed tree
tools/lab/aaps-ws-delivery/start-servers.sh <crm worktree> <outdir> [mongodb://127.0.0.1:27316]
node tools/lab/aaps-ws-delivery/aaps-ws-lab.js <crm worktree> <outdir>
# stop: kill the PIDs in <outdir>/source.pid and <outdir>/target.pid
```

- `start-servers.sh` boots a **source** Nightscout (port 17317, database `bf164src`) and the **target**
  under test (port 17316, database `bf164tgt`) with nightscout-connect reading the source
  (`CONNECT_SOURCE=nightscout`), so connector writes are real. Both use `AUTH_DEFAULT_ROLES=denied`.
  Two API secrets are generated per run into `<outdir>/secrets` (mode 600); nothing secret lives in
  this directory.
- `aaps-ws-lab.js` creates a follower subject with the built-in `readable` role and a writer subject
  with `admin`, then runs the scenarios below with a simulated client (`SimAAPS`). Each modelling
  choice cites the AndroidAPS file it comes from (comments C1 to C7 at the top of the script).
  Liveness of both servers is checked around every measured step. Output: `<outdir>/lab.log` and
  `<outdir>/results.json`.

Scenarios, for a carb written through API v1, through the main socket (`dbAdd`), and a reading written
by nightscout-connect: S1 the socket stays up for 45 s; S2 a reconnect with no API v3 write in that
collection in between; S3 a reconnect after an API v3 write in the same collection. Control: an API v3
create while the socket is up.

Results: [results/2026-10-25-dev-b29f1bf7/](results/2026-10-25-dev-b29f1bf7/) (`dev` `b29f1bf7`,
Node v22.23.4). The connector's copy took 84 to 190 s in that run, so a full run takes about 7.5 min.
Re-run: [results/2026-10-27-dev-dcf20bfb/](results/2026-10-27-dev-dcf20bfb/) (`dev` `dcf20bfb`, Node v22.23.4,
MongoDB 8.0.34), the same outcome in all 11 cells; the connector's copy took 96 and 183 s.
