# Kubernetes binding (DEPLOY-K8S-BINDING), lane K, 2026-11-10

*Contributor-facing evidence record. Captured 2026-11-10; not edited after capture. Figures are
from tool output in this session. Status words as in AGENTS.md section 4.*

Decision of record: [tanka-binding-parallel](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#tanka-binding-parallel)
(Tanka/Jsonnet in nightscout-deploy, local cluster, in parallel with the Compose bench; the
equivalence claim still waits on `DEPLOY-TRUST-PROBES`). Also applied:
[internal-listener-ory-pattern](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#internal-listener-ory-pattern),
[admin-plane-same-address-different-port](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#admin-plane-same-address-different-port),
[evaluator-static-partition](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#evaluator-static-partition),
[pool-primitive-shared](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#pool-primitive-shared),
[vault-agent-sidecar](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#vault-agent-sidecar).

## Anchors

| tree | commit |
|---|---|
| nightscout-deploy `main` (branch base) | `cda3826` |
| nightscout-deploy `k8s/tanka-binding-20261110` (this lane, local, unpushed) | `19b21ae99a4ce42a655fcba8bce727bdb5b13999` |
| nightscout-deploy `deploy/compose-sync-20261110` (the Compose tree the binding matches; another lane) | `085d88a` |
| core rendered by the preview environment | `16a1fc2d45e59602eb6ec3e3bf6f506f35bcc5b1` |
| tools | `tk` v0.20.0, `kubectl` client v1.25.16, Node v22.23.4 |

Worktree: `/home/bewest/src/nightscout-deploy-k8s-wt` (branch above). Files: `bindings/kubernetes/`
only; the README there carries the shape, run order, check table and equivalence table (one home).

## Result

**Rendered and checked offline; no cluster smoke.** No k3s, minikube, microk8s, kind or k3d is on
the host (Docker 29.1.3 is). Nothing was installed. Root filesystem at capture: 55 % used, 195 GB
free (the brief's 92 % was not observed).

| item | result |
|---|---|
| `tk show environments/preview` | 31 manifests: 3 StatefulSet (cohort, postgres, vault), 3 Deployment (admin, ui, edge), 1 Job, 8 Service, 7 NetworkPolicy, 4 ConfigMap, 2 ServiceAccount, 1 ClusterRoleBinding, 1 PVC, 1 Namespace; 0 Secret |
| golden render `check/golden/preview.yaml` | 1740 lines, sha256 `f101272353b16a9ce9314418eaf8b10e43611a5dc43284ed87212b31721c8065`; `check/golden.sh` ok |
| `check/invariants.js` against the compose-sync tree (`085d88a`) | 8 checks, 0 failures |
| `check/invariants.js` against the branch's own `bindings/compose` (`main`, core `ed2ced00`) | 3 failures, all in `postgres-identities-match-compose` (see below), as expected until the Compose sync merges |
| `check/controls.js` | 9 controls, 9 red as expected, each restored to green |
| `check/vault-kubernetes-auth.test.js` | 3 tests, 3 pass; ablation (environment tokens no longer dropped) fails 1 of 3 with `environment tokens dropped`; restored 3/3 |
| server-side schema validation | UNMEASURED: `kubectl create --dry-run=client` needs API discovery, and no cluster exists |

### Invariants and their controls (exact red messages)

| check | mutation in the Jsonnet | red line |
|---|---|---|
| internal-listener-not-on-service | `ns-ipc` volume as `hostPath` | `StatefulSet/cohort volume ns-ipc must be a pod-private emptyDir, found hostPath` |
| internal-listener-not-on-service | realtime Service targets `int-owner` | `Service/realtime publishes internal port int-owner of StatefulSet/cohort container tenant-admin` |
| admin-not-public | admin Service type `LoadBalancer` | `Service/admin exposes the admin port as LoadBalancer` |
| secrets-by-reference | synthetic connection string as literal api env | `StatefulSet/cohort container api env NS_API_PG is a literal; it must come from a Secret reference` |
| images-pinned | postgres image `postgres:16` | `StatefulSet/postgres container postgres image postgres:16 is not pinned by digest or exact tag` |
| evaluator-statefulset | ordinal env removed | `evaluator env NS_EVALUATOR_POOL_ORDINAL must come from the StatefulSet pod-index label` |
| no-overlap-update | `podManagementPolicy: Parallel` | `StatefulSet/cohort podManagementPolicy must be OrderedReady` |
| service-links-off | `enableServiceLinks: true` on the cohort | `StatefulSet/cohort must set enableServiceLinks: false (...)` |
| postgres-identities-match-compose | `root_writer` dropped from the api inventory | `api: binding names alarm,api,lifetime_api,readiness, Compose names alarm,api,lifetime_api,readiness,root_writer` |

Every control turned exactly its own check red (no other check changed) and the restored copy was
green. Controls run in a scratch copy; the working tree is never mutated.

### Red against the branch's own Compose tree (the real mismatch)

The branch is cut from `main` as briefed, and `main`'s `bindings/compose` is still the `ed2ced00`
import. The binding renders the `serve.internal` contract of `16a1fc2d`, which only the
compose-sync branch carries. Against `main`'s tree the identity check reports:

```
FAIL postgres-identities-match-compose: the ownership overlay ../compose/ownership-admin/ownership-grants.js is missing: the admin identity has no Compose counterpart in this tree
FAIL postgres-identities-match-compose: api: binding names alarm,api,lifetime_api,readiness,root_writer, Compose names alarm,api,lifetime_api,readiness
FAIL postgres-identities-match-compose: the binding renders core 16a1fc2d45e59602eb6ec3e3bf6f506f35bcc5b1 but the Compose tree records ed2ced00c80bd0a6a7d75f834d2c6e2af8c71364
```

It goes green once `deploy/compose-sync-20261110` (or its successor) merges. The binding also
needs that branch at apply time: `scripts/secrets.sh seed` reads the ownership overlay's
`ownership-grants.js`.

## Binding equivalence, summary

Full table: `bindings/kubernetes/README.md` in the branch. 22 rows: 19 **rendered**, 0 **smoked**,
3 **UNMEASURED** (the `demo`/restore operator, the `depends_on` ordering and the `restart: "no"`
policy). Rendered but with a named open measurement: the two-cohort refusal control, NetworkPolicy
enforcement (network-plugin dependent), the Kubernetes-auth Vault login and the provisional pool
variable names.

Differences from Compose, by mechanism:

| Compose | Kubernetes | consequence |
|---|---|---|
| four services share a bind-mounted `ipc` directory | four containers of one Pod share an `emptyDir` | the socket transport is unchanged; a second Pod cannot join it (the restore `demo` must become an ephemeral container in the cohort Pod; not rendered) |
| `depends_on` api -> realtime -> evaluator, `restart: "no"` | containers start together after the Vault Agent sidecar; `restartPolicy: Always` | a role that exits early is restarted in place as a new incarnation; read-derived, UNMEASURED |
| per-role state directory mounted read-only | per-role Secret, copied by an init step into a memory `emptyDir` (0400, uid 1000) | required because `load-env.js` refuses symlinked or group-readable files, and Secret volumes are both (read-derived from `load-env.js` and kubelet behaviour) |
| no Kubernetes service links | `enableServiceLinks: false` on every Pod | without it Kubernetes injects `API_PORT=tcp://...` into every container, which core reads for the consumer listener in every role (`lib/server/serve/listeners.js`); read-derived, invariant `service-links-off` |
| admin on its own private address `admin:1342` | admin Deployment on its Pod IP, ClusterIP Service, operator-only NetworkPolicy | `kubectl port-forward` dials the Pod's loopback and cannot reach a Pod-IP bind (read-derived); operators reach it from a Pod labelled `component: operator` |
| Vault Agent AppRole (`role_id`/`secret_id` files) | Kubernetes auth: projected service-account token (audience `vault`) in the sidecar only; Vault reviews it with `system:auth-delegator` | as the decision sets; the AppRole secret_id re-issue step has no counterpart |
| `prepare.js` keeps the CA key in state | `secrets.sh seed` discards it after signing | a re-issue needs a new CA |
| postgres data at the volume root | `PGDATA` one level down | a fresh PVC carries `lost+found` |

## Stops and mismatches raised

- **Base tree mismatch** (above): the brief asked for a branch from `main`; the Compose tree the
  binding must match exists only on `deploy/compose-sync-20261110`. Not merged or rebased here;
  the check names the gap.
- **No forbidden pattern needed.** No role needs host networking. Shared sockets stay inside one
  Pod. The admin plane is reachable only inside the cluster.
- **Pool flag names are provisional** (`NS_EVALUATOR_POOL_MEMBERS`, `NS_EVALUATOR_POOL_ORDINAL`):
  `MT-POOL-PRIMITIVE` is not started, so core defines no names yet. One place in the renderer
  (`evaluatorPool`) holds them.

## Install request for the cluster smoke (maintainer)

kind runs Kubernetes nodes as Docker containers, which this host has. Kubernetes 1.29 or newer is
needed (native sidecars; pod-index label 1.28+), and the host's `kubectl` 1.25 is outside the
supported one-minor skew of such a server. Both binaries are single files; a user-local directory
avoids a system-wide install. Verify each checksum before use:

```bash
mkdir -p ~/.local/bin && cd "$(mktemp -d)"
curl -fsSLO https://github.com/kubernetes-sigs/kind/releases/download/v0.27.0/kind-linux-amd64
curl -fsSLO https://github.com/kubernetes-sigs/kind/releases/download/v0.27.0/kind-linux-amd64.sha256sum
sha256sum -c kind-linux-amd64.sha256sum && install -m 0755 kind-linux-amd64 ~/.local/bin/kind
curl -fsSLO https://dl.k8s.io/release/v1.32.2/bin/linux/amd64/kubectl
curl -fsSL https://dl.k8s.io/release/v1.32.2/bin/linux/amd64/kubectl.sha256 | awk '{print $1"  kubectl"}' | sha256sum -c && install -m 0755 kubectl ~/.local/bin/kubectl
kind version && ~/.local/bin/kubectl version --client
```

kind v0.27.0's default node image is Kubernetes v1.32.2 (read-derived from the release notes; the
node image version is printed by `kind create cluster`). kindnet enforces NetworkPolicy from kind
v0.24 (read-derived); the smoke must confirm it with a denied connection before the
NetworkPolicy rows count. The binding's `spec.json` names `https://127.0.0.1:6443`; a kind cluster
created with `networking.apiServerPort: 6443` matches it.

Smoke plan once installed (each step a gate; UNMEASURED today): build and re-tag the Compose
image at `16a1fc2d` with the synced tree, `kind load`, `tk apply`, `secrets.sh seed`, Job
`provision` complete, `secrets.sh publish`, cohort Ready; then the synthetic entry round-trip
through `api` (legacy token exchange, then API3 write and read back), a Socket.IO connect through
`edge`, the admin `listOwners` from an operator-labelled Pod, a denied connection to 1342 from an
unlabelled Pod, and the control: scale the cohort to 2 out of band and require the second Pod to
refuse to serve. Then `kind delete cluster` and `docker image prune` for the loaded images.

## What is local and unpushed

- nightscout-deploy branch `k8s/tanka-binding-20261110` at `19b21ae`, worktree
  `/home/bewest/src/nightscout-deploy-k8s-wt`. It replaces `bindings/kubernetes/README.md`, which
  the README lane (`docs/operator-readme-20261110`) also edits: expect a one-file conflict there.
- This record, committed alone on alignment `main`. Queue, `decisions.md` and `contents.md` are
  not edited.

## 2026-11-10 (evening): cluster smoke on kind

*Appended after capture of the sections above, which stand as recorded. Figures from tool output in
this session.*

### Anchors

| tree or tool | value |
|---|---|
| nightscout-deploy `main` (branch base; pushed, includes the compose sync and lane K) | `16fe4d4` |
| nightscout-deploy `k8s/cluster-smoke-20261110` (this smoke; local, unpushed) | `65f55c1` |
| core rendered and built | `16a1fc2d45e59602eb6ec3e3bf6f506f35bcc5b1` |
| image | `git archive 16a1fc2d` with `deploy/multitenant` replaced by `bindings/compose/multitenant` at `16fe4d4`, built with that tree's Dockerfile and revision label; image id `sha256:9188bf0fa23a…` |
| kind | v0.27.0, cluster `ns-k8s-smoke`, one node |
| `kubectl` client / server | v1.32.2 / v1.32.2 |
| `tk` | v0.20.0 |
| golden render at the branch head | sha256 `2f3e51a18fe5eabf64ef369dd048cb2395fd63920fec0e05a6d7568293ba5b52` |

Disk before loading: `/` 56 % (190 GB free, Docker's root), `/home` 92 % (40 GB free). The cluster was
deleted at the end, and the built image and kind node image were removed.

### Smoke table

| step | result (quoted from output) |
|---|---|
| apply | `tk apply` panicked: `slice bounds out of range [:192] with length 189` in `client.splitRow` (tk v0.20.0 reading `kubectl` v1.32 output). The committed render was applied with `kubectl apply -f check/golden/preview.yaml`: 31 objects created. The server accepted every object, so server-side schema validation passed |
| `secrets.sh seed` | `{"state":"seeded","secrets":["ns-postgres-password","ns-vault-tls","ns-ca"],"configMaps":["ownership-grants"]}` |
| vault Ready | **binding defect 1**: never Ready. The probe dialled `https://vault:8200`, and that Service has no endpoint until the probe passes. Fixed to loopback with `-tls-server-name=vault`. `OrderedReady` would not replace the unready Pod (`currentRevision` ≠ `updateRevision`), so `vault-0` was deleted by hand; Ready after |
| Job `provision` | `bootstrap`: `{"state":"synthetic-demo-provisioned",…}`; `vault-kubernetes-auth`: `{"state":"vault-agent-provisioned","method":"kubernetes","role":"nsdemo_vault_agent",…}`; `ownership-grants`: `{"state":"ownership-grants-provisioned","role":"nsdemo_ownership_operator","grants":10}`; `done`: `{"state":"provisioned"}` |
| `secrets.sh publish` | `{"state":"published","secrets":["ns-config-api","ns-config-realtime","ns-config-evaluator","ns-config-tenant-admin","ns-config-ui","ns-config-admin"]}` |
| Vault Agent sidecar | `authentication successful, sending token to sinks`; `token written: path=/run/ns-vault/token`; `renewed auth token`. The sink is `-rw------- owner=1000 group=1000` |
| cohort roles, first start | all four exited: `could not start: preview startup failed`. **Binding defect 2**: an `emptyDir` root is `3777 0:1000` (measured with a probe Pod), and core requires a socket directory owned by the process uid with no group or other bits (`transport.js:115`). Fixed by an init-made 0700 subdirectory mounted with `subPath: d`. After the fix: tenant-admin `Listening … 0.0.0.0:1341`; evaluator `Evaluator preview started; configured tenants: 2` |
| api | **Compose-tree defect A** (reproduces the bench lane's finding): `preview readiness or storage initialization refused`. A debug Pod showed `LIFECYCLE_WINDOW_SCHEMA_UNSAFE` inside the subject-admin store's transaction, then `SUBJECT_ADMIN_STORE_UNSAFE`. `config.js` excludes `root_writer` from the control-schema reads. With bench fix 1's grants applied by hand in the disposable database: `Listening for role api on 0.0.0.0:1337` |
| realtime | `Listening for role realtime on 0.0.0.0:1339`, after one exit 78 (`realtime preview readiness or initialization refused`) when it started before api. The in-place restart then served |
| cohort Ready | `cohort-0 5/5 Running` |
| admin | **Compose-tree defect B** (ownership overlay): `invalid explicit admin operator configuration`. `admin.json` keys are `connectionEnv, namespace, operator, tenants`, but core's `admin-config.js` requires `lifecycleNamespace`. With the key added to the Secret by hand: `Listening for role admin on 10.244.0.26:1342` |
| entry round-trip through `edge` → `api` (synthetic tenant A) | `exchangeA 200, putA 201, getA 200, roundTrip true` |
| tenant isolation (same entry) | read with tenant B's own token on B's host: `404`; tenant A's token on B's host: `401` |
| realtime connects through `edge` | Engine.IO polling `200`, open `true`, upgrades `["websocket"]`; WebSocket frames `open, 0{, 40`, namespace `connected` |
| admin from an operator-labelled Pod | `admin:1342=connected … listOwners=listed owners=1` |
| admin from an unlabelled Pod | `admin:1342=timeout`. The same Pod: `api:1337=timeout realtime:1339=timeout postgres:5432=timeout edge:8080=connected` |
| NetworkPolicy control | with `default-deny-ingress` and `admin-from-operator` deleted, an unlabelled Pod got `admin:1342=connected`. With them restored: `admin:1342=timeout`. kindnet enforces NetworkPolicy |
| **two-Pod refusal control** | **red.** `kubectl scale sts cohort --replicas=2` made `cohort-1` `5/5 Running`. Its api, realtime and tenant-admin are listening and its evaluator reports `configured tenants: 2`. Endpoints `api 10.244.0.25:1337,10.244.0.34:1337`, and `realtime` the same. Two cohorts served at once and nothing refused. Scaled back to 1; the round-trip and realtime smoke then repeated with the same results |
| update without overlap | `rollout restart sts/cohort`: `delete Pod cohort-0` 03:51:52Z, then `create Pod cohort-0` 03:51:53Z, with a new uid |
| restore operator (`demo`) | not run. The API refused an ephemeral container with `subPath` ("cannot be set for an Ephemeral Container"), and core refuses the volume root as socket directory. The Compose `demo` therefore has no Kubernetes counterpart yet |

### Controls after the smoke

The branch has 9 invariants with 0 failures, and 12 controls, all red as expected.
- New invariant `private-directories`. Mounting `ns-ipc` at its root gives `container api mounts ns-ipc at its root; mount the 0700 subdirectory (subPath d)`.
- `evaluator-statefulset` reworked:
  - an ordinal with the partition off gives `partition is off but the evaluator sets MULTITENANT_POOL_EVALUATOR_ORDINAL`;
  - partition on with `metadata.name` gives `… ORDINAL must come from the StatefulSet pod-index label`;
  - an extra readiness argument gives `evaluator readiness must be the role health check only`.

Golden current. Vault step test 3/3.

### Pool variables (canonical names)

The binding now uses core's `MULTITENANT_POOL_EVALUATOR_{PARTITION,MEMBERS,ORDINAL,LEASE_MS,DATABASE_URL,NAMESPACE}`. The provisional names map as `NS_EVALUATOR_POOL_ORDINAL` → `ORDINAL` and `NS_EVALUATOR_POOL_MEMBERS` → `MEMBERS`.

**Mismatch with the coordinator's instruction ("render only the ordinal").** On core `codex/pool-primitive-20261110` `5a789903`, `lib/pool-membership/config.js` `fromEnvironment` refuses an ordinal while the partition is off:
- `{ORDINAL: "0"}` gives `partition is off but MULTITENANT_POOL_EVALUATOR_ORDINAL set`;
- `{PARTITION: "on", ORDINAL: "0"}` gives `MULTITENANT_POOL_EVALUATOR_MEMBERS must be a non-negative integer`.

The binding therefore renders no pool variable with the partition off, which is the preview. With `partition: 'on'` it renders `PARTITION=on` plus `ORDINAL` from the pod-index label and no `MEMBERS`, per the decision that the count lives in the pool table. Core at `5a789903` still requires `MEMBERS` when on, so that combination refuses until core follows the decision. Readiness stays the role health check.

### Equivalence summary after the smoke

The table is in `bindings/kubernetes/README.md` at `65f55c1`. Of 23 rows:
- 18 smoked. 2 of those (api and admin) needed the lab workarounds for Compose-tree defects A and B.
- 1 smoked difference: start order.
- 1 rendered only: PostgreSQL identities.
- 1 **control red**: two cohorts both serve.
- 2 UNMEASURED: the restore operator, and container-restart semantics beyond the observed realtime restart.

### Lab interventions (disposable cluster only, not in any tree)

- Bench fix 1's three `GRANT`s for `nsdemo_root_writer`, run as the PostgreSQL superuser.
- `ownership.lifecycleNamespace` added to `ns-config-admin`'s `admin.json`.
- `vault-0` deleted once so the fixed probe could roll.
- Debug and probe Pods, labelled outside the StatefulSet selector.
- `docker image prune -f` at teardown reclaimed 3.746 GB of dangling images host-wide, the kind node image among them.
