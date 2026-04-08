"""Manim animations for the Meal Detection via Supply × Demand report.

Scenes:
  1. ThroughputMealDetection — shows how S×D amplifies meal events
  2. GracefulDegradation — supply channel shifts as data disappears
  3. PreconditionGating — telemetry requirements animation
"""

from manim import *
import numpy as np

# ── colour constants ────────────────────────────────────────────────
C_SUPPLY  = GREEN
C_DEMAND  = RED
C_PRODUCT = PURPLE
C_GLUCOSE = BLUE
C_HEPATIC = ORANGE
C_CARB    = YELLOW


class ThroughputMealDetection(Scene):
    """Animate how supply × demand creates sharp meal peaks."""

    def construct(self):
        title = Text("Meal Detection via Throughput", font_size=32).to_edge(UP)
        self.play(Write(title))

        # Create three axes stacked vertically
        ax_s = Axes(
            x_range=[0, 24, 3], y_range=[0, 5, 1],
            x_length=10, y_length=1.8,
            axis_config={"include_tip": False, "font_size": 18},
        ).shift(UP * 1.5)
        lab_s = Text("Supply & Demand", font_size=16, color=WHITE
                     ).next_to(ax_s, LEFT, buff=0.2)

        ax_p = Axes(
            x_range=[0, 24, 3], y_range=[0, 8, 2],
            x_length=10, y_length=1.8,
            axis_config={"include_tip": False, "font_size": 18},
        ).shift(DOWN * 1.2)
        lab_p = Text("Throughput S×D", font_size=16, color=PURPLE
                     ).next_to(ax_p, LEFT, buff=0.2)

        x_lab = Text("Hour of Day", font_size=16).next_to(ax_p.x_axis, DOWN)

        self.play(
            Create(ax_s), Create(ax_p),
            Write(lab_s), Write(lab_p), Write(x_lab),
            run_time=1.5
        )

        # Define supply and demand as functions
        meal_times = [8, 12.5, 18.5]
        meal_sizes = [3.0, 2.0, 3.5]

        def supply_func(x):
            base = 1.0 + 0.2 * np.sin(2 * np.pi * x / 24)
            for mt, ms in zip(meal_times, meal_sizes):
                t = (x - mt) * 60
                if 0 < t < 180:
                    base += ms * np.exp(-(t-30)**2 / (2*40**2))
            return base

        def demand_func(x):
            base = 0.8
            for mt, ms in zip(meal_times, meal_sizes):
                t = (x - mt - 0.33) * 60  # 20-min lag
                if 0 < t < 240:
                    base += ms * 0.8 * np.exp(-(t-50)**2 / (2*50**2))
            return base

        def product_func(x):
            return supply_func(x) * demand_func(x)

        # Draw supply
        supply_graph = ax_s.plot(supply_func, x_range=[0, 24, 0.05],
                                color=GREEN, stroke_width=3)
        supply_area = ax_s.get_area(supply_graph, x_range=[0, 24],
                                    color=GREEN, opacity=0.15)

        # Draw demand
        demand_graph = ax_s.plot(demand_func, x_range=[0, 24, 0.05],
                                color=RED, stroke_width=3)

        self.play(
            Create(supply_graph), FadeIn(supply_area),
            run_time=2
        )
        self.play(Create(demand_graph), run_time=2)

        # Now show the product building up
        product_graph = ax_p.plot(product_func, x_range=[0, 24, 0.05],
                                 color=PURPLE, stroke_width=3)
        product_area = ax_p.get_area(product_graph, x_range=[0, 24],
                                     color=PURPLE, opacity=0.2)

        formula = MathTex(
            r"\text{Throughput} = \text{Supply} \times \text{Demand}",
            font_size=28, color=PURPLE
        ).next_to(ax_p, DOWN, buff=0.5)

        self.play(
            Create(product_graph), FadeIn(product_area),
            Write(formula),
            run_time=3
        )

        # Add meal markers
        for mt in meal_times:
            dot_s = Dot(ax_s.c2p(mt, supply_func(mt)), color=YELLOW, radius=0.08)
            dot_p = Dot(ax_p.c2p(mt + 0.5, product_func(mt + 0.5)),
                        color=YELLOW, radius=0.08)
            arrow = Triangle(color=WHITE, fill_color=WHITE, fill_opacity=1
                             ).scale(0.12).rotate(PI).move_to(
                                 ax_p.c2p(mt + 0.5, product_func(mt + 0.5) + 1))
            self.play(
                FadeIn(dot_s), FadeIn(dot_p), FadeIn(arrow),
                run_time=0.5
            )

        # Highlight: "18× at meal frequencies"
        highlight = Text("18× spectral power\nat meal frequencies",
                         font_size=22, color=YELLOW
                         ).to_edge(RIGHT).shift(DOWN)
        self.play(Write(highlight))
        self.wait(2)


class GracefulDegradation(Scene):
    """Animate supply channel shifting as carb data disappears."""

    def construct(self):
        title = Text("Graceful Degradation", font_size=32).to_edge(UP)
        subtitle = Text("Framework adapts when data is missing",
                        font_size=20, color=GRAY).next_to(title, DOWN, buff=0.2)
        self.play(Write(title), Write(subtitle))

        # Three columns representing patient types
        cols = [
            ("Traditional\nBoluser", [80, 10, 10], "sum_flux\n76% recall"),
            ("SMB-Dominant\n(7/11 patients)", [30, 50, 20], "residual\n65% recall"),
            ("100% UAM\n(live-split)", [0, 75, 25], "demand_only\n2.0/day"),
        ]

        bar_groups = VGroup()
        for i, (label, parts, method) in enumerate(cols):
            x_offset = (i - 1) * 4
            col_label = Text(label, font_size=16).move_to(
                [x_offset, -2.5, 0])

            # Stacked bars
            colors = [YELLOW, TEAL, ORANGE]
            y_start = -1.8
            bars = VGroup()
            for j, (pct, color) in enumerate(zip(parts, colors)):
                height = pct / 100 * 3.5
                if height > 0:
                    rect = Rectangle(
                        width=1.5, height=height,
                        fill_color=color, fill_opacity=0.7,
                        stroke_color=WHITE, stroke_width=1
                    ).move_to([x_offset, y_start + height/2, 0])
                    pct_label = Text(f"{pct}%", font_size=14
                                     ).move_to(rect.get_center())
                    bars.add(VGroup(rect, pct_label))
                    y_start += height

            method_label = Text(method, font_size=14, color=PURPLE
                                ).move_to([x_offset, y_start + 0.3, 0])
            bar_groups.add(VGroup(col_label, bars, method_label))

        # Legend
        legend = VGroup(
            VGroup(Square(0.2, fill_color=YELLOW, fill_opacity=0.7,
                          stroke_width=0),
                   Text("Explicit Carbs", font_size=14)).arrange(RIGHT, buff=0.1),
            VGroup(Square(0.2, fill_color=TEAL, fill_opacity=0.7,
                          stroke_width=0),
                   Text("Residual (implicit)", font_size=14)).arrange(RIGHT, buff=0.1),
            VGroup(Square(0.2, fill_color=ORANGE, fill_opacity=0.7,
                          stroke_width=0),
                   Text("Hepatic Only", font_size=14)).arrange(RIGHT, buff=0.1),
        ).arrange(DOWN, aligned_edge=LEFT, buff=0.1).to_edge(RIGHT).shift(UP)

        # Animate: show each column sequentially
        self.play(FadeIn(legend), run_time=1)

        for group in bar_groups:
            self.play(FadeIn(group), run_time=1.5)

        # Arrow showing degradation direction
        arrow = Arrow(start=LEFT*4 + DOWN*3, end=RIGHT*4 + DOWN*3,
                      color=GRAY, stroke_width=3)
        arrow_label = Text("Less data → framework adapts",
                           font_size=16, color=GRAY
                           ).next_to(arrow, DOWN, buff=0.15)
        self.play(Create(arrow), Write(arrow_label))
        self.wait(2)


class PreconditionGating(Scene):
    """Animate the precondition gating concept."""

    def construct(self):
        title = Text("Precondition Gating", font_size=32).to_edge(UP)
        self.play(Write(title))

        # Create a "day grid" — 61 days in ~9 rows of 7
        grid = VGroup()
        statuses = (
            ['ready'] * 50 + ['cgm_gap'] * 7 + ['ins_gap'] * 1 + ['both'] * 3
        )
        np.random.seed(42)
        np.random.shuffle(statuses)

        color_map = {
            'ready': GREEN,
            'cgm_gap': RED,
            'ins_gap': ORANGE,
            'both': GRAY,
        }

        rows, cols_per_row = 9, 7
        for i, status in enumerate(statuses):
            row = i // cols_per_row
            col = i % cols_per_row
            sq = Square(
                side_length=0.45,
                fill_color=color_map[status],
                fill_opacity=0.6,
                stroke_color=WHITE,
                stroke_width=1
            ).move_to([col * 0.55 - 1.65, -row * 0.55 + 2.0, 0])
            grid.add(sq)

        grid_label = Text("61 Calendar Days", font_size=18
                          ).next_to(grid, UP, buff=0.3)

        # Legend
        legend = VGroup(
            VGroup(Square(0.2, fill_color=GREEN, fill_opacity=0.6,
                          stroke_width=0),
                   Text("READY (50)", font_size=14)).arrange(RIGHT, buff=0.1),
            VGroup(Square(0.2, fill_color=RED, fill_opacity=0.6,
                          stroke_width=0),
                   Text("CGM Gap (7)", font_size=14)).arrange(RIGHT, buff=0.1),
            VGroup(Square(0.2, fill_color=ORANGE, fill_opacity=0.6,
                          stroke_width=0),
                   Text("INS Gap (1)", font_size=14)).arrange(RIGHT, buff=0.1),
            VGroup(Square(0.2, fill_color=GRAY, fill_opacity=0.6,
                          stroke_width=0),
                   Text("Both Gap (3)", font_size=14)).arrange(RIGHT, buff=0.1),
        ).arrange(DOWN, aligned_edge=LEFT, buff=0.1
                  ).next_to(grid, RIGHT, buff=0.8)

        self.play(FadeIn(grid), Write(grid_label), run_time=2)
        self.play(FadeIn(legend), run_time=1)

        # Preconditions box
        preconds = VGroup(
            Text("Preconditions:", font_size=18, color=YELLOW),
            Text("• CGM coverage ≥ 70%", font_size=16),
            Text("• Insulin telemetry ≥ 10%", font_size=16),
        ).arrange(DOWN, aligned_edge=LEFT, buff=0.15).to_edge(DOWN).shift(UP * 0.5 + LEFT * 2)

        self.play(Write(preconds), run_time=1.5)

        # Results comparison
        results = VGroup(
            Text("All 61 days → 82% detection", font_size=18, color=GRAY),
            Text("50 READY days → 96% detection", font_size=18, color=GREEN),
        ).arrange(DOWN, buff=0.2).next_to(preconds, RIGHT, buff=1.5)

        self.play(Write(results[0]), run_time=1)
        self.wait(0.5)

        # Highlight READY squares
        for sq, status in zip(grid, statuses):
            if status != 'ready':
                sq.generate_target()
                sq.target.set_opacity(0.15)
        anims = [MoveToTarget(sq) for sq, s in zip(grid, statuses) if s != 'ready']
        self.play(*anims, Write(results[1]), run_time=1.5)
        self.wait(2)


if __name__ == '__main__':
    print("Run with: manim -ql --format=gif meal_detection_animation.py <SceneName>")
