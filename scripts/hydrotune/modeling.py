"""HydroTune model execution runtime for native and external runs."""

from __future__ import annotations
import json,subprocess
from pathlib import Path
import numpy as np
import pandas as pd
from .common import RUN_VERSION,finish,result
from .intake import load_dataset
from .models import get_model
from .routing import muskingum


def read_run(path:Path):
    run=json.loads(path.read_text(encoding="utf-8"))
    if run.get("schema_version")!=RUN_VERSION:raise ValueError("run.json does not use hydrotune.run.v1")
    if not all(k in run for k in ("model","input_dataset","parameters")):raise ValueError("run.json missing required keys")
    return run

def _hours(meta):
    return pd.Timedelta(meta.get("timestep") or "1h").total_seconds()/3600

def _muskingum_config(meta, routing):
    """Validate the mandatory routing contract when an upstream release exists."""
    upstream = next((v["column"] for v in meta["variables"] if v["role"] == "upstream_discharge"), None)
    if not upstream: return None, None
    if not routing: raise ValueError("upstream_discharge requires mandatory Muskingum routing")
    if routing.get("method", "muskingum").lower() != "muskingum": raise ValueError("upstream_discharge must use routing.method=muskingum")
    if "K" not in routing or "X" not in routing: raise ValueError("Muskingum routing requires K and X")
    K, X, dt = float(routing["K"]), float(routing["X"]), float(routing.get("dt_hours", _hours(meta)))
    if K <= 0 or not 0 <= X <= .5: raise ValueError("Muskingum requires K > 0 and 0 <= X <= 0.5")
    if dt > 2 * K * (1 - X): raise ValueError("Muskingum stability requires dt_hours <= 2*K*(1-X)")
    return upstream, {**routing, "method": "muskingum", "K": K, "X": X, "dt_hours": dt}

def _assert_modeling_ready(meta):
    readiness = meta.get("modeling_readiness") or {}
    if readiness.get("modeling_status") != "not_ready":
        return
    blocking = readiness.get("blocking") or ["dataset modeling_readiness is not_ready"]
    raise ValueError("model input requirement unmet: " + "; ".join(map(str, blocking)))

def simulate(frame,meta,name,params,routing=None):
    model=get_model(name)["runner"]; groups=[g for _,g in frame.groupby("event_id",sort=False)] if meta.get("series_mode")=="event_collection" else [frame]
    model_params=dict(params);model_params.setdefault("dt_hours",_hours(meta))
    depth=np.concatenate([model(g,model_params) for g in groups]); variable=next((v for v in meta["variables"] if v["role"]=="discharge"),None)
    if not variable: raise ValueError("dataset lacks observed discharge")
    unit=variable.get("unit","").lower().replace("³","3")
    if "m3/s" in unit or "m^3/s" in unit:
        area=meta.get("basin",{}).get("area_km2")
        # Legacy v1 runs did not require area; preserve their historical depth output.
        if not area: return depth
        depth=depth*float(area)*1000/(_hours(meta)*3600)
    upstream, routing = _muskingum_config(meta, routing)
    if routing:
        depth += np.concatenate([muskingum(pd.to_numeric(g[upstream],errors="coerce").fillna(0).to_numpy(float),routing["K"],routing["X"],routing["dt_hours"],routing.get("reaches",1),routing.get("initial_flow")) for g in groups])
    return depth


def cmd_model(args):
    out,run_path=Path(args.output),Path(args.run);out.mkdir(parents=True,exist_ok=True)
    try:
        run=read_run(run_path);kind=run["model"]["kind"]
        if kind=="native":
            frame,meta=load_dataset(Path(run["input_dataset"]));_assert_modeling_ready(meta);roles={v["role"]:v["column"] for v in meta["variables"]}
            if "precipitation" not in roles:raise ValueError("model input requirement unmet: precipitation variable")
            params=dict(run["parameters"]);params.setdefault("precipitation_column",roles["precipitation"])
            if "temperature" in roles:params.setdefault("temperature_column",roles["temperature"])
            if "pet" in roles:params.setdefault("pet_column",roles["pet"])
            if meta.get("series_mode")=="event_collection" and meta["splits"].get("warmup_steps") is None:raise ValueError("event_collection requires confirmed warmup_steps in dataset.json before model execution")
            name=run["model"].get("name","hbv").lower();simulated=simulate(frame,meta,name,params,run.get("routing")); simulated_frame=pd.DataFrame({"timestamp":frame.timestamp,"discharge_sim":simulated,"model":name})
            if "event_id" in frame:simulated_frame["event_id"]=frame.event_id.to_numpy()
        elif kind=="external-command":
            command=run.get("command");
            if not isinstance(command,list) or not command:raise ValueError("external command must be a non-empty command array")
            done=subprocess.run(command,cwd=run_path.parent,capture_output=True,text=True,timeout=run.get("timeout_seconds",3600),check=False)
            if done.returncode:raise ValueError(f"external command failed ({done.returncode}): {done.stderr.strip()}")
            simulated_frame=pd.read_csv(run_path.parent/run.get("model_output_csv","model_output.csv"))
            if not {"timestamp","discharge_sim"}.issubset(simulated_frame.columns):raise ValueError("external output requires timestamp and discharge_sim columns")
        else:raise ValueError("unsupported model; use native Tank, HBV, XAJ, or external-command")
    except Exception as exc:return finish(out,result("model",errors=[str(exc)]))
    simulated_frame.to_parquet(out/"simulation.parquet",index=False);return finish(out,result("model",outputs=["simulation.parquet"],run=run))
