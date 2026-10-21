"""45-degree 3D near-target trajectories for P01/P05 Speed-family trials."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "analysis_outputs" / "p01_p05_speed_frame_20260924"
PLOT_DEPS = ROOT / "analysis" / "_plot_deps"
if PLOT_DEPS.exists():
    sys.path.insert(0, str(PLOT_DEPS))

import matplotlib.pyplot as plt


TECHNIQUES = ["Speed", "Speed-Dwell", "Speed-Release", "Speed-Direction"]
SIZES = ["Large", "Medium", "Small"]
PARTICIPANTS = ["P01", "P05"]
COLORS = {"P01": "#326B9B", "P05": "#D66A31"}


def rotation_to_x(vector: np.ndarray) -> np.ndarray:
    """Return a Rodrigues rotation taking vector onto the positive x axis."""
    v = vector / max(np.linalg.norm(vector), 1e-12)
    target = np.array([1.0, 0.0, 0.0])
    cross = np.cross(v, target)
    s = np.linalg.norm(cross)
    c = float(np.dot(v, target))
    if s < 1e-10:
        return np.eye(3) if c > 0 else np.diag([-1.0, -1.0, 1.0])
    k = np.array([[0, -cross[2], cross[1]], [cross[2], 0, -cross[0]], [-cross[1], cross[0], 0]])
    return np.eye(3) + k + k @ k * ((1 - c) / (s * s))


def aligned_segment(row: pd.Series, frames: pd.DataFrame, before_entry: int = 15) -> tuple[np.ndarray, int]:
    g = frames[
        (frames["participant"] == row.participant)
        & (frames["run_id"] == row.run_id)
        & (frames["technique"] == row.technique)
        & (frames["target_size"] == row.target_size)
        & (frames["trial_case"] == row.trial_case)
    ].sort_values("frame_in_trial")
    center = np.array([row.target_center_x, row.target_center_y, row.target_center_z], float)
    rel = (g[["indexLocX", "indexLocY", "indexLocZ"]].to_numpy(float) - center) / float(row.target_radius_m)
    entry = int(row.first_entry_frame)
    if entry < 0 or len(rel) == 0:
        return np.empty((0, 3)), 0
    prior = max(0, entry - 4)
    incoming_outward = rel[prior] - rel[entry]
    rel = rel @ rotation_to_x(incoming_outward).T
    start = max(0, entry - before_entry)
    stop = min(len(rel), int(row.trigger_frame) + 1)
    return rel[start:stop], start


def choose_representatives(trials: pd.DataFrame) -> pd.DataFrame:
    chosen = []
    for participant in PARTICIPANTS:
        for size in SIZES:
            for technique in TECHNIQUES:
                g = trials[
                    (trials.participant == participant)
                    & (trials.technique == technique)
                    & (trials.target_size == size)
                    & trials.first_entry_trigger_success_logged
                    & (trials.first_entry_frame >= 0)
                ].copy()
                if not len(g):
                    g = trials[
                        (trials.participant == participant)
                        & (trials.technique == technique)
                        & (trials.target_size == size)
                        & (trials.first_entry_frame >= 0)
                    ].copy()
                    score_col = "trial_total_time_s_exact"
                else:
                    score_col = "first_entry_to_trigger_s_exact_when_single_entry"
                target = g[score_col].median()
                row = g.loc[(g[score_col] - target).abs().idxmin()].copy()
                row["representative_basis"] = score_col
                chosen.append(row)
    return pd.DataFrame(chosen)


def draw_sphere(ax) -> None:
    u, v = np.mgrid[0 : 2 * np.pi : 32j, 0 : np.pi : 16j]
    x = np.cos(u) * np.sin(v)
    y = np.sin(u) * np.sin(v)
    z = np.cos(v)
    ax.plot_wireframe(x, y, z, rstride=2, cstride=2, color="#7A8796", alpha=0.20, linewidth=0.45)


def main() -> None:
    trials = pd.read_csv(OUT / "trial_level_metrics.csv")
    frames = pd.read_csv(OUT / "derived_aligned_frames.csv.gz", compression="gzip")
    reps = choose_representatives(trials)

    fig = plt.figure(figsize=(20, 27))
    legend_handles = None
    for ri, (participant, size) in enumerate([(p, s) for p in PARTICIPANTS for s in SIZES]):
        for ci, technique in enumerate(TECHNIQUES):
            ax = fig.add_subplot(6, 4, ri * 4 + ci + 1, projection="3d")
            condition = trials[
                (trials.participant == participant)
                & (trials.technique == technique)
                & (trials.target_size == size)
            ]
            # All trials provide distributional context; only the near-target segment is shown.
            for _, row in condition.iterrows():
                rel, _ = aligned_segment(row, frames)
                if len(rel):
                    ax.plot(rel[:, 0], rel[:, 1], rel[:, 2], color=COLORS[participant], alpha=0.10, lw=0.8)

            row = reps[
                (reps.participant == participant)
                & (reps.technique == technique)
                & (reps.target_size == size)
            ].iloc[0]
            rel, start = aligned_segment(row, frames)
            ax.plot(rel[:, 0], rel[:, 1], rel[:, 2], color=COLORS[participant], lw=2.8, label="Representative trajectory")
            for idx, color, marker, label in [
                (int(row.first_entry_frame), "#087F5B", "o", "Entry"),
                (int(row.threshold_frame), "#7048E8", "^", "Threshold crossing"),
                (int(row.trigger_frame), "#F08C00", "X", "Trigger"),
            ]:
                local = idx - start
                if 0 <= local < len(rel):
                    ax.scatter(*rel[local], color=color, marker=marker, s=55, depthshade=False, label=label)

            draw_sphere(ax)
            ax.view_init(elev=30, azim=45)
            ax.set_xlim(-2.2, 2.2)
            ax.set_ylim(-2.2, 2.2)
            ax.set_zlim(-2.2, 2.2)
            ax.set_box_aspect((1, 1, 1))
            ax.set_xticks([-2, -1, 0, 1, 2])
            ax.set_yticks([-2, -1, 0, 1, 2])
            ax.set_zticks([-2, -1, 0, 1, 2])
            ax.tick_params(labelsize=7, pad=0)
            ax.set_xlabel("Aligned x / R", fontsize=8, labelpad=2)
            ax.set_ylabel("y / R", fontsize=8, labelpad=2)
            ax.set_zlabel("z / R", fontsize=8, labelpad=2)
            ax.set_title(
                f"{participant} · {technique} · {size}\n"
                f"Representative trial {int(row.trial_case)}; 16 trials in light lines",
                fontsize=10, fontweight="bold", pad=5,
            )
            ax.grid(True, alpha=0.18)
            if legend_handles is None:
                legend_handles = ax.get_legend_handles_labels()

    if legend_handles:
        fig.legend(legend_handles[0], legend_handles[1], loc="lower center", ncol=4, frameon=False, fontsize=11)
    fig.suptitle(
        "P01 vs P05 Speed-family trajectories — center/radius normalized, entry direction aligned\n"
        "Camera: azimuth 45°, elevation 30°; sphere boundary = 1 target radius",
        fontsize=18, fontweight="bold", y=0.995,
    )
    fig.text(
        0.5, 0.018,
        "Thick line = condition-representative first-entry-success trial; light lines = all 16 trials. "
        "Trajectory window: 15 nominal frames before first entry through trigger. Threshold marker is shown when the "
        "sphere-based reconstruction contains a crossing; no post-trigger frames are inferred.",
        ha="center", fontsize=10,
    )
    fig.subplots_adjust(left=0.03, right=0.98, top=0.965, bottom=0.045, wspace=0.03, hspace=0.15)
    fig.savefig(OUT / "fig08_speed_trajectories_3d_45deg.png", dpi=190, bbox_inches="tight", facecolor="white")
    plt.close(fig)

    cols = [
        "participant", "technique", "target_size", "run_id", "trial_case",
        "trial_order_within_technique", "first_entry_trigger_success_logged",
        "trial_total_time_s_exact", "first_entry_to_trigger_s_exact_when_single_entry",
        "attempt_count_logged", "first_entry_frame", "threshold_frame", "trigger_frame",
        "representative_basis",
    ]
    reps[cols].to_csv(OUT / "fig08_representative_trials.csv", index=False, encoding="utf-8-sig")
    shutil.copy2(Path(__file__), OUT / "p01_p05_speed_3d_45deg.py")
    print(f"wrote {len(reps)} representative conditions")


if __name__ == "__main__":
    main()
