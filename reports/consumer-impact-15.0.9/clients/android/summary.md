# Android clients — join-step summary (from the agent's hand-back, saved by the main session)

Refs: AndroidAPS master 598e2eb39c 2026-08-02 (3.4.2.6), dev 7e1d537d49 2026-09-23 (4.0.0-dev-c; v1 socket client removed by 30fe4591a7 "Eliminate NSCv1", v3 on Ktor). xDrip master 1ed760048 2026-09-18 (no dev branch). All read-derived.

Ranked:
1. AAPS v3 `/alarm` socket (master NSClientV3Service.kt:184-199,343-346; dev NsConnectHandler.kt:78-89): the candidate (alarmSocket.js@ef3404fd:141-153) sends alarms only to tokens with `api:*:read` and drops `ack` without `notifications:*:ack`; subscribe still replies success. Join: which token role do AAPS setup docs prescribe?
2. xDrip treatment PUT/DELETE by its own lowercase 24-hex `_id` (NightscoutUploader.java:245-256,880-903,810-847): #8758 fixes the duplicate-on-PUT and DELETE-miss for string-`_id` records. Join: one record after PUT, DELETE removes both forms.
3. AAPS v1 socket (3.4.x only): authorize {secret sha1, history 48}; never loadRetro/dbRemove; reads `[0]._id` from dbAdd reply. Join: dbAdd reply still carries `_id`. socket.io-client 2.1.2 (EIO=4 inferred); server allowEIO3 true on every ref. AAPS v1 `ack` on main namespace was never handled by any server version (pre-existing).
4. xDrip follower: any 4xx on `devicestatus.json?count=1` disables devicestatus polling 6 h (NightscoutFollow.java:193-216). Join: can the candidate newly 4xx it?
5. 400 handling: AAPS v3 treatments/entries skip the record permanently; devicestatus/profile stall and retry; xDrip entries retry forever. Neither client's requests hit the new 400s (S1 counts 10/2880/1; S2 only `find[date][$gt]`, `find[uuid]`; no `$in`; v3 limits 500/1000/10/1/100).
6. AAPS v3 paging never uses skip, so the `_id` tiebreaker is inert; failed-auth delay change is an improvement.

Not analysed: older AAPS tags, xDrip MongoDB direct uploader, EIO verified only by library version, AAPS token-role documentation (external).
