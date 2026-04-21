#!/usr/bin/env python3
"""
Static-analysis-derived simulator of AAPS profile-store sync.

Models the deterministic state machine of:
  - ProfilePlugin.storeSettings (sets LocalProfileLastChange in preferences)
  - DataSyncSelectorV1.processChangedProfileStore (and V3, same structure)
  - The interaction between Save clicks, NSClient ack timing, and the
    confirmLastProfileStore(dateUtil.now()) post-ack write.

Goal: enumerate which sequences of (install, import, save, save, ...)
produce the Discord-reported symptom — many edits in AAPS but only ONE
profile-store doc in Nightscout.

Source citations (AAPS commit on disk, externals/AndroidAPS):
  - ProfilePlugin.kt:184-209  storeSettings
  - ProfilePlugin.kt:269       loadFromStore -> storeSettings(store.getStartDate())
  - ProfilePlugin.kt:346       ProfileFragment Save -> storeSettings(now)
  - ProfilePlugin.kt:368       removeCurrentProfile -> storeSettings(timestamp = 0)
  - DataSyncSelectorV1.kt:778-805  processChangedProfileStore + confirmLastProfileStore
  - DataSyncSelectorV3.kt:712-728  same shape
  - ProfileStoreObject.kt:106-111   allProfilesValid
  - ProfileSealed.kt:123-220        Pure.isValid (basal/dia/ic/isf/target ranges + pump caps)

Each scenario returns a trace with:
  - posts_to_ns: list of profile-store payloads that actually reached
    activeNsClient.nsAdd("profile", ...) (i.e., the only path that creates
    a profile-store doc in NS mongo)
  - silent_skips: list of (scenario_step, branch_name, reason)

If posts_to_ns has length 1 but the user clicked Save N times, that's
the Discord symptom. The scenario name + which silent_skip branches
fired tells us the root cause.
"""

from dataclasses import dataclass, field
from typing import Optional


# Default-zero unless previously written, mirroring AAPS preferences defaults.
PREF_DEFAULT = 0


@dataclass
class Pump:
    is_30min_basal_capable: bool = False
    basal_minimum_rate: float = 0.05
    basal_maximum_rate: float = 25.0


@dataclass
class HardLimits:
    min_dia: float = 5.0
    max_dia: float = 9.0
    max_basal: float = 25.0
    min_ic: float = 2.0
    max_ic: float = 100.0


@dataclass
class Profile:
    """In-AAPS representation of one profile in the store."""
    name: str
    dia: float
    basal_rates: list  # list of (start_seconds, amount)
    ic: float
    isf: float
    target_low: float = 100.0
    target_high: float = 120.0


@dataclass
class State:
    # Preferences (the persistent key/value store AAPS reads at boot)
    LocalProfileLastChange: int = PREF_DEFAULT
    ProfileStoreLastSyncedId: int = PREF_DEFAULT
    nsclient_paused: bool = False
    nsclient_authorized_for_profile: bool = True

    # Active profile in memory
    profile: Optional[Profile] = None
    pump: Pump = field(default_factory=Pump)
    hard_limits: HardLimits = field(default_factory=HardLimits)

    # Outgoing record of NS mongo state
    posts_to_ns: list = field(default_factory=list)
    silent_skips: list = field(default_factory=list)

    # Mock clock
    clock: int = 1_000_000_000_000  # ms

    def now(self) -> int:
        self.clock += 1
        return self.clock

    def advance(self, ms: int):
        self.clock += ms


def is_valid(profile: Profile, pump: Pump, hl: HardLimits) -> tuple[bool, str]:
    """Mirror of ProfileSealed.Pure.isValid (subset relevant to silent skip)."""
    if profile is None:
        return False, "no profile loaded"
    for start, amount in profile.basal_rates:
        if not pump.is_30min_basal_capable and (start % 3600) != 0:
            return False, "basal block not aligned to hours"
        if not (0.01 <= amount <= hl.max_basal):
            return False, f"basal {amount} out of hard limits"
        if amount < pump.basal_minimum_rate:
            return False, f"basal {amount} < pump minimum {pump.basal_minimum_rate}"
        if amount > pump.basal_maximum_rate:
            return False, f"basal {amount} > pump maximum {pump.basal_maximum_rate}"
    if not (hl.min_dia <= profile.dia <= hl.max_dia):
        return False, f"dia {profile.dia} out of [{hl.min_dia},{hl.max_dia}]"
    if not (hl.min_ic <= profile.ic <= hl.max_ic):
        return False, f"ic {profile.ic} out of [{hl.min_ic},{hl.max_ic}]"
    return True, ""


def all_profiles_valid(state: State) -> tuple[bool, str]:
    if state.profile is None:
        return False, "no active profile"
    return is_valid(state.profile, state.pump, state.hard_limits)


# ---- The two AAPS operations we model ------------------------------------

def store_settings(state: State, timestamp: int, step: str):
    """Mirror ProfilePlugin.storeSettings:184-209.
    Sets LocalProfileLastChange = timestamp and fires (implicitly) the sync.
    """
    state.LocalProfileLastChange = timestamp
    # rxBus.send(EventProfileStoreChanged) -> NSClientService.resend() ->
    # processChangedProfileStore in next coroutine tick. We simulate inline
    # but track the step for diagnostics.
    process_changed_profile_store(state, step)


def process_changed_profile_store(state: State, step: str, ack_delay_ms: int = 100, ack_arrives: bool = True):
    """Mirror DataSyncSelectorV1.processChangedProfileStore:786-805.
    The five guard branches, in source order:
    """
    if state.nsclient_paused:
        state.silent_skips.append((step, "isPaused", "NSClient paused/disabled"))
        return

    last_change = state.LocalProfileLastChange
    last_sync = state.ProfileStoreLastSyncedId

    if last_change == 0:
        state.silent_skips.append((step, "lastChange==0L",
            "LocalProfileLastChange is 0; never set or explicitly reset (e.g., loadFromStore "
            "with startDate=0, or removeCurrentProfile)."))
        return

    if not (last_change > last_sync):
        state.silent_skips.append((step, "lastChange<=lastSync",
            f"lastChange={last_change} <= lastSync={last_sync}; the previous sync's "
            f"post-ack confirmLastProfileStore(now) leapfrogged this edit."))
        return

    valid, reason = all_profiles_valid(state)
    if not valid:
        state.silent_skips.append((step, "!allProfilesValid", reason))
        return

    # Built the dataPair, called nsAdd. Now wait up to 60s for ack.
    if not ack_arrives:
        state.silent_skips.append((step, "ack timeout/REST 4xx",
            "nsAdd dispatched but no ack within 60s (NSClient unauthorized for profile, "
            "REST 4xx, or socket disconnect)."))
        return

    # Successful POST — record what reached NS.
    state.posts_to_ns.append({
        "step": step,
        "lastChange_at_emit": last_change,
        "profile_name": state.profile.name,
        "dia": state.profile.dia,
    })

    # Ack arrived; advance clock by ack_delay_ms then write confirmLastProfileStore(now)
    state.advance(ack_delay_ms)
    state.ProfileStoreLastSyncedId = state.now()


# ---- Scenarios -----------------------------------------------------------

def scenario_S0_baseline_two_clean_saves():
    """User installs, imports NS profile (with valid startDate>0), then makes
    two saves separated by enough time that the first sync's ack returns
    before the second save."""
    s = State(profile=Profile("Test", dia=6.5, basal_rates=[(0, 0.8)], ic=10, isf=50))
    # imported with valid startDate
    store_settings(s, timestamp=s.now(), step="import (loadFromStore, startDate=now)")
    s.advance(60_000)  # 1 minute later
    store_settings(s, timestamp=s.now(), step="Save #1")
    s.advance(60_000)
    store_settings(s, timestamp=s.now(), step="Save #2")
    return "S0_baseline_two_clean_saves", s


def scenario_S1_lastchange_zero_from_loadFromStore():
    """User imports a NS profile whose startDate is 0/missing.
    loadFromStore -> storeSettings(timestamp = store.getStartDate()) sets
    LocalProfileLastChange = 0. Subsequent processChangedProfileStore bails."""
    s = State(profile=Profile("Test", dia=6.5, basal_rates=[(0, 0.8)], ic=10, isf=50))
    store_settings(s, timestamp=0, step="import (loadFromStore, startDate=0)")
    # The user sees "Default 1969" — because lastChange=0 produces no POST.
    return "S1_lastchange_zero_from_loadFromStore", s


def scenario_S2_lastchange_zero_then_save_recovers():
    """Same as S1, then user clicks Save which uses dateUtil.now() — should recover."""
    s = State(profile=Profile("Test", dia=6.5, basal_rates=[(0, 0.8)], ic=10, isf=50))
    store_settings(s, timestamp=0, step="import (startDate=0)")
    s.advance(10_000)
    store_settings(s, timestamp=s.now(), step="Save #1 (now)")
    s.advance(10_000)
    store_settings(s, timestamp=s.now(), step="Save #2 (now)")
    return "S2_lastchange_zero_then_save_recovers", s


def scenario_S3_rapid_saves_ack_leapfrog():
    """User clicks Save twice within < ack_delay. Second save's lastChange may
    end up <= the first sync's confirmLastProfileStore(now), silently skipped."""
    s = State(profile=Profile("Test", dia=6.5, basal_rates=[(0, 0.8)], ic=10, isf=50))
    store_settings(s, timestamp=s.now(), step="import")
    # Save #1 with long ack delay (slow network)
    state_step = "Save #1"
    s.LocalProfileLastChange = s.now()
    process_changed_profile_store(s, state_step, ack_delay_ms=5000)
    # User immediately clicks Save #2, but their click happens DURING the ack wait;
    # in our model we already wrote ProfileStoreLastSyncedId = clock+5001.
    # User's Save #2 timestamp:
    save2_ts = s.now()
    s.LocalProfileLastChange = save2_ts
    process_changed_profile_store(s, "Save #2 (clicked during Save #1 ack wait)")
    return "S3_rapid_saves_ack_leapfrog", s


def scenario_S4_invalid_profile_silently_skipped():
    """User has a profile with dia=15 (out of hard limits). All saves skip."""
    s = State(profile=Profile("Test", dia=15.0, basal_rates=[(0, 0.8)], ic=10, isf=50))
    store_settings(s, timestamp=s.now(), step="Save #1 (invalid dia)")
    store_settings(s, timestamp=s.now(), step="Save #2 (invalid dia)")
    return "S4_invalid_profile_silently_skipped", s


def scenario_S5_nsclient_unauthorized_no_ack():
    """NSClient connection lacks profile.create role. POST is dispatched but
    no ack arrives within 60s; confirmLastProfileStore is never called.
    Subsequent saves: lastChange keeps growing > lastSync (still 0), so each
    one re-attempts and re-times-out — but no doc reaches NS."""
    s = State(profile=Profile("Test", dia=6.5, basal_rates=[(0, 0.8)], ic=10, isf=50),
              nsclient_authorized_for_profile=False)
    for i in range(3):
        save_ts = s.now()
        s.LocalProfileLastChange = save_ts
        process_changed_profile_store(s, f"Save #{i+1}", ack_arrives=False)
    return "S5_nsclient_unauthorized_no_ack", s


def scenario_S6_paused_nsclient():
    """User toggled NSClient pause; no syncs at all."""
    s = State(profile=Profile("Test", dia=6.5, basal_rates=[(0, 0.8)], ic=10, isf=50),
              nsclient_paused=True)
    store_settings(s, timestamp=s.now(), step="Save #1")
    store_settings(s, timestamp=s.now(), step="Save #2")
    return "S6_paused_nsclient", s


def scenario_S7_basal_misaligned_to_hour():
    """User edits a basal block boundary to e.g. 00:30 — pump.is_30min_basal_capable
    is False (most pumps), so allProfilesValid returns False silently."""
    s = State(profile=Profile("Test", dia=6.5,
                              basal_rates=[(0, 0.8), (30 * 60, 0.9)], ic=10, isf=50))
    store_settings(s, timestamp=s.now(), step="Save #1 (basal at :30)")
    return "S7_basal_misaligned_to_hour", s


# ---- Driver --------------------------------------------------------------

def run():
    scenarios = [
        scenario_S0_baseline_two_clean_saves,
        scenario_S1_lastchange_zero_from_loadFromStore,
        scenario_S2_lastchange_zero_then_save_recovers,
        scenario_S3_rapid_saves_ack_leapfrog,
        scenario_S4_invalid_profile_silently_skipped,
        scenario_S5_nsclient_unauthorized_no_ack,
        scenario_S6_paused_nsclient,
        scenario_S7_basal_misaligned_to_hour,
    ]
    print("=" * 78)
    print("AAPS profile-store sync simulator (static-analysis-derived)")
    print("=" * 78)
    rows = []
    for fn in scenarios:
        name, s = fn()
        # Count Save-like steps for ratio
        save_steps = [skip for skip in s.silent_skips if skip[0].startswith("Save")]
        save_count = len(save_steps) + sum(1 for p in s.posts_to_ns if p["step"].startswith("Save"))
        posts = len(s.posts_to_ns)
        matches_symptom = (
            posts <= 1 and (
                save_count >= 2 or any("import" in p["step"] for p in s.posts_to_ns) or len(s.silent_skips) >= 2
            )
        )
        rows.append((name, posts, save_count, len(s.silent_skips), matches_symptom))

        print(f"\n--- {name} ---")
        print(f"  posts to NS: {posts}")
        for p in s.posts_to_ns:
            print(f"    + {p['step']:55} dia={p['dia']}  lastChange={p['lastChange_at_emit']}")
        print(f"  silent skips: {len(s.silent_skips)}")
        for step, branch, reason in s.silent_skips:
            print(f"    - {step:55} [{branch}]\n        {reason}")

    print("\n" + "=" * 78)
    print(f"{'scenario':<48} {'posts':>6} {'saves':>6} {'skips':>6} {'matches?':>10}")
    print("-" * 78)
    for name, posts, saves, skips, m in rows:
        flag = "★ YES" if m else "no"
        print(f"{name:<48} {posts:>6} {saves:>6} {skips:>6} {flag:>10}")

    print("\nMatches the Discord-reported symptom (many edits, ≤1 profile-store doc in NS):")
    for name, posts, saves, skips, m in rows:
        if m:
            print(f"  • {name}")


if __name__ == "__main__":
    run()
