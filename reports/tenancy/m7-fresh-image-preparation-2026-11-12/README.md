# Fresh-host preparation dependency repair

Scope: reproduced pre-build preparation failure and focused source repair; no
fresh application image, cloud, full acceptance or capacity result is claimed here.

The remote diagnostic's first attempt stopped during local preparation, before
image building or tenant provisioning. The coordinator independently reproduced
that failure from core `6dbe931ac452ef628c9a457be0072a4ccdd17fe7` and the deployment
binding archived at `d4cae9d20a9ea630b3801b7dee8103e19ba2d4ee`, in an owned clean
source worktree with no `node_modules`. See [failure](clean-before.txt): reading
`registry-plan.leaseSessions` loaded `pool-config`, whose eager import of
`PreviewConfigError` loaded the serving configuration, domain catalogue and API3
date helpers. The missing dependency was `moment`. Dependency-equipped local
prototypes had masked this preparation requirement.

Core `a50130e67e8a8e066ce866535aeb8b627a068904` puts the same error constructor in
`lib/server/serve/preview-config-error.js`; the serving parser and pool sizing
import it directly. No pool values, validation bounds or deployment authority
change. Actual preparation on the advanced clean worktree succeeds before any
application dependencies are installed: [capture](clean-prepare.txt). Its overlay
still names the earlier deployment archive; the runtime binding subtree is
unchanged. The refreshed diagnostic binding
`9799c51b61a9870bfc1257212fa19f4fb3f85ae3` records this source and passes the five-file
source/delta identity gate. The latter is a metadata pin, not a second deployment
acceptance claim.

[Focused serving/pool checks](focused.txt): 45 pass. The new check copies only the
pool-sizing module and shared error module into scratch, reads the operation pool,
and requires invalid input to throw the shared constructor. Restoring the eager
serving import makes it fail with `Cannot find module './preview-config'`:
[red control](dependency-control.txt). This specifically establishes dependency
independence; the separate original clean-source failure establishes the full
missing-`moment` chain. [Restored pool checks](restored.txt): 17 pass, including
constructor identity with the serving parser.

[Artifact hashes](artifacts.json) retain the private original stderr hash. The
public failure copy replaces only its owned absolute source prefix. Private TLS
state remains local and uncommitted. The next diagnostic must use its committed
instrument and a distinct bounded diagnostic receipt; it does not inherit a full
acceptance PASS. A separate read-derived generator concern—production images prune
the development-only stock client—is being resolved in the instrument before any
paid retry.
