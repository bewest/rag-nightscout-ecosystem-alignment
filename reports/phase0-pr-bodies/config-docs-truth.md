<!-- Draft body, branch bf/config-docs-truth at c102d98f (five commits on dev ca6fcfaf). Local only: not pushed, no PR opened. This comment is hidden on GitHub. -->
The documentation and configuration information now match what the code reads: the API v3 settings (BF-46), the webhook plugin's settings (BF-48), the HSTS sub-domains spelling (BF-49), the entries collection name (BF-50) and the Azure template's Node version (BF-51). Five commits on `dev` `ca6fcfaf`, one per register id. No `.js` file changes, so Nightscout's behaviour does not change, with one exception: a new Azure deployment from `azuredeploy.json` now gets the Node version its form asks for.

## What changes for you

*A plain-language summary for people who run their own Nightscout site, for themselves or for a family member. Nothing here is medical advice.*

**What was wrong.** Some settings that Nightscout reads were not written down anywhere an operator would look, and some that were written down were wrong:

- **API v3 settings.** Nightscout's newer API (API v3, used by apps such as AAPS) reads ten settings whose names begin `API3_`, and the README listed none of them. Six of them, `API3_AUTOPRUNE_ENTRIES` and five others, **permanently delete** your stored records older than a number of days you choose. `API3_AUTOPRUNE_ENTRIES` covers your glucose history. They are off unless someone sets them.
- **Webhook plugin.** The plugin that sends each new glucose reading to another server has four address settings that were not documented.
- **HSTS sub-domains setting.** The setting is `SECURE_HSTS_HEADER_INCLUDESUBDOMAINS`, with `INCLUDESUBDOMAINS` as one word. Spelled with an underscore before `SUBDOMAINS`, it does nothing. The README already used the working spelling but did not say the other one fails.
- **`MONGODB_COLLECTION`.** The README listed it as a required setting. Nightscout has never read it. The settings that do pick the collection for CGM entries are `ENTRIES_COLLECTION` and the older `MONGO_COLLECTION`.
- **Azure one-click deployment.** The template asked for a Node version but always used Node 8.11.1, whatever you entered. The README told Azure users to use Node 16.16.0. Neither version is supported any more.

**What this change does.** The README now lists each of these settings with its default, the spellings Nightscout accepts, and what it does. For the `API3_AUTOPRUNE_` settings it says plainly what is deleted, when, and that it cannot be undone. The Azure template now uses the Node version on its form, which defaults to Node 22.

**Do you need to do anything?** Check whether any `API3_AUTOPRUNE_` setting is set on your site. Look in your hosting service's settings, which may be called Config Vars, environment variables or app settings. If one is set and you did not mean it to be, remove it and restart Nightscout. Records already deleted cannot be brought back by Nightscout, so if you need them, restore them from your own database backup. If you set `MONGODB_COLLECTION`, it never had any effect: your entries are in the collection named by `ENTRIES_COLLECTION` or `MONGO_COLLECTION`, or in `entries` if neither is set. Otherwise, no.

## Technical detail

### BF-46 · the API v3 settings (`ae41d611`)

What the code reads, at `ca6fcfaf`:

- `lib/api3/index.js:20-34` `setENVTruthy` reads `process.env` directly, not through `lib/server/env.js`. It tries `CUSTOMCONNSTR_<NAME>`, `CUSTOMCONNSTR_<name>`, `<NAME>` and `<name>` in that order, and the first non-empty value wins. `on` and `true` become `true`, `off` and `false` become `false`, in any case; anything else is kept as a string, so for the three switches whose default is `true`, only `false`/`off` turns them off.
- `:66` `CI`, read as `process.env['CI']` only, together with `NODE_ENV` (`app.get('env')`, which Express defaults to `development`), gates the `/api/v3/test` route at `:80-81`.
- `:69-72` read `API3_SECURITY_ENABLE`, `API3_DEDUP_FALLBACK_ENABLED`, `API3_CREATED_AT_FALLBACK_ENABLED` and `API3_MAX_LIMIT`, with defaults from `lib/api3/const.json:3-6` (`true`, `true`, `true`, `1000`).
- `lib/api3/security.js:15`: with security off, every request is given the `*` permission.
- `lib/api3/generic/collection.js:77`: `parseInt(API3_MAX_LIMIT) || 1000` is both the default and the ceiling, for search and history.
- `:31` and `lib/api3/generic/setup.js`: the dedup fallback fields for each collection; settings has none.
- `:176-200` `parseDate`, called on create and update but not on patch: the `created_at` fallback.
- `:32` and `:137-169` autoprune. `API3_AUTOPRUNE_<COLLECTION>` for the six collections in `index.js:67`, without a default. It runs only when the value is a number above zero, and deletes with `$or` over `srvCreated`, `created_at` and `date` older than *days* × 24 h. It is called from `create/insert.js:51`, `update/replace.js:63`, `patch/operation.js:99` and `delete/operation.js:69,97`, after the request succeeds. The first such request after start runs it at once, and after that it runs at most once an hour for each collection. There is no timer.

The README gains an **API v3 (optional)** section that documents the eleven names (the ten `API3_*` plus `CI`). The API v3 swagger description (`lib/api3/swagger.yaml`, and the same text in `swagger.json`) used to keep its own list. That list said *"default is only `DEVICESTATUS`=60"*, which the code has never done (no default at `collection.js:32`, here or in the commit that introduced it, `2dd576a6`). The description now points at the README section, so the README is the only place these settings are described. `lib/api3/doc/security.md:30` already agrees with the README and is unchanged.

Not changed: the names still do not go through `env.js`, and the delete is still not awaited. Both are code changes; see *Open points*.

### BF-48 · the webhook plugin (`87cd365b`)

`lib/plugins/webhook.js:36-39` reads `WEBHOOK_PROTOCOL` (`http`), `WEBHOOK_HOST` (`localhost`), `WEBHOOK_PORT` (`3000`) and `WEBHOOK_PATH` (`/nightscout`) from `process.env` with `||` defaults. Only these exact upper-case names are read. The plugin is registered on the server at `lib/plugins/index.js:106` and runs only when `webhook` is in `ENABLE` (`register`, `:214-232`). The README gains a `webhook` entry under *Plugins*. It covers the payload (`source`, `mgdl`, `mills`, `iso`), the startup skip, the 5-second timeout and retry-while-latest, and the fact that the request carries no credentials. All of these were read from the same file.

### BF-49 · the HSTS sub-domains spelling (`7a08fb5f`)

`lib/server/env.js:89` reads `SECURE_HSTS_HEADER_INCLUDESUBDOMAINS`, and `lib/server/app.js:115` uses it. `lib/settings.js:48` key `secureHstsHeaderIncludeSubdomains` makes `nameFromKey` (`:190`) ask for `SECURE_HSTS_HEADER_INCLUDE_SUBDOMAINS`. That value is stored in `env.settings` and read by nothing in `lib/`, `views/` or `static/`. The README entry now says the name is one word and that the underscored form has no effect. No alias was added. The other four dead settings keys (`insecureUseHttp`, `secureHstsHeader`, `secureHstsHeaderPreload`, `secureCsp`, `settings.js:46-50`) generate the same names `env.js` reads, so the README is already right for them; they are dead only as settings-dictionary entries.

### BF-50 · `MONGODB_COLLECTION` (`5d2a584e`)

`git grep MONGODB_COLLECTION` at `ca6fcfaf` finds only the README line. `lib/server/env.js:155` reads `ENTRIES_COLLECTION`, then `MONGO_COLLECTION`, with the default `entries`. The line moves out of *Required* and is replaced under *Core* by `ENTRIES_COLLECTION` with its `MONGO_COLLECTION` fallback. `azuredeploy.json` already sets `MONGO_COLLECTION`, so it needed no change.

### BF-51 · the Azure template's Node version (`c102d98f`)

At `ca6fcfaf`, `azuredeploy.json` declared `WEBSITE_NODE_DEFAULT_VERSION` (default `16.16.0`) and set the app setting to the literal `8.11.1`. Nothing referenced the parameter. The app setting is now `[parameters('WEBSITE_NODE_DEFAULT_VERSION')]` and the default is `~22`. Why 22:

- `package.json` `engines` asks for `>=20.x`, and CI tests 20, 22 and 24.
- `.nvmrc` and the `Dockerfile` both pin 22.
- Node 20 reached end of life on 2026-04-30.

The README's Azure note asked for `16.16.0`, which `engines` no longer allows. It now asks for `~22`, and its garbled first sentence is repaired. The template still parses as JSON. This is the one change here that affects a deployment: a new one-click Azure deployment gets the Node version on its form rather than 8.11.1. Existing Azure sites keep their own app settings.

## Gates

The gates are `tools/queue/gates/config-surface-census.js` in the alignment repository, five arms. They ran with `--ref` and with `QUEUE_GATE_ROOT` pointing at this worktree, so that the `hsts` arm, which `require`s `lib/settings.js` from the working tree rather than from `--ref`, measures this branch.

| arm | `ca6fcfaf` | this branch | why |
|---|---|---|---|
| `readme` (BF-50) | red | **green** | README no longer names `MONGODB_COLLECTION` |
| `azure` (BF-51) | red | **green** | the parameter is referenced once |
| `api3` (BF-46) | red | red | needs the names in `lib/server/env.js` too, and checks that the delete is awaited; both are code changes |
| `webhook` (BF-48) | red | red | needs the names in `lib/server/env.js` too |
| `hsts` (BF-49) | red | red | measures whether `env.js` reads the name `nameFromKey` produces; only a code change satisfies it |

Each arm's control is green on both refs. To show that the README half of `api3` and `webhook` is met, both arms were re-run with `--envjs` pointing at a copy of `ca6fcfaf`'s `env.js` with the fourteen names appended as a comment. Against `ca6fcfaf`'s README, every name is still reported absent (10 of 10 and 4 of 4). Against this branch's README, none is (0 of 10, 0 of 4). The `api3` deletion check stays red either way.

## Tests

No test file is added or changed. No test reads `README.md` or `azuredeploy.json`. The one README-derived check, `tests/plugins.test.js`, reads the `ENABLE` feature list, and this branch does not touch it.

### Validation (Node 24.15.0, MongoDB 7.0.43 in a dedicated container)

- `npm ci` clean.
- Full suite (`ci.test.env` form, at `c102d98f`): 3534 passing, 0 failing, 4 pending. The base `ca6fcfaf` was not re-run on this machine; no test was added or removed.
- `azuredeploy.json` and `lib/api3/swagger.json` parse as JSON, and `lib/api3/swagger.yaml` parses with `js-yaml`. The two swagger descriptions are identical, and `git diff --check` is clean.

## Open points

- **The autoprune delete, unawaited (BF-156; a separate fix, after 15.0.9).** Reproduced in process, without MongoDB, using the shipping `Collection` and `CachedCollectionStorage` with only the Mongo layer faked. `collection.js:157` passes a callback that `deleteManyOr` (async, one argument) never calls, so the "Auto-pruned N documents" line is never logged. When the delete rejects, the rejection is unhandled, and on Node 24 the process exits with code 1. A database error during an autoprune would therefore end the server. Recommended fix: `.then`/`.catch` on the returned promise. This is a code change and is not made here.
- **Routing `API3_*` and `WEBHOOK_*` through `env.js`.** This is what the `api3` and `webhook` arms still measure. It is a configuration-surface change, and minor under semver.
- **An alias for `SECURE_HSTS_HEADER_INCLUDE_SUBDOMAINS`.** This would be a one-line change in `lib/server/env.js`, not in `settings.js`. A deployment that already sets the underscored name would start sending `includeSubDomains`, so it changes behaviour, and it is left for a decision.
- **Azure `~22`.** Not checked against a live Azure deployment: the runtimes Azure offers were not looked up. The `rt/cut1` line uses `~24`, and the two will meet when cut 1 is rebased.
