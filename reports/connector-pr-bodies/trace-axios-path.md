<!-- DRAFT: not yet opened as a pull request. Branch fix/trace-axios-path, commit 894b132, based on dev 1946beb. -->

# DRAFT: Load the capture tracer from lib/ in the Nightscout and Dexcom Share sources

## Who this affects

Only people who run the connector's **capture** command by hand. Capture is a troubleshooting tool that records the connector's web requests to files. For example: `nightscout-connect capture ./har --source nightscout` or `--source dexcomshare`.

With either of those two sources, capture crashed as soon as it started, with `Error: Cannot find module '../../trace-axios'`. It crashed before sending any request, so no recording was made.

**Nothing changes for anyone who runs the connector inside Nightscout** (the usual setup, with `CONNECT_SOURCE` and related settings) **or with `nightscout-connect forever`.** Neither of those loads the file this fix touches, so data syncing was never affected. Glooko, Minimed CareLink and LibreLinkUp capture were already working.

## What changed

`lib/sources/nightscout.js` and `lib/sources/dexcomshare.js` both loaded `require('../../trace-axios')`. From `lib/sources/`, that path points at a `trace-axios` file in the repository root, and no such file exists. The module is `lib/trace-axios.js`, so both now use `'../trace-axios'`, the same path `librelinkup.js` already uses. Glooko and CareLink live one directory deeper (`lib/sources/<name>/index.js`), so `'../../trace-axios'` is the right path for them.

The require only runs when capture starts: the loop's `tracker` becomes `capture.start` in `lib/builder.js`, and it is called from `startCapture` in `lib/machines/cycle.js`. That is why the existing tests never loaded it. This bug is also present in v0.0.13.

## Evidence

- **Before (dev 1946beb):** both commands exit 1 with `MODULE_NOT_FOUND`. The stack goes through `tracker_for` (`nightscout.js:190` / `dexcomshare.js:243`) and then `cycle.js:76`. Both were run with a dummy source at `127.0.0.1:9` and `--output filesystem`.
- **After (this branch):** both commands start capture and keep running. The only errors are the expected authentication failures against the unreachable dummy source.

## Test

New file `test/capture-tracker.test.js` with two tests:

1. For every source registered in `lib/sources/index.js`, it runs `generate_driver`, then starts the `tracker` of each registered loop and checks that it returns a HAR tracer. A source added later is covered automatically. The test also requires the five current vendor sources to register a tracker, so it cannot pass by finding nothing to check.
2. It checks that every literal relative `require` in `lib/` and `commands/` resolves (73 today; the test fails if it finds 20 or fewer).

On dev both tests fail: the first with `MODULE_NOT_FOUND` from `nightscout/NightscoutEntries`, the second naming `lib/sources/dexcomshare.js:243 require('../../trace-axios')` and `Cannot find module`. Two deliberate breaks both fail both tests, and each failure names the file:

- putting the wrong path back in `dexcomshare.js` gives `dexcomshare/DexcomShare tracker failed to start: Cannot find module '../../trace-axios'`
- changing Glooko's correct path to `'../trace-axios'` gives `glooko/Glooko tracker failed to start`

Suite (`node --test test/*.test.js`):

| Node | dev 1946beb | this branch |
|---|---|---|
| 20.20.0 | 289/289 | 291/291 |
| 22.23.2 | 289/289 | 291/291 |
| 24.20.0 | 289/289 | 291/291 |

## Not in this change

A check of every literal relative `require` in the repository (175 of them, outside `node_modules`) found no other broken path. A few `scripts/` lab tools load Nightscout files through a path given on the command line. They are developer-only and were not changed.
