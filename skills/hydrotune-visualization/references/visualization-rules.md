# HydroTune 固定可视化规则

所有模板使用固定字体、DPI、布局和配色。Agent 只能选择模板和输入 artifacts，不得在运行时修改样式或临时替换绘图实现。

## 建模前模板

- `visualize dataset`：用于 Intake 后查看时序数据。continuous 显示完整时间轴和 warmup/calibration/validation split；event_collection 按事件分组展示，不表达事件之间的连续性。
- `visualize events`：用于 Analysis 后查看 `event_features.parquet` 中已有的事件特征。只绘制存在且非空的指标；unavailable 指标只写入 metadata，不画估计值。
- `visualize geo`：用于 Geo runtime 后查看 vector artifacts。绘制 basin、subbasins、stations 和可选 streams、flowpaths、snapped outlet、HRU；不读取 DEM raster，不生成 hillshade，不重跑空间处理。

## 建模后模板

- Continuous hydrographs put precipitation bars above observed/simulated flow lines and show warmup, calibration, and validation bands.
- Event plots show the full validation event and shade its non-scored warmup samples.
- Scatter plots use validation samples only and include a 1:1 line.

## 边界

Visualization 不计算水文指标，不解释模型偏差，不补齐缺失数据，不改变 artifact。缺少必要输入时返回 `error`；缺少可选空间图层时可以返回 `warning` 并绘制可用图层。
