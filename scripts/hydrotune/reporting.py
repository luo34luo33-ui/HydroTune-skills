"""HydroTune evidence-driven report artifact runtime."""

from __future__ import annotations
import json
from pathlib import Path
import pandas as pd
from .common import finish, result, write_json


def _read(path): return json.loads(Path(path).read_text(encoding="utf-8")) if path else None
def _header(sources): return "---\nreport_language: zh-CN\nsource_artifacts:\n"+"\n".join(f"  - {v}" for v in sources.values() if v)+"\n---\n\n"
def _sources_lines(sources): return ["## 证据来源", *[f"- {k}: `{v}`" for k,v in sources.items() if v]]
def _markdown_table(rows, columns):
    table = pd.DataFrame(rows, columns=columns)
    if table.empty: return "无可用技术核验数据。"
    display = table.copy()
    for column in display.select_dtypes(include="number"):
        display[column] = display[column].map(lambda value: f"{value:.6g}" if pd.notna(value) else "")
    return display.to_markdown(index=False)

def _event_metric_note(dataset):
    if dataset.get("series_mode") == "event_collection":
        return "率定期和验证期指标均按场次独立计算，并以场次指标的算术平均值报告。"
    return "率定期和验证期指标按连续时序数据划分计算。"


def cmd_report_readiness(args):
    out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
    try:
        sources={"dataset":str(Path(args.dataset)/"dataset.json"),"preanalysis":str(Path(args.analysis)/"preanalysis.json"),"analysis":str(Path(args.analysis)/"analysis.json")}; dataset=_read(sources["dataset"]);pre=_read(sources["preanalysis"]); analysis=_read(sources["analysis"]); quality=pre["quality"]
        readiness=(analysis or {}).get("modeling_readiness") or dataset.get("modeling_readiness") or {}
        status=readiness.get("modeling_status") or readiness.get("status") or "unknown"
        blocking=list(readiness.get("blocking", []))
        warnings=list(readiness.get("warnings", []))
        enrichment=list(readiness.get("enrichment_required", []))
        rows=[]
        for role,item in quality["variables"].items():
            rows.append({"role":role,"column":item["column"],"unit":item.get("unit"),"samples":item["samples"],"missing_fraction":item["missing_fraction"],"outlier_count":item["outlier_count"],"modeling_status":status})
        columns=["role","column","unit","samples","missing_fraction","outlier_count","modeling_status"]
        pd.DataFrame(rows,columns=columns).to_csv(out/"readiness-summary.csv",index=False,encoding="utf-8")
        actions=blocking + warnings + [f"{item} 需要外部数据补全。" for item in enrichment] + list(pre["unavailable"])
        if not actions: actions=["数据满足当前已知模型输入要求；可进入建模与率定阶段。"]
        lines=[_header(sources),"# 数据与建模就绪摘要","","## 决策结论",f"- 建模状态：**{status}**。",f"- 数据形态：`{dataset.get('series_mode')}`；样本数：{pre['data_scope']['samples']}。",f"- {_event_metric_note(dataset)}","","## 数据质量与建模条件",f"- 重复时间戳：{quality['duplicate_timestamps']}；不规则/缺口间隔：{quality['irregular_or_gap_intervals']}。",f"- 已识别/保留洪水事件：{pre['event_summary']['count']}。","","## 待处理事项与下一步",*[f"- {item}" for item in actions],"","## 技术核验表",_markdown_table(rows,columns),"",*_sources_lines(sources)]
        (out/"readiness-report.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
        return finish(out,result("report-readiness",outputs=["readiness-report.md","readiness-summary.csv"],modeling_status=status))
    except Exception as exc:return finish(out,result("report-readiness",errors=[str(exc)]))

def cmd_report_comparison(args):
    out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
    try:
        sources={"dataset":str(Path(args.dataset)/"dataset.json"),"comparison":str(Path(args.comparison)/"comparison.json"),"diagnosis":args.diagnosis}; dataset=_read(sources["dataset"]); comparison=_read(sources["comparison"]); diagnosis=_read(args.diagnosis)
        rows=[]
        for item in comparison["ranking"]:
            routing=item.get("routing") or {}; validation=item.get("validation") or {}; calibration=item.get("calibration") or {}
            rows.append({"model":item["model"],"rank":next((index for index,candidate in enumerate(comparison["ranking"],1) if candidate["model"]==item["model"]),None),"optimizer":comparison.get("optimizer"),"objective":comparison.get("objective"),"routing_K":routing.get("K"),"routing_X":routing.get("X"),"calibration_NSE":calibration.get("NSE"),"validation_NSE":validation.get("NSE"),"validation_KGE":validation.get("KGE"),"validation_RMSE":validation.get("RMSE"),"validation_MAE":validation.get("MAE"),"validation_PBIAS":validation.get("PBIAS"),"bma_weight":comparison.get("bma",{}).get("weights",{}).get(item["model"])})
        bma=comparison.get("bma",{}); bma_validation=bma.get("validation_metrics",{})
        rows.append({"model":"bma","rank":None,"optimizer":comparison.get("optimizer"),"objective":comparison.get("objective"),"routing_K":None,"routing_X":None,"calibration_NSE":bma.get("calibration_metrics",{}).get("NSE"),"validation_NSE":bma_validation.get("NSE"),"validation_KGE":bma_validation.get("KGE"),"validation_RMSE":bma_validation.get("RMSE"),"validation_MAE":bma_validation.get("MAE"),"validation_PBIAS":bma_validation.get("PBIAS"),"bma_weight":None})
        columns=["model","rank","optimizer","objective","routing_K","routing_X","calibration_NSE","validation_NSE","validation_KGE","validation_RMSE","validation_MAE","validation_PBIAS","bma_weight"]
        pd.DataFrame(rows,columns=columns).to_csv(out/"comparison-decision.csv",index=False,encoding="utf-8")
        recommended=comparison["recommended_model"]; selected=next(item for item in comparison["ranking"] if item["model"]==recommended); validation=selected.get("validation",{}); routed=any(item.get("routing") for item in comparison["ranking"])
        risks=(diagnosis or {}).get("hypotheses") or (["诊断 artifact 未提供；未生成额外诊断风险结论。"] if diagnosis is None else ["诊断未识别需报告的系统性偏差。"])
        lines=[_header(sources),"# 模型比较与推荐摘要","","## 决策结论",f"- 推荐模型：**{recommended.upper()}**（按验证期 NSE 排名）。",f"- 推荐模型验证期 NSE：{validation.get('NSE','unavailable')}。",f"- BMA 权重仅基于率定期 NSE；验证期仅用于独立评估。",f"- {_event_metric_note(dataset)}","","## 配置与路由",f"- 率定算法：`{comparison.get('optimizer')}`；目标函数：`{comparison.get('objective')}`；随机种子：{comparison.get('seed')}。",f"- Muskingum 路由：{'已启用；K/X 见技术核验表。' if routed else '未启用（数据未要求上游来水路由）。'}","","## 风险与下一步",*[f"- {item}" for item in risks],"- 将推荐模型的验证期表现作为外样本依据；如需工程应用，应结合流域外部验证和参数合理性复核。","","## 技术核验表",_markdown_table(rows,columns),"",*_sources_lines(sources)]
        (out/"comparison-report.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
        return finish(out,result("report-comparison",outputs=["comparison-report.md","comparison-decision.csv"],recommended_model=recommended))
    except Exception as exc:return finish(out,result("report-comparison",errors=[str(exc)]))

def cmd_report_preanalysis(args):
    out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
    try:
        sources={"dataset":str(Path(args.dataset)/"dataset.json"),"preanalysis":str(Path(args.analysis)/"preanalysis.json"),"event_features":str(Path(args.analysis)/"event_features.parquet")}; dataset=_read(sources["dataset"]);pre=_read(sources["preanalysis"])
        evidence={"schema_version":"hydrotune.report-evidence.v1","report_type":"preanalysis","artifact_sources":sources,"dataset":{k:dataset.get(k) for k in ("series_mode","timestep","splits","variables","basin")},"preanalysis":pre};write_json(out/"preanalysis-evidence.json",evidence)
        q=pre["quality"]; lines=[_header(sources),"# 水文数据预分析报告","","## 数据范围与形态",f"- 数据形态：{dataset.get('series_mode')}。",f"- 样本数：{pre['data_scope']['samples']}。","","## 数据质量与建模可用性",f"- 重复时间戳：{q['duplicate_timestamps']}；不规则/缺口间隔：{q['irregular_or_gap_intervals']}。","","## 洪水事件与特征",f"- 识别/保留事件数：{pre['event_summary']['count']}。","","## 限制与后续建议",*[f"- {x}" for x in pre["unavailable"]],"","## 工程分析（由宿主 LLM 基于 evidence 补充）","- 仅可引用 `preanalysis-evidence.json` 中的事实；应区分观测事实、工程推断和建议。","",*_sources_lines(sources)]
        (out/"data-preanalysis-report.md").write_text("\n".join(lines)+"\n",encoding="utf-8");return finish(out,result("report-preanalysis",outputs=["preanalysis-evidence.json","data-preanalysis-report.md"]))
    except Exception as exc:return finish(out,result("report-preanalysis",errors=[str(exc)]))

def cmd_report_model_run(args):
    out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
    try:
        sources={"dataset":str(Path(args.dataset)/"dataset.json"),"run":args.run,"model_result":args.model_result,"calibration":args.calibration,"comparison":args.comparison,"diagnosis":args.diagnosis}; dataset=_read(sources["dataset"]);run=_read(args.run)
        evidence={"schema_version":"hydrotune.report-evidence.v1","report_type":"model_run","artifact_sources":sources,"dataset":{k:dataset.get(k) for k in ("series_mode","splits","variables")},"run":run,"model_result":_read(args.model_result),"calibration":_read(args.calibration),"comparison":_read(args.comparison),"diagnosis":_read(args.diagnosis)};write_json(out/"model-run-evidence.json",evidence)
        lines=[_header(sources),"# 水文模型运行结果分析报告","","## 运行范围与数据划分",f"- 数据形态：{dataset.get('series_mode')}。",f"- 切分：`{dataset.get('splits')}`。","","## 模型与率定配置",f"- 模型：{run.get('model') if run else 'unavailable'}。",f"- Muskingum 路由：{run.get('routing') if run and run.get('routing') else '未配置'}。","","## 性能与诊断证据",f"- 诊断：{evidence['diagnosis'] if evidence['diagnosis'] else 'unavailable'}。","","## 工程分析（由宿主 LLM 基于 evidence 补充）","- 不得将验证期排名描述为率定证据；仅依据 evidence 说明过拟合风险、限制与建议。","",*_sources_lines(sources)]
        (out/"model-run-analysis-report.md").write_text("\n".join(lines)+"\n",encoding="utf-8");return finish(out,result("report-model-run",outputs=["model-run-evidence.json","model-run-analysis-report.md"]))
    except Exception as exc:return finish(out,result("report-model-run",errors=[str(exc)]))
