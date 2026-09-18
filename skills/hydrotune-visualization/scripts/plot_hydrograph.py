from __future__ import annotations
import argparse
from pathlib import Path
import matplotlib.pyplot as plt
import pandas as pd
from plot_common import load, output_metadata

def main():
    p = argparse.ArgumentParser(); p.add_argument("--dataset", required=True); p.add_argument("--simulation", required=True); p.add_argument("--metadata", required=True); p.add_argument("--output", required=True); args = p.parse_args()
    frame, meta, discharge = load(args.dataset, args.simulation, args.metadata)
    if meta.get("series_mode") != "continuous": raise SystemExit("plot_hydrograph requires continuous series_mode")
    frame = frame.sort_values("timestamp"); out = Path(args.output); out.parent.mkdir(parents=True, exist_ok=True)
    fig, (rain_ax, flow_ax) = plt.subplots(2, 1, figsize=(12, 6), dpi=160, sharex=True, gridspec_kw={"height_ratios": [1, 3]})
    precip = next((v for v in meta["variables"] if v["role"] == "precipitation"), None)
    if precip:
        rain_ax.bar(frame.timestamp, pd.to_numeric(frame[precip["column"]], errors="coerce").fillna(0), color="#4C78A8", width=0.02); rain_ax.invert_yaxis(); rain_ax.set_ylabel(f"P ({precip['unit']})")
    else: rain_ax.set_visible(False)
    flow_ax.plot(frame.timestamp, frame[discharge], color="#222222", lw=1.5, label="Observed")
    flow_ax.plot(frame.timestamp, frame.discharge_sim, color="#D1495B", lw=1.5, label="Simulated")
    colors = {"warmup": "#E5E5E5", "calibration": "#D8EAD3", "validation": "#D8E5F3"}
    for name, split in meta["splits"].items():
        if isinstance(split, dict) and "start" in split: flow_ax.axvspan(pd.Timestamp(split["start"]), pd.Timestamp(split["end"]), color=colors[name], alpha=.35, label=name.title())
    flow_ax.set_ylabel(f"Q ({next(v['unit'] for v in meta['variables'] if v['column'] == discharge)})"); flow_ax.set_xlabel("Time"); flow_ax.legend(ncol=5, fontsize=8); flow_ax.grid(alpha=.25); fig.tight_layout(); fig.savefig(out); plt.close(fig)
    output_metadata(out, "plot_hydrograph", meta, {"range": [str(frame.timestamp.min()), str(frame.timestamp.max())]})
if __name__ == "__main__": main()
