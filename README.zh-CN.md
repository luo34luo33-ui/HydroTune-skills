# HydroTune-Skills

HydroTune-Skills 是一套面向流域降雨径流研究的 Agent + runtime 工作流组件。

当前边界是：

- **前处理可以 Agent 化**：原始 CSV/XLSX/Parquet 检查、列语义识别、单位确认、series mode 判断、DEM/边界/出口/站点整理，由 Agent 根据 `SKILL.md` 和任务上下文完成。
- **核心水文计算 runtime 化**：dataset artifact 写入、建模前分析、HBV/Tank/XAJ 运行、Muskingum 路由、参数率定、模型比较、BMA、诊断指标、固定图表，优先使用 CLI。

```text
Agent checks and confirms raw inputs
  -> hydrotune intake writes dataset artifacts
  -> hydrotune analyze/model/calibrate/compare/diagnose/report/visualize
```

## 当前完成度

- 已保留核心 runtime：Analysis、HBV/Tank/XAJ 原生建模、Muskingum routing、Calibration、Comparison/BMA、Diagnosis、Reporting、Visualization。
- Intake 已瘦身：不再提供正式 `inspect` 契约，不再自动推断列角色，不再处理 Geo。它只把 Agent 已确认的信息写成 `dataset.json`、`dataset.parquet`、`result.json`。
- Geo 处理已移出核心 runtime：DEM 水文处理、子流域划分、河段拓扑、HRU 生成和子流域雨量站面积权重应由 Agent 使用合适工具或外部 GIS 成果完成。Analysis/Visualization 仍可读取现成 `geo.json` 和 GeoJSON artifacts。
- 三个原生模型统一返回本流域径流深 `mm/step`；运行层负责时间步传递、面积换算、分场次状态重置和上游 Muskingum 路由。
- 已冻结核心 contracts：`dataset.parquet + dataset.json`、`run.json`、`result.json`。

## 安装

运行环境：Python 3.10+。

```powershell
python -m pip install -e .
```

XLSX 输入需要 `openpyxl`。若要绘制现成 Geo artifacts：

```powershell
python -m pip install -e ".[geo]"
```

## 快速开始

所有命令从仓库根目录执行。

```powershell
python scripts/hydrotune.py intake data/raw.csv artifacts/basin-a `
  --time-column Time `
  --role precipitation=Rain `
  --role discharge=Flow `
  --role temperature=Temp `
  --unit precipitation=mm `
  --unit discharge=m3/s `
  --unit temperature=degC `
  --basin-id basin-a `
  --basin-area-km2 582

python scripts/hydrotune.py analyze artifacts/basin-a artifacts/analysis-a
python scripts/hydrotune.py model run.json artifacts/model-a
python scripts/hydrotune.py diagnose artifacts/basin-a artifacts/model-a/simulation.parquet artifacts/diagnosis-a
python scripts/hydrotune.py calibrate artifacts/basin-a artifacts/calibration-a --model hbv --optimizer sce --iterations 100 --seed 42
python scripts/hydrotune.py compare artifacts/basin-a artifacts/comparison --optimizer sce --iterations 100 --seed 42
python scripts/hydrotune.py report readiness --dataset artifacts/basin-a --analysis artifacts/analysis-a artifacts/readiness-report
python scripts/hydrotune.py visualize dataset artifacts/basin-a artifacts/dataset-figure
```

目录输入如果是一组独立洪水场次，需要显式确认：

```powershell
python scripts/hydrotune.py intake data/events artifacts/events `
  --time-column Time `
  --series-mode event_collection `
  --role precipitation=Rain `
  --role discharge=Flow `
  --unit precipitation=mm `
  --unit discharge=mm
```

分场次 Intake 会把每个文件名写成 `event_id`，并在 `dataset.json` 中生成按场次开始时间划分的率定/验证集合。`splits.warmup_steps` 初始为 `null`；必须根据场次截取方式和模型初始状态假设确认非负整数后，才能运行、率定或诊断：

```json
{
  "splits": {
    "warmup_steps": 3,
    "warmup_status": "confirmed"
  }
}
```

三个模型会按 `event_id` 逐场重新初始化，禁止把不同洪水场次拼接成连续状态。前向模拟保留所有时段，warmup 行只在率定和验证评分时排除。

从连续序列提取洪水场次时，阈值和短间断步数必须来自用户确认：

```powershell
python scripts/hydrotune.py intake data/raw.csv artifacts/flood-events `
  --time-column Time `
  --role precipitation=Rain `
  --role discharge=Flow `
  --unit precipitation=mm `
  --unit discharge=mm `
  --extract-events `
  --event-flow-threshold 3 `
  --event-merge-gap-steps 1
```

## 三个原生集总式模型

HBV、XAJ 和 Tank 共用 `hydrotune.run.v1`。数据列通常由 `dataset.json.variables` 的角色映射自动传入，时间步由 `dataset.json.timestep` 转换为 `dt_hours`：

```json
{
  "schema_version": "hydrotune.run.v1",
  "model": {"kind": "native", "name": "hbv"},
  "input_dataset": "artifacts/events",
  "parameters": {}
}
```

将 `model.name` 分别设为 `hbv`、`xaj`、`tank`，并写入独立输出目录：

```powershell
python scripts/hydrotune.py model runs/hbv.json artifacts/models/hbv
python scripts/hydrotune.py model runs/xaj.json artifacts/models/xaj
python scripts/hydrotune.py model runs/tank.json artifacts/models/tank
```

模型参数体系：

- **HBV**：`fc, beta, c, k0, l, k1, k2, kp, lp`；保留 `uzl, perc, tt, cfmax` 旧参数兼容。缺少 PET 时使用内置月均 PET。
- **XAJ**：三层蒸散、蓄满产流、三水源划分和多级河道汇流，参数包括 `B, C, WM, WUM, WLM, IM, SM, EX, K, KG, KI, CG, CI, CS, L, X, n` 及初始状态参数。
- **Tank**：完整四层水箱，使用 `t0_* ... t3_*` 描述初始蓄水、底孔/侧孔系数和孔高；保留 `a1...a4, b1...b3, h1...h3` 旧参数兼容。

HBV 和 Tank 的日尺度系数会按数据时间步换算；XAJ 的 `L` 和 `n` 在模型内部整数化。空 `parameters` 只适合用户明确要求的未率定基线，不能当作率定成果。

每次运行都应读取 `result.json`。成功时 `simulation.parquet` 至少包含 `timestamp, discharge_sim, model`；分场次数据还包含 `event_id`。应检查输入输出行数、场次集合和各场行数一致，且模拟值全部有限非负。

## Geo artifacts

HydroTune core runtime 不再生成 DEM/HRU artifacts。若研究需要空间输入，Agent 应检查或生成外部 artifacts，并记录来源、CRS、出口含义、站点角色、阈值和限制。

Analysis 和 Visualization 可以读取现成目录：

```powershell
python scripts/hydrotune.py analyze artifacts/basin-a artifacts/analysis-a --geo artifacts/geo-a
python scripts/hydrotune.py visualize geo artifacts/geo-a artifacts/geo-figure-a
```

最小 Geo 目录通常包含：

- `geo.json`
- `basin.geojson`
- `subbasins.geojson`
- `stations.geojson`
- `parameters.csv`
- 可选：`streams.geojson`、`flowpaths.geojson`、`snapped_outlet.geojson`、`hru.geojson`

需要半分布式或分布式建模时，Agent 可进一步生成 HydroBase：

- `subbasins.csv`：子流域面积、像元数和关联河段。
- `reaches.csv`：河段长度、坡度、等级和上下游属性。
- `topology.csv`：稳定的河段/子流域拓扑关系。
- `subbasin_rainfall_weights.csv`：可选的子流域—雨量站面积权重。

雨量站权重采用子流域栅格上的像元级最近站分区，相当于栅格尺度 Thiessen 面积比例，不是 IDW，也不能用“子流域质心最近站”替代。主表使用 long format：

```csv
subbasin_id,station,weight
1,S01,0.625
1,S02,0.375
2,S02,1.000
```

雨量站与子流域栅格必须使用一致的米制 CRS；站点标识必须唯一。每个有效子流域的权重和应满足 `abs(sum(weight) - 1) <= 1e-6`。部分站点时序缺测不得静默按 0 处理，应按已确认规则标记缺失、重新归一化或先插补。

## 项目结构

```text
HydroTune-Skills/
├─ skills/                         # Agent 指令层：判断、追问、调用顺序
├─ scripts/hydrotune.py            # CLI 入口
├─ scripts/hydrotune/              # 核心水文 runtime
│  ├─ intake.py                    # 薄 dataset artifact writer
│  ├─ analysis.py                  # 建模前 evidence
│  ├─ modeling.py                  # 模型调度、单位换算、routing
│  ├─ calibration.py               # 参数率定
│  ├─ comparison.py                # 三模型比较和 BMA
│  ├─ diagnosis.py                 # observed-simulated 指标与证据
│  └─ models/                      # HBV、XAJ、Tank 与共享 forcing/time-step 工具
├─ contracts/                       # JSON Schema
└─ tests/                           # e2e 测试
```

## 核心约束

- 不得把列名推断、常见经验或 Agent 判断写成用户确认。
- 未确认的单位、流量语义、series mode、event warmup、模型参数和 routing 参数必须先问。
- `event_collection` 必须保持事件独立，不得拼成连续序列。
- `event_collection` 的 `warmup_steps` 必须确认；不同场次之间不得传递土壤含水、积雪、水箱蓄水或河道状态。
- `upstream_discharge` 存在时，native model 必须使用 Muskingum routing；率定会把 `routing.K` 和 `routing.X` 纳入搜索空间。
- 模型本体只返回本流域 `mm/step`；真实面积换算和上游流量叠加只能在共享运行层执行一次。
- 子流域雨量站权重必须基于有效像元面积统计，并通过逐子流域权重和检查。
- 所有 CLI 步骤都必须读取 `result.json` 后再继续。
