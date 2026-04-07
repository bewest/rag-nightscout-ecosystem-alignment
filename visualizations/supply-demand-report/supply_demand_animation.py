#!/usr/bin/env python3
"""
Supply-Demand Manim Animations
===============================

Animated visualizations of key supply-demand concepts using Manim.

Scenes:
  1. GlucoseConservation — Supply/demand balance animation
  2. PhaseLagAnimation — Animated phase lag between supply and demand
  3. InvisibleMetabolicWorld — AID masking metabolic flux
  4. EvolutionTimeline — PK → Flux → Supply-Demand progression

Render all:
  manim -ql supply_demand_animation.py --format=gif

Render individual scenes at higher quality:
  manim -qm supply_demand_animation.py GlucoseConservation --format=gif
"""

from manim import *
import numpy as np

# Color palette matching the matplotlib figures
GLUCOSE_BLUE = "#2196F3"
SUPPLY_GREEN = "#4CAF50"
DEMAND_RED = "#F44336"
HEPATIC_LT = "#8BC34A"
CARB_ORANGE = "#FF9800"
RESIDUAL_PURPLE = "#9C27B0"
NET_GREY = "#607D8B"
ACCENT_CYAN = "#00BCD4"


class GlucoseConservation(Scene):
    """Animate the glucose conservation law: ∫(Supply − Demand) ≈ ΔBG ≈ 0"""

    def construct(self):
        title = Text("Glucose Conservation Law", font_size=36, weight=BOLD)
        title.to_edge(UP, buff=0.3)
        self.play(Write(title))

        equation = MathTex(
            r"\Delta BG(t) = ",
            r"\underbrace{\text{Supply}(t)}_{\text{hepatic + carbs}}",
            r" - ",
            r"\underbrace{\text{Demand}(t)}_{\text{insulin action}}",
            r" + \varepsilon(t)",
            font_size=28
        )
        equation[1].set_color(SUPPLY_GREEN)
        equation[3].set_color(DEMAND_RED)
        equation[4].set_color(RESIDUAL_PURPLE)
        equation.next_to(title, DOWN, buff=0.3)
        self.play(Write(equation), run_time=2)
        self.wait(1)

        # Create axes for the balance visualization
        axes = Axes(
            x_range=[0, 12, 2],
            y_range=[-4, 4, 1],
            x_length=10,
            y_length=4,
            axis_config={"include_tip": False, "font_size": 20},
            x_axis_config={"numbers_to_include": range(0, 13, 2)},
        ).shift(DOWN * 0.8)
        x_label = Text("t (hours)", font_size=18).next_to(axes.x_axis, DOWN, buff=0.3)
        y_label = Text("Net flux", font_size=18).next_to(axes.y_axis, LEFT, buff=0.3).rotate(PI/2)
        self.play(Create(axes), Write(x_label), Write(y_label))

        # Animate supply - demand over 12 hours
        def net_flux(t):
            return 2.0 * np.sin(2*np.pi*t/4) + 1.5 * np.sin(2*np.pi*t/6)

        supply_curve = axes.plot(
            lambda t: max(net_flux(t), 0),
            x_range=[0, 12],
            color=SUPPLY_GREEN,
            stroke_width=0
        )
        demand_curve = axes.plot(
            lambda t: min(net_flux(t), 0),
            x_range=[0, 12],
            color=DEMAND_RED,
            stroke_width=0
        )
        net_curve = axes.plot(net_flux, x_range=[0, 12], color=NET_GREY, stroke_width=3)

        # Fill areas
        supply_area = axes.get_area(supply_curve, x_range=[0, 12],
                                     color=SUPPLY_GREEN, opacity=0.3)
        demand_area = axes.get_area(demand_curve, x_range=[0, 12],
                                     color=DEMAND_RED, opacity=0.3)

        self.play(Create(net_curve), run_time=2)
        self.play(FadeIn(supply_area), FadeIn(demand_area), run_time=1)

        # Labels
        supply_label = Text("Supply > Demand", font_size=16, color=SUPPLY_GREEN)
        supply_label.move_to(axes.c2p(3, 3))
        demand_label = Text("Demand > Supply", font_size=16, color=DEMAND_RED)
        demand_label.move_to(axes.c2p(5, -3))
        self.play(Write(supply_label), Write(demand_label))
        self.wait(1)

        # Show conservation result
        result_box = VGroup(
            Text("Over 12h:", font_size=20),
            MathTex(r"\int_0^{12} (\text{Supply} - \text{Demand})\, dt \approx 0",
                    font_size=24),
            Text("Green area ≈ Red area", font_size=18, color=NET_GREY),
            Text("EXP-421: mean = −1.8 ± 28.4 mg·h", font_size=16,
                 color=RESIDUAL_PURPLE, slant=ITALIC),
        ).arrange(DOWN, buff=0.15)
        result_box.move_to(axes.c2p(9.5, 2.5))
        box_bg = SurroundingRectangle(result_box, color=WHITE, fill_color=BLACK,
                                       fill_opacity=0.8, buff=0.15, corner_radius=0.1)
        self.play(FadeIn(box_bg), Write(result_box), run_time=2)
        self.wait(2)


class PhaseLagAnimation(Scene):
    """Animate the 20-min phase lag between supply and demand peaks."""

    def construct(self):
        title = Text("Phase Lag: Supply Leads Demand", font_size=36, weight=BOLD)
        title.to_edge(UP, buff=0.3)
        self.play(Write(title))

        axes = Axes(
            x_range=[-30, 240, 30],
            y_range=[0, 4, 1],
            x_length=10,
            y_length=4,
            axis_config={"include_tip": False, "font_size": 18},
        ).shift(DOWN * 0.5)
        x_label = Text("Minutes from meal", font_size=16).next_to(axes.x_axis, DOWN, buff=0.3)
        self.play(Create(axes), Write(x_label))

        # Supply curve (peaks earlier)
        def supply_fn(t):
            return 3.0 * np.exp(-0.5*((t-30)/25)**2) + 0.5*np.exp(-0.5*((t-80)/40)**2)

        def demand_fn(t):
            return 2.5 * np.exp(-0.5*((t-50)/30)**2) + 0.4*np.exp(-0.5*((t-100)/45)**2)

        # Animate supply appearing first
        supply_curve = axes.plot(supply_fn, x_range=[-30, 240],
                                 color=SUPPLY_GREEN, stroke_width=3)
        supply_label = Text("Supply (carbs + hepatic)", font_size=16, color=SUPPLY_GREEN)
        supply_label.next_to(supply_curve, UP, buff=0.1).shift(LEFT*2)

        self.play(Create(supply_curve), Write(supply_label), run_time=2)
        self.wait(0.5)

        # Then demand (delayed)
        demand_curve = axes.plot(demand_fn, x_range=[-30, 240],
                                  color=DEMAND_RED, stroke_width=3)
        demand_label = Text("Demand (insulin)", font_size=16, color=DEMAND_RED)
        demand_label.next_to(demand_curve, DOWN, buff=0.1).shift(RIGHT*2)

        self.play(Create(demand_curve), Write(demand_label), run_time=2)
        self.wait(0.5)

        # Mark peaks and show lag
        supply_peak = axes.c2p(30, supply_fn(30))
        demand_peak = axes.c2p(50, demand_fn(50))

        sp_dot = Dot(supply_peak, color=SUPPLY_GREEN, radius=0.1)
        dp_dot = Dot(demand_peak, color=DEMAND_RED, radius=0.1)
        self.play(Create(sp_dot), Create(dp_dot))

        sp_line = DashedLine(
            axes.c2p(30, 0), axes.c2p(30, supply_fn(30)),
            color=SUPPLY_GREEN, dash_length=0.1
        )
        dp_line = DashedLine(
            axes.c2p(50, 0), axes.c2p(50, demand_fn(50)),
            color=DEMAND_RED, dash_length=0.1
        )
        self.play(Create(sp_line), Create(dp_line))

        # Animated lag arrow
        lag_arrow = DoubleArrow(
            axes.c2p(30, -0.3), axes.c2p(50, -0.3),
            color=RESIDUAL_PURPLE, buff=0, stroke_width=4
        )
        lag_text = Text("~20 min lag", font_size=20, color=RESIDUAL_PURPLE, weight=BOLD)
        lag_text.next_to(lag_arrow, DOWN, buff=0.1)

        self.play(Create(lag_arrow), Write(lag_text), run_time=1)
        self.wait(1)

        # Show the two meal types
        box = VGroup(
            Text("Announced meals:", font_size=16, color=SUPPLY_GREEN),
            Text("  Phase lag = 10 min (pre-bolused)", font_size=14),
            Text("UAM meals:", font_size=16, color=DEMAND_RED),
            Text("  Phase lag = 45 min (AID reacts)", font_size=14),
            Text("35-min separation → meal classifier",
                 font_size=16, color=RESIDUAL_PURPLE, weight=BOLD),
        ).arrange(DOWN, buff=0.12, aligned_edge=LEFT)
        box.to_corner(DR, buff=0.3)
        box_bg = SurroundingRectangle(box, color=WHITE, fill_color=BLACK,
                                       fill_opacity=0.85, buff=0.15, corner_radius=0.1)
        self.play(FadeIn(box_bg), Write(box), run_time=2)
        self.wait(2)


class InvisibleMetabolicWorld(Scene):
    """Show how AID systems mask metabolic activity under flat glucose."""

    def construct(self):
        title = Text("The Invisible Metabolic World", font_size=36, weight=BOLD)
        subtitle = Text("Well-controlled glucose hides enormous metabolic activity",
                        font_size=20, color=GREY, slant=ITALIC)
        header = VGroup(title, subtitle).arrange(DOWN, buff=0.15)
        header.to_edge(UP, buff=0.2)
        self.play(Write(title), run_time=1)
        self.play(Write(subtitle), run_time=1)

        # Top axes: Glucose (flat)
        ax_top = Axes(
            x_range=[0, 24, 4],
            y_range=[60, 220, 40],
            x_length=10, y_length=2.5,
            axis_config={"include_tip": False, "font_size": 16},
        ).shift(UP * 0.5)
        top_label = Text("Glucose (mg/dL)", font_size=12).next_to(ax_top, LEFT, buff=0.1).rotate(PI/2)
        self.play(Create(ax_top), Write(top_label))

        # Nearly flat glucose with tiny meal bumps
        def glucose(t):
            g = 120 + 8*np.sin(2*np.pi*t/24)
            for mh in [7.5, 12.5, 18.5]:
                g += 25*np.exp(-0.5*((t-mh)/0.8)**2)
            return g

        glucose_curve = ax_top.plot(glucose, x_range=[0, 24],
                                     color=GLUCOSE_BLUE, stroke_width=3)
        target_area = ax_top.get_area(
            ax_top.plot(lambda t: 180, x_range=[0, 24], stroke_width=0),
            x_range=[0, 24], bounded_graph=ax_top.plot(lambda t: 70, x_range=[0, 24], stroke_width=0),
            color=GLUCOSE_BLUE, opacity=0.05
        )
        self.play(FadeIn(target_area), Create(glucose_curve), run_time=2)

        tir_label = Text("TIR = 92% — looks great!", font_size=16, color=SUPPLY_GREEN)
        tir_label.next_to(ax_top, RIGHT, buff=0.2)
        self.play(Write(tir_label))
        self.wait(1)

        # Question
        question = Text("But what's really happening underneath?",
                        font_size=20, color=CARB_ORANGE, weight=BOLD)
        question.move_to(ORIGIN)
        self.play(Write(question), run_time=1)
        self.wait(0.5)
        self.play(FadeOut(question))

        # Bottom axes: Metabolic flux (dramatic)
        ax_bot = Axes(
            x_range=[0, 24, 4],
            y_range=[0, 6, 1],
            x_length=10, y_length=2.5,
            axis_config={"include_tip": False, "font_size": 16},
        ).shift(DOWN * 2)
        bot_label = Text("Metabolic Flux", font_size=12).next_to(ax_bot, LEFT, buff=0.1).rotate(PI/2)
        self.play(Create(ax_bot), Write(bot_label))

        def supply(t):
            s = 1.2 + 0.2*np.sin(2*np.pi*t/24)
            for mh, c in [(7.5, 3), (12.5, 3.5), (18.5, 4)]:
                s += c * np.exp(-0.5*((t-mh)/0.6)**2)
            return s

        def demand(t):
            d = 0.8
            for mh, dose in [(7.5, 2.5), (12.5, 3), (18.5, 3.5)]:
                d += dose * np.exp(-0.5*((t-(mh+0.3))/0.7)**2)
            return d

        supply_curve = ax_bot.plot(supply, x_range=[0, 24],
                                    color=SUPPLY_GREEN, stroke_width=3)
        demand_curve = ax_bot.plot(demand, x_range=[0, 24],
                                    color=DEMAND_RED, stroke_width=3)

        supply_area = ax_bot.get_area(supply_curve, x_range=[0, 24],
                                       color=SUPPLY_GREEN, opacity=0.2)
        demand_area = ax_bot.get_area(demand_curve, x_range=[0, 24],
                                       color=DEMAND_RED, opacity=0.2)

        self.play(
            Create(supply_curve), Create(demand_curve),
            FadeIn(supply_area), FadeIn(demand_area),
            run_time=3
        )

        # Labels
        sl = Text("Supply", font_size=14, color=SUPPLY_GREEN)
        sl.move_to(ax_bot.c2p(20, 2))
        dl = Text("Demand", font_size=14, color=DEMAND_RED)
        dl.move_to(ax_bot.c2p(22, 1))
        self.play(Write(sl), Write(dl))

        # Meal markers
        for mh, name in [(7.5, "B"), (12.5, "L"), (18.5, "D")]:
            line = DashedLine(ax_bot.c2p(mh, 0), ax_bot.c2p(mh, 6),
                              color=CARB_ORANGE, dash_length=0.1, stroke_width=1)
            label = Text(name, font_size=12, color=CARB_ORANGE)
            label.next_to(line, UP, buff=0.05)
            self.play(Create(line), Write(label), run_time=0.3)

        # Insight
        insight = Text(
            "3-8× metabolic activity during meals — invisible in glucose!",
            font_size=18, color=ACCENT_CYAN, weight=BOLD
        )
        insight.next_to(ax_bot, DOWN, buff=0.3)
        self.play(Write(insight), run_time=2)
        self.wait(2)


class EvolutionTimeline(Scene):
    """Animated timeline showing PK → Flux → Supply-Demand evolution."""

    def construct(self):
        title = Text("Evolution of Glucose Modeling", font_size=36, weight=BOLD)
        title.to_edge(UP, buff=0.3)
        self.play(Write(title))

        # Timeline base
        timeline = Line(LEFT*5.5, RIGHT*5.5, color=WHITE, stroke_width=2)
        timeline.shift(DOWN*0.5)
        self.play(Create(timeline))

        # Era 1
        e1_dot = Dot(LEFT*4, color=GLUCOSE_BLUE, radius=0.15).shift(DOWN*0.5)
        e1_title = Text("Classical PK", font_size=20, color=GLUCOSE_BLUE, weight=BOLD)
        e1_title.next_to(e1_dot, UP, buff=0.3)
        e1_items = VGroup(
            Text("• IOB / COB", font_size=14),
            Text("• Simple decay curves", font_size=14),
            Text("• Zero when no events", font_size=14),
        ).arrange(DOWN, buff=0.08, aligned_edge=LEFT)
        e1_items.next_to(e1_title, UP, buff=0.15)
        e1_label = Text("EXP-001–341", font_size=12, color=GREY, slant=ITALIC)
        e1_label.next_to(e1_dot, DOWN, buff=0.2)

        self.play(Create(e1_dot), Write(e1_title), run_time=1)
        self.play(Write(e1_items), Write(e1_label), run_time=1.5)
        self.wait(1)

        # Arrow 1→2
        arr1 = Arrow(LEFT*2.5, LEFT*0.5, color=WHITE, stroke_width=3).shift(DOWN*0.5)
        self.play(Create(arr1))

        # Era 2
        e2_dot = Dot(ORIGIN, color=SUPPLY_GREEN, radius=0.15).shift(DOWN*0.5)
        e2_title = Text("Metabolic Flux", font_size=20, color=SUPPLY_GREEN, weight=BOLD)
        e2_title.next_to(e2_dot, UP, buff=0.3)
        e2_items = VGroup(
            Text("• |Supply| + |Demand|", font_size=14),
            Text("• Hepatic production", font_size=14),
            Text("• Always non-zero", font_size=14),
            Text("• AUC 0.87–0.95", font_size=14),
        ).arrange(DOWN, buff=0.08, aligned_edge=LEFT)
        e2_items.next_to(e2_title, UP, buff=0.15)
        e2_label = Text("EXP-435–440", font_size=12, color=GREY, slant=ITALIC)
        e2_label.next_to(e2_dot, DOWN, buff=0.2)

        self.play(Create(e2_dot), Write(e2_title), run_time=1)
        self.play(Write(e2_items), Write(e2_label), run_time=1.5)
        self.wait(1)

        # Arrow 2→3
        arr2 = Arrow(RIGHT*1.5, RIGHT*3.5, color=WHITE, stroke_width=3).shift(DOWN*0.5)
        self.play(Create(arr2))

        # Era 3
        e3_dot = Dot(RIGHT*4, color=RESIDUAL_PURPLE, radius=0.15).shift(DOWN*0.5)
        e3_title = Text("Supply-Demand", font_size=20, color=RESIDUAL_PURPLE, weight=BOLD)
        e3_title.next_to(e3_dot, UP, buff=0.3)
        e3_items = VGroup(
            Text("• dBG/dt = S − D + ε", font_size=14),
            Text("• Conservation law", font_size=14),
            Text("• Phase lag classifier", font_size=14),
            Text("• Fidelity score 15–84", font_size=14),
        ).arrange(DOWN, buff=0.08, aligned_edge=LEFT)
        e3_items.next_to(e3_title, UP, buff=0.15)
        e3_label = Text("EXP-441–493", font_size=12, color=GREY, slant=ITALIC)
        e3_label.next_to(e3_dot, DOWN, buff=0.2)

        self.play(Create(e3_dot), Write(e3_title), run_time=1)
        self.play(Write(e3_items), Write(e3_label), run_time=1.5)
        self.wait(1)

        # Final insight
        insight = VGroup(
            Text("Key Insight:", font_size=18, color=ACCENT_CYAN, weight=BOLD),
            Text("Conservation of glucose provides diagnostic power",
                 font_size=16, color=WHITE),
            Text("from a fundamental symmetry of the physics.",
                 font_size=16, color=WHITE),
        ).arrange(DOWN, buff=0.08)
        insight.to_edge(DOWN, buff=0.3)
        box_bg = SurroundingRectangle(insight, color=ACCENT_CYAN,
                                       fill_color=BLACK, fill_opacity=0.85,
                                       buff=0.15, corner_radius=0.1)
        self.play(FadeIn(box_bg), Write(insight), run_time=2)
        self.wait(3)
