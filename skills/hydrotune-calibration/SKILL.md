---
name: hydrotune-calibration
description: Search rainfall-runoff model parameters and report reproducible objective metrics. Use after a runnable HydroTune model contract and observed discharge are available.
---

# HydroTune Calibration

本 Skill 用于参数率定和三模型比较。它可以调用：

```text
python scripts/hydrotune.py calibrate <dataset-dir> <output-dir> --optimizer <algorithm>
python scripts/hydrotune.py compare <dataset-dir> <output-dir> --optimizer <algorithm>
```

它不做 Intake、Analysis、建模前图表或模型误差叙事诊断。

## 运行前确认

在调用 `calibrate` 或 `compare` 前，必须确认：

- 优化器：用户必须从 `de`、`pso`、`ga`、`sce`、`two_stage` 中选择一个；不得由 Agent 默认选择。
- 目标函数：如果用户明确给出，按用户选择传入；否则 runtime 默认 NSE，但报告时必须说明这是 runtime 默认 objective。
- `event_collection` 的 `warmup_steps`：必须已经由用户确认，否则不得率定或比较。
- 如果 dataset 含 confirmed `upstream_discharge`，Muskingum routing 必须参与率定；不得绕过上游来水。
- 若用户提供自定义 bounds、iterations、seed 或 optimizer config，必须原样记录并传入。

不要把 Analysis 的 readiness、常见经验参数范围或 Agent 判断当作用户确认的 optimizer、warmup 或 routing 选择。

## Event collection 指标口径

对 `event_collection`，每个 calibration 或 validation 事件必须在排除 confirmed warmup 样本后独立计算指标。split-level 指标是事件指标的算术平均值，不得把不同事件样本池化后计算一个总指标。

## Routing 规则

如果 dataset 包含 confirmed `upstream_discharge`，Calibration 必须把 `routing.K` 和 `routing.X` 纳入搜索空间，并将选中的 K/X 与模型参数一起持久化。

## Compare 规则

`compare` 对 Tank、HBV、XAJ 使用同一个用户确认的 optimizer、objective、seed 和 split。模型排名只依据 validation NSE；BMA 权重只来自 calibration NSE。

## Result handling

运行后读取 `result.json`：

- `success`：可以进入 comparison report、visualization 或 diagnosis。
- `warning`：说明 warning 对参数可信度或后续应用的影响。
- `error`：停止；不要手工补 calibration artifact 或修改 validation 结果。
