---
name: hydrotune-diagnosis
description: Diagnose observed-versus-simulated runoff differences with metrics, timing evidence, and bounded hypotheses. Use after a HydroTune model result exists.
---

# HydroTune Diagnosis

本 Skill 用于模型运行后诊断 observed-versus-simulated runoff 差异：

```text
python scripts/hydrotune.py diagnose <dataset-dir> <simulation.parquet> <output-dir>
```

它不做建模前数据预分析、不运行模型、不率定参数。

## 运行前确认

调用前必须确认：

- dataset 来自成功或 warning 状态的 HydroTune Intake artifact。
- `simulation.parquet` 是用户想诊断的模型输出，而不是 calibration/validation/ensemble 中的误选文件。
- 如果同一研究中有多个模型、BMA 或 routed simulation，必须确认要诊断哪一个 artifact，并在解释中说明 provenance。
- 对 `event_collection`，dataset 中必须已有 confirmed `warmup_steps`；否则先回到 modeling/calibration 所需确认。

不要凭最近生成的文件名自动决定用户要诊断哪个模型；如果存在多个 plausible simulation，先问。

## 解释规则

Diagnosis 可以报告 aggregate bias、fit metrics、洪峰幅值差异、缺失 overlap 和 runtime 产生的 hypotheses。

必须区分：

- 观测/模拟证据：来自 `diagnosis.json.evidence`。
- 有界假设：来自 `diagnosis.json.hypotheses` 或由 Agent 基于 evidence 谨慎表述。
- 未确认原因：需要外部资料或用户补充才能判断的机制。

可能原因不是事实。不得仅凭 PBIAS、峰值差异或散点图就断言降雨、蒸散发、土地利用、DEM 或参数一定有问题。

## Result handling

运行后读取 `result.json`：

- `success`：可以生成诊断说明或模型运行报告。
- `warning`：说明 warning 是否影响诊断可信度。
- `error`：停止；不要手工合并 observed/simulated 或临时计算指标来绕过 runtime。
