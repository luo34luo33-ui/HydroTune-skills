from __future__ import annotations
import argparse
from pathlib import Path
import matplotlib.pyplot as plt
import numpy as np
from plot_common import load, output_metadata

def main():
    p=argparse.ArgumentParser(); p.add_argument("--dataset",required=True); p.add_argument("--simulation",required=True); p.add_argument("--metadata",required=True); p.add_argument("--output",required=True); args=p.parse_args()
    frame,meta,discharge=load(args.dataset,args.simulation,args.metadata); splits=meta["splits"]
    if meta.get("series_mode")=="continuous": frame=frame[(frame.timestamp>=splits["validation"]["start"])&(frame.timestamp<=splits["validation"]["end"])]
    else:
        if splits.get("warmup_steps") is None: raise SystemExit("event_collection requires confirmed warmup_steps")
        frame=frame[frame.event_id.isin(splits["validation_event_ids"])]; frame=frame[frame.groupby("event_id").cumcount()>=int(splits["warmup_steps"])]
    obs=frame[discharge].to_numpy(float); sim=frame.discharge_sim.to_numpy(float); lim=max(np.nanmax(obs),np.nanmax(sim)); out=Path(args.output); out.parent.mkdir(parents=True,exist_ok=True)
    fig,ax=plt.subplots(figsize=(5,5),dpi=160); ax.scatter(obs,sim,s=16,alpha=.7,color="#4C78A8"); ax.plot([0,lim],[0,lim],"--",color="#555555",label="1:1"); ax.set(xlabel="Observed flow",ylabel="Simulated flow",xlim=(0,lim),ylim=(0,lim)); ax.grid(alpha=.25); ax.legend(); fig.tight_layout(); fig.savefig(out); plt.close(fig); output_metadata(out,"plot_obs_sim_scatter",meta,{"samples":int(len(frame)),"scope":"validation"})
if __name__=="__main__": main()
