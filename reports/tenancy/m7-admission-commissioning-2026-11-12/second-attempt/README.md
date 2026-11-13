# Second admission commissioning attempt

**Reproduced: bootstrap and private plan-view validation passed; the first API exited during health checking.** Exact source, image, runner and plan are in [the selected summary](summary.json). The [first attempt](../first-attempt/README.md) retains its separate bootstrap failure.

The repaired mount path was exercised successfully, followed by controller bind and admin startup. API2, tagged capture and controlled restart were not reached. PostgreSQL recorded one preauthentication timeout; the API’s sanitized startup message does not establish which constructor or typed error caused it.

An independent whole-project census matched the exact retained PostgreSQL, Vault, admin and API identities and confirmed all four stopped. Admin’s generation is retired; API’s generation remains issued with its credits held. Stopped containers do not grant API retirement. Original run/state remain unchanged and raw captures stay outside Git.

A separate actual-driver recording reproduced a concrete core074 bug: spreading pg-pool options loses its non-enumerable password on the API’s separate-field operation-pool path. The selected client then refuses a synthetic SCRAM challenge; URL and unselected controls succeed. Descriptor-preserving source repair `d0036890d0623ae79f14bfa71e7226c0fa122a29` passes that recording discriminator without network activity. This is source/driver evidence, not attribution of the original hidden startup error or new runtime acceptance. The next candidate requires a coherent source/deployment/image/profile/instrument freeze and fresh state.

Full clinical, capacity and production acceptance remain unmeasured.
