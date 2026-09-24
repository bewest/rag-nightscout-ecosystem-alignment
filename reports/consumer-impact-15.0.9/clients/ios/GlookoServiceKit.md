# GlookoServiceKit — Nightscout API surface

All claims **read-derived** (git grep/show on the ref; nothing run).

- Repo: externals/GlookoServiceKit
- Ref analysed: `origin/main` **8e2cad1** 2026-06-27 (only remote branch)
- Local staleness: behind=0, dirty=0

## Finding: no Nightscout surface

GlookoServiceKit is a LoopKit `RemoteDataService` plugin (Trio/Loop) that uploads the user's data
**to Glooko**, not to or from Nightscout (`README.md` at the ref: "uploads Trio (and Loop) diabetes
data to Glooko"). Its hosts are Glooko's own: `GlookoServiceKit@8e2cad1
GlookoServiceKit/Core/GlookoConstants.swift:11,12,18,20`. Its socket.io client
(`GlookoServiceKit/Data/Transport/GlookoSocketIO.swift`, a hand-written `URLSessionWebSocketTask`
client with `EIO=4`) connects to the Glooko XT host, not to Nightscout.

### Positive control

`git grep -n -I -i 'https://\|/api/v[23]' origin/main -- GlookoServiceKit` reaches its network code:
`GlookoServiceKit/Data/Classic/GlookoClassicAPI.swift:73,92,110,125,154,168` (Glooko `/api/v2/users/sign_in`,
`/api/v2/<endpoint>`, `/api/v3/device/file/upload`) and `GlookoConstants.swift:11-20`. The same method
finds no Nightscout path.

### Patterns searched (whole tree at the ref), all with no Nightscout hit

`nightscout` (only bundle identifiers `org.nightscout.*` in `project.pbxproj` and a keychain prefix in
`Data/Auth/GlookoCredentialStore.swift:13`), `api/v1`, `api-secret`, `entries`, `treatments`,
`devicestatus`, `profile`, `count=`, `find[`, `$exists`, `$in`, `token=`, `verifyauth`,
`notifications/loop`, `socket` (Glooko only).

| S-id | what the client does | anchor | patterns searched |
|---|---|---|---|
| S1 | none found (no Nightscout requests) | — | `count`, `count=` |
| S2 | none found | — | `find[`, `$exists`, `$in`, `$regex` |
| S3 | none found | — | `find[`, `$gte`, `$lte` |
| S4 | none found | — | `api/v1/count`, `times`, `slice`, `echo`, `properties`, `ddata`, `status`, `verifyauth` |
| S5 | none found for Nightscout (Glooko JWT/cookie auth only) | GlookoConstants.swift:11-20 | `api-secret`, `token`, `Bearer`, `authorization` |
| S6 | socket.io used only against Glooko XT (`EIO=4`, own client, no library); **not** Nightscout | GlookoServiceKit@8e2cad1 Data/Transport/GlookoSocketIO.swift:24-37 | `socket`, `EIO`, `authorize`, `dataUpdate` |
| S7 | none found | — | `_id`, `identifier` (Nightscout sense) |
| S8 | none found | — | `treatments`, `PUT`, `DELETE` against NS |
| S9 | none found (Glooko `/api/v2/foods` is Glooko's API) | GlookoClassicAPI.swift:154 | `food`, `quickpick` |
| S10 | none found | — | `profile` |
| S11 | none found | — | `cob`, `iob`, `devicestatus` |
| S12 | none found | — | `$in`, `[]=` |
| S13 | none found (Glooko `/api/v3/...` paths are Glooko's) | GlookoClassicAPI.swift:110,125,168 | `api/v3` |
| S14 | none found | — | `notifications/loop`, `ack`, `alexa` |
| S15 | none found for Nightscout | — | `statusCode`, `400` |

## Join questions

None. GlookoServiceKit is not affected by any cgm-remote-monitor change. (It runs inside Trio/Loop,
so a user of it is affected only through that app's own Nightscout uploader.)
