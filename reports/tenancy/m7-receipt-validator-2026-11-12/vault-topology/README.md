# Vault topology attribution follow-up

Exact source `e62e7c865b60f89e37495a50e0d55247c594e001`, following original validator/evidence `8749ef63e467bbc40a603a22e3f991bff1ae26a9`. Coordinator review corrected a topology assumption: the default Compose capacity profile runs a Vault server; Vault Agent is an opt-in overlay. Earlier evidence remains immutable.

Base capacity inventory now requires logical `vault` server, with a separate optional `vault-agent` group. They cannot share the same service label. The broad scaling component set still requires actual Vault Agent proof. Its source-specific contract pins Agent service names, requires those roles to be present in each observed configuration, and requires sample/metric selectors underneath those observed role dictionaries, disjoint from the pinned server names. Server observations cannot be relabelled Agent observations. No overlay is activated by this checker.

[Exact focused capture](focused-exact.txt): **44 tests pass**. Synthetic temporary-record controls show server-only capacity passes its honest milestone scope, does not satisfy broad scaling, and refuses both relabelled server-as-Agent and missing actual Agent observations. Existing source/identity, inventory, numeric metric and read-only controls remain green. There is no actual capacity/Agent measurement or production PASS receipt in this record.

No producer, queue, release, decision, deployment transport or core source changed. Root owns integration and future source-paired proof selection. The incoming profile lane will record default versus selected-overlay topology explicitly, without activating Agent or inventing its metrics.
