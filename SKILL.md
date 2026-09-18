---
name: hydrotune-skills
description: 路由可复现的流域降雨径流研究 workflow，协调 HydroTune 的 intake、analysis、modeling、calibration、diagnosis、reporting 和 visualization skills。
---

# HydroTune-Skills

## 总体定位

HydroTune-Skills 是一套面向流域降雨径流研究的可复用工作流组件。Agent 负责理解用户目标、前处理原始数据、解释证据、识别科学不确定性并向用户确认关键决策；HydroTune CLI 负责核心水文计算、artifact 生成和结果状态记录。

优先使用仓库内置 CLI 完成已覆盖的计算和制图任务：

```text
python scripts/hydrotune.py <command> ...
```

当安装为 Python package 后，`hydrotune <command> ...` 与上述命令等价。所有路径应显式传入，不依赖宿主环境的隐式工作目录。

## 安装与运行

安装或复制时必须保留整个仓库结构：

```text
HydroTune-Skills/
  SKILL.md
  skills/
  contracts/
  scripts/
  references/
  pyproject.toml
```

使用 Python 3.10 或更高版本。从仓库根目录安装 deterministic runtime：

```text
python -m pip install -e .
```

XLSX intake 需要 `openpyxl`。Geo visualization 依赖可选 GIS 包；DEM、边界、出口、站点、子流域或 HRU 的前处理由 Agent 或外部 GIS 工具完成，不属于核心 CLI runtime。

## 稳定 artifact contract

HydroTune 的核心 artifact 流程是：

```text
dataset.parquet + dataset.json  ->  run.json  ->  result.json
```

- `dataset.parquet` 保存标准化时序数据。
- `dataset.json` 保存变量、单位、时间元数据、流域元数据、split、用户确认和 provenance。
- `run.json` 描述模型运行、输入、参数、时间范围、输出位置和软件上下文。
- `result.json` 是每次 CLI 执行的权威结果。

读取 `result.json` 后再进入下一步：

- `success`：可以继续当前 workflow。
- `warning`：只有 warning 不影响当前科学有效性时才继续，并向用户说明相关风险。
- `error`：必须停止当前阶段，不得手工改 artifact、绕过 validation 或伪造成功结果。

不得发明单位、流域属性、缺测值、模型参数或物理结论。`unavailable` 必须保留其原因，不能由 Agent 估算替代。

## Skill 路由表

先读本根文件，再只加载当前任务需要的 component `SKILL.md`。不要一次性加载所有 component skill。

| 用户目标 | 读取并使用 |
| --- | --- |
| 检查 CSV/XLSX/Parquet 时序数据、确认元数据、标准化 dataset、提取洪水场次，或处理 DEM/边界/出口/站点 Geo 输入 | `skills/hydrotune-intake/SKILL.md` |
| 建模前分析已标准化数据、事件特征、数据质量、Geo-aware readiness，或生成智能预分析报告 | `skills/hydrotune-analysis/SKILL.md` |
| 构造 `run.json` 或执行 HBV/XAJ/Tank/外部模型的前向模拟 | `skills/hydrotune-modeling/SKILL.md` |
| 参数率定、三模型比较、BMA 或优化器驱动的模型选择 | `skills/hydrotune-calibration/SKILL.md` |
| 模型运行后解释 observed-versus-simulated 差异、指标、偏差和有界假设 | `skills/hydrotune-diagnosis/SKILL.md` |
| 绘制建模前时序/事件/空间图，或建模后 observed-simulated 固定模板图 | `skills/hydrotune-visualization/SKILL.md` |
| 协调多阶段流域研究 | `skills/hydrotune/SKILL.md`，再按阶段加载所需 component skills |

## 全局确认闸门

在向任何 HydroTune CLI 传入 metadata、参数、阈值、模型设置、optimizer、routing、外部命令或文件选择前，Agent 必须先判断其来源：

- 确定性 artifact 事实：来自 `dataset.json`、`analysis.json`、`geo.json`、`result.json` 等明确字段。
- runtime 推断/推荐：来自 analysis 或 readiness 的 evidence/recommendation。
- 用户确认：用户在当前对话或明确配置中给出的决定。
- 未知：没有可靠来源。

只有“确定性 artifact 事实”和“用户确认”可以作为 confirmed CLI 输入。列名推断、常见水文惯例、最近文件名、Agent 自身判断，都只能作为向用户提问的证据。

当必需信息未知时，先停下来问，不要填方便的默认值，除非对应 component skill 明确说明这是 runtime contract 的默认行为。

追问规则：

- 每次最多问三个问题，并合并相关不确定性。
- 只有 evidence 足够时才给推荐选项，并允许用户修正。
- 每个问题必须说明：需要确认什么、为什么科学上重要、Agent 找到了什么证据、答案会进入哪个 CLI 参数或 artifact 字段。
- 不重复询问用户已经明确确认的信息。
- 不把推断、推荐、列名或经验写成 confirmed metadata。

## 数据形态与 workflow 不变量

陌生源数据进入 Intake 前，Agent 应先自主检查表头、样例行、时间范围、缺失值、重复时间、多个文件的时间窗和候选变量角色。检查结果只是证据，不是自动选择权限。

`continuous` 表示同一条按时间连续的记录，可以由不重叠片段组成；只有用户确认后才能把目录合并为 continuous。HydroTune 对 continuous 使用 chronological warmup/calibration/validation split。

`event_collection` 表示一组独立洪水场次。必须保留 `event_id` 和事件边界；不得跨事件填补、推断连续性、传递模型状态或把事件样本池化成一条连续序列。建模、率定和诊断前必须确认 `warmup_steps`。

如果确认数据中包含 `upstream_discharge`，native model run 必须使用 Muskingum routing。`K` 和 `X` 必须是用户确认或 calibration 选出的值；不得绕过 routing。

Geo artifacts 独立于时序 dataset。只有用户有 DEM、流域边界、出口点、站点等输入，且目标涉及分布式/半分布式模型、子流域、河道汇流或空间参数时，Agent 才处理空间前处理或读取外部 GIS 成果。集总式模型或纯时序标准化不需要 Geo。

## 确定性执行与临时扩展

凡是 CLI 已覆盖的 artifact 写入、analysis、modeling、calibration、diagnosis、reporting 和 visualization 任务，都应优先使用 HydroTune CLI 与固定 artifacts。普通原始数据探索和 Geo 前处理可以由 Agent 自主完成。

如果用户需求科学上必要但当前 CLI 没有覆盖，Agent 可以写 task-local 临时代码，但必须：

- 仿照最接近的 HydroTune runtime 结构和 artifact 风格。
- 写出 `result.json` 或等价结果说明。
- 记录输入、单位、参数、随机种子、provenance 和限制。
- 明确标注该实现是当前任务的临时扩展，不是稳定 CLI feature。
- 不改变已有 artifact schema 或把临时结果伪装成官方 runtime 输出。

标准 HydroTune 图表仍应使用 `hydrotune-visualization` 固定模板，避免临时绘图破坏跨环境可比性。

## 典型工作流

最小多阶段流程：

```text
agent checks raw data
  -> clarify required metadata
  -> intake
  -> analyze
  -> clarify readiness gaps or modeling choices
  -> model and/or calibrate
  -> diagnose / report / visualize
```

常用命令示例：

```text
python scripts/hydrotune.py intake <raw-data> artifacts/dataset --time-column <confirmed> --role precipitation=<column> --role discharge=<column> --unit precipitation=mm --unit discharge=<unit>
python scripts/hydrotune.py analyze artifacts/dataset artifacts/analysis
python scripts/hydrotune.py model <run.json> artifacts/model
python scripts/hydrotune.py diagnose artifacts/dataset artifacts/model/simulation.parquet artifacts/diagnosis
```

在每个阶段切换前，检查当前 artifacts 中的 `unavailable`、readiness gaps、warning 和多个可能的下游选择。只向用户询问会影响下一步计算或解释的内容。

`calibrate` 或 `compare` 前，必须要求用户选择一个 optimizer：`de`、`pso`、`ga`、`sce` 或 `two_stage`。传入同一个选择，不得静默使用 Agent 自选 optimizer。

## 报告与可视化

报告必须先生成 deterministic evidence，再由 Agent 基于 evidence 写叙述：

```text
python scripts/hydrotune.py report preanalysis ...
python scripts/hydrotune.py report readiness ...
python scripts/hydrotune.py report model-run ...
python scripts/hydrotune.py report comparison ...
```

报告中必须区分观测事实、runtime 证据、工程推断、建议和待确认事项。不要把 validation ranking 描述为 calibration evidence，不要把相关性或偏差直接写成因果事实。

可视化优先使用固定模板：

```text
python scripts/hydrotune.py visualize dataset ...
python scripts/hydrotune.py visualize events ...
python scripts/hydrotune.py visualize geo ...
```

模型运行后的 observed-simulated 图继续按 `hydrotune-visualization` skill 指南选择固定脚本。图表解释必须引用 `figure.json`、dataset、analysis、geo、simulation 或 comparison artifacts 中真实存在的信息。

## 可移植性核查

跨环境比较或移交时，应保持：

- 相同仓库版本。
- 相同依赖环境。
- 相同输入 artifacts。
- 相同用户确认元数据。
- 相同 CLI 命令。
- 相同随机种子和 optimizer 设置。

可比较的对象包括 `dataset.json`、`run.json`、`result.json`、analysis/report evidence、`figure.json` 和输出 hash。自然语言解释可以不同，但所有事实必须能追溯到同一组 deterministic artifacts。
