"""HydroTune observed-versus-simulated diagnostic runtime."""

from __future__ import annotations
from pathlib import Path
import pandas as pd
from .common import finish,result,write_json
from .intake import load_dataset, select_scoring_frame
from .metrics import metrics


def cmd_diagnose(args):
    out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
    try:
        observed,meta=load_dataset(Path(args.dataset));sim=pd.read_parquet(Path(args.simulation));discharge=next((v["column"] for v in meta["variables"] if v["role"]=="discharge"),None)
        if not discharge:raise ValueError("dataset lacks observed discharge")
        keys=["timestamp"]+(["event_id"] if meta.get("series_mode")=="event_collection" else []);joined=select_scoring_frame(observed[keys+[discharge]].merge(sim[keys+["discharge_sim"]],on=keys,how="inner"),meta,"validation");report=metrics(joined[discharge].to_numpy(float),joined.discharge_sim.to_numpy(float))
        if not report:raise ValueError("no valid observed-simulated overlap")
        evidence={"metrics":report,"peak_observed":float(joined[discharge].max()),"peak_simulated":float(joined.discharge_sim.max())};hyp=[]
        if report["PBIAS"]<-10:hyp.append("Systematic underestimation is evidenced; inspect precipitation input and water-balance parameters.")
        if report["PBIAS"]>10:hyp.append("Systematic overestimation is evidenced; inspect evapotranspiration, losses, and storage parameters.")
        write_json(out/"diagnosis.json",{"evidence":evidence,"hypotheses":hyp});return finish(out,result("diagnosis",outputs=["diagnosis.json"],evidence=evidence,hypotheses=hyp))
    except Exception as exc:return finish(out,result("diagnosis",errors=[str(exc)]))
