# 报告证据规则

## 用途

用于约束所有 HydroTune 中文报告的证据使用、事实边界和表达方式。Agent 在撰写预分析、建模就绪、模型运行、模型比较或诊断相关报告前，应先应用本规则。

## 必须读取的证据

根据报告类型读取对应 evidence artifacts。常见来源包括：

- `dataset.json`
- `analysis.json`
- `preanalysis.json`
- `preanalysis-evidence.json`
- `model-run-evidence.json`
- `calibration.json`
- `comparison.json`
- `diagnosis.json`
- `figure.json`

报告只能使用已读取 evidence 中存在的值、状态、路径和说明。

## 报告结构

每份报告至少应包含：

1. 结论或摘要
2. 关键证据
3. 限制或风险
4. 下一步建议
5. 证据来源

具体章节名称可按对应模板调整，但证据来源必须保留。

## 写作规则

- 将陈述分为“观测事实”“工程推断”“建议”。
- 观测事实只能来自 evidence 中的明确字段。
- 工程推断必须基于 evidence，且在存在多个可能原因时使用条件式表达。
- 建议必须对应 evidence 中的限制、warning、blocking、unavailable 或用户目标。
- 每个报告章节至少引用一次其主要 evidence 来源。
- `unavailable` 必须保留原始原因，不得估算替代。
- 验证期结果必须写成外样本证据；率定期结果必须写成拟合阶段证据。

## 禁止事项

- 不得把 validation ranking 写成 calibration evidence。
- 不得从相关性、偏差或单一指标直接断言因果机制。
- 不得把列名推断、工具建议、常见经验或 Agent 判断写成用户确认事实。
- 不得补算 evidence 中没有的指标、参数、单位或空间属性。
- 不得把 `unavailable` 改写成可用结论。
- 不得在报告中嵌入图表；Visualization artifacts 是单独交付物。
- 不得复制大型原始 JSON、Parquet 内容或模拟序列到报告正文。

## 输出要求

报告使用中文 Markdown。数值、状态和模型名称应保持与 evidence 一致；必要时可翻译解释含义，但不得改变字段语义。证据来源部分列出 artifact 路径，便于用户追溯。
