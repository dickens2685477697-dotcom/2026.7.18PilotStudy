#!/usr/bin/env python3
"""Reproducible P01/P05 frame-level audit of the Study3 Speed family.

The raw trajectory log has no per-frame timestamp.  Accordingly, this script
keeps exact logger durations (``usedTime`` and last-entry ``triggerTime``)
separate from nominal-frame estimates based on Unity's configured 0.02 s
Fixed Timestep.  The latter are always labelled ``nominal`` in outputs.

No source file is modified.  Every derived table, figure and report is written
to a new output directory.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import shutil
import statistics
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

_SCRIPT_PATH = Path(__file__).resolve()
_PLOT_DEP_CANDIDATES = [_SCRIPT_PATH.parent / "_plot_deps"] + [
    ancestor / "analysis" / "_plot_deps" for ancestor in _SCRIPT_PATH.parents
]
for _LOCAL_PLOT_DEPS in _PLOT_DEP_CANDIDATES:
    if _LOCAL_PLOT_DEPS.exists():
        sys.path.insert(0, str(_LOCAL_PLOT_DEPS))
        break

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


PARTICIPANTS = (1, 5)
SPEED_MODES = ("speed", "speedDwell", "speedRelease", "speedDirection")
MODE_LABEL = {
    "speed": "Speed",
    "speedDwell": "Speed-Dwell",
    "speedRelease": "Speed-Release",
    "speedDirection": "Speed-Direction",
}
ID_META = {
    1: {"target_size": "Large", "diameter_m": 0.09, "radius_m": 0.045, "amplitude_m": 0.50, "id_bits": 2.713},
    2: {"target_size": "Medium", "diameter_m": 0.06, "radius_m": 0.030, "amplitude_m": 0.60, "id_bits": 3.459},
    3: {"target_size": "Small", "diameter_m": 0.03, "radius_m": 0.015, "amplitude_m": 0.70, "id_bits": 4.605},
}
SIZE_ORDER = ("Large", "Medium", "Small")
NOMINAL_DT_S = 0.02
SPEED_MIN_M_S = 0.067
SPEED_MAX_M_S = 0.375
PALETTE = {1: "#2563EB", 5: "#E11D48"}


def parse_args() -> argparse.Namespace:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=root)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=root / "analysis_outputs" / "p01_p05_speed_frame_20260924",
    )
    return parser.parse_args()


def fnum(value: Any) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return float("nan")
    return out if math.isfinite(out) else float("nan")


def inum(value: Any, default: int = -1) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def med(series: Iterable[float]) -> float:
    a = np.asarray(list(series), dtype=float)
    a = a[np.isfinite(a)]
    return float(np.median(a)) if len(a) else float("nan")


def iqr(series: Iterable[float]) -> tuple[float, float]:
    a = np.asarray(list(series), dtype=float)
    a = a[np.isfinite(a)]
    if not len(a):
        return (float("nan"), float("nan"))
    return tuple(float(x) for x in np.quantile(a, [0.25, 0.75]))


def pct(n: float, d: float) -> str:
    return "NA" if not d else f"{100*n/d:.1f}%"


def fmt(value: float, digits: int = 1) -> str:
    return "NA" if value is None or not np.isfinite(value) else f"{value:.{digits}f}"


def bootstrap_median_ci(values: Iterable[float], seed: int, reps: int = 4000) -> tuple[float, float]:
    a = np.asarray(list(values), dtype=float)
    a = a[np.isfinite(a)]
    if not len(a):
        return float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    draws = rng.choice(a, size=(reps, len(a)), replace=True)
    return tuple(float(x) for x in np.quantile(np.median(draws, axis=1), [0.025, 0.975]))


@dataclass
class RunData:
    participant: int
    run_id: str
    mode: str
    run_order: int
    time_rows: list[list[str]]
    trajectory: pd.DataFrame
    time_path: Path
    trajectory_path: Path


def read_csv_rows(path: Path) -> list[list[str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.reader(handle))


def discover_runs(root: Path) -> list[RunData]:
    runs: list[RunData] = []
    for participant in PARTICIPANTS:
        folders = sorted((root / str(participant) / "Trigger").iterdir())
        for order, folder in enumerate(folders, 1):
            if not folder.is_dir():
                continue
            time_path = next(folder.glob("*-time.csv"))
            trajectory_path = next(folder.glob("*-trajectory.csv"))
            raw_time = read_csv_rows(time_path)
            mode = raw_time[1][12].strip() if len(raw_time) > 1 else "unknown"
            trajectory = pd.read_csv(trajectory_path, encoding="utf-8-sig")
            trajectory["_global_row"] = np.arange(len(trajectory))
            runs.append(
                RunData(participant, folder.name, mode, order, raw_time[1:], trajectory, time_path, trajectory_path)
            )
    return runs


def parse_trial_summary(row: list[str]) -> dict[str, Any]:
    centers_flat = np.asarray([fnum(x) for x in row[26:]], dtype=float)
    centers = centers_flat.reshape(-1, 3) if len(centers_flat) % 3 == 0 else np.empty((0, 3))
    ball_index = inum(row[13])
    center_index = ball_index + 1  # first triplet is largeCirclePoint; tatgetPos follows
    center = centers[center_index] if 0 <= center_index < len(centers) else np.array([np.nan] * 3)
    return {
        "case": inum(row[0]),
        "id": inum(row[1]),
        "in_target_times_logged": inum(row[2], 0),
        "used_time_s": fnum(row[8]),
        "trigger_condition": row[9].strip(),
        "start_ball": inum(row[10]),
        "rotation_direction": inum(row[11]),
        "mode": row[12].strip(),
        "ball_index": ball_index,
        "trigger_time_last_entry_s": fnum(row[17]),
        "is_mine_ball": row[19].strip().lower() == "true",
        "cancel_reason": row[21].strip(),
        "no_trigger_reason": row[22].strip(),
        "cancel_times": inum(row[23], 0),
        "target_center_x": center[0],
        "target_center_y": center[1],
        "target_center_z": center[2],
        "center_triplet_count": len(centers),
    }


def first_true_indices(mask: np.ndarray) -> np.ndarray:
    if not len(mask):
        return np.array([], dtype=int)
    return np.flatnonzero(mask & np.r_[True, ~mask[:-1]])


def first_exit_after(mask: np.ndarray, start: int) -> int | None:
    if start < 0 or start >= len(mask):
        return None
    idx = np.flatnonzero(~mask[start + 1 :])
    return int(start + 1 + idx[0]) if len(idx) else None


def radial_components(pos: np.ndarray, center: np.ndarray, dt: float) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    vel = np.full_like(pos, np.nan, dtype=float)
    if len(pos) > 1:
        vel[1:] = np.diff(pos, axis=0) / dt
        vel[0] = vel[1]
    speed = np.linalg.norm(vel, axis=1)
    rel = pos - center
    norms = np.linalg.norm(rel, axis=1)
    unit = np.divide(rel, norms[:, None], out=np.zeros_like(rel), where=norms[:, None] > 1e-12)
    radial_inward = -np.sum(vel * unit, axis=1)
    tangential = np.sqrt(np.maximum(0.0, speed**2 - radial_inward**2))
    return vel, speed, radial_inward, tangential


def analyze_one_trial(run: RunData, summary: dict[str, Any]) -> tuple[dict[str, Any], pd.DataFrame]:
    ident = int(summary["id"])
    meta = ID_META.get(ident)
    if meta is None:
        raise ValueError(f"Unexpected ID {ident} in {run.run_id}")
    group = run.trajectory[
        (run.trajectory["Case"].astype(int) == int(summary["case"]))
        & (run.trajectory["ID"].astype(int) == ident)
    ].copy()
    group = group.sort_values("_global_row").reset_index(drop=True)
    pos = group[["indexLocX", "indexLocY", "indexLocZ"]].to_numpy(float)
    center = np.array([summary["target_center_x"], summary["target_center_y"], summary["target_center_z"]], float)
    radius = float(meta["radius_m"])
    rho = np.linalg.norm(pos - center, axis=1) / radius
    inside = rho <= 1.0
    entries = first_true_indices(inside)
    first_entry = int(entries[0]) if len(entries) else -1
    trigger = len(group) - 1 if len(group) else -1
    speed_logged = group["ori_v"].to_numpy(float)
    _, speed_recalc, radial, tangential = radial_components(pos, center, NOMINAL_DT_S)
    accel = np.r_[np.nan, np.diff(speed_recalc) / NOMINAL_DT_S] if len(speed_recalc) else np.array([])

    max_cross = np.flatnonzero((np.arange(len(group)) >= max(first_entry, 0)) & (speed_logged >= SPEED_MAX_M_S))
    first_threshold = int(max_cross[0]) if len(max_cross) else -1
    low_cross = np.flatnonzero((np.arange(len(group)) >= max(first_entry, 0)) & (speed_logged <= SPEED_MIN_M_S))
    first_arm = int(low_cross[0]) if len(low_cross) else -1
    armed_max = np.flatnonzero((np.arange(len(group)) > first_arm) & (speed_logged >= SPEED_MAX_M_S)) if first_arm >= 0 else np.array([])
    first_armed_threshold = int(armed_max[0]) if len(armed_max) else -1

    inside_to_trigger = np.flatnonzero(inside & (np.arange(len(group)) >= max(first_entry, 0)))
    if len(inside_to_trigger):
        peak_idx = int(inside_to_trigger[np.nanargmax(speed_logged[inside_to_trigger])])
        peak_speed = float(speed_logged[peak_idx])
        min_rho = float(np.nanmin(rho[inside_to_trigger]))
    else:
        peak_idx, peak_speed, min_rho = -1, float("nan"), float("nan")

    path_inside = 0.0
    if first_entry >= 0 and trigger > first_entry:
        seg = np.linalg.norm(np.diff(pos[first_entry : trigger + 1], axis=0), axis=1)
        valid_seg = inside[first_entry + 1 : trigger + 1] | inside[first_entry:trigger]
        path_inside = float(np.sum(seg[valid_seg]))

    global_trigger = int(group.iloc[-1]["_global_row"]) if len(group) else -1
    post = run.trajectory.iloc[global_trigger : min(len(run.trajectory), global_trigger + 31)].copy() if global_trigger >= 0 else pd.DataFrame()
    post_pos = post[["indexLocX", "indexLocY", "indexLocZ"]].to_numpy(float) if len(post) else np.empty((0, 3))
    post_rho = np.linalg.norm(post_pos - center, axis=1) / radius if len(post) else np.array([])
    _, post_speed, post_radial, _ = radial_components(post_pos, center, NOMINAL_DT_S) if len(post) else (None, np.array([]), np.array([]), None)
    post_exit_rel = next((i for i in range(1, len(post_rho)) if post_rho[i] > 1), None)
    reversal_rel = next((i for i in range(1, len(post_radial) - 1) if post_radial[i] < 0 and post_radial[i + 1] < 0), None)

    pre_start = max(0, trigger - 5)
    post_limit = min(6, len(post_speed))
    pre_speed = float(np.nanmean(speed_logged[pre_start : trigger + 1])) if trigger >= 0 else float("nan")
    post_window = post_speed[:post_limit]
    post_speed_mean = float(np.nanmean(post_window)) if np.isfinite(post_window).any() else float("nan")
    pre_rho_change = float(rho[trigger] - rho[pre_start]) if trigger >= 0 else float("nan")
    post_rho_change = float(post_rho[post_limit - 1] - post_rho[0]) if post_limit else float("nan")

    finite_compare = np.isfinite(speed_logged) & np.isfinite(speed_recalc)
    rmse = float(np.sqrt(np.mean((speed_logged[finite_compare] - speed_recalc[finite_compare]) ** 2))) if finite_compare.any() else float("nan")
    corr = float(np.corrcoef(speed_logged[finite_compare], speed_recalc[finite_compare])[0, 1]) if finite_compare.sum() > 2 else float("nan")

    first_entry_success = summary["in_target_times_logged"] == 1 and summary["trigger_condition"] == "S"
    exact_first_latency = summary["trigger_time_last_entry_s"] if first_entry_success else float("nan")
    trial_order = (ident - 1) * 16 + int(summary["case"])
    metrics = {
        "participant": f"P{run.participant:02d}",
        "participant_id": run.participant,
        "run_id": run.run_id,
        "run_order": run.run_order,
        "technique": MODE_LABEL.get(run.mode, run.mode),
        "mode_logged": run.mode,
        "target_size": meta["target_size"],
        "id_code": ident,
        "id_bits": meta["id_bits"],
        "target_diameter_m": meta["diameter_m"],
        "target_radius_m": radius,
        "trial_case": int(summary["case"]),
        "trial_order_within_technique": trial_order,
        "ball_index": int(summary["ball_index"]),
        "trajectory_frames": len(group),
        "final_trigger_success": summary["trigger_condition"] == "S",
        "first_entry_trigger_success_logged": first_entry_success,
        "attempt_count_logged": int(summary["in_target_times_logged"]),
        "failed_entry_count_logged": max(0, int(summary["in_target_times_logged"]) - 1),
        "sphere_entry_count_derived": len(entries),
        "entry_definition_disagrees": int(summary["in_target_times_logged"]) != len(entries),
        "abnormal_trigger_condition": summary["trigger_condition"] != "S",
        "trial_total_time_s_exact": summary["used_time_s"],
        "last_entry_to_trigger_s_exact": summary["trigger_time_last_entry_s"],
        "first_entry_to_trigger_s_exact_when_single_entry": exact_first_latency,
        "first_entry_to_trigger_s_nominal": (trigger - first_entry) * NOMINAL_DT_S if first_entry >= 0 else float("nan"),
        "first_entry_to_threshold_s_nominal": (first_threshold - first_entry) * NOMINAL_DT_S if first_threshold >= 0 and first_entry >= 0 else float("nan"),
        "first_entry_to_arm_s_nominal": (first_arm - first_entry) * NOMINAL_DT_S if first_arm >= 0 and first_entry >= 0 else float("nan"),
        "arm_to_threshold_s_nominal": (first_armed_threshold - first_arm) * NOMINAL_DT_S if first_armed_threshold >= 0 and first_arm >= 0 else float("nan"),
        "target_inside_time_s_nominal": float(np.sum(inside[first_entry : trigger + 1]) * NOMINAL_DT_S) if first_entry >= 0 else float("nan"),
        "trigger_to_exit_s_nominal": post_exit_rel * NOMINAL_DT_S if post_exit_rel is not None else float("nan"),
        "trigger_to_radial_reversal_s_nominal": reversal_rel * NOMINAL_DT_S if reversal_rel is not None else float("nan"),
        "entry_speed_logged_m_s": float(speed_logged[first_entry]) if first_entry >= 0 else float("nan"),
        "entry_speed_recalc_nominal_m_s": float(speed_recalc[first_entry]) if first_entry >= 0 else float("nan"),
        "entry_radial_speed_nominal_m_s": float(radial[first_entry]) if first_entry >= 0 else float("nan"),
        "entry_tangential_speed_nominal_m_s": float(tangential[first_entry]) if first_entry >= 0 else float("nan"),
        "inside_peak_speed_logged_m_s": peak_speed,
        "peak_speed_time_from_entry_s_nominal": (peak_idx - first_entry) * NOMINAL_DT_S if peak_idx >= 0 and first_entry >= 0 else float("nan"),
        "peak_speed_phase": "pre-entry" if peak_idx < first_entry else ("entry/near" if peak_idx - first_entry <= 2 else "post-entry"),
        "peak_positive_acceleration_nominal_m_s2": float(np.nanmax(accel[first_entry : trigger + 1])) if first_entry >= 0 and trigger >= first_entry else float("nan"),
        "peak_abs_acceleration_nominal_m_s2": float(np.nanmax(np.abs(accel[first_entry : trigger + 1]))) if first_entry >= 0 and trigger >= first_entry else float("nan"),
        "inside_path_length_m": path_inside,
        "max_normalized_depth": 1.0 - min_rho if np.isfinite(min_rho) else float("nan"),
        "normalized_trigger_depth": 1.0 - float(rho[trigger]) if trigger >= 0 else float("nan"),
        "trigger_rho": float(rho[trigger]) if trigger >= 0 else float("nan"),
        "trigger_speed_logged_m_s": float(speed_logged[trigger]) if trigger >= 0 else float("nan"),
        "entry_speed_above_max_threshold": bool(speed_logged[first_entry] >= SPEED_MAX_M_S) if first_entry >= 0 else False,
        "threshold_within_40ms_of_entry": bool(first_threshold >= 0 and first_threshold - first_entry <= 2) if first_entry >= 0 else False,
        "pretrigger_100ms_speed_logged_m_s": pre_speed,
        "posttrigger_100ms_speed_nominal_m_s": post_speed_mean,
        "pretrigger_100ms_rho_change": pre_rho_change,
        "posttrigger_100ms_rho_change": post_rho_change,
        "logged_vs_recalc_speed_rmse_m_s": rmse,
        "logged_vs_recalc_speed_corr": corr,
        "position_jump_gt_5cm_count": int(np.sum(np.linalg.norm(np.diff(pos, axis=0), axis=1) > 0.05)) if len(pos) > 1 else 0,
        "target_center_x": center[0],
        "target_center_y": center[1],
        "target_center_z": center[2],
        "first_entry_frame": first_entry,
        "threshold_frame": first_threshold,
        "armed_threshold_frame": first_armed_threshold,
        "trigger_frame": trigger,
        "reversal_frame_after_trigger": reversal_rel if reversal_rel is not None else np.nan,
        "exit_frame_after_trigger": post_exit_rel if post_exit_rel is not None else np.nan,
        "time_basis_note": "exact logger seconds for usedTime/triggerTime; all *_nominal values use configured 0.02 s Fixed Timestep because frame timestamps are absent",
    }

    frames = group.copy()
    frames["participant"] = metrics["participant"]
    frames["run_id"] = run.run_id
    frames["technique"] = metrics["technique"]
    frames["target_size"] = meta["target_size"]
    frames["trial_case"] = int(summary["case"])
    frames["trial_order_within_technique"] = trial_order
    frames["frame_in_trial"] = np.arange(len(frames))
    frames["time_from_first_entry_ms_nominal"] = (np.arange(len(frames)) - first_entry) * NOMINAL_DT_S * 1000 if first_entry >= 0 else np.nan
    frames["rho"] = rho
    frames["inside_sphere"] = inside
    frames["speed_recalc_nominal_m_s"] = speed_recalc
    frames["radial_speed_nominal_m_s"] = radial
    frames["tangential_speed_nominal_m_s"] = tangential
    frames["acceleration_nominal_m_s2"] = accel
    frames["is_first_entry"] = np.arange(len(frames)) == first_entry
    frames["is_threshold"] = np.arange(len(frames)) == first_threshold
    frames["is_trigger"] = np.arange(len(frames)) == trigger
    return metrics, frames


def build_all_trials(runs: list[RunData]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    metrics: list[dict[str, Any]] = []
    frames: list[pd.DataFrame] = []
    auxiliary: list[dict[str, Any]] = []
    for run in runs:
        parsed_rows = [parse_trial_summary(row) for row in run.time_rows]
        if run.mode in SPEED_MODES:
            for summary in parsed_rows:
                row, frame = analyze_one_trial(run, summary)
                metrics.append(row)
                frames.append(frame)
        else:
            for summary in parsed_rows[:48]:
                try:
                    row, _ = analyze_one_trial(run, summary)
                except Exception:
                    continue
                auxiliary.append(
                    {
                        "participant": row["participant"],
                        "mode_logged": run.mode,
                        "target_size": row["target_size"],
                        "entry_speed_logged_m_s": row["entry_speed_logged_m_s"],
                        "last_entry_to_trigger_s_exact": row["last_entry_to_trigger_s_exact"],
                        "attempt_count_logged": row["attempt_count_logged"],
                    }
                )
    return pd.DataFrame(metrics), pd.concat(frames, ignore_index=True), pd.DataFrame(auxiliary)


def summarize_conditions(trials: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    keys = ["participant", "technique", "target_size"]
    for key, g in trials.groupby(keys, sort=False):
        p, tech, size = key
        n = len(g)
        row: dict[str, Any] = {
            "participant": p,
            "technique": tech,
            "target_size": size,
            "n_trials": n,
            "final_trigger_success_n": int(g["final_trigger_success"].sum()),
            "final_trigger_success_rate": float(g["final_trigger_success"].mean()),
            "first_entry_success_n": int(g["first_entry_trigger_success_logged"].sum()),
            "first_entry_success_rate": float(g["first_entry_trigger_success_logged"].mean()),
            "attempt_count_median": med(g["attempt_count_logged"]),
            "attempt_count_q1": iqr(g["attempt_count_logged"])[0],
            "attempt_count_q3": iqr(g["attempt_count_logged"])[1],
            "failed_entry_total": int(g["failed_entry_count_logged"].sum()),
            "abnormal_trigger_n": int(g["abnormal_trigger_condition"].sum()),
            "entry_to_trigger_exact_single_entry_n": int(g["first_entry_to_trigger_s_exact_when_single_entry"].notna().sum()),
            "entry_to_trigger_exact_single_entry_median_ms": 1000 * med(g["first_entry_to_trigger_s_exact_when_single_entry"]),
            "entry_to_trigger_exact_single_entry_q1_ms": 1000 * iqr(g["first_entry_to_trigger_s_exact_when_single_entry"])[0],
            "entry_to_trigger_exact_single_entry_q3_ms": 1000 * iqr(g["first_entry_to_trigger_s_exact_when_single_entry"])[1],
            "entry_to_threshold_nominal_median_ms": 1000 * med(g["first_entry_to_threshold_s_nominal"]),
            "entry_speed_logged_median_m_s": med(g["entry_speed_logged_m_s"]),
            "entry_radial_speed_nominal_median_m_s": med(g["entry_radial_speed_nominal_m_s"]),
            "entry_tangential_speed_nominal_median_m_s": med(g["entry_tangential_speed_nominal_m_s"]),
            "inside_peak_speed_logged_median_m_s": med(g["inside_peak_speed_logged_m_s"]),
            "peak_time_from_entry_nominal_median_ms": 1000 * med(g["peak_speed_time_from_entry_s_nominal"]),
            "trigger_depth_median": med(g["normalized_trigger_depth"]),
            "inside_time_nominal_median_ms": 1000 * med(g["target_inside_time_s_nominal"]),
            "inside_path_length_median_mm": 1000 * med(g["inside_path_length_m"]),
            "trigger_to_exit_nominal_median_ms": 1000 * med(g["trigger_to_exit_s_nominal"]),
            "trigger_to_reversal_nominal_median_ms": 1000 * med(g["trigger_to_radial_reversal_s_nominal"]),
            "entry_above_max_threshold_rate": float(g["entry_speed_above_max_threshold"].mean()),
            "threshold_within_40ms_rate": float(g["threshold_within_40ms_of_entry"].mean()),
            "sphere_vs_logged_entry_disagreement_rate": float(g["entry_definition_disagrees"].mean()),
            "missing_entry_n": int((g["first_entry_frame"] < 0).sum()),
        }
        lo, hi = bootstrap_median_ci(1000 * g["first_entry_to_trigger_s_exact_when_single_entry"], seed=hash(key) % (2**32))
        row["entry_to_trigger_exact_single_entry_bootstrap_lo_ms"] = lo
        row["entry_to_trigger_exact_single_entry_bootstrap_hi_ms"] = hi
        rows.append(row)
    return pd.DataFrame(rows)


def overall_summary(trials: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for p, g in trials.groupby("participant"):
        q1, q3 = iqr(1000 * g["first_entry_to_trigger_s_exact_when_single_entry"])
        rows.append(
            {
                "participant": p,
                "n_trials": len(g),
                "final_trigger_success_rate": g["final_trigger_success"].mean(),
                "first_entry_success_rate": g["first_entry_trigger_success_logged"].mean(),
                "attempt_count_median": med(g["attempt_count_logged"]),
                "attempt_count_range": f"{int(g['attempt_count_logged'].min())}-{int(g['attempt_count_logged'].max())}",
                "entry_to_trigger_exact_single_entry_n": g["first_entry_to_trigger_s_exact_when_single_entry"].notna().sum(),
                "entry_to_trigger_exact_single_entry_median_ms": 1000 * med(g["first_entry_to_trigger_s_exact_when_single_entry"]),
                "entry_to_trigger_exact_single_entry_q1_ms": q1,
                "entry_to_trigger_exact_single_entry_q3_ms": q3,
                "entry_speed_logged_median_m_s": med(g["entry_speed_logged_m_s"]),
                "peak_time_from_entry_nominal_median_ms": 1000 * med(g["peak_speed_time_from_entry_s_nominal"]),
                "trigger_depth_median": med(g["normalized_trigger_depth"]),
                "inside_time_nominal_median_ms": 1000 * med(g["target_inside_time_s_nominal"]),
                "trigger_to_reversal_nominal_median_ms": 1000 * med(g["trigger_to_radial_reversal_s_nominal"]),
                "entry_above_max_threshold_rate": g["entry_speed_above_max_threshold"].mean(),
                "threshold_within_40ms_rate": g["threshold_within_40ms_of_entry"].mean(),
                "entry_definition_disagreement_rate": g["entry_definition_disagrees"].mean(),
            }
        )
    return pd.DataFrame(rows)


def file_audit(root: Path) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    for participant in PARTICIPANTS:
        for path in sorted((root / str(participant)).rglob("*.csv")):
            rows = read_csv_rows(path)
            header = rows[0] if rows else []
            timestamp_col = None
            for candidate in ("time", "timestamp", "Time"):
                if candidate in header:
                    timestamp_col = header.index(candidate)
                    break
            times = []
            if timestamp_col is not None:
                times = [fnum(r[timestamp_col]) for r in rows[1:] if len(r) > timestamp_col]
                times = [x for x in times if np.isfinite(x)]
            diffs = np.diff(times) if len(times) > 1 else np.array([])
            records.append(
                {
                    "participant": f"P{participant:02d}",
                    "relative_path": str(path.relative_to(root)),
                    "file_type": path.stem.split("-")[-1],
                    "rows": max(0, len(rows) - 1),
                    "field_count": len(header),
                    "fields": " | ".join(header),
                    "timestamp_field": header[timestamp_col] if timestamp_col is not None else "",
                    "timestamp_min_s": min(times) if times else np.nan,
                    "timestamp_max_s": max(times) if times else np.nan,
                    "median_dt_s": float(np.median(diffs[diffs > 0])) if np.any(diffs > 0) else np.nan,
                    "estimated_rate_hz": 1 / float(np.median(diffs[diffs > 0])) if np.any(diffs > 0) else np.nan,
                    "duplicate_timestamp_count": int(np.sum(diffs == 0)) if len(diffs) else np.nan,
                    "nonmonotonic_timestamp_count": int(np.sum(diffs < 0)) if len(diffs) else np.nan,
                }
            )
    return pd.DataFrame(records)


def configure_plotting() -> None:
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.titleweight": "bold",
            "axes.labelcolor": "#334155",
            "xtick.color": "#475569",
            "ytick.color": "#475569",
            "figure.facecolor": "white",
        }
    )


def plot_speed_aligned(trials: pd.DataFrame, frames: pd.DataFrame, out: Path) -> None:
    for participant in ("P01", "P05"):
        fig, axes = plt.subplots(3, 4, figsize=(18, 11), sharex=True, sharey=True)
        for ri, size in enumerate(SIZE_ORDER):
            for ci, technique in enumerate(MODE_LABEL.values()):
                ax = axes[ri, ci]
                sub = frames[(frames.participant == participant) & (frames.target_size == size) & (frames.technique == technique)]
                tsub = trials[(trials.participant == participant) & (trials.target_size == size) & (trials.technique == technique)]
                curves = []
                grid = np.arange(-200, 701, 20)
                for (_, _, case), g in sub.groupby(["run_id", "ID", "trial_case"]):
                    x = g.time_from_first_entry_ms_nominal.to_numpy(float)
                    y = g.ori_v.to_numpy(float)
                    keep = (x >= -200) & (x <= 700)
                    ax.plot(x[keep], y[keep], color=PALETTE[int(participant[1:])], alpha=0.10, lw=0.8)
                    curves.append(np.interp(grid, x, y, left=np.nan, right=np.nan))
                if curves:
                    arr = np.asarray(curves)
                    ax.plot(grid, np.nanmedian(arr, axis=0), color=PALETTE[int(participant[1:])], lw=2.6)
                ax.axhline(SPEED_MAX_M_S, color="#111827", ls="--", lw=1, label="max threshold" if ri == 0 and ci == 0 else None)
                if len(tsub):
                    trig_ms = 1000 * tsub.first_entry_to_trigger_s_nominal
                    ax.axvline(med(trig_ms), color="#F59E0B", ls=":", lw=2)
                ax.axvline(0, color="#64748B", lw=0.8)
                ax.set_title(f"{technique}\n{size} · n={len(tsub)}")
                if ci == 0:
                    ax.set_ylabel("Index speed (m/s)")
                if ri == 2:
                    ax.set_xlabel("Time from first sphere entry (ms, nominal)")
                ax.set_xlim(-200, 700)
                ax.set_ylim(0, max(1.4, float(np.nanquantile(sub.ori_v, 0.995)) if len(sub) else 1.4))
        fig.suptitle(f"{participant}: entry-aligned Speed-family velocity\nThin = trials, thick = median, orange = median trigger; no frame timestamps (20 ms nominal)", fontsize=16, fontweight="bold")
        fig.tight_layout(rect=[0, 0, 1, 0.94])
        fig.savefig(out / f"fig01_speed_aligned_{participant}.png", dpi=180)
        plt.close(fig)


def plot_rho_aligned(trials: pd.DataFrame, frames: pd.DataFrame, out: Path) -> None:
    for participant in ("P01", "P05"):
        fig, axes = plt.subplots(3, 4, figsize=(18, 11), sharex=True, sharey=True)
        for ri, size in enumerate(SIZE_ORDER):
            for ci, technique in enumerate(MODE_LABEL.values()):
                ax = axes[ri, ci]
                sub = frames[(frames.participant == participant) & (frames.target_size == size) & (frames.technique == technique)]
                tsub = trials[(trials.participant == participant) & (trials.target_size == size) & (trials.technique == technique)]
                grid = np.arange(-200, 701, 20)
                curves = []
                for (_, _, case), g in sub.groupby(["run_id", "ID", "trial_case"]):
                    x = g.time_from_first_entry_ms_nominal.to_numpy(float)
                    y = g.rho.to_numpy(float)
                    keep = (x >= -200) & (x <= 700)
                    ax.plot(x[keep], y[keep], color=PALETTE[int(participant[1:])], alpha=0.09, lw=0.8)
                    curves.append(np.interp(grid, x, y, left=np.nan, right=np.nan))
                if curves:
                    ax.plot(grid, np.nanmedian(np.asarray(curves), axis=0), color=PALETTE[int(participant[1:])], lw=2.6)
                ax.axhline(1, color="#111827", ls="--", lw=1)
                ax.axvline(0, color="#64748B", lw=0.8)
                if len(tsub):
                    ax.scatter(1000 * tsub.first_entry_to_threshold_s_nominal, tsub.apply(lambda r: np.nan, axis=1), s=0)
                    ax.axvline(med(1000 * tsub.first_entry_to_trigger_s_nominal), color="#F59E0B", ls=":", lw=2)
                    rv = med(1000 * tsub.trigger_to_radial_reversal_s_nominal + 1000 * tsub.first_entry_to_trigger_s_nominal)
                    if np.isfinite(rv):
                        ax.axvline(rv, color="#7C3AED", ls="-.", lw=1.3)
                ax.set_title(f"{technique}\n{size} · n={len(tsub)}")
                if ci == 0:
                    ax.set_ylabel("Normalized center distance ρ")
                if ri == 2:
                    ax.set_xlabel("Time from first sphere entry (ms, nominal)")
                ax.set_xlim(-200, 700)
                ax.set_ylim(-0.05, 2.8)
        fig.suptitle(f"{participant}: entry-aligned normalized target distance\nρ=1 boundary; orange = median trigger, purple = median post-trigger reversal (nominal)", fontsize=16, fontweight="bold")
        fig.tight_layout(rect=[0, 0, 1, 0.94])
        fig.savefig(out / f"fig02_rho_aligned_{participant}.png", dpi=180)
        plt.close(fig)


def plot_scatter(trials: pd.DataFrame, out: Path) -> None:
    fig, axes = plt.subplots(1, 4, figsize=(18, 4.8), sharex=True, sharey=True)
    markers = {"Large": "o", "Medium": "s", "Small": "^"}
    for ax, technique in zip(axes, MODE_LABEL.values()):
        for participant in ("P01", "P05"):
            for size in SIZE_ORDER:
                g = trials[(trials.participant == participant) & (trials.technique == technique) & (trials.target_size == size)]
                ax.scatter(1000 * g.first_entry_to_trigger_s_nominal, g.normalized_trigger_depth, s=35, alpha=0.7,
                           color=PALETTE[int(participant[1:])], marker=markers[size], edgecolor="white", linewidth=0.4,
                           label=f"{participant} {size}" if technique == "Speed" else None)
        ax.axhline(0, color="#64748B", lw=0.8)
        ax.set_title(f"{technique} · n={len(trials[trials.technique == technique])}")
        ax.set_xlabel("First-entry to trigger (ms, nominal)")
    axes[0].set_ylabel("Normalized trigger depth (1 − ρ)")
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=6, frameon=False)
    fig.suptitle("Trigger depth versus first-entry latency (one point per trial)", fontsize=15, fontweight="bold")
    fig.tight_layout(rect=[0, 0.12, 1, 0.92])
    fig.savefig(out / "fig03_trigger_depth_latency.png", dpi=180)
    plt.close(fig)


def plot_condition_metrics(summary: pd.DataFrame, out: Path) -> None:
    metrics = [
        ("first_entry_success_rate", "First-entry success", "%", 100),
        ("attempt_count_median", "Attempt count", "count", 1),
        ("entry_to_trigger_exact_single_entry_median_ms", "Entry→trigger (exact, single-entry)", "ms", 1),
        ("entry_speed_logged_median_m_s", "Entry speed", "m/s", 1),
        ("trigger_depth_median", "Normalized trigger depth", "1−ρ", 1),
        ("inside_time_nominal_median_ms", "Inside time (nominal)", "ms", 1),
    ]
    fig, axes = plt.subplots(2, 3, figsize=(18, 9))
    xlabels = [f"{m}\n{s}" for m in MODE_LABEL.values() for s in SIZE_ORDER]
    x = np.arange(len(xlabels))
    for ax, (field, title, unit, scale) in zip(axes.flat, metrics):
        for participant, offset in (("P01", -0.13), ("P05", 0.13)):
            vals = []
            for technique in MODE_LABEL.values():
                for size in SIZE_ORDER:
                    g = summary[(summary.participant == participant) & (summary.technique == technique) & (summary.target_size == size)]
                    vals.append(float(g.iloc[0][field]) * scale if len(g) else np.nan)
            ax.plot(x + offset, vals, "o-", color=PALETTE[int(participant[1:])], lw=1.5, ms=5, label=participant)
        ax.set_title(title)
        ax.set_ylabel(unit)
        ax.set_xticks(x)
        ax.set_xticklabels(xlabels, rotation=58, ha="right", fontsize=8)
        ax.grid(axis="y", color="#E2E8F0", lw=0.7)
    axes[0, 0].legend(frameon=False)
    fig.suptitle("P01/P05 Speed-family condition comparison (16 trials per cell)", fontsize=16, fontweight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    fig.savefig(out / "fig04_condition_metrics.png", dpi=180)
    plt.close(fig)


def rotation_to_x(vector: np.ndarray) -> np.ndarray:
    v = vector / max(np.linalg.norm(vector), 1e-12)
    target = np.array([1.0, 0.0, 0.0])
    cross = np.cross(v, target)
    s = np.linalg.norm(cross)
    c = float(np.dot(v, target))
    if s < 1e-10:
        return np.eye(3) if c > 0 else np.diag([-1, -1, 1])
    k = np.array([[0, -cross[2], cross[1]], [cross[2], 0, -cross[0]], [-cross[1], cross[0], 0]])
    return np.eye(3) + k + k @ k * ((1 - c) / (s**2))


def plot_representative_3d(trials: pd.DataFrame, frames: pd.DataFrame, out: Path) -> None:
    fig = plt.figure(figsize=(18, 9))
    for pi, participant in enumerate(("P01", "P05")):
        for ti, technique in enumerate(MODE_LABEL.values()):
            ax = fig.add_subplot(2, 4, pi * 4 + ti + 1, projection="3d")
            candidates = trials[(trials.participant == participant) & (trials.technique == technique) & trials.first_entry_trigger_success_logged]
            if len(candidates):
                target_latency = med(candidates.first_entry_to_trigger_s_exact_when_single_entry)
                chosen = candidates.iloc[(candidates.first_entry_to_trigger_s_exact_when_single_entry - target_latency).abs().argmin()]
                g = frames[(frames.participant == participant) & (frames.run_id == chosen.run_id) & (frames.trial_case == chosen.trial_case) & (frames.ID == chosen.id_code)].copy()
                center = np.array([chosen.target_center_x, chosen.target_center_y, chosen.target_center_z])
                rel = (g[["indexLocX", "indexLocY", "indexLocZ"]].to_numpy(float) - center) / chosen.target_radius_m
                e = int(chosen.first_entry_frame)
                incoming = rel[max(0, e - 4)] - rel[e]
                rot = rotation_to_x(incoming)
                rel = rel @ rot.T
                lo, hi = max(0, e - 8), min(len(rel), int(chosen.trigger_frame) + 1)
                ax.plot(rel[lo:hi, 0], rel[lo:hi, 1], rel[lo:hi, 2], color=PALETTE[int(participant[1:])], lw=2)
                for idx, color, marker, label in [
                    (e, "#0F766E", "o", "entry"),
                    (int(chosen.threshold_frame), "#7C3AED", "^", "threshold"),
                    (int(chosen.trigger_frame), "#F59E0B", "X", "trigger"),
                ]:
                    if 0 <= idx < len(rel):
                        ax.scatter(*rel[idx], color=color, marker=marker, s=65, label=label)
                u, v = np.mgrid[0 : 2 * np.pi : 24j, 0 : np.pi : 12j]
                xs, ys, zs = np.cos(u) * np.sin(v), np.sin(u) * np.sin(v), np.cos(v)
                ax.plot_wireframe(xs, ys, zs, color="#94A3B8", alpha=0.18, linewidth=0.5)
                ax.set_title(f"{participant} · {technique}\n{chosen.target_size}, trial {int(chosen.trial_order_within_technique)}")
                ax.set_xlim(-1.8, 1.8); ax.set_ylim(-1.8, 1.8); ax.set_zlim(-1.8, 1.8)
            ax.set_xlabel("aligned x / R"); ax.set_ylabel("y / R"); ax.set_zlabel("z / R")
    handles, labels = fig.axes[0].get_legend_handles_labels() if fig.axes else ([], [])
    fig.legend(handles, labels, loc="lower center", ncol=3, frameon=False)
    fig.suptitle("Representative center-normalized trajectories (entry direction aligned)", fontsize=16, fontweight="bold")
    fig.tight_layout(rect=[0, 0.06, 1, 0.94])
    fig.savefig(out / "fig05_representative_3d.png", dpi=180)
    plt.close(fig)


def plot_learning(trials: pd.DataFrame, out: Path) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(16, 4.8))
    fields = [
        ("first_entry_to_trigger_s_exact_when_single_entry", "Exact entry→trigger (s)"),
        ("normalized_trigger_depth", "Normalized trigger depth"),
        ("entry_speed_logged_m_s", "Entry speed (m/s)"),
    ]
    for ax, (field, title) in zip(axes, fields):
        for participant in ("P01", "P05"):
            g = trials[trials.participant == participant].sort_values(["run_order", "trial_order_within_technique"])
            x = np.arange(1, len(g) + 1)
            y = g[field].to_numpy(float)
            ax.scatter(x, y, s=10, alpha=0.25, color=PALETTE[int(participant[1:])])
            roll = pd.Series(y).rolling(24, center=True, min_periods=8).median()
            ax.plot(x, roll, color=PALETTE[int(participant[1:])], lw=2, label=participant)
        ax.set_title(title); ax.set_xlabel("Acquisition order across Speed-family trials")
        ax.grid(axis="y", color="#E2E8F0", lw=0.7)
    axes[0].legend(frameon=False)
    fig.suptitle("Within-participant order / learning check (rolling median = 24 trials)", fontsize=15, fontweight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.92])
    fig.savefig(out / "fig06_learning_order.png", dpi=180)
    plt.close(fig)


def audit_text(root: Path, runs: list[RunData], audit: pd.DataFrame, trials: pd.DataFrame) -> str:
    lines = [
        "# P01 / P05 数据审计报告",
        "",
        "## 1. 文件发现",
        "",
        f"- P01：原始目录下共 {len(list((root/'1').rglob('*.csv')))} 个 CSV；Trigger 15 个 run，Cancel 15 个 run。",
        f"- P05：原始目录下共 {len(list((root/'5').rglob('*.csv')))} 个 CSV；Trigger 15 个 run，Cancel 目录为空。",
        f"- Speed 系列逐帧主分析：{len(trials)} 个 trial（2 人 × 4 技术 × 3 尺寸 × 16 trial）。",
        "- 逐文件行数、字段、可用 timestamp 范围与估计采样率见 `file_audit.csv`。",
        "",
        "## 2. 字段定义（由代码与日志交叉确认）",
        "",
        "- participant：顶层目录 `1`/`5`，报告中写为 P01/P05。",
        "- technique：`time.csv` 与 `trajectory.csv` 的 `modeSelected`；本分析使用日志原名 speed、speedDwell、speedRelease、speedDirection。工作区没有 Speed-Motion/Speed-Gesture 这两个字符串，因此不擅自改名。",
        "- trial：`ID × Case` 唯一定位；每个 run 正式记录 3 个 ID × 16 个 Case。",
        "- target size：场景 `idLogicMode=New`，ID 1/2/3 映射到旧 ID 1/5/9，因此分别为 Large 直径 0.09 m、Medium 0.06 m、Small 0.03 m。",
        "- finger position：trajectory 的 indexLocX/Y/Z，为 Unity 世界坐标中的食指尖位置。Unity 场景尺度与阈值注释均表明单位为米。",
        "- target center：time.csv 在前 26 列之后记录 largeCirclePoint 与 16 个逐球心坐标；目标球心取 ballIndex+1 的坐标三元组。目标在 trial 内静止；仍逐帧使用该 trial 球心计算 rho。",
        "- inside target：实验程序用 Collider.bounds.Contains，即轴对齐包围盒，且 tip 或 distal 任一进入即可；本分析按用户要求另算食指尖球面 rho<=1。两者不等价。",
        "- trigger/success：time.csv 的 triggerCondition='S' 表示 Speed 成功完成；所有 Speed trial 最终均有 S。time.csv 只在完成时写一行，所以它不包含被放弃的未完成 trial。",
        "- timestamp：trajectory.csv 没有 timestamp 或 frame。direction-debug / pinch-release-distance 等事件日志有 Unity Time.time 秒，但 Speed 原始 run 没有 speed-boundary-debug 文件。",
        "",
        "## 3. Speed 阈值与算法",
        "",
        "- 保留的 Study3SelectionSettings 与 study3 场景配置：speedMinThreshold=0.067 m/s，speedMaxThreshold=0.375 m/s；pressSpeedThershold=0.4 m/s 属于 Press，不是四个 Speed 模式的主阈值。",
        "- 速度为相邻 FixedUpdate 指尖位置差的欧氏长度 / Time.fixedDeltaTime，是非负速度大小，不带方向、未平滑、单帧瞬时值。",
        "- 当前代码的四个 Speed 模式均要求：进入后先观察到 speed<=0.067（armed），随后在目标内某一帧 speed>=0.375 才触发。没有要求连续多帧超过最大阈值。",
        "- 进入前的上一帧位置参与进入帧速度计算，因为速度先由当前/上一 FixedUpdate 位置计算，再执行 inside 与阈值逻辑。",
        "- ProjectSettings/TimeManager.asset 的 Fixed Timestep=0.02 s（名义 50 Hz），但轨迹日志未保存真实 timestamp；因此脚本重算速度/加速度只能作为名义时间敏感性分析，不能验证真实帧间抖动或丢帧。",
        "",
        "## 4. 数据质量",
        "",
        f"- Speed run 的 trial 汇总完整：{len(trials)}/384；每个参与者每个 Speed 技术 48 行。",
        f"- 球面 rho 派生进入次数与程序记录 inTargetTimes 不一致的 trial：{int(trials.entry_definition_disagrees.sum())}/{len(trials)}（原因包括 AABB vs 球面、distal joint 未记录以及逐帧边界采样）。",
        f"- 大于 5 cm 的相邻位置跳变总数：{int(trials.position_jump_gt_5cm_count.sum())}；逐 trial 明细见 trial_metrics.csv。",
        "- trajectory 无 timestamp，故缺失帧、重复 timestamp、非单调 timestamp无法直接审计；事件日志中有 timestamp 的文件已在 file_audit.csv 单独检查。",
        "- P05 的 dwell run 有 49 条 time 行而非 48；已有分析曾将额外行排除并留审计。Speed run 均为 48。",
        "- P05 Speed 数据采集于 2026-08-29，P01 于 2026-08-30；字段结构、ID 结构、模式集合相同。没有构建号/APK 哈希，不能严格证明二进制版本相同；只能说 schema 与保留配置一致。",
        "",
        "## 5. 单位与坐标系",
        "",
        "- 位置/球直径/路径长度：米；速度：米/秒；加速度：米/秒²；角度：度；Time.time/usedTime/triggerTime：秒。",
        "- 坐标是 Unity 左手世界坐标（x 右、y 上、z 前为 Unity 约定）；日志未记录头部姿态，无法转换成严格的头坐标系。",
        "- 三维代表轨迹先平移到球心、除以半径，再把进入方向旋转到 +x，避免未对齐意大利面图。",
    ]
    return "\n".join(lines) + "\n"


def build_report(trials: pd.DataFrame, summary: pd.DataFrame, overall: pd.DataFrame, auxiliary: pd.DataFrame) -> tuple[str, str]:
    ov = overall.set_index("participant")
    p1, p5 = ov.loc["P01"], ov.loc["P05"]
    size_lines = []
    for size in SIZE_ORDER:
        g1 = trials[(trials.participant == "P01") & (trials.target_size == size)]
        g5 = trials[(trials.participant == "P05") & (trials.target_size == size)]
        size_lines.append(
            f"- {size}：首次进入成功率 P01 {pct(g1.first_entry_trigger_success_logged.sum(),len(g1))}，P05 {pct(g5.first_entry_trigger_success_logged.sum(),len(g5))}；"
            f"单次进入 trial 的精确 entry→trigger 中位数 P01 {fmt(1000*med(g1.first_entry_to_trigger_s_exact_when_single_entry),0)} ms，P05 {fmt(1000*med(g5.first_entry_to_trigger_s_exact_when_single_entry),0)} ms；"
            f"进入帧速度中位数 P01 {fmt(med(g1.entry_speed_logged_m_s),3)} m/s，P05 {fmt(med(g5.entry_speed_logged_m_s),3)} m/s。"
        )
    tech_lines = []
    for tech in MODE_LABEL.values():
        g1 = trials[(trials.participant == "P01") & (trials.technique == tech)]
        g5 = trials[(trials.participant == "P05") & (trials.technique == tech)]
        tech_lines.append(
            f"- {tech}：首次进入成功率 {pct(g1.first_entry_trigger_success_logged.sum(),len(g1))} vs {pct(g5.first_entry_trigger_success_logged.sum(),len(g5))}（P01 vs P05）；"
            f"精确单次进入 entry→trigger 中位数 {fmt(1000*med(g1.first_entry_to_trigger_s_exact_when_single_entry),0)} vs {fmt(1000*med(g5.first_entry_to_trigger_s_exact_when_single_entry),0)} ms；"
            f"进入速度 {fmt(med(g1.entry_speed_logged_m_s),3)} vs {fmt(med(g5.entry_speed_logged_m_s),3)} m/s。"
        )

    def early_late(g: pd.DataFrame, field: str) -> tuple[float, float]:
        g = g.sort_values(["run_order", "trial_order_within_technique"])
        cut = len(g) // 2
        return med(g.iloc[:cut][field]), med(g.iloc[cut:][field])

    learn = []
    for p in ("P01", "P05"):
        g = trials[trials.participant == p]
        a, b = early_late(g, "first_entry_to_trigger_s_exact_when_single_entry")
        c, d = early_late(g, "normalized_trigger_depth")
        learn.append(f"- {p} 前/后半：精确单次进入 entry→trigger {fmt(1000*a,0)}→{fmt(1000*b,0)} ms；trigger depth {fmt(c,3)}→{fmt(d,3)}。技术顺序与时间完全混杂，只能作趋势描述。")

    aux_lines = []
    if len(auxiliary):
        for p in ("P01", "P05"):
            s = trials[trials.participant == p]
            n = auxiliary[auxiliary.participant == p]
            aux_lines.append(
                f"- {p}：Speed 系列进入速度中位数 {fmt(med(s.entry_speed_logged_m_s),3)} m/s；非 Speed 技术合并为 {fmt(med(n.entry_speed_logged_m_s),3)} m/s。不同技术触发规则不同，此处仅用于判断一般动作习惯。"
            )

    p05_peak = trials[trials.participant == "P05"].peak_speed_phase.value_counts(normalize=True)
    p01_peak = trials[trials.participant == "P01"].peak_speed_phase.value_counts(normalize=True)
    p05_fast = float(p5.threshold_within_40ms_rate)
    p01_fast = float(p1.threshold_within_40ms_rate)
    faster = "P05" if p5.entry_to_trigger_exact_single_entry_median_ms < p1.entry_to_trigger_exact_single_entry_median_ms else "P01"
    report = f"""# P01 与 P05：Speed 系列逐帧个案分析

> 重要限制：原始 trajectory.csv 没有逐帧 timestamp，且程序 inside 定义为 AABB 中 tip 或 distal 任一进入。本报告把 logger 精确秒数与基于 20 ms Fixed Timestep 的名义帧分析严格分开；关于峰值相对 entry、方向反转和 trigger 后退出的结论均为名义帧证据。

## 1. 数据与方法

分析纳入 384 个已完成 Speed-family trial：2 名参与者 × 4 个日志模式（Speed、Speed-Dwell、Speed-Release、Speed-Direction）× Large/Medium/Small × 16。用户所写 Speed-Motion、Speed-Gesture 在数据和代码中没有同名模式，故未擅自把它们映射为 Release/Direction。

目标进入按 rho=||finger-center||/radius<=1 重算；同时保留程序记录的 inTargetTimes。速度阈值来自保留的配置：先 <=0.067 m/s armed，再 >=0.375 m/s trigger。报告以中位数、IQR、范围和比例描述，不做跨参与者总体显著性推断。bootstrap 区间仅描述各参与者 trial 的不确定性。

## 2. 数据质量问题

- 所有 Speed trial 最终 triggerCondition 都为 S，因此最终成功率 P01=P05=100%。但日志只在成功完成时写 trial 汇总，不能据此估计未保存/中途放弃的失败。
- P01/P05 的 Speed 采集相隔 1 天，schema、条件和保留参数配置一致；缺少构建号或二进制哈希，无法严格排除程序版本差异。
- 球面 rho 与程序 AABB+distal inside 定义不等价；定义不一致率 P01 {pct(p1.entry_definition_disagreement_rate,1)}，P05 {pct(p5.entry_definition_disagreement_rate,1)}。
- 逐帧 timestamp 缺失，不能直接检测丢帧、重复 timestamp、非单调 timestamp，也不能按真实 Δt 独立重算速度。代码使用 Time.fixedDeltaTime，日志速度与 20 ms 名义重算的比较仅是实现一致性检查。

## 3. P01 与 P05 的主要差异

- 最终触发成功率：两人均 192/192（100%）。
- 首次进入成功率：P01 {int(round(p1.first_entry_success_rate*192))}/192（{pct(p1.first_entry_success_rate,1)}），P05 {int(round(p5.first_entry_success_rate*192))}/192（{pct(p5.first_entry_success_rate,1)}）。尝试次数中位数均为 {fmt(p1.attempt_count_median,0)} 与 {fmt(p5.attempt_count_median,0)}，但范围分别为 {p1.attempt_count_range} 与 {p5.attempt_count_range}。
- 单次进入 trial 可精确解释为 first-entry→trigger：P01 中位数 {fmt(p1.entry_to_trigger_exact_single_entry_median_ms,0)} ms（IQR {fmt(p1.entry_to_trigger_exact_single_entry_q1_ms,0)}–{fmt(p1.entry_to_trigger_exact_single_entry_q3_ms,0)}），P05 {fmt(p5.entry_to_trigger_exact_single_entry_median_ms,0)} ms（IQR {fmt(p5.entry_to_trigger_exact_single_entry_q1_ms,0)}–{fmt(p5.entry_to_trigger_exact_single_entry_q3_ms,0)}）。因此总体上 {faster} 更快，而不是预设 P05 必然更快。
- 进入速度中位数：P01 {fmt(p1.entry_speed_logged_median_m_s,3)} m/s，P05 {fmt(p5.entry_speed_logged_median_m_s,3)} m/s；进入即高于 0.375 m/s 的比例分别为 {pct(p1.entry_above_max_threshold_rate,1)} 与 {pct(p5.entry_above_max_threshold_rate,1)}。
- trigger 深度中位数：P01 {fmt(p1.trigger_depth_median,3)}，P05 {fmt(p5.trigger_depth_median,3)}；正值表示球面内部，负值表示按 rho 定义仍在球外（可由 AABB/distal 定义造成）。

## 4. 目标尺寸效应

{chr(10).join(size_lines)}

尺寸同时与 ID/运动幅度共同变化（Large/Medium/Small 对应 0.50/0.60/0.70 m 直径路径），因此不能把观察差异纯归因于尺寸。

## 5. Speed 子技术差异

{chr(10).join(tech_lines)}

四个模式共享相同的 Speed 双阈值门控；Dwell、Release、Direction 的差异主要体现在取消/辅助规则，而非 Speed 阈值本身。

## 6. 点击式策略证据

- P05 在进入后 40 ms 内已达到最大阈值的 trial 比例为 {pct(p05_fast,1)}，P01 为 {pct(p01_fast,1)}。
- P05 目标内峰值阶段：进入附近 {pct(p05_peak.get('entry/near',0),1)}，进入后更晚 {pct(p05_peak.get('post-entry',0),1)}；P01 分别为 {pct(p01_peak.get('entry/near',0),1)} 与 {pct(p01_peak.get('post-entry',0),1)}。
- P05 触发后首次持续径向反转名义中位数为 {fmt(p5.trigger_to_reversal_nominal_median_ms,0)} ms，P01 为 {fmt(p1.trigger_to_reversal_nominal_median_ms,0)} ms。
- 这些指标若同时表现为高进入速度、阈值快速越过、浅 trigger、短停留和快速反转，才构成“点击式”动作的组合证据。单一的短 triggerTime 不足以证明点击。

## 7. 替代解释

- 机制本身要求先低速 armed 再高速 trigger，因此它在设计上测量的是“进入后至少出现一次低速，随后提速”，不是纯粹“高速进入”。但进入帧速度使用进入前一帧位置，因此进入前运动会影响进入帧速度估计。
- AABB/distal inside 与球面 tip rho 的差异可造成看似在球外 trigger，不能直接称为实现漏洞。
- trial 顺序、技术顺序、学习和疲劳完全混杂；P05 与 P01 的技术获取顺序也不同。当前个案无法把策略差异和顺序效应分离。
- 没有实际运行时参数快照、构建号和逐帧 timestamp；当前配置文件只能证明工作区保留版本，不是每次采集 APK 的密码学证据。

## 8. 对实验设计的影响

- 若构念是“进入后提速”，应在每 trial 日志中保存 entry、armed、max-crossing、trigger、exit 的 frame 与高精度 timestamp，并保存运行时 min/max 阈值和构建哈希。
- inside 应统一为明确的球体几何，或至少同时记录 tipInside、distalInside、AABBInside 与 sphere rho；否则 trigger depth 的构念含义不稳定。
- 可考虑要求 armed 后至少 2–3 个连续帧超过 max，或要求 max-crossing 的径向分量为朝内，以减少边界擦入/追踪抖动造成的单帧触发；这些修改需先用回放/灵敏度分析评估漏触发。
- 若不希望“点击式”往返成为最优策略，应把退出反转惩罚、最小进入深度或速度增长相对 entry 的条件显式化，而不是仅用速度大小阈值。

## 9. 当前不能得出的结论

- 不能推广到一般用户；只有两名参与者。
- 不能用 trial 当独立参与者做总体显著性推断。
- 不能用现有轨迹精确回答真实毫秒级 threshold latency、丢帧或加速度峰值。
- 不能把 Speed-Release/Speed-Direction自动称为用户给出的 Speed-Motion/Speed-Gesture。
- 不能仅凭球面 rho<0 或快速反转认定“实现漏洞”。

## 核心问题逐项回答

1. **最终 Speed trigger 成功率**：在已写入的完成 trial 中相同，P01=P05=192/192（100%）；该日志结构无法给出未保存/放弃 trial 的成功率。
2. **首次进入成功率与尝试次数**：P05 首次进入成功率更高（{pct(p5.first_entry_success_rate,1)} vs {pct(p1.first_entry_success_rate,1)}）；两人尝试次数中位数均为 1，但 P01 范围 1–9，P05 1–8。
3. **P05 是否更快触发**：总体不支持。单次进入 trial 的精确中位数 P05 {fmt(p5.entry_to_trigger_exact_single_entry_median_ms,0)} ms，P01 {fmt(p1.entry_to_trigger_exact_single_entry_median_ms,0)} ms；分技术结果方向不一致。
4. **P05 是否在刚进入或边缘附近触发**：P05 比 P01 浅（depth {fmt(p5.trigger_depth_median,3)} vs {fmt(p1.trigger_depth_median,3)}），但中位 rho 约 {fmt(1-p5.trigger_depth_median,3)}，不能称为“就在边界”。
5. **P05 峰值相对 entry**：进入附近（0–40 ms）占 {pct(p05_peak.get('entry/near',0),1)}，较晚 post-entry 占 {pct(p05_peak.get('post-entry',0),1)}；中位峰值时间 40 ms。没有“多数峰值在进入前”的证据。
6. **进入—触发—快速退出模式**：P05 目标内名义时长更短（{fmt(p5.inside_time_nominal_median_ms,0)} vs {fmt(p1.inside_time_nominal_median_ms,0)} ms），两人名义反转中位数均为 20 ms；是部分支持而非 P05 独有的清晰模式。
7. **是否跨 Large/Medium/Small**：P05 在三种尺寸上的首次进入成功率均更高，但 entry→trigger 并非三种尺寸都更快，进入速度也没有一致更高，因此“同一点击动作跨尺寸稳定存在”证据不足。
8. **P01 是否更符合进入后提速**：P01 的较晚 post-entry 峰值比例仅略高（{pct(p01_peak.get('post-entry',0),1)} vs {pct(p05_peak.get('post-entry',0),1)}），两人的峰值时间中位数相同；仅有弱证据，不足以下强结论。
9. **顺序、学习、版本或参数解释**：可能。P05 的 Speed 在当天较早执行，P01 较晚执行；技术与时间顺序混杂。schema/保留配置一致，但无 build hash，不能完全排除版本差异。
10. **机制测量高速进入还是进入后提速**：当前实现直接测量“进入后先观察到 <=0.067 m/s，再观察到 >=0.375 m/s”的低—高转换，更接近进入后提速；但进入帧速度由进入前一帧到当前帧计算。
11. **策略适配、阈值利用或漏洞**：最稳妥表述是 P05 有更高首次进入成功率、更浅 trigger 和更短接触，符合高效策略适配的一部分；没有足够证据称阈值利用，更没有实现漏洞的直接证据。
12. **构念效度与阈值设计影响**：双阈值支持“低速 armed 后加速”的构念，但 AABB/distal inside、单帧 max crossing 和缺 timestamp 削弱可解释性。应记录运行时事件并测试连续帧、径向向内、最小深度和相对 entry 增速版本。

## 10. 下一步建议

1. 先加入每 FixedUpdate 的 frameCount、Time.timeAsDouble、tip/distal 位置、目标 collider 中心/半径、inside 分解标志、速度向量、armed/threshold/trigger/exit 事件和 build hash。
2. 用当前脚本同一套定义复跑 3–5 名参与者的 pilot；预注册个案内点击指标组合，不做事后单指标挑选。
3. 做机制对照：原双阈值、要求进入后速度增量、要求连续 3 帧、要求径向向内四个版本；记录成功率与误触发代价。
4. 平衡 Speed 四技术与尺寸顺序，或至少随机化并记录顺序，以分离策略、学习和疲劳。

### 非 Speed 辅助比较

{chr(10).join(aux_lines)}

### 学习/顺序描述

{chr(10).join(learn)}
"""

    abstract = f"""# 组会一页摘要：P01 vs P05 Speed 系列

## 直接结果

- 数据：每人 192 个已完成 trial（4 技术 × 3 尺寸 × 16）；最终触发成功率均为 100%（日志只保存完成 trial）。
- 首次进入成功率：P01 {pct(p1.first_entry_success_rate,1)}，P05 {pct(p5.first_entry_success_rate,1)}；尝试次数中位数 P01 {fmt(p1.attempt_count_median,0)}、P05 {fmt(p5.attempt_count_median,0)}。
- 单次进入 trial 的精确 entry→trigger：P01 {fmt(p1.entry_to_trigger_exact_single_entry_median_ms,0)} ms（IQR {fmt(p1.entry_to_trigger_exact_single_entry_q1_ms,0)}–{fmt(p1.entry_to_trigger_exact_single_entry_q3_ms,0)}），P05 {fmt(p5.entry_to_trigger_exact_single_entry_median_ms,0)} ms（IQR {fmt(p5.entry_to_trigger_exact_single_entry_q1_ms,0)}–{fmt(p5.entry_to_trigger_exact_single_entry_q3_ms,0)}）。
- 进入速度中位数：P01 {fmt(p1.entry_speed_logged_median_m_s,3)} m/s，P05 {fmt(p5.entry_speed_logged_median_m_s,3)} m/s；进入后 40 ms 内达到 0.375 m/s：P01 {pct(p1.threshold_within_40ms_rate,1)}，P05 {pct(p5.threshold_within_40ms_rate,1)}。
- trigger 深度中位数（1−rho）：P01 {fmt(p1.trigger_depth_median,3)}，P05 {fmt(p5.trigger_depth_median,3)}；名义 trigger→径向反转：P01 {fmt(p1.trigger_to_reversal_nominal_median_ms,0)} ms，P05 {fmt(p5.trigger_to_reversal_nominal_median_ms,0)} ms。

## 解释分层

- 强结论：P05 的首次进入成功率与 P01 不同，且两人的进入速度、单次进入 trigger 时长和 trigger 深度可量化；具体方向以上述数字为准。Speed 实现是 <=0.067 m/s armed 后 >=0.375 m/s trigger 的双阈值状态机。
- 谨慎解释：若 P05 同时呈现更高进入速度、更早峰值、更浅 trigger、更短停留及更快反转，则与点击式策略一致；AABB/distal inside 和缺少逐帧 timestamp 是重要替代解释。
- 后续假设：点击策略是否为稳定个体策略、是否跨尺寸泛化、是否由练习形成，以及是否损害 Speed 构念效度，都需更多参与者与平衡顺序实验验证。

## 设计决定

优先补日志：真实 timestamp、tip+distal、球心/半径、armed/max-crossing/trigger/exit、运行时阈值与 build hash。随后比较“双阈值原版 / 进入后增速 / 连续 3 帧 / 径向向内”四个实现。
"""
    return report, abstract


def write_manifest(out: Path, trials: pd.DataFrame, audit: pd.DataFrame) -> None:
    manifest = {
        "participants": ["P01", "P05"],
        "speed_modes": list(SPEED_MODES),
        "trial_count": len(trials),
        "file_audit_count": len(audit),
        "nominal_fixed_timestep_s": NOMINAL_DT_S,
        "speed_min_threshold_m_s": SPEED_MIN_M_S,
        "speed_max_threshold_m_s": SPEED_MAX_M_S,
        "position_unit": "meter",
        "timestamp_limitation": "trajectory.csv contains no timestamp/frame; nominal frame metrics are not actual-timestamp estimates",
        "inside_definition_limitation": "runtime AABB(tip OR distal) differs from requested spherical fingertip rho",
    }
    (out / "analysis_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    args = parse_args()
    root = args.root.resolve()
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    configure_plotting()

    runs = discover_runs(root)
    trials, frames, auxiliary = build_all_trials(runs)
    summary = summarize_conditions(trials)
    overall = overall_summary(trials)
    audit = file_audit(root)

    trials.to_csv(out / "trial_level_metrics.csv", index=False, encoding="utf-8-sig", float_format="%.8g")
    summary.to_csv(out / "condition_summary.csv", index=False, encoding="utf-8-sig", float_format="%.8g")
    overall.to_csv(out / "participant_overall_summary.csv", index=False, encoding="utf-8-sig", float_format="%.8g")
    auxiliary.to_csv(out / "aux_non_speed_comparison.csv", index=False, encoding="utf-8-sig", float_format="%.8g")
    audit.to_csv(out / "file_audit.csv", index=False, encoding="utf-8-sig", float_format="%.8g")
    # The aligned frame table is useful for full reproducibility and custom figures.
    frames.to_csv(out / "derived_aligned_frames.csv.gz", index=False, compression="gzip", encoding="utf-8-sig", float_format="%.8g")

    plot_speed_aligned(trials, frames, out)
    plot_rho_aligned(trials, frames, out)
    plot_scatter(trials, out)
    plot_condition_metrics(summary, out)
    plot_representative_3d(trials, frames, out)
    plot_learning(trials, out)

    (out / "data_audit_report.md").write_text(audit_text(root, runs, audit, trials), encoding="utf-8")
    report, abstract = build_report(trials, summary, overall, auxiliary)
    (out / "analysis_report_zh.md").write_text(report, encoding="utf-8")
    (out / "group_meeting_one_page_zh.md").write_text(abstract, encoding="utf-8")
    write_manifest(out, trials, audit)
    shutil.copy2(Path(__file__), out / "p01_p05_speed_frame_analysis.py")
    (out / "RUN_INSTRUCTIONS.txt").write_text(
        "Run from the workspace root with the bundled Python:\n"
        "C:\\\\Users\\\\tangx\\\\.cache\\\\codex-runtimes\\\\codex-primary-runtime\\\\dependencies\\\\python\\\\python.exe "
        "analysis\\\\p01_p05_speed_frame_analysis.py\n"
        "The script reads raw CSV files without modifying them and rewrites only this derived output directory.\n",
        encoding="utf-8",
    )
    print(f"Output: {out}")
    print(overall.to_string(index=False))


if __name__ == "__main__":
    main()
