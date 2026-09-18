---
name: hydrotune-visualization
description: 使用固定 HydroTune 模板绘制建模前时序/事件/空间图，以及建模后 observed-simulated 诊断图。不要临时生成绘图代码或改变模板样式。
---

# HydroTune Visualization

本 Skill 指导 Agent 选择 HydroTune 固定可视化模板。runtime 负责读取 canonical artifacts、绘制确定性 PNG，并写出 `figure.json` 和 `result.json`；Agent 负责选择合适模板、解释图表对应的 evidence，不得在任务中临时写新绘图代码或改样式。

## 何时使用

建模前使用：

- Intake 后查看 `dataset.json` / `dataset.parquet` 的时序结构。
- Analysis 后查看事件特征概览。
- 查看现成 Geo artifacts 中的流域边界、子流域、站点和可选河网。

建模后使用：

- 模型运行后查看 observed-simulated hydrograph。
- event_collection 验证事件逐场次图。
- 验证样本 observed-simulated scatter。

Visualization 不做 Intake、Analysis、Geo preprocessing、Modeling、Calibration 或 Diagnosis。缺少上游 artifact 时必须停止并解释 `result.json` 中的错误。

## 建模前固定模板

时序数据图：

```text
python scripts/hydrotune.py visualize dataset <dataset-dir> <output-dir> [--variables role-or-column ...]
```

- `continuous`：绘制完整时间轴，并标注 warmup/calibration/validation split。
- `event_collection`：按事件分组展示，不把事件拼成连续序列。
- `--variables` 可传 role 或 column；不存在时 runtime 返回 `error`。

事件特征图：

```text
python scripts/hydrotune.py visualize events <dataset-dir> <analysis-dir> <output-dir>
```

- 必须先运行 `hydrotune analyze`。
- 读取 `event_features.parquet` 和 `preanalysis.json`。
- 只绘制 evidence 中存在的事件指标；unavailable 指标不得伪造。

空间概览图：

```text
python scripts/hydrotune.py visualize geo <geo-output-dir> <output-dir>
```

- 用于现成 Geo artifacts 的流域/子流域/站点/河网/汇流路径/snapped outlet/HRU 查看。
- 只读取 `geo.json`、`basin.geojson`、`subbasins.geojson`、`stations.geojson` 和可选 `streams.geojson`、`flowpaths.geojson`、`snapped_outlet.geojson`、`hru.geojson`。
- 不读取 DEM raster 做 hillshade，不重跑 WhiteboxTools，不生成或修改 Geo artifacts。

## 建模后固定模板

保留现有 skill-level scripts：

- Continuous records：调用 `scripts/plot_hydrograph.py` 绘制完整 observed-simulated hydrograph。
- Event collections：调用 `scripts/plot_event_panel.py` 为验证事件逐一绘图。
- Validation diagnostics：调用 `scripts/plot_obs_sim_scatter.py` 绘制 observed-simulated scatter。

这些脚本要求成功的 dataset 和 simulation artifacts。event_collection 建模后图表必须有已确认的 warmup metadata；runtime 会拒绝未确认 warmup 的输入。

## Result handling

每次可视化后读取 `result.json`：

- `success`：可以展示 PNG，并引用 `figure.json` 说明输入来源。
- `warning`：可以展示图，但必须说明被跳过或缺失的图层/指标。
- `error`：不要展示或解释不存在的图；先解决缺失 artifact、变量或 metadata。

`figure.json` 是图表 provenance 的依据。解释图表时只引用 dataset、analysis、geo、simulation 或 comparison artifacts 中真实存在的信息。

## 模板选择规则

读取 [visualization-rules.md](references/visualization-rules.md) 来决定使用哪个固定模板。Agent 可以选择模板和输入 artifacts，但不得：

- 临时写绘图脚本；
- 改配色、线型、DPI 或布局；
- 将 event_collection 当作连续序列；
- 用图表替代 analysis 或 diagnosis；
- 为 unavailable 指标绘制猜测值。

如果现有模板不能表达用户需要，应说明当前固定模板不覆盖该图，并建议先扩展 visualization runtime，而不是在当前任务里临时画一张不可复现的图。
