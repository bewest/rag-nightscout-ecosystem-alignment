"""Synthetic Loop-style Nightscout data for demonstration reports.

SYNTHETIC DATA ONLY. Every value this module writes is generated from a
seeded random number generator and a small closed-loop simulation; no
real person's data is read, copied or used as a template.

It writes the four Nightscout collections that ``tools.ns2parquet
convert`` reads (``entries.json``, ``treatments.json``,
``devicestatus.json``, ``profile.json``), so a demonstration report goes
through the same ingestion as a real Nightscout export.

Model (deliberately simple, deterministic for a given seed):

* Glucose moves each 5-minute step by endogenous production, insulin
  action and carbohydrate absorption, plus an AR(1) disturbance.
  Endogenous production is balanced by the *true* basal need, so a
  scheduled basal that differs from it shows up as drift.
* Insulin action uses the exponential insulin curve LoopKit uses
  (action duration 360 min, peak 75 min).
* The *true* physiology differs from the *profile* on purpose (true
  basal need is higher, with a dawn rise; true ISF lower; true CR
  lower), so the decision-support prototype has something to find.
* A Loop-like controller runs every 5 minutes on the noisy CGM value,
  using only the profile: it predicts an eventual glucose from net IOB
  and logged COB, suspends when the prediction runs low, and otherwise
  sets a 30-minute temp basal toward target ("Temp Basal Only"; set
  ``AUTOBOLUS`` to give 40 % of a positive correction as an automatic
  bolus instead). The simulated user boluses for logged meals with the
  profile CR and sometimes gives a manual correction when high. It
  uploads ``loop`` devicestatus records and ``Temp Basal`` /
  ``Correction Bolus`` / ``Carb Correction`` treatments the way Loop
  does.
* Meals: three a day plus snacks; some are not logged, logged carbs
  are estimated with error, and pre-bolus timing varies. Low glucose is
  treated with fast carbs. Twice a week there is exercise with a
  temporary override. Sites change every 3 days, sensors every 10 days
  (with a 2-hour warm-up gap).

The profile timezone is ``Etc/UTC``.

Usage::

    python -m tools.cgmencode.synthetic_demo_patient --out DIR [--seed N] [--days 90]
"""
from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

GENERATOR_PATH = "tools/cgmencode/synthetic_demo_patient.py"
DEFAULT_SEED = 20261016
DEFAULT_DAYS = 90
# Fixed start so output is a pure function of (seed, days).
DEFAULT_START = datetime(2026, 1, 5, tzinfo=timezone.utc)

STEP_MIN = 5
STEPS_PER_DAY = 24 * 60 // STEP_MIN
DIA_MIN = 360
PEAK_MIN = 75
CURVE_STEPS = DIA_MIN // STEP_MIN

DEVICE = "loop://Synthetic-Demo-Phone"
CGM_DEVICE = "synthetic-demo-cgm"

# Profile the controller uses (what the "user" has configured).
PROFILE_BASAL = [("00:00", 0.80), ("06:00", 0.90), ("12:00", 0.85), ("21:00", 0.80)]
PROFILE_ISF = [("00:00", 50.0), ("06:00", 45.0), ("22:00", 50.0)]
PROFILE_CR = [("00:00", 11.0), ("06:00", 9.0), ("11:00", 11.0), ("17:00", 10.0)]
TARGET_LOW, TARGET_HIGH = 100.0, 115.0
SUSPEND_THRESHOLD = 75.0
MAX_BASAL = 3.5
MAX_AUTOBOLUS = 2.0
MAX_IOB = 8.0
# Loop dosing strategy: False = "Temp Basal Only", True = "Automatic Bolus".
# Temp-basal-only leaves manual corrections isolated from automatic
# boluses, which the demand-phase ISF analysis needs.
AUTOBOLUS = False


def _true_basal(hour: float) -> float:
    """True basal need (U/h): above the profile, with a dawn rise."""
    base = 0.95
    dawn = 0.30 * math.exp(-((hour - 5.5) ** 2) / (2 * 1.5 ** 2))
    return base + dawn


def _true_isf(hour: float) -> float:
    return 40.0 if 6 <= hour < 22 else 44.0


def _true_cr(hour: float) -> float:
    return 7.5 if 6 <= hour < 11 else 9.5


def _sched_value(schedule, hour: float) -> float:
    val = schedule[0][1]
    for hhmm, v in schedule:
        h, m = (int(x) for x in hhmm.split(":"))
        if hour >= h + m / 60.0:
            val = v
    return val


def _insulin_curves():
    """LoopKit exponential model: per-step absorbed fraction and IOB."""
    td, tp = float(DIA_MIN), float(PEAK_MIN)
    tau = tp * (1 - tp / td) / (1 - 2 * tp / td)
    a = 2 * tau / td
    s = 1 / (1 - a + (1 + a) * math.exp(-td / tau))

    def iob(t):
        if t <= 0:
            return 1.0
        if t >= td:
            return 0.0
        return 1 - s * (1 - a) * (
            (t * t / (tau * td * (1 - a)) - t / tau - 1) * math.exp(-t / tau) + 1)

    iob_curve = np.array([iob(i * STEP_MIN) for i in range(CURVE_STEPS + 1)])
    frac = iob_curve[:-1] - iob_curve[1:]
    return frac, iob_curve[:-1]


def _carb_curve(minutes: float) -> np.ndarray:
    """Triangular absorption profile over ``minutes``; sums to 1."""
    n = max(6, int(minutes // STEP_MIN))
    x = np.arange(n) + 0.5
    peak = n / 3.0
    w = np.where(x <= peak, x / peak, (n - x) / (n - peak))
    w = np.clip(w, 0, None)
    return w / w.sum()


def _iso(t: datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _ms(t: datetime) -> int:
    return int(t.timestamp() * 1000)


def _direction(delta15: float) -> str:
    r = delta15 / 15.0
    if r > 3:
        return "DoubleUp"
    if r > 2:
        return "SingleUp"
    if r > 1:
        return "FortyFiveUp"
    if r > -1:
        return "Flat"
    if r > -2:
        return "FortyFiveDown"
    if r > -3:
        return "SingleDown"
    return "DoubleDown"


def _profile_doc(start: datetime) -> list:
    def sched(pairs):
        out = []
        for hhmm, v in pairs:
            h, m = (int(x) for x in hhmm.split(":"))
            out.append({"time": hhmm, "timeAsSeconds": h * 3600 + m * 60,
                        "value": v})
        return out

    store = {
        "Default": {
            "dia": DIA_MIN / 60.0,
            "timezone": "Etc/UTC",
            "units": "mg/dl",
            "basal": sched(PROFILE_BASAL),
            "sens": sched(PROFILE_ISF),
            "carbratio": sched(PROFILE_CR),
            "target_low": sched([("00:00", TARGET_LOW)]),
            "target_high": sched([("00:00", TARGET_HIGH)]),
            "carbs_hr": 20,
            "delay": 20,
        }
    }
    return [{
        "_id": "5e0000000000000000000001",
        "defaultProfile": "Default",
        "enteredBy": "synthetic-demo-generator",
        "startDate": _iso(start),
        "created_at": _iso(start),
        "mills": _ms(start),
        "units": "mg/dl",
        "store": store,
    }]


def generate(seed: int = DEFAULT_SEED, days: int = DEFAULT_DAYS,
             start: datetime = DEFAULT_START) -> dict:
    """Return the four Nightscout collections as Python objects."""
    rng = np.random.default_rng(seed)
    n = days * STEPS_PER_DAY
    frac, iob_curve = _insulin_curves()

    # ── Plan the days: meals, exercise, sensor/site events ───────────
    meals = []      # (step, true_carbs, logged_carbs|None, bolus_offset_steps, absorb_min)
    exercise = []   # (step, duration_steps)
    for d in range(days):
        day0 = d * STEPS_PER_DAY
        plan = [
            (7.0, 0.6, (30, 60), 0.92, 180),
            (12.5, 0.9, (40, 80), 0.75, 210),
            (18.75, 0.9, (50, 100), 0.85, 240),
        ]
        if rng.random() < 0.5:
            plan.append((15.5, 0.5, (15, 30), 0.65, 120))
        if rng.random() < 0.35:
            plan.append((21.5, 0.5, (15, 35), 0.65, 150))
        for hour, sd_h, (lo, hi), p_logged, absorb in plan:
            h = hour + rng.normal(0, sd_h)
            step = day0 + int(max(0, min(23.9, h)) * 12)
            true_c = float(rng.uniform(lo, hi))
            logged = None
            if rng.random() < p_logged:
                logged = float(5 * round(true_c * rng.uniform(0.75, 1.05) / 5))
                logged = max(5.0, logged)
            offset = int(rng.choice([-3, -2, 0, 0, 0, 1, 2]))  # steps; <0 = pre-bolus
            meals.append((step, true_c, logged, offset, absorb))
        if d % 7 in (1, 4):
            h = 17.0 + rng.normal(0, 0.5)
            exercise.append((day0 + int(h * 12), int(rng.integers(8, 13))))

    day_sens = np.exp(rng.normal(0, 0.10, size=days))

    # Arrays of future effects (true physiology).
    ins_absorb = np.zeros(n + CURVE_STEPS + 2)       # U absorbed per step
    carb_absorb = np.zeros(n + 100)                  # g absorbed per step
    exercise_active = np.zeros(n + 200, dtype=bool)
    for s, dur in exercise:
        exercise_active[s:s + dur] = True
        exercise_active[s + dur:s + dur + 24] = True  # after-effect window

    # Controller ledgers (profile-based).
    net_deliveries = np.zeros(n + 1)                 # net U vs schedule
    logged_carb_events = []                          # (step, grams)

    meal_by_step = {}
    for m in meals:
        meal_by_step.setdefault(m[0], []).append(m)
    bolus_by_step = {}
    for (s, true_c, logged, off, absorb) in meals:
        if logged is not None:
            bolus_by_step.setdefault(max(0, s + off), []).append((logged, absorb))
    exercise_start = {s: dur for s, dur in exercise}

    entries, treatments, devicestatus = [], [], []
    bg = 115.0
    ar = 0.0
    cgm_hist = []
    last_hypo_tx = -999
    reservoir = 200.0
    override_until = -1
    last_user_bolus = -999
    last_logged_carb = -999

    for k in range(n):
        t = start + timedelta(minutes=STEP_MIN * k)
        hour = (k % STEPS_PER_DAY) / 12.0
        day = k // STEPS_PER_DAY
        sched_basal = _sched_value(PROFILE_BASAL, hour)
        isf_p = _sched_value(PROFILE_ISF, hour)
        cr_p = _sched_value(PROFILE_CR, hour)

        # Device events.
        if k % (3 * STEPS_PER_DAY) == 10 * 12:
            treatments.append({"eventType": "Site Change", "created_at": _iso(t),
                               "enteredBy": "synthetic-demo"})
            reservoir = 200.0
        sensor_age_steps = (k - 9 * 12) % (10 * STEPS_PER_DAY)
        if sensor_age_steps == 0:
            treatments.append({"eventType": "Sensor Start", "created_at": _iso(t),
                               "enteredBy": "synthetic-demo"})
        warmup = sensor_age_steps < 24 and k >= 9 * 12

        # Carbs eaten now (true) and logged.
        for (s, true_c, logged, off, absorb) in meal_by_step.get(k, []):
            prof = _carb_curve(absorb * rng.uniform(0.85, 1.2))
            carb_absorb[k + 2:k + 2 + len(prof)] += true_c * prof  # ~10 min lag
        for logged, absorb in bolus_by_step.get(k, []):
            treatments.append({
                "eventType": "Carb Correction", "created_at": _iso(t),
                "carbs": logged, "absorptionTime": absorb,
                "enteredBy": "loop://Synthetic-Demo-Phone",
            })
            logged_carb_events.append((k, logged))
            last_logged_carb = k

        if k in exercise_start:
            dur = exercise_start[k]
            treatments.append({
                "eventType": "Temporary Override", "created_at": _iso(t),
                "duration": dur * STEP_MIN + 60, "reason": "Workout",
                "correctionRange": [140, 160], "insulinNeedsScaleFactor": 0.6,
                "enteredBy": "loop://Synthetic-Demo-Phone",
            })
            treatments.append({"eventType": "Exercise", "created_at": _iso(t),
                               "duration": dur * STEP_MIN,
                               "enteredBy": "synthetic-demo"})
            override_until = k + dur + 12

        # ── CGM reading ──────────────────────────────────────────────
        cgm = float(np.clip(bg + rng.normal(0, 3.0), 40, 400))
        cgm_hist.append(cgm)
        if not warmup:
            delta15 = cgm - cgm_hist[-4] if len(cgm_hist) >= 4 else 0.0
            entries.append({
                "type": "sgv", "sgv": int(round(cgm)), "date": _ms(t),
                "dateString": _iso(t), "direction": _direction(delta15),
                "device": CGM_DEVICE,
            })

        # Hypo treatment (fast carbs), logged most of the time.
        if bg < 65 and k - last_hypo_tx > 6:
            g = float(rng.choice([12, 15, 20]))
            carb_absorb[k + 1:k + 1 + 6] += g * _carb_curve(30)
            if rng.random() < 0.7:
                treatments.append({"eventType": "Carb Correction",
                                   "created_at": _iso(t), "carbs": g,
                                   "absorptionTime": 30,
                                   "enteredBy": "loop://Synthetic-Demo-Phone"})
                logged_carb_events.append((k, g))
                last_logged_carb = k
            last_hypo_tx = k

        # ── Controller (profile-only view) ────────────────────────────
        lo = max(0, k - CURVE_STEPS + 1)
        iob = float(np.dot(net_deliveries[lo:k + 1][::-1],
                           iob_curve[:k + 1 - lo]))
        cob = 0.0
        for (s, g) in logged_carb_events[-12:]:
            age = k - s
            if 0 <= age < 36:
                cob += g * (1 - age / 36.0)
        overriding = k <= override_until
        target = 150.0 if overriding else (TARGET_LOW + TARGET_HIGH) / 2
        isf_eff = isf_p / 0.6 if overriding else isf_p
        eventual = cgm - iob * isf_eff + cob * isf_eff / cr_p
        tau = 60.0
        preds = [cgm + (eventual - cgm) * (1 - math.exp(-(i * 5) / tau))
                 for i in range(73)]
        # Short-term momentum on the first hour of the prediction.
        mom = (cgm_hist[-1] - cgm_hist[-3]) / 2 if len(cgm_hist) >= 3 else 0.0
        preds = [p + mom * min(i, 6) * math.exp(-i / 12) for i, p in enumerate(preds)]
        pred_min = min(preds)
        correction = (eventual - target) / isf_eff

        autobolus = 0.0
        if warmup:
            rate = sched_basal
        elif pred_min < SUSPEND_THRESHOLD or eventual < 85:
            rate = 0.0
        elif correction > 0 and AUTOBOLUS:
            rate = sched_basal
            ab = math.floor(0.4 * correction / 0.05) * 0.05
            ab = min(ab, MAX_AUTOBOLUS, max(0.0, MAX_IOB - iob))
            if ab >= 0.05:
                autobolus = round(ab, 2)
            else:
                rate = min(MAX_BASAL, sched_basal + correction / 0.5)
        elif correction > 0:
            rate = min(MAX_BASAL, sched_basal + correction / 0.5)
        else:
            rate = max(0.0, sched_basal + correction / 0.5)
        rate = round(rate * 40) / 40.0

        # User meal boluses (profile CR), plus occasional manual correction.
        manual = 0.0
        for logged, absorb in bolus_by_step.get(k, []):
            manual += logged / cr_p
        # Manual correction: high, no bolus for 3 h, no carbs for 1 h.
        if (manual == 0.0 and not warmup and cgm > 180
                and k - last_user_bolus >= 36 and k - last_logged_carb >= 12
                and rng.random() < 0.15):
            dose = (cgm - target) / isf_p - max(iob, 0.0)
            manual = dose if dose >= 0.5 else 0.0
        manual = round(manual * 20) / 20.0
        if manual > 0:
            last_user_bolus = k

        # Upload treatments.
        treatments.append({
            "eventType": "Temp Basal", "created_at": _iso(t), "rate": rate,
            "absolute": rate, "duration": 30, "temp": "absolute",
            "automatic": True, "enteredBy": "loop://Synthetic-Demo-Phone",
            **({"reason": "suspend"} if rate == 0.0 else {}),
        })
        if autobolus > 0:
            treatments.append({
                "eventType": "Correction Bolus", "created_at": _iso(t),
                "insulin": autobolus, "type": "normal", "automatic": True,
                "enteredBy": "loop://Synthetic-Demo-Phone",
            })
        if manual > 0:
            treatments.append({
                "eventType": "Correction Bolus", "created_at": _iso(t),
                "insulin": manual, "type": "normal", "automatic": False,
                "enteredBy": "loop://Synthetic-Demo-Phone",
            })

        devicestatus.append({
            "device": DEVICE, "created_at": _iso(t),
            "loop": {
                "name": "Loop", "version": "3.4.0", "timestamp": _iso(t),
                "iob": {"iob": round(iob, 3), "timestamp": _iso(t)},
                "cob": {"cob": round(cob, 1), "timestamp": _iso(t)},
                "predicted": {"startDate": _iso(t),
                              "values": [int(round(min(400, max(39, p)))) for p in preds]},
                "enacted": {"rate": rate, "duration": 1800, "timestamp": _iso(t),
                            "received": True, "bolusVolume": autobolus},
                "recommendedBolus": 0,
            },
            "pump": {"clock": _iso(t), "reservoir": round(reservoir, 1),
                     "battery": {"percent": 100 - (k % (3 * STEPS_PER_DAY)) * 60 // (3 * STEPS_PER_DAY)},
                     "suspended": False},
            "uploader": {"battery": 80},
        })

        # ── Delivery: true absorption and controller ledger ──────────
        delivered = rate / 12.0 + autobolus + manual
        reservoir = max(0.0, reservoir - delivered)
        ins_absorb[k:k + CURVE_STEPS] += delivered * frac
        net_deliveries[k] += (rate - sched_basal) / 12.0 + autobolus + manual

        # ── True physiology step ─────────────────────────────────────
        isf_t = _true_isf(hour) * day_sens[day]
        cr_t = _true_cr(hour)
        egp = _true_basal(hour) / 12.0 * _true_isf(hour)
        ex_gain = 1.6 if exercise_active[k] else 1.0
        dbg = (egp
               - ins_absorb[k] * isf_t * ex_gain
               + carb_absorb[k] * isf_t / cr_t
               - (0.6 if exercise_active[k] else 0.0))
        ar = 0.85 * ar + rng.normal(0, 0.9)
        bg = float(np.clip(bg + dbg + ar * 0.5, 39, 400))

    return {
        "entries": entries,
        "treatments": treatments,
        "devicestatus": devicestatus,
        "profile": _profile_doc(start),
    }


def write(out_dir: Path, seed: int = DEFAULT_SEED, days: int = DEFAULT_DAYS) -> dict:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    data = generate(seed=seed, days=days)
    # Newest-first, as the Nightscout API returns them.
    for name in ("entries", "treatments", "devicestatus"):
        data[name] = list(reversed(data[name]))
    for name, obj in data.items():
        (out_dir / f"{name}.json").write_text(json.dumps(obj))
    (out_dir / "SYNTHETIC.txt").write_text(
        f"Synthetic demonstration data generated by {GENERATOR_PATH} "
        f"with seed {seed} over {days} days. No real person's data.\n")
    return {k: len(v) for k, v in data.items()}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out", required=True, help="Output directory for the JSON files")
    p.add_argument("--seed", type=int, default=DEFAULT_SEED)
    p.add_argument("--days", type=int, default=DEFAULT_DAYS)
    args = p.parse_args(argv)
    counts = write(Path(args.out), seed=args.seed, days=args.days)
    print(f"Wrote synthetic collections to {args.out}: {counts}")


if __name__ == "__main__":
    main()
