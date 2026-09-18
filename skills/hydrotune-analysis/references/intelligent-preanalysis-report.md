# 智能水文数据预分析报告模板

## 用途

用于指导 Agent 基于 HydroTune deterministic artifacts 生成中文增强版预分析报告。报告可以包含工程解释和后续建议，但所有技术事实、数值、状态和限制必须来自 evidence。

## 必须读取的证据

- `dataset.json`
- `analysis.json`
- `preanalysis.json`
- `event_features.parquet`
- `preanalysis-evidence.json`，如果已经运行 `hydrotune report preanalysis`
- `geo.json` 和相关 Geo artifacts，仅当 analysis 使用了 `--geo`
- `report-evidence-rules.md`

## 报告结构

报告正文建议包含以下部分：

1. 数据概况
2. 数据质量与可用性
3. 事件与水文特征
4. 空间数据与分布式建模就绪性
5. 建模准备判断
6. 后续建议
7. 证据来源

## 写作规则

- 每个技术事实都应能追溯到 `dataset.json`、`preanalysis.json`、`analysis.json`、`event_features.parquet` 或 `preanalysis-evidence.json`。
- 使用“观测事实”“工程推断”“建议”区分陈述类型。
- `unavailable` 项必须保留 evidence 中记录的原因，不得估算或补算。
- 对 `event_collection`，必须保留场次独立性，不得描述为一条连续水文序列。
- 存在 `geographic_readiness` 时，只说明 Geo artifacts 的完整性、子流域数量、站点角色、空间参数表和建模影响。
- 没有 `--geo` evidence 时，只说明本次预分析未纳入空间 artifacts，不得推断 DEM、子流域或河网条件。
- 建模准备判断必须使用 `analysis.json.modeling_readiness` 的状态、blocking、warning 和 enrichment 信息。

## 禁止事项

- 不得把列名、推断、常见水文惯例或工具建议写成用户确认事实。
- 不得计算 NSE、KGE、RMSE、MAE、PBIAS 或解释模拟误差；这些属于 Diagnosis 或 Calibration。
- 不得自行降低 runtime 给出的风险等级。
- 不得用模型偏好、地区经验或默认参数替代 evidence。
- 不得把工程建议写成观测事实。

## 输出要求

报告应使用中文 Markdown。每节应尽量包含：

- 事实依据：来自哪个 artifact。
- 工程含义：该事实可能影响什么。
- 待确认事项：如果 evidence 不足，说明需要用户补充什么。

证据来源部分必须列出本报告引用的 artifact 路径。报告不嵌入图表；图表由 Visualization artifacts 单独交付。
