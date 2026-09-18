# HydroTune-Skills

面向流域降雨径流研究的 Agent Skills 与确定性水文计算工具集。

HydroTune-Skills 为 AI Agent 提供从原始水文数据整理、建模前分析，到模型运行、参数率定、结果诊断和可视化的完整工作流。项目将自然语言交互与可复现计算分开：Agent 负责理解任务、检查证据和确认关键科学决策，HydroTune runtime 负责执行计算并生成标准化 artifacts。

```text
原始数据
  -> Intake
  -> Analysis
  -> Modeling / Calibration / Comparison
  -> Diagnosis / Reporting / Visualization
```

## 项目目标

- 为降雨径流研究提供可组合、可复用的 Agent Skills。
- 用固定的数据契约和命令行工具保证计算过程可复现。
- 明确区分观测事实、程序证据、Agent 推断与用户确认。
- 支持连续水文序列和相互独立的洪水场次。
- 提供 HBV、XAJ、Tank 三种集总式降雨径流模型及 Muskingum 河道汇流。

## Skills 一览

| Skill | 作用 |
| --- | --- |
| `hydrotune` | 协调多阶段流域研究，并按任务选择所需组件 |
| `hydrotune-intake` | 检查并标准化 CSV、XLSX、Parquet 水文时序数据 |
| `hydrotune-analysis` | 分析数据质量、事件特征、水文特征和建模准备度 |
| `hydrotune-modeling` | 构造运行契约并执行 HBV、XAJ、Tank 或外部模型 |
| `hydrotune-calibration` | 搜索模型参数、比较模型并生成 BMA 组合结果 |
| `hydrotune-diagnosis` | 诊断观测与模拟流量之间的偏差、时序和指标差异 |
| `hydrotune-visualization` | 生成可复现的水文过程线、事件面板和诊断图 |

每个 Skill 的详细行为、适用边界和确认规则见对应目录中的 `SKILL.md`。

## 核心能力

- 原始数据检查、字段角色确认、单位记录和标准化。
- 连续序列与独立洪水场次管理。
- 基于显式配置的 Eckhardt 基流分割、quickflow 洪峰识别和场次边界提取。
- 数据质量、事件统计和建模准备度分析。
- HBV、XAJ、Tank 前向模拟。
- DE、PSO、GA、SCE 和两阶段参数优化。
- 三模型比较、验证集排序和 Bayesian Model Averaging。
- 上游来流的 Muskingum 路由。
- NSE、KGE、RMSE、MAE、Bias 等诊断指标。
- 固定模板报告与水文可视化。
- 可选 Geo artifacts 读取与空间结果展示。

## 环境要求

- Python 3.10+
- NumPy、pandas、PyArrow、Matplotlib、SciPy
- XLSX 输入需要 `openpyxl`
- Geo 可视化可选安装 GeoPandas、Shapely、PyProj 和 Fiona

## 安装

克隆仓库并安装 runtime：

```bash
git clone git@github.com:luo34luo33-ui/HydroTune-skills.git
cd HydroTune-skills
python -m pip install -e .
```

需要读取和绘制已有 Geo artifacts 时：

```bash
python -m pip install -e ".[geo]"
```

安装后可以使用 `hydrotune` 命令，也可以直接从仓库根目录运行：

```bash
python scripts/hydrotune.py --help
```

## 快速开始

以下示例将降雨、流量和温度时序整理为标准数据集，再执行分析：

```bash
python scripts/hydrotune.py intake data/raw.csv artifacts/basin-a \
  --time-column Time \
  --role precipitation=Rain \
  --role discharge=Flow \
  --role temperature=Temp \
  --unit precipitation=mm \
  --unit discharge=m3/s \
  --unit temperature=degC \
  --basin-id basin-a \
  --basin-area-km2 582

python scripts/hydrotune.py analyze artifacts/basin-a artifacts/analysis-a
```

从连续序列提取事件集合时，必须提供包含全部已确认参数的 JSON：

```bash
python scripts/hydrotune.py intake data/raw.csv artifacts/flood-events \
  --time-column Time \
  --role precipitation=Rain \
  --role discharge=Flow \
  --unit precipitation=mm \
  --unit discharge=m3/s \
  --extract-events \
  --event-config event-config.json
```

事件配置必须显式给出 Eckhardt、洪峰、边界、复峰合并、规模筛选和 warmup 参数，完整字段见 `skills/hydrotune-intake/SKILL.md`。runtime 不提供已移除的简单流量阈值切分模式。

使用运行契约执行模型，并对模拟结果进行诊断：

```bash
python scripts/hydrotune.py model run.json artifacts/model-a

python scripts/hydrotune.py diagnose \
  artifacts/basin-a \
  artifacts/model-a/simulation.parquet \
  artifacts/diagnosis-a
```

率定单个模型或比较三个模型：

```bash
python scripts/hydrotune.py calibrate \
  artifacts/basin-a artifacts/calibration-a \
  --model hbv --optimizer sce --iterations 100 --seed 42

python scripts/hydrotune.py compare \
  artifacts/basin-a artifacts/comparison-a \
  --optimizer sce --iterations 100 --seed 42
```

生成报告与图表：

```bash
python scripts/hydrotune.py report readiness \
  --dataset artifacts/basin-a \
  --analysis artifacts/analysis-a \
  artifacts/readiness-report

python scripts/hydrotune.py visualize dataset \
  artifacts/basin-a artifacts/dataset-figure
```

## 标准 Artifact 契约

HydroTune 使用稳定的三阶段契约连接各个 Skill：

```text
dataset.parquet + dataset.json  ->  run.json  ->  result.json
```

- `dataset.parquet`：标准化后的时序数据。
- `dataset.json`：变量、单位、时间步、流域信息、数据划分和 provenance。
- `run.json`：模型、参数、输入数据、运行范围和软件上下文。
- `result.json`：每次命令执行的权威状态和输出索引。

下游步骤必须先读取 `result.json`：`success` 可以继续，`warning` 需要评估影响，`error` 必须停止当前阶段。

## Agent 使用原则

HydroTune 不会把列名猜测、常见经验或 Agent 推荐自动当成用户确认。以下信息在进入计算前应有明确来源：

- 时间列、变量角色和单位。
- 连续序列或独立洪水场次的判定。
- 洪水场次的 warmup 步数。
- 模型参数、率定优化器和随机种子。
- 上游来流及 Muskingum 参数。
- 事件提取配置和空间处理规则。

对于 `event_collection`，每场洪水必须独立初始化模型状态，不得把不同场次拼接为连续序列。若数据包含上游来流，原生模型运行必须使用 Muskingum routing。

## 项目结构

```text
HydroTune-Skills/
├── SKILL.md                 # 总入口与全局工作流规则
├── skills/                  # 各阶段 Agent Skills
├── scripts/hydrotune/       # 确定性水文 runtime
│   ├── intake.py            # dataset writer 与事件提取接线
│   └── flood_events.py      # 基流、洪峰和场次边界算法
├── scripts/hydrotune.py     # CLI 入口
├── contracts/               # dataset、run、result JSON Schema
├── references/              # 数据质量与率定参考资料
└── tests/                   # 单元测试与端到端测试
```

## 测试

在仓库根目录运行：

```bash
python -m unittest discover -s tests -v
```

测试覆盖数据契约、端到端工作流、共享模型逻辑，以及 HBV、XAJ、Tank 的核心行为。

## 当前边界

HydroTune core runtime 不直接执行 DEM 水文处理、子流域划分、河网拓扑构建或 HRU 生成。这类空间前处理应由 Agent 使用合适的 GIS 工具完成，或读取外部生成的 Geo artifacts；Analysis 和 Visualization 可以继续使用这些成果。

更完整的命令说明、模型参数和空间数据约定见 [README.zh-CN.md](README.zh-CN.md)。

## 贡献

欢迎通过 Issue 或 Pull Request 补充模型、诊断指标、报告模板、测试案例和文档。新增功能应尽量保持现有 artifact contract，并为涉及科学结论或共享行为的改动提供相应测试。
