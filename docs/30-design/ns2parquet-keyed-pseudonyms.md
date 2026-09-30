# ns2parquet keyed pseudonyms: design

**Status:** design, 2026-09-30. Not yet implemented. Follow-up to the site
publishing work on branch `site/phase1`.

## What changes

ns2parquet will make participant IDs with a keyed hash (HMAC-SHA256 under a
secret key) in place of today's unsalted hash. The key must stay the same
over time, so it is pinned in two places:

- the key itself, kept private outside git;
- a public key id, committed in the repo.

With the key id pinned, every tool refuses to run under a different key. That
stops IDs changing without anyone noticing. The same key and formula are
shared with the site build, so a participant gets the same pseudonym in a new
dataset as on the public site.

## Current state (measured at `main` 01c19311)

- **Nightscout sites.** `tools/ns2parquet/cli.py:23` makes opaque IDs as
  `ns-` plus the first 12 hex of `sha256("ns2parquet:" + normalized source)`.
  The source is the site URL (`ingest`, `batch_ingest`) or a directory name
  (`convert`, `convert-all`).
  - The prefix is a public constant, so the hash is unsalted.
  - Nobody can reverse an ID. But anyone who already knows or guesses a
    site's URL can compute its ID, then find that site's data in published
    research.
  - The docstring says "the source cannot be recovered from the ID". That is
    true of reversal, but not of confirming a guess.
- **Data commons.** `cmd_convert_odc` (`cli.py:611`) writes the commons' own
  participant ID (`odc-` plus 8 digits) unless `--opaque-ids` is passed, which
  is off by default. When it is passed, the same unsalted hash applies.
- **Spread in tracked text.**
  - 13 distinct `ns-` IDs across 83 files, 47 of them in
    `docs/60-research`.
  - Raw data-commons IDs in 203 files, 12 distinct.
  - The site build rewrites the data-commons IDs at publish time
    (`tools/site/pseudonym.py`). The `ns-` IDs are published as they are, by
    maintainer decision on 2026-09-30.
- **The IDs are persisted, not just displayed.** The `patient_id` column in
  every parquet dataset holds them (`externals/ns-parquet*`, untracked). So do
  the manifest (`manifest.json`, the `patients` list) and research documents.
  - `batch_ingest` skips sites whose ID is already in the grid (`already_done`,
    `batch_ingest.py:65-72`), and it retries auth failures by ID.
  - `merge` deduplicates by ID. Append depends on the ID being deterministic.
  - Experiment code, especially `tools/cgmencode`, hard-codes some raw
    data-commons IDs.

## Why the key must be pinned

A keyed hash is only as stable as its key. If the key is lost, regenerated, or
differs between two machines, every ID changes, and nothing fails:

- `batch_ingest` sees no ingested sites and fetches every site again as a
  new participant. That duplicates people in the grid, and cohort counts go
  wrong without any error.
- `merge` puts the same person's data under two IDs.
- Manifests and research notes that cite an ID stop matching the data.
- On the public site, every data-commons pseudonym changes on the next deploy.
  Readers' saved links and quotes break, and old and new builds can be
  compared to learn more.

So yes, a durable value has to be pinned, but not in git. The key must stay
secret: if it were published, the keyed hash would be no better than the
unsalted one. What goes in git is a **key id** that identifies the key without
revealing it, and every tool checks it.

## Design

### One scheme, one key

- **Formula** (scheme `hmac-sha256-v1`):
  - data commons: `odc-p-` + first 8 hex of `HMAC-SHA256(key, "odc-" + pid)`;
  - Nightscout sites: `ns-p-` + first 12 hex of
    `HMAC-SHA256(key, "ns:" + normalized source)`.

  The data-commons form is byte-for-byte what `tools/site/pseudonym.py`
  produces today. New datasets therefore carry the same pseudonym readers see
  on the site, and the site needs no rewriting for them.
- **Collisions.** 8 hex digits is 32 bits: a 50% collision chance needs
  about 65,000 participants. 12 hex digits is 48 bits. Both are ample. Tools
  must still check for collisions and fail when one appears.
- **New prefixes.** `odc-p-` and `ns-p-` differ from the legacy `odc-` and
  `ns-` forms. An ID shows which scheme made it, so old and new cannot be
  mixed up.
- **Normalization is unchanged.** Strip, drop a trailing `/`, lowercase.
  Leaving it as is keeps the crosswalk (below) straightforward.

### The private half: the key

- **Default location:** `~/.config/nightscout-alignment/pseudonym.key`, mode
  0600, holding 32 random bytes as hex (`openssl rand -hex 32`).
- **Override:** the environment variable `NS_PSEUDONYM_KEY`. The site build
  reads its key the same way; `SITE_PSEUDONYM_KEY` stays as an alias so the
  current Makefile still works.
- **Backup.** The maintainer keeps a copy somewhere durable, such as a
  password manager. A lost key means new datasets can't be joined to old
  ones, and the site's pseudonyms change.
- **No default key.** A tool that needs the key and doesn't find it fails.

### The public half: the key id

- **What is committed:** `tools/ns2parquet/pseudonym-scheme.json`:

  ```json
  {
    "scheme": "hmac-sha256-v1",
    "kid": "<first 16 hex of HMAC-SHA256(key, 'nightscout-alignment/kid/v1')>",
    "odc_hex": 8,
    "ns_hex": 12
  }
  ```

- **Why publishing it is safe:** the `kid` does not reveal the key, and it
  can't be used to compute any participant's ID.
- **Who checks it:**
  - ns2parquet (`convert*`, `ingest`, `batch_ingest`, `merge`) computes the
    local key's kid and refuses to run on a mismatch. The message names both
    kids.
  - The site build refuses too, so a new key can't reach the public site
    unnoticed.
- **Where else it is recorded:**
  - Each dataset's `manifest.json` gains `id_scheme` and `kid`.
  - `merge` refuses to combine datasets with different schemes or kids,
    unless it is given a crosswalk.
  - The site's `build/site-report.json` records the kid.
- **Changing the key on purpose** (for example, after a leak) is an explicit
  step: a new kid in `pseudonym-scheme.json`, a crosswalk for existing
  datasets, and a note in the commit message that every site pseudonym will
  change.

### Existing data: leave it, add a private crosswalk

- **Tracked documents are left as they are.** Their legacy `ns-` IDs stay
  published, by the 2026-09-30 decision. Their raw data-commons IDs stay in
  the repo and are rewritten on the site, as today.
- **Existing parquet datasets are not rewritten in place.** Their manifests
  are marked `id_scheme: legacy-sha256-v0`, with no kid.
- **A crosswalk command.** `ns2parquet crosswalk --dataset <dir>` writes a
  legacy-to-v1 map for a dataset. The map is private: it goes into the dataset
  directory, which sits under the untracked `externals/`, and is never
  committed. The command needs the key and refuses to write inside a
  git-tracked path.
- **Joining old and new.** `merge --crosswalk <file>` renames legacy IDs to
  v1 while merging, so old and new data can be joined under one scheme.
- **Legacy input stays accepted,** so existing experiment code and the
  hard-coded IDs in it keep working against legacy datasets.

### Defaults

- `convert-odc` writes v1 pseudonyms by default. Raw commons IDs need an
  explicit `--raw-ids`, which warns that the output must not be published.
- `convert` and `convert-all` switch `--opaque-ids` to default on, under v1.
  Raw directory names need `--raw-ids`.
- `ingest` and `batch_ingest` already use opaque IDs; they switch to v1.
  - `batch_ingest`'s "already done" check has to work on both schemes. For a
    legacy grid it computes both the legacy ID and the v1 ID of each URL, so
    switching schemes does not re-ingest every site.
  - This is the one place where the switch-over could cause the duplicate
    ingestion described above, so it needs its own test.

## Tests

The tests use throwaway keys in a temp dir only.

- **Determinism.** The same key and input give the same ID. A different key
  gives a different ID. The prefix and length match the scheme.
- **Same as the site.** v1 `odc-p-` IDs are equal to
  `tools/site/pseudonym.py` output for the same key. Both must import one
  shared function, or a test pins them together.
- **Key id gate.** A mismatched key makes every entry point refuse. So does
  a missing key.
  - Break it to prove it: comment out the check and show the test fails.
  - Pair it with the matched-key run.
- **Crosswalk.** The crosswalk covers every legacy ID in a fixture dataset.
  `merge --crosswalk` output equals a fresh v1 conversion of the same input.
- **No re-ingest after the switch.** `batch_ingest` over a legacy grid with
  the v1 scheme skips every already-ingested site. This is the one where
  silent duplicates would come from.
- **Collision.** Two inputs forced to one truncated ID make the tool fail.
- **Existing test.** `test_ns2parquet.py:42` tests `_generate_opaque_id` for
  determinism. It stays, under a legacy name, and a v1 counterpart is added.

## Decisions and open points

Decided by the maintainer on 2026-09-30:

1. **One key** for ns2parquet and the site. New datasets therefore match the
   site's pseudonyms, and there is one secret to keep. The cost is that one
   leak affects both.
2. **Existing datasets stay legacy.** They are not regenerated under v1.
   Their manifests are marked `legacy-sha256-v0`, and the crosswalk joins
   them to v1 data when needed.

Still open:

3. **Should the site also rewrite legacy `ns-` IDs** to `ns-p-`, now that
   there will be a key? That would close the guess-a-URL gap on the public
   site too. It reverses the 2026-09-30 "publish as-is" decision, so it is
   the maintainer's call.
4. **Is 8 hex enough** for data-commons pseudonyms? It matches the site
   today. A longer form would change the site's current pseudonyms once.

## Work items

1. Shared `pseudonym` module: the formula, key loading and kid, used by
   ns2parquet and `tools/site`.
2. `pseudonym-scheme.json`, and the kid check at every entry point.
3. Scheme and kid in manifests; `merge` refuses mixed schemes or kids.
4. `crosswalk` command, and `merge --crosswalk`.
5. New defaults; the `--raw-ids` opt-out with its warning.
6. The dual-scheme "already done" check in `batch_ingest`.
7. Tests, as above.
8. README and DATA_DICTIONARY updates; the site README points to the
   shared key.
