# Admission commissioning passed

**Reproduced: commissioning passes on exact cored003/deploymentd831/image9366.** The [selected summary](summary.json) pins source, image, reviewed runner, collector and plan. The [first](../first-attempt/README.md) and [second](../second-attempt/README.md) attempts retain their failures.

Bootstrap and private plan-view validation succeeded. Admin, API and API2 passed their actual shipped health checks without consuming another startup claim. One API stopped normally, received its exact clean retirement acknowledgement, restarted as a new generation and passed health again. All four started generations retired with matching ACKs.

Three charged captures bracket startup, restart and final retirement: held generations 3/3/0 and authenticated tagged clients 20/19/0; unmanaged clients were zero. PostgreSQL’s configured maximum was 314 with three superuser-reserved slots. These are scoped observations: a census cannot see preauthentication, infer historical peaks or refund credits. The configured eleven-slot/sixteen-tenant profile is not a measured production envelope.

An independent whole-project census matched the five exact retained PostgreSQL/Vault/admin/API/API2 identities, all stopped with exit code zero. The replaced old API container was independently absent. Cleanup did not grant retirement; the source/controller/ACK protocol did. Both earlier failed states remain unchanged. Raw captures and private identifiers remain outside Git.

Full clinical/cold-storm/whole-cohort/TIME/isolation/count-CLI qualification is still unmeasured. The repaired core also needs its own coherent full source/browser/enabled-corpus campaign and final prcheck; core K’s earlier result stays attributed to core074.
