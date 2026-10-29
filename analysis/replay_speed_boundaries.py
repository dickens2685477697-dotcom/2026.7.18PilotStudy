"""Replay recorded checks, then evaluate boundary interpolation separately.

No live Unity code, raw data, contact bounds, or speed thresholds are changed.
Only original entries are replayed; unlogged outside-outside contacts are unknown.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "analysis" / "_plot_deps" / "30hz_50hz_runtime"))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

DATA = ROOT / "30hz_50hz_analysis"
OUT = DATA / "results" / "offline_replay"
POS = ["indexX", "indexY", "indexZ"]
PREV = ["previousIndexX", "previousIndexY", "previousIndexZ"]
DIST = ["distalX", "distalY", "distalZ"]
CENTER = ["boundsCenterX", "boundsCenterY", "boundsCenterZ"]
EXTENT = ["boundsExtentX", "boundsExtentY", "boundsExtentZ"]
SIZES = {1: 90, 2: 60, 3: 30}
EPS = 1e-8


def vec(row, names):
    return np.asarray([row[n] for n in names], dtype=float)


def segment_box(p0, p1, center, extent):
    """Closed segment against the logged, axis-aligned bounds; return u range."""
    lo, hi = 0.0, 1.0
    for start, delta, c, radius in zip(p0, p1-p0, center, extent):
        if abs(delta) < 1e-14:
            if start < c-radius-EPS or start > c+radius+EPS:
                return None
        else:
            a, b = sorted(((c-radius-start)/delta, (c+radius-start)/delta))
            lo, hi = max(lo, a), min(hi, b)
            if lo > hi + EPS:
                return None
    return max(0., lo), min(1., hi)


def contact_components(p0, p1, d0, d1, center, extent):
    intervals = [x for x in [segment_box(p0, p1, center, extent),
                              segment_box(d0, d1, center, extent)] if x is not None]
    merged = []
    for lo, hi in sorted(intervals):
        if merged and lo <= merged[-1][1] + EPS:
            merged[-1] = (merged[-1][0], max(hi, merged[-1][1]))
        else:
            merged.append((lo, hi))
    return merged


def speed_crossing_fraction(v0, v1, threshold):
    return (threshold-v0)/(v1-v0) if v1 > v0 and v0 < threshold <= v1 else np.nan


def validate_geometry_kernel():
    c, r = np.zeros(3), np.ones(3)
    assert segment_box(np.zeros(3), np.array([2., 0, 0]), c, r) == (0., .5)
    assert segment_box(np.array([2., 0, 0]), np.array([2., 1, 0]), c, r) is None
    assert segment_box(np.zeros(3), np.zeros(3), c, r) == (0., 1.)
    assert segment_box(np.array([-2., 0, 0]), np.array([2., 0, 0]), c, r) == (.25, .75)
    assert segment_box(np.array([-2., 1, 0]), np.array([2., 1, 0]), c, r) == (.25, .75)
    # One joint leaves before the other enters: do not bridge the contact gap.
    merged = contact_components(np.zeros(3), np.array([4., 0, 0]),
                                 np.array([-4., 0, 0]), np.zeros(3), c, r)
    assert merged == [(0., .25), (.75, 1.)]
    assert np.isclose(speed_crossing_fraction(.2, .6, .4), .5)
    assert np.isnan(speed_crossing_fraction(.2, .3, .4))
    assert np.isnan(speed_crossing_fraction(.6, .2, .4))
    assert np.isclose(speed_crossing_fraction(.2, .4, .4), 1.)


def discrete_replay(checks, speed_column="decisionSpeed"):
    armed, arm_time, trigger_time = False, np.nan, np.nan
    for _, row in checks.iterrows():
        if row.reentryRequired or not row.enableTrigger:
            continue
        speed = row[speed_column]
        if not armed:
            if speed <= row.minSpeedThreshold:
                armed, arm_time = True, float(row.time)
            continue
        if row.allowHighSpeedTrigger and speed >= row.maxSpeedThreshold:
            trigger_time = float(row.time)
            break
    return {"triggered": bool(np.isfinite(trigger_time)), "armed": armed,
            "arm_time": arm_time, "trigger_time": trigger_time}


def prepare_filter(checks, samples, tau_ms):
    values, state = {}, None
    for _, row in samples.iterrows():
        alpha = 1 - np.exp(-row.motionDeltaTime / (tau_ms / 1000))
        state = float(row.decisionSpeed) if state is None else float(state + alpha*(row.decisionSpeed-state))
        values[int(row.motionSampleSequence)] = state
    q = checks.copy()
    raw_values = samples.set_index("motionSampleSequence").decisionSpeed
    assert np.allclose(q.motionSampleSequence.map(raw_values), q.decisionSpeed, atol=1e-9, rtol=0)
    q["filtered_speed"] = q.motionSampleSequence.astype(int).map(values)
    assert q.filtered_speed.notna().all()
    return q


def jitter_diagnostics(samples, exit_row, session, entry):
    # Check each entry only. Never concatenate positions belonging to new targets.
    points = samples.copy()
    if exit_row is not None:
        points = pd.concat([points, pd.DataFrame([exit_row])], ignore_index=True)
    records, windows = [], []
    p = points[POS].to_numpy(float)
    d = points[DIST].to_numpy(float)
    seq = points.motionSampleSequence.to_numpy(int)
    times = points.motionFixedTime.to_numpy(float)
    for i in range(1, len(points)):
        dt = times[i]-times[i-1]
        if seq[i]-seq[i-1] != 1 or not np.isclose(dt, points.iloc[i].motionDeltaTime, atol=1e-7):
            continue
        step = float(np.linalg.norm(p[i]-p[i-1]))
        if step > .1 and step/dt > 5:
            records.append({"session": session, "entrySequence": entry,
                            "case": int(points.iloc[i]["case"]), "hz": int(points.iloc[i].requestedSamplingHz),
                            "sample_sequence": int(seq[i]), "event": points.iloc[i].event,
                            "time_s": times[i], "step_mm": step*1000, "speed_m_s": step/dt,
                            "distal_step_mm": float(np.linalg.norm(d[i]-d[i-1])*1000),
                            "tip_distal_delta_difference_mm": float(np.linalg.norm((p[i]-p[i-1])-(d[i]-d[i-1]))*1000)})
    # A short alternating trace is an observation, not proof of sensor noise.
    # Five poses, 3 reversals, >=0.5 mm steps, <=10 mm total spatial span.
    # Only sub-trigger-speed windows are considered for the light-filter gate.
    for i in range(4, len(samples)):
        q = samples.iloc[i-4:i+1]
        if not np.all(np.diff(q.motionSampleSequence) == 1):
            continue
        a = q[POS].to_numpy(float)
        delta = np.diff(a, axis=0)
        length = np.linalg.norm(delta, axis=1)
        if np.any(length < .0005) or q.decisionSpeed.max() >= .375:
            continue
        cosine = np.sum(delta[:-1]*delta[1:], axis=1)/(length[:-1]*length[1:])
        span = float(np.max(np.linalg.norm(a[:, None]-a[None, :], axis=2)))
        if np.all(cosine <= -.5) and span <= .010:
            windows.append({"session": session, "entrySequence": entry,
                            "case": int(q.iloc[0]["case"]), "hz": int(q.iloc[0].requestedSamplingHz),
                            "start_sequence": int(q.iloc[0].motionSampleSequence),
                            "end_sequence": int(q.iloc[-1].motionSampleSequence),
                            "start_time_s": float(q.iloc[0].motionFixedTime),
                            "end_time_s": float(q.iloc[-1].motionFixedTime),
                            "spatial_span_mm": span*1000,
                            "path_length_mm": float(length.sum()*1000),
                            "net_displacement_mm": float(np.linalg.norm(a[-1]-a[0])*1000),
                            "speed_min": float(q.decisionSpeed.min()), "speed_max": float(q.decisionSpeed.max()),
                            "low_threshold_crossings": int(np.sum(np.diff((q.decisionSpeed <= .067).astype(int)) != 0))})
    return records, windows


def repeated_pose_diagnostics(samples, checks, session, entry):
    records = []
    q = samples.reset_index(drop=True)
    for i in range(1, len(q)):
        previous, row = q.iloc[i-1], q.iloc[i]
        if row.decisionSpeed != 0:
            continue
        consecutive = row.motionSampleSequence == previous.motionSampleSequence+1
        same_pose = np.linalg.norm(vec(row, POS)-vec(previous, POS)) < 1e-12
        duplicate_frame = row.frame == previous.frame
        if consecutive and same_pose and duplicate_frame:
            records.append({"session": session, "entrySequence": entry, "case": int(row["case"]),
                            "hz": int(row.requestedSamplingHz), "sample_sequence": int(row.motionSampleSequence),
                            "time_s": float(row.motionFixedTime), "render_frame": int(row.frame),
                            "fixed_time_difference_ms": (row.motionFixedTime-previous.motionFixedTime)*1000,
                            "realtime_difference_ms": (row.realtime-previous.realtime)*1000,
                            "previous_speed_m_s": float(previous.decisionSpeed),
                            "following_speed_m_s": float(q.iloc[i+1].decisionSpeed) if i+1 < len(q) else np.nan,
                            "newly_armed_at_zero": bool((checks.motionSampleSequence.eq(row.motionSampleSequence)
                                                       & checks.speedMinArmed.eq(0)).any()),
                            "tip_and_distal_repeated": bool(np.linalg.norm(vec(row, DIST)-vec(previous, DIST)) < 1e-12)})
    return records


def make_visuals(e, summary, repeats, filters, groups):
    fonts = {f.name for f in font_manager.fontManager.ttflist}
    font = next((f for f in ["Microsoft YaHei", "SimHei", "Noto Sans CJK SC"] if f in fonts), "DejaVu Sans")
    plt.rcParams.update({"font.family": font, "font.size": 10, "axes.unicode_minus": False,
                         "axes.spines.top": False, "axes.spines.right": False,
                         "axes.titlesize": 12, "axes.titleweight": "bold"})
    fig, axes = plt.subplots(2, 2, figsize=(13.8, 10.5))
    fig.subplots_adjust(top=.85, bottom=.17, left=.08, right=.96, wspace=.30, hspace=.54)
    fig.suptitle("边界模型可解释 22/69 次失败，轻度滤波暂未显示补救收益", x=.08, y=.97, ha="left", fontsize=18)
    fig.text(.08, .917, "原始判定 261 次进入全部复现。22 次使用局部连续边界模型；排除进入首点跳变后为 19 次。", color="#555555", fontsize=11)
    ax = axes[0, 0]
    h = summary[summary.grouping.eq("hz")]
    a, b = h.linear_explained_guarded.to_numpy(), h.unexplained_linear_guarded.to_numpy()
    ax.barh([0, 1], a, color="#316A9B", height=.48, label="线性模型可解释")
    ax.barh([0, 1], b, left=a, color="#C5C8CD", height=.48, label="仍不能解释")
    for i, (_, row) in enumerate(h.iterrows()):
        ax.text(a[i]/2, i, str(int(a[i])), ha="center", va="center", color="white")
        ax.text(a[i]+b[i]/2, i, str(int(b[i])), ha="center", va="center")
        ax.text(row.original_failures+.6, i, f"{row.linear_fraction_of_failures_guarded:.1%}", va="center")
    ax.set(yticks=[0, 1], yticklabels=["30 Hz", "50 Hz"], xlim=(0, 44), xlabel="原始失败进入次数", title="A  线性边界模型解释约三成失败")
    ax.invert_yaxis()
    ax.legend(frameon=False, loc="lower left", bbox_to_anchor=(0, -.29), ncol=2, fontsize=9)
    ax = axes[0, 1]
    q = e[e.coarse_boundary_candidate].sort_values("boundary_to_threshold_margin_ms")
    for i, (_, row) in enumerate(q.iterrows()):
        color = "#9C3636" if row.gross_jump_in_recorded_entry else ("#316A9B" if row.hz == 30 else "#B66B2F")
        ax.scatter(row.boundary_to_threshold_margin_ms, i, color=color,
                   marker="x" if row.gross_jump_in_recorded_entry else "o", s=32)
    ax.axvline(0, color="#555555", linewidth=1)
    ax.set(yticks=[], xlabel="离开时刻 − 阈值插值时刻（ms）", title="B  6 个候选先离开、后达到阈值")
    ax.text(.03, .98, "蓝：30 Hz；橙：50 Hz；红叉：退出跳变\n正值：模型支持；负值：模型不支持", transform=ax.transAxes, va="top", fontsize=9)
    ax = axes[1, 0]
    totals = filters.groupby("tau_ms")[["original_success_now_right_censored", "original_triggered"]].sum()
    kept = (totals.original_triggered-totals.original_success_now_right_censored).to_numpy()
    censored = totals.original_success_now_right_censored.to_numpy()
    ax.barh([0, 1], kept, height=.5, color="#447E6C", label="原成功在截止前复现")
    ax.barh([0, 1], censored, left=kept, height=.5, color="#C5C8CD", label="截止前未复现：右截尾")
    for i in range(2):
        ax.text(kept[i]/2, i, str(int(kept[i])), ha="center", va="center", color="white")
        ax.text(kept[i]+censored[i]/2, i, str(int(censored[i])), ha="center", va="center")
        ax.text(197, i, "补回失败 0", va="center", fontsize=9)
    ax.set(yticks=[0, 1], yticklabels=["EMA 10 ms", "EMA 20 ms"], xlim=(0, 232), xlabel="原始成功进入（共 192 次）", title="C  独立滤波评估受日志截尾限制")
    ax.invert_yaxis()
    ax.legend(frameon=False, loc="lower left", bbox_to_anchor=(-.02, -.30), fontsize=9)
    ax = axes[1, 1]
    event = repeats[repeats.newly_armed_at_zero & repeats.previous_speed_m_s.gt(.2)].iloc[0]
    _, _, samples = next(g for g in groups if g[0]["session"] == event.session and g[0]["entrySequence"] == event.entrySequence)
    samples = samples.reset_index(drop=True)
    k = int(np.flatnonzero(samples.motionSampleSequence.eq(event.sample_sequence))[0])
    view = samples.iloc[max(0, k-2):k+4]
    x = (view.motionFixedTime-event.time_s)*1000
    ax.plot(x, view.decisionSpeed, "o-", color="#316A9B", label="原始速度")
    for tau, color in [(10, "#A4752E"), (20, "#5A806C")]:
        filtered_view = prepare_filter(samples, samples, tau).loc[view.index]
        ax.plot(x, filtered_view.filtered_speed, ".--", color=color, label=f"EMA {tau} ms")
    ax.axhline(.067, color="#777777", linestyle=":", label="低速阈值 0.067")
    ax.annotate("重复位置 → 速度 0 → 就绪", (0, 0), xytext=(0, .33), fontsize=9,
                arrowprops={"arrowstyle": "->", "color": "#777777"})
    ax.text(.03, .97, f"同帧采样固定时间差 20 ms\n实际日志时间差 {event.realtime_difference_ms:.3f} ms", transform=ax.transAxes, va="top", fontsize=9)
    ax.set(xlabel="相对零值采样的固定时间（ms）", ylabel="速度（m/s）", ylim=(-.025, max(.52, view.decisionSpeed.max()*1.1)), title="D  已确认重复采样造成的伪零值")
    ax.legend(frameon=False, fontsize=8, loc="upper left", bbox_to_anchor=(-.02, -.29), ncol=2)
    fig.text(.08, .028, "来源：四次 speed-boundary-debug / speed-entry-summary。边界仅补判已记录的离开区间，低速就绪规则不变。\n边界解释量依赖插值假设，并非已验证恢复量。滤波独立改变速度，接触几何不变；右截尾不能当作新增失败。", fontsize=9.5, color="#555555", linespacing=1.6)
    fig.savefig(OUT / "replay_comparison.png", dpi=170)
    fig.savefig(OUT / "replay_comparison.svg")
    plt.close(fig)


def write_report(e, summary, repeats, filters, trial, audit):
    def table(df, columns):
        lines = ["| " + " | ".join(x[1] for x in columns) + " |", "| " + " | ".join("---" for _ in columns) + " |"]
        for _, row in df.iterrows():
            lines.append("| " + " | ".join(format(row[k], fmt) if fmt else str(row[k]) for k, _, fmt in columns) + " |")
        return "\n".join(lines)
    fs = []
    for (tau, hz), q in filters.groupby(["tau_ms", "hz"]):
        fs.append({"tau_ms": tau, "hz": hz, "original_successes": int(q.original_triggered.sum()),
                   "reproduced": int((q.original_triggered & q.ema_triggered_before_log_end).sum()),
                   "right_censored": int(q.original_success_now_right_censored.sum()),
                   "new_triggers": int(q.original_failure_new_trigger.sum())})
    filter_summary = pd.DataFrame(fs)
    filter_summary.to_csv(OUT / "light_filter_summary.csv", index=False, encoding="utf-8-sig")
    hz_table = table(summary[summary.grouping.eq("hz")], [
        ("group", "采样 Hz", ""), ("original_failures", "原始失败", ".0f"),
        ("linear_explained_guarded", "线性边界模型解释", ".0f"),
        ("linear_fraction_of_failures_guarded", "占失败比例", ".1%"),
        ("mean_model_explained_guarded", "宽松均速模型解释", ".0f")])
    size_table = table(summary[summary.grouping.eq("target")], [
        ("group", "直径 mm", ""), ("original_failures", "原始失败", ".0f"),
        ("linear_explained_guarded", "线性边界模型解释", ".0f"),
        ("linear_fraction_of_failures_guarded", "占失败比例", ".1%")])
    filter_table = table(filter_summary, [("tau_ms", "EMA 时间常数 ms", ".0f"), ("hz", "采样 Hz", ".0f"),
        ("original_successes", "原成功", ".0f"), ("reproduced", "截止前复现", ".0f"),
        ("right_censored", "截止前未复现（右截尾）", ".0f"), ("new_triggers", "原失败新增触发", ".0f")])
    margin = e[e.linear_crossing_recovered_guarded].boundary_to_threshold_margin_ms
    strict = int(e.linear_recovered_strict_history.sum())
    candidates = e[e.coarse_boundary_candidate & ~e.linear_crossing_recovered_raw]
    dt_median = repeats.realtime_difference_ms.median()
    arming = int(repeats.newly_armed_at_zero.sum())
    report = f"""# speed 离线重放：离散判定、跨采样边界与独立滤波

原始状态机在 **261/261 次进入**上完全复现，包括 192 次触发与 69 次退出未触发，低速就绪时间和触发时间也全部匹配。仅对失败的离开区间补判、保持原低速就绪规则，排除退出时的大幅位置跳变后，线性模型可解释 **22/69 = 31.9%** 的失败。宽松均速模型可解释 **28/69 = 40.6%**。进一步排除进入首采样也发生大幅跳变的完整 entry，线性模型剩 **{strict}/69 = {strict/69:.1%}**。

这些是不同建模与质量筛选规则下的解释量，不是真实可恢复率的置信区间或严格上下界。没有修改 Unity、速度阈值、目标尺寸或原始日志。

![重放比较](replay_comparison.png)

## 1. 基线与输入核验

沿原日志顺序重放 check：进入时未就绪，速度 ≤0.067 m/s 后就绪，后续速度 ≥0.375 m/s 且 enableTrigger、reentryRequired、allowHighSpeedTrigger 门控允许时触发。按 entryExperimentStarted=1 筛选正式目标进入。重复渲染 check 保留用于精确复现；滤波只按新 motionSampleSequence 更新。

4,834 个内侧运动采样点的接触标记均已用原始 AABB bounds 与指尖/远端关节位置独立重建；速度由当前位置减 previousIndex 再除 motionDeltaTime 独立复算通过。几何核覆盖平行、静止、穿越、贴面和双关节之间的接触间隙等测试。69 个离开区间均满足运动采样连续、固定时间差正确、previousIndex 匹配、不变 bounds、有效 pose 和触发门控检查。

## 2. 边界模型的具体含义

分别将指尖和远端关节的相邻位置连成线段，与日志 AABB 求交，取两者接触区间的并集，再保留包含最后内侧采样的连续接触段。若一个关节离开后另一关节才进入，中间空隙不视为持续接触。所有补判都要求在该区间开始前已经按原算法低速就绪。

**线性阈值时刻模型**：位置在两采样点间线性变化，同时对记录的速度端点做线性插值。令 u 为区间进度，则达到高速的比例 `u_v=(0.375-v0)/(v1-v0)`；只有这个时刻不晚于连续接触结束时刻，才补判触发。记录速度是区间差分速度，把它当作端点值插值是离线假设，不能据此确定真实的连续瞬时速度。

**区间均速模型（宽松敏感性）**：将退出采样的差分速度分配给整个跨界区间；只要均速达阈值且该区间有连续接触，就补判。这种分配更宽松，也可能把实际上离开之后才达到的高速提前归因。

原内侧检查和原成功结局保留，只增加离开区间补判。未推断两端都在外面但中间完整穿过目标的未记录接触，也未补判跨界区间中新的低速就绪。

## 3. 对失败的解释量

{hz_table}

31 个粗略的离开帧高速候选中，25 个通过线性时刻检查，其中 3 个退出区间发生大幅跳变，排除后为 22 个。宽松模型接受全部 31 个，排除同样 3 个后为 28 个。不能把离开帧速度高就直接算成漏触发：其余 **6 个非跳变候选均来自 50 Hz**，在线性模型中，达到阈值比离开晚约 **2.71–6.96 ms**。

22 个结果的阈值领先边界余量中位数为 **{margin.median():.2f} ms**，范围 {margin.min():.2f}–{margin.max():.2f} ms。其中 {int((margin < 1).sum())} 个余量不足 1 ms；若要求至少 1 ms 余量，解释数为 {int((margin >= 1).sum())}/69。这只是模型敏感性检查，不能当作 SDK 精度估计。

按目标条件：

{size_table}

线性模型仍不能解释 **47 次**失败：27 次从未低速就绪，11 次已就绪但连离开采样也未达到高速，6 次阈值时刻晚于边界，3 次退出区间大幅跳变。6 个退出跳变中的另 3 个包含在未就绪的 27 次内，不重复计数。

举例：第一次 30 Hz 的 case 1、entry 2，阈值约在最后内侧采样后 9.15 ms，离开约在 23.34 ms，模型支持补判；第一次 50 Hz 的 case 18、entry 26，离开约在 2.67 ms，阈值约在 5.38 ms，模型不支持补判。逐条比例、时间余量与排除原因均见 entry_replay.csv。

22 个解释 entry 分布在 18 个试次，13 个原失败的首次进入变为模型触发。冻结原始动作轨迹时，30 Hz 首次进入成功数由 75/96 变为模型的 84/96，50 Hz 由 79/96 变为 83/96。实际提前选中会改变后续动作和重试，这些不能当作上线后的实测成功率或总时间节省。

## 4. 抖动证据与采样时序

**大幅跳变**：6 个退出区间的指尖单步位移为 510–641 mm、差分速度 15.3–32.1 m/s；远端关节也同步移动约 518–624 mm，SDK 有效标记仍为真。此外，7 次进入首采样的 previousIndex 至当前位置也有 >100 mm 且 >5 m/s 的步长，缺少上一远端关节的完整记录，单独标记。6 个退出跳变和 7 个进入首点大步长共 13 段，不应作为正常运动来直接外推。

主结果只排除退出区间局部跳变；若进一步排除包含上述进入首点大步长的整个 entry，线性解释数从 22 降至 **{strict}**。这项更严格的历史筛选结果也写入逐进入明细，避免隐藏质量规则对结论的影响。

**持续小幅位置往返**：未发现满足“连续 5 点、每步 ≥0.5 mm、3 次转向余弦均 ≤−0.5、空间跨度 ≤10 mm、最高速度 <0.375 m/s”的窗口。这不能证明没有噪声，只说明现有日志不足以把持续小幅位置抖动当作主要原因。

**速度时序伪影已确认**：两次 50 Hz 会话分别有 26、29 次零速度，共 **55 次，涉及 49 次进入**。所有这些采样都与前一采样处于同一渲染帧，指尖和远端关节位置均完全相同。固定时间差为 20 ms，实际日志时间差中位数只有 **{dt_median:.3f} ms**（范围 {repeats.realtime_difference_ms.min():.3f}–{repeats.realtime_difference_ms.max():.3f} ms）。其中 **{arming} 次**就在这个零值采样进入低速就绪；30 Hz 没有同类零值。

日志直接支持“重复 pose 被记为新的固定步长运动采样，形成速度伪零值”的时序问题，不能把这些零值直接视为真实停手。这个可重复结构证据先于滤波评估得到确认，与大幅跳变和持续小幅位置往返分开记录。

## 5. 轻度滤波的独立评估

保持原始离散几何，只滤速度标量，不叠加边界补判。因果 EMA 为 `f = f_prev + (1-exp(-dt/tau))*(v-f_prev)`；tau=10/20 ms，dt 为各自固定步长。每个新运动采样更新一次，重复 check 不更新。entry 前缺少完整同源速度历史，故每个 entry 用首个原始速度初始化；这不等同于充分预热、持续运行的线上滤波器。

{filter_table}

10 ms EMA 在原 192 次成功中复现 175 次，17 次在日志截止前未复现；20 ms 复现 133 次，59 次未复现。两档都未在原来的 69 次失败内产生新触发。共同复现的成功仍发生在原检查时刻。

**成功日志在原触发时截止**，所以未复现者属于右截尾：不知道继续运行是否延迟触发、会延迟多久或是否已经离开。不能把 17/59 次直接当作新增失败，也不能据此计算完整滤波后成功率或平均延迟。有限记录内没有补救收益，且有阈值延后或就绪改变风险，暂不支持直接加入轻度滤波。

## 6. 后续优先级与解释限制

先验证带采样有效性检查的边界补判，并核对同帧 FixedUpdate 追赶与 SDK pose 的更新时间，区分新 pose 与重复读取。轻度滤波不能替代运动采样语义的修复，也不能解决半米量级的跳变。本次没有修改在线代码。

边界补判不能解决未就绪和真正晚于边界的高速动作。现有任务缺少独立非意图动作真值，误触代价仍需线上验证。每频率仅两次会话，实验顺序与熟练度仍影响跨频率比较，不对数千帧做独立样本显著性推断。

## 7. 文件与复现

- [逐进入判定与排除原因](entry_replay.csv)、[按频率/会话/尺寸汇总](replay_summary.csv)
- [冻结轨迹的逐试次结果](trial_replay.csv)
- [退出区间跳变](pose_jumps.csv)、[同帧重复 pose](repeated_pose_samples.csv)
- [独立轻度滤波明细](light_filter_replay.csv)、[滤波汇总](light_filter_summary.csv)
- [核验与原始文件 SHA-256](replay_audit.json)
- [重放脚本](../../../analysis/replay_speed_boundaries.py)

原始判定输入为四次 speed-boundary-debug 与 speed-entry-summary；原始文件从未改写。具备 NumPy、pandas、Matplotlib 的 Python 环境可执行 `python analysis/replay_speed_boundaries.py` 重建本目录结果。
"""
    (OUT / "replay_report_zh.md").write_text(report, encoding="utf-8")


def run():
    validate_geometry_kernel()
    output, all_jumps, all_jitter, all_repeats, groups, raw_hashes = [], [], [], [], [], []
    for folder in sorted(DATA.glob("20261022-*")):
        b = pd.read_csv(folder / f"{folder.name}-speed-boundary-debug.csv")
        ends = pd.read_csv(folder / f"{folder.name}-speed-entry-summary.csv")
        ends = ends[ends.entryExperimentStarted.eq(1) & ends.source.eq("target") & ends.isMineBall.eq(0)]
        b["log_order"] = np.arange(len(b))
        for file in folder.glob("*.csv"):
            raw_hashes.append({"path": file.relative_to(ROOT).as_posix(),
                               "sha256": hashlib.sha256(file.read_bytes()).hexdigest()})
        for _, end in ends.iterrows():
            q = b[b.entrySequence.eq(end.entrySequence)].sort_values("log_order")
            checks = q[q.event.eq("check")]
            samples = q[q.event.eq("sample")]
            assert not samples.duplicated("motionSampleSequence").any()
            assert len(samples) == end.insideSampleCount
            # Independently reconstruct the geometry and velocity from logged poses.
            p = samples[POS].to_numpy(float)
            d = samples[DIST].to_numpy(float)
            center = samples[CENTER].to_numpy(float)
            extent = samples[EXTENT].to_numpy(float)
            assert np.array_equal(np.all(np.abs(p-center) <= extent+1e-8, axis=1), samples.tipInside.astype(bool))
            assert np.array_equal(np.all(np.abs(d-center) <= extent+1e-8, axis=1), samples.distalInside.astype(bool))
            computed_speed = np.linalg.norm(p-samples[PREV].to_numpy(float), axis=1)/samples.motionDeltaTime.to_numpy(float)
            assert np.allclose(computed_speed, samples.decisionSpeed, atol=1e-5, rtol=0)
            base = discrete_replay(checks)
            assert base["triggered"] == (end.event == "trigger"), (folder.name, end.entrySequence)
            assert base["armed"] == bool(end.armedEver), (folder.name, end.entrySequence, "armed")
            if base["triggered"]:
                assert np.isclose(base["trigger_time"], end.time, atol=1e-9, rtol=0)
            if base["armed"]:
                assert np.isclose((base["arm_time"]-end.entryTime)*1000, end.armedLatencyMs, atol=1e-6, rtol=0)
            exit_row = end if end.event == "exit" else None
            jumps, jitter = jitter_diagnostics(samples, exit_row, folder.name, int(end.entrySequence))
            all_jumps.extend(jumps)
            all_jitter.extend(jitter)
            all_repeats.extend(repeated_pose_diagnostics(samples, checks, folder.name, int(end.entrySequence)))
            rec = {"session": folder.name, "entrySequence": int(end.entrySequence),
                   "case": int(end["case"]), "id": int(end.id), "target_diameter_mm": SIZES[int(end.id)],
                   "hz": int(end.requestedSamplingHz), "observed_outcome": end.event,
                   "reason": end.reason, "discrete_triggered": base["triggered"],
                   "discrete_armed": base["armed"], "baseline_matches": True,
                   "original_trigger_time_s": base["trigger_time"],
                   "entry_time_s": float(end.entryTime), "exit_time_s": float(end.time) if exit_row is not None else np.nan,
                   "coarse_boundary_candidate": bool(end.boundaryHighSpeedCandidate),
                   "gross_jump_in_recorded_entry": bool(jumps),
                   "first_sample_large_step": bool(samples.iloc[0].decisionSpeed > 5 and
                       np.linalg.norm(vec(samples.iloc[0], POS)-vec(samples.iloc[0], PREV)) > .1),
                   "oscillatory_windows": len(jitter), "interval_valid": False,
                   "linear_crossing_recovered_raw": False, "linear_crossing_recovered_guarded": False,
                   "interval_mean_recovered_raw": False, "interval_mean_recovered_guarded": False,
                   "linear_trigger_time_s": np.nan, "interval_mean_trigger_time_s": np.nan,
                   "boundary_fraction": np.nan, "speed_crossing_fraction": np.nan,
                   "boundary_to_threshold_margin_ms": np.nan, "boundary_step_mm": np.nan,
                   "exit_speed_m_s": np.nan, "last_inside_speed_m_s": float(samples.iloc[-1].decisionSpeed),
                   "interval_exclusion": "not_a_failed_entry" if exit_row is None else ""}
            if exit_row is not None:
                previous = samples.iloc[-1]
                dt = float(end.motionFixedTime-previous.motionFixedTime)
                p0, p1, d0, d1 = vec(previous, POS), vec(end, POS), vec(previous, DIST), vec(end, DIST)
                center, extent = vec(previous, CENTER), vec(previous, EXTENT)
                exclusions = []
                if end.motionSampleSequence != previous.motionSampleSequence+1 or not np.isclose(dt, end.motionDeltaTime, atol=1e-7):
                    exclusions.append("non_adjacent_samples")
                if not np.allclose(vec(end, PREV), p0, atol=2e-7, rtol=0):
                    exclusions.append("previous_tip_mismatch")
                if not np.allclose(center, vec(end, CENTER), atol=1e-7, rtol=0) or not np.allclose(extent, vec(end, EXTENT), atol=1e-7, rtol=0):
                    exclusions.append("bounds_changed")
                if not (end.tipPoseValid and end.distalPoseValid and previous.tipPoseValid and previous.distalPoseValid) or end.trackingLossObserved:
                    exclusions.append("tracking_invalid_or_gap")
                if not (end.enableTrigger and end.allowHighSpeedTrigger and not end.reentryRequired):
                    exclusions.append("trigger_gate_blocked")
                intervals = contact_components(p0, p1, d0, d1, center, extent)
                initial = next((x for x in intervals if x[0] <= EPS), None)
                if initial is None:
                    exclusions.append("no_contact_at_last_inside_pose")
                rec["interval_valid"] = not exclusions
                rec["interval_exclusion"] = ";".join(exclusions)
                rec["boundary_step_mm"] = float(np.linalg.norm(p1-p0)*1000)
                rec["exit_speed_m_s"] = float(end.decisionSpeed)
                if not exclusions:
                    u_exit = initial[1]
                    v0, v1, threshold = float(previous.decisionSpeed), float(end.decisionSpeed), float(end.maxSpeedThreshold)
                    u_cross = speed_crossing_fraction(v0, v1, threshold)
                    rec["boundary_fraction"] = u_exit
                    rec["speed_crossing_fraction"] = u_cross
                    if np.isfinite(u_cross):
                        rec["boundary_to_threshold_margin_ms"] = (u_exit-u_cross)*dt*1000
                    armed_before_segment = base["armed"] and base["arm_time"] <= previous.time + EPS
                    linear = bool(armed_before_segment and np.isfinite(u_cross) and u_cross <= u_exit+EPS)
                    interval_mean = bool(armed_before_segment and v1 >= threshold and u_exit > EPS)
                    rec["linear_crossing_recovered_raw"] = linear
                    rec["linear_crossing_recovered_guarded"] = linear and not jumps
                    rec["interval_mean_recovered_raw"] = interval_mean
                    rec["interval_mean_recovered_guarded"] = interval_mean and not jumps
                    if linear:
                        rec["linear_trigger_time_s"] = float(previous.motionFixedTime+u_cross*dt)
                    if interval_mean:
                        rec["interval_mean_trigger_time_s"] = float(previous.motionFixedTime)
            output.append(rec)
            groups.append((rec, checks, samples))
    OUT.mkdir(exist_ok=True)
    result = pd.DataFrame(output)
    jumps = pd.DataFrame(all_jumps)
    jitter = pd.DataFrame(all_jitter)
    repeats = pd.DataFrame(all_repeats)
    # Require repeated oscillation across entries, rather than a single gross jump.
    jitter_entries = len(jitter[["session", "entrySequence"]].drop_duplicates()) if len(jitter) else 0
    jitter_sessions = jitter.session.nunique() if len(jitter) else 0
    repeated_entries = len(repeats[["session", "entrySequence"]].drop_duplicates()) if len(repeats) else 0
    repeated_sessions = repeats.session.nunique() if len(repeats) else 0
    filter_gate = (jitter_entries >= 5 and jitter_sessions >= 2) or (repeated_entries >= 5 and repeated_sessions >= 2)
    filtered = []
    if filter_gate:
        for rec, checks, samples in groups:
            for tau in [10, 20]:
                replay = discrete_replay(prepare_filter(checks, samples, tau), "filtered_speed")
                filtered.append({"session": rec["session"], "entrySequence": rec["entrySequence"],
                                 "case": rec["case"], "hz": rec["hz"], "tau_ms": tau,
                                 "original_triggered": rec["discrete_triggered"],
                                 "original_outcome": rec["observed_outcome"],
                                 "ema_triggered_before_log_end": replay["triggered"],
                                 "ema_armed_before_log_end": replay["armed"],
                                 "common_trigger_time_shift_ms": (replay["trigger_time"]-rec["original_trigger_time_s"])*1000,
                                 "original_success_now_right_censored": rec["discrete_triggered"] and not replay["triggered"],
                                 "original_failure_new_trigger": not rec["discrete_triggered"] and replay["triggered"]})
    filters = pd.DataFrame(filtered)
    summaries = []
    for grouping, group_keys in [("all", []), ("hz", ["hz"]), ("target", ["target_diameter_mm"]), ("session", ["session"])]:
        iterable = [("all", result)] if not group_keys else result.groupby(group_keys[0], sort=True)
        for key, q in iterable:
            failures = q[~q.discrete_triggered]
            summaries.append({"grouping": grouping, "group": key, "entries": len(q),
                              "original_triggers": int(q.discrete_triggered.sum()), "original_failures": len(failures),
                              "coarse_candidates": int(failures.coarse_boundary_candidate.sum()),
                              "valid_exit_intervals": int(failures.interval_valid.sum()),
                              "linear_explained_raw": int(failures.linear_crossing_recovered_raw.sum()),
                              "linear_explained_guarded": int(failures.linear_crossing_recovered_guarded.sum()),
                              "linear_fraction_of_failures_guarded": float(failures.linear_crossing_recovered_guarded.mean()),
                              "mean_model_explained_raw": int(failures.interval_mean_recovered_raw.sum()),
                              "mean_model_explained_guarded": int(failures.interval_mean_recovered_guarded.sum()),
                              "unexplained_linear_guarded": int((~failures.linear_crossing_recovered_guarded).sum()),
                              "gross_jump_entries": int(q.gross_jump_in_recorded_entry.sum())})
    summary = pd.DataFrame(summaries)
    result["linear_recovered_strict_history"] = (result.linear_crossing_recovered_guarded
                                                   & ~result.first_sample_large_step)
    source_summary = []
    for (session, case), q in result.groupby(["session", "case"], sort=True):
        q = q.sort_values("entrySequence")
        first = q.iloc[0]
        source_summary.append({"session": session, "case": case, "hz": int(first.hz),
                               "original_entry_count": len(q), "original_first_entry_success": bool(first.discrete_triggered),
                               "linear_explained_failed_entry_in_trial": bool(q.linear_crossing_recovered_guarded.any()),
                               "linear_first_entry_success_model": bool(first.discrete_triggered or first.linear_crossing_recovered_guarded),
                               "mean_model_first_entry_success": bool(first.discrete_triggered or first.interval_mean_recovered_guarded)})
    trial = pd.DataFrame(source_summary)
    for name, df in [("entry_replay", result), ("replay_summary", summary), ("trial_replay", trial),
                     ("pose_jumps", jumps), ("oscillatory_windows", jitter), ("repeated_pose_samples", repeats)]:
        # Empty diagnostics still get an explicit, parseable schema.
        if not len(df.columns):
            df = pd.DataFrame(columns=["session", "entrySequence"])
        df.to_csv(OUT / f"{name}.csv", index=False, encoding="utf-8-sig")
    if filter_gate:
        filters.to_csv(OUT / "light_filter_replay.csv", index=False, encoding="utf-8-sig")
    audit = {"baseline_entries": len(result), "baseline_outcomes_matched": int(result.baseline_matches.sum()),
             "baseline_arm_times_and_trigger_times_matched": True,
             "geometry_kernel_cases_passed": 6, "threshold_kernel_cases_passed": 4,
             "all_4834_inside_pose_contact_flags_and_velocity_formulas_verified": True,
             "raw_sources": raw_hashes,
             "jump_rule": "consecutive poses: tip step >100 mm AND speed >5 m/s; flag whole observed entry",
             "jitter_rule": "5 consecutive inside poses; 4 steps each >=0.5 mm; all 3 turn cosines <=-0.5; span <=10 mm; speed max <0.375 m/s",
             "filter_gate_rule": "either oscillatory windows OR same-render-frame repeated pose zero-speed samples in >=5 entries and >=2 sessions",
             "jitter_entries": jitter_entries, "jitter_sessions": int(jitter_sessions),
             "repeated_pose_events": len(repeats), "repeated_pose_entries": repeated_entries,
             "first_sample_large_steps": int(result.first_sample_large_step.sum()),
             "repeated_pose_sessions": int(repeated_sessions), "filter_gate_passed": bool(filter_gate)}
    (OUT / "replay_audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    make_visuals(result, summary, repeats, filters, groups)
    write_report(result, summary, repeats, filters, trial, audit)
    print(summary.to_string(index=False))
    print("JUMPS", jumps.to_dict("records"))
    print("JITTER", {"windows": len(jitter), "entries": jitter_entries, "sessions": int(jitter_sessions), "filter_gate": filter_gate})
    print("REPEATED_POSE", {"events": len(repeats), "entries": repeated_entries, "sessions": int(repeated_sessions),
                            "new_arming_events": int(repeats.newly_armed_at_zero.sum()) if len(repeats) else 0})
    if len(jitter):
        print(jitter.to_string(index=False))
    if filter_gate:
        print("FILTER", filters.groupby(["tau_ms", "hz"])[["ema_triggered_before_log_end", "original_success_now_right_censored", "original_failure_new_trigger"]].sum().to_string())
    return result, summary, jumps, jitter, repeats, filters, trial, audit


if __name__ == "__main__":
    run()
