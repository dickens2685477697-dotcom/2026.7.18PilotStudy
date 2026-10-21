#!/usr/bin/env python3
"""Combine Subjects 1 and 5 Trigger records using a 48-event scope.

Each technique contributes 16 logged events per ID (L/M/H), including the
Starting Ball.  A Trigger trial is marked failed when ``in_target_times > 1``.
The script keeps subject-level values and reports an equal-weight two-subject
mean plus between-subject SD.  Subject 5's dwell run contains one extra raw
duplicate after the planned 48-event sequence; it is audited and excluded
from the selected 48-event scope rather than silently changing the denominator.
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Sequence

import subject2_trigger_analysis as base


SUBJECT_IDS = (1, 5)
EVENTS_PER_ID = 16
IDS = (1, 2, 3)
ID_ORDER = ["L-ID", "M-ID", "H-ID"]
ID_BY_CODE = {1: "L-ID", 2: "M-ID", 3: "H-ID"}
EXPECTED_TECHNIQUES = 15
EXPECTED_SELECTED_ROWS_PER_SUBJECT = EXPECTED_TECHNIQUES * 3 * EVENTS_PER_ID


def parse_args() -> argparse.Namespace:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=root / "analysis_outputs" / "subjects1_5_trigger_48",
        help="Directory for combined CSV, PNG, and QC outputs.",
    )
    parser.add_argument(
        "--subject1-input",
        type=Path,
        default=root / "1" / "Trigger",
        help="Subject 1 Trigger directory.",
    )
    parser.add_argument(
        "--subject5-input",
        type=Path,
        default=root / "5" / "Trigger",
        help="Subject 5 Trigger directory.",
    )
    return parser.parse_args()


def parse_nonnegative(value: str) -> float | None:
    parsed = base.finite_float(value)
    if parsed is None or parsed < 0:
        return None
    return parsed


def record_from_row(
    row: list[str],
    subject_id: int,
    run_id: str,
    technique: str,
    distances: dict[int, float],
    sample_counts: dict[int, int],
) -> dict[str, Any]:
    case = int(row[base.TIME_INDEX["case"]])
    logged_id_code = int(row[base.TIME_INDEX["logged_id_code"]])
    start_ball = int(row[base.TIME_INDEX["start_ball"]])
    ball_index = int(row[base.TIME_INDEX["ball_index"]])
    in_target_times_value = base.finite_float(
        row[base.TIME_INDEX["in_target_times"]]
    )
    if in_target_times_value is None or in_target_times_value < 0:
        raise ValueError(f"{run_id} Case {case}: invalid inTargetTimes")
    in_target_times = int(in_target_times_value)

    points = base.target_points(row)
    diameter_m = base.layout_diameter(points)
    id_level, id_bits = base.match_id(diameter_m)
    expected_level = ID_BY_CODE.get(logged_id_code)
    if expected_level is not None and id_level != expected_level:
        raise ValueError(
            f"{run_id} Case {case}: logged ID{logged_id_code} maps to {id_level}, "
            f"but geometry maps to {expected_level}"
        )

    trigger_time = parse_nonnegative(row[base.TIME_INDEX["trigger_time_s"]])
    used_time = parse_nonnegative(row[base.TIME_INDEX["used_time_s"]])
    return {
        "subject_id": subject_id,
        "run_id": run_id,
        "technique": technique,
        "case": case,
        "logged_id_code": logged_id_code,
        "id_level": id_level,
        "id_bits": id_bits,
        "layout_diameter_m": diameter_m,
        "start_ball": start_ball,
        "ball_index": ball_index,
        "is_start_ball": ball_index == start_ball,
        "position_within_id": None,
        "in_target_times": in_target_times,
        "trigger_failed": in_target_times > 1,
        "used_time_s": used_time,
        "trigger_time_s": trigger_time,
        "movement_distance_m": distances.get(case),
        "trajectory_sample_count": sample_counts.get(case, 0),
        "analysis_scope": "raw_48_selected",
        "raw_data_length": len(row),
        "raw_row_json": json.dumps(row, ensure_ascii=False, separators=(",", ":")),
    }


def collect_subject(
    input_dir: Path, subject_id: int
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[str], list[str]]:
    time_files = sorted(input_dir.glob("*/*-time.csv"))
    if not time_files:
        raise FileNotFoundError(f"No *-time.csv files under {input_dir}")

    selected_rows: list[dict[str, Any]] = []
    extra_rows: list[dict[str, Any]] = []
    run_qc: list[dict[str, Any]] = []
    qc: list[str] = [
        f"Subject {subject_id} input: {input_dir}",
        f"Time files found: {len(time_files)}",
    ]
    techniques: list[str] = []

    for time_path in time_files:
        run_id = time_path.parent.name
        trajectory_path = time_path.with_name(
            time_path.name.replace("-time.csv", "-trajectory.csv")
        )
        if not trajectory_path.exists():
            raise FileNotFoundError(f"Missing trajectory file for {time_path}")
        header, raw_rows = base.read_time_rows(time_path)
        if not raw_rows:
            raise ValueError(f"No rows in {time_path}")
        techniques_in_file = {
            row[base.TIME_INDEX["technique"]].strip() for row in raw_rows
        }
        if len(techniques_in_file) != 1:
            raise ValueError(
                f"{run_id}: multiple techniques {sorted(techniques_in_file)}"
            )
        technique = next(iter(techniques_in_file))
        techniques.append(technique)

        case_values = [int(row[base.TIME_INDEX["case"]]) for row in raw_rows]
        if case_values != list(range(1, len(raw_rows) + 1)):
            raise ValueError(f"{run_id}: Case values are not sequential from 1")

        distances, sample_counts = base.trajectory_distances(trajectory_path)
        by_id: dict[int, list[list[str]]] = defaultdict(list)
        for row in raw_rows:
            by_id[int(row[base.TIME_INDEX["logged_id_code"]])].append(row)
        if set(by_id) != set(IDS):
            raise ValueError(
                f"{run_id}: expected logged ID codes {IDS}, found {sorted(by_id)}"
            )

        records_by_id: dict[int, list[dict[str, Any]]] = {}
        extra_rows_before_run = len(extra_rows)
        for logged_id_code in IDS:
            block_rows = sorted(by_id[logged_id_code], key=lambda row: int(row[0]))
            if len(block_rows) < EVENTS_PER_ID:
                raise ValueError(
                    f"{run_id} ID{logged_id_code}: expected at least {EVENTS_PER_ID} events, "
                    f"found {len(block_rows)}"
                )
            selected_block_rows = block_rows[:EVENTS_PER_ID]
            extras = block_rows[EVENTS_PER_ID:]
            selected_block = [
                record_from_row(
                    row,
                    subject_id,
                    run_id,
                    technique,
                    distances,
                    sample_counts,
                )
                for row in selected_block_rows
            ]
            for position, record in enumerate(selected_block, start=1):
                record["position_within_id"] = position
            records_by_id[logged_id_code] = selected_block

            seen_ball_indices: set[int] = set()
            duplicate_selected = 0
            for record in selected_block:
                if not record["is_start_ball"] and record["ball_index"] in seen_ball_indices:
                    duplicate_selected += 1
                seen_ball_indices.add(record["ball_index"])
            for extra_row in extras:
                extra_record = record_from_row(
                    extra_row,
                    subject_id,
                    run_id,
                    technique,
                    distances,
                    sample_counts,
                )
                extra_record["analysis_scope"] = "raw_extra_excluded"
                extra_record["extra_reason"] = (
                    "More than 16 raw events in this logged-ID block; "
                    "excluded after the planned 48-event sequence."
                )
                extra_rows.append(extra_record)

        selected_for_run = [
            record
            for logged_id_code in IDS
            for record in records_by_id[logged_id_code]
        ]
        selected_rows.extend(selected_for_run)
        extra_count_run = len(extra_rows) - extra_rows_before_run
        trajectory_cases = set(distances)
        time_cases = {int(row[base.TIME_INDEX["case"]]) for row in raw_rows}
        missing_trajectory_cases = sorted(time_cases - trajectory_cases)
        extra_trajectory_cases = sorted(trajectory_cases - time_cases)
        duplicate_nonstart_selected = sum(
            1
            for logged_id_code in IDS
            for record in records_by_id[logged_id_code]
            if not record["is_start_ball"]
        ) - sum(
            len(
                {
                    record["ball_index"]
                    for record in records_by_id[logged_id_code]
                    if not record["is_start_ball"]
                }
            )
            for logged_id_code in IDS
        )
        notes: list[str] = []
        if extra_count_run:
            notes.append(f"extra raw rows excluded={extra_count_run}")
        if duplicate_nonstart_selected:
            notes.append(
                f"duplicate non-start records inside selected 48={duplicate_nonstart_selected}"
            )
        if missing_trajectory_cases:
            notes.append(f"missing trajectory cases={missing_trajectory_cases}")
        if extra_trajectory_cases:
            notes.append(f"extra trajectory cases={extra_trajectory_cases}")
        status = "PASS" if not missing_trajectory_cases and not duplicate_nonstart_selected else "CHECK"

        raw_id_counts = Counter(
            int(row[base.TIME_INDEX["logged_id_code"]]) for row in raw_rows
        )
        run_qc.append(
            {
                "subject_id": subject_id,
                "run_id": run_id,
                "technique": technique,
                "header_columns": len(header),
                "data_columns": ";".join(
                    str(value) for value in sorted({len(row) for row in raw_rows})
                ),
                "raw_rows": len(raw_rows),
                "selected_48_rows": len(selected_for_run),
                "extra_raw_rows_excluded": extra_count_run,
                "raw_id1_rows": raw_id_counts.get(1, 0),
                "raw_id2_rows": raw_id_counts.get(2, 0),
                "raw_id3_rows": raw_id_counts.get(3, 0),
                "selected_id1_rows": len(records_by_id[1]),
                "selected_id2_rows": len(records_by_id[2]),
                "selected_id3_rows": len(records_by_id[3]),
                "starting_ball_rows_retained": sum(
                    record["is_start_ball"] for record in selected_for_run
                ),
                "duplicate_nonstart_selected": duplicate_nonstart_selected,
                "trajectory_case_count": len(trajectory_cases),
                "missing_trajectory_case_count": len(missing_trajectory_cases),
                "extra_trajectory_case_count": len(extra_trajectory_cases),
                "status": status,
                "notes": "; ".join(notes),
            }
        )
        qc.append(
            f"{run_id}: technique={technique}, raw_rows={len(raw_rows)}, "
            f"selected_48_rows={len(selected_for_run)}, "
            f"extra_excluded={extra_count_run}, status={status}"
        )

    expected = set(base.CANONICAL_TECHNIQUE_ORDER)
    observed = set(techniques)
    if len(techniques) != len(observed) or observed != expected:
        raise ValueError(
            f"Subject {subject_id} technique mismatch: missing={sorted(expected-observed)}, "
            f"extra={sorted(observed-expected)}"
        )
    return (
        selected_rows,
        extra_rows,
        run_qc,
        qc,
        list(base.CANONICAL_TECHNIQUE_ORDER),
    )


def values(rows: Sequence[dict[str, Any]], key: str) -> list[float]:
    result: list[float] = []
    for row in rows:
        value = row.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            result.append(float(value))
    return result


def mean_or_none(items: Sequence[float]) -> float | None:
    return statistics.mean(items) if items else None


def median_or_none(items: Sequence[float]) -> float | None:
    return statistics.median(items) if items else None


def sd_or_none(items: Sequence[float]) -> float | None:
    return statistics.stdev(items) if len(items) > 1 else (0.0 if items else None)


def summarize_subject(
    rows: Sequence[dict[str, Any]], subject_id: int, technique_order: Sequence[str]
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(row["technique"], row["id_level"])].append(row)

    summaries: list[dict[str, Any]] = []
    for technique in technique_order:
        for id_level in ID_ORDER:
            group = sorted(grouped[(technique, id_level)], key=lambda row: row["case"])
            if len(group) != EVENTS_PER_ID:
                raise ValueError(
                    f"Subject {subject_id} {technique} {id_level}: expected {EVENTS_PER_ID}, found {len(group)}"
                )
            formal = [row for row in group if not row["is_start_ball"]]
            if len(formal) != EVENTS_PER_ID - 1:
                raise ValueError(
                    f"Subject {subject_id} {technique} {id_level}: expected 15 non-start rows, found {len(formal)}"
                )
            failed = [row for row in group if row["trigger_failed"]]
            formal_failed = [row for row in formal if row["trigger_failed"]]
            trigger_values = values(group, "trigger_time_s")
            formal_trigger_values = values(formal, "trigger_time_s")
            used_values = values(group, "used_time_s")
            movement_values = values(group, "movement_distance_m")
            entry_total = sum(int(row["in_target_times"]) for row in group)
            formal_entry_total = sum(int(row["in_target_times"]) for row in formal)
            summaries.append(
                {
                    "subject_id": subject_id,
                    "technique": technique,
                    "id_level": id_level,
                    "id_bits": group[0]["id_bits"],
                    "layout_diameter_m": group[0]["layout_diameter_m"],
                    "raw_48_trial_count": len(group),
                    "raw_48_failure_n": len(failed),
                    "raw_48_success_n": len(group) - len(failed),
                    "raw_48_failure_rate": len(failed) / len(group),
                    "raw_48_entry_total": entry_total,
                    "raw_48_entry_mean_per_event": entry_total / len(group),
                    "task_completion_time_48_s": sum(used_values) if used_values else None,
                    "task_time_valid_n_48": len(used_values),
                    "movement_distance_48_m": sum(movement_values) if movement_values else None,
                    "movement_valid_n_48": len(movement_values),
                    "trigger_time_valid_n_48": len(trigger_values),
                    "trigger_time_mean_48_s": mean_or_none(trigger_values),
                    "trigger_time_median_48_s": median_or_none(trigger_values),
                    "trigger_time_sd_48_s": sd_or_none(trigger_values),
                    "trigger_time_min_48_s": min(trigger_values) if trigger_values else None,
                    "trigger_time_max_48_s": max(trigger_values) if trigger_values else None,
                    "starting_ball_n": sum(row["is_start_ball"] for row in group),
                    "formal_45_trial_count": len(formal),
                    "formal_45_failure_n": len(formal_failed),
                    "formal_45_failure_rate": len(formal_failed) / len(formal),
                    "formal_45_entry_total": formal_entry_total,
                    "formal_45_trigger_time_valid_n": len(formal_trigger_values),
                    "formal_45_trigger_time_mean_s": mean_or_none(formal_trigger_values),
                }
            )
    return summaries


def combine_summaries(
    subject_summaries: Sequence[dict[str, Any]], technique_order: Sequence[str]
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in subject_summaries:
        grouped[(row["technique"], row["id_level"])].append(row)

    metric_specs = [
        ("raw_48_entry_total", "target_entry_total_48"),
        ("task_completion_time_48_s", "task_completion_time_48_s"),
        ("movement_distance_48_m", "movement_distance_48_m"),
        ("trigger_time_mean_48_s", "trigger_time_mean_48_s"),
        ("raw_48_failure_rate", "trigger_failure_rate_48"),
    ]
    combined: list[dict[str, Any]] = []
    for technique in technique_order:
        for id_level in ID_ORDER:
            group = sorted(
                grouped[(technique, id_level)], key=lambda row: row["subject_id"]
            )
            if [row["subject_id"] for row in group] != list(SUBJECT_IDS):
                raise ValueError(
                    f"{technique} {id_level}: expected Subjects {SUBJECT_IDS}, "
                    f"found {[row['subject_id'] for row in group]}"
                )
            output: dict[str, Any] = {
                "technique_order": list(technique_order).index(technique) + 1,
                "technique": technique,
                "id_level": id_level,
                "id_bits": group[0]["id_bits"],
                "layout_diameter_m": group[0]["layout_diameter_m"],
                "subject_count": len(group),
                "raw_48_trial_count_pooled": sum(
                    row["raw_48_trial_count"] for row in group
                ),
                "trigger_failure_n_48_pooled": sum(
                    row["raw_48_failure_n"] for row in group
                ),
                "trigger_success_n_48_pooled": sum(
                    row["raw_48_success_n"] for row in group
                ),
                "formal_45_trial_count_pooled": sum(
                    row["formal_45_trial_count"] for row in group
                ),
                "formal_45_failure_n_pooled": sum(
                    row["formal_45_failure_n"] for row in group
                ),
                "formal_45_failure_rate_pooled": sum(
                    row["formal_45_failure_n"] for row in group
                )
                / sum(row["formal_45_trial_count"] for row in group),
                "formal_45_entry_total_pooled": sum(
                    row["formal_45_entry_total"] for row in group
                ),
            }
            output["trigger_failure_rate_48"] = output[
                "trigger_failure_n_48_pooled"
            ] / output["raw_48_trial_count_pooled"]
            output["target_entry_total_48_pooled"] = sum(
                row["raw_48_entry_total"] for row in group
            )
            for subject_id, row in zip(SUBJECT_IDS, group):
                output[f"trigger_failure_rate_48_subject{subject_id}"] = row[
                    "raw_48_failure_rate"
                ]
                output[f"target_entry_total_48_subject{subject_id}"] = row[
                    "raw_48_entry_total"
                ]
                output[f"task_completion_time_48_s_subject{subject_id}"] = row[
                    "task_completion_time_48_s"
                ]
                output[f"movement_distance_48_m_subject{subject_id}"] = row[
                    "movement_distance_48_m"
                ]
                output[f"trigger_time_mean_48_s_subject{subject_id}"] = row[
                    "trigger_time_mean_48_s"
                ]
            for source_key, combined_key in metric_specs:
                metric_values = [row[source_key] for row in group]
                if any(value is None for value in metric_values):
                    output[combined_key] = None
                    output[f"{combined_key}_between_subject_sd"] = None
                else:
                    output[combined_key] = statistics.mean(metric_values)
                    output[f"{combined_key}_between_subject_sd"] = sd_or_none(
                        [float(value) for value in metric_values]
                    )
            # Give charts the canonical key used by the existing Pillow
            # renderer for whole-number entry-axis tick labels.
            output["in_target_entries_total"] = output["target_entry_total_48"]
            combined.append(output)
    return combined


def write_csv(path: Path, rows: Sequence[dict[str, Any]], fields: Sequence[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields), extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    field: base.round_value(row.get(field))
                    if isinstance(row.get(field), float)
                    else ("" if row.get(field) is None else row.get(field))
                    for field in fields
                }
            )


def render_metric_charts(output_dir: Path, combined: Sequence[dict[str, Any]]) -> None:
    charts = [
        (
            "task_completion_time_48_s",
            "Task Completion Time — 48-event mean",
            "Time (s)",
            "task_completion_time_48_by_id.png",
            "task_completion_time_48_s_between_subject_sd",
        ),
        (
            "movement_distance_48_m",
            "Movement Distance — 48-event mean",
            "Distance (m)",
            "movement_distance_48_by_id.png",
            "movement_distance_48_m_between_subject_sd",
        ),
        (
            "trigger_time_mean_48_s",
            "Mean Trigger Time — 48-event mean",
            "Trigger time (s)",
            "trigger_time_mean_48_by_id.png",
            "trigger_time_mean_48_s_between_subject_sd",
        ),
        (
            "trigger_failure_rate_48",
            "Trigger Trial Failure Rate — in_target_times > 1",
            "Failure rate",
            "trigger_failure_rate_48_by_id.png",
            "trigger_failure_rate_48_between_subject_sd",
        ),
        (
            "in_target_entries_total",
            "Target Entry Count — 48-event mean",
            "Entries (count)",
            "target_entries_48_by_id.png",
            "target_entry_total_48_between_subject_sd",
        ),
    ]
    for metric, title, unit, filename, error_key in charts:
        image = base.Image.new("RGB", (2400, 1600), (249, 250, 252))
        draw = base.ImageDraw.Draw(image)
        base.draw_bar_panel(
            draw,
            (90, 70, 2310, 1510),
            combined,
            list(base.CANONICAL_TECHNIQUE_ORDER),
            metric,
            f"{title} — Subjects 1 & 5",
            unit,
            error_key,
            show_legend=True,
            large=True,
        )
        image.save(output_dir / filename, format="PNG", optimize=True)

    panel_width = 2200
    panel_height = 1310
    panel_rows = 3
    legend_top = 175 + panel_rows * panel_height + 50
    combined_image = base.Image.new(
        "RGB", (4500, legend_top + 3 * 105 + 160), (249, 250, 252)
    )
    draw = base.ImageDraw.Draw(combined_image)
    title_font = base.load_font(50, bold=True)
    subtitle_font = base.load_font(26)
    draw.text(
        (110, 55),
        "Subjects 1 & 5 Trigger Performance — 48-event scope",
        font=title_font,
        fill=(23, 34, 52),
    )
    draw.text(
        (112, 120),
        "Equal-weight mean of two subjects; bars within each ID follow technique order T01–T15.",
        font=subtitle_font,
        fill=(82, 92, 108),
    )
    for index, (metric, title, unit, _, error_key) in enumerate(charts):
        column = index % 2
        row_index = index // 2
        base.draw_bar_panel(
            draw,
            (
                40 + column * panel_width,
                175 + row_index * panel_height,
                40 + (column + 1) * panel_width - 20,
                175 + (row_index + 1) * panel_height - 20,
            ),
            combined,
            list(base.CANONICAL_TECHNIQUE_ORDER),
            metric,
            title,
            unit,
            error_key,
            show_legend=False,
            large=False,
        )
    base.draw_technique_legend(
        draw,
        (160, legend_top),
        list(base.CANONICAL_TECHNIQUE_ORDER),
        columns=5,
        column_width=850,
        row_height=105,
        font_size=24,
    )
    combined_image.save(
        output_dir / "subjects1_5_trigger_48_metrics_by_id.png",
        format="PNG",
        optimize=True,
    )


def write_entry_table_csv(output_dir: Path, combined: Sequence[dict[str, Any]]) -> None:
    fields = [
        "technique_order",
        "technique",
        "id_level",
        "id_bits",
        "raw_48_trial_count_pooled",
        "target_entry_total_48_subject1",
        "target_entry_total_48_subject5",
        "target_entry_total_48",
        "target_entry_total_48_between_subject_sd",
        "target_entry_total_48_pooled",
    ]
    rows = []
    for row in combined:
        output = dict(row)
        output["target_entry_total_48_pooled"] = (
            row["target_entry_total_48_subject1"]
            + row["target_entry_total_48_subject5"]
        )
        rows.append(output)
    write_csv(output_dir / "target_entry_count_48_by_id.csv", rows, fields)


def draw_entry_table(output_dir: Path, combined: Sequence[dict[str, Any]]) -> None:
    width, row_height = 2100, 66
    top = 190
    height = top + row_height * (len(base.CANONICAL_TECHNIQUE_ORDER) + 1) + 125
    image = base.Image.new("RGB", (width, height), (249, 250, 252))
    draw = base.ImageDraw.Draw(image)
    title_font = base.load_font(40, bold=True)
    subtitle_font = base.load_font(20)
    header_font = base.load_font(22, bold=True)
    cell_font = base.load_font(19)
    small_font = base.load_font(16)
    dark = (30, 41, 59)
    muted = (80, 90, 105)
    line = (205, 212, 222)
    draw.text(
        (70, 42),
        "Target Entry Count — Subjects 1 & 5, 48-event scope",
        font=title_font,
        fill=dark,
    )
    draw.text(
        (72, 103),
        "Cell = equal-subject mean (Subject 1 / Subject 5); sum of in_target_times over 16 events per ID.",
        font=subtitle_font,
        fill=muted,
    )
    x0 = 70
    col_widths = [120, 510, 450, 450, 450]
    headers = [
        "Order",
        "Technique",
        "L-ID\n2.713 bits",
        "M-ID\n3.459 bits",
        "H-ID\n4.605 bits",
    ]
    x_positions = [x0]
    for col_width in col_widths[:-1]:
        x_positions.append(x_positions[-1] + col_width)
    right = x0 + sum(col_widths)
    y0 = top
    draw.rectangle((x0, y0, right, y0 + row_height), fill=(225, 231, 239), outline=line, width=2)
    for x, col_width, header in zip(x_positions, col_widths, headers):
        parts = header.split("\n")
        if len(parts) == 1:
            base.text_centered(draw, (x + col_width / 2, y0 + row_height / 2), header, header_font, dark)
        else:
            base.text_centered(draw, (x + col_width / 2, y0 + 22), parts[0], header_font, dark)
            base.text_centered(draw, (x + col_width / 2, y0 + 46), parts[1], small_font, muted)

    by_key = {(row["technique"], row["id_level"]): row for row in combined}
    for index, technique in enumerate(base.CANONICAL_TECHNIQUE_ORDER):
        y = top + row_height * (index + 1)
        fill = (255, 255, 255) if index % 2 == 0 else (244, 247, 250)
        draw.rectangle((x0, y, right, y + row_height), fill=fill, outline=line, width=1)
        base.text_centered(draw, (x_positions[0] + col_widths[0] / 2, y + row_height / 2), f"T{index + 1:02d}", cell_font, dark)
        base.text_centered(draw, (x_positions[1] + col_widths[1] / 2, y + row_height / 2), technique, cell_font, dark)
        for id_index, id_level in enumerate(ID_ORDER):
            row = by_key[(technique, id_level)]
            s1 = row["target_entry_total_48_subject1"]
            s5 = row["target_entry_total_48_subject5"]
            mean = row["target_entry_total_48"]
            label = f"{mean:.1f} ({int(s1)}/{int(s5)})"
            column = id_index + 2
            base.text_centered(
                draw,
                (x_positions[column] + col_widths[column] / 2, y + row_height / 2),
                label,
                cell_font,
                dark,
            )
    draw.text(
        (72, height - 75),
        "T01–T15 follow the acquisition order; CSV includes pooled totals and between-subject SD.",
        font=subtitle_font,
        fill=muted,
    )
    image.save(
        output_dir / "target_entry_count_table_48.png", format="PNG", optimize=True
    )


def main() -> None:
    args = parse_args()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    input_dirs = {1: args.subject1_input.resolve(), 5: args.subject5_input.resolve()}

    all_selected: list[dict[str, Any]] = []
    all_extras: list[dict[str, Any]] = []
    all_run_qc: list[dict[str, Any]] = []
    qc_sections: list[str] = []
    subject_summaries: list[dict[str, Any]] = []
    technique_order: list[str] | None = None

    for subject_id in SUBJECT_IDS:
        selected, extras, run_qc, qc, order = collect_subject(
            input_dirs[subject_id], subject_id
        )
        summaries = summarize_subject(selected, subject_id, order)
        all_selected.extend(selected)
        all_extras.extend(extras)
        all_run_qc.extend(run_qc)
        subject_summaries.extend(summaries)
        qc_sections.append("\n".join(qc))
        if technique_order is None:
            technique_order = order
        elif set(order) != set(technique_order):
            raise ValueError("Subjects 1 and 5 do not contain the same techniques")

    assert technique_order is not None
    combined = combine_summaries(subject_summaries, technique_order)

    trial_fields = [
        "subject_id",
        "run_id",
        "technique",
        "case",
        "logged_id_code",
        "id_level",
        "id_bits",
        "layout_diameter_m",
        "start_ball",
        "ball_index",
        "is_start_ball",
        "position_within_id",
        "in_target_times",
        "trigger_failed",
        "used_time_s",
        "trigger_time_s",
        "movement_distance_m",
        "trajectory_sample_count",
        "analysis_scope",
        "raw_data_length",
        "raw_row_json",
    ]
    extra_fields = trial_fields + ["extra_reason"]
    subject_fields = [
        "subject_id",
        "technique",
        "id_level",
        "id_bits",
        "layout_diameter_m",
        "raw_48_trial_count",
        "raw_48_failure_n",
        "raw_48_success_n",
        "raw_48_failure_rate",
        "raw_48_entry_total",
        "raw_48_entry_mean_per_event",
        "task_completion_time_48_s",
        "task_time_valid_n_48",
        "movement_distance_48_m",
        "movement_valid_n_48",
        "trigger_time_valid_n_48",
        "trigger_time_mean_48_s",
        "trigger_time_median_48_s",
        "trigger_time_sd_48_s",
        "trigger_time_min_48_s",
        "trigger_time_max_48_s",
        "starting_ball_n",
        "formal_45_trial_count",
        "formal_45_failure_n",
        "formal_45_failure_rate",
        "formal_45_entry_total",
        "formal_45_trigger_time_valid_n",
        "formal_45_trigger_time_mean_s",
    ]
    combined_fields = [
        "technique_order",
        "technique",
        "id_level",
        "id_bits",
        "layout_diameter_m",
        "subject_count",
        "raw_48_trial_count_pooled",
        "trigger_failure_n_48_pooled",
        "trigger_success_n_48_pooled",
        "trigger_failure_rate_48",
        "trigger_failure_rate_48_between_subject_sd",
        "trigger_failure_rate_48_subject1",
        "trigger_failure_rate_48_subject5",
        "target_entry_total_48_pooled",
        "target_entry_total_48",
        "target_entry_total_48_between_subject_sd",
        "target_entry_total_48_subject1",
        "target_entry_total_48_subject5",
        "task_completion_time_48_s",
        "task_completion_time_48_s_between_subject_sd",
        "task_completion_time_48_s_subject1",
        "task_completion_time_48_s_subject5",
        "movement_distance_48_m",
        "movement_distance_48_m_between_subject_sd",
        "movement_distance_48_m_subject1",
        "movement_distance_48_m_subject5",
        "trigger_time_mean_48_s",
        "trigger_time_mean_48_s_between_subject_sd",
        "trigger_time_mean_48_s_subject1",
        "trigger_time_mean_48_s_subject5",
        "formal_45_trial_count_pooled",
        "formal_45_failure_n_pooled",
        "formal_45_failure_rate_pooled",
        "formal_45_entry_total_pooled",
    ]
    run_qc_fields = list(all_run_qc[0].keys()) if all_run_qc else []

    write_csv(output_dir / "combined_48_trial_metrics.csv", all_selected, trial_fields)
    write_csv(output_dir / "extra_raw_event_audit.csv", all_extras, extra_fields)
    write_csv(output_dir / "subject_48_technique_metrics.csv", subject_summaries, subject_fields)
    write_csv(output_dir / "combined_48_technique_metrics.csv", combined, combined_fields)
    write_csv(output_dir / "run_qc.csv", all_run_qc, run_qc_fields)
    write_entry_table_csv(output_dir, combined)
    render_metric_charts(output_dir, combined)
    draw_entry_table(output_dir, combined)

    selected_by_subject = Counter(row["subject_id"] for row in all_selected)
    extras_by_subject = Counter(row["subject_id"] for row in all_extras)
    raw_by_subject = {
        subject_id: sum(int(row["raw_rows"]) for row in all_run_qc if row["subject_id"] == subject_id)
        for subject_id in SUBJECT_IDS
    }
    raw_failure_n = sum(row["trigger_failed"] for row in all_selected)
    raw_trial_n = len(all_selected)
    formal_rows = [row for row in all_selected if not row["is_start_ball"]]
    formal_failure_n = sum(row["trigger_failed"] for row in formal_rows)
    complete_runs = sum(
        row["selected_48_rows"] == EVENTS_PER_ID * 3 for row in all_run_qc
    )
    qc_sections.append(
        "===== Combined validation =====\n"
        f"Selected 48-event rows: {len(all_selected)} (expected {len(SUBJECT_IDS) * EXPECTED_SELECTED_ROWS_PER_SUBJECT})\n"
        f"Raw rows read before extra-row audit: Subject 1={raw_by_subject[1]}, Subject 5={raw_by_subject[5]}\n"
        f"Selected rows by subject: Subject 1={selected_by_subject[1]}, Subject 5={selected_by_subject[5]}\n"
        f"Extra raw rows excluded and audited: Subject 1={extras_by_subject[1]}, Subject 5={extras_by_subject[5]}\n"
        f"Complete selected 48-event runs: {complete_runs}/{len(all_run_qc)}\n"
        f"Raw-48 Trigger failures: {raw_failure_n}/{raw_trial_n} ({raw_failure_n / raw_trial_n:.1%})\n"
        f"Formal-45 Trigger failures (Starting Ball excluded): {formal_failure_n}/{len(formal_rows)} ({formal_failure_n / len(formal_rows):.1%})\n"
        "Failure rule: in_target_times > 1 means failed; in_target_times <= 1 means successful.\n"
        "Combined estimates use equal subject weighting; error bars are sample SD between Subjects 1 and 5.\n"
        "Starting Balls are retained in the primary 48-event scope; no raw outlier removal was applied.\n"
        "This is Trigger-specific multi-entry failure, not Task Error Rate or Throughput."
    )
    (output_dir / "quality_report.txt").write_text(
        "\n\n".join(qc_sections) + "\n", encoding="utf-8"
    )
    manifest = {
        "subject_ids": list(SUBJECT_IDS),
        "input_dirs": {str(subject_id): str(input_dirs[subject_id]) for subject_id in SUBJECT_IDS},
        "output_dir": str(output_dir),
        "primary_scope": "raw_48_selected_including_starting_ball",
        "events_per_id": EVENTS_PER_ID,
        "selected_rows": len(all_selected),
        "raw_rows_read": raw_by_subject,
        "extra_rows_excluded": extras_by_subject,
        "combined_cells": len(combined),
        "raw_48_failure_n": raw_failure_n,
        "raw_48_failure_rate": raw_failure_n / raw_trial_n,
        "formal_45_failure_n": formal_failure_n,
        "formal_45_failure_rate": formal_failure_n / len(formal_rows),
        "rule": "in_target_times > 1",
        "aggregation": "equal subject weighting; between-subject sample SD",
    }
    (output_dir / "analysis_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Output: {output_dir}")
    print(f"Selected 48-event rows: {len(all_selected)}")
    print(f"Extra raw rows audited/excluded: {len(all_extras)}")
    print(f"Raw-48 failures: {raw_failure_n}/{raw_trial_n} ({raw_failure_n / raw_trial_n:.1%})")
    print(f"Technique x ID combined rows: {len(combined)}")


if __name__ == "__main__":
    main()
