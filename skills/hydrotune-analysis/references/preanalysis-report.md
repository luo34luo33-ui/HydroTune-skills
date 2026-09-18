# 水文数据预分析报告模板

## 用途

用于指导 Agent 基于 `preanalysis-evidence.json` 撰写中文基础预分析报告。该报告是 evidence-driven 的数据本体检查报告，不包含模型运行、率定、模型比较或误差诊断结论。

## 必须读取的证据

- `preanalysis-evidence.json`
- `dataset.json`，通过 evidence 中的来源路径核对
- `preanalysis.json`，通过 evidence 中的来源路径核对
- `event_features.parquet`，仅用于核对事件特征来源
- `report-evidence-rules.md`

## 报告结构

报告正文固定包含以下部分：

1. 数据范围与形态
2. 数据质量与建模可用性
3. 洪水事件与特征
4. 限制与后续建议
5. 证据来源

## 写作规则

- 每个数值陈述必须来自 `preanalysis-evidence.json`。
- 必须说明数据是 `continuous` 还是 `event_collection`。
- 对 `event_collection`，保留事件身份和独立性，不得描述为连续水文记录。
- 时间范围、样本数、变量角色、单位、流域面积、timestep、缺失率、重复时间戳和不规则间隔只能按 evidence 表述。
- 事件数量、洪峰、降雨总量、径流体积、径流系数等物理诊断必须以 availability 为前提。
- 若 evidence 记录某项 unavailable，必须说明原因。

## 禁止事项

- 不得补算 evidence 中没有的统计量。
- 不得把列名推断、常见经验或建议写成用户确认事实。
- 不得计算模型性能指标。
- 不得解释模型高估、低估、峰现错位或参数问题。
- 不得把报告写成模型选择建议。

## 输出要求

报告使用中文 Markdown。正文应短于智能预分析报告，重点是数据范围、质量、可用性和下一步需要补充的信息。证据来源部分必须列出引用 artifact 路径。
