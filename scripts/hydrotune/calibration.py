"""HydroTune calibration runtime for seeded parameter search."""

from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
from .common import finish,result,write_json
from .intake import load_dataset, select_scoring_frame
from .metrics import metrics
from .models import get_model
from .modeling import _assert_modeling_ready, simulate
from .optimizers import optimize


def _routing_bounds(meta, bounds):
    """Append mandatory Muskingum parameters when upstream release is available."""
    has_upstream = any(v["role"] == "upstream_discharge" for v in meta["variables"])
    if not has_upstream: return bounds, False
    dt = pd.Timedelta(meta.get("timestep") or "1h").total_seconds() / 3600
    bounds = dict(bounds)
    bounds.setdefault("routing.K", (max(dt, .01), 120.0))
    bounds.setdefault("routing.X", (0.0, .5))
    return bounds, True

def _loss(report, objective):
    key=objective.upper()
    if key in {"NSE","KGE"}: return -float(report[key])
    if key in {"RMSE","MAE"}: return float(report[key])
    if key=="PBIAS": return abs(float(report[key]))
    raise ValueError("objective must be NSE, KGE, RMSE, MAE, or PBIAS")


def cmd_calibrate(args):
    out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
    try:
        frame,meta=load_dataset(Path(args.dataset)); _assert_modeling_ready(meta); discharge=next((v["column"] for v in meta["variables"] if v["role"]=="discharge"),None)
        if not discharge:raise ValueError("calibration requires observed discharge")
        precipitation=next((v["column"] for v in meta["variables"] if v["role"]=="precipitation"),None)
        if not precipitation: raise ValueError("calibration requires precipitation")
        name=args.model.lower(); spec=get_model(name); frame=select_scoring_frame(frame,meta,"calibration"); bounds=json.loads(Path(args.bounds).read_text(encoding="utf-8")) if args.bounds else spec["bounds"]
        bounds, routed = _routing_bounds(meta, bounds)
        names=list(bounds); pairs=[tuple(bounds[n]) for n in names]; config=json.loads(args.optimizer_config) if args.optimizer_config else {}; observed=pd.to_numeric(frame[discharge],errors="coerce").to_numpy(float); trials=[]
        def objective(vector):
            all_params={n:float(v) for n,v in zip(names,vector)}; routing={"method":"muskingum","K":all_params["routing.K"],"X":all_params["routing.X"]} if routed else None; params={k:v for k,v in all_params.items() if not k.startswith("routing.")}; run={**params,"precipitation_column":precipitation}
            try: score=metrics(observed,simulate(frame,meta,name,run,routing))
            except ValueError: score={}
            loss=_loss(score,args.objective) if score and np.isfinite(score.get(args.objective.upper(),np.nan)) else 1e100; trials.append({"parameters":params,"routing":routing,"metrics":score,"loss":loss}); return loss
        best_vector,loss,history=optimize(args.optimizer,objective,pairs,args.iterations,args.seed,config); all_params={n:float(v) for n,v in zip(names,best_vector)}; params={k:v for k,v in all_params.items() if not k.startswith("routing.")}; routing={"method":"muskingum","K":all_params["routing.K"],"X":all_params["routing.X"]} if routed else None; best=min(trials,key=lambda x:x["loss"]) if trials else {"parameters":params,"routing":routing,"metrics":{},"loss":loss}
        payload={"model":name,"objective":args.objective.upper(),"optimizer":args.optimizer,"optimizer_config":config,"seed":args.seed,"iterations":args.iterations,"bounds":bounds,"routing_required":routed,"selected":best,"history":history,"evaluations":trials};write_json(out/"calibration.json",payload);return finish(out,result("calibration",outputs=["calibration.json"],selected=best))
    except Exception as exc:return finish(out,result("calibration",errors=[str(exc)]))
