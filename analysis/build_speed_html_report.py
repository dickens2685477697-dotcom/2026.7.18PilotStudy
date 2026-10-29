"""Build a self-contained, offline HTML report from verified analysis outputs."""
from pathlib import Path
import hashlib
import json
import math
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "30hz_50hz_analysis" / "results"
REPLAY = RESULTS / "offline_replay"


def records(path, columns=None):
    frame = pd.read_csv(path)
    if columns:
        frame = frame[columns]
    return json.loads(frame.to_json(orient="records", force_ascii=False, double_precision=14))


def main():
    audit = json.loads((REPLAY / "replay_audit.json").read_text(encoding="utf-8"))
    for item in audit["raw_sources"]:
        assert hashlib.sha256((ROOT / item["path"]).read_bytes()).hexdigest() == item["sha256"]
    entries = records(RESULTS / "formal_entries.csv", [
        "session", "session_order", "hz", "case", "id", "target_diameter_mm", "entrySequence",
        "event", "reason", "entryElapsed", "armedLatencyMs", "decisionSpeed"])
    trials = records(RESULTS / "formal_trials.csv", [
        "session", "session_order", "hz", "Case", "ID", "target_diameter_mm", "usedTime",
        "entry_count", "first_entry_success", "successful_entry_time_s"])
    replay = records(REPLAY / "entry_replay.csv")
    filters = records(REPLAY / "light_filter_summary.csv")
    repeats = records(REPLAY / "repeated_pose_samples.csv")
    examples, repeat_trace = [], None
    for session in sorted({e["session"] for e in replay}):
        path = ROOT / "30hz_50hz_analysis" / session / f"{session}-speed-boundary-debug.csv"
        b = pd.read_csv(path)
        for end in [e for e in replay if e["session"] == session and e["observed_outcome"] == "exit"]:
            q = b[b.entrySequence.eq(end["entrySequence"])]
            last = q[q.event.eq("sample")].iloc[-1]
            outside = q[q.event.eq("exit")].iloc[0]
            examples.append({"key": f"{session}:{end['entrySequence']}", "tip0": last[["indexX", "indexY", "indexZ"]].tolist(),
                "tip1": outside[["indexX", "indexY", "indexZ"]].tolist(),
                "distal0": last[["distalX", "distalY", "distalZ"]].tolist(),
                "distal1": outside[["distalX", "distalY", "distalZ"]].tolist(),
                "center": last[["boundsCenterX", "boundsCenterY", "boundsCenterZ"]].tolist(),
                "extent": last[["boundsExtentX", "boundsExtentY", "boundsExtentZ"]].tolist()})
        if repeat_trace is None:
            candidates = [r for r in repeats if r["session"] == session and r["newly_armed_at_zero"] and r["previous_speed_m_s"] > .2]
            if candidates:
                event = candidates[0]
                s = b[b.entrySequence.eq(event["entrySequence"]) & b.event.eq("sample")].reset_index(drop=True)
                for tau in [10, 20]:
                    state, values = None, []
                    for _, row in s.iterrows():
                        alpha = 1 - math.exp(-row.motionDeltaTime/(tau/1000))
                        state = row.decisionSpeed if state is None else state+alpha*(row.decisionSpeed-state)
                        values.append(state)
                    s[f"ema{tau}"] = values
                k = int(s.index[s.motionSampleSequence.eq(event["sample_sequence"])][0])
                v = s.iloc[max(0, k-2):k+4].copy()
                v["relative_ms"] = (v.motionFixedTime-event["time_s"])*1000
                repeat_trace = {"event": event, "points": json.loads(v[["relative_ms", "decisionSpeed", "ema10", "ema20"]].to_json(orient="records"))}
    payload = {"entries": entries, "trials": trials, "replay": replay, "filters": filters,
               "repeats": repeats, "repeatTrace": repeat_trace, "geometry": examples,
               "sessions": records(RESULTS / "session_summary.csv"), "audit": audit}
    assert len(entries) == 261 and len(trials) == 192 and len(examples) == 69
    assert sum(r["linear_crossing_recovered_guarded"] for r in replay) == 22
    assert sum(r["linear_recovered_strict_history"] for r in replay) == 19
    assert all(r["interval_valid"] and r["boundary_fraction"] is not None for r in replay if not r["discrete_triggered"])
    encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(",", ":")).replace("</", "<\\/")
    template = (ROOT / "analysis" / "speed_report_template.html").read_text(encoding="utf-8")
    assert template.count("__REPORT_DATA__") == 1
    output = RESULTS / "speed_framerate_interpolation_report.html"
    output.write_text(template.replace("__REPORT_DATA__", encoded), encoding="utf-8", newline="\n")
    print(f"Built {output} ({output.stat().st_size:,} bytes). Raw hashes and data totals verified.")


if __name__ == "__main__":
    main()
