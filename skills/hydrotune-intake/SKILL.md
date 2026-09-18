---
name: hydrotune-intake
description: 指导 Agent 检查、确认并整理流域降水、流量、气象时序和可选空间输入，按需提取洪水场次，再写出标准 HydroTune dataset artifacts；不要用于模型率定。
---

# HydroTune Intake

用本 Skill 时，Agent 负责读取原始 CSV/XLSX/Parquet、理解列含义、发现缺口并向用户确认科学元数据。HydroTune Intake runtime 用于把已确认的输入写成后续建模、率定、诊断可复用的 `dataset.json`、`dataset.parquet` 和 `result.json`；当用户明确要求并提供完整事件配置时，runtime 还可执行确定性的 Eckhardt 基流分割、quickflow 洪峰识别和场次边界提取。

## 何时使用

使用本 Skill：

- 用户提供降雨、流量、气象时序数据，并希望进入 HydroTune workflow。
- 需要把已确认的时间列、变量角色、单位、流域面积、数据形态写成 HydroTune dataset artifacts。
- 用户希望从连续流量序列中执行基流分割、洪峰识别、复峰合并、洪量筛选和场次成果整理。
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

Intake runtime 的职责限于 dataset artifact 写入、必要硬校验和已配置的确定性洪水场次提取。以下事项由 Agent 在调用 runtime 前完成：

- 检查原始数据结构、时间列候选、变量候选和缺失情况。
- 确认变量角色、单位、数据形态和必要流域元数据。
- 判断空白降雨是 0 降雨还是缺测。
- 确认自然流量、上游入流或调度出库语义。
- 确认事件定义、基流分割、峰值、边界、合并、规模门槛和前期窗口参数，并写入事件配置 JSON。
- 处理或整理 DEM、流域边界、出口点、站点、HRU 等空间输入。

Runtime 提供以下可复用能力：

- 读取已确认的表格输入。
- 校验显式 `--time-column`、`--role`、`--unit`。
- 写出 `dataset.json`、`dataset.parquet`、`result.json`。
- 为 `continuous` 写 chronological split。
- 为 `event_collection` 写事件 split，并标记 `warmup_steps` 仍需后续确认。
- 在显式 `--extract-events --event-config` 下执行 Eckhardt 基流分割、quickflow 洪峰识别、总流量初始边界、复峰合并和 quickflow 边界收紧，并写出 `event_collection`。
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
- 连续序列事件提取的事件定义、基流分割与峰值参数、规模门槛和前期窗口。

## 数据形态

`continuous` 表示同一条连续时间轴。目录输入只有在用户确认是连续分段后才可用 `--series-mode continuous` 合并；runtime 会拒绝重复时间戳。

`event_collection` 表示独立洪水场次集合。每个文件会成为一个 `event_id`；后续步骤不得跨事件填补、推断连续状态或传递模型状态。

## 连续序列洪水场次提取

仅在用户明确要求从连续流量、入库流量或其他已确认目标流量中提取洪水场次时进入本流程。若用户只要求年最大流量、超阈值次数或固定日期窗口，不要自动升级为完整场次提取。

洪水场次提取由 Intake runtime 的固定 `eckhardt_peak_boundary_v1` 方法执行。它不包含旧的简单流量阈值切分模式；所有影响结果的参数必须由用户确认后写入 JSON，不得依赖源脚本示例值或 Agent 静默默认。

```text
python scripts/hydrotune.py intake <continuous-input> <dataset-output-dir> \
  --time-column <confirmed-time-column> \
  --role precipitation=<confirmed-rain-column> \
  --role discharge=<confirmed-flow-column> \
  --unit precipitation=mm \
  --unit discharge=m3/s \
  --extract-events \
  --event-config <confirmed-event-config.json>
```

事件配置必须显式包含全部字段；`alpha: null` 表示按退水段估计，`min_peak_flow` 或 `min_event_volume` 为 `null` 表示关闭对应门槛：

```json
{
  "bfi_max": 0.80,
  "alpha": null,
  "peak_quantile": 0.90,
  "prominence_factor": 0.25,
  "min_peak_distance_hours": 24.0,
  "boundary_fraction": 0.05,
  "boundary_persistence_steps": 3,
  "max_search_days": 20.0,
  "merge_gap_hours": 24.0,
  "valley_ratio_threshold": 0.60,
  "min_event_duration_hours": 1.0,
  "min_peak_flow": null,
  "min_event_volume": null,
  "warmup_steps": 72
}
```

上例只展示文件结构，其中数值必须按当前流域确认。`--extract-events` 不得与 `--series-mode event_collection` 同时使用；`--event-config` 不得脱离 `--extract-events` 单独使用。

### 开始前确认

先读取文件结构、表头、少量样例和时间范围，给出可验证的候选映射，再集中确认会实质改变结果的设置：

| 类别 | 必须确认的内容 |
|---|---|
| 数据定位 | 输入文件、工作表或表名，以及目标时间列 |
| 时间语义 | 格式、时区、时间戳代表瞬时值还是区间值 |
| 流量语义 | 用于提取的列是天然流量、入流、出流、调度流量还是水位 |
| 单位与频率 | 流量单位；分钟、小时、日或不规则时间步 |
| 事件定义 | 水文洪水、调度入库过程还是降雨径流事件 |
| 规模门槛 | 最小洪峰、总洪量或直接径流洪量、最短历时及其业务依据 |
| 前期窗口 | 起涨前保留的实际时长、用途以及是否允许相邻事件窗口重叠 |
| 数据修复 | 重复时间规则、允许插值的最大连续缺失长度和长缺口处理方式 |
| 输出 | 汇总表、逐场文件、需要保留的原始驱动列、图和文件格式 |

出现相应情况时再确认雨量站列及面雨量、入流与出流的导出范围、水位流量转换、水库调度影响、人工场次清单、重采样规则、测站迁移或评级曲线变化。每次追问仍遵守“最多三个科学问题”的总规则。

### 输入整理与时间规则

1. 将时间列显式转换为时间类型；报告无法解析的记录，不得静默丢弃。
2. 按时间升序排序；重复时间戳必须按用户确认的删除、保留、聚合或分组规则处理。
3. 将目标流量显式转换为数值，检查负值、无穷值、异常尖峰、长期恒值、传感器归零和单位变化。异常尖峰先报告位置、幅度和影响，不自动删除。
4. 统计缺失点、连续缺失段及其实际时长。事件 runtime 不执行插值；必须由 Agent 按用户确认规则在独立成果中处理短缺失并保留标记。仍有缺失、非数值或无穷流量时停止。
5. 有效流量少于 10 点、存在负流量或派生列名与输入列冲突时停止场次提取。
6. 以相邻时间差的中位数表示候选步长：

```text
dt_seconds = median(diff(time))
regularity = count(abs(diff(time) - dt_seconds) <= max(1 second, 0.01 * dt_seconds)) / count(diff(time))
```

规则度低于 `99%` 时 runtime 发出警告并按中位时间步继续固定步长计算。真实缺步、变频或大量不规则间隔应在调用前重采样或分段；不得把该 warning 当作数据已修复。

### 场次算法

除非用户明确选择其他事件定义，按以下顺序处理，不要交换“基流分割、洪峰识别、边界识别、复峰合并、主峰收紧、规模筛选”的先后关系：

```text
连续序列
  -> 数据质量和时间规则检查
  -> Eckhardt 基流分割
  -> 在 quickflow 上识别候选洪峰
  -> 在总流量上确定初始边界
  -> 合并重叠事件和相邻复峰
  -> 围绕主峰在 quickflow 上收紧边界
  -> 按历时、洪峰和洪量筛选
  -> 附加起涨前窗口
  -> 指标、过程表、完整序列和诊断图
```

1. **Eckhardt 基流分割**

   ```text
   baseflow = Eckhardt(Q, alpha, BFImax)
   quickflow = max(Q - baseflow, 0)
   quickflow_ratio = quickflow / max(Q, epsilon)
   ```

   用户有率定值或文献值时优先采用并记录来源。没有 `alpha` 时，可从相邻正流量下降段的 `Q(t) / Q(t-1)` 估计：有效下降比值少于 20 个时可用 `0.95` 作为待检查起点，否则用其 90% 分位数，并限制在 `[0.80, 0.9999]`。`BFImax=0.80` 只能作为示例起点，必须结合含水层和基流特性判断。递推结果限制为 `0 <= baseflow <= Q`，并用总流量、基流和直接径流图检查水文合理性。

2. **在直接径流上识别候选洪峰**

   ```text
   peak_height_threshold = quantile(positive_quickflow, peak_quantile)
   prominence = prominence_factor * std(quickflow)
   distance_steps = round(min_peak_distance_hours * 3600 / dt_seconds)
   ```

   峰高、prominence 和最小峰间距须同时满足。没有正直接径流时返回空事件集，不再构造边界。

3. **在总流量上确定初始边界**

   对峰前、峰后分别在 `max_search_days` 限定范围内计算局部最低流量 `baseline`：

   ```text
   boundary_threshold = baseline + boundary_fraction * (peak_flow - baseline)
   ```

   从峰值向两侧搜索，连续 `boundary_persistence_steps` 个点不高于阈值时形成边界候选；范围内无满足点时，使用该侧最低流量位置。左右基线分别计算。

4. **合并重叠事件和相邻复峰**

   重叠窗口直接合并。对于不重叠且间隔不超过 `merge_gap_hours` 的窗口，计算：

   ```text
   valley_ratio = valley_flow / min(peak_1, peak_2)
   ```

   当 `valley_ratio >= valley_ratio_threshold` 时视为退水不充分并合并；合并窗口取最早起点、最晚终点和窗口内最大总流量对应的主峰。

5. **围绕主峰收紧边界**

   合并后以主峰为中心，在 `quickflow` 上重新执行边界搜索。检查收紧后是否丢失用户希望保留的次峰、是否重新重叠，以及 `start <= peak <= end`。用户要求保留完整复峰过程时，应保留合并窗口或调整边界策略，不得机械缩成单峰。

6. **按历时和规模筛选**

   ```text
   duration_hours = (end_idx - start_idx) * dt_seconds / 3600
   total_volume = integral(Q dt)
   quickflow_volume = integral(quickflow dt)
   baseflow_volume = integral(baseflow dt)
   ```

   可按已确认的 `min_event_duration_hours`、`min_peak_flow`、`min_event_volume` 筛选；`None` 表示关闭相应门槛。必须写明洪量门槛比较总流量还是直接径流洪量。流量为 `m3/s` 时积分洪量为 `m3`；日均流量仍按实际秒数积分。

7. **附加起涨前窗口**

   ```text
   warmup_steps = round(warmup_duration_hours * 3600 / dt_seconds)
   export_start_idx = max(0, start_idx - warmup_steps)
   ```

   前期记录标记 `is_warmup=True`，`relative_step` 和 `hours_from_start` 为负，不参与洪峰、洪量和历时计算。优先向用户询问实际时长，再换算为步数；不要把 `72 steps` 直接称为 72 小时。只有真正用于模型状态恢复时才称为 warmup，并确认所需驱动变量、序列开头不足和相邻窗口重叠的处理方式。

### 参数使用规则

下列值来自附件中的算法示例，只可作为候选起点，不是跨流域通用标准：

| 参数 | 示例起点 | 调大后的主要影响 |
|---|---:|---|
| `bfi_max` | `0.80` | 通常增加基流、减少 quickflow |
| `alpha` | 自动估计 | 基流变化更平缓、退水记忆更强 |
| `peak_quantile` | `0.90` | 提高峰高门槛，减少候选峰 |
| `prominence_factor` | `0.25` | 排除更多不突出的峰 |
| `min_peak_distance_hours` | `24 h` | 相近峰更难同时保留 |
| `boundary_fraction` | `0.05` | 边界阈值升高，事件通常更短 |
| `boundary_persistence_steps` | `3` | 边界更稳定，也可能更远 |
| `max_search_days` | `20 d` | 允许更长事件 |
| `merge_gap_hours` | `24 h` | 更多相邻峰进入合并判断 |
| `valley_ratio_threshold` | `0.60` | 只有更浅谷值才合并，条件更严格 |
| `min_event_duration_hours` | `1 h` | 剔除更多短事件 |
| `min_peak_flow` | `300` | 剔除更多小洪峰；数值仅对原单位有意义 |
| `min_event_volume` | `25,000,000` | 剔除更多小洪量事件；数值仅对原单位有意义 |
| `warmup_steps` | `72 steps` | 仅扩展导出上下文，不改变事件指标 |

有防洪标准、调度规程、历史场次或专家规则时优先采用并记录来源。没有业务标准时，先报告流量和正 quickflow 分布、prominence、峰间距、初步洪峰/洪量/历时分布，再比较少量宽松、中等、严格组合。一次只调整少量相关参数，保存每组参数、候选峰数、初始事件数、合并数、筛除数和最终场次数；不得仅凭最终事件数选择“最优”参数。

### 场次成果

至少生成三类互相可核对的数据产品：

- **场次汇总表**：一行一场，至少包含 `event_id`、`warmup_start_time`、`start_time`、`peak_time`、`end_time`、`start_flow`、`peak_flow`、`end_flow`、`duration_hours`、`rise_time_hours`、`recession_time_hours`、`total_volume`、`quickflow_volume`、`baseflow_volume`、`quickflow_fraction`、`n_local_peaks`。`n_local_peaks` 只作复杂度提示，不直接解释为独立场次数。
- **场次过程表**：保留用户要求的原始驱动列，并增加 `event_id`、`baseflow`、`quickflow`、`quickflow_ratio`、`is_warmup`、`relative_step`、`hours_from_start`。前期窗口可以在相邻事件中重复；下游需要唯一时间戳时另行确认去重规则。
- **完整序列表**：保留清理后的连续序列、基流、直接径流和场次编号；事件外和仅属于前期窗口的记录不写 `event_id`。

Runtime 主输出：

```text
dataset-output-dir/
|-- dataset.json
|-- dataset.parquet
`-- result.json
```

`dataset.parquet` 按事件复制窗口并包含 `event_id`、`baseflow`、`quickflow`、`quickflow_ratio`、`is_warmup`、`relative_step` 和 `hours_from_start`。`dataset.json.events` 保存每场起点、峰值、终点、洪量和历时；`provenance.event_extraction` 保存完整配置、实际 `alpha`、时间规则度以及候选、合并、收紧、筛除和最终事件数量。

runtime 不生成 Excel、逐场 CSV 或诊断图。用户需要这些成果时，Agent 可从标准 dataset 另行导出或调用固定 Visualization 能力，但不得改变事件识别结果。

诊断图至少包括全序列总流量、基流和最终洪峰，以及代表性单场的总流量、基流、直接径流、起止点、主峰和前期窗口。绘图可以抽稀，识别和指标计算不得使用抽稀数据。

### 提取质量门槛

声明提取完成前必须验证：

- 时间可解析且严格递增；重复、缺失、长缺口、异常值和不规则步长已按确认规则处理或标记。
- `0 <= baseflow <= flow`、`quickflow >= 0`、`flow ≈ baseflow + quickflow`、`0 <= quickflow_ratio <= 1`。
- 每场满足 `start_idx <= peak_idx <= end_idx`，历时为正，主峰是窗口内最大总流量，最终事件没有未解释重叠或跨越未处理长缺口。
- 前期窗口不参与事件指标；总洪量近似等于直接径流洪量与基流洪量之和，所有洪量非负且单位正确，`quickflow_fraction` 位于 `[0, 1]`。
- 汇总表、过程表、完整序列和逐场文件的 `event_id` 一致，最终场次数一致，计划输出均可读取且未发生文件覆盖。
- 没有事件时依次检查列映射、quickflow、`BFImax/alpha`、峰高与 prominence、规模门槛和单位；不要只放宽单个阈值后直接接受结果。
- 事件过多时检查噪声、峰值门槛、峰间距、规模门槛和合并规则；误拆或误并时检查峰间间隔、谷峰比、边界参数与主峰收紧；窗口或洪量异常时检查步长、积分方法、缺口、单位和事件完整性。

只有输入映射与单位、事件定义、关键参数、前期窗口实际时长、数据质量处理、数值检查和标准 artifacts 都已记录并通过检查，才能声明场次提取完成。runtime 会直接写出 `series_mode=event_collection`，并把配置中的 `warmup_steps` 标为 `confirmed_from_event_config`；评分优先依据逐行 `is_warmup` 排除前期窗口，不同事件之间不得传递模型状态。

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
