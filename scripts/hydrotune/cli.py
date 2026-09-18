"""HydroTune command-line adapter and command registry."""

from __future__ import annotations
import argparse
from pathlib import Path
from .analysis import cmd_analyze
from .calibration import cmd_calibrate
from .diagnosis import cmd_diagnose
from .intake import cmd_intake, load_dataset
from .modeling import cmd_model
from .comparison import cmd_compare
from .reporting import cmd_report_comparison, cmd_report_model_run, cmd_report_preanalysis, cmd_report_readiness
from .visualization import cmd_visualize_dataset, cmd_visualize_events, cmd_visualize_geo


def cmd_export(args):
    try: frame,_=load_dataset(Path(args.dataset));frame.to_csv(args.output,index=False);print('{"status":"success"}');return 0
    except Exception as exc: print('{"status":"error","error":"'+str(exc)+'"}');return 2
def main(argv=None):
    parser=argparse.ArgumentParser(prog="hydrotune");sub=parser.add_subparsers(dest="command",required=True)
    p=sub.add_parser("intake");p.add_argument("input");p.add_argument("output");p.add_argument("--time-column",required=True);p.add_argument("--role",action="append",default=[],help="confirmed HydroTune role mapping, e.g. precipitation=Rain");p.add_argument("--unit",action="append",default=[]);p.add_argument("--basin-id",default=None);p.add_argument("--basin-area-km2",type=float);p.add_argument("--series-mode",choices=["continuous","event_collection"]);p.add_argument("--extract-events",action="store_true");p.add_argument("--event-flow-threshold",type=float);p.add_argument("--event-merge-gap-steps",type=int);p.add_argument("--modeling-intent",choices=["rainfall_runoff","artifact_only"],default="rainfall_runoff");p.set_defaults(func=cmd_intake)
    p=sub.add_parser("analyze");p.add_argument("dataset");p.add_argument("output");p.add_argument("--geo");p.set_defaults(func=cmd_analyze)
    p=sub.add_parser("model");p.add_argument("run");p.add_argument("output");p.set_defaults(func=cmd_model)
    p=sub.add_parser("calibrate");p.add_argument("dataset");p.add_argument("output");p.add_argument("--model",choices=["hbv","xaj","tank"],default="hbv");p.add_argument("--optimizer",choices=["de","pso","ga","sce","two_stage"],required=True,help="required calibration algorithm selected before execution");p.add_argument("--objective",choices=["NSE","KGE","RMSE","MAE","PBIAS"],default="NSE");p.add_argument("--optimizer-config");p.add_argument("--iterations",type=int,default=100);p.add_argument("--seed",type=int,default=42);p.add_argument("--bounds");p.set_defaults(func=cmd_calibrate)
    p=sub.add_parser("diagnose");p.add_argument("dataset");p.add_argument("simulation");p.add_argument("output");p.set_defaults(func=cmd_diagnose)
    p=sub.add_parser("visualize");visualize=p.add_subparsers(dest="visualize_command",required=True)
    q=visualize.add_parser("dataset");q.add_argument("dataset");q.add_argument("output");q.add_argument("--variables",nargs="+");q.set_defaults(func=cmd_visualize_dataset)
    q=visualize.add_parser("events");q.add_argument("dataset");q.add_argument("analysis");q.add_argument("output");q.set_defaults(func=cmd_visualize_events)
    q=visualize.add_parser("geo");q.add_argument("geo");q.add_argument("output");q.set_defaults(func=cmd_visualize_geo)
    p=sub.add_parser("compare");p.add_argument("dataset");p.add_argument("output");p.add_argument("--optimizer",choices=["de","pso","ga","sce","two_stage"],required=True,help="one required algorithm, shared by Tank/HBV/XAJ");p.add_argument("--objective",choices=["NSE","KGE","RMSE","MAE","PBIAS"],default="NSE");p.add_argument("--optimizer-config");p.add_argument("--iterations",type=int,default=100);p.add_argument("--seed",type=int,default=42);p.add_argument("--bma-temperature",type=float,default=2.0);p.set_defaults(func=cmd_compare)
    p=sub.add_parser("report");reports=p.add_subparsers(dest="report_type",required=True)
    q=reports.add_parser("preanalysis");q.add_argument("--dataset",required=True);q.add_argument("--analysis",required=True);q.add_argument("output");q.set_defaults(func=cmd_report_preanalysis)
    q=reports.add_parser("model-run");q.add_argument("--dataset",required=True);q.add_argument("--run",required=True);q.add_argument("--model-result");q.add_argument("--calibration");q.add_argument("--comparison");q.add_argument("--diagnosis");q.add_argument("output");q.set_defaults(func=cmd_report_model_run)
    q=reports.add_parser("readiness",help="generate compact data-and-model readiness report");q.add_argument("--dataset",required=True);q.add_argument("--analysis",required=True);q.add_argument("output");q.set_defaults(func=cmd_report_readiness)
    q=reports.add_parser("comparison",help="generate compact model comparison and recommendation report");q.add_argument("--dataset",required=True);q.add_argument("--comparison",required=True);q.add_argument("--diagnosis");q.add_argument("output");q.set_defaults(func=cmd_report_comparison)
    p=sub.add_parser("export");p.add_argument("dataset");p.add_argument("output");p.set_defaults(func=cmd_export)
    args=parser.parse_args(argv);return args.func(args)
