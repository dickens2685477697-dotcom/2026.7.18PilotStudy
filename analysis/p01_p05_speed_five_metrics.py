"""Create the five Speed-family comparison metrics for P01 and P05.

Inputs are derived, non-destructive outputs of p01_p05_speed_frame_analysis.py.
The script writes a trial-level table, a condition summary, and one presentation-ready PNG.
"""

from __future__ import annotations

import sys
import shutil
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "analysis_outputs" / "p01_p05_speed_frame_20260924"
PLOT_DEPS = ROOT / "analysis" / "_plot_deps"
if PLOT_DEPS.exists():
    sys.path.insert(0, str(PLOT_DEPS))

import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter


TECHNIQUE_ORDER = ["Speed", "Speed-Dwell", "Speed-Release", "Speed-Direction"]
SIZE_ORDER = ["Large", "Medium", "Small"]
PARTICIPANT_ORDER = ["P01", "P05"]


def build_trial_table(trials: pd.DataFrame, frames: pd.DataFrame) -> pd.DataFrame:
    keys = ["participant", "run_id", "technique", "target_size", "trial_case"]
    frames = frames.sort_values(keys + ["frame_in_trial"]).copy()

    def path_length(group: pd.DataFrame) -> float:
        xyz = group[["indexLocX", "indexLocY", "indexLocZ"]].to_numpy(float)
        if len(xyz) < 2:
            return 0.0
        return float(np.linalg.norm(np.diff(xyz, axis=0), axis=1).sum())

    distances = (
        frames.groupby(keys, observed=True, sort=False)
        .apply(path_length, include_groups=False)
        .rename("movement_distance_m")
        .reset_index()
    )
    out = trials.merge(distances, on=keys, how="left", validate="one_to_one")
    out["trigger_trial_failed_first_entry"] = out["attempt_count_logged"] > 1
    cols = [
        "participant", "run_id", "run_order", "technique", "target_size", "id_code",
        "trial_case", "trial_order_within_technique", "ball_index", "trajectory_frames",
        "trial_total_time_s_exact", "movement_distance_m", "last_entry_to_trigger_s_exact",
        "attempt_count_logged", "trigger_trial_failed_first_entry",
        "first_entry_trigger_success_logged", "final_trigger_success",
    ]
    return out[cols].sort_values(
        ["participant", "technique", "id_code", "trial_case"], kind="stable"
    )


def summarize(trial: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (participant, technique, size), g in trial.groupby(
        ["participant", "technique", "target_size"], observed=True, sort=False
    ):
        rows.append(
            {
                "participant": participant,
                "technique": technique,
                "target_size": size,
                "n_trials": len(g),
                "task_completion_time_total_s": g["trial_total_time_s_exact"].sum(),
                "task_completion_time_median_s": g["trial_total_time_s_exact"].median(),
                "movement_distance_total_m": g["movement_distance_m"].sum(),
                "movement_distance_median_per_trial_m": g["movement_distance_m"].median(),
                "mean_trigger_time_s": g["last_entry_to_trigger_s_exact"].mean(),
                "median_trigger_time_s": g["last_entry_to_trigger_s_exact"].median(),
                "trigger_trial_failure_rate": g["trigger_trial_failed_first_entry"].mean(),
                "target_entries_total": g["attempt_count_logged"].sum(),
                "target_entries_median_per_trial": g["attempt_count_logged"].median(),
            }
        )
    out = pd.DataFrame(rows)
    out["technique"] = pd.Categorical(out["technique"], TECHNIQUE_ORDER, ordered=True)
    out["target_size"] = pd.Categorical(out["target_size"], SIZE_ORDER, ordered=True)
    return out.sort_values(["technique", "target_size", "participant"]).reset_index(drop=True)


def plot_summary(summary: pd.DataFrame, path: Path) -> None:
    metrics = [
        ("task_completion_time_total_s", "Task completion time", "Total across 16 trials (s)"),
        ("movement_distance_total_m", "Movement distance", "Total full trajectory (m)"),
        ("mean_trigger_time_s", "Mean trigger time", "Last entry to trigger (s)"),
        ("trigger_trial_failure_rate", "Trigger trial failure rate", "Trials with entries > 1"),
        ("target_entries_total", "Number of target entries", "Total entries (count)"),
    ]
    categories = [(tech, size) for tech in TECHNIQUE_ORDER for size in SIZE_ORDER]
    labels = [f"{tech}\n{size[0]}" for tech, size in categories]
    x = np.arange(len(categories), dtype=float)
    colors = {"P01": "#3B6EA8", "P05": "#E07A35"}
    width = 0.36

    fig, axes = plt.subplots(3, 2, figsize=(20, 14), constrained_layout=True)
    axes = axes.ravel()
    for ax, (metric, title, ylabel) in zip(axes, metrics):
        for j, participant in enumerate(PARTICIPANT_ORDER):
            vals = []
            for tech, size in categories:
                row = summary[
                    (summary["participant"] == participant)
                    & (summary["technique"] == tech)
                    & (summary["target_size"] == size)
                ]
                vals.append(float(row.iloc[0][metric]) if len(row) else np.nan)
            xpos = x + (j - 0.5) * width
            bars = ax.bar(xpos, vals, width=width, color=colors[participant], label=participant)
            for bar, value in zip(bars, vals):
                if not np.isfinite(value):
                    continue
                if metric == "trigger_trial_failure_rate":
                    label = f"{100 * value:.0f}%"
                elif metric == "target_entries_total":
                    label = f"{value:.0f}"
                elif metric in {"mean_trigger_time_s"}:
                    label = f"{value:.2f}"
                else:
                    label = f"{value:.1f}"
                ax.annotate(label, (bar.get_x() + bar.get_width() / 2, value),
                            xytext=(0, 3), textcoords="offset points", ha="center",
                            va="bottom", fontsize=7, rotation=90)
        ax.set_title(title, loc="left", fontsize=13, fontweight="bold")
        ax.set_ylabel(ylabel)
        ax.set_xticks(x, labels, fontsize=8)
        ax.grid(axis="y", alpha=0.25)
        ax.set_axisbelow(True)
        ax.margins(y=0.16)
        if metric == "trigger_trial_failure_rate":
            ax.yaxis.set_major_formatter(PercentFormatter(1.0))
            ax.set_ylim(0, max(1.0, ax.get_ylim()[1]))
        for split in [2.5, 5.5, 8.5]:
            ax.axvline(split, color="#C8CDD4", lw=0.8)
    axes[0].legend(frameon=False, ncol=2, loc="upper left")
    axes[-1].axis("off")
    axes[-1].text(
        0.02, 0.95,
        "Reading guide\n\n"
        "L/M/S = Large / Medium / Small.\n"
        "Each bar uses 16 completed trials.\n"
        "Failure = logged target-entry count > 1.\n"
        "Trigger time is the exact logged time from the last entry to trigger.\n"
        "Movement distance is recomputed from all recorded fingertip positions.\n\n"
        "P01/P05 are individual-case descriptions; bars are not population estimates.",
        va="top", fontsize=12, linespacing=1.45,
        bbox={"boxstyle": "round,pad=0.6", "facecolor": "#F4F6F8", "edgecolor": "#D2D7DE"},
    )
    fig.suptitle(
        "P01 vs P05 — Speed-family five-metric comparison",
        fontsize=18, fontweight="bold"
    )
    fig.savefig(path, dpi=220, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def main() -> None:
    trials = pd.read_csv(OUT / "trial_level_metrics.csv")
    frames = pd.read_csv(OUT / "derived_aligned_frames.csv.gz", compression="gzip")
    trial = build_trial_table(trials, frames)
    summary = summarize(trial)

    trial.to_csv(OUT / "speed_five_metrics_trial_level.csv", index=False, encoding="utf-8-sig", float_format="%.8g")
    summary.to_csv(OUT / "speed_five_metrics_condition_summary.csv", index=False, encoding="utf-8-sig", float_format="%.8g")
    plot_summary(summary, OUT / "fig07_speed_five_metrics_p01_p05.png")
    shutil.copy2(Path(__file__), OUT / "p01_p05_speed_five_metrics.py")
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
