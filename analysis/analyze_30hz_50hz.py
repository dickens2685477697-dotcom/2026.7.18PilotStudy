"""Describe the four 2026-10-22 speed experiments without altering raw logs.

Run with the bundled Python runtime. Only numpy, pandas and matplotlib are needed.
Analysis unit: a formal target entry, and separately a completed formal trial.
"""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
runtime_extras = ROOT / "analysis" / "_plot_deps" / "30hz_50hz_runtime"
if runtime_extras.is_dir():
    sys.path.insert(0, str(runtime_extras))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
import numpy as np
import pandas as pd

DATA = ROOT / "30hz_50hz_analysis"
OUT = DATA / "results"
SIZES = {1: 90, 2: 60, 3: 30}
COLORS = {30: "#3366A6", 50: "#B65826"}


def table_read(folder: Path, suffix: str) -> pd.DataFrame:
    return pd.read_csv(folder / f"{folder.name}-{suffix}.csv")


def read_trials(folder: Path) -> tuple[pd.DataFrame, dict]:
    # The writer appends centre + 16 target coordinates (51 values), but its
    # header declares 15 target coordinates (45 values). The first 26 columns
    # are correctly aligned. Letting pandas infer an index silently shifts them.
    with (folder / f"{folder.name}-time.csv").open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))
    widths = sorted(set(map(len, rows[1:])))
    assert len(rows[0]) == 71 and widths == [77], (folder, widths)
    df = pd.DataFrame([r[:26] for r in rows[1:]], columns=rows[0][:26])
    for c in ["Case", "ID", "inTargetTimes", "errorTimes", "errorInTimes", "usedTime", "triggerTime", "cancelTimes"]:
        df[c] = pd.to_numeric(df[c], errors="raise")
    return df, {"header_columns": len(rows[0]), "row_columns": widths,
                "handling": "Read first 26 fields by csv.reader; do not infer pandas index."}


def metrics(e: pd.DataFrame, t: pd.DataFrame) -> dict:
    good = e[e.event.eq("trigger")]
    fail = e[~e.event.eq("trigger")]
    return {
        "trials": len(t), "entries": len(e), "triggers": len(good),
        "entry_trigger_rate": len(good) / len(e),
        "first_entry_successes": int(t.first_entry_success.sum()),
        "first_entry_success_rate": float(t.first_entry_success.mean()),
        "retry_trials": int((t.entry_count > 1).sum()), "failed_entries": len(fail),
        "minimum_speed_failures": int(fail.reason.eq("minimum_speed_not_reached_before_exit").sum()),
        "maximum_speed_failures": int(fail.reason.eq("maximum_speed_not_reached_before_exit").sum()),
        "boundary_candidates": int(e.boundaryHighSpeedCandidate.sum()),
        "boundary_candidates_per_entry": float(e.boundaryHighSpeedCandidate.mean()),
        "trial_time_mean_s": float(t.usedTime.mean()),
        "trial_time_median_s": float(t.usedTime.median()),
        "trial_time_p90_s": float(t.usedTime.quantile(.9)),
        "successful_entry_time_mean_s": float(good.entryElapsed.mean()),
        "successful_entry_time_median_s": float(good.entryElapsed.median()),
        "successful_entry_time_p90_s": float(good.entryElapsed.quantile(.9)),
        "successful_arming_time_mean_ms": float(good.armedLatencyMs.mean()),
        "armed_to_trigger_mean_ms": float((good.entryElapsed * 1000 - good.armedLatencyMs).mean()),
        "successful_trigger_speed_median_m_s": float(good.decisionSpeed.median()),
        "successful_inside_samples_mean": float(good.insideSampleCount.mean()),
        "all_inside_samples_mean": float(e.insideSampleCount.mean()),
        "failed_entry_time_total_s": float(fail.entryElapsed.sum()),
        "trial_errors": int(t.errorTimes.sum()),
        "tracking_loss_entries": int(e.trackingLossObserved.sum()),
        "mixed_sampling_entries": int(e.mixedSamplingRate.sum()),
        "settings_changed_entries": int(e.settingsChanged.sum()),
    }


def load_data():
    sessions, entries, trials, samples, boundaries, audits, sources = [], [], [], [], [], [], []
    folders = sorted(p for p in DATA.iterdir() if p.is_dir() and p.name.startswith("20261022-"))
    assert len(folders) == 4
    for order, folder in enumerate(folders, 1):
        a = table_read(folder, "session-settings")
        all_e = table_read(folder, "speed-entry-summary")
        all_b = table_read(folder, "speed-boundary-debug")
        traj = table_read(folder, "trajectory")
        t, width_audit = read_trials(folder)
        hz = int(a.requestedSamplingHz.iloc[0])
        assert a.requestedSamplingHz.nunique() == 1
        assert np.allclose(a.fixedSamplingHz, hz)
        assert a.minSpeedThreshold.eq(.067).all() and a.maxSpeedThreshold.eq(.375).all()
        assert a.timeScale.eq(1).all()
        assert all_e.entrySequence.is_unique
        e = all_e[all_e.entryExperimentStarted.eq(1) & all_e.source.eq("target")
                  & all_e.isMineBall.eq(0) & all_e["mode"].eq("speed")].copy()
        b = all_b[all_b.entrySequence.isin(e.entrySequence)].copy()
        assert len(e) == len(all_e[all_e.entryExperimentStarted.eq(1)])
        assert e.currentExperimentStarted.eq(1).all()
        assert e.event.isin(["trigger", "exit"]).all()
        assert e[e.event.eq("trigger")].groupby("case").size().eq(1).all()
        assert set(e["case"]) == set(t.Case) == set(range(1, 49))
        assert len(t) == 48 and t.modeSelected.eq("speed").all()
        assert e.groupby("case").size().sort_index().equals(
            t.set_index("Case").inTargetTimes.astype("int64").sort_index())
        assert not e[["mixedSamplingRate", "settingsChanged", "trackingLossObserved"]].to_numpy().any()
        s = b[b.event.eq("sample")].copy()
        assert not s.duplicated(["entrySequence", "motionSampleSequence"]).any()
        assert s.groupby("entrySequence").size().sort_index().equals(
            e.set_index("entrySequence").insideSampleCount.sort_index())
        assert e.groupby("id").boundsExtentX.first().round(4).to_dict() == {1: .045, 2: .030, 3: .015}
        assert e.tipPoseValid.eq(1).all() and e.distalPoseValid.eq(1).all()
        # Independent time check using settings event timestamps.
        expected_times = []
        for _, block in a.groupby("id", sort=False):
            start = block[block.event.eq("experiment_start")].iloc[0]
            ended = block[block.event.eq("trial_end")]
            delta = np.diff(np.r_[start.time, ended.time.to_numpy()])
            expected_times.extend(zip(ended["case"].astype(int), delta))
        time_check = dict(expected_times)
        err = np.abs(t.usedTime.to_numpy() - t.Case.map(time_check).to_numpy())
        assert err.max() < .00005, (folder, err.max())
        counts = e.groupby("case").size()
        first = e.sort_values("entrySequence").groupby("case").first()
        trigger = e[e.event.eq("trigger")].set_index("case")
        t["entry_count"] = t.Case.map(counts)
        t["first_entry_success"] = t.Case.map(first.event.eq("trigger"))
        t["successful_entry_time_s"] = t.Case.map(trigger.entryElapsed)
        t["successful_arming_time_ms"] = t.Case.map(trigger.armedLatencyMs)
        t["failed_entry_count"] = t.entry_count - 1
        t["target_diameter_mm"] = t.ID.map(SIZES)
        e["target_diameter_mm"] = e.id.map(SIZES)
        for df in [t, e, s, b]:
            df["session"] = folder.name
            df["session_order"] = order
            df["pair"] = (order + 1) // 2
            df["hz"] = hz
        starts, ends = a[a.event.eq("experiment_start")], a[a.event.eq("experiment_end")]
        elapsed = (ends.realtime.to_numpy() - starts.realtime.to_numpy()).sum()
        frames = (ends.frame.to_numpy() - starts.frame.to_numpy()).sum()
        summary = {"session": folder.name, "session_order": order, "pair": (order + 1) // 2,
                   "hz": hz, **metrics(e, t), "render_fps": float(frames / elapsed),
                   "inside_speed_median_m_s": float(s.decisionSpeed.median()),
                   "inside_speed_p95_m_s": float(s.decisionSpeed.quantile(.95)),
                   "debug_rows": len(b), "unique_inside_samples": len(s),
                   "formal_motion_sample_hz": float(1 / traj.fixedDeltaTime.median()),
                   "pre_experiment_entries_excluded": len(all_e) - len(e)}
        sessions.append(summary)
        entries.append(e)
        trials.append(t)
        samples.append(s)
        boundaries.append(b)
        audits.append({"session": folder.name, **width_audit,
                       "trial_time_max_absolute_difference_s": float(err.max()),
                       "summary_vs_time_entry_counts_match": True,
                       "summary_vs_unique_sample_counts_match": True,
                       "pre_experiment_entries_excluded": len(all_e) - len(e)})
        for path in sorted(folder.glob("*.csv")):
            sources.append({"path": str(path.relative_to(ROOT)), "bytes": path.stat().st_size,
                            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    return (pd.DataFrame(sessions), pd.concat(entries, ignore_index=True),
            pd.concat(trials, ignore_index=True), pd.concat(samples, ignore_index=True),
            pd.concat(boundaries, ignore_index=True), audits, sources)


def md_table(df: pd.DataFrame, columns: list[tuple[str, str, str]]) -> str:
    lines = ["| " + " | ".join(label for _, label, _ in columns) + " |",
             "| " + " | ".join("---" for _ in columns) + " |"]
    for _, row in df.iterrows():
        values = []
        for key, _, fmt in columns:
            value = row[key]
            values.append(format(value, fmt) if fmt else str(value))
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def make_figures(r, e, t, h, c):
    fonts = {x.name for x in font_manager.fontManager.ttflist}
    chosen = next((x for x in ["Microsoft YaHei", "SimHei", "Noto Sans CJK SC"] if x in fonts), "DejaVu Sans")
    plt.rcParams.update({"font.family": chosen, "font.size": 11, "axes.unicode_minus": False,
                         "axes.spines.top": False, "axes.spines.right": False,
                         "axes.titleweight": "bold", "axes.titlesize": 13,
                         "figure.facecolor": "white", "axes.facecolor": "white"})
    fig, axes = plt.subplots(2, 2, figsize=(13.4, 10.2))
    fig.subplots_adjust(top=.86, bottom=.12, left=.085, right=.96, wspace=.26, hspace=.50)
    fig.suptitle("50 Hz 下触发更快，小目标触发率未改善", fontsize=20, x=.085, ha="left", y=.97)
    fig.text(.085, .918, "4 次实验按 30 / 50 / 30 / 50 Hz 进行；每次 48 个正式试次。每种频率只有 2 次实验。", fontsize=11, color="#555555")
    labels = ["第 1 次\n30 Hz", "第 2 次\n50 Hz", "第 3 次\n30 Hz", "第 4 次\n50 Hz"]
    ax = axes[0, 0]
    bars = ax.bar(np.arange(4), r.entry_trigger_rate * 100, color=[COLORS[x] for x in r.hz], width=.57)
    for bar, (_, row) in zip(bars, r.iterrows()):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height()+2,
                f"{row.entry_trigger_rate:.1%}\n48/{int(row.entries)}", ha="center", va="bottom", fontsize=10)
    ax.set(xticks=np.arange(4), xticklabels=labels, ylim=(0, 104), ylabel="触发次数 / 正式进入次数（%）",
           title="A  每次进入的触发率")
    ax.set_yticks([0, 25, 50, 75, 100])
    ax = axes[0, 1]
    for pair, style in [(1, "-"), (2, "--")]:
        q = r[r.pair.eq(pair)].sort_values("hz")
        ax.plot(q.hz, q.successful_entry_time_mean_s * 1000, style, color="#8C8C8C", linewidth=1.8)
        ax.scatter(q.hz, q.successful_entry_time_mean_s * 1000, c=[COLORS[x] for x in q.hz], s=70, zorder=3)
        for _, row in q.iterrows():
            above = (row.hz == 30 and pair == 1) or (row.hz == 50 and pair == 2)
            ax.annotate(f"第 {int(row.session_order)} 次：{row.successful_entry_time_mean_s*1000:.0f} ms",
                        (row.hz, row.successful_entry_time_mean_s*1000), xytext=(0, 13 if above else -25),
                        textcoords="offset points", ha="center", fontsize=10)
    ax.set(xlim=(23, 57), xticks=[30, 50], xticklabels=["30 Hz", "50 Hz"], ylim=(350, 650),
           ylabel="成功进入至触发的平均时间（ms）", title="B  两轮均出现较短的触发耗时")
    ax.text(.04, .06, "实线：第 1 轮；虚线：第 2 轮", transform=ax.transAxes, fontsize=9, color="#666666")
    ax = axes[1, 0]
    x = np.arange(3)
    for hz, off in [(30, -.18), (50, .18)]:
        q = c[c.hz.eq(hz)].set_index("target_diameter_mm").loc[[90, 60, 30]]
        bars = ax.bar(x+off, q.entry_trigger_rate*100, .34, color=COLORS[hz], label=f"{hz} Hz")
        for bar, (_, row) in zip(bars, q.iterrows()):
            ax.text(bar.get_x()+bar.get_width()/2, bar.get_height()+1.5,
                    f"{row.entry_trigger_rate:.1%}\n32/{int(row.entries)}", ha="center", fontsize=9)
    ax.set(xticks=x, xticklabels=["90 mm\nID 1", "60 mm\nID 2", "30 mm\nID 3"], ylim=(0, 118),
           ylabel="触发次数 / 正式进入次数（%）", title="C  两种频率下，小目标都更难触发")
    ax.legend(frameon=False, loc="upper left", ncol=2, fontsize=10)
    ax = axes[1, 1]
    vals = []
    cats = ["minimum_speed_failures", "maximum_speed_failures"]
    for hz in [30, 50]:
        q = h[h.hz.eq(hz)].iloc[0]
        vals.append([q[cats[0]], q[cats[1]]])
    vals = np.array(vals)
    ax.barh([0, 1], vals[:, 0], color="#A8ACB3", height=.48, label="未达到低速就绪条件")
    ax.barh([0, 1], vals[:, 1], left=vals[:, 0], color="#566B84", height=.48, label="已就绪，目标内未达到高速阈值")
    for i, hz in enumerate([30, 50]):
        ax.text(vals[i, 0]/2, i, str(int(vals[i, 0])), ha="center", va="center", color="#222222")
        ax.text(vals[i, 0]+vals[i, 1]/2, i, str(int(vals[i, 1])), ha="center", va="center", color="white")
        q = h[h.hz.eq(hz)].iloc[0]
        ax.text(vals[i].sum()+.7, i, f"共 {int(vals[i].sum())} 次\n边界候选 {int(q.boundary_candidates)} 次", va="center", fontsize=10)
    ax.set(yticks=[0, 1], yticklabels=["30 Hz", "50 Hz"], xlim=(0, 51), xlabel="失败进入次数", title="D  主要差异来自高速阈值之前离开目标")
    ax.invert_yaxis()
    ax.legend(frameon=False, loc="center left", bbox_to_anchor=(0, .5), fontsize=9)
    fig.text(.085, .035, "来源：四次 session-settings、speed-entry-summary 与 time 日志。排除起始球。\n边界候选表示离开后首个采样点才达到高速阈值，不能据此认定其全部为可恢复漏触发；实验顺序与熟练度未分离。",
             fontsize=9.5, color="#555555", va="bottom", linespacing=1.6)
    fig.savefig(OUT / "frame_rate_speed_comparison.png", dpi=170)
    fig.savefig(OUT / "frame_rate_speed_comparison.svg")
    plt.close(fig)
    return chosen


def write_report(r, h, c, e, t, s, b, audits):
    low, high = h.set_index("hz").loc[30], h.set_index("hz").loc[50]
    latency_diff = (low.successful_entry_time_mean_s - high.successful_entry_time_mean_s) * 1000
    latency_pct = 1 - high.successful_entry_time_mean_s / low.successful_entry_time_mean_s
    used_pct = 1 - high.trial_time_mean_s / low.trial_time_mean_s
    session_table = md_table(r, [
        ("session", "会话", ""), ("hz", "采样 Hz", ".0f"),
        ("entries", "正式进入次数", ".0f"), ("entry_trigger_rate", "单次进入触发率", ".1%"),
        ("first_entry_success_rate", "首次进入成功率", ".1%"),
        ("successful_entry_time_mean_s", "成功进入至触发均值 / s", ".3f"),
        ("trial_time_mean_s", "试次完成时间均值 / s", ".3f")])
    pooled = h.copy()
    pooled_table = md_table(pooled, [
        ("hz", "采样 Hz", ".0f"), ("trials", "正式试次", ".0f"),
        ("entries", "正式进入次数", ".0f"), ("failed_entries", "失败进入次数", ".0f"),
        ("entry_trigger_rate", "单次进入触发率", ".1%"),
        ("first_entry_success_rate", "首次进入成功率", ".1%"),
        ("successful_entry_time_mean_s", "成功进入耗时均值 / s", ".3f"),
        ("successful_entry_time_median_s", "成功进入耗时中位数 / s", ".3f"),
        ("trial_time_mean_s", "试次完成时间均值 / s", ".3f")])
    size_rows = []
    for size in [90, 60, 30]:
        q = c[c.target_diameter_mm.eq(size)].set_index("hz")
        size_rows.append({"size": size, "rate30": q.loc[30, "entry_trigger_rate"],
                          "rate50": q.loc[50, "entry_trigger_rate"],
                          "entries30": int(q.loc[30, "entries"]), "entries50": int(q.loc[50, "entries"]),
                          "lat30": q.loc[30, "successful_entry_time_mean_s"] * 1000,
                          "lat50": q.loc[50, "successful_entry_time_mean_s"] * 1000})
    size_table = md_table(pd.DataFrame(size_rows), [
        ("size", "目标直径 / mm", ".0f"), ("entries30", "30 Hz 进入数", ".0f"),
        ("entries50", "50 Hz 进入数", ".0f"),
        ("rate30", "30 Hz 触发率", ".1%"), ("rate50", "50 Hz 触发率", ".1%"),
        ("lat30", "30 Hz 成功进入耗时 / ms", ".0f"),
        ("lat50", "50 Hz 成功进入耗时 / ms", ".0f")])
    reason_table = md_table(h, [
        ("hz", "采样 Hz", ".0f"), ("minimum_speed_failures", "未低速就绪便离开", ".0f"),
        ("maximum_speed_failures", "已就绪，内侧未达到高速便离开", ".0f"),
        ("boundary_candidates", "其中：离开帧高速候选", ".0f"),
        ("boundary_candidates_per_entry", "候选 / 全部进入", ".1%")])
    sample_parts = []
    for hz in [30, 50]:
        q = s[s.hz.eq(hz)]
        sample_parts.append(f"{hz} Hz：{len(q):,} 个独立内侧采样点，速度中位数 {q.decisionSpeed.median():.4f} m/s，95 分位 {q.decisionSpeed.quantile(.95):.4f} m/s")
    raw_links = []
    for folder in sorted(DATA.glob("20261022-*")):
        links = [f"[{suffix}](../{folder.name}/{folder.name}-{suffix}.csv)" for suffix in
                 ["session-settings", "speed-entry-summary", "speed-boundary-debug", "time", "trajectory"]]
        raw_links.append(f"- {folder.name}：" + "、".join(links))
    report = f"""# 固定步长采样频率对 speed 触发的影响

本次四组记录中，50 Hz 与更短的触发耗时相关，整体单次进入触发率略高；改善主要体现在 60 mm 条件。30 mm 小目标在两种频率下的触发率接近，仍是主要困难。每种频率只有两次会话，以下结果是本次测试的描述性比较，不能将全部差异认定为帧率的因果效应。

![采样频率与 speed 触发对比](frame_rate_speed_comparison.png)

## 1. 数据与统计口径

实际目录为 `30hz_50hz_analysis`。四次会话按 30、50、30、50 Hz 交替，各包含 48 个正式试次（ID 2、3、1 各 16 次），共 192 个。ID 是目标条件，不应当作受试者编号。三种直径根据遥测 boundsExtentX 的两倍确认，分别为 ID 1 = 90 mm、ID 2 = 60 mm、ID 3 = 30 mm；这些条件同时包含不同的目标环半径，因此尺寸间差异不能归因于直径一个因素。

所有记录为 speed 模式，低速阈值 0.067 m/s、高速阈值 0.375 m/s、timeScale=1，参数一致。按照 entryExperimentStarted=1 排除正式实验开始前的起始球记录，共排除 22 次进入，其中有 12 次起始球触发。保留 261 次正式进入，包含 192 次触发与 69 次离开未触发。

- **单次进入触发率**：正式触发次数 / 所有正式进入次数。一个试次可重入多次，分母不是完成试次数。
- **首次进入成功率**：每个试次的第一个正式 entry 是否成功 / 正式试次数。
- **成功进入至触发耗时**：只对最终成功 entry 计算 entryElapsed，包含等待低速就绪和随后达到高速的时间，不包含此前失败 entry 和目标间移动。
- **试次完成时间**：time.csv 的 usedTime，包含目标间移动、失败与重入等整个试次过程。

所有试次最终完成，且 errorTimes=0。这不等于每次接触都成功，也不能据此估计无意动作的误触率。

日志中的 30/50 Hz 是 FixedUpdate 采样频率；四次会话在正式区间内由 frame/realtime 估计的渲染帧率分别为 {', '.join(f'{v:.2f}' for v in r.render_fps)} FPS。此次比较主要改变了动作采样步长，而渲染帧率基本相同。

## 2. 四次会话分别比较

{session_table}

相邻会话作为两轮描述性比较：第一轮 50 Hz 比 30 Hz 的成功 entry 平均耗时短 150 ms，单次进入触发率高 3.9 个百分点；第二轮短 79 ms，高 3.9 个百分点。首次进入成功率在第一轮改善 8.3 个百分点，第二轮两者相同。两轮都支持“触发耗时较短”的方向，但触发可靠性改善幅度较小。

## 3. 合并后的频率差异

{pooled_table}

50 Hz 的成功进入平均触发耗时短 **{latency_diff:.0f} ms（{latency_pct:.1%}）**，中位数从 533 ms 降至 420 ms。平均试次完成时间从 1.818 s 降至 1.551 s，短 **{(low.trial_time_mean_s-high.trial_time_mean_s)*1000:.0f} ms（{used_pct:.1%}）**。

单次进入触发率从 96/134 = 71.6% 升至 96/127 = 75.6%，提高 **3.95 个百分点**。首次进入成功率从 75/96 = 78.1% 升至 79/96 = 82.3%，提高 4.17 个百分点。需要重试的试次从 21 次降至 17 次；失败 entry 从 38 次降至 31 次。

低速就绪时间均值从 159 ms 缩短到 133 ms；就绪后至触发时间从 396 ms 缩短到 306 ms。115 ms 差异中的大部分出现在“已低速就绪到达到高速”阶段。这是行为与判定共同形成的耗时，不能直接解释为系统处理延迟降低 115 ms。

## 4. 按目标条件拆分

每个频率、每个目标条件都有 32 个正式完成试次。

{size_table}

**60 mm 条件的改善最明显**：单次进入触发率提高 18.9 个百分点，失败 entry 从 9 次降到 1 次。90 mm 条件均为 91.4%，可靠性相同，但 50 Hz 耗时更短。

**30 mm 条件没有可靠性改善**：触发率 55.2% 对 54.2%，失败 entry 为 26 次对 27 次，首次进入成功率为 68.8% 对 59.4%。50 Hz 的成功 entry 耗时仍短约 117 ms，但这不能等同于更容易一次成功。小目标仍需要进一步优化。

## 5. 失败发生在哪里

源码的顺序为：进入接触区域后，先在速度 ≤ 0.067 m/s 时置为就绪，随后仅在允许触发且速度 ≥ 0.375 m/s 时触发。接触判断为指尖或食指远端关节任意一个位于 collider 的轴对齐 bounds 内，并非只检查指尖是否位于球面内。

{reason_table}

50 Hz 下未低速就绪便离开的次数没有减少（13 对 14），主要减少的是已就绪后、目标内没有达到高速阈值的失败（25 对 17）。未发现目标内已满足高速且就绪却仍未触发的正式 entry。

“离开帧高速候选”是已就绪、内侧最后一个速度低于高速阈值，但第一次离开采样速度已达到阈值的 entry。30 Hz 为 19 次，50 Hz 为 12 次，分别占全部进入的 14.2% 与 9.4%。它们是上一列失败的子集，不应重复相加。这与更密采样可能减少边界时机损失的解释一致，但两次端点观测不能证明跨界前的连续真实速度一定已达阈值。

其中，第一次 30 Hz 会话有 3 个候选的离开速度达到 15.3–17.5 m/s，应检查原始 tracking/pose 连续性。SDK 的有效标记和 trackingLossObserved=0 不能排除位置跳变。即使仅在候选机制分析中暂不计这 3 个异常点，候选仍是 16 对 12。主结果保留全部原始记录，未根据这个诊断阈值删除 trial 或 entry。

## 6. 速度估计与时间采样的解释

源码的速度公式为 `v = ||当前位置 - 前一采样位置|| / Time.fixedDeltaTime`，不是直接使用每帧位移。两种频率已经按各自时间间隔归一化。

- {sample_parts[0]}。
- {sample_parts[1]}。

这两个分布整体接近，没有证据表明 50 Hz 将速度普遍放大。逐帧数据有时间与试次内相关性，上述分位数仅描述采样值，不作为独立样本推断。50 Hz 的 2,717 个内侧点中有 55 个零速度点，30 Hz 的 2,117 个点中没有零值；这可以由相邻 pose 重复等因素形成，现有日志不足以判定其原因。

采样间隔从 33.33 ms 缩短到 20 ms，减少 13.33 ms。作为几何尺度示例：以 0.375 m/s 匀速运动时，一个采样间隔内的位移分别为 12.5 mm 和 7.5 mm。更短步长有机会捕获阈值与边界之间的时刻，但本次观察到约 115 ms 的完整 entry 耗时差异明显大于 13.33 ms，不能只用一次采样等待来解释。

## 7. 实验限制与下一步

两种频率的第二次会话都出现明显的可靠性改善：30 Hz 从 66.7% 到 77.4%，50 Hz 从 70.6% 到 81.4%，均约 10.8 个百分点，大于合并频率差异的 3.95 个百分点。这提示顺序、熟练度或其他会话差异影响较大。50 Hz 每次都紧跟在 30 Hz 后面，尚未对顺序做平衡；记录中也缺少可用于估计跨受试者效应的受试者标识。

因此，本报告不把 261 个 entry 或数千帧当作独立受试者来做显著性检验，也不据此宣称普遍的显著帧率效应。

本次调试可优先沿用 50 Hz，并保留 30 Hz 作为对照。若目标是修复 30 mm 小目标问题，应优先复查边界处的轨迹、就绪状态和 pose 跳变。对跨采样区间的接触与阈值做离线重放后，再评估连续碰撞/区间内判定方案及其误触代价。现有数据不足以给出应下调多少速度阈值的结论。

下一轮可采用跨会话或跨受试者平衡顺序的 ABBA/BAAB，充分练习后再测，保留每种目标条件的首次进入成功率、成功 entry 耗时、完整试次耗时和边界候选。正式统计应按受试者和会话处理重复测量。

## 8. 数据核验与可复现文件

发现四个 time.csv 均为表头 71 列、数据行 77 列。写入器追加了中心点与 16 个目标坐标，旧表头只列出 15 组坐标。前 26 个行为字段实际对齐，若直接 `pandas.read_csv`，可能自动推断多列索引，导致列值整体错读。本分析使用 csv.reader 按前 26 列解析，未修改原文件。

完成以下交叉核对：每个 trial 的 inTargetTimes 与正式 entry 数完全一致；每个成功 trial 对应且仅对应一次 trigger；insideSampleCount 与按 entry 和 motionSampleSequence 去重的 sample 数完全一致；usedTime 与 settings 相邻事件时间差的最大误差小于 0.008 ms。所有正式 entry 均无设置变更、采样率混合或已记录的追踪丢失。

分析仅将独立 motion sample 用于速度分布，未将重复 check 行当作独立采样。原文件的路径、字节数及 SHA-256 记录于 [audit.json](audit.json)。

- [按会话汇总](session_summary.csv)
- [按频率汇总](sampling_rate_summary.csv)
- [按目标条件汇总](target_size_summary.csv)
- [正式试次明细](formal_trials.csv)
- [正式进入明细](formal_entries.csv)
- [边界候选明细](boundary_candidates.csv)
- [可复现分析脚本](../../analysis/analyze_30hz_50hz.py)

原始证据：

{chr(10).join(raw_links)}

算法对照：[AcceStudy3.cs](D:/HLStudy4_22/Assets/Scripts/Study3/AcceStudy3.cs)、[S2AccMode.cs](D:/HLStudy4_22/Assets/Scripts/Study3/S2AccMode.cs)、[SpeedStudyTelemetry.cs](D:/HLStudy4_22/Assets/Scripts/Study3/SpeedStudyTelemetry.cs)、[LogWriter3.cs](D:/HLStudy4_22/Assets/Scripts/Study3/LogWriter3.cs)。源码用于解释现有字段，实际实验条件以会话日志为准。
"""
    (OUT / "analysis_report_zh.md").write_text(report, encoding="utf-8")


def main():
    OUT.mkdir(exist_ok=True)
    r, e, t, s, b, audits, sources = load_data()
    h = pd.DataFrame([{"hz": hz, **metrics(e[e.hz.eq(hz)], t[t.hz.eq(hz)])} for hz in [30, 50]])
    c = pd.DataFrame([{"hz": hz, "target_diameter_mm": size,
                       **metrics(e[e.hz.eq(hz) & e.target_diameter_mm.eq(size)],
                                 t[t.hz.eq(hz) & t.target_diameter_mm.eq(size)])}
                      for size in [90, 60, 30] for hz in [30, 50]])
    bnd = e[e.boundaryHighSpeedCandidate.eq(1)].copy()
    # This is a diagnostic flag, not an exclusion rule or a validated physiological cutoff.
    bnd["exit_speed_above_5_m_s_diagnostic"] = bnd.exitFrameSpeed.gt(5)
    sample_stats = []
    for hz in [30, 50]:
        q = s[s.hz.eq(hz)]
        sample_stats.append({"hz": hz, "inside_samples": len(q),
                             "inside_speed_median_m_s": float(q.decisionSpeed.median()),
                             "inside_speed_p95_m_s": float(q.decisionSpeed.quantile(.95)),
                             "zero_speed_samples": int(q.decisionSpeed.eq(0).sum())})
    font = make_figures(r, e, t, h, c)
    write_report(r, h, c, e, t, s, b, audits)
    for name, df in [("session_summary", r), ("sampling_rate_summary", h),
                     ("target_size_summary", c), ("formal_trials", t),
                     ("formal_entries", e), ("boundary_candidates", bnd)]:
        df.to_csv(OUT / f"{name}.csv", index=False, encoding="utf-8-sig")
    (OUT / "audit.json").write_text(json.dumps({"sessions": audits, "source_files": sources,
                                                "sample_stats": sample_stats, "plot_font": font},
                                               ensure_ascii=False, indent=2), encoding="utf-8")
    print("SESSIONS\n" + r.to_string(index=False))
    print("HZ\n" + h.to_string(index=False))
    print("SIZES\n" + c.to_string(index=False))
    print("SAMPLES", sample_stats)
    print("BOUNDARY_SPIKES", bnd[bnd.exit_speed_above_5_m_s_diagnostic][
        ["session", "case", "id", "entrySequence", "lastInsideSpeed", "exitFrameSpeed"]].to_dict("records"))
    print("AUDIT", audits)


if __name__ == "__main__":
    main()
