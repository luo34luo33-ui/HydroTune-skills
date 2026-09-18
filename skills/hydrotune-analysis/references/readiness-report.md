# 数据与建模就绪摘要模板

## 用途

用于指导 Agent 撰写跨平台交付用的中文数据与建模就绪摘要。报告应帮助用户快速判断当前 dataset 是否可以进入建模、率定或比较，并明确还缺哪些科学确认或输入条件。

## 必须读取的证据

- `dataset.json`
- `analysis.json`
- `preanalysis.json`
- `readiness-summary.csv`，仅用于核对变量级摘要输出
- `report-evidence-rules.md`

## 报告结构

报告正文固定包含以下部分：

1. 决策结论
2. 数据质量与建模条件
3. 待处理事项与下一步
4. 技术核验表
5. 证据来源

首屏只说明：

- 建模状态。
- 数据形态。
- 样本数。
- 连续序列或事件集合的指标口径。

不要复制完整输入元数据、完整事件明细或原始 JSON。

## 写作规则

- 建模状态必须来自 `analysis.json.modeling_readiness` 或 `dataset.json.modeling_readiness`。
- blocking、warning、enrichment_required 和 unavailable 项必须逐项保留，不得合并成模糊描述。
- 变量级质量信息只引用 evidence 中已有的 role、column、unit、samples、missing_fraction、outlier_count。
- 对 `event_collection`，说明 warmup 是否仍需确认；未确认时不得建议直接进入评分或率定。
- 如果 Geo readiness 存在，只说明空间 artifacts 是否满足当前建模目标，不重新处理或解释 DEM。

## 禁止事项

- 不得因为没有 blocking 就忽略 warning。
- 不得把 `ready_with_warnings` 写成完全就绪。
- 不得为缺失 PET、流域面积、单位、warmup 或 Geo artifacts 提供猜测值。
- 不得在摘要目录复制原始 `dataset.json`、`preanalysis.json` 或 `event_features.parquet`。

## 输出要求

Markdown 报告应简洁，优先给出是否可进入下一步和需要补齐的事项。

CSV 必须逐变量列出：

- `role`
- `column`
- `unit`
- `samples`
- `missing_fraction`
- `outlier_count`
- `modeling_status`

证据来源部分必须列出所引用 artifact 的路径。
