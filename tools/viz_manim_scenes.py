#!/usr/bin/env python3
"""Manim animation scenes for CGM prediction research findings.

Four Scene classes visualising key results from the Nightscout
ecosystem alignment research programme:

  MealResponsePhenotypes  – 5 meal-response categories (EXP-514)
  TemporalLeadLag         – carb/insulin/glucose timing (EXP-521)
  WindowSizeAnimation     – DIA confusion U-curve
  ModelStackingProgression – stacking R² progression
"""
from manim import *
import numpy as np

# ── Shared constants ────────────────────────────────────────────────
TITLE_SCALE = 0.7
LABEL_SCALE = 0.35
SMALL_SCALE = 0.30


# ════════════════════════════════════════════════════════════════════
# Scene 1 – Meal Response Phenotypes
# ════════════════════════════════════════════════════════════════════
class MealResponsePhenotypes(Scene):
    """Animate the 5 meal-response categories discovered in EXP-514.

    Categories: Flat (50%), Biphasic (41%), Fast (5%),
    Slow (2%), Moderate (1%).
    """

    def construct(self):
        # ── Curve definitions ───────────────────────────────────────
        def flat_fn(t):
            return 1.0 * np.exp(-t / 10.0)

        def biphasic_fn(t):
            return (30.0 * np.exp(-((t - 45) ** 2) / 800.0)
                    + 60.0 * np.exp(-((t - 90) ** 2) / 1200.0))

        def fast_fn(t):
            if t <= 0:
                return 0.0
            return 48.0 * (t / 30.0) * np.exp(1.0 - t / 30.0)

        def slow_fn(t):
            if t <= 0:
                return 0.0
            return 53.0 * (t / 150.0) * np.exp(1.0 - t / 150.0)

        def moderate_fn(t):
            if t <= 0:
                return 0.0
            return 52.0 * (t / 65.0) * np.exp(1.0 - t / 65.0)

        phenotypes = [
            ("Flat",      "50%", "+1 mg/dL @ 5 min — AID suppresses completely",
             flat_fn,      GREY),
            ("Biphasic",  "41%", "+60 mg/dL @ 90 min — classic two-phase",
             biphasic_fn,  BLUE),
            ("Fast",      "5%",  "+48 mg/dL @ 30 min — simple carbs, rapid spike",
             fast_fn,      RED),
            ("Slow",      "2%",  "+53 mg/dL @ 150 min — fat/protein delayed",
             slow_fn,      ORANGE),
            ("Moderate",  "1%",  "+52 mg/dL @ 65 min — standard absorption",
             moderate_fn,  GREEN),
        ]

        # ── Title ───────────────────────────────────────────────────
        title = Text("Meal Response Phenotypes", font_size=36).to_edge(UP, buff=0.3)
        subtitle = Text("EXP-514 · Temporal Alignment Report", font_size=20,
                        color=GREY_B).next_to(title, DOWN, buff=0.1)
        self.play(Write(title), FadeIn(subtitle, shift=UP * 0.2))
        self.wait(0.5)

        # ── Axes (no LaTeX – manual tick labels) ────────────────────
        axes = Axes(
            x_range=[0, 180, 30],
            y_range=[-20, 80, 20],
            x_length=9,
            y_length=4.5,
            axis_config={"include_numbers": False, "font_size": 20},
            tips=False,
        ).shift(DOWN * 0.4)

        # Manual tick labels
        xt = VGroup(*[
            Text(str(v), font_size=14).next_to(axes.c2p(v, -20), DOWN, buff=0.1)
            for v in range(0, 181, 30)
        ])
        yt = VGroup(*[
            Text(str(v), font_size=14).next_to(axes.c2p(0, v), LEFT, buff=0.1)
            for v in range(-20, 81, 20)
        ])

        x_label = Text("Time after meal (min)", font_size=18).next_to(
            axes.x_axis, DOWN, buff=0.35)
        y_label = Text("Delta BG (mg/dL)", font_size=18).next_to(
            axes.y_axis, LEFT, buff=0.35).rotate(PI / 2)

        self.play(Create(axes), FadeIn(xt), FadeIn(yt),
                  FadeIn(x_label), FadeIn(y_label))

        # ── Target zone (green band around 0-line) ──────────────────
        zone = axes.get_area(
            axes.plot(lambda t: 10, x_range=[0, 180]),
            bounded_graph=axes.plot(lambda t: -10, x_range=[0, 180]),
            color=GREEN,
            opacity=0.12,
        )
        zone_label = Text("Target zone", font_size=14, color=GREEN_D).move_to(
            axes.c2p(170, -15))
        self.play(FadeIn(zone), FadeIn(zone_label))
        self.wait(0.3)

        # ── Draw each phenotype one by one ──────────────────────────
        drawn_curves = []
        for name, freq, desc, fn, color in phenotypes:
            curve = axes.plot(fn, x_range=[0, 180, 0.5], color=color,
                              stroke_width=3)
            label_txt = f"{name} ({freq})"
            info_box = VGroup(
                Text(label_txt, font_size=22, color=color, weight=BOLD),
                Text(desc, font_size=16, color=GREY_B),
            ).arrange(DOWN, aligned_edge=LEFT, buff=0.05)
            info_box.to_corner(UR, buff=0.5).shift(DOWN * 0.6)

            self.play(Create(curve, run_time=1.5), FadeIn(info_box))
            self.wait(0.8)
            self.play(FadeOut(info_box))
            drawn_curves.append(curve)

        # ── All curves together + frequency pie ─────────────────────
        freq_data = [
            ("Flat 50%",     0.50, GREY),
            ("Biphasic 41%", 0.41, BLUE),
            ("Fast 5%",      0.05, RED),
            ("Slow 2%",      0.02, ORANGE),
            ("Moderate 1%",  0.01, GREEN),
        ]
        # Build a simple pie with sectors
        pie_group = VGroup()
        start_angle = 0.0
        pie_radius = 0.8
        for lbl, frac, clr in freq_data:
            angle = frac * TAU
            sector = AnnularSector(
                inner_radius=0,
                outer_radius=pie_radius,
                angle=angle,
                start_angle=start_angle,
                color=clr,
                fill_opacity=0.8,
                stroke_width=1,
                stroke_color=WHITE,
            )
            pie_group.add(sector)
            start_angle += angle

        # Pie labels
        pie_labels = VGroup()
        start_angle = 0.0
        for lbl, frac, clr in freq_data:
            angle = frac * TAU
            mid_angle = start_angle + angle / 2
            if frac >= 0.05:
                direction = np.array([np.cos(mid_angle), np.sin(mid_angle), 0])
                t = Text(lbl, font_size=12, color=clr)
                t.move_to(direction * (pie_radius + 0.45))
                pie_labels.add(t)
            start_angle += angle

        pie_all = VGroup(pie_group, pie_labels)
        pie_all.to_corner(DR, buff=0.6)

        self.play(FadeIn(pie_all, shift=LEFT))
        self.wait(2)
        self.play(*[FadeOut(m) for m in self.mobjects])


# ════════════════════════════════════════════════════════════════════
# Scene 2 – Temporal Lead / Lag  (Hypothesis → Reality)
# ════════════════════════════════════════════════════════════════════
class TemporalLeadLag(Scene):
    """Two-act animation: idealized hypothesis then actual EXP-521 data.

    Act 1 – 'The Hypothesis': clean Gaussian signals offset by neat lags.
    Act 2 – 'The Reality':    per-patient measured lags, weak correlations,
                              massive variance, state-dependent structure.

    All Act 2 numbers are exact values from the temporal-alignment-report
    (EXP-521 table, lines 72-88; EXP-523 lines 106-113; EXP-525 lines 121-128).
    """

    # ── Exact experimental data (EXP-521, table lines 72-88) ────────
    PATIENT_DATA = {
        #       net_lag  supply_lag  demand_lag  zero_lag_corr
        "a": (  +15,     -120,       +10,        0.208),
        "b": (   +0,      -45,       +20,        0.177),
        "c": (  +10,      -95,       +20,        0.266),
        "d": (  +10,       +0,      +120,        0.131),
        "e": (  +20,      -45,       +50,        0.200),
        "f": (  +10,      -70,       +35,        0.227),
        "g": (  +10,      -40,       +45,        0.212),
        "h": (   +0,     -100,       +15,        0.173),
        "i": (  +25,      -20,       +35,        0.243),
        "j": (  +15,      +30,      +120,        0.045),
        "k": (   +5,       +5,        +0,        0.084),
    }

    # EXP-523: Circadian lag profile (lines 106-113)
    CIRCADIAN = [
        ("Night 00-06",     +5,  0.18),
        ("Morning 06-12",  +10,  0.19),
        ("Afternoon 12-18", +5,  0.21),
        ("Evening 18-24",   +5,  0.21),
    ]

    # EXP-525: State-dependent lag (lines 121-128)
    STATE_DEP = [
        ("Meal",       0, 0.20),
        ("Fasting",  +10, 0.10),
        ("High BG",    0, 0.21),
        ("Correction", 0, 0.19),
    ]

    def construct(self):
        self._act1_hypothesis()
        self._act2_reality()

    # ────────────────────────────────────────────────────────────────
    # ACT 1 – The Hypothesis (idealized)
    # ────────────────────────────────────────────────────────────────
    def _act1_hypothesis(self):
        title = Text("Act 1: The Hypothesis", font_size=34).to_edge(UP, buff=0.3)
        subtitle = Text(
            "Idealized temporal coupling of supply -> glucose -> demand",
            font_size=18, color=GREY_B,
        ).next_to(title, DOWN, buff=0.08)
        self.play(Write(title), FadeIn(subtitle, shift=UP * 0.2))
        self.wait(0.4)

        axes = Axes(
            x_range=[-120, 120, 30], y_range=[-0.1, 1.15, 0.2],
            x_length=10, y_length=3.6,
            axis_config={"include_numbers": False}, tips=False,
        ).shift(DOWN * 0.55)

        x_ticks = VGroup(*[
            Text(str(v), font_size=13).next_to(axes.c2p(v, 0), DOWN, buff=0.12)
            for v in [-120, -60, 0, 60, 120]
        ])
        x_lbl = Text("Time offset (min)", font_size=15).next_to(
            axes.x_axis, DOWN, buff=0.4)
        y_lbl = Text("Amplitude", font_size=15).next_to(
            axes.y_axis, LEFT, buff=0.2).rotate(PI / 2)
        now_line = DashedLine(
            axes.c2p(0, -0.1), axes.c2p(0, 1.15),
            color=YELLOW, stroke_width=1, dash_length=0.08)
        now_txt = Text("0", font_size=14, color=YELLOW, weight=BOLD).next_to(
            axes.c2p(0, 0), DOWN, buff=0.3)

        self.play(Create(axes), FadeIn(x_ticks), FadeIn(x_lbl),
                  FadeIn(y_lbl), Create(now_line), FadeIn(now_txt))

        def gauss(center):
            return lambda t: np.exp(-((t - center) ** 2) / 800.0)

        sig_defs = [
            ("Carb absorption (supply)", GREEN,  gauss(-10), "Leads by 10 min"),
            ("Glucose response",         BLUE,   gauss(0),   "Reference"),
            ("Insulin effect (demand)",   RED,    gauss(+20), "Lags by 20 min"),
        ]
        curves = []
        for name, color, fn, note in sig_defs:
            c = axes.plot(fn, x_range=[-120, 120, 0.5], color=color, stroke_width=3)
            lbl = Text(f"{name}: {note}", font_size=15, color=color)
            lbl.next_to(axes, DOWN, buff=0.7 + 0.25 * len(curves))
            self.play(Create(c, run_time=0.8), FadeIn(lbl))
            curves.append((c, lbl))

        arr_s = Arrow(
            axes.c2p(-10, 1.05), axes.c2p(0, 1.05),
            color=GREEN, stroke_width=2.5, buff=0,
            max_tip_length_to_length_ratio=0.35)
        arr_d = Arrow(
            axes.c2p(0, 0.92), axes.c2p(20, 0.92),
            color=RED, stroke_width=2.5, buff=0,
            max_tip_length_to_length_ratio=0.35)
        self.play(GrowArrow(arr_s), GrowArrow(arr_d))
        self.wait(0.8)

        caveat = Text(
            "But is this what the data actually shows?",
            font_size=24, color=YELLOW, weight=BOLD,
        ).to_edge(DOWN, buff=0.25)
        self.play(Write(caveat))
        self.wait(1.5)
        self.play(*[FadeOut(m) for m in self.mobjects])

    # ────────────────────────────────────────────────────────────────
    # ACT 2 – The Reality (EXP-521 measured data)
    # ────────────────────────────────────────────────────────────────
    def _act2_reality(self):
        title = Text("Act 2: The Reality (EXP-521)", font_size=34).to_edge(UP, buff=0.3)
        subtitle = Text(
            "Measured per-patient lags | 11 patients | xcorr of net flux vs dBG/dt",
            font_size=16, color=GREY_B,
        ).next_to(title, DOWN, buff=0.08)
        self.play(Write(title), FadeIn(subtitle, shift=UP * 0.2))
        self.wait(0.4)

        # ── Panel A: Per-patient net lag scatter ────────────────────
        panel_a_title = Text("A. Net Lag per Patient", font_size=20,
                             weight=BOLD).move_to(UP * 1.8 + LEFT * 3.2)
        self.play(FadeIn(panel_a_title))

        ax_lag = Axes(
            x_range=[-5, 30, 5], y_range=[-0.5, 11.5, 1],
            x_length=5, y_length=3.5,
            axis_config={"include_numbers": False}, tips=False,
        ).move_to(LEFT * 3.2 + DOWN * 0.3)

        lag_xticks = VGroup(*[
            Text(str(v), font_size=11).next_to(ax_lag.c2p(v, 0), DOWN, buff=0.1)
            for v in [0, 5, 10, 15, 20, 25]
        ])
        lag_xlabel = Text("Net lag (min)", font_size=13).next_to(
            ax_lag.x_axis, DOWN, buff=0.35)
        self.play(Create(ax_lag), FadeIn(lag_xticks), FadeIn(lag_xlabel))

        patients = sorted(self.PATIENT_DATA.keys())
        dots = VGroup()
        labels = VGroup()
        for idx, pid in enumerate(patients):
            net_lag = self.PATIENT_DATA[pid][0]
            corr = self.PATIENT_DATA[pid][3]
            r = 0.06 + corr * 0.25
            dot = Dot(ax_lag.c2p(net_lag, idx), radius=r, color=BLUE)
            lbl = Text(
                f"{pid} (r={corr:.3f})", font_size=10,
            ).next_to(dot, RIGHT, buff=0.08)
            dots.add(dot)
            labels.add(lbl)

        self.play(LaggedStart(
            *[FadeIn(d, scale=0.5) for d in dots],
            lag_ratio=0.08, run_time=1.2))
        self.play(FadeIn(labels, lag_ratio=0.05, run_time=0.8))

        net_lags = [self.PATIENT_DATA[p][0] for p in patients]
        median_lag = float(np.median(net_lags))
        med_line = DashedLine(
            ax_lag.c2p(median_lag, -0.5), ax_lag.c2p(median_lag, 11.5),
            color=YELLOW, stroke_width=2, dash_length=0.06)
        med_lbl = Text(
            f"Median: +{median_lag:.0f} min", font_size=13, color=YELLOW,
        ).next_to(ax_lag.c2p(median_lag, 11.5), UP, buff=0.1)
        self.play(Create(med_line), FadeIn(med_lbl))

        range_note = Text("Range: 0 to +25 min", font_size=12,
                          color=GREY_B).next_to(ax_lag, DOWN, buff=0.55)
        self.play(FadeIn(range_note))
        self.wait(0.8)

        # ── Panel B: Supply vs Demand lag scatter ──────────────────
        panel_b_title = Text("B. Supply vs Demand Lag", font_size=20,
                             weight=BOLD).move_to(UP * 1.8 + RIGHT * 3.2)
        self.play(FadeIn(panel_b_title))

        ax_sd = Axes(
            x_range=[-130, 40, 20], y_range=[-10, 130, 20],
            x_length=5, y_length=3.5,
            axis_config={"include_numbers": False}, tips=False,
        ).move_to(RIGHT * 3.2 + DOWN * 0.3)

        sd_xticks = VGroup(*[
            Text(str(v), font_size=10).next_to(ax_sd.c2p(v, 0), DOWN, buff=0.1)
            for v in [-120, -80, -40, 0, 30]
        ])
        sd_yticks = VGroup(*[
            Text(str(v), font_size=10).next_to(ax_sd.c2p(-130, v), LEFT, buff=0.1)
            for v in [0, 40, 80, 120]
        ])
        sd_xlabel = Text("Supply lag (min)", font_size=12, color=GREEN).next_to(
            ax_sd.x_axis, DOWN, buff=0.35)
        sd_ylabel = Text("Demand lag (min)", font_size=12, color=RED).next_to(
            ax_sd.y_axis, LEFT, buff=0.35).rotate(PI / 2)

        self.play(Create(ax_sd), FadeIn(sd_xticks), FadeIn(sd_yticks),
                  FadeIn(sd_xlabel), FadeIn(sd_ylabel))

        sd_dots = VGroup()
        sd_labels = VGroup()
        for pid in patients:
            s_lag = self.PATIENT_DATA[pid][1]
            d_lag = self.PATIENT_DATA[pid][2]
            dot = Dot(ax_sd.c2p(s_lag, d_lag), radius=0.08, color=TEAL)
            lbl = Text(pid, font_size=10, color=WHITE).next_to(dot, UR, buff=0.04)
            sd_dots.add(dot)
            sd_labels.add(lbl)

        self.play(LaggedStart(
            *[FadeIn(d, scale=0.5) for d in sd_dots],
            lag_ratio=0.08, run_time=1.0))
        self.play(FadeIn(sd_labels, run_time=0.5))

        outlier_note = Text(
            "Patients d, j: demand lag +120 min\n"
            "Patient a: supply lag -120 min",
            font_size=11, color=ORANGE,
        ).next_to(ax_sd, DOWN, buff=0.5)
        self.play(FadeIn(outlier_note))
        self.wait(1.0)

        # ── Key insight box ─────────────────────────────────────────
        self.play(FadeOut(outlier_note), FadeOut(range_note))

        insight_lines = VGroup(
            Text("KEY FINDINGS (EXP-521/523/525)", font_size=16,
                 weight=BOLD, color=YELLOW),
            Text("", font_size=6),
            Text("Correlations are WEAK (r = 0.045 - 0.266)", font_size=14,
                 color=WHITE),
            Text("Supply and demand lags are in OPPOSITE directions",
                 font_size=14, color=WHITE),
            Text("Supply: -120 to +30 min   Demand: 0 to +120 min",
                 font_size=13, color=GREY_B),
            Text("", font_size=6),
            Text("State-dependent (EXP-525):", font_size=14,
                 weight=BOLD, color=TEAL),
            Text("  Meals: 0 min lag (r=0.20)   Fasting: +10 min (r=0.10)",
                 font_size=13),
            Text("", font_size=6),
            Text("Circadian (EXP-523):", font_size=14,
                 weight=BOLD, color=TEAL),
            Text("  Morning: +10 min (r=0.19)   Afternoon: +5 min (r=0.21)",
                 font_size=13),
            Text("", font_size=6),
            Text("Lag correction adds only +0.6% R-squared on average (EXP-522)",
                 font_size=14, color=ORANGE),
        ).arrange(DOWN, aligned_edge=LEFT, buff=0.04)
        insight_lines.to_edge(DOWN, buff=0.15)
        bg = SurroundingRectangle(
            insight_lines, color=GREY, buff=0.12,
            corner_radius=0.1, fill_color=BLACK, fill_opacity=0.7)
        self.play(FadeIn(bg), FadeIn(insight_lines, shift=UP * 0.2))
        self.wait(3)

        # ── Final summary ───────────────────────────────────────────
        self.play(FadeOut(bg), FadeOut(insight_lines))
        summary = VGroup(
            Text("The lag structure is REAL but WEAK", font_size=26,
                 color=YELLOW, weight=BOLD),
            Text("Median +10 min, but range 0-25 min across patients",
                 font_size=18),
            Text("Contributes <1% R-squared -- not a major prediction lever",
                 font_size=18, color=ORANGE),
        ).arrange(DOWN, buff=0.12).to_edge(DOWN, buff=0.35)
        self.play(Write(summary[0]), run_time=1.0)
        self.play(FadeIn(summary[1]), FadeIn(summary[2]))
        self.wait(2)
        self.play(*[FadeOut(m) for m in self.mobjects])


# ════════════════════════════════════════════════════════════════════
# Scene 3 – Window Size U-Curve & DIA Confusion Zone
# ════════════════════════════════════════════════════════════════════
class WindowSizeAnimation(Scene):
    """Animate the window-size U-curve showing the DIA confusion zone."""

    def construct(self):
        # ── data ────────────────────────────────────────────────────
        raw = [
            (1,   -0.346),
            (2,   -0.367),
            (4,   -0.537),
            (6,   -0.544),
            (8,   -0.642),
            (12,  -0.339),
            (168, -0.301),   # 7 days = 168 h
        ]
        x_labels_map = {1: "1h", 2: "2h", 4: "4h", 6: "6h",
                        8: "8h", 12: "12h", 168: "7d"}

        # Map to plotting coords (log-ish spacing for readability)
        plot_x = {1: 1, 2: 2, 4: 3, 6: 4, 8: 5, 12: 6, 168: 7}
        data = [(plot_x[h], s) for h, s in raw]

        # ── Title ───────────────────────────────────────────────────
        title = Text("Why Window Size Matters for Pattern Recognition",
                     font_size=32).to_edge(UP, buff=0.3)
        self.play(Write(title))
        self.wait(0.4)

        # ── Axes ────────────────────────────────────────────────────
        axes = Axes(
            x_range=[0.5, 7.5, 1],
            y_range=[-0.7, -0.2, 0.1],
            x_length=9,
            y_length=4.5,
            axis_config={"include_numbers": False, "font_size": 18},
            tips=False,
        ).shift(DOWN * 0.3)

        # Custom x-tick labels
        xtick_labels = VGroup()
        for h, px in plot_x.items():
            lbl = Text(x_labels_map[h], font_size=14)
            lbl.next_to(axes.c2p(px, -0.7), DOWN, buff=0.15)
            xtick_labels.add(lbl)

        # y-tick labels
        ytick_labels = VGroup()
        for v in np.arange(-0.7, -0.15, 0.1):
            lbl = Text(f"{v:.1f}", font_size=12)
            lbl.next_to(axes.c2p(0.5, v), LEFT, buff=0.15)
            ytick_labels.add(lbl)

        y_label = Text("Silhouette score", font_size=16).next_to(
            axes.y_axis, LEFT, buff=0.55).rotate(PI / 2)
        x_label = Text("Window duration", font_size=16).next_to(
            axes.x_axis, DOWN, buff=0.45)

        self.play(Create(axes), FadeIn(xtick_labels), FadeIn(ytick_labels),
                  FadeIn(x_label), FadeIn(y_label))
        self.wait(0.3)

        # ── Animate points left → right ─────────────────────────────
        dots = []
        labels = []
        for px, sil in data:
            dot = Dot(axes.c2p(px, sil), radius=0.07, color=YELLOW)
            lbl = Text(f"{sil:.3f}", font_size=12, color=GREY_B).next_to(
                dot, UP, buff=0.1)
            dots.append(dot)
            labels.append(lbl)

        for i, (dot, lbl) in enumerate(zip(dots, labels)):
            self.play(FadeIn(dot, scale=1.5), FadeIn(lbl), run_time=0.5)

        # Connect with line
        points_for_line = [axes.c2p(px, sil) for px, sil in data]
        polyline = VMobject(color=YELLOW, stroke_width=2)
        polyline.set_points_smoothly(points_for_line)
        self.play(Create(polyline, run_time=1))
        self.wait(0.5)

        # ── DIA confusion zone (4-8 h = px 3-5) ────────────────────
        dia_zone = Rectangle(
            width=axes.c2p(5, 0)[0] - axes.c2p(3, 0)[0],
            height=axes.c2p(0, -0.2)[1] - axes.c2p(0, -0.7)[1],
            fill_color=RED, fill_opacity=0.15,
            stroke_color=RED, stroke_width=1,
        ).move_to(axes.c2p(4, -0.45))
        dia_label = Text("Insulin DIA Zone (4–8 h)", font_size=16,
                         color=RED, weight=BOLD).next_to(dia_zone, UP, buff=0.1)
        self.play(FadeIn(dia_zone), Write(dia_label))
        self.wait(0.5)

        # ── Insulin action curve inset ──────────────────────────────
        inset_axes = Axes(
            x_range=[0, 360, 60],
            y_range=[0, 1.1, 0.5],
            x_length=3.0,
            y_length=1.5,
            axis_config={"include_numbers": False, "font_size": 10},
            tips=False,
        )
        # Insulin action: peaks ~75 min, lasts ~300 min
        ia_curve = inset_axes.plot(
            lambda t: (t / 75.0) * np.exp(1.0 - t / 75.0) if t > 0 else 0,
            x_range=[0, 360, 1], color=RED_B, stroke_width=2)
        inset_title = Text("Insulin Action Curve", font_size=12,
                           color=RED_B).next_to(inset_axes, UP, buff=0.05)
        inset_group = VGroup(inset_axes, ia_curve, inset_title)
        inset_group.to_corner(UL, buff=0.5).shift(DOWN * 0.7)
        inset_border = SurroundingRectangle(inset_group, color=GREY,
                                            buff=0.1, corner_radius=0.05)
        self.play(FadeIn(inset_group), Create(inset_border))
        self.wait(0.8)

        # ── Annotate 12h recovery ───────────────────────────────────
        star = Star(n=5, outer_radius=0.15, inner_radius=0.07,
                    color=GREEN, fill_opacity=1).move_to(axes.c2p(6, -0.339))
        star_note = Text("12h: captures full cycle", font_size=14,
                         color=GREEN).next_to(star, RIGHT, buff=0.15)
        self.play(FadeIn(star, scale=2), FadeIn(star_note))
        self.wait(0.5)

        # ── 7d best marker ──────────────────────────────────────────
        best_star = Star(n=5, outer_radius=0.15, inner_radius=0.07,
                         color=GOLD, fill_opacity=1).move_to(axes.c2p(7, -0.301))
        best_note = Text("7d: best overall", font_size=14,
                         color=GOLD).next_to(best_star, RIGHT, buff=0.15)
        self.play(FadeIn(best_star, scale=2), FadeIn(best_note))
        self.wait(0.8)

        # ── Final insight ───────────────────────────────────────────
        insight = Text(
            "Windows must be shorter than DIA or long enough\n"
            "to see the full insulin cycle.",
            font_size=20, color=YELLOW, weight=BOLD,
        ).to_edge(DOWN, buff=0.35)
        self.play(Write(insight, run_time=1.5))
        self.wait(2)
        self.play(*[FadeOut(m) for m in self.mobjects])


# ════════════════════════════════════════════════════════════════════
# Scene 4 – Model Stacking Progression
# ════════════════════════════════════════════════════════════════════
class ModelStackingProgression(Scene):
    """Animate how the glucose prediction model improves through stacking."""

    def construct(self):
        # ── Data ────────────────────────────────────────────────────
        stages = [
            ("Ridge baseline\n(BG + IOB + COB + timing)",          0.506, BLUE),
            ("+ PK Derivatives\n(dIOB/dt, dCOB/dt)",              0.515, TEAL),
            ("+ Meal Shape\nFeatures",                             0.521, GREEN),
            ("+ CV Stacking\nMeta-learner",                        0.561, GOLD),
        ]
        oracle = 0.616
        sota = 0.577
        block_cv = 0.542

        # ── Title ───────────────────────────────────────────────────
        title = Text("Building the Best Glucose Predictor",
                     font_size=34).to_edge(UP, buff=0.3)
        self.play(Write(title))
        self.wait(0.4)

        # ── Axes ────────────────────────────────────────────────────
        bar_width = 1.2
        gap = 0.3
        n = len(stages)
        total_w = n * bar_width + (n - 1) * gap
        start_x = -total_w / 2 + bar_width / 2

        # Value range 0.45 – 0.65 for nice bar heights
        val_lo, val_hi = 0.45, 0.65
        bar_max_h = 4.5
        y_base = -2.0

        def val_to_h(v):
            return (v - val_lo) / (val_hi - val_lo) * bar_max_h

        # Background axis line
        axis_line = Line(
            start=np.array([-total_w / 2 - 0.4, y_base, 0]),
            end=np.array([total_w / 2 + 0.6, y_base, 0]),
            color=GREY, stroke_width=1)
        self.play(Create(axis_line))

        # y-axis tick marks
        y_ticks = VGroup()
        for v in np.arange(0.45, 0.66, 0.05):
            y_pos = y_base + val_to_h(v)
            tick_line = Line(
                start=np.array([-total_w / 2 - 0.4, y_pos, 0]),
                end=np.array([-total_w / 2 - 0.2, y_pos, 0]),
                color=GREY, stroke_width=1)
            tick_lbl = Text(f"{v:.2f}", font_size=12, color=GREY_B).next_to(
                tick_line, LEFT, buff=0.05)
            y_ticks.add(tick_line, tick_lbl)
        r2_label = Text("R²", font_size=18).move_to(
            np.array([-total_w / 2 - 1.0, y_base + bar_max_h / 2, 0]))
        self.play(FadeIn(y_ticks), FadeIn(r2_label))

        # ── Animate bars growing stage by stage ─────────────────────
        bars = []
        bar_labels = []
        value_labels = []
        prev_val = val_lo
        for i, (label_text, val, color) in enumerate(stages):
            cx = start_x + i * (bar_width + gap)
            h = val_to_h(val)
            bar = Rectangle(
                width=bar_width, height=h,
                fill_color=color, fill_opacity=0.8,
                stroke_color=WHITE, stroke_width=1,
            )
            bar.move_to(np.array([cx, y_base + h / 2, 0]))

            # Stage label below bar
            s_label = Text(label_text, font_size=13,
                           color=GREY_A).next_to(bar, DOWN, buff=0.15)

            # R² value on top
            v_label = Text(f"R² = {val:.3f}", font_size=16,
                           color=color, weight=BOLD).next_to(bar, UP, buff=0.08)

            bars.append(bar)
            bar_labels.append(s_label)
            value_labels.append(v_label)

            if i == 0:
                self.play(GrowFromEdge(bar, DOWN, run_time=1.0),
                          FadeIn(s_label), FadeIn(v_label))
            else:
                delta = val - stages[i - 1][1]
                delta_label = Text(f"+{delta:.3f}", font_size=14,
                                   color=YELLOW).next_to(v_label, RIGHT, buff=0.15)
                self.play(GrowFromEdge(bar, DOWN, run_time=0.8),
                          FadeIn(s_label), FadeIn(v_label), FadeIn(delta_label))
                if i == 3:
                    # Emphasise the biggest jump
                    flash_rect = SurroundingRectangle(
                        VGroup(bar, v_label, delta_label),
                        color=YELLOW, buff=0.1)
                    emphasis = Text("Biggest gain!", font_size=16,
                                    color=YELLOW, weight=BOLD)
                    emphasis.next_to(flash_rect, RIGHT, buff=0.2)
                    self.play(Create(flash_rect), FadeIn(emphasis))
                    self.wait(0.5)
                    self.play(FadeOut(flash_rect), FadeOut(emphasis))

            self.wait(0.4)

        # ── Oracle ceiling dashed line ──────────────────────────────
        oracle_y = y_base + val_to_h(oracle)
        oracle_line = DashedLine(
            start=np.array([-total_w / 2 - 0.4, oracle_y, 0]),
            end=np.array([total_w / 2 + 0.6, oracle_y, 0]),
            color=PURPLE, dash_length=0.1, stroke_width=2)
        oracle_lbl = Text(f"Oracle ceiling R² = {oracle:.3f}",
                          font_size=16, color=PURPLE, weight=BOLD)
        oracle_lbl.next_to(oracle_line, RIGHT, buff=0.1)
        self.play(Create(oracle_line), FadeIn(oracle_lbl))
        self.wait(0.5)

        # ── % of theoretical maximum ────────────────────────────────
        pct = stages[-1][1] / oracle * 100
        pct_lbl = Text(f"{pct:.1f}% of theoretical maximum",
                       font_size=18, color=YELLOW).to_edge(DOWN, buff=0.9)
        self.play(FadeIn(pct_lbl, shift=UP * 0.2))
        self.wait(0.5)

        # ── Block-CV honest estimate marker ─────────────────────────
        bcv_y = y_base + val_to_h(block_cv)
        bcv_line = DashedLine(
            start=np.array([-total_w / 2 - 0.4, bcv_y, 0]),
            end=np.array([total_w / 2 + 0.6, bcv_y, 0]),
            color=GREY_B, dash_length=0.08, stroke_width=1.5)
        bcv_lbl = Text(f"Block-CV honest R² = {block_cv:.3f}",
                       font_size=14, color=GREY_B)
        bcv_lbl.next_to(bcv_line, LEFT, buff=0.1)
        self.play(Create(bcv_line), FadeIn(bcv_lbl))
        self.wait(0.5)

        # ── Final insight ───────────────────────────────────────────
        final = Text("Stacking contributes more than any single feature group",
                     font_size=22, color=GOLD, weight=BOLD)
        final.to_edge(DOWN, buff=0.3)
        self.play(Write(final, run_time=1.5))
        self.wait(2)
        self.play(*[FadeOut(m) for m in self.mobjects])


# ════════════════════════════════════════════════════════════════════
# CLI entry point
# ════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("Render individual scenes with:")
    print("  manim -pql tools/viz_manim_scenes.py MealResponsePhenotypes")
    print("  manim -pql tools/viz_manim_scenes.py TemporalLeadLag")
    print("  manim -pql tools/viz_manim_scenes.py WindowSizeAnimation")
    print("  manim -pql tools/viz_manim_scenes.py ModelStackingProgression")
    print()
    print("For high quality: manim -pqh tools/viz_manim_scenes.py SceneName")
    print("Output goes to media/ directory")
