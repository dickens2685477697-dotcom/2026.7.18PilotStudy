#!/usr/bin/env python3
"""Analyze Subject 1 Trigger data using the study's 48-event scope.

Each technique contributes 16 logged events for each ID condition.  The
Starting Ball is retained in the primary scope.  A Trigger trial is marked
failed when ``in_target_times > 1``.  This script produces a standalone
Subject 1 output directory without pooling another participant.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any, Sequence

import subject2_trigger_analysis as base
import subjects1_5_trigger_48_combined as shared


SUBJECT_ID = 1
ID_ORDER = ["L-ID", "M-ID", "H-ID"]


def parse_args() -> argparse.Namespace:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--subject-id",
        type=int,
        default=SUBJECT_ID,
        help="Participant folder ID written to outputs.",
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=root / "1" / "Trigger",
        help="Subject 1 Trigger directory.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=root / "analysis_outputs" / "subject1_trigger_48",
        help="Standalone output directory.",
    )
    return parser.parse_args()


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


def normalize_for_base_charts(
    summaries: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Map 48-event summary names to the existing Pillow chart interface."""

    normalized: list[dict[str, Any]] = []
    for source in summaries:
        row = dict(source)
        row.update(
            {
                "trial_count": source["raw_48_trial_count"],
                "trigger_failure_n": source["raw_48_failure_n"],
                "trigger_success_n": source["raw_48_success_n"],
                "trigger_failure_rate": source["raw_48_failure_rate"],
                "in_target_entries_total": source["raw_48_entry_total"],
                "task_completion_time_s": source["task_completion_time_48_s"],
                "movement_distance_m": source["movement_distance_48_m"],
                "trigger_time_valid_n": source["trigger_time_valid_n_48"],
                "trigger_time_mean_s": source["trigger_time_mean_48_s"],
                "trigger_time_median_s": source["trigger_time_median_48_s"],
                "trigger_time_sd_s": source["trigger_time_sd_48_s"],
                "trigger_time_min_s": source["trigger_time_min_48_s"],
                "trigger_time_max_s": source["trigger_time_max_48_s"],
            }
        )
        normalized.append(row)
    return normalized


def render_charts(
    output_dir: Path,
    summaries: Sequence[dict[str, Any]],
    technique_order: Sequence[str],
) -> None:
    normalized = normalize_for_base_charts(summaries)
    base.render_charts(
        output_dir,
        normalized,
        technique_order,
        subject_label="Subject 1 — 48-event scope",
        composite_filename="subject1_trigger_48_metrics_by_id.png",
        error_keys={"trigger_time_mean_s": "trigger_time_sd_s"},
    )
    # Keep the 48-event scope explicit in each standalone filename.
    rename_map = {
        "task_completion_time_by_id.png": "task_completion_time_48_by_id.png",
        "movement_distance_by_id.png": "movement_distance_48_by_id.png",
        "trigger_time_by_id.png": "trigger_time_mean_48_by_id.png",
        "trigger_failure_rate_by_id.png": "trigger_failure_rate_48_by_id.png",
        "target_entries_by_id.png": "target_entries_48_by_id.png",
    }
    for old_name, new_name in rename_map.items():
        old_path = output_dir / old_name
        new_path = output_dir / new_name
        if old_path.exists():
            old_path.replace(new_path)


def render_entry_table(
    output_dir: Path,
    summaries: Sequence[dict[str, Any]],
    technique_order: Sequence[str],
) -> None:
    width, row_height = 2100, 66
    top = 190
    height = top + row_height * (len(technique_order) + 1) + 125
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
        "Target Entry Count — Subject 1, 48-event scope",
        font=title_font,
        fill=dark,
    )
    draw.text(
        (72, 103),
        "Cell = sum of in_target_times over 16 retained events per ID.",
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
    draw.rectangle(
        (x0, y0, right, y0 + row_height), fill=(225, 231, 239), outline=line, width=2
    )
    for x, col_width, header in zip(x_positions, col_widths, headers):
        parts = header.split("\n")
        if len(parts) == 1:
            base.text_centered(
                draw,
                (x + col_width / 2, y0 + row_height / 2),
                header,
                header_font,
                dark,
            )
        else:
            base.text_centered(
                draw,
                (x + col_width / 2, y0 + 22),
                parts[0],
                header_font,
                dark,
            )
            base.text_centered(
                draw,
                (x + col_width / 2, y0 + 46),
                parts[1],
                small_font,
                muted,
            )

    by_key = {(row["technique"], row["id_level"]): row for row in summaries}
    for index, technique in enumerate(technique_order):
        y = top + row_height * (index + 1)
        fill = (255, 255, 255) if index % 2 == 0 else (244, 247, 250)
        draw.rectangle((x0, y, right, y + row_height), fill=fill, outline=line, width=1)
        base.text_centered(
            draw,
            (x_positions[0] + col_widths[0] / 2, y + row_height / 2),
            f"T{index + 1:02d}",
            cell_font,
            dark,
        )
        base.text_centered(
            draw,
            (x_positions[1] + col_widths[1] / 2, y + row_height / 2),
            technique,
            cell_font,
            dark,
        )
        for id_index, id_level in enumerate(ID_ORDER):
            value = by_key[(technique, id_level)]["raw_48_entry_total"]
            column = id_index + 2
            base.text_centered(
                draw,
                (x_positions[column] + col_widths[column] / 2, y + row_height / 2),
                f"{int(value)}",
                cell_font,
                dark,
            )

    draw.text(
        (72, height - 75),
        "T01–T15 follow the acquisition order; Starting Ball is included.",
        font=subtitle_font,
        fill=muted,
    )
    image.save(output_dir / "target_entry_count_table_48.png", format="PNG", optimize=True)


def build_qc(
    base_qc: Sequence[str],
    trials: Sequence[dict[str, Any]],
    summaries: Sequence[dict[str, Any]],
    technique_order: Sequence[str],
    extras: Sequence[dict[str, Any]],
    run_qc: Sequence[dict[str, Any]],
) -> list[str]:
    qc = list(base_qc)
    qc.extend(
        [
            "",
            "Validation",
            f"Expected trial rows: 15 x 3 x 16 = 720; actual={len(trials)}",
            f"Expected technique-by-ID rows: 15 x 3 = 45; actual={len(summaries)}",
            f"Complete selected runs: {sum(row['selected_48_rows'] == 48 for row in run_qc)}/{len(run_qc)}",
            f"Extra raw rows audited/excluded: {len(extras)}",
            f"Missing trial trajectories: {sum(row['movement_distance_m'] is None for row in trials)}",
            f"Invalid Trigger Time values excluded: {sum(row['trigger_time_s'] is None for row in trials)}",
            "Failure rule: in_target_times > 1 means the Trigger trial failed; in_target_times <= 1 means successful.",
            "Raw-48 scope includes Starting Ball. Formal-45 values are retained only as a comparison.",
        ]
    )
    failure_n = sum(bool(row["trigger_failed"]) for row in trials)
    qc.append(f"Raw-48 Trigger failures: {failure_n}/{len(trials)} ({failure_n / len(trials):.1%})")
    for id_level in ID_ORDER:
        id_trials = [row for row in trials if row["id_level"] == id_level]
        id_failure_n = sum(bool(row["trigger_failed"]) for row in id_trials)
        qc.append(
            f"{id_level} Trigger failures: {id_failure_n}/{len(id_trials)} "
            f"({id_failure_n / len(id_trials):.1%})"
        )
    formal_rows = [row for row in trials if not row["is_start_ball"]]
    formal_failure_n = sum(bool(row["trigger_failed"]) for row in formal_rows)
    qc.append(
        f"Formal-45 comparison: {formal_failure_n}/{len(formal_rows)} "
        f"({formal_failure_n / len(formal_rows):.1%})"
    )
    qc.extend(
        [
            "ID plotting order: L-ID (2.713), M-ID (3.459), H-ID (4.605)",
            "No outlier removal was applied.",
            "Task Error Rate and Throughput were not calculated.",
            "This is a Trigger-specific multi-entry failure rate, not Task Error Rate.",
            "Technique acquisition order:",
        ]
    )
    qc.extend(f"{index + 1:02d}. {name}" for index, name in enumerate(technique_order))
    return qc


def main() -> None:
    args = parse_args()
    input_dir = args.input_dir.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    trials, extras, run_qc, base_qc, technique_order = shared.collect_subject(
        input_dir, args.subject_id
    )
    summaries = shared.summarize_subject(trials, args.subject_id, technique_order)

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
    summary_fields = [
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
    failure_fields = [
        "subject_id",
        "technique",
        "id_level",
        "id_bits",
        "layout_diameter_m",
        "raw_48_trial_count",
        "raw_48_failure_n",
        "raw_48_success_n",
        "raw_48_failure_rate",
        "formal_45_trial_count",
        "formal_45_failure_n",
        "formal_45_failure_rate",
    ]
    entry_fields = [
        "subject_id",
        "technique",
        "id_level",
        "id_bits",
        "raw_48_trial_count",
        "raw_48_entry_total",
        "raw_48_entry_mean_per_event",
    ]
    qc_fields = list(run_qc[0].keys()) if run_qc else []

    write_csv(output_dir / "trial_metrics_48.csv", trials, trial_fields)
    write_csv(output_dir / "extra_raw_event_audit.csv", extras, trial_fields + ["extra_reason"])
    write_csv(output_dir / "id_technique_metrics_48.csv", summaries, summary_fields)
    write_csv(output_dir / "trigger_failure_rate_48_by_id.csv", summaries, failure_fields)
    write_csv(output_dir / "target_entry_count_48_by_id.csv", summaries, entry_fields)
    write_csv(output_dir / "run_qc.csv", run_qc, qc_fields)
    render_charts(output_dir, summaries, technique_order)
    render_entry_table(output_dir, summaries, technique_order)

    qc = build_qc(base_qc, trials, summaries, technique_order, extras, run_qc)
    (output_dir / "quality_report.txt").write_text("\n".join(qc) + "\n", encoding="utf-8")

    formal_rows = [row for row in trials if not row["is_start_ball"]]
    raw_failure_n = sum(bool(row["trigger_failed"]) for row in trials)
    formal_failure_n = sum(bool(row["trigger_failed"]) for row in formal_rows)
    manifest = {
        "subject_id": args.subject_id,
        "input_dir": str(input_dir),
        "output_dir": str(output_dir),
        "primary_scope": "raw_48_selected_including_starting_ball",
        "events_per_id": 16,
        "selected_rows": len(trials),
        "extra_rows_excluded": len(extras),
        "summary_cells": len(summaries),
        "raw_48_failure_n": raw_failure_n,
        "raw_48_failure_rate": raw_failure_n / len(trials),
        "formal_45_failure_n": formal_failure_n,
        "formal_45_failure_rate": formal_failure_n / len(formal_rows),
        "rule": "in_target_times > 1",
        "task_error_rate_calculated": False,
        "throughput_calculated": False,
    }
    (output_dir / "analysis_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Input: {input_dir}")
    print(f"Output: {output_dir}")
    print(f"Selected 48-event rows: {len(trials)}")
    print(f"Raw-48 failures: {raw_failure_n}/{len(trials)} ({raw_failure_n / len(trials):.1%})")
    print(f"Technique x ID rows: {len(summaries)}")


if __name__ == "__main__":
    main()
