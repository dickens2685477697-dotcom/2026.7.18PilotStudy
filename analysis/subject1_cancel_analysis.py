#!/usr/bin/env python3
"""Analyze Subject 1 Cancel data using all 48 events per technique.

Cancel is not treated as the Magic-Tap 45-target task here.  The 16 recorded
events in each logged ID block are retained, including the Starting Ball, so
one complete technique contributes 48 events (16 per ID).  Incomplete raw
runs are kept and reported as NA in the technique-by-ID summary.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Sequence

import subject2_cancel_analysis as base


SUBJECT_ID = 1
EVENTS_PER_ID = 16
EXPECTED_TECHNIQUES = 15
EXPECTED_RAW_ROWS = EXPECTED_TECHNIQUES * 3 * EVENTS_PER_ID
RAW_ID_TO_LEVEL = {1: "L-ID", 2: "M-ID", 3: "H-ID"}
ID_LAYOUT = {
    "L-ID": (2.713, 0.5),
    "M-ID": (3.459, 0.6),
    "H-ID": (4.605, 0.7),
}


SUMMARY_FIELDS = [
    "subject_id",
    "technique",
    "technique_short",
    "id_level",
    "id_bits",
    "layout_diameter_m",
    "trial_count",
    "target_event_n",
    "mine_event_n",
    "mine_cancel_success_n",
    "mine_cancel_failure_n",
    "mine_cancel_unresolved_n",
    "cancel_success_rate",
    "cancel_failure_rate",
    "cancel_unresolved_rate",
    "cancel_success_ci_lower",
    "cancel_success_ci_upper",
    "cancel_failure_ci_lower",
    "cancel_failure_ci_upper",
    "cancel_time_valid_n",
    "cancel_time_mean_s",
    "cancel_time_median_s",
    "cancel_time_sd_s",
    "cancel_time_iqr_s",
    "cancel_time_min_s",
    "cancel_time_max_s",
    "successful_cancel_time_valid_n",
    "successful_cancel_time_mean_s",
    "target_activation_valid_n",
    "target_activation_rate",
    "target_trigger_time_mean_s",
    "target_trigger_time_median_s",
    "target_trigger_time_sd_s",
    "target_trigger_time_iqr_s",
    "target_trigger_time_min_s",
    "target_trigger_time_max_s",
    "reentry_total",
    "reentry_mean",
    "cancel_times_total",
    "task_completion_time_all_s",
    "task_completion_time_target_s",
    "task_completion_time_mine_s",
    "task_time_valid_n",
    "movement_distance_all_m",
    "movement_distance_target_m",
    "movement_distance_mine_m",
    "movement_distance_valid_n",
    "trajectory_missing_n",
    "cancel_time_outlier_n",
    "target_trigger_time_outlier_n",
    "used_time_outlier_n",
    "movement_distance_outlier_n",
]

COUNT_FIELDS = {
    "trial_count",
    "target_event_n",
    "mine_event_n",
    "mine_cancel_success_n",
    "mine_cancel_failure_n",
    "mine_cancel_unresolved_n",
    "cancel_time_valid_n",
    "successful_cancel_time_valid_n",
    "target_activation_valid_n",
    "reentry_total",
    "cancel_times_total",
    "task_time_valid_n",
    "movement_distance_valid_n",
    "trajectory_missing_n",
    "cancel_time_outlier_n",
    "target_trigger_time_outlier_n",
    "used_time_outlier_n",
    "movement_distance_outlier_n",
}


def parse_args() -> argparse.Namespace:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=root / "1" / "Cancel",
        help="Subject 1 Cancel directory containing run folders.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=root / "analysis_outputs" / "subject1_cancel",
        help="Directory for CSV, QC, JSON, and PNG outputs.",
    )
    return parser.parse_args()


def make_record(
    row: Sequence[str],
    subject_id: int,
    run_id: str,
    distances: dict[int, float],
    sample_counts: dict[int, int],
) -> dict[str, Any]:
    case = base.finite_int(row[base.TIME_INDEX["case"]])
    raw_id = base.finite_int(row[base.TIME_INDEX["logged_id_code"]])
    start_ball = base.finite_int(row[base.TIME_INDEX["start_ball"]])
    ball_index = base.finite_int(row[base.TIME_INDEX["ball_index"]])
    if case is None or raw_id is None or start_ball is None or ball_index is None:
        raise ValueError("Missing Case, ID, start, or ballIndex core field")

    try:
        points = base.target_points(row)
        diameter_m = base.layout_diameter(points)
        id_level, id_bits = base.match_id(diameter_m)
        geometry_valid = True
    except ValueError:
        diameter_m = ID_LAYOUT[RAW_ID_TO_LEVEL.get(raw_id, "L-ID")][1]
        id_level = RAW_ID_TO_LEVEL.get(raw_id, "Unknown")
        id_bits = ID_LAYOUT.get(id_level, (None, None))[0]
        geometry_valid = False

    mine_value = base.parse_bool(row[base.TIME_INDEX["is_mine_ball"]])
    success_value = base.parse_bool(row[base.TIME_INDEX["successfully_canceled"]])
    trigger_time = base.parse_sentinel_float(row[base.TIME_INDEX["trigger_time_s"]])
    cancel_time = base.parse_sentinel_float(row[base.TIME_INDEX["cancel_time_s"]])

    record: dict[str, Any] = {
        "subject_id": subject_id,
        "run_id": run_id,
        "technique": row[base.TIME_INDEX["technique"]].strip(),
        "technique_short": base.TECHNIQUE_SHORT.get(
            row[base.TIME_INDEX["technique"]].strip(),
            row[base.TIME_INDEX["technique"]].strip(),
        ),
        "case": case,
        "logged_id_code": raw_id,
        "id_level": id_level,
        "id_bits": id_bits,
        "layout_diameter_m": diameter_m,
        "start_ball": start_ball,
        "ball_index": ball_index,
        "is_start_ball": ball_index == start_ball,
        # Keep the base module's canonical scope name so its auxiliary
        # summaries (e.g. direction diagnostics) include these 48-event
        # records.  The 48-event rule itself is enforced by this script's
        # grouping/validation rather than by the scope label.
        "analysis_scope": "primary",
        "position_within_id": None,
        "trigger_condition": row[base.TIME_INDEX["trigger_condition"]].strip(),
        "in_target_times": base.finite_int(row[base.TIME_INDEX["in_target_times"]]),
        "used_time_s": base.parse_sentinel_float(row[base.TIME_INDEX["used_time_s"]]),
        "react_time_s": base.parse_sentinel_float(row[base.TIME_INDEX["react_time_s"]]),
        "react_frequency": base.finite_float(row[base.TIME_INDEX["react_frequency"]]),
        "obstacle_react_frequency": base.finite_float(
            row[base.TIME_INDEX["obstacle_react_frequency"]]
        ),
        "trigger_time_s": trigger_time,
        "target_trigger_time_s": trigger_time if mine_value is False else None,
        "cancel_time_s": cancel_time,
        "is_mine_ball": mine_value,
        "successfully_canceled": success_value,
        "cancel_reason": row[base.TIME_INDEX["cancel_reason"]].strip(),
        "no_trigger_reason": row[base.TIME_INDEX["no_trigger_reason"]].strip(),
        "cancel_times": base.finite_int(row[base.TIME_INDEX["cancel_times"]]) or 0,
        "direction_angle_frame": row[base.TIME_INDEX["direction_angle_frame"]].strip(),
        "direction_speed_min": base.finite_float(
            row[base.TIME_INDEX["direction_speed_min"]]
        ),
        "movement_distance_m": distances.get(case),
        "trajectory_sample_count": sample_counts.get(case, 0),
        "geometry_valid": geometry_valid,
        "raw_data_length": len(row),
        "raw_row_json": json.dumps(list(row), ensure_ascii=False, separators=(",", ":")),
    }
    return record


def process_runs(
    input_dir: Path, subject_id: int
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[str], dict[str, dict[int, dict[str, Any]]]]:
    time_files = sorted(input_dir.glob("*/*-time.csv"))
    if not time_files:
        raise FileNotFoundError(f"No time CSV files under {input_dir}")

    rows: list[dict[str, Any]] = []
    start_audit: list[dict[str, Any]] = []
    run_qc: list[dict[str, Any]] = []
    qc: list[str] = [f"Subject folder ID: {subject_id}", f"Time files found: {len(time_files)}"]
    technique_order: list[str] = []
    time_rows_by_run: dict[str, dict[int, dict[str, Any]]] = {}

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
        row_lengths = sorted({len(row) for row in raw_rows})
        technique_values = {
            row[base.TIME_INDEX["technique"]].strip()
            for row in raw_rows
            if len(row) > base.TIME_INDEX["technique"]
        }
        if len(technique_values) != 1:
            raise ValueError(f"{run_id}: multiple techniques {sorted(technique_values)}")
        technique = next(iter(technique_values))
        technique_order.append(technique)

        case_values = [
            base.finite_int(row[base.TIME_INDEX["case"]])
            for row in raw_rows
            if len(row) > base.TIME_INDEX["case"]
        ]
        case_sequence_ok = case_values == list(range(1, len(raw_rows) + 1))
        distances, sample_counts, trajectory_cases = base.trajectory_distances(
            trajectory_path
        )
        time_cases = {case for case in case_values if case is not None}
        missing_trajectory_cases = sorted(time_cases - trajectory_cases)
        extra_trajectory_cases = sorted(trajectory_cases - time_cases)

        run_records: list[dict[str, Any]] = []
        for row in raw_rows:
            record = make_record(row, subject_id, run_id, distances, sample_counts)
            run_records.append(record)
        by_id: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for record in run_records:
            by_id[record["logged_id_code"]].append(record)
            time_rows_by_run.setdefault(run_id, {})[record["case"]] = record

        raw_id_counts = Counter(record["logged_id_code"] for record in run_records)
        start_count = 0
        duplicate_count = 0
        missing_ids = sorted({1, 2, 3} - set(by_id))
        for raw_id in sorted(by_id):
            block = sorted(by_id[raw_id], key=lambda item: item["case"])
            seen_nonstart: set[int] = set()
            for position, record in enumerate(block, start=1):
                record["position_within_id"] = position
                if record["is_start_ball"]:
                    start_count += 1
                    start_audit.append(
                        {
                            key: value
                            for key, value in record.items()
                            if key != "raw_row_json"
                        }
                        | {
                            "audit_note": "Starting Ball retained in the 48-event Cancel analysis."
                        }
                    )
                elif record["ball_index"] in seen_nonstart:
                    duplicate_count += 1
                seen_nonstart.add(record["ball_index"])

        expected_complete = set(by_id) == {1, 2, 3} and all(
            len(block) == EVENTS_PER_ID for block in by_id.values()
        )
        status = "PASS" if expected_complete and not missing_trajectory_cases else "CHECK"
        notes: list[str] = []
        if missing_ids:
            notes.append(f"missing logged IDs={missing_ids}")
        short_blocks = [
            f"ID{raw_id} rows={len(block)}"
            for raw_id, block in sorted(by_id.items())
            if len(block) != EVENTS_PER_ID
        ]
        notes.extend(short_blocks)
        if duplicate_count:
            notes.append(f"duplicate non-start ball records retained={duplicate_count}")
        if missing_trajectory_cases:
            notes.append(f"missing trajectory cases={missing_trajectory_cases}")
        if extra_trajectory_cases:
            notes.append(f"extra trajectory cases={extra_trajectory_cases}")

        run_qc.append(
            {
                "subject_id": subject_id,
                "run_id": run_id,
                "technique": technique,
                "header_columns": len(header),
                "data_columns": ";".join(str(value) for value in row_lengths),
                "raw_rows": len(run_records),
                "raw_id1_rows": raw_id_counts.get(1, 0),
                "raw_id2_rows": raw_id_counts.get(2, 0),
                "raw_id3_rows": raw_id_counts.get(3, 0),
                "primary_48_event_rows": len(run_records),
                "primary_id1_rows": raw_id_counts.get(1, 0),
                "primary_id2_rows": raw_id_counts.get(2, 0),
                "primary_id3_rows": raw_id_counts.get(3, 0),
                "excluded_start_rows": 0,
                "starting_ball_rows_retained": start_count,
                "duplicate_nonstart_targets_retained": duplicate_count,
                "case_sequence_ok": case_sequence_ok,
                "trajectory_rows": sum(sample_counts.values()),
                "trajectory_case_count": len(trajectory_cases),
                "missing_trajectory_case_count": len(missing_trajectory_cases),
                "extra_trajectory_case_count": len(extra_trajectory_cases),
                "status": status,
                "notes": "; ".join(notes),
            }
        )
        qc.append(
            f"{run_id}: mode={technique}, raw_rows={len(run_records)}, "
            f"48-event_rows={len(run_records)}, starts_retained={start_count}, "
            f"status={status}"
        )
        rows.extend(run_records)

    observed = set(technique_order)
    expected = set(base.CANONICAL_TECHNIQUE_ORDER)
    if len(technique_order) != len(observed) or observed != expected:
        raise ValueError(
            f"Technique set mismatch: missing={sorted(expected-observed)}, "
            f"extra={sorted(observed-expected)}"
        )
    qc.extend(
        [
            f"Unique techniques: {len(observed)}",
            f"Raw Cancel event rows retained: {len(rows)} (nominal expected {EXPECTED_RAW_ROWS})",
            "Analysis scope: all available Cancel records; Starting Balls are retained, "
            "so a complete technique has 48 events (16 per logged ID).",
            "ID mapping: raw 1/2/3 -> L-ID/M-ID/H-ID; geometry diameters 0.5/0.6/0.7 m.",
            "NA, blank, and -1 time values are treated as missing, never as zero.",
            "No raw outlier removal; M +/- 3 SD flags are sensitivity annotations only.",
        ]
    )
    return rows, start_audit, run_qc, qc, time_rows_by_run


def blank_summary(technique: str, id_level: str, subject_id: int) -> dict[str, Any]:
    id_bits, diameter = ID_LAYOUT[id_level]
    result: dict[str, Any] = {field: None for field in SUMMARY_FIELDS}
    result.update(
        {
            "subject_id": subject_id,
            "technique": technique,
            "technique_short": base.TECHNIQUE_SHORT[technique],
            "id_level": id_level,
            "id_bits": id_bits,
            "layout_diameter_m": diameter,
            "trial_count": 0,
            "target_event_n": 0,
            "mine_event_n": 0,
            "mine_cancel_success_n": 0,
            "mine_cancel_failure_n": 0,
            "mine_cancel_unresolved_n": 0,
            "cancel_time_valid_n": 0,
            "successful_cancel_time_valid_n": 0,
            "target_activation_valid_n": 0,
            # A missing technique × ID cell must stay NA in charts/tables;
            # zero is a valid observed count and would be misleading here.
            "reentry_total": None,
            "reentry_mean": None,
            "cancel_times_total": None,
            "task_time_valid_n": 0,
            "movement_distance_valid_n": 0,
            "trajectory_missing_n": 0,
            "cancel_time_outlier_n": 0,
            "target_trigger_time_outlier_n": 0,
            "used_time_outlier_n": 0,
            "movement_distance_outlier_n": 0,
        }
    )
    return result


def build_summary(rows: Sequence[dict[str, Any]], subject_id: int) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(row["technique"], row["id_level"])].append(row)

    summaries: list[dict[str, Any]] = []
    for technique in base.CANONICAL_TECHNIQUE_ORDER:
        for id_level in base.ID_ORDER:
            condition_rows = sorted(
                grouped[(technique, id_level)], key=lambda item: item["case"]
            )
            if not condition_rows:
                summaries.append(blank_summary(technique, id_level, subject_id))
                continue

            mine_rows = [row for row in condition_rows if row["is_mine_ball"] is True]
            target_rows = [row for row in condition_rows if row["is_mine_ball"] is False]
            successful = [
                row for row in mine_rows if row["successfully_canceled"] is True
            ]
            failed = [
                row for row in mine_rows if row["successfully_canceled"] is False
            ]
            unresolved = [
                row for row in mine_rows if row["successfully_canceled"] is None
            ]

            def values(source_rows: Sequence[dict[str, Any]], key: str) -> list[float]:
                result = [base.metric_value(row, key) for row in source_rows]
                return [value for value in result if value is not None]

            cancel_values = values(mine_rows, "cancel_time_s")
            successful_cancel_values = values(successful, "cancel_time_s")
            target_trigger_values = values(target_rows, "target_trigger_time_s")
            all_time = values(condition_rows, "used_time_s")
            target_time = values(target_rows, "used_time_s")
            mine_time = values(mine_rows, "used_time_s")
            all_distance = values(condition_rows, "movement_distance_m")
            target_distance = values(target_rows, "movement_distance_m")
            mine_distance = values(mine_rows, "movement_distance_m")
            layout = condition_rows[0]
            mine_success_ci = base.exact_binomial_interval(
                len(successful), len(mine_rows)
            )
            mine_failure_ci = base.exact_binomial_interval(len(failed), len(mine_rows))

            summaries.append(
                {
                    "subject_id": subject_id,
                    "technique": technique,
                    "technique_short": base.TECHNIQUE_SHORT[technique],
                    "id_level": id_level,
                    "id_bits": layout["id_bits"],
                    "layout_diameter_m": layout["layout_diameter_m"],
                    "trial_count": len(condition_rows),
                    "target_event_n": len(target_rows),
                    "mine_event_n": len(mine_rows),
                    "mine_cancel_success_n": len(successful),
                    "mine_cancel_failure_n": len(failed),
                    "mine_cancel_unresolved_n": len(unresolved),
                    "cancel_success_rate": len(successful) / len(mine_rows)
                    if mine_rows
                    else None,
                    "cancel_failure_rate": len(failed) / len(mine_rows)
                    if mine_rows
                    else None,
                    "cancel_unresolved_rate": len(unresolved) / len(mine_rows)
                    if mine_rows
                    else None,
                    "cancel_success_ci_lower": mine_success_ci[0],
                    "cancel_success_ci_upper": mine_success_ci[1],
                    "cancel_failure_ci_lower": mine_failure_ci[0],
                    "cancel_failure_ci_upper": mine_failure_ci[1],
                    "cancel_time_valid_n": len(cancel_values),
                    "cancel_time_mean_s": statistics.mean(cancel_values)
                    if cancel_values
                    else None,
                    "cancel_time_median_s": base.median_or_none(cancel_values),
                    "cancel_time_sd_s": base.sample_sd(cancel_values),
                    "cancel_time_iqr_s": base.iqr(cancel_values),
                    "cancel_time_min_s": min(cancel_values) if cancel_values else None,
                    "cancel_time_max_s": max(cancel_values) if cancel_values else None,
                    "successful_cancel_time_valid_n": len(successful_cancel_values),
                    "successful_cancel_time_mean_s": statistics.mean(
                        successful_cancel_values
                    )
                    if successful_cancel_values
                    else None,
                    "target_activation_valid_n": len(target_trigger_values),
                    "target_activation_rate": len(target_trigger_values)
                    / len(target_rows)
                    if target_rows
                    else None,
                    "target_trigger_time_mean_s": statistics.mean(
                        target_trigger_values
                    )
                    if target_trigger_values
                    else None,
                    "target_trigger_time_median_s": base.median_or_none(
                        target_trigger_values
                    ),
                    "target_trigger_time_sd_s": base.sample_sd(target_trigger_values),
                    "target_trigger_time_iqr_s": base.iqr(target_trigger_values),
                    "target_trigger_time_min_s": min(target_trigger_values)
                    if target_trigger_values
                    else None,
                    "target_trigger_time_max_s": max(target_trigger_values)
                    if target_trigger_values
                    else None,
                    "reentry_total": sum(
                        int(row["in_target_times"] or 0) for row in condition_rows
                    ),
                    "reentry_mean": statistics.mean(
                        [int(row["in_target_times"] or 0) for row in condition_rows]
                    ),
                    "cancel_times_total": sum(
                        int(row["cancel_times"] or 0) for row in condition_rows
                    ),
                    "task_completion_time_all_s": sum(all_time) if all_time else None,
                    "task_completion_time_target_s": sum(target_time)
                    if target_time
                    else None,
                    "task_completion_time_mine_s": sum(mine_time) if mine_time else None,
                    "task_time_valid_n": len(all_time),
                    "movement_distance_all_m": sum(all_distance)
                    if all_distance
                    else None,
                    "movement_distance_target_m": sum(target_distance)
                    if target_distance
                    else None,
                    "movement_distance_mine_m": sum(mine_distance)
                    if mine_distance
                    else None,
                    "movement_distance_valid_n": len(all_distance),
                    "trajectory_missing_n": sum(
                        row["movement_distance_m"] is None for row in condition_rows
                    ),
                    "cancel_time_outlier_n": sum(
                        row.get("outlier_3sd_cancel_time", False)
                        for row in condition_rows
                    ),
                    "target_trigger_time_outlier_n": sum(
                        row.get("outlier_3sd_target_trigger_time", False)
                        for row in condition_rows
                    ),
                    "used_time_outlier_n": sum(
                        row.get("outlier_3sd_used_time", False)
                        for row in condition_rows
                    ),
                    "movement_distance_outlier_n": sum(
                        row.get("outlier_3sd_movement_distance", False)
                        for row in condition_rows
                    ),
                }
            )
    return summaries


def compose_selected_charts(output_dir: Path) -> None:
    names = [
        "cancel_success_rate_by_id.png",
        "cancel_failure_rate_by_id.png",
        "cancel_time_by_id.png",
        "target_trigger_time_by_id.png",
    ]
    images = [base.Image.open(output_dir / name).convert("RGB") for name in names]
    width = max(image.width for image in images)
    height = max(image.height for image in images)
    canvas = base.Image.new("RGB", (width * 2, height * 2), (249, 250, 252))
    title_font = base.load_font(48, bold=True)
    subtitle_font = base.load_font(24)
    draw = base.ImageDraw.Draw(canvas)
    draw.text(
        (85, 30),
        "Subject 1 Cancel Performance — 48-event scope",
        font=title_font,
        fill=(23, 34, 52),
    )
    draw.text(
        (87, 94),
        "Starting Balls are retained; contact010 is incomplete for L-ID and shown as NA.",
        font=subtitle_font,
        fill=(82, 92, 108),
    )
    offsets = [(0, 130), (width, 130), (0, height + 90), (width, height + 90)]
    for image, (x, y) in zip(images, offsets):
        canvas.paste(image, (x, y))
    canvas.save(output_dir / "subject1_cancel_metrics_by_id.png", format="PNG", optimize=True)


def write_target_entry_table(
    output_dir: Path, summaries: Sequence[dict[str, Any]]
) -> None:
    """Write a compact table for total target-entry counts.

    ``in_target_times`` is a per-event counter in the source log.  The
    requested table reports its sum for each technique × ID cell, with the
    corresponding per-event mean retained as a second column for auditability.
    """
    fields = [
        "subject_id",
        "technique_order",
        "technique",
        "technique_short",
        "id_level",
        "id_bits",
        "trial_count",
        "target_entry_count_total",
        "target_entry_count_mean_per_event",
        "complete_48_event_cell",
    ]
    rows: list[dict[str, Any]] = []
    order = {technique: index + 1 for index, technique in enumerate(base.CANONICAL_TECHNIQUE_ORDER)}
    for summary in summaries:
        trial_count = int(summary["trial_count"] or 0)
        rows.append(
            {
                "subject_id": summary["subject_id"],
                "technique_order": order[summary["technique"]],
                "technique": summary["technique"],
                "technique_short": summary["technique_short"],
                "id_level": summary["id_level"],
                "id_bits": summary["id_bits"],
                "trial_count": trial_count,
                "target_entry_count_total": summary["reentry_total"],
                "target_entry_count_mean_per_event": summary["reentry_mean"],
                "complete_48_event_cell": trial_count == EVENTS_PER_ID,
            }
        )
    base.write_csv(output_dir / "target_entry_count_by_id.csv", rows, fields)


def draw_target_entry_table(
    output_dir: Path, summaries: Sequence[dict[str, Any]]
) -> None:
    """Render a publication-friendly wide table (T01–T15 × three IDs)."""
    width, row_height = 2050, 66
    top = 190
    height = top + row_height * (len(base.CANONICAL_TECHNIQUE_ORDER) + 1) + 120
    image = base.Image.new("RGB", (width, height), (249, 250, 252))
    draw = base.ImageDraw.Draw(image)
    title_font = base.load_font(40, bold=True)
    subtitle_font = base.load_font(20)
    header_font = base.load_font(22, bold=True)
    cell_font = base.load_font(20)
    small_font = base.load_font(17)
    dark = (30, 41, 59)
    muted = (80, 90, 105)
    line = (205, 212, 222)
    draw.text((70, 42), "Target Entry Count by Technique × ID — Subject 1", font=title_font, fill=dark)
    draw.text(
        (72, 103),
        "Total = sum of in_target_times over retained 16 events per ID; contact010 L-ID is unavailable.",
        font=subtitle_font,
        fill=muted,
    )

    x0 = 70
    col_widths = [125, 500, 430, 430, 430]
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
    table_right = x0 + sum(col_widths)

    # Header row.
    y0 = top
    draw.rectangle((x0, y0, table_right, y0 + row_height), fill=(225, 231, 239), outline=line, width=2)
    for index, (x, col_width, header) in enumerate(zip(x_positions, col_widths, headers)):
        parts = header.split("\n")
        if len(parts) == 1:
            base.draw_text_centered(draw, (x + col_width / 2, y0 + row_height / 2), header, header_font, dark)
        else:
            base.draw_text_centered(draw, (x + col_width / 2, y0 + 22), parts[0], header_font, dark)
            base.draw_text_centered(draw, (x + col_width / 2, y0 + 46), parts[1], small_font, muted)

    by_key = {(row["technique"], row["id_level"]): row for row in summaries}
    for index, technique in enumerate(base.CANONICAL_TECHNIQUE_ORDER):
        y = top + row_height * (index + 1)
        fill = (255, 255, 255) if index % 2 == 0 else (244, 247, 250)
        draw.rectangle((x0, y, table_right, y + row_height), fill=fill, outline=line, width=1)
        order_label = f"T{index + 1:02d}"
        base.draw_text_centered(draw, (x_positions[0] + col_widths[0] / 2, y + row_height / 2), order_label, cell_font, dark)
        base.draw_text_centered(draw, (x_positions[1] + col_widths[1] / 2, y + row_height / 2), technique, cell_font, dark)
        for id_index, id_level in enumerate(base.ID_ORDER):
            column_index = id_index + 2
            row = by_key.get((technique, id_level), {})
            count = row.get("reentry_total")
            label = "NA" if count is None or int(row.get("trial_count") or 0) == 0 else str(int(count))
            base.draw_text_centered(
                draw,
                (x_positions[column_index] + col_widths[column_index] / 2, y + row_height / 2),
                label,
                cell_font,
                (166, 78, 78) if label == "NA" else dark,
            )
    draw.text(
        (72, height - 73),
        "Counts are descriptive; use target_entry_count_by_id.csv for the long-form values and denominators.",
        font=subtitle_font,
        fill=muted,
    )
    image.save(output_dir / "target_entry_count_table.png", format="PNG", optimize=True)


def main() -> None:
    args = parse_args()
    input_dir = args.input_dir.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    # Configure reusable rendering helpers for this standalone analysis.
    base.SUBJECT_ID = SUBJECT_ID
    base.CHART_SCOPE_LABEL = "All 48 Cancel events"

    rows, start_audit, run_qc, qc, time_rows_by_run = process_runs(input_dir, SUBJECT_ID)
    base.add_m3sd_flags(rows)
    summaries = build_summary(rows, SUBJECT_ID)
    reason_cancel = base.build_reason_summary(rows, "cancel_reason", "cancel_reason")
    reason_no_trigger = base.build_reason_summary(
        rows, "no_trigger_reason", "no_trigger_reason"
    )
    direction_summary = base.build_direction_summary(input_dir, time_rows_by_run)

    trial_fields = [
        "subject_id", "run_id", "technique", "technique_short", "case", "logged_id_code", "id_level", "id_bits",
        "layout_diameter_m", "start_ball", "ball_index", "is_start_ball", "analysis_scope", "position_within_id",
        "trigger_condition", "in_target_times", "used_time_s", "react_time_s", "react_frequency",
        "obstacle_react_frequency", "trigger_time_s", "target_trigger_time_s", "cancel_time_s", "is_mine_ball",
        "successfully_canceled", "cancel_reason", "no_trigger_reason", "cancel_times", "direction_angle_frame",
        "direction_speed_min", "movement_distance_m", "trajectory_sample_count", "geometry_valid", "raw_data_length",
        "outlier_3sd_cancel_time", "outlier_3sd_target_trigger_time", "outlier_3sd_used_time", "outlier_3sd_movement_distance",
        "raw_row_json",
    ]
    summary_fields = SUMMARY_FIELDS
    reason_fields = [
        "subject_id", "technique", "technique_short", "id_level", "source_field", "reason_category", "count"
    ]
    direction_fields = list(direction_summary[0].keys()) if direction_summary else [
        "subject_id", "technique", "technique_short", "id_level", "debug_rows", "angle_valid_n", "angle_mean_deg",
        "angle_median_deg", "angle_threshold_mean_deg", "index_speed_mean", "angle_pass_rate", "speed_pass_rate",
        "window_ready_rate", "cancel_already_triggered_n",
    ]
    run_qc_fields = list(run_qc[0].keys()) if run_qc else []
    start_fields = [field for field in trial_fields if field != "position_within_id"] + ["audit_note"]

    base.write_csv(output_dir / "cancel_trial_metrics.csv", rows, trial_fields)
    base.write_csv(output_dir / "cancel_start_ball_audit.csv", start_audit, start_fields)
    base.write_csv(output_dir / "cancel_id_technique_metrics.csv", summaries, summary_fields)
    base.write_csv(output_dir / "cancel_reason_summary.csv", reason_cancel, reason_fields)
    base.write_csv(output_dir / "no_trigger_reason_summary.csv", reason_no_trigger, reason_fields)
    base.write_csv(output_dir / "cancel_direction_debug_summary.csv", direction_summary, direction_fields)
    base.write_csv(output_dir / "run_qc.csv", run_qc, run_qc_fields)

    base.render_trigger_style_metric_charts(output_dir, summaries)
    # The source log also includes a per-event in_target_times counter.  Keep
    # this separate from activation rate: every target row has a valid trigger
    # in this data, while re-entry counts vary by technique and ID.
    base.draw_trigger_style_bar_chart(
        output_dir / "target_entry_count_by_id.png",
        summaries,
        "reentry_total",
        "Target Entry Count",
        "Entry count",
    )
    write_target_entry_table(output_dir, summaries)
    draw_target_entry_table(output_dir, summaries)
    base.draw_reason_chart(
        output_dir / "cancel_reason_counts.png",
        reason_cancel,
        "Cancel Reason Categories — Subject 1",
        "All retained 48-event Cancel records; detailed counts are in cancel_reason_summary.csv",
    )
    base.draw_reason_chart(
        output_dir / "no_trigger_reason_counts.png",
        reason_no_trigger,
        "No-trigger Reason Categories — Subject 1",
        "All retained 48-event Cancel records; detailed counts are in no_trigger_reason_summary.csv",
    )
    compose_selected_charts(output_dir)

    complete_techniques = sum(
        1 for run in run_qc if run["raw_rows"] == EVENTS_PER_ID * 3
    )
    missing_contact_l = any(
        row["technique"] == "contact010" and row["id_level"] == "L-ID" and row["trial_count"] == 0
        for row in summaries
    )
    qc.extend(
        [
            "",
            "Validation",
            f"Expected raw rows for 15 techniques x 3 IDs x 16 events: {EXPECTED_RAW_ROWS}; actual={len(rows)}",
            f"Technique x ID summary rows: {len(summaries)} (expected 45; empty cells are retained as NA)",
            f"Complete 48-event technique runs: {complete_techniques}/15",
            f"contact010 L-ID missing: {'yes' if missing_contact_l else 'no'} (the source file contains only IDs 2 and 3)",
            f"Starting Ball rows retained in primary scope: {len(start_audit)}",
            f"Missing trial trajectories: {sum(row['movement_distance_m'] is None for row in rows)}",
            f"Invalid/negative time values represented as missing: {sum(row['cancel_time_s'] is None for row in rows)} cancel-time fields; source sentinels remain auditable in raw files",
            "No Trigger comparison was pooled into this standalone Cancel analysis; Trigger uses a different 45-target scope.",
            "Cancel reasons and no-trigger reasons are summarized separately.",
            "Target entry count is the sum of in_target_times across the retained 16 events per ID; see target_entry_count_by_id.csv and target_entry_count_table.png.",
        ]
    )
    (output_dir / "quality_report.txt").write_text("\n".join(qc) + "\n", encoding="utf-8")

    manifest = {
        "subject_id": SUBJECT_ID,
        "input_dir": str(input_dir),
        "output_dir": str(output_dir),
        "event_scope": "all_available_cancel_records",
        "events_per_id_target": EVENTS_PER_ID,
        "nominal_raw_rows": EXPECTED_RAW_ROWS,
        "raw_rows_retained": len(rows),
        "summary_rows": len(summaries),
        "starting_ball_rows_retained": len(start_audit),
        "trigger_comparison_used": False,
        "notes": [
            "Unlike Magic-Tap Trigger, Cancel analysis retains the 16 events per logged ID, including Starting Balls.",
            "contact010 source data contains only 32 rows (IDs 2 and 3); its L-ID summary is NA.",
            "Target entry count is the sum of in_target_times; activation rate is reported separately.",
            "No raw outlier removal; M +/- 3 SD flags are sensitivity annotations.",
        ],
    }
    (output_dir / "analysis_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"Input: {input_dir}")
    print(f"Output: {output_dir}")
    print(f"Raw Cancel event rows retained: {len(rows)}")
    print(f"Technique x ID summaries: {len(summaries)}")
    print("Charts: 8 metric PNGs, 2 reason PNGs, 1 target-entry table PNG, and 1 composite PNG")


if __name__ == "__main__":
    main()
