---
name: hydrotune-intake
description: 指导 Agent 检查、确认并整理流域降水、流量、气象时序和可选空间输入，再写出标准 HydroTune dataset artifacts；不要用于模型率定。
---

# HydroTune Intake

用本 Skill 时，Agent 负责读取原始 CSV/XLSX/Parquet、理解列含义、发现缺口、向用户确认科学元数据，并在必要时自行编写临时检查代码。HydroTune Intake runtime 用于把已确认的输入写成后续建模、率定、诊断可复用的 `dataset.json`、`dataset.parquet` 和 `result.json`。

## 何时使用

使用本 Skill：

- 用户提供降雨、流量、气象时序数据，并希望进入 HydroTune workflow。
- 需要把已确认的时间列、变量角色、单位、流域面积、数据形态写成 HydroTune dataset artifacts。
- 用户明确希望从连续流量序列中按已确认阈值提取洪水场次。
- 用户提供 DEM、流域边界、出口点或站点空间位置，需要判断是否应进入分布式/半分布式建模准备。

不使用本 Skill 做 HBV/XAJ/Tank 运行、参数率定、模型比较、NSE/KGE/RMSE/MAE/PBIAS 计算或模型误差诊断。

## 标准流程

1. 自主检查原始数据
   - 读取表头、样例行、时间范围、缺失值、重复时间、多个文件的时间窗。
   - 识别候选时间列和候选水文变量，但不要把列名推断当作用户确认。
   - 判断数据更像 `continuous` 还是 `event_collection`，并向用户说明证据。

2. 确认科学元数据
   - 时间列：哪个源列代表时间，时间戳是区间起点、区间终点还是瞬时观测。
   - 变量角色：哪些列分别是 `precipitation`、`discharge`、`upstream_discharge`、`temperature`、`pet`。
   - 单位：每个用于 HydroTune 的变量必须有确认单位。
   - 数据形态：目录输入必须确认 `continuous` 或 `event_collection`。
   - 流域面积：若后续需要 `m3/s` 到径流深转换、径流系数或面积相关模型，应确认 `basin_area_km2`。

3. 写出 HydroTune dataset artifacts

```text
python scripts/hydrotune.py intake <input-or-directory> <dataset-output-dir> \
  --time-column <confirmed-time-column> \
  --role precipitation=<confirmed-rain-column> \
  --role discharge=<confirmed-flow-column> \
  --unit precipitation=mm \
  --unit discharge=m3/s \
  [--series-mode continuous|event_collection] \
  [--basin-area-km2 <confirmed-area>]
```

完成后必须读取 `result.json`。`error` 时停止并解释；`warning` 时说明 warning 对后续建模的影响；`success` 时可以进入 Analysis/Modeling/Calibration。

## Runtime 边界

Intake runtime 的职责限于 dataset artifact 写入和必要硬校验。以下事项由 Agent 在调用 runtime 前完成：

- 检查原始数据结构、时间列候选、变量候选和缺失情况。
- 确认变量角色、单位、数据形态和必要流域元数据。
- 判断空白降雨是 0 降雨还是缺测。
- 确认自然流量、上游入流或调度出库语义。
- 处理或整理 DEM、流域边界、出口点、站点、HRU 等空间输入。

Runtime 提供以下可复用能力：

- 读取已确认的表格输入。
- 校验显式 `--time-column`、`--role`、`--unit`。
- 写出 `dataset.json`、`dataset.parquet`、`result.json`。
- 为 `continuous` 写 chronological split。
- 为 `event_collection` 写事件 split，并标记 `warmup_steps` 仍需后续确认。
- 在用户确认阈值后，从连续流量序列提取事件集合。
- 为后续 modeling/calibration/diagnosis 提供稳定 `load_dataset` 和 split 选择契约。

## 科学确认规则

推断证据不是确认。不得仅凭以下内容直接写入 HydroTune role 或单位：

- 列名，例如 `rain_mm`、`flow`、`Q`。
- 常见水文惯例。
- Agent 自己的默认判断。
- 未经确认的工具建议。

必须确认的典型信息：

- 每个变量的物理含义和单位。
- `Q`、`flow`、`outflow`、`release`、`inflow` 等流量列到底是天然出口流量、上游来水还是工程调度量。
- 空白降雨是 0 降雨还是缺测；若不明确，报告中保留不确定性。
- `event_collection` 的 warmup 样本数；未确认前不得进入评分、率定或诊断。
- 连续序列事件提取的流量阈值和短间断合并步数。

## 数据形态

`continuous` 表示同一条连续时间轴。目录输入只有在用户确认是连续分段后才可用 `--series-mode continuous` 合并；runtime 会拒绝重复时间戳。

`event_collection` 表示独立洪水场次集合。每个文件会成为一个 `event_id`；后续步骤不得跨事件填补、推断连续状态或传递模型状态。

## 连续序列事件提取

只有当用户明确要求，并确认阈值和短间断合并步数后，才可调用：

```text
python scripts/hydrotune.py intake <continuous-input> <dataset-output-dir> \
  --time-column <confirmed-time-column> \
  --role precipitation=<confirmed-rain-column> \
  --role discharge=<confirmed-flow-column> \
  --unit precipitation=mm \
  --unit discharge=mm \
  --extract-events \
  --event-flow-threshold <confirmed-flow-threshold> \
  --event-merge-gap-steps <confirmed-gap-steps>
```

规则：

- 不得自动选择 `--event-flow-threshold`。
- 不得自动选择 `--event-merge-gap-steps`；它的单位是样本步数。
- `--extract-events` 不得与 `--series-mode event_collection` 同时使用。
- 若没有检测到超过阈值的事件，runtime 返回 `error`，不得继续 workflow。

## DEM 与空间前处理

只有研究目标需要分布式或半分布式模型、子流域、河道汇流、空间参数或 HRU 时，才执行空间前处理。仅制作坡度图、地形阴影图或等高线时，不触发完整 DEM 水文处理链；集总式建模没有空间离散需求时，也不要引入该流程。

空间前处理由 Agent 使用任务环境中合适的 GIS 工具完成，不依赖 HydroTune Intake runtime。可以使用 WhiteboxTools、GDAL、Rasterio、GeoPandas 或已有 GIS 成果，但必须遵守下述水文约束并记录实际工具、版本和参数。

### 开始前确认

检查并在缺少关键事实时向用户确认：

- DEM、流域边界、出口点和站点的来源、CRS、水平单位与垂向单位。
- DEM 是否完整覆盖真实流域以及边界外的必要分析范围。
- 流域边界是否为有效 `Polygon` 或 `MultiPolygon`，出口点是否代表目标控制断面。
- 站点角色是 `rain_gauge`、`hydro_station`、`outlet` 还是其他类型。
- 河网起始汇水面积、空间离散程度以及单出口或多出口的研究预期。
- 是否需要土地利用、土壤、坡度分级、HRU 组合和最小面积过滤。

不得猜测缺失 CRS。DEM 不可读取、没有有效 CRS、分辨率异常、边界无有效几何或空间覆盖不足以支持可靠拓扑时，停止相应处理并说明缺口。所有结果写入独立输出目录，不修改或覆盖原始 DEM 和用户已有成果。

### DEM 水文处理链

按以下逻辑组织处理；工具名称可以变化，水文含义和数据依赖必须保持一致：

```text
DEM + 流域边界
  -> 输入检查与米制投影
  -> 按外扩边界裁出分析 DEM
  -> 水文校正（通常为 Fill Depressions）
  -> D8 流向
  -> D8 汇流累积
  -> 按汇水面积阈值提取河网
  -> 河段编号与 Strahler 分级
  -> 河网矢量化与子流域划分
  -> 在完整分析范围构建河段拓扑
  -> 按真实流域边界筛选
  -> 计算面积、长度、坡度和上下游关系
  -> HydroBase 表、空间 artifacts 与质量检查成果
```

核心规则：

- 面积、河长和坡度必须在适合研究区的米制投影下计算；矢量数据与分析 DEM 使用同一 CRS。
- 先将真实流域边界适当外扩，在完整分析范围建立拓扑，再按真实边界筛选河段和子流域。不得先严格裁边再依据残缺线段猜测上下游关系。
- 输入 DEM 若已严格裁到真实边界，外扩操作不能恢复边界外高程。应请求覆盖更大的 DEM，或明确标记边界河段和出口判定的不可靠性。
- 水文校正方法一次采用一个明确方案。若比较不同方法，分别运行并记录参数及其对流向的影响。
- D8 流向、汇流累积、河段识别和拓扑解析必须使用一致的指针编码。使用 Whitebox 默认编码时保持 `esri_pntr=False`，不得按 ESRI D8 编码解释。
- 河网阈值使用汇水面积表达。工具需要像元数时，按 `ceil(stream_area_km2 * 1,000,000 / cell_area_m2)` 换算；像元面积从完整仿射变换计算，不把平方千米数直接作为像元阈值。
- 用户未指定河网阈值时，可依据流域尺度、DEM 分辨率和目标空间离散程度提出有依据的起始值；必须记录面积阈值、像元阈值和选择理由。

使用 WhiteboxTools 时，对应操作通常为 `FillDepressions`、`D8Pointer`、`D8FlowAccumulation`、`ExtractStreams`、`StreamLinkIdentifier`、`StrahlerStreamOrder`、`RasterStreamsToVector` 和 `Subbasins`。每一步都要确认输出存在、可读取，并与上游结果保持 CRS、仿射变换、行列数和像元网格一致。

### 河段拓扑

拓扑应基于 D8 Pointer、Stream Links 和 Flow Accumulation，并在真实边界筛选前建立：

1. 对每个 `reach_id`，在其河道像元中统计有效 `subbasin_id`，采用众数建立映射。没有有效映射时记录警告，不得静默令 `sub_id = reach_id`。
2. 将 D8 下游像元离开当前河段或流出栅格的像元作为下游端候选；存在多个候选时优先选择汇流累积最大的候选，并把不一致候选记录为拓扑异常。
3. 从下游端沿 D8 追踪。进入另一有效河段即得到 `downstream_reach_id`；短距离经过非河道像元时继续追踪；流出分析范围时记为 `0`。
4. 追踪过程设置最大步数并检测重复像元。发现循环、异常分叉或无法解释的多个直接下游时，停止最终交付并保留诊断成果。
5. 根据下游关系反向生成 `upstream_reach_ids` 和 `upstream_count`。`downstream_reach_id = 0` 表示流域出口，`upstream_count = 0` 表示源头河段。
6. 按真实边界筛选后，若原下游河段不在保留集合中，将当前河段记为出口，并根据筛选后的下游关系重新计算上游关系；不得根据裁切后线段的空间接触重新推断拓扑。

### 水文属性

- 子流域面积：按真实边界内有效像元统计 `area_km2 = cell_count * cell_area_m2 / 1,000,000`。若采用矢量精确相交法，说明它与栅格像元法的差异；用于栅格模型时优先与模型离散方式保持一致。
- 河段长度：沿 D8 栅格中心路径累计投影坐标距离，只计两端均有效的河网连接，输出 `length_m`。
- 河段坡度：输出 `elev_up_m`、`elev_down_m`、`drop_m`、`slope_m_m` 和 `slope_percent`，其中 `slope_m_m = accumulated_nonnegative_elevation_drop / length_m`。长度为零或高程无效时保留缺失并警告；不得用绝对高差掩盖逆坡。
- 若沿下游出现大量负落差，检查 D8 编码、DEM 水文校正以及 DEM 与河网栅格对齐，不要直接修饰结果。

### 子流域雨量站面积权重

当用户提供雨量站点，并要求将站点降雨分配到各子流域时，采用像元级最近站分区计算面积权重。该方法等价于在子流域栅格分辨率下统计 Thiessen 分区中各站控制的子流域面积比例，不是距离反比插值；不得将结果描述为 IDW 权重。

需要的输入包括：

- 子流域编号栅格。
- 雨量站点矢量。
- 非空且唯一的雨量站标识字段，例如 `station` 或 `station_id`。

计算前必须确认：

- 子流域栅格具有有效 CRS、仿射变换和明确 NoData，有效子流域编号为正整数。
- 雨量站图层具有 CRS，所有有效几何均为 `Point`，且至少存在一个有效站点。
- 站点已转换到子流域栅格 CRS，计算距离所用 CRS 是合适的米制投影。
- 完全重合的站点已有用户确认的合并、保留或优先级规则；不得依赖不稳定的并列最近邻结果任意分配。
- 不因站点位于总流域边界外而自动删除。边界附近的外部站点可能控制流域内部分 Thiessen 区域，候选站集合应由用户数据范围或明确筛选规则确定。

按以下流程计算：

1. 建立有效子流域像元掩膜：

```text
valid = subbasin_id > 0
valid = valid AND subbasin_id != nodata
```

2. 提取有效像元行列号，通过栅格仿射变换计算像元中心 X/Y 坐标。
3. 使用所有有效站点坐标建立最近邻空间索引；Python 实现可使用 `scipy.spatial.cKDTree`。
4. 对每个有效像元中心查询唯一最近站，并累计 `subbasin_id × station_id` 的像元数。
5. 对每个子流域和站点计算：

```text
weight(s, i) = count(s, i) / total_valid_cells(s)
```

其中 `count(s, i)` 是子流域 `s` 内分配给站点 `i` 的像元数。米制等面积栅格中，像元数比例等于面积比例。

有效像元很多时，应按栅格窗口或像元块分批生成中心坐标、执行最近邻查询并累计计数，避免一次性创建全部坐标导致内存压力。分块与一次性计算必须产生相同权重。

不得用“站点到子流域质心的最近距离”替代像元级面积统计。质心方法只能得到整块子流域的单站分配，无法表达一个子流域横跨多个站点控制区的情况。

主输出为 long format 的 `subbasin_rainfall_weights.csv`：

| 字段 | 含义 |
|---|---|
| `subbasin_id` | 子流域编号 |
| `station` | 唯一雨量站标识 |
| `weight` | 站点在该子流域中的面积权重 |

只输出 `weight > 0` 的组合，并按 `subbasin_id`、`station` 稳定排序。例如：

```csv
subbasin_id,station,weight
1,S01,0.625
1,S02,0.375
2,S02,1.000
```

如果 HydroBase 其他表使用 `sub_id`，可以把 `subbasin_id` 统一为 `sub_id`，但同一项目内必须一致并记录字段映射。可额外生成宽表用于人工检查，但宽表不能替代 long format 主输出。

对每个子流域必须执行权重检查：

```text
abs(sum(weight) - 1.0) <= tolerance
```

`tolerance` 应显式设置，例如 `1e-6`。同时验证：

- 所有权重有限且满足 `0 < weight <= 1`。
- 每个有效子流域至少有一条权重记录，输出子流域集合与目标栅格一致。
- 输出站点均存在于站点图层，不存在重复的 `subbasin_id + station` 组合。
- 每个子流域的站点像元计数总和等于该子流域有效像元数。
- 若生成宽表，每行权重和也在容差内等于 1。
- 随机抽查边界像元，确认最近站分配符合空间位置。

建议生成检查图，显示子流域边界、站点位置、像元最近站分区和站点编号，用于发现 CRS 错误、遗漏站点或异常控制区。

权重表只表示固定站网下的空间面积比例。子流域 `s` 在时刻 `t` 的面雨量为：

```text
P_subbasin(s, t) = sum(weight(s, i) * P_station(i, t))
```

某时刻部分站点缺测时，不得静默当作 0。必须按项目确认的规则选择：把该时刻子流域降雨标记为缺失；在明确允许时只对可用站权重重新归一化；或先完成站点时间序列缺测插补，再应用固定权重。权重计算方法、站点筛选范围和缺测处理规则都要写入报告。

### HydroBase 与空间 artifacts

当目标模型需要河网和子流域拓扑时，至少生成：

- 水文校正 DEM、D8 流向、汇流累积、河网、河段编号、Strahler 等级和子流域栅格。
- 河网线、真实流域内河段矢量、流域边界以及任务所需的站点空间数据。
- `subbasins.csv`、`reaches.csv`、`topology.csv`、拓扑检查表、检查报告和检查图。

`subbasins.csv` 至少包含 `sub_id`、`area_km2`、`cell_count`、`reach_count`、`reach_ids` 和 `outlet_reach_ids`。

`reaches.csv` 至少包含 `reach_id`、`sub_id`、`strahler_order`、`length_m`、`elev_up_m`、`elev_down_m`、`drop_m`、`slope_m_m`、`slope_percent`、`upstream_count`、`upstream_reach_ids`、`downstream_reach_id`、`downstream_sub_id`、`is_headwater` 和 `is_outlet`。

`topology.csv` 至少包含 `sub_id`、`reach_id`、`upstream_count`、`upstream_reach_ids`、`downstream_sub_id`、`downstream_reach_id`、`topo_level`、`is_headwater` 和 `is_outlet`。

CSV 使用 UTF-8，编号字段保持整数，出口使用 `0`，列表字段采用一种稳定且已记录的分隔符。若后续 Analysis 或 Visualization 需要空间输入，同时提供来源可解释的 `geo.json`、`basin.geojson`、`subbasins.geojson`、`stations.geojson` 或等价 GeoPackage，并记录路径、CRS、阈值、站点角色和限制。

### 质量门槛

声明空间前处理完成前，必须验证：

- 所有核心栅格的行列数、CRS、仿射变换和像元网格完全一致。
- 不存在 `reach_id == downstream_reach_id`、完整拓扑循环、未知的非零下游编号或未经解释的异常分叉。
- 每个保留河段具有有效子流域映射；拓扑排序能够覆盖全部河段。
- `area_km2 > 0`，正常河段 `length_m > 0`，坡度没有无穷值，河流等级为正整数。
- 子流域面积总和与栅格化流域面积基本一致，河段数量与 Stream Links 的有效编号数量一致。
- 出口数量符合研究区预期或已有明确解释。多个出口不得通过删除河段强制合并为一个。
- 检查图能够辨认真实边界、子流域、河段、流向、出口、`reach_id`、Strahler 等级以及异常统计。

没有提取到河网时，依次检查汇流累积、面积阈值、面积到像元数的换算、投影和 NoData；不要直接把阈值调到极小值。出现多个出口时，检查 DEM 裁边与覆盖、拓扑建立时机、河网连续性、D8 编码和平坦区处理，并保留真实多排水系统的可能性。发现循环、异常分叉或子流域映射失败时，不得宣告 HydroBase 构建成功。

## 追问策略

- 每次最多问三个会影响后续建模或 artifact 的科学问题。
- 问题必须说明证据、影响和会进入哪个 CLI 参数或 artifact 字段。
- 不重复询问已经明确确认的信息。
- 不为了运行 CLI 而猜测科学信息；宁可停止并说明缺口。

## 后续边界

Intake 完成后，如需建模前统计，切换 `hydrotune-analysis`；如需运行模型，切换 `hydrotune-modeling`；如需率定或比较，切换 `hydrotune-calibration`；如需模型误差解释，切换 `hydrotune-diagnosis`。
