# Image start forms

Builds two cgm-remote-monitor images from clean trees (`git archive <commit>`, `docker build`). It runs the same `docker run` forms against each image with a throwaway MongoDB 8.0 container, and records for each form:

- whether `/api/v1/status.json` answers 200, and how soon;
- PID 1's command line, and the number of node or npm processes;
- the time `docker stop -t 10` takes, and the exit code.

The API secret is generated per run and is never written to disk.

```
# images nslab:dev and nslab:pr8865 built first (see results for the commits)
tools/lab/image-start-forms/run.sh
```

## 2026-10-27: dev `dcf20bfb` against #8865 `9bb1f0b4`

| form | dev | #8865 |
|---|---|---|
| default (no command) | serves; PID 1 `node lib/server/server.js`; stop 10.1 s, exit 137 | serves; PID 1 `node /usr/local/bin/nightscout single`; stop 0.13 s, exit 0 |
| `node lib/server/server.js` | serves; stop 10.1 s, exit 137 | serves; same PID 1 as dev; stop 0.13 s, exit 0 |
| `sh -c 'node lib/server/server.js'` | serves; stop 10.2 s, exit 137 | serves; stop 0.15 s, exit 0 |
| `nightscout single` | exits 1 (no such program) | serves |
| `npm start` | exits 1: `npm` is not in the runtime image | the same |
| `env`, `node --version` | same environment names, v24.22.1 | the same |
| SIGINT (`docker kill -s INT`) | ignored: node as PID 1 installs no handler | exit 0 after 0.13 s |
| `nightscout healthcheck` inside a running container | not present | exit 0 |

Both images have Entrypoint `docker-entrypoint.sh`, no HEALTHCHECK, user `node` and workdir `/opt/app`. Only the default command differs (`node lib/server/server.js` against `nightscout single`). The images are 259 MB and 260 MB. With the default start, `status.json` is identical apart from the server time. In every form, one node process serves.

Not covered: a SIGTERM that something other than `docker stop` sends, such as a platform supervisor, or a person running `docker kill -s TERM`. On dev the server ignores that signal, as it ignores SIGINT, because node as PID 1 installs no handler; the site keeps running. On #8865 the server exits 0. A container running under `restart: always` or `unless-stopped` comes back, but one under `restart: on-failure` stays stopped. Tooling that matches PID 1's command line is not covered either.
