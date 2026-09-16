p='/home/bewest/src/rag-nightscout-ecosystem-alignment/docs/40-migration/legacy-cgm-ingestion-to-connect-2026-09-15.md'
s=open(p,encoding='utf-8').read(); orig=s
def rep(old,new):
    global s
    assert s.count(old)==1, ("count=%d for %r" % (s.count(old), old[:90]))
    s=s.replace(old,new,1)

# ---- §3.1 ----
rep("""Look at your Nightscout settings. You are affected **only** if you have one of these pairs set:

- `BRIDGE_USER_NAME` **and** `BRIDGE_PASSWORD` → you use the **legacy Dexcom bridge**.
- `MMCONNECT_USER_NAME` **and** `MMCONNECT_PASSWORD` → you use the **legacy MiniMed path**.

(Azure operators: the same names, with a `CUSTOMCONNSTR_` prefix.)

If neither pair is set, **this migration does not affect you.** If your readings come from a phone
app, from Loop, Trio, AAPS, or xDrip+, or from `CONNECT_*` settings you already configured, you are
not affected either.

Another way to check: open your Nightscout graph, hover over a recent reading, and look at the
device name.""",
"""**Check the device name first — it is the reliable test.** Open your Nightscout graph, hover over a
recent reading, and look at the device name. The settings-based test below is a second opinion, not
the primary one, and the reason is in the table: on the version you are running today, having
`BRIDGE_*` set does **not** necessarily mean the old Dexcom bridge is what is fetching your data.""")

rep("""| Device name you see | What it means |
| --- | --- |
| `share2` | legacy Dexcom bridge — **you are affected** |""",
"""| Device name you see | What it means |
| --- | --- |
| `share2` | legacy Dexcom bridge is actually running — **you are affected**. On 15.0.8 or the 15.0.9 candidate this normally means you have set `DEXCOM_BRIDGE_USE_LEGACY=true` |""")

rep("""| anything else | a different uploader; unaffected |
""",
"""| anything else | a different uploader; unaffected |

**Then check your settings, for the MiniMed case and as a cross-check:**

- `MMCONNECT_USER_NAME` **and** `MMCONNECT_PASSWORD` set → you use the **legacy MiniMed path**, and
  you are affected. There is no auto-migration for MiniMed on today's release, so if these are set,
  the old MiniMed plugin *is* running.
- `BRIDGE_USER_NAME` **and** `BRIDGE_PASSWORD` set → you supplied Dexcom Share credentials. On
  **15.0.8 and the 15.0.9 candidate these are already handed to Nightscout Connect at startup and
  the old bridge stands down**, unless you also set `DEXCOM_BRIDGE_USE_LEGACY=true`. So `BRIDGE_*`
  on its own usually means you are *already* on the replacement. (Measured on `origin/master` and
  `origin/dev`; §5.3.4.) The device name settles it.

(Azure operators: the same names, with a `CUSTOMCONNSTR_` prefix.)

If none of these is set, **this migration does not affect you.** If your readings come from a phone
app, from Loop, Trio, AAPS, or xDrip+, or from `CONNECT_*` settings you already configured, you are
not affected either.
""")
open(p,'w',encoding='utf-8').write(s)
print('ok delta', len(s)-len(orig))
