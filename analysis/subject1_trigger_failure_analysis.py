#!/usr/bin/env python3
"""Compute Subject 1 Trigger trial failure under the multi-entry rule.

The study-specific rule is explicit: a Trigger trial is failed when
``in_target_times > 1``.  This companion analysis keeps both denominators
auditable:

* raw-48 scope: all 16 logged events per ID, including Starting Ball;
* formal-45 scope: the existing Trigger convention, excluding Starting Ball.

The raw-48 result is the primary result when comparing with the Subject 1
Cancel analysis, which also retains Starting Balls.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import subject2_trigger_analysis as base


SUBJECT_ID = 1
EVENTS_PER_ID_RAW = 16
EVENTS_PER_ID_FORMAL = 15
EXPECTED_TECHNIQUES = 15
EXPECTED_RAW_ROWS = EXPECTED_TECHNIQUES * 3 * EVENTS_PER_ID_RAW
ID_BY_CODE = {1: "L-ID", 2: "M-ID", 3: "H-ID"}
ID_ORDER = ["L-ID", "M-ID", "H-ID"]


def parse_args() -> argparse.Namespace:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--subject-id", type=int, default=SUBJECT_ID, help="Subject identifier."
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=root / "1" / "Trigger",
        help="Subject Trigger directory containing run folders.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=root / "analysis_outputs" / "subject1_trigger",
        help="Output directory shared with the main Trigger analysis.",
    )
    return parser.parse_args()


def make_raw_record(
    row: list[str],
    subject_id: int,
    run_id: str,
    technique: str,
    distances: dict[int, float],
    sample_counts: dict[int, int],
) -> dict[str, Any]:
    case = int(row[base.TIME_INDEX["case"]])
    logged_id_code = int(row[base.TIME_INDEX["logged_id_code"]])
    in_target_times_float = base.finite_float(row[base.TIME_INDEX["in_target_times"]])
    if in_target_times_float is None or in_target_times_float < 0:
        raise ValueError(f"{run_id} Case {case}: invalid inTargetTimes")
    in_target_times = int(in_target_times_float)
    start_ball = int(row[base.TIME_INDEX["start_ball"]])
    ball_index = int(row[base.TIME_INDEX["ball_index"]])
    points = base.target_points(row)
    diameter_m = base.layout_diameter(points)
    id_level, id_bits = base.match_id(diameter_m)
    trigger_time = base.finite_float(row[base.TIME_INDEX["trigger_time_s"]])
    if trigger_time is not None and trigger_time < 0:
        trigger_time = None
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
        "used_time_s": base.finite_float(row[base.TIME_INDEX["used_time_s"]]),
        "trigger_time_s": trigger_time,
        "movement_distance_m": distances.get(case),
        "trajectory_sample_count": sample_counts.get(case, 0),
        "raw_data_length": len(row),
        "raw_row_json": json.dumps(row, ensure_ascii=False, separators=(",", ":")),
    }


def collect_raw_events(
    input_dir: Path, subject_id: int
) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    time_files = sorted(input_dir.glob("*/*-time.csv"))
    if not time_files:
        raise FileNotFoundError(f"No *-time.csv files under {input_dir}")
    rows: list[dict[str, Any]] = []
    qc: list[str] = [
        f"Subject folder ID: {subject_id}",
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
        technique_values = {
            row[base.TIME_INDEX["technique"]].strip() for row in raw_rows
        }
        if len(technique_values) != 1:
            raise ValueError(f"{run_id}: multiple techniques {sorted(technique_values)}")
        technique = next(iter(technique_values))
        techniques.append(technique)

        case_values = [int(row[base.TIME_INDEX["case"]]) for row in raw_rows]
        if case_values != list(range(1, len(raw_rows) + 1)):
            raise ValueError(f"{run_id}: Case values are not sequential from 1")
        distances, sample_counts = base.trajectory_distances(trajectory_path)
        records = [
            make_raw_record(
                row,
                subject_id,
                run_id,
                technique,
                distances,
                sample_counts,
            )
            for row in raw_rows
        ]
        by_id: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for record in records:
            by_id[record["logged_id_code"]].append(record)
        if set(by_id) != {1, 2, 3}:
            raise ValueError(f"{run_id}: expected ID codes 1,2,3, found {sorted(by_id)}")
        for logged_id_code in (1, 2, 3):
            block = sorted(by_id[logged_id_code], key=lambda item: item["case"])
            if len(block) != EVENTS_PER_ID_RAW:
                raise ValueError(
                    f"{run_id} ID{logged_id_code}: expected {EVENTS_PER_ID_RAW} raw events, found {len(block)}"
                )
            for position, record in enumerate(block, start=1):
                record["position_within_id"] = position
        rows.extend(records)
        qc.append(
            f"{run_id}: mode={technique}, header_columns={len(header)}, "
            f"data_columns={sorted({len(row) for row in raw_rows})}, "
            f"raw_rows={len(records)}, starts_retained={sum(record['is_start_ball'] for record in records)}"
        )

    expected = set(base.CANONICAL_TECHNIQUE_ORDER)
    observed = set(techniques)
    if len(techniques) != len(observed) or observed != expected:
        raise ValueError(
            f"Technique set mismatch: missing={sorted(expected - observed)}, "
            f"extra={sorted(observed - expected)}"
        )
    return rows, qc, list(base.CANONICAL_TECHNIQUE_ORDER)


def build_summaries(
    rows: list[dict[str, Any]], technique_order: list[str], subject_id: int
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(row["technique"], row["id_level"])].append(row)
    summaries: list[dict[str, Any]] = []
    for technique in technique_order:
        for id_level in ID_ORDER:
            group = sorted(
                grouped[(technique, id_level)], key=lambda item: item["case"]
            )
            if len(group) != EVENTS_PER_ID_RAW:
                raise ValueError(
                    f"{technique} {id_level}: expected {EVENTS_PER_ID_RAW} raw events, found {len(group)}"
                )
            formal = [row for row in group if not row["is_start_ball"]]
            raw_failed = sum(row["trigger_failed"] for row in group)
            formal_failed = sum(row["trigger_failed"] for row in formal)
            summaries.append(
                {
                    "subject_id": subject_id,
                    "technique": technique,
                    "id_level": id_level,
                    "id_bits": group[0]["id_bits"],
                    "layout_diameter_m": group[0]["layout_diameter_m"],
                    "raw_48_trial_count": len(group),
                    "raw_48_failure_n": raw_failed,
                    "raw_48_success_n": len(group) - raw_failed,
                    "raw_48_failure_rate": raw_failed / len(group),
                    "formal_45_trial_count": len(formal),
                    "formal_45_failure_n": formal_failed,
                    "formal_45_success_n": len(formal) - formal_failed,
                    "formal_45_failure_rate": formal_failed / len(formal)
                    if formal
                    else None,
                    "raw_48_entry_total": sum(
                        row["in_target_times"] for row in group
                    ),
                    "formal_45_entry_total": sum(
                        row["in_target_times"] for row in formal
                    ),
                }
            )
    return summaries


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
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


def render_failure_chart(output_dir: Path, summaries: list[dict[str, Any]]) -> None:
    image = base.Image.new("RGB", (2400, 1600), (249, 250, 252))
    draw = base.ImageDraw.Draw(image)
    base.draw_bar_panel(
        draw,
        (90, 70, 2310, 1510),
        summaries,
        list(base.CANONICAL_TECHNIQUE_ORDER),
        "raw_48_failure_rate",
        "Trigger Trial Failure Rate — Raw 48-event scope — Subject 1",
        "Failure rate",
        None,
        True,
        large=True,
    )
    image.save(output_dir / "trigger_failure_rate_48_by_id.png", format="PNG", optimize=True)


def main() -> None:
    args = parse_args()
    input_dir = args.input_dir.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    rows, qc, technique_order = collect_raw_events(input_dir, args.subject_id)
    summaries = build_summaries(rows, technique_order, args.subject_id)
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
        "formal_45_success_n",
        "formal_45_failure_rate",
        "raw_48_entry_total",
        "formal_45_entry_total",
    ]
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
        "raw_data_length",
        "raw_row_json",
    ]
    write_csv(output_dir / "trigger_failure_rate_48_by_id.csv", summaries, failure_fields)
    write_csv(output_dir / "trigger_failure_trial_metrics_48.csv", rows, trial_fields)
    render_failure_chart(output_dir, summaries)

    raw_failure_n = sum(row["trigger_failed"] for row in rows)
    formal_rows = [row for row in rows if not row["is_start_ball"]]
    formal_failure_n = sum(row["trigger_failed"] for row in formal_rows)
    qc.extend(
        [
            "",
            "Validation",
            f"Raw-48 events retained: {len(rows)} (expected {EXPECTED_RAW_ROWS})",
            f"Formal-45 events available for comparison: {len(formal_rows)} (expected {EXPECTED_TECHNIQUES * 3 * EVENTS_PER_ID_FORMAL})",
            "Failure rule: in_target_times > 1 => failed Trigger trial; in_target_times <= 1 => successful Trigger trial.",
            f"Raw-48 failure rate: {raw_failure_n}/{len(rows)} ({raw_failure_n / len(rows):.1%})",
            f"Formal-45 failure rate: {formal_failure_n}/{len(formal_rows)} ({formal_failure_n / len(formal_rows):.1%})",
            "Raw-48 scope includes Starting Ball; formal-45 scope excludes Starting Ball.",
            "This is a Trigger-specific multi-entry failure rate, not Task Error Rate.",
        ]
    )
    (output_dir / "trigger_failure_48_quality_report.txt").write_text(
        "\n".join(qc) + "\n", encoding="utf-8"
    )
    manifest = {
        "subject_id": args.subject_id,
        "input_dir": str(input_dir),
        "output_dir": str(output_dir),
        "primary_scope": "raw_48_including_starting_ball",
        "raw_48_rows": len(rows),
        "raw_48_failure_n": raw_failure_n,
        "raw_48_failure_rate": raw_failure_n / len(rows),
        "formal_45_rows": len(formal_rows),
        "formal_45_failure_n": formal_failure_n,
        "formal_45_failure_rate": formal_failure_n / len(formal_rows),
        "rule": "in_target_times > 1",
    }
    (output_dir / "trigger_failure_48_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Input: {input_dir}")
    print(f"Output: {output_dir}")
    print(f"Raw-48 failures: {raw_failure_n}/{len(rows)} ({raw_failure_n / len(rows):.1%})")
    print(
        f"Formal-45 failures: {formal_failure_n}/{len(formal_rows)} ({formal_failure_n / len(formal_rows):.1%})"
    )


if __name__ == "__main__":
    main()
