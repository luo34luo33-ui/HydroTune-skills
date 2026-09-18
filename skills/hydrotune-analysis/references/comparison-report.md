# 模型比较与推荐摘要模板

## 用途

用于指导 Agent 基于 `comparison.json` 和可选 `diagnosis.json` 撰写中文模型比较与推荐摘要。报告面向跨平台交付，应帮助用户快速理解推荐模型、验证期表现、BMA 权重口径、路由配置和主要风险。

## 必须读取的证据

- `dataset.json`
- `comparison.json`
- `diagnosis.json`，仅当用户提供或报告命令已生成
- `comparison-decision.csv`，仅用于核对报告表格输出，不作为新增事实来源

## 报告结构

报告正文固定包含以下部分：

1. 决策结论
2. 配置与路由
3. 风险与下一步
4. 技术核验表
5. 证据来源

首屏必须说明：

- 推荐模型及推荐依据。
- 推荐模型的验证期 NSE。
- BMA 权重来自率定期表现，验证期只用于独立评估。
- 指标口径是连续序列划分，还是 `event_collection` 的逐场次独立计算后算术平均。

## 写作规则

- 模型排名只能按 `comparison.json.selection_metric` 或 `comparison.json.ranking` 表述。
- 验证期表现必须写成 out-of-sample evidence，不得描述为率定阶段证据。
- BMA 权重只按 `comparison.json.bma.fit_split` 和 `comparison.json.bma.weights` 解释。
- 若存在 Muskingum routing，只引用证据中的 `K`、`X` 和 routing 配置；不得补充未记录的稳定性结论。
- 风险与下一步可以引用 `diagnosis.json.hypotheses`，但必须说明这些是假设或待复核事项。

## 禁止事项

- 不得把 validation ranking 写成 calibration evidence。
- 不得声称推荐模型在所有流域、所有洪水类型或工程场景中一定最优。
- 不得根据 NSE、KGE 或 PBIAS 单独断言具体因果机制。
- 不得复制模拟序列、图表、完整率定历史或大型 JSON 内容到摘要报告。
- 不得为缺失的模型、BMA 权重或诊断结论编造占位解释。

## 输出要求

Markdown 报告应简洁，优先给出结论和限制。技术表格应覆盖 Tank、HBV、XAJ 和 BMA。

CSV 至少包含：

- `model`
- `rank`
- `optimizer`
- `objective`
- `routing_K`
- `routing_X`
- `calibration_NSE`
- `validation_NSE`
- `validation_KGE`
- `validation_RMSE`
- `validation_MAE`
- `validation_PBIAS`
- `bma_weight`

证据来源部分必须列出所引用 artifact 的路径。
