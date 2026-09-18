from __future__ import annotations
import argparse
from pathlib import Path
import matplotlib.pyplot as plt
from plot_common import load, output_metadata

def main():
    p=argparse.ArgumentParser(); p.add_argument("--dataset", required=True); p.add_argument("--simulation", required=True); p.add_argument("--metadata", required=True); p.add_argument("--output-dir", required=True); args=p.parse_args()
    frame, meta, discharge = load(args.dataset,args.simulation,args.metadata)
    if meta.get("series_mode") != "event_collection": raise SystemExit("plot_event_panel requires event_collection series_mode")
    warmup=meta["splits"].get("warmup_steps")
    if warmup is None: raise SystemExit("event_collection requires confirmed warmup_steps")
    out=Path(args.output_dir); out.mkdir(parents=True,exist_ok=True); outputs=[]
    for event_id in meta["splits"]["validation_event_ids"]:
        item=frame[frame.event_id==event_id].sort_values("timestamp"); fig,ax=plt.subplots(figsize=(10,4),dpi=160)
        ax.plot(item.timestamp,item[discharge],color="#222222",lw=1.5,label="Observed"); ax.plot(item.timestamp,item.discharge_sim,color="#D1495B",lw=1.5,label="Simulated")
        if len(item): ax.axvspan(item.timestamp.iloc[0],item.timestamp.iloc[min(int(warmup),len(item)-1)],color="#E5E5E5",alpha=.7,label="Warmup (not scored)")
        ax.set(title=f"Validation event {event_id}",xlabel="Time",ylabel="Flow"); ax.grid(alpha=.25); ax.legend(fontsize=8); fig.tight_layout(); path=out/f"{event_id}_hydrograph.png"; fig.savefig(path); plt.close(fig); outputs.append(str(path))
    if not outputs: raise SystemExit("no validation event panels were generated")
    output_metadata(Path(outputs[0]),"plot_event_panel",meta,{"validation_events":meta["splits"]["validation_event_ids"],"warmup_steps":warmup,"event_pngs":outputs})
if __name__ == "__main__": main()
