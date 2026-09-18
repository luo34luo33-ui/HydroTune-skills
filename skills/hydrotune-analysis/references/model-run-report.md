# 水文模型运行结果分析报告模板

## 用途

用于指导 Agent 基于模型运行、率定、比较和诊断 evidence 撰写中文模型运行结果报告。报告应说明模型运行范围、数据划分、模型配置、性能证据、诊断信息、限制和后续行动。

## 必须读取的证据

- `dataset.json`
- `run.json`
- 模型运行 `result.json`
- `model-run-evidence.json`，如果已经运行 `hydrotune report model-run`
- `calibration.json`，仅当报告包含率定信息
- `comparison.json`，仅当报告包含模型比较或推荐信息
- `diagnosis.json`，仅当报告包含 observed-versus-simulated 诊断信息
- `report-evidence-rules.md`

## 报告结构

报告正文建议包含以下部分：

1. 运行范围与数据划分
2. 模型与参数配置
3. 路由与上游来水处理
4. 性能与诊断证据
5. 工程解释
6. 限制与下一步
7. 证据来源

## 写作规则

- 运行范围应说明数据形态、时间划分、率定期/验证期或事件集合 split。
- 对 `event_collection`，必须列明或概述率定事件和验证事件，并说明 warmup 样本不参与性能评价。
- 模型配置只能引用 `run.json`、`calibration.json` 或 `comparison.json` 中存在的参数。
- 若数据含上游来水并启用 Muskingum routing，只按 evidence 说明 `method`、`K`、`X` 和已记录的配置。
- 性能评价必须来自 `diagnosis.json`、`calibration.json` 或 `comparison.json` 中已有指标。
- 验证期结果必须表述为外样本证据。
- 工程解释应使用条件式表述，说明“可能提示”“需要复核”，不得写成确定因果。

## 禁止事项

- 不得将验证期排名、验证期指标或诊断结论描述为率定过程的证据。
- 不得根据单一指标直接断言降雨、蒸散、土地利用、DEM 或参数一定有问题。
- 不得编造未记录的参数、优化器、随机种子、routing 设置或模型版本。
- 不得手工补算性能指标来填补缺失 evidence。
- 不得嵌入图表；图表应作为 Visualization artifacts 单独交付。

## 输出要求

报告使用中文 Markdown。每个关键结论应标明证据来源。若某类 evidence 未提供，例如没有 `diagnosis.json`，应明确写成“未提供相应诊断 evidence”，不要补写诊断结论。
