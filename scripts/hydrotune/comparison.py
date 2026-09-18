"""HydroTune multi-model comparison and BMA runtime."""

from __future__ import annotations
import argparse
import json
from pathlib import Path
import subprocess
import sys
import numpy as np
import pandas as pd
from .calibration import cmd_calibrate
from .common import finish, result, write_json
from .ensemble import bma, bma_weights
from .intake import load_dataset, select_scoring_frame
from .metrics import metrics
from .modeling import _assert_modeling_ready, simulate


MODEL_ORDER = ("tank", "hbv", "xaj")


def _run_parameters(meta: dict, parameters: dict) -> dict:
    """Restore standard input-column hints so a calibrated run contract is reusable."""
    result = dict(parameters)
    for variable in meta["variables"]:
        role = variable["role"]
        if role in {"precipitation", "temperature", "pet"}:
            result.setdefault(f"{role}_column", variable["column"])
    return result


def _simulation_frame(frame: pd.DataFrame, meta: dict, name: str, parameters: dict, routing: dict | None, discharge: str, split: str | None = None) -> pd.DataFrame:
    payload = pd.DataFrame({"timestamp": frame.timestamp.to_numpy(), "discharge_obs": pd.to_numeric(frame[discharge], errors="coerce").to_numpy(), "discharge_sim": simulate(frame, meta, name, parameters, routing), "model": name})
    if "event_id" in frame: payload["event_id"] = frame.event_id.to_numpy()
    if split: payload["split"] = split
    return payload


def _ensemble_frame(frame: pd.DataFrame, discharge: str, simulated: np.ndarray, split: str | None = None) -> pd.DataFrame:
    """Create a BMA artifact without treating the ensemble as a native model."""
    payload = pd.DataFrame({"timestamp": frame.timestamp.to_numpy(), "discharge_obs": pd.to_numeric(frame[discharge], errors="coerce").to_numpy(), "discharge_sim": simulated, "model": "bma"})
    if "event_id" in frame: payload["event_id"] = frame.event_id.to_numpy()
    if split: payload["split"] = split
    return payload


def _write_table(out: Path, rows: list[dict]) -> None:
    columns = ["model", "rank", "optimizer", "objective", "routing_required", "routing_K", "routing_X", "calibration_NSE", "calibration_KGE", "calibration_RMSE", "calibration_MAE", "calibration_PBIAS", "validation_NSE", "validation_KGE", "validation_RMSE", "validation_MAE", "validation_PBIAS"]
    table = pd.DataFrame(rows, columns=columns)
    table.to_csv(out / "comparison-summary.csv", index=False)
    display = table.copy()
    for column in display.select_dtypes(include="number"):
        display[column] = display[column].map(lambda value: f"{value:.6g}" if pd.notna(value) else "")
    (out / "comparison-summary.md").write_text(display.to_markdown(index=False) + "\n", encoding="utf-8")


def _render_standard_figures(dataset: Path, out: Path, meta: dict, simulation_paths: dict[str, Path], provenance: dict) -> list[str]:
    """Use only the fixed visualization templates bundled with HydroTune."""
    root = Path(__file__).parents[2]
    visual = root / "skills" / "hydrotune-visualization" / "scripts"
    outputs = []
    for name, simulation in simulation_paths.items():
        target = out / "figures" / name
        if meta.get("series_mode") == "continuous":
            png = target / "hydrograph.png"
            command = [sys.executable, str(visual / "plot_hydrograph.py"), "--dataset", str(dataset / "dataset.parquet"), "--simulation", str(simulation), "--metadata", str(dataset / "dataset.json"), "--output", str(png)]
        else:
            command = [sys.executable, str(visual / "plot_event_panel.py"), "--dataset", str(dataset / "dataset.parquet"), "--simulation", str(simulation), "--metadata", str(dataset / "dataset.json"), "--output-dir", str(target)]
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        if completed.returncode:
            raise ValueError(f"{name} fixed visualization failed: {completed.stderr.strip() or completed.stdout.strip()}")
        figure = target / "figure.json"
        evidence = json.loads(figure.read_text(encoding="utf-8")); evidence["comparison_provenance"] = provenance | {"model": name}
        write_json(figure, evidence)
        outputs.append(str(figure))
    return outputs


def cmd_compare(args):
    out=Path(args.output); out.mkdir(parents=True,exist_ok=True)
    try:
        dataset = Path(args.dataset); frame,meta=load_dataset(dataset); _assert_modeling_ready(meta); discharge=next(v["column"] for v in meta["variables"] if v["role"]=="discharge"); items=[]; validation_sims=[]; calibration_sims=[]; calibration_scores=[]; figure_inputs={}; calibration_frame=select_scoring_frame(frame,meta,"calibration"); validation_frame=select_scoring_frame(frame,meta,"validation")
        for name in MODEL_ORDER:
            directory=out/name; calibration_args=argparse.Namespace(dataset=args.dataset,output=directory,model=name,optimizer=args.optimizer,objective=args.objective,optimizer_config=args.optimizer_config,iterations=args.iterations,seed=args.seed,bounds=None)
            if cmd_calibrate(calibration_args): raise ValueError(f"{name} calibration failed")
            payload=json.loads((directory/"calibration.json").read_text(encoding="utf-8")); params=_run_parameters(meta, payload["selected"]["parameters"]); routing=payload["selected"].get("routing")
            run={"schema_version":"hydrotune.run.v1","model":{"kind":"native","name":name},"input_dataset":str(dataset.resolve()),"parameters":params}
            if routing: run["routing"]=routing
            write_json(directory/"calibrated-run.json",run)
            calibration_simulation=_simulation_frame(calibration_frame,meta,name,params,routing,discharge,"calibration"); validation_simulation=_simulation_frame(validation_frame,meta,name,params,routing,discharge,"validation")
            calibration_simulation.to_parquet(directory/"calibration-simulation.parquet",index=False); validation_simulation.to_parquet(directory/"validation-simulation.parquet",index=False)
            calibration_report=metrics(calibration_simulation.discharge_obs.to_numpy(float),calibration_simulation.discharge_sim.to_numpy(float)); validation_report=metrics(validation_simulation.discharge_obs.to_numpy(float),validation_simulation.discharge_sim.to_numpy(float))
            full_simulation=_simulation_frame(frame,meta,name,params,routing,discharge); full_simulation.to_parquet(directory/"simulation.parquet",index=False)
            item={"model":name,"calibration":calibration_report,"validation":validation_report,"parameters":params,"routing":routing,"artifacts":{"run":str(directory/"calibrated-run.json"),"calibration_simulation":str(directory/"calibration-simulation.parquet"),"validation_simulation":str(directory/"validation-simulation.parquet"),"simulation":str(directory/"simulation.parquet")}}
            items.append(item); validation_sims.append(validation_simulation.discharge_sim.to_numpy(float)); calibration_sims.append(calibration_simulation.discharge_sim.to_numpy(float)); calibration_scores.append(calibration_report["NSE"]); figure_inputs[name]=directory/"simulation.parquet"
        weights=bma_weights(calibration_scores,args.bma_temperature); bma_calibration=_ensemble_frame(calibration_frame,discharge,bma(calibration_sims,weights),"calibration"); bma_validation=_ensemble_frame(validation_frame,discharge,bma(validation_sims,weights),"validation")
        bma_calibration.to_parquet(out/"bma-calibration-simulation.parquet",index=False); bma_validation.to_parquet(out/"bma-validation-simulation.parquet",index=False)
        full_bma = _ensemble_frame(frame,discharge,bma([pd.read_parquet(item["artifacts"]["simulation"]).discharge_sim.to_numpy(float) for item in items],weights)); full_bma.to_parquet(out/"bma-simulation.parquet",index=False); figure_inputs["bma"]=out/"bma-simulation.parquet"
        bma_calibration_metrics=metrics(bma_calibration.discharge_obs.to_numpy(float),bma_calibration.discharge_sim.to_numpy(float)); ensemble_metrics=metrics(bma_validation.discharge_obs.to_numpy(float),bma_validation.discharge_sim.to_numpy(float)); ranking=sorted(items,key=lambda x:x["validation"]["NSE"],reverse=True)
        ranks={item["model"]: index for index,item in enumerate(ranking,1)}; table_rows=[]
        for item in items:
            routing=item["routing"] or {}; table_rows.append({"model":item["model"],"rank":ranks[item["model"]],"optimizer":args.optimizer,"objective":args.objective.upper(),"routing_required":bool(routing),"routing_K":routing.get("K"),"routing_X":routing.get("X"),**{f"calibration_{key}":item["calibration"].get(key) for key in ("NSE","KGE","RMSE","MAE","PBIAS")},**{f"validation_{key}":item["validation"].get(key) for key in ("NSE","KGE","RMSE","MAE","PBIAS")}})
        _write_table(out,table_rows)
        provenance={"optimizer":args.optimizer,"objective":args.objective.upper(),"routing_required":any(item["routing"] for item in items),"bma_fit_split":"calibration","bma_weights":{item["model"]:float(weight) for item,weight in zip(items,weights)}}
        figure_outputs=_render_standard_figures(dataset,out,meta,figure_inputs,provenance)
        payload={"objective":args.objective.upper(),"optimizer":args.optimizer,"seed":args.seed,"iterations":args.iterations,"selection_metric":"validation_NSE","ranking":ranking,"recommended_model":ranking[0]["model"],"bma":{"weights":provenance["bma_weights"],"fit_split":"calibration","calibration_metrics":bma_calibration_metrics,"validation_metrics":ensemble_metrics,"artifacts":{"calibration_simulation":"bma-calibration-simulation.parquet","validation_simulation":"bma-validation-simulation.parquet","simulation":"bma-simulation.parquet"}},"summary":{"csv":"comparison-summary.csv","markdown":"comparison-summary.md"},"figures":figure_outputs}
        write_json(out/"comparison.json",payload)
        outputs=["comparison.json","comparison-summary.csv","comparison-summary.md","bma-calibration-simulation.parquet","bma-validation-simulation.parquet","bma-simulation.parquet",*figure_outputs]
        return finish(out,result("compare",outputs=outputs,recommended_model=ranking[0]["model"]))
    except Exception as exc: return finish(out,result("compare",errors=[str(exc)]))
