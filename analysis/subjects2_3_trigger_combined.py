#!/usr/bin/env python3
"""Combine Subjects 1, 2, and 3 Trigger metrics with equal subject weighting."""

from __future__ import annotations

import statistics
from collections import defaultdict
from pathlib import Path

from subject2_trigger_analysis import (
    ID_ORDER,
    build_qc,
    collect_trials,
    render_charts,
    summarize,
    write_csv,
)


METRICS = [
    (
        "task_completion_time_s",
        "task_completion_time_between_subject_sd_s",
    ),
    (
        "movement_distance_m",
        "movement_distance_between_subject_sd_m",
    ),
    (
        "trigger_time_mean_s",
        "trigger_time_between_subject_sd_s",
    ),
    (
        "in_target_entries_total",
        "in_target_entries_between_subject_sd",
    ),
]

SUBJECT_IDS = (1, 2, 3)


def combine_subject_summaries(
    summaries: list[dict], technique_order: list[str]
) -> list[dict]:
    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in summaries:
        grouped[(row["technique"], row["id_level"])].append(row)

    combined: list[dict] = []
    for technique in technique_order:
        for id_level in ID_ORDER:
            rows = sorted(
                grouped[(technique, id_level)], key=lambda row: row["subject_id"]
            )
            if [row["subject_id"] for row in rows] != list(SUBJECT_IDS):
                raise ValueError(
                    f"{technique} {id_level}: expected Subjects {SUBJECT_IDS}"
                )
            output = {
                "technique": technique,
                "id_level": id_level,
                "id_bits": rows[0]["id_bits"],
                "layout_diameter_m": rows[0]["layout_diameter_m"],
                "subject_count": len(SUBJECT_IDS),
            }
            for metric, sd_key in METRICS:
                values = [float(row[metric]) for row in rows]
                for subject_id, value in zip(SUBJECT_IDS, values):
                    output[f"{metric}_subject{subject_id}"] = value
                output[metric] = statistics.mean(values)
                output[sd_key] = statistics.stdev(values)
            combined.append(output)
    return combined


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    output_dir = root / "analysis_outputs" / "subjects1_2_3_trigger"
    output_dir.mkdir(parents=True, exist_ok=True)

    all_trials: list[dict] = []
    all_summaries: list[dict] = []
    qc_sections: list[str] = []
    technique_order: list[str] | None = None

    for subject_id in SUBJECT_IDS:
        input_dir = root / str(subject_id) / (
            "trigger" if subject_id == 1 else "Trigger"
        )
        trials, base_qc, order = collect_trials(
            input_dir, subject_id
        )
        summaries = summarize(trials, order, subject_id)
        subject_qc = build_qc(base_qc, trials, summaries, order)
        qc_sections.append(
            f"===== Subject {subject_id} =====\n" + "\n".join(subject_qc)
        )
        if technique_order is None:
            technique_order = order
        elif set(order) != set(technique_order):
            raise ValueError(
                f"Subjects {SUBJECT_IDS} do not contain the same techniques"
            )
        all_trials.extend(trials)
        all_summaries.extend(summaries)

    assert technique_order is not None
    combined = combine_subject_summaries(all_summaries, technique_order)

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
        "used_time_s",
        "trigger_time_s",
        "movement_distance_m",
        "trajectory_sample_count",
    ]
    subject_summary_fields = [
        "subject_id",
        "technique",
        "id_level",
        "id_bits",
        "layout_diameter_m",
        "trial_count",
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
    combined_fields = [
        "technique",
        "id_level",
        "id_bits",
        "layout_diameter_m",
        "subject_count",
    ]
    for metric, sd_key in METRICS:
        combined_fields.extend(
            [f"{metric}_subject{subject_id}" for subject_id in SUBJECT_IDS]
        )
        combined_fields.extend([metric, sd_key])

    write_csv(output_dir / "combined_trial_metrics.csv", all_trials, trial_fields)
    write_csv(
        output_dir / "subject_id_technique_metrics.csv",
        all_summaries,
        subject_summary_fields,
    )
    write_csv(
        output_dir / "combined_technique_metrics.csv",
        combined,
        combined_fields,
    )

    render_charts(
        output_dir,
        combined,
        technique_order,
        subject_label="Subjects 1-3 Mean (n=3)",
        composite_filename="subjects1_2_3_mean_metrics_by_id.png",
        error_keys={metric: sd_key for metric, sd_key in METRICS},
    )

    qc_sections.append(
        "===== Combined validation =====\n"
        f"Combined formal trials: {len(all_trials)} (expected 2025)\n"
        f"Subject-level technique x ID rows: {len(all_summaries)} (expected 135)\n"
        f"Combined technique x ID rows: {len(combined)} (expected 45)\n"
        "Aggregation: each subject summarized first, then Subjects 1, 2, and 3 "
        "received equal weight.\n"
        "Error bars: sample SD between the three subject-level values.\n"
        "No inferential statistics were performed because n=3."
    )
    (output_dir / "quality_report.txt").write_text(
        "\n\n".join(qc_sections) + "\n", encoding="utf-8"
    )

    print(f"Output: {output_dir}")
    print(f"Combined formal trials: {len(all_trials)}")
    print(f"Subject-level rows: {len(all_summaries)}")
    print(f"Combined rows: {len(combined)}")
    print("Charts: 5 PNG files")


if __name__ == "__main__":
    main()
