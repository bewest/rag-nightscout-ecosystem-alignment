# `bf/count-client-compat`: reads accept the count shapes OpenAPS and GluPredKit send

**OPENED 2026-09-24 as nightscout/cgm-remote-monitor #8761** (head `b4ead206`). A second commit,
`516f971a` (two settings, local, not pushed), follows. Branch `bf/count-client-compat` on `origin/dev`
`ddd9b600`. No `CHANGELOG.md` edit. The version stays 15.0.9. This implements the
maintainer's 2026-09-24 decision (queue item `RT-COUNT-COMPAT`; semver policy §3.2, "Decided
2026-09-24"). The posting copy is the text below the line.

---

15.0.9's `count` rule (#8738, amended by #8748) answers two real clients differently from 15.0.8. This change makes 15.0.9 read the shapes those clients actually send the way 15.0.8 did, so 15.0.9 can stay a patch release. Both shapes get a deprecation warning. Every other malformed count is still refused, and deletes are unchanged.

| what changes | who can see it |
|---|---|
| a read whose `count` is a whole number followed by `?` and other text, such as `1?token=…`, reads the number, where `dev` answers `400` | OpenAPS (oref0) rigs, on every loop |
| a read with `count=0` and a `find` that bounds one date field from both sides returns everything in that window, where `dev` returns an empty list | GluPredKit, and any tool that asks for "zero" meaning "all in this range" |
| a read with `count=0` and no such window returns the endpoint's default, as if no count had been given, where `dev` returns an empty list | any app or script that sends `count=0` without a range |
| two settings, `API_V1_COUNT_LEADING_NUMBER` and `API_V1_COUNT_ZERO_WINDOW`, both `true` by default; set to `false`, that shape gets `dev`'s answer | operators who want the stricter rule now, and the future release that flips the default |
| deletes: unchanged from `dev`. A delete whose count is `0` or not a whole number, a number followed by `?` included, is refused and deletes nothing | nobody; stated so a reviewer does not have to infer it |

## What changes for you

*Plain-language summary for people running their own Nightscout site. Nightscout is not a medical device and none of this is medical advice.*

- **OpenAPS keeps working as it does on 15.0.8.** OpenAPS asks Nightscout for its most recent treatment in a way that adds extra text after the number. Without this change, 15.0.9 refused that request. The rig then re-uploaded the last 24 hours of its pump history on every loop instead of only what was new. That caused no duplicate insulin or carbs, but it did mean that **an edit made in Nightscout to a treatment the rig had uploaded, such as an added note, was undone on the next loop**. With this change, the rig uploads only new records again.
- **GluPredKit gets its data again.** GluPredKit asks for "zero" records over a date range, meaning "everything in this range". Without this change, 15.0.9 answered with nothing, and its data download failed. It now gets everything in the range, as it did on 15.0.8.
- **Asking for zero records without a date range** now returns the usual default number of records, for example the last 10 glucose readings. On 15.0.8, this could return your whole history.
- **These two request forms are deprecated.** Answers to them carry a warning, and the server notes it once in its log. A future major release may refuse them. Nothing changes for you today. If you maintain one of these tools, send a plain whole number of 1 or more.
- **Each one can be turned off.** Two new settings control them. Both are on (`true`) unless you change them. You only need to change them if you want the stricter behaviour now:
  - `API_V1_COUNT_LEADING_NUMBER` covers the OpenAPS form. Set to `false`, it is refused with an error. **Don't set it to `false` if an OpenAPS rig uploads to your site.**
  - `API_V1_COUNT_ZERO_WINDOW` covers the GluPredKit form. Set to `false`, every request for zero records gets none.

If a tool you use stops working after the upgrade, report it to that tool's author with the tool's name and version, not your data. If your glucose data stops arriving, use your meter or CGM app and your usual routine while it is sorted out, and talk to your care team if you are unsure about any treatment decision.

## Technical detail

On `GET` and `HEAD` under `/api/v1`, `validateCount` (`lib/api/index.js`) now rewrites `req.query.count` before it checks it:

- **`N?<anything>` becomes `N`**, using `countParam.leadingCount` (`/^\s*(\d+)\?/`). oref0's `ns-get.sh` appends its credential to the query with a second `?`, so `count=1` arrives as `1?<credential>` or `1?token=<token>`. Only digits followed by `?` are accepted: `abc`, `-3`, `2.5`, `1e2`, `0x10` and `x1` are still `400`, with or without a `?` after them. **Neither the value nor what follows the `?` is logged or echoed**, since for oref0 it holds a credential.
- **Zero with a date window becomes `2147483647`**, the largest 32-bit limit and in practice no limit. `countParam.hasDateWindow` accepts a lower bound (`$gte`/`$gt`) and an upper bound (`$lte`/`$lt`) on the same one of `date`, `dateString`, `created_at`, `mills`, `sysTime`, `startDate`, `srvCreated` or `srvModified`. Every v1 read path already handles a numeric count, so no handler changed.
- **Zero without a date window is deleted from the query**, so each endpoint applies its own default: entries 10, profiles 10, treatments 100 (1000 with a `find`), devicestatus 10. Activity has no default and reads unbounded without a count, as it already does on `dev`.
- **Both rewrites set `Deprecation: true` and `Warning: 299 - "…"`**, naming the setting, and `console.warn` once per process per shape.
- **Each rewrite has a setting** in `lib/server/env.js`, read on every request: `env.apiV1CountLeadingNumber` (`API_V1_COUNT_LEADING_NUMBER`) and `env.apiV1CountZeroWindow` (`API_V1_COUNT_ZERO_WINDOW`). Both default to `true`. The comment says to switch them to `false` in a future release, as `ALLOW_UNRESTRICTED_FRAME_EMBEDDING`'s does. With one `false`, that shape meets #8748's rule unchanged: `1?…` is `400`, and `count=0` reaches the storage layer and returns `[]`. With only the zero setting off, `0?…` reads as `0` and returns `[]`. Both settings are documented in `README.md`, next to `UUID_HANDLING`.

The storage layer is unchanged. `lib/server/count.js` still answers a zero it is handed directly with no documents and never calls `.limit(0)`, so internal callers see what they saw before. Deletes, saves and updates keep #8748's rule.

What 15.0.8 did, for comparison: the string `"0"` is truthy, so the endpoint defaults were skipped and `.limit(parseInt("0"))`, which means no limit, reached the driver. The exceptions were devicestatus, which read `0` as 10, and treatments without a `find`, which could be served as an empty slice from the cache. `1?…` was read by `parseInt` as 1.

Two differences from 15.0.8 remain, both on shapes no client in the census sends:
- `count=0` without a window returns the default where 15.0.8 returned everything.
- devicestatus with `count=0` inside a window returns the whole window where 15.0.8 returned 10.

`/api/v1/profile` ignores `find`, as it did before, so a windowed `count=0` there returns every profile.

## Verifying it

With `--ulimit nofile=64000:64000` on every MongoDB container:

| check | result |
|---|---|
| `tests/api.count-parameter.test.js` | 49 passing |
| full suite (`npm test`), Node 20.20.0, 22.23.2 and 24.20.0 × MongoDB 4.4 and 7 | 2466 passing, 0 failing, 3 pending in all six cells (`dev` `ddd9b600`: 2453; +13 net new tests) |
| full suite at `516f971a` (with the settings), the same six cells | 2471 passing, 0 failing, 3 pending in all six (+5: four setting tests in the count suite, one in `tests/env.test.js`) |
| break-it: the settings ignored | 3 of the 4 setting tests fail; the fourth is a control |
| break-it: the rewrite call removed | 18 of the new tests fail |
| break-it: only the date-window rule removed | the 2 entries window tests fail. The other collections are seeded with fewer documents than their default, so they cannot tell the window from the default. |

The consumer-replay lab from the 15.0.9 survey replays each client's own requests against a running server. It was re-run on this branch with `AUTH_DEFAULT_ROLES=readable` and `denied`:

| probe | 15.0.8 | `dev` / candidate | this branch |
|---|---|---|---|
| oref0 latest-treatment, hashed-secret and token modes | 200 | 400 | 200 |
| oref0's own `jq`/`date` cull: records kept for upload | 1 | 57 | 1 |
| GluPredKit `count=0`, 50 h window: profile / treatments / entries | 1 / 137 / 576 | 0 / 0 / 0 | 1 / 137 / 576 |

The `count=100000` control returns the full window on all three builds.

Not yet run: a combined run with #8754 and #8758, and a real OpenAPS rig or GluPredKit install (the lab replays their requests, not the programs).
