#!/usr/bin/env python3
"""Analyze Subject 2 Cancel runs with an auditable, descriptive workflow.

The Cancel files contain one 16-ball block per logged ID in standard runs.
The first 48 rows of the 64-row dwellDirection run are the primary 3-ID
dataset; cases 49-64 are retained as supplemental raw events. Start-ball
rows are audited but excluded from the 15-event primary condition summaries.

The script writes CSV summaries, a quality report, a matched exploratory
comparison with Subject 2 Trigger summaries, and static PNG figures. Raw
input files are never overwritten.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Sequence

from PIL import Image, ImageDraw, ImageFont


SUBJECT_ID = 2
CHART_SCOPE_LABEL = "All non-start events"
CASES_PER_ID_RAW = 16
CASES_PER_ID_FORMAL = 15
EXPECTED_TECHNIQUES = 15
EXPECTED_PRIMARY_ROWS = EXPECTED_TECHNIQUES * 3 * CASES_PER_ID_FORMAL
SUPPLEMENTAL_TECHNIQUE = "dwellDirection"
SUPPLEMENTAL_PRIMARY_CASE_LIMIT = 48

ID_BY_DIAMETER = {
    0.5: ("L-ID", 2.713),
    0.6: ("M-ID", 3.459),
    0.7: ("H-ID", 4.605),
}
ID_ORDER = ["L-ID", "M-ID", "H-ID"]
RAW_ID_TO_LEVEL = {1: "L-ID", 2: "M-ID", 3: "H-ID"}

TIME_INDEX = {
    "case": 0,
    "logged_id_code": 1,
    "in_target_times": 2,
    "used_time_s": 8,
    "trigger_condition": 9,
    "start_ball": 10,
    "direction": 11,
    "technique": 12,
    "ball_index": 13,
    "react_time_s": 14,
    "react_frequency": 15,
    "obstacle_react_frequency": 16,
    "trigger_time_s": 17,
    "cancel_time_s": 18,
    "is_mine_ball": 19,
    "successfully_canceled": 20,
    "cancel_reason": 21,
    "no_trigger_reason": 22,
    "cancel_times": 23,
    "direction_angle_frame": 24,
    "direction_speed_min": 25,
}

CANONICAL_TECHNIQUE_ORDER = [
    "pinchReleaseTrigger",
    "pinchDwell",
    "pinchDirection",
    "pinchThumbSwipe",
    "dwell",
    "dwellRelease",
    "dwellDirection",
    "speed",
    "speedDwell",
    "speedRelease",
    "speedDirection",
    "release010",
    "time010",
    "direction010",
    "contact010",
]

TECHNIQUE_SHORT = {
    technique: f"T{index:02d}"
    for index, technique in enumerate(CANONICAL_TECHNIQUE_ORDER, start=1)
}

PALETTE = [
    "#4E79A7",
    "#F28E2B",
    "#E15759",
    "#76B7B2",
    "#59A14F",
    "#EDC948",
    "#B07AA1",
    "#FF9DA7",
    "#9C755F",
    "#BAB0AC",
    "#1F77B4",
    "#D62728",
    "#2CA02C",
    "#9467BD",
    "#8C564B",
]


def parse_args() -> argparse.Namespace:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--subject-id", type=int, default=SUBJECT_ID)
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=root / "2" / "Cancel",
        help="Subject Cancel directory containing run folders.",
    )
    parser.add_argument(
        "--trigger-summary",
        type=Path,
        default=root / "analysis_outputs" / "subject2_trigger" / "id_technique_metrics.csv",
        help="Existing Subject 2 Trigger summary used for exploratory comparison.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=root / "analysis_outputs" / "subject2_cancel",
    )
    return parser.parse_args()


def finite_float(value: Any) -> float | None:
    try:
        result = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def nonnegative_float(value: Any) -> float | None:
    result = finite_float(value)
    return result if result is not None and result >= 0 else None


def finite_int(value: Any) -> int | None:
    try:
        result = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return result


def parse_bool(value: Any) -> bool | None:
    text = str(value).strip().lower()
    if text == "true":
        return True
    if text == "false":
        return False
    return None


def parse_sentinel_float(value: Any) -> float | None:
    """Return finite nonnegative values; NA, blank and -1 are missing."""

    return nonnegative_float(value)


def sample_sd(values: Sequence[float]) -> float | None:
    return statistics.stdev(values) if len(values) > 1 else (0.0 if values else None)


def median_or_none(values: Sequence[float]) -> float | None:
    return statistics.median(values) if values else None


def iqr(values: Sequence[float]) -> float | None:
    if len(values) < 2:
        return 0.0 if values else None
    ordered = sorted(values)
    midpoint = len(ordered) // 2
    if len(ordered) % 2:
        lower = ordered[:midpoint]
        upper = ordered[midpoint + 1 :]
    else:
        lower = ordered[:midpoint]
        upper = ordered[midpoint:]
    return statistics.median(upper) - statistics.median(lower)


def round_value(value: Any, digits: int = 6) -> Any:
    if isinstance(value, float):
        return round(value, digits)
    return value


def target_points(row: Sequence[str]) -> list[tuple[float, float, float]]:
    # The coordinate list is the final 17 XYZ triples even though the number
    # of preceding diagnostic columns differs between file versions.
    values = [finite_float(value) for value in row[-51:]]
    if len(values) != 51 or any(value is None for value in values):
        raise ValueError(f"Malformed target coordinates: {len(values)} values")
    return [
        (float(values[index]), float(values[index + 1]), float(values[index + 2]))
        for index in range(0, 51, 3)
    ]


def layout_diameter(points: Sequence[tuple[float, float, float]]) -> float:
    return max(math.dist(first, second) for first in points for second in points)


def match_id(diameter_m: float, tolerance: float = 1e-4) -> tuple[str, float]:
    for expected, id_info in ID_BY_DIAMETER.items():
        if abs(diameter_m - expected) <= tolerance:
            return id_info
    raise ValueError(f"Unexpected target-layout diameter: {diameter_m:.6f} m")


def trajectory_distances(path: Path) -> tuple[dict[int, float], dict[int, int], set[int]]:
    points_by_case: dict[int, list[tuple[float, float, float]]] = defaultdict(list)
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            try:
                case = int(row["Case"])
                point = (
                    float(row["indexLocX"]),
                    float(row["indexLocY"]),
                    float(row["indexLocZ"]),
                )
            except (KeyError, TypeError, ValueError):
                continue
            if all(math.isfinite(value) for value in point):
                points_by_case[case].append(point)

    distances: dict[int, float] = {}
    counts: dict[int, int] = {}
    for case, points in points_by_case.items():
        distances[case] = sum(
            math.dist(points[index - 1], points[index])
            for index in range(1, len(points))
        )
        counts[case] = len(points)
    return distances, counts, set(points_by_case)


def read_time_rows(path: Path) -> tuple[list[str], list[list[str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.reader(handle))
    if not rows:
        raise ValueError(f"Empty time CSV: {path}")
    return rows[0], rows[1:]


def exact_binomial_interval(successes: int, total: int, alpha: float = 0.05) -> tuple[float | None, float | None]:
    """Clopper-Pearson interval using binomial-tail bisection."""

    if total <= 0:
        return None, None

    def pmf(index: int, probability: float) -> float:
        if probability <= 0:
            return 1.0 if index == 0 else 0.0
        if probability >= 1:
            return 1.0 if index == total else 0.0
        return math.comb(total, index) * probability**index * (1 - probability) ** (total - index)

    def cdf_le(index: int, probability: float) -> float:
        return sum(pmf(item, probability) for item in range(0, index + 1))

    def tail_ge(index: int, probability: float) -> float:
        return sum(pmf(item, probability) for item in range(index, total + 1))

    if successes <= 0:
        lower = 0.0
    else:
        lo, hi = 0.0, 1.0
        target = alpha / 2
        for _ in range(90):
            mid = (lo + hi) / 2
            if tail_ge(successes, mid) < target:
                lo = mid
            else:
                hi = mid
        lower = hi

    if successes >= total:
        upper = 1.0
    else:
        lo, hi = 0.0, 1.0
        target = alpha / 2
        for _ in range(90):
            mid = (lo + hi) / 2
            if cdf_le(successes, mid) > target:
                lo = mid
            else:
                hi = mid
        upper = lo
    return lower, upper


def normalize_reason(text: str) -> list[str]:
    if not text or text.strip().upper() in {"NA", "NONE"}:
        return []
    categories: list[str] = []
    for segment in text.split(","):
        segment = segment.strip()
        if not segment or segment.upper() == "NA":
            continue
        lower = segment.lower()
        if "direction" in lower:
            category = "direction"
        elif "thumb" in lower:
            category = "thumb_contact"
        elif "contact" in lower or "outside" in lower:
            category = "contact_transition"
        elif "dwell" in lower:
            category = "dwell"
        elif "release" in lower:
            category = "release"
        elif "speed" in lower:
            category = "speed"
        elif "pinch" in lower:
            category = "pinch"
        elif "react_stage" in lower:
            category = "react_stage"
        else:
            category = re.split(r"[;:]", segment, maxsplit=1)[0].strip() or "other"
        categories.append(category)
    return categories


def json_or_blank(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def write_csv(path: Path, rows: Sequence[dict[str, Any]], fields: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields), extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    field: round_value(row.get(field))
                    if isinstance(row.get(field), float)
                    else ("" if row.get(field) is None else row.get(field))
                    for field in fields
                }
            )


def load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        Path(r"C:\Windows\Fonts\arialbd.ttf" if bold else r"C:\Windows\Fonts\arial.ttf"),
        Path(r"C:\Windows\Fonts\msyhbd.ttc" if bold else r"C:\Windows\Fonts\msyh.ttc"),
    ]
    for path in candidates:
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


def hex_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[index : index + 2], 16) for index in (0, 2, 4))


def draw_text_centered(draw: ImageDraw.ImageDraw, xy: tuple[float, float], text: str, font: Any, fill: tuple[int, int, int]) -> None:
    box = draw.textbbox((0, 0), text, font=font)
    draw.text(
        (xy[0] - (box[2] - box[0]) / 2, xy[1] - (box[3] - box[1]) / 2),
        text,
        font=font,
        fill=fill,
    )


def metric_value(row: dict[str, Any], key: str) -> float | None:
    value = row.get(key)
    return finite_float(value)


def draw_technique_legend(
    draw: ImageDraw.ImageDraw,
    origin: tuple[int, int],
    technique_order: Sequence[str],
    columns: int = 1,
    column_width: int = 0,
    row_height: int = 54,
    font_size: int = 21,
) -> None:
    """Draw the fixed technique-color legend used in the Trigger figures."""
    font = load_font(font_size)
    x0, y0 = origin
    rows_per_column = math.ceil(len(technique_order) / columns)
    for index, technique in enumerate(technique_order):
        column = index // rows_per_column
        row = index % rows_per_column
        x = x0 + column * column_width
        y = y0 + row * row_height
        color = hex_rgb(PALETTE[index % len(PALETTE)])
        draw.rounded_rectangle((x, y + 4, x + 25, y + 29), radius=4, fill=color)
        draw.text((x + 36, y), f"{index + 1:02d}  {technique}", font=font, fill=(45, 55, 70))


def draw_trigger_style_bar_panel(
    draw: ImageDraw.ImageDraw,
    bounds: tuple[int, int, int, int],
    summaries: Sequence[dict[str, Any]],
    metric: str,
    title: str,
    unit: str,
    error_key: str | None = None,
    show_legend: bool = True,
    percentage: bool = False,
    fixed_y_max: float | None = None,
) -> None:
    """Render a 3-ID, 15-technique bar chart matching Trigger figures."""
    left, top, right, bottom = bounds
    scale = 1.15
    title_font = load_font(int(34 * scale), bold=True)
    axis_font = load_font(int(22 * scale))
    tick_font = load_font(int(18 * scale))
    number_font = load_font(int(12 * scale), bold=True)
    id_font = load_font(int(22 * scale), bold=True)
    dark = (30, 41, 59)
    muted = (80, 90, 105)

    chart_left = left + int(105 * scale)
    legend_space = int(500 * scale) if show_legend else int(25 * scale)
    chart_right = right - legend_space
    chart_top = top + int(95 * scale)
    chart_bottom = bottom - int(145 * scale)

    values = [metric_value(row, metric) for row in summaries]
    values = [value for value in values if value is not None]
    error_values: list[float] = []
    if error_key:
        for row in summaries:
            mean = metric_value(row, metric)
            error = metric_value(row, error_key)
            if mean is not None and error is not None:
                error_values.append(mean + error)
    if fixed_y_max is not None:
        y_max = fixed_y_max
    elif percentage:
        y_max = 1.0
    else:
        maximum = max(values + error_values) if error_values else max(values, default=0.0)
        y_max = maximum * 1.12 if maximum > 0 else 1.0

    def y_pos(value: float) -> float:
        return chart_bottom - value / y_max * (chart_bottom - chart_top)

    draw.text((left + 10, top + 5), title, font=title_font, fill=dark)
    for index in range(6):
        value = y_max * index / 5
        y = y_pos(value)
        draw.line([(chart_left, y), (chart_right, y)], fill=(222, 227, 234), width=max(1, int(2 * scale)))
        label = f"{value:.0%}" if percentage else (f"{value:.2f}" if y_max < 10 else f"{value:.1f}")
        box = draw.textbbox((0, 0), label, font=tick_font)
        draw.text((chart_left - (box[2] - box[0]) - 14, y - (box[3] - box[1]) / 2), label, font=tick_font, fill=muted)

    draw.line([(chart_left, chart_top), (chart_left, chart_bottom)], fill=(75, 85, 100), width=max(2, int(3 * scale)))
    draw.line([(chart_left, chart_bottom), (chart_right, chart_bottom)], fill=(75, 85, 100), width=max(2, int(3 * scale)))

    by_key = {(row["technique"], row["id_level"]): row for row in summaries}
    plot_width = chart_right - chart_left
    outer_gap = int(18 * scale)
    group_gap = int(28 * scale)
    group_width = (plot_width - 2 * outer_gap - 2 * group_gap) / 3
    bar_gap = max(1.0, 2.0 * scale)
    bar_width = (group_width - bar_gap * (len(CANONICAL_TECHNIQUE_ORDER) - 1)) / len(CANONICAL_TECHNIQUE_ORDER)

    for id_index, id_level in enumerate(ID_ORDER):
        group_left = chart_left + outer_gap + id_index * (group_width + group_gap)
        group_right = group_left + group_width
        if id_index % 2 == 0:
            draw.rectangle((group_left - 5, chart_top, group_right + 5, chart_bottom), fill=(244, 246, 249))
            for grid_index in range(6):
                y = y_pos(y_max * grid_index / 5)
                draw.line([(group_left - 5, y), (group_right + 5, y)], fill=(222, 227, 234), width=max(1, int(2 * scale)))

        for technique_index, technique in enumerate(CANONICAL_TECHNIQUE_ORDER):
            row = by_key.get((technique, id_level), {})
            value = metric_value(row, metric)
            x1 = group_left + technique_index * (bar_width + bar_gap)
            x2 = x1 + bar_width
            if value is not None:
                y = y_pos(min(y_max, max(0.0, value)))
                color = hex_rgb(PALETTE[technique_index % len(PALETTE)])
                draw.rectangle((x1, y, x2, chart_bottom), fill=color, outline=(255, 255, 255), width=max(1, int(scale)))
                if error_key:
                    error = metric_value(row, error_key)
                    if error is not None:
                        upper = y_pos(min(y_max, value + error))
                        lower = y_pos(max(0.0, value - error))
                        center = (x1 + x2) / 2
                        cap = max(2, bar_width * 0.35)
                        draw.line([(center, upper), (center, lower)], fill=(48, 58, 72), width=max(1, int(2 * scale)))
                        draw.line([(center - cap, upper), (center + cap, upper)], fill=(48, 58, 72), width=max(1, int(2 * scale)))
                        draw.line([(center - cap, lower), (center + cap, lower)], fill=(48, 58, 72), width=max(1, int(2 * scale)))
            draw_text_centered(draw, ((x1 + x2) / 2, chart_bottom + int(14 * scale)), f"{technique_index + 1}", number_font, (68, 78, 92))

        id_bits = metric_value(
            by_key.get((CANONICAL_TECHNIQUE_ORDER[0], id_level), {}),
            "id_bits",
        )
        if id_bits is None:
            id_bits = {"L-ID": 2.713, "M-ID": 3.459, "H-ID": 4.605}[id_level]
        draw_text_centered(draw, ((group_left + group_right) / 2, chart_bottom + int(48 * scale)), f"{id_level}  ({id_bits:.3f} bits)", id_font, (45, 55, 70))
        if id_index < 2:
            separator = group_right + group_gap / 2
            draw.line([(separator, chart_top), (separator, chart_bottom + 5)], fill=(195, 202, 212), width=max(1, int(2 * scale)))

    draw_text_centered(draw, ((chart_left + chart_right) / 2, bottom - int(30 * scale)), "Index of Difficulty — technique order 01 to 15 within each ID", axis_font, (45, 55, 70))
    draw_text_centered(draw, (left + int(24 * scale), (chart_top + chart_bottom) / 2), unit, axis_font, (45, 55, 70))
    if show_legend:
        draw_technique_legend(
            draw,
            (chart_right + int(48 * scale), chart_top),
            CANONICAL_TECHNIQUE_ORDER,
            columns=1,
            row_height=int(47 * scale),
            font_size=int(18 * scale),
        )


def draw_trigger_style_bar_chart(
    output: Path,
    summaries: Sequence[dict[str, Any]],
    metric: str,
    title: str,
    unit: str,
    error_key: str | None = None,
    percentage: bool = False,
    fixed_y_max: float | None = None,
) -> None:
    width, height = 2400, 1600
    image = Image.new("RGB", (width, height), (249, 250, 252))
    draw = ImageDraw.Draw(image)
    draw_trigger_style_bar_panel(
        draw,
        (90, 70, 2310, 1510),
        summaries,
        metric,
        f"{title} — Subject {SUBJECT_ID}",
        unit,
        error_key=error_key,
        percentage=percentage,
        fixed_y_max=fixed_y_max,
    )
    image.save(output, format="PNG", optimize=True)


def render_trigger_style_metric_charts(output_dir: Path, summaries: Sequence[dict[str, Any]]) -> None:
    charts = [
        ("cancel_success_rate", "Cancel Success Rate", "Success rate", None, True, 1.0, "cancel_success_rate_by_id.png"),
        ("cancel_failure_rate", "Cancel Failure/Error Rate", "Failure/error rate", None, True, 1.0, "cancel_failure_rate_by_id.png"),
        ("cancel_time_mean_s", "Mean Cancel Time", "Cancel time (s)", "cancel_time_sd_s", False, None, "cancel_time_by_id.png"),
        ("target_activation_rate", "Target Activation Rate", "Activation rate", None, True, 1.0, "target_activation_rate_by_id.png"),
        ("target_trigger_time_mean_s", "Target Trigger Time", "Trigger time (s)", "target_trigger_time_sd_s", False, None, "target_trigger_time_by_id.png"),
        ("task_completion_time_all_s", f"Task Time ({CHART_SCOPE_LABEL})", "Time (s)", None, False, None, "task_time_by_id.png"),
        ("movement_distance_all_m", f"Movement Distance ({CHART_SCOPE_LABEL})", "Distance (m)", None, False, None, "movement_distance_by_id.png"),
    ]
    for metric, title, unit, error_key, percentage, fixed_y_max, filename in charts:
        draw_trigger_style_bar_chart(
            output_dir / filename,
            summaries,
            metric,
            title,
            unit,
            error_key=error_key,
            percentage=percentage,
            fixed_y_max=fixed_y_max,
        )


def draw_bar_chart(
    output: Path,
    title: str,
    metric_keys: Sequence[str],
    metric_labels: Sequence[str],
    summaries: Sequence[dict[str, Any]],
    value_format: str = "{:.2f}",
    y_label: str = "Value",
    percent: bool = False,
) -> None:
    width, height = 2600, 1650
    image = Image.new("RGB", (width, height), (249, 250, 252))
    draw = ImageDraw.Draw(image)
    title_font = load_font(42, bold=True)
    axis_font = load_font(24)
    tick_font = load_font(18)
    legend_font = load_font(20)
    technique_font = load_font(17)
    dark = (30, 41, 59)
    muted = (80, 90, 105)
    draw.text((80, 48), title, font=title_font, fill=dark)
    draw.text((82, 103), "Subject 2 | primary non-start events | descriptive only", font=axis_font, fill=muted)

    left, top, right, bottom = 150, 175, width - 105, height - 250
    values = [
        metric_value(row, key)
        for row in summaries
        for key in metric_keys
        if metric_value(row, key) is not None
    ]
    max_value = max(values) if values else 1.0
    if percent:
        max_value = max(1.0, max_value)
    else:
        max_value = max_value * 1.15 if max_value > 0 else 1.0

    def y_pos(value: float) -> float:
        return bottom - (value / max_value) * (bottom - top)

    for tick_index in range(6):
        value = max_value * tick_index / 5
        y = y_pos(value)
        draw.line([(left, y), (right, y)], fill=(222, 227, 234), width=2)
        label = f"{value * 100:.0f}%" if percent else value_format.format(value)
        box = draw.textbbox((0, 0), label, font=tick_font)
        draw.text((left - (box[2] - box[0]) - 16, y - 10), label, font=tick_font, fill=muted)

    draw.line([(left, top), (left, bottom)], fill=(75, 85, 100), width=3)
    draw.line([(left, bottom), (right, bottom)], fill=(75, 85, 100), width=3)

    techniques = CANONICAL_TECHNIQUE_ORDER
    group_width = (right - left) / len(techniques)
    bar_gap = 8
    bar_width = max(8, (group_width - 24 - bar_gap * (len(metric_keys) - 1)) / len(metric_keys))
    for technique_index, technique in enumerate(techniques):
        rows = [row for row in summaries if row["technique"] == technique]
        group_left = left + technique_index * group_width
        for metric_index, key in enumerate(metric_keys):
            metric_rows = [row for row in rows if row["id_level"] == ID_ORDER[metric_index % 3]]
            # For metric panels where keys correspond to ID levels, use the
            # explicit ID row. For one metric per row, use the first row.
            if len(metric_keys) == 3:
                source = metric_rows[0] if metric_rows else None
                value = metric_value(source, key) if source else None
            else:
                source = next((row for row in rows if row["id_level"] == ID_ORDER[metric_index % 3]), None)
                value = metric_value(source, key) if source else None
            if value is None:
                continue
            x1 = group_left + 12 + metric_index * (bar_width + bar_gap)
            x2 = x1 + bar_width
            y = y_pos(value)
            draw.rectangle((x1, y, x2, bottom), fill=hex_rgb(PALETTE[metric_index % len(PALETTE)]))
        draw_text_centered(draw, (group_left + group_width / 2, bottom + 36), TECHNIQUE_SHORT[technique], technique_font, muted)

    draw_text_centered(draw, ((left + right) / 2, height - 62), "Technique (T01-T15; see legend)", axis_font, dark)
    draw_text_centered(draw, (42, (top + bottom) / 2), y_label, axis_font, dark)
    legend_x, legend_y = 160, height - 155
    for index, (label, key) in enumerate(zip(metric_labels, metric_keys)):
        x = legend_x + index * 430
        draw.rectangle((x, legend_y - 9, x + 24, legend_y + 15), fill=hex_rgb(PALETTE[index % len(PALETTE)]))
        draw.text((x + 35, legend_y - 12), label, font=legend_font, fill=muted)
    legend2 = " | ".join(f"{TECHNIQUE_SHORT[t]}={t}" for t in techniques)
    draw.text((160, height - 112), legend2, font=load_font(15), fill=(105, 112, 125))
    image.save(output, format="PNG", optimize=True)


def draw_rate_heatmap(output: Path, summaries: Sequence[dict[str, Any]]) -> None:
    width, height = 2350, 1500
    image = Image.new("RGB", (width, height), (249, 250, 252))
    draw = ImageDraw.Draw(image)
    title_font = load_font(42, bold=True)
    header_font = load_font(24, bold=True)
    cell_font = load_font(19, bold=True)
    small_font = load_font(17)
    dark = (30, 41, 59)
    muted = (80, 90, 105)
    draw.text((80, 45), "Cancel Success and Failure Rates by Technique × ID", font=title_font, fill=dark)
    draw.text((82, 101), "Primary non-start mine events; denominators are shown in each cell", font=small_font, fill=muted)

    panels = [
        ("Cancel Success Rate", "cancel_success_rate", (220, 55, 120, 70)),
        ("Cancel Failure/Error Rate", "cancel_failure_rate", (220, 70, 55, 65)),
    ]
    for panel_index, (panel_title, key, color) in enumerate(panels):
        x0 = 95 + panel_index * 1110
        y0 = 185
        label_w = 300
        cell_w = 235
        cell_h = 67
        draw.text((x0, y0 - 52), panel_title, font=header_font, fill=dark)
        for id_index, id_level in enumerate(ID_ORDER):
            draw_text_centered(draw, (x0 + label_w + cell_w * id_index + cell_w / 2, y0 - 16), id_level, header_font, muted)
        for technique_index, technique in enumerate(CANONICAL_TECHNIQUE_ORDER):
            y = y0 + technique_index * cell_h
            draw.text((x0, y + 18), f"{TECHNIQUE_SHORT[technique]}  {technique}", font=small_font, fill=muted)
            for id_index, id_level in enumerate(ID_ORDER):
                row = next(row for row in summaries if row["technique"] == technique and row["id_level"] == id_level)
                value = metric_value(row, key)
                mine_n = int(row["mine_event_n"])
                success_n = int(row["mine_cancel_success_n"] if key == "cancel_success_rate" else row["mine_cancel_failure_n"])
                x1 = x0 + label_w + cell_w * id_index
                x2 = x1 + cell_w - 8
                y1 = y + 7
                y2 = y1 + cell_h - 12
                if value is None:
                    fill = (225, 229, 234)
                    label = "NA"
                else:
                    shade = max(0.0, min(1.0, float(value)))
                    fill = tuple(int(245 - shade * (245 - base)) for base in color)
                    label = f"{value:.1%} ({success_n}/{mine_n})"
                draw.rounded_rectangle((x1, y1, x2, y2), radius=7, fill=fill, outline=(210, 216, 225), width=1)
                draw_text_centered(draw, ((x1 + x2) / 2, (y1 + y2) / 2), label, cell_font, dark)
    draw.text((95, height - 70), "T01-T15 correspond to the full technique names shown beside each row", font=small_font, fill=muted)
    image.save(output, format="PNG", optimize=True)


def draw_three_panel_line_chart(
    output: Path,
    title: str,
    summaries: Sequence[dict[str, Any]],
    metric_key: str,
    y_label: str,
    error_key: str | None = None,
    comparison: Sequence[dict[str, Any]] | None = None,
    comparison_key: str | None = None,
) -> None:
    width, height = 2450, 1650
    image = Image.new("RGB", (width, height), (249, 250, 252))
    draw = ImageDraw.Draw(image)
    title_font = load_font(42, bold=True)
    axis_font = load_font(24)
    small_font = load_font(17)
    dark = (30, 41, 59)
    muted = (80, 90, 105)
    draw.text((80, 45), title, font=title_font, fill=dark)
    draw.text((82, 101), "Each panel is one ID; T01-T15 follow canonical technique order", font=small_font, fill=muted)
    panel_left, panel_top, panel_width, panel_height = 100, 185, 730, 1170
    for panel_index, id_level in enumerate(ID_ORDER):
        left = panel_left + panel_index * (panel_width + 55)
        right = left + panel_width
        top = panel_top
        bottom = top + panel_height
        draw.text((left, top - 48), id_level, font=axis_font, fill=dark)
        rows = [row for row in summaries if row["id_level"] == id_level]
        all_values = [metric_value(row, metric_key) for row in rows]
        if comparison is not None and comparison_key is not None:
            all_values.extend(metric_value(row, comparison_key) for row in comparison if row["id_level"] == id_level)
        values = [value for value in all_values if value is not None]
        max_value = max(values) * 1.2 if values and max(values) > 0 else 1.0
        min_value = 0.0

        def x_pos(index: int) -> float:
            return left + 60 + index * ((right - left - 100) / max(1, len(CANONICAL_TECHNIQUE_ORDER) - 1))

        def y_pos(value: float) -> float:
            return bottom - (value - min_value) / (max_value - min_value) * (bottom - top)

        for tick_index in range(6):
            value = max_value * tick_index / 5
            y = y_pos(value)
            draw.line([(left + 55, y), (right, y)], fill=(226, 230, 236), width=2)
            draw.text((left + 4, y - 10), f"{value:.2f}", font=small_font, fill=muted)
        draw.line([(left + 55, top), (left + 55, bottom)], fill=(75, 85, 100), width=3)
        draw.line([(left + 55, bottom), (right, bottom)], fill=(75, 85, 100), width=3)

        points: list[tuple[float, float]] = []
        for index, technique in enumerate(CANONICAL_TECHNIQUE_ORDER):
            row = next(row for row in rows if row["technique"] == technique)
            value = metric_value(row, metric_key)
            if value is None:
                continue
            point = (x_pos(index), y_pos(value))
            if points:
                draw.line([points[-1], point], fill=hex_rgb(PALETTE[0]), width=4)
            points.append(point)
            draw.ellipse((point[0] - 7, point[1] - 7, point[0] + 7, point[1] + 7), fill=hex_rgb(PALETTE[0]))
            if error_key:
                error = metric_value(row, error_key)
                if error is not None:
                    upper = y_pos(min(max_value, value + error))
                    lower = y_pos(max(0, value - error))
                    draw.line([(point[0], upper), (point[0], lower)], fill=(36, 48, 65), width=2)
        if comparison is not None and comparison_key is not None:
            comparison_points: list[tuple[float, float]] = []
            for index, technique in enumerate(CANONICAL_TECHNIQUE_ORDER):
                row = next(row for row in comparison if row["technique"] == technique and row["id_level"] == id_level)
                value = metric_value(row, comparison_key)
                if value is None:
                    continue
                point = (x_pos(index), y_pos(value))
                if comparison_points:
                    draw.line([comparison_points[-1], point], fill=hex_rgb(PALETTE[2]), width=4)
                comparison_points.append(point)
                draw.ellipse((point[0] - 7, point[1] - 7, point[0] + 7, point[1] + 7), fill=hex_rgb(PALETTE[2]))
        for index, technique in enumerate(CANONICAL_TECHNIQUE_ORDER):
            draw_text_centered(draw, (x_pos(index), bottom + 27), TECHNIQUE_SHORT[technique], small_font, muted)
    draw_text_centered(draw, (width / 2, height - 75), "Technique order", axis_font, dark)
    draw_text_centered(draw, (38, height / 2), y_label, axis_font, dark)
    draw.rectangle((100, height - 143, 126, height - 117), fill=hex_rgb(PALETTE[0]))
    draw.text((138, height - 148), "Cancel", font=small_font, fill=muted)
    if comparison is not None:
        draw.rectangle((310, height - 143, 336, height - 117), fill=hex_rgb(PALETTE[2]))
        draw.text((348, height - 148), "Trigger", font=small_font, fill=muted)
    image.save(output, format="PNG", optimize=True)


def draw_task_panels(output: Path, summaries: Sequence[dict[str, Any]]) -> None:
    width, height = 2550, 1650
    image = Image.new("RGB", (width, height), (249, 250, 252))
    draw = ImageDraw.Draw(image)
    title_font = load_font(42, bold=True)
    axis_font = load_font(24)
    small_font = load_font(17)
    dark = (30, 41, 59)
    muted = (80, 90, 105)
    draw.text((80, 45), "Cancel Task Time and Movement Distance", font=title_font, fill=dark)
    draw.text((82, 101), "All non-start events; target-only and mine-only values are retained in the CSV", font=small_font, fill=muted)
    panels = [
        ("task_completion_time_all_s", "Task time (s)"),
        ("movement_distance_all_m", "Movement distance (m)"),
    ]
    panel_left, panel_top, panel_width, panel_height = 125, 195, 1100, 1170
    for panel_index, (key, y_label) in enumerate(panels):
        left = panel_left + panel_index * 1230
        right = left + panel_width
        top = panel_top
        bottom = top + panel_height
        values = [metric_value(row, key) for row in summaries]
        values = [value for value in values if value is not None]
        max_value = max(values) * 1.15 if values and max(values) > 0 else 1.0
        draw.text((left, top - 54), y_label, font=axis_font, fill=dark)
        for tick_index in range(6):
            value = max_value * tick_index / 5
            y = bottom - value / max_value * (bottom - top)
            draw.line([(left + 70, y), (right, y)], fill=(226, 230, 236), width=2)
            draw.text((left + 3, y - 10), f"{value:.2f}", font=small_font, fill=muted)
        draw.line([(left + 70, top), (left + 70, bottom)], fill=(75, 85, 100), width=3)
        draw.line([(left + 70, bottom), (right, bottom)], fill=(75, 85, 100), width=3)
        group_width = (right - left - 100) / len(CANONICAL_TECHNIQUE_ORDER)
        bar_width = group_width / 3 - 6
        for technique_index, technique in enumerate(CANONICAL_TECHNIQUE_ORDER):
            group_left = left + 85 + technique_index * group_width
            for id_index, id_level in enumerate(ID_ORDER):
                row = next(row for row in summaries if row["technique"] == technique and row["id_level"] == id_level)
                value = metric_value(row, key)
                if value is None:
                    continue
                x1 = group_left + id_index * (bar_width + 4)
                x2 = x1 + bar_width
                y = bottom - value / max_value * (bottom - top)
                draw.rectangle((x1, y, x2, bottom), fill=hex_rgb(PALETTE[id_index]))
            draw_text_centered(draw, (group_left + group_width / 2, bottom + 28), TECHNIQUE_SHORT[technique], small_font, muted)
    draw.text((120, height - 80), "ID colors: L-ID blue | M-ID orange | H-ID red", font=small_font, fill=muted)
    image.save(output, format="PNG", optimize=True)


def draw_reason_chart(
    output: Path,
    reason_rows: Sequence[dict[str, Any]],
    title: str,
    subtitle: str,
) -> None:
    counts = Counter()
    for row in reason_rows:
        counts[row["reason_category"]] += int(row["count"])
    top_reasons = [reason for reason, _ in counts.most_common(8)]
    width, height = 2200, 1100
    image = Image.new("RGB", (width, height), (249, 250, 252))
    draw = ImageDraw.Draw(image)
    title_font = load_font(40, bold=True)
    axis_font = load_font(22)
    small_font = load_font(18)
    dark = (30, 41, 59)
    muted = (80, 90, 105)
    draw.text((75, 45), title, font=title_font, fill=dark)
    draw.text((77, 95), subtitle, font=small_font, fill=muted)
    left, top, right, bottom = 280, 170, width - 80, height - 150
    max_count = max((counts[reason] for reason in top_reasons), default=1)
    for index, reason in enumerate(top_reasons):
        y = top + index * ((bottom - top) / max(1, len(top_reasons)))
        draw.text((80, y + 9), reason, font=axis_font, fill=muted)
        bar = (counts[reason] / max_count) * (right - left)
        draw.rounded_rectangle((left, y, left + bar, y + 42), radius=8, fill=hex_rgb(PALETTE[index % len(PALETTE)]))
        draw.text((left + bar + 12, y + 8), str(counts[reason]), font=axis_font, fill=dark)
    image.save(output, format="PNG", optimize=True)


def add_m3sd_flags(rows: list[dict[str, Any]]) -> None:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[(row["technique"], row["id_level"])].append(row)
        for field in (
            "outlier_3sd_cancel_time",
            "outlier_3sd_target_trigger_time",
            "outlier_3sd_used_time",
            "outlier_3sd_movement_distance",
        ):
            row[field] = False

    mapping = {
        "cancel_time_s": "outlier_3sd_cancel_time",
        "target_trigger_time_s": "outlier_3sd_target_trigger_time",
        "used_time_s": "outlier_3sd_used_time",
        "movement_distance_m": "outlier_3sd_movement_distance",
    }
    for group_rows in groups.values():
        for source_key, flag_key in mapping.items():
            values = [metric_value(row, source_key) for row in group_rows]
            values = [value for value in values if value is not None]
            if len(values) < 2:
                continue
            mean = statistics.mean(values)
            sd = statistics.stdev(values)
            if sd <= 0:
                continue
            lower, upper = mean - 3 * sd, mean + 3 * sd
            for row in group_rows:
                value = metric_value(row, source_key)
                row[flag_key] = value is not None and (value < lower or value > upper)


def build_summary(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(row["technique"], row["id_level"])].append(row)

    summaries: list[dict[str, Any]] = []
    for technique in CANONICAL_TECHNIQUE_ORDER:
        for id_level in ID_ORDER:
            condition_rows = grouped[(technique, id_level)]
            if len(condition_rows) != CASES_PER_ID_FORMAL:
                raise ValueError(
                    f"{technique} {id_level}: expected 15 formal events, found {len(condition_rows)}"
                )
            mine_rows = [row for row in condition_rows if row["is_mine_ball"] is True]
            target_rows = [row for row in condition_rows if row["is_mine_ball"] is False]
            successful = [row for row in mine_rows if row["successfully_canceled"] is True]
            failed = [row for row in mine_rows if row["successfully_canceled"] is False]
            unresolved = [row for row in mine_rows if row["successfully_canceled"] is None]
            cancel_values = [metric_value(row, "cancel_time_s") for row in mine_rows]
            cancel_values = [value for value in cancel_values if value is not None]
            successful_cancel_values = [metric_value(row, "cancel_time_s") for row in successful]
            successful_cancel_values = [value for value in successful_cancel_values if value is not None]
            target_trigger_values = [metric_value(row, "target_trigger_time_s") for row in target_rows]
            target_trigger_values = [value for value in target_trigger_values if value is not None]
            target_activation_valid_n = len(target_trigger_values)
            mine_success_ci = exact_binomial_interval(len(successful), len(mine_rows))
            mine_failure_ci = exact_binomial_interval(len(failed), len(mine_rows))

            def sum_metric(source_rows: Sequence[dict[str, Any]], key: str) -> float | None:
                values = [metric_value(row, key) for row in source_rows]
                values = [value for value in values if value is not None]
                return sum(values) if values else None

            def mean_metric(source_rows: Sequence[dict[str, Any]], key: str) -> float | None:
                values = [metric_value(row, key) for row in source_rows]
                values = [value for value in values if value is not None]
                return statistics.mean(values) if values else None

            all_time = [metric_value(row, "used_time_s") for row in condition_rows]
            all_time = [value for value in all_time if value is not None]
            all_distance = [metric_value(row, "movement_distance_m") for row in condition_rows]
            all_distance = [value for value in all_distance if value is not None]
            target_time = [metric_value(row, "used_time_s") for row in target_rows]
            target_time = [value for value in target_time if value is not None]
            mine_time = [metric_value(row, "used_time_s") for row in mine_rows]
            mine_time = [value for value in mine_time if value is not None]
            target_distance = [metric_value(row, "movement_distance_m") for row in target_rows]
            target_distance = [value for value in target_distance if value is not None]
            mine_distance = [metric_value(row, "movement_distance_m") for row in mine_rows]
            mine_distance = [value for value in mine_distance if value is not None]
            layout = condition_rows[0]

            summaries.append(
                {
                    "subject_id": SUBJECT_ID,
                    "technique": technique,
                    "technique_short": TECHNIQUE_SHORT[technique],
                    "id_level": id_level,
                    "id_bits": layout["id_bits"],
                    "layout_diameter_m": layout["layout_diameter_m"],
                    "trial_count": len(condition_rows),
                    "target_event_n": len(target_rows),
                    "mine_event_n": len(mine_rows),
                    "mine_cancel_success_n": len(successful),
                    "mine_cancel_failure_n": len(failed),
                    "mine_cancel_unresolved_n": len(unresolved),
                    "cancel_success_rate": len(successful) / len(mine_rows) if mine_rows else None,
                    "cancel_failure_rate": len(failed) / len(mine_rows) if mine_rows else None,
                    "cancel_unresolved_rate": len(unresolved) / len(mine_rows) if mine_rows else None,
                    "cancel_success_ci_lower": mine_success_ci[0],
                    "cancel_success_ci_upper": mine_success_ci[1],
                    "cancel_failure_ci_lower": mine_failure_ci[0],
                    "cancel_failure_ci_upper": mine_failure_ci[1],
                    "cancel_time_valid_n": len(cancel_values),
                    "cancel_time_mean_s": statistics.mean(cancel_values) if cancel_values else None,
                    "cancel_time_median_s": median_or_none(cancel_values),
                    "cancel_time_sd_s": sample_sd(cancel_values),
                    "cancel_time_iqr_s": iqr(cancel_values),
                    "cancel_time_min_s": min(cancel_values) if cancel_values else None,
                    "cancel_time_max_s": max(cancel_values) if cancel_values else None,
                    "successful_cancel_time_valid_n": len(successful_cancel_values),
                    "successful_cancel_time_mean_s": statistics.mean(successful_cancel_values) if successful_cancel_values else None,
                    "target_activation_valid_n": target_activation_valid_n,
                    "target_activation_rate": target_activation_valid_n / len(target_rows) if target_rows else None,
                    "target_trigger_time_mean_s": statistics.mean(target_trigger_values) if target_trigger_values else None,
                    "target_trigger_time_median_s": median_or_none(target_trigger_values),
                    "target_trigger_time_sd_s": sample_sd(target_trigger_values),
                    "target_trigger_time_iqr_s": iqr(target_trigger_values),
                    "target_trigger_time_min_s": min(target_trigger_values) if target_trigger_values else None,
                    "target_trigger_time_max_s": max(target_trigger_values) if target_trigger_values else None,
                    "reentry_total": sum(int(row["in_target_times"]) for row in condition_rows),
                    "reentry_mean": statistics.mean(int(row["in_target_times"]) for row in condition_rows),
                    "cancel_times_total": sum(int(row["cancel_times"]) for row in condition_rows),
                    "task_completion_time_all_s": sum(all_time) if all_time else None,
                    "task_completion_time_target_s": sum(target_time) if target_time else None,
                    "task_completion_time_mine_s": sum(mine_time) if mine_time else None,
                    "task_time_valid_n": len(all_time),
                    "movement_distance_all_m": sum(all_distance) if all_distance else None,
                    "movement_distance_target_m": sum(target_distance) if target_distance else None,
                    "movement_distance_mine_m": sum(mine_distance) if mine_distance else None,
                    "movement_distance_valid_n": len(all_distance),
                    "trajectory_missing_n": sum(row["movement_distance_m"] is None for row in condition_rows),
                    "cancel_time_outlier_n": sum(row["outlier_3sd_cancel_time"] for row in condition_rows),
                    "target_trigger_time_outlier_n": sum(row["outlier_3sd_target_trigger_time"] for row in condition_rows),
                    "used_time_outlier_n": sum(row["outlier_3sd_used_time"] for row in condition_rows),
                    "movement_distance_outlier_n": sum(row["outlier_3sd_movement_distance"] for row in condition_rows),
                }
            )
    return summaries


def build_reason_summary(
    rows: Sequence[dict[str, Any]],
    source_key: str,
    source_label: str,
) -> list[dict[str, Any]]:
    """Summarize one reason field only; never pool cancel and no-trigger reasons."""
    counts: Counter[tuple[str, str, str]] = Counter()
    for row in rows:
        value = row.get(source_key)
        if value:
            for category in normalize_reason(str(value)):
                counts[(row["technique"], row["id_level"], category)] += 1
    return [
        {
            "subject_id": SUBJECT_ID,
            "technique": key[0],
            "technique_short": TECHNIQUE_SHORT[key[0]],
            "id_level": key[1],
            "source_field": source_label,
            "reason_category": key[2],
            "count": value,
        }
        for key, value in sorted(counts.items())
    ]


def build_direction_summary(
    input_dir: Path,
    time_rows_by_run: dict[str, dict[int, dict[str, Any]]],
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for debug_path in sorted(input_dir.glob("*/*-direction-debug.csv")):
        run_id = debug_path.parent.name
        with debug_path.open("r", encoding="utf-8-sig", newline="") as handle:
            debug_rows = list(csv.DictReader(handle))
        if not debug_rows:
            continue
        mode = next(iter(time_rows_by_run[run_id].values()))["technique"]
        grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        for row in debug_rows:
            case = finite_int(row.get("case"))
            if case is None:
                continue
            source = time_rows_by_run[run_id].get(case)
            if source is None:
                continue
            if source["analysis_scope"] != "primary":
                continue
            grouped[(mode, source["id_level"])].append(row)
        for (technique, id_level), group_rows in sorted(grouped.items()):
            angles = [finite_float(row.get("angleDeg")) for row in group_rows]
            angles = [value for value in angles if value is not None]
            thresholds = [finite_float(row.get("angleThresholdDeg")) for row in group_rows]
            thresholds = [value for value in thresholds if value is not None]
            index_speeds = [finite_float(row.get("indexSpeed")) for row in group_rows]
            index_speeds = [value for value in index_speeds if value is not None]
            angle_pass = [parse_bool(row.get("anglePass")) for row in group_rows]
            angle_pass = [value for value in angle_pass if value is not None]
            speed_pass = [parse_bool(row.get("speedPass")) for row in group_rows]
            speed_pass = [value for value in speed_pass if value is not None]
            window_ready = [parse_bool(row.get("windowReady")) for row in group_rows]
            window_ready = [value for value in window_ready if value is not None]
            output.append(
                {
                    "subject_id": SUBJECT_ID,
                    "technique": technique,
                    "technique_short": TECHNIQUE_SHORT[technique],
                    "id_level": id_level,
                    "debug_rows": len(group_rows),
                    "angle_valid_n": len(angles),
                    "angle_mean_deg": statistics.mean(angles) if angles else None,
                    "angle_median_deg": median_or_none(angles),
                    "angle_threshold_mean_deg": statistics.mean(thresholds) if thresholds else None,
                    "index_speed_mean": statistics.mean(index_speeds) if index_speeds else None,
                    "angle_pass_rate": sum(angle_pass) / len(angle_pass) if angle_pass else None,
                    "speed_pass_rate": sum(speed_pass) / len(speed_pass) if speed_pass else None,
                    "window_ready_rate": sum(window_ready) / len(window_ready) if window_ready else None,
                    "cancel_already_triggered_n": sum(parse_bool(row.get("cancelAlreadyTriggered")) is True for row in group_rows),
                }
            )
    return output


def load_trigger_summary(path: Path) -> dict[tuple[str, str], dict[str, Any]]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    return {(row["technique"], row["id_level"]): row for row in rows}


def build_comparison(
    summaries: Sequence[dict[str, Any]],
    trigger: dict[tuple[str, str], dict[str, Any]],
) -> list[dict[str, Any]]:
    comparison: list[dict[str, Any]] = []
    for row in summaries:
        trigger_row = trigger.get((row["technique"], row["id_level"]), {})
        trigger_activation_rate = None
        trigger_trial_count = finite_int(trigger_row.get("trial_count"))
        trigger_valid_n = finite_int(trigger_row.get("trigger_time_valid_n"))
        if trigger_trial_count and trigger_valid_n is not None:
            trigger_activation_rate = trigger_valid_n / trigger_trial_count

        def delta(cancel_key: str, trigger_key: str) -> float | None:
            left = metric_value(row, cancel_key)
            right = finite_float(trigger_row.get(trigger_key))
            return left - right if left is not None and right is not None else None

        comparison.append(
            {
                "subject_id": SUBJECT_ID,
                "technique": row["technique"],
                "technique_short": row["technique_short"],
                "id_level": row["id_level"],
                "id_bits": row["id_bits"],
                "cancel_target_activation_rate": row["target_activation_rate"],
                "trigger_target_activation_rate": trigger_activation_rate,
                "delta_target_activation_rate": (
                    row["target_activation_rate"] - trigger_activation_rate
                    if row["target_activation_rate"] is not None and trigger_activation_rate is not None
                    else None
                ),
                "cancel_target_trigger_time_mean_s": row["target_trigger_time_mean_s"],
                "trigger_target_trigger_time_mean_s": finite_float(trigger_row.get("trigger_time_mean_s")),
                "delta_target_trigger_time_s": delta("target_trigger_time_mean_s", "trigger_time_mean_s"),
                "cancel_target_used_time_s": row["task_completion_time_target_s"],
                "trigger_task_completion_time_s": finite_float(trigger_row.get("task_completion_time_s")),
                "delta_target_used_time_s": delta("task_completion_time_target_s", "task_completion_time_s"),
                "cancel_target_movement_distance_m": row["movement_distance_target_m"],
                "trigger_movement_distance_m": finite_float(trigger_row.get("movement_distance_m")),
                "delta_target_movement_distance_m": delta("movement_distance_target_m", "movement_distance_m"),
                "cancel_all_used_time_s": row["task_completion_time_all_s"],
                "cancel_all_movement_distance_m": row["movement_distance_all_m"],
                "comparison_note": "Target-only values are the preferred exploratory match; all-event Cancel totals include mine/obstacle entries.",
            }
        )
    return comparison


def process_runs(
    input_dir: Path,
    subject_id: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[str], dict[str, dict[int, dict[str, Any]]]]:
    time_files = sorted(input_dir.glob("*/*-time.csv"))
    if not time_files:
        raise FileNotFoundError(f"No time CSV files under {input_dir}")

    primary_rows: list[dict[str, Any]] = []
    supplemental_rows: list[dict[str, Any]] = []
    start_audit: list[dict[str, Any]] = []
    run_qc: list[dict[str, Any]] = []
    qc_text: list[str] = [f"Subject folder ID: {subject_id}", f"Time files found: {len(time_files)}"]
    time_rows_by_run: dict[str, dict[int, dict[str, Any]]] = {}
    technique_order: list[str] = []

    for time_path in time_files:
        run_id = time_path.parent.name
        trajectory_path = time_path.with_name(time_path.name.replace("-time.csv", "-trajectory.csv"))
        if not trajectory_path.exists():
            raise FileNotFoundError(f"Missing trajectory file for {time_path}")
        header, raw_rows = read_time_rows(time_path)
        if not raw_rows:
            raise ValueError(f"No data rows in {time_path}")
        row_lengths = sorted({len(row) for row in raw_rows})
        technique_values = {row[TIME_INDEX["technique"]].strip() for row in raw_rows if len(row) > TIME_INDEX["technique"]}
        if len(technique_values) != 1:
            raise ValueError(f"{run_id}: multiple techniques {sorted(technique_values)}")
        technique = next(iter(technique_values))
        technique_order.append(technique)

        case_values = [finite_int(row[TIME_INDEX["case"]]) for row in raw_rows if len(row) > TIME_INDEX["case"]]
        case_sequence_ok = case_values == list(range(1, len(raw_rows) + 1))
        if not case_sequence_ok:
            qc_text.append(f"WARNING {run_id}: Case values are not sequential")

        distances, sample_counts, trajectory_cases = trajectory_distances(trajectory_path)
        time_cases = {case for case in case_values if case is not None}
        missing_trajectory_cases = sorted(time_cases - trajectory_cases)
        extra_trajectory_cases = sorted(trajectory_cases - time_cases)

        raw_by_case: dict[int, dict[str, Any]] = {}
        for row in raw_rows:
            case = finite_int(row[TIME_INDEX["case"]])
            if case is None:
                continue
            raw_id = finite_int(row[TIME_INDEX["logged_id_code"]])
            start_ball = finite_int(row[TIME_INDEX["start_ball"]])
            ball_index = finite_int(row[TIME_INDEX["ball_index"]])
            if raw_id is None or start_ball is None or ball_index is None:
                continue
            analysis_scope = "primary"
            if technique == SUPPLEMENTAL_TECHNIQUE and len(raw_rows) > 48 and case > SUPPLEMENTAL_PRIMARY_CASE_LIMIT:
                analysis_scope = "supplemental_extra_id2"
            is_start = ball_index == start_ball
            try:
                points = target_points(row)
                diameter_m = layout_diameter(points)
                id_level, id_bits = match_id(diameter_m)
                geometry_ok = True
            except ValueError as error:
                diameter_m = None
                id_level = RAW_ID_TO_LEVEL.get(raw_id, "Unknown")
                id_bits = None
                geometry_ok = False
                qc_text.append(f"WARNING {run_id} Case {case}: {error}")

            mine_value = parse_bool(row[TIME_INDEX["is_mine_ball"]])
            success_value = parse_bool(row[TIME_INDEX["successfully_canceled"]])
            record = {
                "subject_id": subject_id,
                "run_id": run_id,
                "technique": technique,
                "technique_short": TECHNIQUE_SHORT.get(technique, technique),
                "case": case,
                "logged_id_code": raw_id,
                "id_level": id_level,
                "id_bits": id_bits,
                "layout_diameter_m": diameter_m,
                "start_ball": start_ball,
                "ball_index": ball_index,
                "is_start_ball": is_start,
                "analysis_scope": analysis_scope,
                "trigger_condition": row[TIME_INDEX["trigger_condition"]].strip(),
                "in_target_times": finite_int(row[TIME_INDEX["in_target_times"]]),
                "used_time_s": parse_sentinel_float(row[TIME_INDEX["used_time_s"]]),
                "react_time_s": parse_sentinel_float(row[TIME_INDEX["react_time_s"]]),
                "react_frequency": finite_float(row[TIME_INDEX["react_frequency"]]),
                "obstacle_react_frequency": finite_float(row[TIME_INDEX["obstacle_react_frequency"]]),
                "trigger_time_s": parse_sentinel_float(row[TIME_INDEX["trigger_time_s"]]),
                "cancel_time_s": parse_sentinel_float(row[TIME_INDEX["cancel_time_s"]]),
                "is_mine_ball": mine_value,
                "successfully_canceled": success_value,
                "cancel_reason": row[TIME_INDEX["cancel_reason"]].strip() if len(row) > TIME_INDEX["cancel_reason"] else "",
                "no_trigger_reason": row[TIME_INDEX["no_trigger_reason"]].strip() if len(row) > TIME_INDEX["no_trigger_reason"] else "",
                "cancel_times": finite_int(row[TIME_INDEX["cancel_times"]]) or 0,
                "direction_angle_frame": row[TIME_INDEX["direction_angle_frame"]].strip() if len(row) > TIME_INDEX["direction_angle_frame"] else "",
                "direction_speed_min": finite_float(row[TIME_INDEX["direction_speed_min"]]) if len(row) > TIME_INDEX["direction_speed_min"] else None,
                "movement_distance_m": distances.get(case),
                "trajectory_sample_count": sample_counts.get(case, 0),
                "geometry_valid": geometry_ok,
                "raw_data_length": len(row),
                "raw_row_json": json_or_blank(row),
            }
            record["target_trigger_time_s"] = record["trigger_time_s"] if mine_value is False else None
            raw_by_case[case] = record
            time_rows_by_run.setdefault(run_id, {})[case] = record

            if is_start:
                start_audit.append(
                    {
                        **{key: value for key, value in record.items() if key != "raw_row_json"},
                        "audit_note": "Start-ball row retained for audit and excluded from primary condition summaries.",
                    }
                )

            if analysis_scope == "supplemental_extra_id2":
                supplemental_rows.append(record)

        # Build per-block primary formal rows. Grouping by (logged ID, start)
        # preserves the second ID=2 block in the anomalous run.
        blocks: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
        for record in raw_by_case.values():
            if record["analysis_scope"] == "primary":
                blocks[(record["logged_id_code"], record["start_ball"])].append(record)

        primary_formal_for_run: list[dict[str, Any]] = []
        excluded_start = 0
        duplicate_targets = 0
        block_notes: list[str] = []
        for (raw_id, start_ball), block in sorted(blocks.items()):
            block.sort(key=lambda item: item["case"])
            if len(block) != CASES_PER_ID_RAW:
                block_notes.append(f"ID{raw_id}/start{start_ball} rows={len(block)}")
            seen_targets: set[int] = set()
            position = 0
            for record in block:
                if record["is_start_ball"]:
                    excluded_start += 1
                    continue
                if record["ball_index"] in seen_targets:
                    duplicate_targets += 1
                    continue
                seen_targets.add(record["ball_index"])
                position += 1
                record["position_within_id"] = position
                primary_formal_for_run.append(record)
            if len(seen_targets) != CASES_PER_ID_FORMAL:
                block_notes.append(
                    f"ID{raw_id}/start{start_ball} unique_nonstart={len(seen_targets)}"
                )

        primary_rows.extend(primary_formal_for_run)
        direction_path = time_path.with_name(time_path.name.replace("-time.csv", "-direction-debug.csv"))
        direction_debug_rows = 0
        if direction_path.exists():
            with direction_path.open("r", encoding="utf-8-sig", newline="") as handle:
                direction_debug_rows = sum(1 for _ in handle) - 1

        id_counts = Counter(record["logged_id_code"] for record in raw_by_case.values())
        primary_id_counts = Counter(record["logged_id_code"] for record in primary_formal_for_run)
        status = "PASS"
        if len(primary_formal_for_run) != 45 or missing_trajectory_cases or block_notes or not case_sequence_ok:
            status = "CHECK"
        note_parts = []
        if technique == SUPPLEMENTAL_TECHNIQUE and len(raw_rows) > 48:
            note_parts.append(f"cases > {SUPPLEMENTAL_PRIMARY_CASE_LIMIT} retained as supplemental")
        if missing_trajectory_cases:
            note_parts.append(f"missing trajectory cases={missing_trajectory_cases}")
        if extra_trajectory_cases:
            note_parts.append(f"extra trajectory cases={extra_trajectory_cases}")
        if block_notes:
            note_parts.extend(block_notes)
        run_qc.append(
            {
                "subject_id": subject_id,
                "run_id": run_id,
                "technique": technique,
                "header_columns": len(header),
                "data_columns": ";".join(str(value) for value in row_lengths),
                "raw_rows": len(raw_rows),
                "raw_id1_rows": id_counts.get(1, 0),
                "raw_id2_rows": id_counts.get(2, 0),
                "raw_id3_rows": id_counts.get(3, 0),
                "primary_formal_rows": len(primary_formal_for_run),
                "primary_id1_rows": primary_id_counts.get(1, 0),
                "primary_id2_rows": primary_id_counts.get(2, 0),
                "primary_id3_rows": primary_id_counts.get(3, 0),
                "supplemental_raw_rows": sum(record["analysis_scope"] != "primary" for record in raw_by_case.values()),
                "excluded_start_rows": excluded_start,
                "duplicate_nonstart_targets": duplicate_targets,
                "case_sequence_ok": case_sequence_ok,
                "trajectory_rows": sum(sample_counts.values()),
                "trajectory_case_count": len(trajectory_cases),
                "missing_trajectory_case_count": len(missing_trajectory_cases),
                "extra_trajectory_case_count": len(extra_trajectory_cases),
                "direction_debug_rows": direction_debug_rows,
                "status": status,
                "notes": "; ".join(note_parts),
            }
        )
        supplemental_count = sum(
            record["analysis_scope"] != "primary" for record in raw_by_case.values()
        )
        qc_text.append(
            f"{run_id}: mode={technique}, raw_rows={len(raw_rows)}, primary_formal={len(primary_formal_for_run)}, "
            f"start_excluded={excluded_start}, supplemental={supplemental_count}, status={status}"
        )

    observed = set(technique_order)
    expected = set(CANONICAL_TECHNIQUE_ORDER)
    if len(technique_order) != len(observed) or observed != expected:
        missing = sorted(expected - observed)
        extra = sorted(observed - expected)
        raise ValueError(f"Technique set mismatch: missing={missing}, extra={extra}")
    if len(primary_rows) != EXPECTED_PRIMARY_ROWS:
        raise ValueError(f"Expected {EXPECTED_PRIMARY_ROWS} primary rows, found {len(primary_rows)}")

    qc_text.extend(
        [
            f"Unique techniques: {len(observed)}",
            f"Primary formal rows: {len(primary_rows)} (expected {EXPECTED_PRIMARY_ROWS})",
            f"Supplemental raw rows: {len(supplemental_rows)}",
            "ID mapping: raw 1/2/3 -> L-ID/M-ID/H-ID; geometry diameters 0.5/0.6/0.7 m.",
            "NA, blank, and -1 time values are treated as missing, never as zero.",
            "No raw outlier removal was applied; M +/- 3 SD flags are sensitivity annotations only.",
        ]
    )
    return primary_rows, supplemental_rows, start_audit, run_qc, qc_text, time_rows_by_run


def main() -> None:
    args = parse_args()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    primary_rows, supplemental_rows, start_audit, run_qc, qc_text, time_rows_by_run = process_runs(
        args.input_dir.resolve(), args.subject_id
    )
    add_m3sd_flags(primary_rows)
    summaries = build_summary(primary_rows)
    cancel_reasons = build_reason_summary(primary_rows, "cancel_reason", "cancel_reason")
    no_trigger_reasons = build_reason_summary(primary_rows, "no_trigger_reason", "no_trigger_reason")
    qc_text.extend(
        [
            f"Cancel-reason summary rows: {len(cancel_reasons)} (analyzed separately).",
            f"No-trigger-reason summary rows: {len(no_trigger_reasons)} (analyzed separately).",
        ]
    )
    direction_summary = build_direction_summary(args.input_dir.resolve(), time_rows_by_run)
    trigger_summary = load_trigger_summary(args.trigger_summary.resolve())
    comparison = build_comparison(summaries, trigger_summary)

    trial_fields = [
        "subject_id", "run_id", "technique", "technique_short", "case", "logged_id_code", "id_level", "id_bits",
        "layout_diameter_m", "start_ball", "ball_index", "is_start_ball", "analysis_scope", "position_within_id",
        "trigger_condition", "in_target_times", "used_time_s", "react_time_s", "react_frequency",
        "obstacle_react_frequency", "trigger_time_s", "target_trigger_time_s", "cancel_time_s", "is_mine_ball",
        "successfully_canceled", "cancel_reason", "no_trigger_reason", "cancel_times", "direction_angle_frame",
        "direction_speed_min", "movement_distance_m", "trajectory_sample_count", "geometry_valid", "raw_data_length",
        "outlier_3sd_cancel_time", "outlier_3sd_target_trigger_time", "outlier_3sd_used_time", "outlier_3sd_movement_distance",
    ]
    supplemental_fields = trial_fields + ["raw_row_json"]
    summary_fields = list(summaries[0].keys()) if summaries else []
    reason_fields = ["subject_id", "technique", "technique_short", "id_level", "source_field", "reason_category", "count"]
    direction_fields = list(direction_summary[0].keys()) if direction_summary else [
        "subject_id", "technique", "technique_short", "id_level", "debug_rows", "angle_valid_n", "angle_mean_deg",
        "angle_median_deg", "angle_threshold_mean_deg", "index_speed_mean", "angle_pass_rate", "speed_pass_rate",
        "window_ready_rate", "cancel_already_triggered_n",
    ]
    run_qc_fields = list(run_qc[0].keys()) if run_qc else []
    start_fields = [field for field in trial_fields if field != "position_within_id"] + ["audit_note"]
    comparison_fields = list(comparison[0].keys()) if comparison else []

    write_csv(output_dir / "cancel_trial_metrics.csv", primary_rows, trial_fields)
    write_csv(output_dir / "cancel_supplemental_raw_events.csv", supplemental_rows, supplemental_fields)
    write_csv(output_dir / "cancel_start_ball_audit.csv", start_audit, start_fields)
    write_csv(output_dir / "cancel_id_technique_metrics.csv", summaries, summary_fields)
    write_csv(output_dir / "cancel_reason_summary.csv", cancel_reasons, reason_fields)
    write_csv(output_dir / "no_trigger_reason_summary.csv", no_trigger_reasons, reason_fields)
    write_csv(output_dir / "cancel_direction_debug_summary.csv", direction_summary, direction_fields)
    write_csv(output_dir / "subject2_cancel_trigger_comparison.csv", comparison, comparison_fields)
    write_csv(output_dir / "run_qc.csv", run_qc, run_qc_fields)
    (output_dir / "quality_report.txt").write_text("\n".join(qc_text) + "\n", encoding="utf-8")

    draw_rate_heatmap(output_dir / "cancel_rates_by_id.png", summaries)
    draw_three_panel_line_chart(
        output_dir / "cancel_time_by_id.png",
        "Cancel Time by Technique × ID",
        summaries,
        "cancel_time_mean_s",
        "Cancel time (s)",
        error_key="cancel_time_sd_s",
    )
    draw_three_panel_line_chart(
        output_dir / "target_trigger_time_by_id.png",
        "Target Trigger Time by Technique × ID",
        summaries,
        "target_trigger_time_mean_s",
        "Target trigger time (s)",
        error_key="target_trigger_time_sd_s",
        comparison=comparison if trigger_summary else None,
        comparison_key="trigger_target_trigger_time_mean_s" if trigger_summary else None,
    )
    draw_task_panels(output_dir / "task_time_distance_by_id.png", summaries)
    # Re-render the primary condition figures with the same three-ID grouped
    # bar grammar, fixed technique colors, and legend used for Trigger.
    render_trigger_style_metric_charts(output_dir, summaries)
    for legacy_name in ("cancel_rates_by_id.png", "task_time_distance_by_id.png"):
        legacy_path = output_dir / legacy_name
        if legacy_path.exists():
            legacy_path.unlink()
    if trigger_summary:
        draw_three_panel_line_chart(
            output_dir / "trigger_comparison_by_id.png",
            "Cancel vs Trigger: Target Trigger Time",
            comparison,
            "cancel_target_trigger_time_mean_s",
            "Target trigger time (s)",
            comparison=comparison,
            comparison_key="trigger_target_trigger_time_mean_s",
        )
    else:
        (output_dir / "trigger_comparison_by_id.txt").write_text(
            "Trigger summary not found; comparison chart was not generated.\n", encoding="utf-8"
        )
    draw_reason_chart(
        output_dir / "cancel_reason_counts.png",
        cancel_reasons,
        "Cancel Reason Categories — Subject 2",
        "Cancel reasons only across primary events; detailed technique × ID counts are in cancel_reason_summary.csv",
    )
    draw_reason_chart(
        output_dir / "no_trigger_reason_counts.png",
        no_trigger_reasons,
        "No-trigger Reason Categories — Subject 2",
        "No-trigger reasons only across primary events; detailed technique × ID counts are in no_trigger_reason_summary.csv",
    )

    manifest = {
        "subject_id": args.subject_id,
        "input_dir": str(args.input_dir.resolve()),
        "output_dir": str(output_dir),
        "primary_rows": len(primary_rows),
        "supplemental_raw_rows": len(supplemental_rows),
        "summary_rows": len(summaries),
        "technique_count": len(set(row["technique"] for row in primary_rows)),
        "id_levels": ID_ORDER,
        "trigger_summary_used": bool(trigger_summary),
        "notes": [
            "Start-ball rows are excluded from primary condition metrics and retained in cancel_start_ball_audit.csv.",
            "dwellDirection cases 49-64 are supplemental raw events.",
            "No raw outlier removal; M +/- 3 SD flags are sensitivity annotations.",
            "cancel_reason and no_trigger_reason are analyzed in separate CSV summaries and charts.",
        ],
    }
    (output_dir / "analysis_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print(f"Input: {args.input_dir.resolve()}")
    print(f"Output: {output_dir}")
    print(f"Primary trial rows: {len(primary_rows)}")
    print(f"Supplemental raw rows: {len(supplemental_rows)}")
    print(f"Technique x ID summaries: {len(summaries)}")
    print(f"Trigger comparison rows: {len(comparison)}")
    print("Charts: Trigger-style condition bars, Trigger comparison, and separate cancel/no-trigger reason counts")


if __name__ == "__main__":
    main()
