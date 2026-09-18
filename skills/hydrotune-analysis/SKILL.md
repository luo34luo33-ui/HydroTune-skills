---
name: hydrotune-analysis
description: 分析 HydroTune Intake 生成的归一化降雨径流数据，检查数据质量、事件特征、建模就绪性，并可选结合 Geo artifacts 做空间输入就绪性分析。用于建模前数据本体分析；不要用于模型误差诊断。
---

# HydroTune Analysis

本 Skill 指导 Agent 使用 HydroTune Analysis CLI 对 Intake 之后的数据做建模前预分析。runtime 负责确定性统计和 evidence artifact 生成；Agent 负责解释 evidence、说明限制，并在需要时生成中文智能预分析报告。

Analysis 只看数据本身。它不读取 `simulation.parquet`，不计算 NSE/KGE/RMSE/MAE/PBIAS，不解释模型误差原因；模型运行后的 observed-versus-simulated 诊断应切换到 `hydrotune-diagnosis`。

## 何时使用

使用本 Skill：

- `hydrotune-intake` 已经生成 `dataset.json` 和 `dataset.parquet`，且 dataset 状态不是 `error`。
- 用户想了解数据质量、时间覆盖、事件特征、水量诊断可用性或建模准备情况。
- 用户要求“预分析报告”“建模前数据检查”“数据是否适合建模”等。
- 用户已经有可解释来源的 Geo artifacts，且目标涉及分布式/半分布式模型、子流域、河道汇流或空间参数。

不使用本 Skill：

- 原始数据还没有经过 Intake；应先用 `hydrotune-intake`。
- 用户要求运行 HBV/XAJ/Tank、率定参数、模型比较或误差诊断。
- 用户只提供 DEM/边界/出口但还没有整理成 Geo artifacts；应回到 `hydrotune-intake` 的 Agent-first 空间前处理流程，而不是在 Analysis 中处理 DEM。

## 标准流程

基础时序预分析：

```text
python scripts/hydrotune.py analyze <dataset-dir> <analysis-dir>
```

如果用户已经有现成 Geo artifacts，并且当前目标需要空间输入就绪性分析：

```text
python scripts/hydrotune.py analyze <dataset-dir> <analysis-dir> --geo <geo-output-dir>
```

每次运行后必须读取 `result.json`。`error` 时停止并解释 runtime 错误；`warning` 时说明与建模有效性相关的风险；`success` 时可以进入报告或建模准备环节。

## Runtime evidence

Analysis runtime 生成：

- `analysis.json`：建模就绪性摘要、变量 readiness、时序 readiness、可选 geographic readiness。
- `preanalysis.json`：数据范围、时间覆盖、质量统计、事件统计、水量诊断可用性和 unavailable 原因。
- `event_features.parquet`：逐事件或逐降雨片段的确定性特征。
- `result.json`：本次 analysis 的权威执行状态。

Agent 不得用自己的判断替代 runtime 的 `unavailable`。如果 precipitation、discharge、timestep、basin area 或 Geo artifacts 不足，报告中必须保留“不可用/待确认”的状态。

## Geo-aware analysis

只有显式传入 `--geo` 时，Analysis 才读取 Geo artifacts。不要自动搜索邻近目录中的 `geo.json`。

传入 `--geo` 的条件：

- 用户目标需要分布式/半分布式模型、子流域、河道汇流或空间参数；
- Agent 或外部 GIS 工具已经生成 `geo.json` 及相关 artifacts，并且来源可解释；
- 用户希望把空间输入条件纳入建模前判断。

Analysis 只检查现成 Geo artifacts 的就绪性：`geo.json.status`、子流域数量、站点角色摘要、空间参数表、拓扑文件、DEM 派生 raster、可选 HRU artifacts 和关键文件是否存在。它不重新处理 DEM，不重跑 WhiteboxTools，不重新划分 HRU，不修改 Geo artifacts，也不猜测 CRS 或出口点科学含义。

## 智能预分析报告

如果用户要求中文预分析报告，先生成 deterministic evidence：

```text
python scripts/hydrotune.py analyze <dataset-dir> <analysis-dir> [--geo <geo-output-dir>]
python scripts/hydrotune.py report preanalysis --dataset <dataset-dir> --analysis <analysis-dir> <report-dir>
```

然后读取：

- [intelligent-preanalysis-report.md](references/intelligent-preanalysis-report.md)
- [report-evidence-rules.md](references/report-evidence-rules.md)
- `preanalysis-evidence.json`
- `analysis.json`
- `preanalysis.json`
- `event_features.parquet`

由 Agent 自带 LLM 生成中文 `intelligent-preanalysis-report.md`。报告必须区分观测事实、runtime 证据、工程推断、建模建议和待确认事项。所有数值结论必须来自 evidence；不得补算、估算或把 recommendation 写成 confirmation。

## 追问与解释规则

- Analysis 运行前通常不需要向用户确认新的科学参数；它读取已经由 Intake 确认并写入的 dataset metadata。
- 如果用户要求把 Geo 条件纳入预分析，但没有明确提供 Geo artifact 目录，必须先询问 `--geo` 路径或引导回 `hydrotune-intake` 的空间前处理流程。
- Analysis 运行后，如果 `analysis.json.modeling_readiness`、`preanalysis.json.unavailable` 或 `geographic_readiness` 暴露建模前缺口，应在进入 modeling/calibration 前把这些缺口转成用户确认问题。
- 每次最多问三个科学问题。
- 只追问会影响分析解释或后续建模决策的信息。
- 不重复询问用户已经明确确认的信息。
- 对缺失单位、流域面积、event warmup、Geo artifacts 不完整等问题，应说明其影响，而不是自行修补。
- 每个问题都应说明对应 evidence 字段和下游影响，例如是否会影响径流系数、事件评分 warmup、分布式模型空间输入或路由设置。
- 对 `event_collection`，必须保留事件独立性，不得把它描述成连续序列。

## 与 Diagnosis 的边界

Analysis 回答：“观测数据本身是否适合建模？”

Diagnosis 回答：“模型模拟结果与观测流量相比哪里偏差明显？”

如果用户要求解释模型高估、低估、洪峰错位、验证期表现或性能指标，应切换到 `hydrotune-diagnosis`，不要在 Analysis 中临时实现模型误差诊断。

## 参考模板

- 数据预分析报告：读取 [preanalysis-report.md](references/preanalysis-report.md)。
- 智能预分析报告：读取 [intelligent-preanalysis-report.md](references/intelligent-preanalysis-report.md)。
- 数据与建模就绪摘要：读取 [readiness-report.md](references/readiness-report.md)。
- 模型运行报告：读取 [model-run-report.md](references/model-run-report.md)。
- 模型比较摘要：读取 [comparison-report.md](references/comparison-report.md)。
- 所有报告都必须遵守 [report-evidence-rules.md](references/report-evidence-rules.md)。
