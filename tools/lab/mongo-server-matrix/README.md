# mongo-server-matrix lab

Which MongoDB servers a cgm-remote-monitor tree boots and passes its integration tier against,
and what an operator sees when the driver refuses the server. Built for the
[MongoDB server compatibility matrix note](../../../docs/60-research/modernization/mongodb-server-compat-matrix-2026-10-25.md)
(2026-10-25: `dev` `b29f1bf7` with driver 5.9.2, cut 3 with driver 7.7.0, servers 3.6 to 8.0).

> Contributor-facing. Synthetic data only: each cell uses its own database on a lab container and
> must never be pointed at a real site.

## Run it

1. Start one container per server, named `mm-mongo-<suffix>`, from the official `mongo` images, each
   published on its own host port (the 2026-10-25 run used 27450 to 27457 for suffixes 36, 40, 42,
   44, 50, 60, 70 and 80). Read `buildInfo` from each before labelling a run.
2. Install each tree with `npm ci` (the tier runner and the server need its `node_modules`).
3. Boot cells, one at a time:

   ```sh
   MM_OUT=/path/to/out tools/lab/mongo-server-matrix/boot.sh <tree> dev-42 27452 31502 60
   ```

4. Integration cells, one container each (several may run at once, since each cell shares only its
   own container's network namespace):

   ```sh
   MM_OUT=/path/to/out tools/lab/mongo-server-matrix/run-tree.sh <tree> dev 36 40 42 44 50 60 70 80
   ```

| variable | default | meaning |
|---|---|---|
| `MM_OUT` | `$TMPDIR/mongo-server-matrix` | logs, generated env files, results |
| `MM_GITDIR` | `externals/cgm-remote-monitor-official/.git` | mounted read-only into the test container |
| `MM_NODE` | unset (the `node:22` image's own) | a host `node` binary to mount instead |

`boot.sh` generates the API secret per run. `itest-docker.sh` uses the tree's own
`tests/ci.test.env` with only the connection string changed. Nothing secret lives in this directory.

## What not to do

Run integration cells on the host against host-published ports only one at a time: the
2026-10-25 lane's first attempt ran a host cell alongside others and got 4 timeouts (hook
timeouts and slow tests) that the container runs did not reproduce.

## Driver floor probe

The driver floors in the note come from each driver package's own constants
(`MIN_SUPPORTED_SERVER_VERSION`, `MIN_SUPPORTED_WIRE_VERSION` in `lib/cmap/wire_protocol/constants.js`)
and from a connection attempt per driver version and server with a short server-selection timeout;
that probe was a one-off in the lane's scratch directory and is not kept here.
