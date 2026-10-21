#!/usr/bin/env python3
"""Analyze one subject's Trigger data by index of difficulty.

Outputs trial-level data, technique-by-ID summaries, a QC report, and
publication-ready PNG charts. Trigger trial failure is defined as
``in_target_times > 1``. The raw time CSV files have 70 header columns
but 76 data columns, so the stable first 25 columns are parsed by position.
"""

from __future__ import annotations

import argparse
import csv
import math
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Iterable, Sequence

from PIL import Image, ImageDraw, ImageFont


SUBJECT_ID = 2
CORE_COLUMN_COUNT = 25
EXPECTED_CASES = 45
CASES_PER_ID = 15

ID_BY_DIAMETER = {
    0.5: ("L-ID", 2.713),
    0.6: ("M-ID", 3.459),
    0.7: ("H-ID", 4.605),
}
ID_ORDER = ["L-ID", "M-ID", "H-ID"]

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
    "trigger_time_s": 17,
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


def parse_args() -> argparse.Namespace:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--subject-id",
        type=int,
        default=SUBJECT_ID,
        help="Subject identifier written to outputs and chart titles.",
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=root / "2" / "Trigger",
        help="Directory containing the selected subject's Trigger run folders.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=root / "analysis_outputs" / "subject2_trigger",
        help="Directory for CSV, QC, and PNG outputs.",
    )
    return parser.parse_args()


def finite_float(value: str) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def sample_sd(values: Sequence[float]) -> float:
    return statistics.stdev(values) if len(values) > 1 else 0.0


def round_value(value: float | None, digits: int = 6) -> float | str:
    return "" if value is None else round(value, digits)


def target_points(row: Sequence[str]) -> list[tuple[float, float, float]]:
    # Debug/cancellation fields before the target list vary by run. The
    # target layout is always the final 17 XYZ triples (51 values).
    values = [finite_float(value) for value in row[-51:]]
    if any(value is None for value in values) or len(values) % 3 != 0:
        raise ValueError(
            f"Malformed target coordinates: {len(values)} values after core fields"
        )
    return [
        (float(values[i]), float(values[i + 1]), float(values[i + 2]))
        for i in range(0, len(values), 3)
    ]


def layout_diameter(points: Sequence[tuple[float, float, float]]) -> float:
    return max(math.dist(first, second) for first in points for second in points)


def match_id(diameter_m: float, tolerance: float = 1e-4) -> tuple[str, float]:
    for expected, id_info in ID_BY_DIAMETER.items():
        if abs(diameter_m - expected) <= tolerance:
            return id_info
    raise ValueError(f"Unexpected target-layout diameter: {diameter_m:.6f} m")


def trajectory_distances(path: Path) -> tuple[dict[int, float], dict[int, int]]:
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
    return distances, counts


def read_time_rows(path: Path) -> tuple[list[str], list[list[str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.reader(handle))
    if not rows:
        raise ValueError(f"Empty time CSV: {path}")
    return rows[0], rows[1:]


def collect_trials(
    input_dir: Path, subject_id: int = SUBJECT_ID
) -> tuple[list[dict], list[str], list[str]]:
    time_files = sorted(input_dir.glob("*/*-time.csv"))
    if not time_files:
        raise FileNotFoundError(f"No *-time.csv files found under {input_dir}")

    trials: list[dict] = []
    qc: list[str] = []
    technique_order: list[str] = []
    logged_id_pairs: set[tuple[int, str]] = set()
    diameter_observations: dict[str, set[float]] = defaultdict(set)
    raw_internal_id_values: set[str] = set()
    raw_trigger_counts: dict[str, int] = defaultdict(int)

    qc.append(f"Subject folder ID: {subject_id}")
    qc.append(f"Time files found: {len(time_files)}")

    for time_path in time_files:
        run_id = time_path.parent.name
        trajectory_path = time_path.with_name(
            time_path.name.replace("-time.csv", "-trajectory.csv")
        )
        if not trajectory_path.exists():
            raise FileNotFoundError(f"Missing trajectory file for {time_path}")

        header, rows = read_time_rows(time_path)
        row_lengths = sorted({len(row) for row in rows})
        qc.append(
            f"{run_id}: header_columns={len(header)}, "
            f"data_columns={row_lengths}, rows={len(rows)}"
        )
        if min(row_lengths) < CORE_COLUMN_COUNT:
            raise ValueError(f"{run_id}: time row has fewer than 25 core fields")

        if len(header) > TIME_INDEX["logged_id_code"]:
            raw_internal_id_values.update(
                row[TIME_INDEX["logged_id_code"]].strip()
                for row in rows
                if len(row) > TIME_INDEX["logged_id_code"]
            )

        distances, sample_counts = trajectory_distances(trajectory_path)
        case_values = [int(row[TIME_INDEX["case"]]) for row in rows]
        if case_values != list(range(1, len(rows) + 1)):
            raise ValueError(f"{run_id}: Case values are not sequential from 1")

        technique_values = {row[TIME_INDEX["technique"]] for row in rows}
        if len(technique_values) != 1:
            raise ValueError(f"{run_id}: multiple techniques in one run")
        technique = next(iter(technique_values))
        technique_order.append(technique)
        raw_trigger_counts[technique] += len(rows)

        rows_by_logged_id: dict[int, list[list[str]]] = defaultdict(list)
        for row in rows:
            rows_by_logged_id[int(row[TIME_INDEX["logged_id_code"]])].append(row)
        if set(rows_by_logged_id) != {1, 2, 3}:
            raise ValueError(
                f"{run_id}: expected logged ID codes 1,2,3; "
                f"found {sorted(rows_by_logged_id)}"
            )

        selected_rows: list[tuple[list[str], int]] = []
        excluded_start = 0
        excluded_duplicate = 0
        for logged_id_code in (1, 2, 3):
            seen_targets: set[int] = set()
            position = 0
            for row in rows_by_logged_id[logged_id_code]:
                ball_index = int(row[TIME_INDEX["ball_index"]])
                start_ball = int(row[TIME_INDEX["start_ball"]])
                if ball_index == start_ball:
                    excluded_start += 1
                    continue
                if ball_index in seen_targets:
                    excluded_duplicate += 1
                    continue
                seen_targets.add(ball_index)
                position += 1
                selected_rows.append((row, position))
            if len(seen_targets) != CASES_PER_ID:
                raise ValueError(
                    f"{run_id} logged ID {logged_id_code}: expected 15 unique "
                    f"non-start targets, found {len(seen_targets)}"
                )
        qc.append(
            f"{run_id}: selected_formal_trials={len(selected_rows)}, "
            f"excluded_start_ball={excluded_start}, "
            f"excluded_duplicate_targets={excluded_duplicate}"
        )

        for row, position_within_id in selected_rows:
            case = int(row[TIME_INDEX["case"]])
            logged_id_code = int(row[TIME_INDEX["logged_id_code"]])
            points = target_points(row)
            if len(points) != 17:
                raise ValueError(
                    f"{run_id} Case {case}: expected 17 target points, "
                    f"found {len(points)}"
                )
            diameter_m = layout_diameter(points)
            id_level, id_bits = match_id(diameter_m)
            logged_id_pairs.add((logged_id_code, id_level))
            diameter_observations[id_level].add(round(diameter_m, 6))

            used_time = finite_float(row[TIME_INDEX["used_time_s"]])
            in_target_times = finite_float(row[TIME_INDEX["in_target_times"]])
            trigger_time_raw = finite_float(row[TIME_INDEX["trigger_time_s"]])
            trigger_time = (
                trigger_time_raw
                if trigger_time_raw is not None and trigger_time_raw >= 0
                else None
            )
            if used_time is None:
                raise ValueError(f"{run_id} Case {case}: invalid usedTime")
            if in_target_times is None or in_target_times < 0:
                raise ValueError(f"{run_id} Case {case}: invalid inTargetTimes")

            trials.append(
                {
                    "subject_id": subject_id,
                    "logged_id_code": logged_id_code,
                    "run_id": run_id,
                    "technique": technique,
                    "trigger_condition": row[
                        TIME_INDEX["trigger_condition"]
                    ].strip(),
                    "case": case,
                    "position_within_id": position_within_id,
                    "ball_index": int(row[TIME_INDEX["ball_index"]]),
                    "id_level": id_level,
                    "id_bits": id_bits,
                    "layout_diameter_m": diameter_m,
                    "in_target_times": int(in_target_times),
                    # A Trigger trial is failed when the target is entered
                    # more than once, per the study-specific rule.
                    "trigger_failed": int(in_target_times) > 1,
                    "used_time_s": used_time,
                    "trigger_time_s": trigger_time,
                    "movement_distance_m": distances.get(case),
                    "trajectory_sample_count": sample_counts.get(case, 0),
                }
            )

    if len(set(technique_order)) != len(technique_order):
        raise ValueError("Technique names are not unique across run folders")
    if set(technique_order) != set(CANONICAL_TECHNIQUE_ORDER):
        missing = sorted(set(CANONICAL_TECHNIQUE_ORDER) - set(technique_order))
        extra = sorted(set(technique_order) - set(CANONICAL_TECHNIQUE_ORDER))
        raise ValueError(f"Technique set mismatch; missing={missing}, extra={extra}")
    technique_order = list(CANONICAL_TECHNIQUE_ORDER)

    qc.append(f"Unique techniques: {len(technique_order)}")
    qc.append(f"Trial rows produced: {len(trials)}")
    qc.append(
        f"Participant ID source: folder/CLI value={subject_id}; raw CSV "
        f"'ID' values={sorted(raw_internal_id_values)} are logged ID conditions "
        "(so an internal ID=3 is not a participant-3 label)."
    )
    qc.append(
        "Raw Trigger records by technique: "
        + ", ".join(
            f"{technique}={raw_trigger_counts[technique]}"
            for technique in technique_order
        )
    )
    raw_counts = list(raw_trigger_counts.values())
    qc.append(
        "Raw Trigger record total: "
        f"{sum(raw_counts)}; per-technique range={min(raw_counts)}-"
        f"{max(raw_counts)} (nominal 48; formal target records exclude "
        "Starting Balls and duplicate targets)."
    )
    qc.append(
        "Logged ID code to geometry-derived ID mapping: "
        + ", ".join(
            f"{code}->{level}" for code, level in sorted(logged_id_pairs)
        )
    )
    for id_level in ID_ORDER:
        qc.append(
            f"{id_level} observed diameters (m): "
            f"{sorted(diameter_observations[id_level])}"
        )

    return trials, qc, technique_order


def summarize(
    trials: Sequence[dict],
    technique_order: Sequence[str],
    subject_id: int = SUBJECT_ID,
) -> list[dict]:
    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for trial in trials:
        grouped[(trial["technique"], trial["id_level"])].append(trial)

    summaries: list[dict] = []
    for technique in technique_order:
        for id_level in ID_ORDER:
            rows = grouped[(technique, id_level)]
            if len(rows) != CASES_PER_ID:
                raise ValueError(
                    f"{technique} {id_level}: expected 15 trials, found {len(rows)}"
                )
            if any(row["movement_distance_m"] is None for row in rows):
                missing = [
                    row["case"]
                    for row in rows
                    if row["movement_distance_m"] is None
                ]
                raise ValueError(
                    f"{technique} {id_level}: missing trajectories for Cases {missing}"
                )
            trigger_values = [
                row["trigger_time_s"]
                for row in rows
                if row["trigger_time_s"] is not None
            ]
            summaries.append(
                {
                    "subject_id": subject_id,
                    "technique": technique,
                    "id_level": id_level,
                    "id_bits": rows[0]["id_bits"],
                    "layout_diameter_m": rows[0]["layout_diameter_m"],
                    "trial_count": len(rows),
                    "trigger_failure_n": sum(
                        1 for row in rows if row["trigger_failed"]
                    ),
                    "trigger_success_n": sum(
                        1 for row in rows if not row["trigger_failed"]
                    ),
                    "trigger_failure_rate": sum(
                        1 for row in rows if row["trigger_failed"]
                    )
                    / len(rows),
                    "in_target_entries_total": sum(
                        row["in_target_times"] for row in rows
                    ),
                    "task_completion_time_s": sum(
                        row["used_time_s"] for row in rows
                    ),
                    "movement_distance_m": sum(
                        row["movement_distance_m"] for row in rows
                    ),
                    "trigger_time_valid_n": len(trigger_values),
                    "trigger_time_mean_s": (
                        statistics.mean(trigger_values) if trigger_values else None
                    ),
                    "trigger_time_median_s": (
                        statistics.median(trigger_values) if trigger_values else None
                    ),
                    "trigger_time_sd_s": (
                        sample_sd(trigger_values) if trigger_values else None
                    ),
                    "trigger_time_min_s": min(trigger_values)
                    if trigger_values
                    else None,
                    "trigger_time_max_s": max(trigger_values)
                    if trigger_values
                    else None,
                }
            )
    return summaries


def write_csv(path: Path, rows: Sequence[dict], fields: Sequence[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
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


def load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = [
        Path(r"C:\Windows\Fonts\arialbd.ttf" if bold else r"C:\Windows\Fonts\arial.ttf"),
        Path(
            r"C:\Windows\Fonts\msyhbd.ttc"
            if bold
            else r"C:\Windows\Fonts\msyh.ttc"
        ),
    ]
    for path in candidates:
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default(size=size)


def hex_color(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[index : index + 2], 16) for index in (0, 2, 4))


def text_centered(
    draw: ImageDraw.ImageDraw,
    xy: tuple[float, float],
    text: str,
    font: ImageFont.ImageFont,
    fill: tuple[int, int, int],
) -> None:
    box = draw.textbbox((0, 0), text, font=font)
    width = box[2] - box[0]
    height = box[3] - box[1]
    draw.text((xy[0] - width / 2, xy[1] - height / 2), text, font=font, fill=fill)


def resolve_label_positions(
    desired: Sequence[tuple[float, str, tuple[int, int, int]]],
    top: float,
    bottom: float,
    spacing: float,
) -> list[tuple[float, str, tuple[int, int, int]]]:
    ordered = sorted(desired, key=lambda item: item[0])
    positions: list[list] = []
    for value, label, color in ordered:
        placed = max(value, top if not positions else positions[-1][0] + spacing)
        positions.append([placed, label, color])
    if positions and positions[-1][0] > bottom:
        positions[-1][0] = bottom
        for index in range(len(positions) - 2, -1, -1):
            positions[index][0] = min(
                positions[index][0], positions[index + 1][0] - spacing
            )
    if positions and positions[0][0] < top:
        shift = top - positions[0][0]
        for item in positions:
            item[0] += shift
    return [(float(y), label, color) for y, label, color in positions]


def draw_panel(
    draw: ImageDraw.ImageDraw,
    bounds: tuple[int, int, int, int],
    summaries: Sequence[dict],
    technique_order: Sequence[str],
    metric: str,
    title: str,
    unit: str,
    show_error: bool,
    large: bool = False,
) -> None:
    left, top, right, bottom = bounds
    scale = 1.35 if large else 1.0
    title_font = load_font(int(34 * scale), bold=True)
    axis_font = load_font(int(23 * scale))
    tick_font = load_font(int(20 * scale))
    label_font = load_font(int(18 * scale))

    chart_left = left + int(110 * scale)
    chart_right = right - int(430 * scale)
    chart_top = top + int(100 * scale)
    chart_bottom = bottom - int(125 * scale)
    label_x = chart_right + int(65 * scale)

    values = [
        float(row[metric])
        for row in summaries
        if row.get(metric) is not None
    ]
    error_values = []
    if show_error:
        for row in summaries:
            mean = row.get(metric)
            sd = row.get("trigger_time_sd_s")
            if mean is not None and sd is not None:
                error_values.append(float(mean) + float(sd))
    maximum = max(values + error_values) if error_values else max(values)
    # Failure rate is a proportion; keep the visual scale interpretable as
    # 0–100% even when the observed maximum is below 100%.
    is_failure_rate = "failure_rate" in metric
    y_max = 1.0 if is_failure_rate else (maximum * 1.12 if maximum > 0 else 1.0)

    x_values = [2.713, 3.459, 4.605]
    x_min, x_max = min(x_values), max(x_values)

    def x_pos(value: float) -> float:
        return chart_left + (value - x_min) / (x_max - x_min) * (
            chart_right - chart_left
        )

    def y_pos(value: float) -> float:
        return chart_bottom - value / y_max * (chart_bottom - chart_top)

    draw.text((left + 10, top + 10), title, font=title_font, fill=(30, 41, 59))

    for index in range(6):
        value = y_max * index / 5
        y = y_pos(value)
        draw.line(
            [(chart_left, y), (chart_right, y)],
            fill=(222, 227, 234),
            width=max(1, int(2 * scale)),
        )
        if metric == "in_target_entries_total":
            label = f"{value:.0f}"
        elif is_failure_rate:
            label = f"{value:.0%}"
        else:
            label = f"{value:.2f}" if y_max < 10 else f"{value:.1f}"
        box = draw.textbbox((0, 0), label, font=tick_font)
        draw.text(
            (chart_left - (box[2] - box[0]) - 16, y - (box[3] - box[1]) / 2),
            label,
            font=tick_font,
            fill=(80, 90, 105),
        )

    draw.line(
        [(chart_left, chart_top), (chart_left, chart_bottom)],
        fill=(75, 85, 100),
        width=max(2, int(3 * scale)),
    )
    draw.line(
        [(chart_left, chart_bottom), (chart_right, chart_bottom)],
        fill=(75, 85, 100),
        width=max(2, int(3 * scale)),
    )

    id_labels = {
        2.713: "L-ID\n2.713",
        3.459: "M-ID\n3.459",
        4.605: "H-ID\n4.605",
    }
    for value in x_values:
        x = x_pos(value)
        draw.line(
            [(x, chart_bottom), (x, chart_bottom + 10)],
            fill=(75, 85, 100),
            width=max(2, int(3 * scale)),
        )
        lines = id_labels[value].splitlines()
        text_centered(
            draw,
            (x, chart_bottom + int(30 * scale)),
            lines[0],
            tick_font,
            (55, 65, 80),
        )
        text_centered(
            draw,
            (x, chart_bottom + int(60 * scale)),
            lines[1],
            tick_font,
            (80, 90, 105),
        )

    text_centered(
        draw,
        ((chart_left + chart_right) / 2, bottom - int(23 * scale)),
        "Index of Difficulty (bits)",
        axis_font,
        (45, 55, 70),
    )
    text_centered(
        draw,
        (left + int(24 * scale), (chart_top + chart_bottom) / 2),
        unit,
        axis_font,
        (45, 55, 70),
    )

    by_key = {
        (row["technique"], row["id_level"]): row for row in summaries
    }
    endpoint_labels = []
    endpoints = {}

    for technique_index, technique in enumerate(technique_order):
        color = hex_color(PALETTE[technique_index % len(PALETTE)])
        series = [by_key[(technique, id_level)] for id_level in ID_ORDER]
        points = [
            (x_pos(float(row["id_bits"])), y_pos(float(row[metric])))
            for row in series
        ]
        draw.line(points, fill=color, width=max(2, int(4 * scale)))

        for point, row in zip(points, series):
            x, y = point
            if show_error:
                sd = row.get("trigger_time_sd_s")
                if sd is not None:
                    mean = float(row[metric])
                    upper = y_pos(min(y_max, mean + float(sd)))
                    lower = y_pos(max(0, mean - float(sd)))
                    draw.line(
                        [(x, upper), (x, lower)],
                        fill=color,
                        width=max(1, int(2 * scale)),
                    )
                    cap = int(7 * scale)
                    draw.line(
                        [(x - cap, upper), (x + cap, upper)],
                        fill=color,
                        width=max(1, int(2 * scale)),
                    )
                    draw.line(
                        [(x - cap, lower), (x + cap, lower)],
                        fill=color,
                        width=max(1, int(2 * scale)),
                    )
            radius = int(6 * scale)
            draw.ellipse(
                (x - radius, y - radius, x + radius, y + radius),
                fill=color,
                outline=(255, 255, 255),
                width=max(1, int(2 * scale)),
            )

        endpoint_labels.append((points[-1][1], technique, color))
        endpoints[technique] = points[-1]

    spacing = int(25 * scale)
    resolved = resolve_label_positions(
        endpoint_labels, chart_top, chart_bottom, spacing
    )
    for label_y, technique, color in resolved:
        endpoint_x, endpoint_y = endpoints[technique]
        draw.line(
            [(endpoint_x + int(8 * scale), endpoint_y), (label_x - 8, label_y)],
            fill=color,
            width=max(1, int(2 * scale)),
        )
        draw.text(
            (label_x, label_y - int(10 * scale)),
            technique,
            font=label_font,
            fill=color,
        )


def draw_technique_legend(
    draw: ImageDraw.ImageDraw,
    origin: tuple[int, int],
    technique_order: Sequence[str],
    columns: int,
    column_width: int,
    row_height: int,
    font_size: int,
) -> None:
    font = load_font(font_size)
    x0, y0 = origin
    rows_per_column = math.ceil(len(technique_order) / columns)
    for index, technique in enumerate(technique_order):
        column = index // rows_per_column
        row = index % rows_per_column
        x = x0 + column * column_width
        y = y0 + row * row_height
        color = hex_color(PALETTE[index % len(PALETTE)])
        draw.rounded_rectangle(
            (x, y + 3, x + 22, y + 25),
            radius=4,
            fill=color,
        )
        draw.text(
            (x + 32, y),
            f"{index + 1:02d}  {technique}",
            font=font,
            fill=(45, 55, 70),
        )


def draw_bar_panel(
    draw: ImageDraw.ImageDraw,
    bounds: tuple[int, int, int, int],
    summaries: Sequence[dict],
    technique_order: Sequence[str],
    metric: str,
    title: str,
    unit: str,
    error_key: str | None,
    show_legend: bool,
    large: bool = False,
) -> None:
    left, top, right, bottom = bounds
    scale = 1.15 if large else 1.0
    title_font = load_font(int(34 * scale), bold=True)
    axis_font = load_font(int(22 * scale))
    tick_font = load_font(int(18 * scale))
    number_font = load_font(int(12 * scale), bold=True)
    id_font = load_font(int(22 * scale), bold=True)

    chart_left = left + int(105 * scale)
    legend_space = int(500 * scale) if show_legend else int(25 * scale)
    chart_right = right - legend_space
    chart_top = top + int(95 * scale)
    chart_bottom = bottom - int(145 * scale)

    values = [
        float(row[metric])
        for row in summaries
        if row.get(metric) is not None
    ]
    error_values = []
    if error_key:
        for row in summaries:
            mean = row.get(metric)
            sd = row.get(error_key)
            if mean is not None and sd is not None:
                error_values.append(float(mean) + float(sd))
    maximum = max(values + error_values) if error_values else max(values)
    # Failure rate is a proportion; keep the visual scale interpretable as
    # 0–100% even when the observed maximum is below 100%.
    is_failure_rate = "failure_rate" in metric
    y_max = 1.0 if is_failure_rate else (maximum * 1.12 if maximum > 0 else 1.0)

    def y_pos(value: float) -> float:
        return chart_bottom - value / y_max * (chart_bottom - chart_top)

    draw.text((left + 10, top + 5), title, font=title_font, fill=(30, 41, 59))

    for index in range(6):
        value = y_max * index / 5
        y = y_pos(value)
        draw.line(
            [(chart_left, y), (chart_right, y)],
            fill=(222, 227, 234),
            width=max(1, int(2 * scale)),
        )
        if metric == "in_target_entries_total":
            label = f"{value:.0f}"
        elif is_failure_rate:
            label = f"{value:.0%}"
        else:
            label = f"{value:.2f}" if y_max < 10 else f"{value:.1f}"
        box = draw.textbbox((0, 0), label, font=tick_font)
        draw.text(
            (chart_left - (box[2] - box[0]) - 14, y - (box[3] - box[1]) / 2),
            label,
            font=tick_font,
            fill=(80, 90, 105),
        )

    draw.line(
        [(chart_left, chart_top), (chart_left, chart_bottom)],
        fill=(75, 85, 100),
        width=max(2, int(3 * scale)),
    )
    draw.line(
        [(chart_left, chart_bottom), (chart_right, chart_bottom)],
        fill=(75, 85, 100),
        width=max(2, int(3 * scale)),
    )

    by_key = {
        (row["technique"], row["id_level"]): row for row in summaries
    }
    plot_width = chart_right - chart_left
    outer_gap = int(18 * scale)
    group_gap = int(28 * scale)
    group_width = (plot_width - 2 * outer_gap - 2 * group_gap) / 3
    bar_gap = max(1.0, 2.0 * scale)
    bar_width = (group_width - bar_gap * (len(technique_order) - 1)) / len(
        technique_order
    )

    for id_index, id_level in enumerate(ID_ORDER):
        group_left = chart_left + outer_gap + id_index * (group_width + group_gap)
        group_right = group_left + group_width
        if id_index % 2 == 0:
            draw.rectangle(
                (group_left - 5, chart_top, group_right + 5, chart_bottom),
                fill=(244, 246, 249),
            )
            for grid_index in range(6):
                y = y_pos(y_max * grid_index / 5)
                draw.line(
                    [(group_left - 5, y), (group_right + 5, y)],
                    fill=(222, 227, 234),
                    width=max(1, int(2 * scale)),
                )

        for technique_index, technique in enumerate(technique_order):
            row = by_key[(technique, id_level)]
            value = float(row[metric])
            color = hex_color(PALETTE[technique_index % len(PALETTE)])
            x1 = group_left + technique_index * (bar_width + bar_gap)
            x2 = x1 + bar_width
            y = y_pos(value)
            draw.rectangle(
                (x1, y, x2, chart_bottom),
                fill=color,
                outline=(255, 255, 255),
                width=max(1, int(scale)),
            )

            if error_key:
                sd = row.get(error_key)
                if sd is not None:
                    upper = y_pos(min(y_max, value + float(sd)))
                    lower = y_pos(max(0, value - float(sd)))
                    center = (x1 + x2) / 2
                    cap = max(2, bar_width * 0.35)
                    draw.line(
                        [(center, upper), (center, lower)],
                        fill=(48, 58, 72),
                        width=max(1, int(2 * scale)),
                    )
                    draw.line(
                        [(center - cap, upper), (center + cap, upper)],
                        fill=(48, 58, 72),
                        width=max(1, int(2 * scale)),
                    )
                    draw.line(
                        [(center - cap, lower), (center + cap, lower)],
                        fill=(48, 58, 72),
                        width=max(1, int(2 * scale)),
                    )

            text_centered(
                draw,
                ((x1 + x2) / 2, chart_bottom + int(14 * scale)),
                f"{technique_index + 1}",
                number_font,
                (68, 78, 92),
            )

        id_bits = by_key[(technique_order[0], id_level)]["id_bits"]
        text_centered(
            draw,
            ((group_left + group_right) / 2, chart_bottom + int(48 * scale)),
            f"{id_level}  ({float(id_bits):.3f} bits)",
            id_font,
            (45, 55, 70),
        )
        if id_index < 2:
            separator = group_right + group_gap / 2
            draw.line(
                [(separator, chart_top), (separator, chart_bottom + 5)],
                fill=(195, 202, 212),
                width=max(1, int(2 * scale)),
            )

    text_centered(
        draw,
        ((chart_left + chart_right) / 2, bottom - int(30 * scale)),
        "Index of Difficulty — technique order 01 to 15 within each ID",
        axis_font,
        (45, 55, 70),
    )
    text_centered(
        draw,
        (left + int(24 * scale), (chart_top + chart_bottom) / 2),
        unit,
        axis_font,
        (45, 55, 70),
    )

    if show_legend:
        draw_technique_legend(
            draw,
            (chart_right + int(48 * scale), chart_top),
            technique_order,
            columns=1,
            column_width=0,
            row_height=int(47 * scale),
            font_size=int(18 * scale),
        )


def render_charts(
    output_dir: Path,
    summaries: Sequence[dict],
    technique_order: Sequence[str],
    subject_label: str = "Subject 2",
    composite_filename: str = "subject2_metrics_by_id.png",
    error_keys: dict[str, str] | None = None,
) -> None:
    if error_keys is None:
        error_keys = {"trigger_time_mean_s": "trigger_time_sd_s"}
    metrics = [
        (
            "task_completion_time_s",
            "Task Completion Time",
            "Time (s)",
            "task_completion_time_by_id.png",
        ),
        (
            "movement_distance_m",
            "Movement Distance",
            "Distance (m)",
            "movement_distance_by_id.png",
        ),
        (
            "trigger_time_mean_s",
            "Mean Trigger Time",
            "Trigger time (s)",
            "trigger_time_by_id.png",
        ),
        (
            "trigger_failure_rate",
            "Trigger Trial Failure Rate (in_target_times > 1)",
            "Failure rate",
            "trigger_failure_rate_by_id.png",
        ),
        (
            "in_target_entries_total",
            "Number of Target Entries",
            "Entries (count)",
            "target_entries_by_id.png",
        ),
    ]

    for metric, title, unit, filename in metrics:
        image = Image.new("RGB", (2400, 1600), (249, 250, 252))
        draw = ImageDraw.Draw(image)
        draw_bar_panel(
            draw,
            (90, 70, 2310, 1510),
            summaries,
            technique_order,
            metric,
            f"{title} — {subject_label}",
            unit,
            error_keys.get(metric),
            show_legend=True,
            large=True,
        )
        image.save(output_dir / filename, format="PNG", optimize=True)

    panel_width = 2200
    panel_height = 1310
    panel_rows = math.ceil(len(metrics) / 2)
    legend_top = 175 + panel_rows * panel_height + 55
    combined_height = legend_top + 3 * 105 + 160
    combined = Image.new("RGB", (4500, combined_height), (249, 250, 252))
    draw = ImageDraw.Draw(combined)
    title_font = load_font(50, bold=True)
    subtitle_font = load_font(26)
    draw.text(
        (110, 55),
        f"{subject_label} Trigger Performance by Index of Difficulty",
        font=title_font,
        fill=(23, 34, 52),
    )
    draw.text(
        (112, 120),
        "Within each ID, bars follow the same technique order (01-15); lower values are better.",
        font=subtitle_font,
        fill=(82, 92, 108),
    )
    for index, (metric, title, unit, _) in enumerate(metrics):
        column = index % 2
        row = index // 2
        draw_bar_panel(
            draw,
            (
                40 + column * panel_width,
                175 + row * panel_height,
                40 + (column + 1) * panel_width - 20,
                175 + (row + 1) * panel_height - 20,
            ),
            summaries,
            technique_order,
            metric,
            title,
            unit,
            error_keys.get(metric),
            show_legend=False,
            large=False,
        )
    draw_technique_legend(
        draw,
        (160, legend_top),
        technique_order,
        columns=5,
        column_width=850,
        row_height=105,
        font_size=24,
    )
    combined.save(
        output_dir / composite_filename, format="PNG", optimize=True
    )


def build_qc(
    base_qc: Sequence[str],
    trials: Sequence[dict],
    summaries: Sequence[dict],
    technique_order: Sequence[str],
) -> list[str]:
    qc = list(base_qc)
    qc.append("")
    qc.append("Validation")
    qc.append(f"Expected trial rows: 15 x 3 x 15 = 675; actual={len(trials)}")
    qc.append(
        f"Expected technique-by-ID rows: 15 x 3 = 45; actual={len(summaries)}"
    )
    missing_trajectories = sum(
        trial["movement_distance_m"] is None for trial in trials
    )
    invalid_trigger_times = sum(
        trial["trigger_time_s"] is None for trial in trials
    )
    entry_totals = [row["in_target_entries_total"] for row in summaries]
    qc.append(f"Missing trial trajectories: {missing_trajectories}")
    qc.append(f"Invalid/negative Trigger Time values excluded: {invalid_trigger_times}")
    qc.append(
        "Target-entry totals per technique x ID: "
        f"min={min(entry_totals)}, max={max(entry_totals)}"
    )
    failure_n = sum(1 for trial in trials if trial.get("trigger_failed"))
    failure_rate = failure_n / len(trials) if trials else None
    qc.append(
        "Trigger trial failure rule: in_target_times > 1 means the trial is failed; "
        "in_target_times <= 1 means successful."
    )
    qc.append(
        f"Trigger trial failures: {failure_n}/{len(trials)} "
        f"({failure_rate:.1%} overall)"
        if failure_rate is not None
        else "Trigger trial failures: no trials"
    )
    for id_level in ID_ORDER:
        id_trials = [trial for trial in trials if trial["id_level"] == id_level]
        id_failure_n = sum(1 for trial in id_trials if trial.get("trigger_failed"))
        id_rate = id_failure_n / len(id_trials) if id_trials else None
        qc.append(
            f"{id_level} Trigger trial failures: {id_failure_n}/{len(id_trials)} "
            f"({id_rate:.1%})"
            if id_rate is not None
            else f"{id_level} Trigger trial failures: no trials"
        )
    qc.append(
        "ID plotting order: L-ID (2.713), M-ID (3.459), H-ID (4.605)"
    )
    qc.append("")
    qc.append("Technique acquisition order")
    qc.extend(f"{index + 1:02d}. {name}" for index, name in enumerate(technique_order))
    qc.append("")
    qc.append("No outlier removal was applied.")
    qc.append("Task Error Rate and Throughput were not calculated.")
    return qc


def main() -> None:
    args = parse_args()
    input_dir = args.input_dir.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    trials, base_qc, technique_order = collect_trials(input_dir, args.subject_id)
    summaries = summarize(trials, technique_order, args.subject_id)

    trial_fields = [
        "subject_id",
        "logged_id_code",
        "run_id",
        "technique",
        "trigger_condition",
        "case",
        "position_within_id",
        "ball_index",
        "id_level",
        "id_bits",
        "layout_diameter_m",
        "in_target_times",
        "trigger_failed",
        "used_time_s",
        "trigger_time_s",
        "movement_distance_m",
        "trajectory_sample_count",
    ]
    summary_fields = [
        "subject_id",
        "technique",
        "id_level",
        "id_bits",
        "layout_diameter_m",
        "trial_count",
        "trigger_failure_n",
        "trigger_success_n",
        "trigger_failure_rate",
        "in_target_entries_total",
        "task_completion_time_s",
        "movement_distance_m",
        "trigger_time_valid_n",
        "trigger_time_mean_s",
        "trigger_time_median_s",
        "trigger_time_sd_s",
        "trigger_time_min_s",
        "trigger_time_max_s",
    ]
    write_csv(output_dir / "trial_metrics.csv", trials, trial_fields)
    write_csv(
        output_dir / "id_technique_metrics.csv", summaries, summary_fields
    )
    failure_fields = [
        "subject_id",
        "technique",
        "id_level",
        "id_bits",
        "layout_diameter_m",
        "trial_count",
        "trigger_failure_n",
        "trigger_success_n",
        "trigger_failure_rate",
    ]
    write_csv(
        output_dir / "trigger_failure_rate_by_id.csv",
        summaries,
        failure_fields,
    )
    render_charts(
        output_dir,
        summaries,
        technique_order,
        subject_label=f"Subject {args.subject_id}",
        composite_filename=f"subject{args.subject_id}_metrics_by_id.png",
    )

    qc = build_qc(base_qc, trials, summaries, technique_order)
    (output_dir / "quality_report.txt").write_text(
        "\n".join(qc) + "\n", encoding="utf-8"
    )

    print(f"Input: {input_dir}")
    print(f"Output: {output_dir}")
    print(f"Trials: {len(trials)}")
    print(f"Technique x ID rows: {len(summaries)}")
    print("Charts: 6 PNG files")


if __name__ == "__main__":
    main()
