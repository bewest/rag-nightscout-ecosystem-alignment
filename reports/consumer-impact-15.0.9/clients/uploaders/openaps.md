# openaps (toolkit) — Nightscout API use

All findings are **read-derived**. Nothing was run.

- Repo: `externals/openaps`
- Ref analysed: `origin/master` **bd9a831** (2020-02-25). `origin/dev` 84628a1 (2017-07-15) is older
  than master; not separately analysed.
- Local checkout: HEAD bd9a831, behind=0, dirty=0.

## Finding: no Nightscout HTTP client in this repo

openaps is the report/device framework. It has no HTTP library import and builds no Nightscout
URL. Rigs reach Nightscout through an openaps `process` device named `ns` whose command is
oref0's `bin/nightscout.sh` (registered by `nightscout autoconfigure-device-crud`,
oref0@88cf032a `bin/nightscout.sh:337-342`). **Every Nightscout request an openaps rig makes is
therefore mapped in `oref0.md`.**

**Positive control** (the grep reaches openaps' vendor code and Nightscout-related formatting):
`openaps@bd9a831 openaps/vendors/dexcom.py:446` (`adjust_nightscout_dates`), `:825`
(`class nightscout_calibrations`), `:761` and `openaps/vendors/medtronic.py:587`
(`dict(count=int(args.count))` — the **device** record count for Dexcom/Medtronic reads over USB,
not a Nightscout parameter).

Patterns searched (`git grep -n -i -E <pat> origin/master -- .`): `api/v1`, `api/v2`, `api/v3`,
`nightscout`, `count=`, `find\[`, `api-secret`, `api_secret`, `verifyauth`, `socket.io`, `_id`,
`import requests`, `urllib`, `httplib`, `http://`, `https://`, `curl `. The only `http(s)://` hits
are comment links (`openaps/cli/__init__.py:86`, `:96`; `openaps/vendors/dexcom.py:448`, `:498`, `:541`).

| S-id | what the client does | anchor | patterns searched |
|---|---|---|---|
| S1–S15 | None found: no Nightscout request is made by this repo. `dexcom.py` formats records for Nightscout (dates) but does not send them. | `openaps/vendors/dexcom.py:446-500`, `:825-835` | as above |

## Worth cross-checking

None here; see `oref0.md` (the `ns` device).
