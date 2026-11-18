# Private commissioning population selection

The private phase603 commissioner needs an additive projection for an authored
`profile.population.maxTenants`. The reviewed public binding already refuses a
dropped or changed explicit selection. Its refusal must remain in force.

[commissioning_population.py](commissioning_population.py) creates a fresh source
copy and applies the fixed [population patch](commissioning-population-ceiling.patch).
It verifies the original overlay, preflight, private receipt validator and
preparation constructor by SHA-256 before creating the output directory. It also
checks the patch hash. An existing output or different source refuses; there is
no in-place mode. The original private source and entered cases stay unchanged.

The copy receives the selected instrument's `frozen.py` and the five Python
modules it imports for population/primer validation. Their hashes and the new
private source file hashes are recorded in `population-commissioner.json`.
These are existing receipt validators; copying them performs no image probe or
provider operation. The selected instrument remains the source for their bytes.

```bash
python3 -B tools/mt-bench/kubernetes/commissioning_population.py \
  --source /absolute/private-phase603 \
  --preparer /absolute/prepare-private-case.py \
  --out /mounted/artifacts/lane/fresh-commissioner
```

The new preparation constructor derives `populationCeiling` from the existing
validated intent. It adds no second population option. Omission emits no field
and refuses an inherited, undeclared ceiling in the base environment. The
overlay passes only that optional field into `binding.new`; its default output
and inventory retain the original bytes on the same unselected source context.

Use the fresh constructor with its fresh `--commissioner` directory. Its optional
`--jsonnet /absolute/jsonnet` selects the existing local compiler when the new
source copy has a different artifact layout. Omission keeps the historical
relative compiler path. Record the selected compiler hash and actual render
proof; this option supplies no cluster or delivery authority.

Private static preflight joins the intent, selected receipt validator, private
environment, immutable rendered source contract and bootstrap environment. An
old validator that ignores the ceiling refuses. Dropping, changing or duplicating
the rendered bootstrap value also refuses. With an explicit source-supported
ceiling, the existing tenant-count check uses that ceiling; omission retains
10,000. Other deadlines, resources, ownership, source-image proof and clinical
checks retain their existing contracts.

Apply this materialization first to the exact private phase603 base. Subsequent
private patches belong to their own owners:

| Patch | Integration boundary |
|---|---|
| `commissioning-owned-worker.patch` at `2ab951511f39a9f807d2e95cebac3a531c1af7fd` | Apply at the fresh directory containing `ops/` and `prepare-private-case.py`; install the worker owner's helpers and proof separately. |
| `commissioning-node-memory.patch` at `c834e8d03cbd62779e0e2768f4d7e2baf49e6cab` | Apply within the fresh `ops/staging-k8s/`; install the memory owner's helpers and proof separately. |

Population source hunks commute with each of those exact patches. Focused
controls compare both patch orders and run the actual population preparation
with each peer patch present and its optional peer setting omitted. This does
not qualify selected worker or memory authority, their mutual combination, or a
later peer patch. Those remain separate source/receipt integration boundaries.
There is no new gate on an existing normal or local run.

Run the focused external-source controls with the exact source packet and
compiler. Missing inputs explicitly skip; a skip is not qualification:

```bash
K8S_POPULATION_COMMISSIONER=/absolute/private-phase603 \
K8S_POPULATION_PREPARER=/absolute/prepare-private-case.py \
K8S_POPULATION_PACKET=/absolute/selected-population-packet \
K8S_POPULATION_JSONNET=/absolute/jsonnet \
K8S_POPULATION_SCRATCH=/mounted/artifacts/lane/offline-controls \
python3 -B -m unittest discover -s tools/mt-bench/kubernetes \
  -p test_commissioning_population_ceiling.py -v
```

These controls exercise the real private compiler, constructor, static preflight
and stage writer with a planned delivery and an inert synthetic native template.
Known-bad projection, source, validator and preflight controls must refuse and
restore. They create no Docker, Kubernetes or provider actor. Actual delivery,
configuration readback and capacity remain separate operator measurements. The
population ceiling also remains distinct from the primer's pending chunk budget.
