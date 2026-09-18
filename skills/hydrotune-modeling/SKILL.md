---
name: hydrotune-modeling
description: 指导 Agent 基于 HydroTune 标准 dataset 和 run contract，逐场独立运行 HBV、XAJ、Tank 三个集总式降雨径流模型；用于前向模拟，不用于参数率定。
---

# HydroTune Modeling

本 Skill 用于读取 HydroTune dataset artifacts，构造 `hydrotune.run.v1`，并调用 `scripts/hydrotune` 中的原生 HBV、XAJ、Tank 模型完成前向模拟。分场次洪水必须按 `event_id` 独立运行和重置状态，结果写为后续率定、比较、可视化和诊断可复用的 `simulation.parquet` 与 `result.json`。

## 何时使用

使用本 Skill：

- 已有 HydroTune `dataset.json` 和 `dataset.parquet`，需要运行 HBV、XAJ 或 Tank。
- 数据是 `event_collection`，需要保持洪水场次独立并生成带 `event_id` 的模拟结果。
- 已有一组确认参数，或者用户明确要求用模型默认参数做未率定的基线运行。
- 需要为同一数据集分别生成三个集总式模型的前向模拟结果。

不使用本 Skill 搜索参数、选择最优模型、计算率定目标或解释模拟误差。参数率定和三模型比较切换到 `hydrotune-calibration`，误差解释切换到 `hydrotune-diagnosis`。外部命令模型只在用户明确提供并确认命令契约时使用，细则见 `references/custom-command-adapter.md`。

## 标准流程

1. 检查 dataset artifacts
   - 读取 `dataset.json`、`dataset.parquet` 和最近的 `result.json`。
   - 确认 `schema_version`、`status`、`modeling_readiness`、`series_mode`、`timestep`、`variables`、`basin` 和 `splits`。
   - Dataset 为 `error`，缺少降水或实测流量角色，或 `modeling_readiness.modeling_status == "not_ready"` 时停止。

2. 检查分场次结构
   - `event_collection` 必须包含 `event_id`；核对每场行数、时间顺序和时间步。
   - 不得跨场次补值、拼接连续状态或传递模型状态。
   - `splits.warmup_steps` 必须是已经确认的非负整数；为 `null` 时停止并向用户确认。
   - Warmup 行保留在前向模拟输出中，只在率定或验证评分时排除。

3. 确认模型和参数
   - 模型名只能是 `hbv`、`xaj` 或 `tank`。
   - 已有确认参数时写入 `parameters`。
   - 用户明确要求默认参数基线时可使用空对象 `{}`，但必须把结果标记为“未率定基线”，不得当作率定成果。
   - 不得把流域面积、`event_id`、实测流量或上游路由参数写入 `parameters`。
   - 降水、PET 和温度列名通常由 dataset role 自动映射；`dt_hours` 由 `dataset.json.timestep` 自动传入模型。

4. 为每个模型写 run contract

```json
{
  "schema_version": "hydrotune.run.v1",
  "model": {"kind": "native", "name": "hbv"},
  "input_dataset": "<dataset-directory>",
  "parameters": {}
}
```

将 `model.name` 分别改为 `hbv`、`xaj` 和 `tank`，每个模型保存独立 run 文件和输出目录。

5. 分别运行三个模型

```text
python scripts/hydrotune.py model <hbv-run.json> <output-root>/hbv
python scripts/hydrotune.py model <xaj-run.json> <output-root>/xaj
python scripts/hydrotune.py model <tank-run.json> <output-root>/tank
```

6. 检查结果
   - 每次运行后读取 `result.json`，不得只根据进程退出码判断成功。
   - `error` 时停止对应模型并解释原因；不得手工伪造或修补 `simulation.parquet`。
   - `success` 时检查 `simulation.parquet` 的列、行数、`event_id`、模型名和数值有效性。

## Runtime 边界

HydroTune Modeling runtime 负责：

- 读取 `hydrotune.run.v1` 和标准 dataset artifacts。
- 根据 dataset role 设置降水、PET 和温度列。
- 根据 dataset timestep 向原生模型传入 `dt_hours`。
- 对 `event_collection` 按 `event_id` 分组，逐场重新初始化并调用模型。
- 将模型输出的 `mm/step` 径流深按流域面积和时间步转换为 `m3/s`。
- 对已确认的 `upstream_discharge` 统一执行 Muskingum 路由并叠加。
- 写出 `simulation.parquet` 和 `result.json`。

Runtime 不负责：

- 猜测变量物理含义、单位、流域面积、warmup 长度或路由参数。
- 率定模型参数、选择最优模型或解释误差来源。
- 在模型内部重复加入上游流量。
- 把多个洪水事件拼成一条连续状态序列。
- 调用 `model_hbv.py`、`model_tank.py`、`hbv_runner.py` 或 `tank_runner.py` 等旧适配层；原生入口是 `models/hbv.py`、`models/xaj.py` 和 `models/tank.py`。

## 科学确认规则

以下信息必须来自 dataset 中已确认的 metadata 或用户明确确认：

- 降水、实测出口流量、上游流量、PET 和温度的角色与单位。
- 实测流量是天然出口流量、入库流量还是工程调度量。
- 流域面积；当实测流量单位为 `m3/s` 时，没有面积就不能可靠完成径流深到流量的统一换算。
- `event_collection` 的 `warmup_steps`。
- 模型参数；默认参数只能用于用户明确同意的未率定基线。
- 上游 Muskingum `K`、`X`、可选河段数和初始流量。

不得把列名、常见经验值、Analysis recommendation 或 Agent 自己的判断当作科学确认。

## 数据形态

`continuous` 表示同一条连续时间轴，模型状态可沿时间顺序持续更新。

`event_collection` 表示相互独立的洪水场次集合。Runtime 会按 `event_id` 分组并为每场重新调用模型。必须验证：

- 每一行都有非空 `event_id`。
- 同一场次内时间有序，且各场时间步与 dataset metadata 一致。
- 输出保留全部输入场次和原始行数。
- 不跨事件传递土壤含水量、积雪、水箱蓄水或河道汇流状态。

## 三个原生模型

三个模型都接收统一 DataFrame 和参数字典，并返回本流域 `mm/step` 径流深。真实面积换算和上游路由由共享运行层完成。

- HBV：率定参数为 `fc, beta, c, k0, l, k1, k2, kp, lp`；旧 run 中的 `uzl, perc, tt, cfmax` 仍兼容。缺少 PET 时使用内置月均 PET，缺少温度时使用模型默认值。
- XAJ：率定参数为 `B, C, WM, WUM, WLM, IM, SM, EX, K, KG, KI, CG, CI, CS, L, X, n, WUM_init, WLM_init, WDM_init, FR1, S1, Q`。`L` 和 `n` 在模型内部整数化。
- Tank：使用 `t0_*` 至 `t3_*` 参数描述四层初始蓄水、底孔/侧孔系数和孔高；旧 run 中的 `a1...a4, b1...b3, h1...h3` 仍兼容。

Tank 和 XAJ 缺少 PET 时使用零值。PET 缺失会影响蒸散和水量平衡，必须在结果说明中保留该限制。

## 上游流量与 Routing

当 dataset 含已确认的 `upstream_discharge` 时，每个 native run 必须包含顶层 `routing`：

```json
{
  "routing": {
    "method": "muskingum",
    "K": 3.0,
    "X": 0.2,
    "reaches": 1
  }
}
```

规则：

- `K > 0`，`0 <= X <= 0.5`，并满足 `dt_hours <= 2*K*(1-X)`。
- 默认使用 dataset 时间步；只有经过确认时才显式设置 `routing.dt_hours`。
- `reaches` 和 `initial_flow` 可选，但不得猜测。
- 三个模型只模拟本流域产汇流；不得在模型参数或模型代码内再次叠加上游流量。
- 缺少 routing 或稳定性检查失败时停止，不得绕过。

## 结果与质量门槛

每个成功输出目录至少包含：

- `result.json`。
- `simulation.parquet`，列为 `timestamp`、`discharge_sim`、`model`；分场次数据还必须包含 `event_id`。

声明运行完成前必须验证：

- 输出行数与输入行数一致。
- `event_collection` 的输入、输出 `event_id` 集合及各场行数一致。
- `discharge_sim` 全部为有限非负值。
- `model` 列只包含当前模型名。
- 实测流量为 `m3/s` 时，已确认流域面积并完成单位转换。
- 有上游流量时，routing 只应用一次且逐场重置。
- 三个模型使用相同 dataset，但各自拥有独立 run 文件和输出目录。

## 追问策略

- 每次最多问三个会改变运行契约或科学含义的问题。
- 问题必须说明缺口、影响以及会写入哪个 dataset/run 字段。
- 不重复询问已经存在于已确认 metadata 中的信息。
- 不为了尽快运行而猜测 warmup、模型参数、面积或 Muskingum 参数。

## 后续边界

需要模型参数搜索或三模型统一比较时切换 `hydrotune-calibration`；需要绘制分场次过程线时切换 `hydrotune-visualization`；需要解释观测与模拟差异时切换 `hydrotune-diagnosis`。
