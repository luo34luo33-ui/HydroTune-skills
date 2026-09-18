"""HydroTune 数据预分析运行时。

本模块负责在建模前检查已经由 Intake 生成的 HydroTune 数据集，并把结果
整理成可复现、可供 Agent/LLM 解读的 evidence artifacts。

公开能力：

- analyze dataset：分析时序数据质量、时间覆盖、事件特征和建模就绪性。
- analyze optional Geo artifacts：显式提供 Geo 目录时，检查空间输入就绪性。
- load analysis output：读取已经生成的 analysis artifacts。

确定性约束：相同 dataset、相同可选 Geo artifacts 和相同 policy，会得到相同
的预分析结果。

本模块不运行水文模型，不率定参数，不计算模型表现指标，不解释模拟误差原因。
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .common import finish, result, write_json
from .intake import load_dataset


# 预分析产物版本和文件名，保持当前报告 runtime 可继续读取。
PREANALYSIS_VERSION = "hydrotune.preanalysis.v1"
ANALYSIS_VERSION = "hydrotune.analysis.v1"

ANALYSIS_FILE = "analysis.json"
PREANALYSIS_FILE = "preanalysis.json"
EVENT_FEATURES_FILE = "event_features.parquet"

# 数据质量 policy：当前离群值规则沿用原 runtime 的 median/MAD 阈值。
OUTLIER_MAD_MULTIPLIER = 3.5
GAP_INTERVAL_MULTIPLIER = 1.5

# 只有体积单位明确为流量率时，才计算体积和径流系数。
DISCHARGE_VOLUME_UNITS = {"m3/s", "m^3/s"}

# Geo analysis 只检查 Geo runtime 已输出的 artifacts，不重新进行空间处理。
GEO_MANIFEST_FILE = "geo.json"
GEO_REQUIRED_ARTIFACTS = (
    "basin.geojson",
    "subbasins.geojson",
    "stations.geojson",
    "parameters.csv",
)
GEO_OPTIONAL_ARTIFACTS = (
    "streams.geojson",
    "flowpaths.geojson",
    "snapped_outlet.geojson",
    "precipitation_zones.geojson",
    "topology.json",
    "processed_dem.tif",
    "slope.tif",
    "aspect.tif",
    "flow_direction.tif",
    "flow_accumulation.tif",
    "streams.tif",
    "hru.json",
    "hru.geojson",
    "hru_parameters.csv",
    "hru_summary.csv",
)

__all__ = [
    "analyze_dataset",
    "cmd_analyze",
    "load_analysis",
]


# ---------------------------------------------------------------------------
# 内部确定性操作
# ---------------------------------------------------------------------------


def _role_variables(meta: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """把 dataset.json 的变量清单按 hydrologic role 索引。"""
    return {variable["role"]: variable for variable in meta.get("variables", [])}


def _expected_timestep_seconds(meta: dict[str, Any]) -> float | None:
    """把 dataset.json 中的 timestep 转为秒数；无法解析时返回 None。"""
    try:
        seconds = pd.Timedelta(meta.get("timestep") or "0s").total_seconds()
    except Exception:
        return None
    return float(seconds) if seconds > 0 else None


def _time_diffs_seconds(frame: pd.DataFrame) -> pd.Series:
    """返回按时间排序后的相邻时间差秒数。"""
    times = pd.to_datetime(frame.timestamp).sort_values()
    return times.diff().dropna().dt.total_seconds()


def _quality(frame: pd.DataFrame, meta: dict[str, Any]) -> dict[str, Any]:
    """计算时间戳和变量级基础质量统计。"""
    times = pd.to_datetime(frame.timestamp)
    expected = _expected_timestep_seconds(meta)
    diffs = _time_diffs_seconds(frame)
    variables: dict[str, dict[str, Any]] = {}

    for variable in meta.get("variables", []):
        column = variable["column"]
        values = pd.to_numeric(frame[column], errors="coerce")
        median = values.median()
        mad = (values - median).abs().median()
        outlier_count = 0
        if pd.notna(mad) and mad > 0:
            outlier_count = int(
                ((values - median).abs() > OUTLIER_MAD_MULTIPLIER * mad).sum()
            )

        variables[variable["role"]] = {
            "column": column,
            "unit": variable.get("unit"),
            "samples": int(len(values)),
            "missing_fraction": float(values.isna().mean()),
            "outlier_count": outlier_count,
        }

    return {
        "duplicate_timestamps": int(times.duplicated().sum()),
        "irregular_or_gap_intervals": (
            int((diffs > expected * GAP_INTERVAL_MULTIPLIER).sum())
            if expected
            else 0
        ),
        "expected_timestep_seconds": expected,
        "variables": variables,
    }


def _temporal_coverage(frame: pd.DataFrame, meta: dict[str, Any]) -> dict[str, Any]:
    """汇总时间覆盖范围、实际间隔和最长缺口。"""
    times = pd.to_datetime(frame.timestamp)
    diffs = _time_diffs_seconds(frame)
    expected = _expected_timestep_seconds(meta)
    gap_threshold = expected * GAP_INTERVAL_MULTIPLIER if expected else None
    gap_diffs = diffs[diffs > gap_threshold] if gap_threshold else pd.Series(dtype=float)

    return {
        "start": times.min().isoformat() if times.notna().any() else None,
        "end": times.max().isoformat() if times.notna().any() else None,
        "samples": int(len(frame)),
        "expected_timestep_seconds": expected,
        "observed_interval_count": int(len(diffs)),
        "irregular_or_gap_intervals": int(len(gap_diffs)),
        "longest_gap_seconds": float(gap_diffs.max()) if not gap_diffs.empty else None,
    }


def _event_groups(
    frame: pd.DataFrame,
    meta: dict[str, Any],
    precipitation_column: str | None,
) -> list[tuple[str, pd.DataFrame]]:
    """按数据形态选择事件分组：事件集合用 event_id，连续序列用降雨片段。"""
    if meta.get("series_mode") == "event_collection":
        return [
            (str(event_id), group.sort_values("timestamp"))
            for event_id, group in frame.groupby("event_id", sort=False)
        ]

    if precipitation_column is None:
        return []

    rain = pd.to_numeric(frame[precipitation_column], errors="coerce").fillna(0)
    raining = rain.gt(0)
    labels = (raining != raining.shift()).cumsum()
    return [
        (f"event-{int(label)}", group.sort_values("timestamp"))
        for label, group in frame[raining].groupby(labels[raining])
    ]


def _empty_event_features() -> pd.DataFrame:
    """返回稳定列结构的空事件特征表。"""
    return pd.DataFrame(
        columns=[
            "event_id",
            "start",
            "end",
            "samples",
            "duration_seconds",
            "precipitation_total",
            "local_precipitation_total",
            "local_precipitation_missing_fraction",
            "discharge_peak",
            "peak_time",
            "upstream_discharge_peak",
            "event_type",
            "classification_confidence",
            "flow_volume_m3",
            "runoff_coefficient",
        ]
    )


def _event_features(
    frame: pd.DataFrame,
    meta: dict[str, Any],
    roles: dict[str, dict[str, Any]],
) -> pd.DataFrame:
    """为每个事件或降雨片段计算保守的可验证水文特征。"""
    precipitation = roles.get("precipitation")
    discharge = roles.get("discharge")
    upstream_discharge = roles.get("upstream_discharge")
    timestep_seconds = _expected_timestep_seconds(meta)
    area_km2 = meta.get("basin", {}).get("area_km2")
    rows: list[dict[str, Any]] = []

    precipitation_column = precipitation["column"] if precipitation else None
    for event_id, group in _event_groups(frame, meta, precipitation_column):
        rain = (
            pd.to_numeric(group[precipitation["column"]], errors="coerce")
            if precipitation
            else pd.Series(dtype=float)
        )
        flow = (
            pd.to_numeric(group[discharge["column"]], errors="coerce")
            if discharge
            else pd.Series(dtype=float)
        )
        upstream = (
            pd.to_numeric(group[upstream_discharge["column"]], errors="coerce")
            if upstream_discharge
            else pd.Series(dtype=float)
        )
        peak_index = flow.idxmax() if not flow.empty and flow.notna().any() else None
        flow_unit = (discharge or {}).get("unit", "").lower().replace("³", "3")
        volume = None
        if discharge and flow_unit in DISCHARGE_VOLUME_UNITS and timestep_seconds:
            volume = float(flow.fillna(0).sum() * timestep_seconds)

        runoff_coefficient = None
        if volume is not None and area_km2 and precipitation and rain.notna().any():
            precipitation_total = float(rain.sum())
            if precipitation_total > 0:
                rainfall_volume = precipitation_total / 1000.0 * float(area_km2) * 1e6
                runoff_coefficient = volume / rainfall_volume
        precipitation_total = float(rain.sum(skipna=True)) if precipitation else None
        precipitation_missing_fraction = float(rain.isna().mean()) if precipitation and len(rain) else None
        upstream_peak = float(upstream.max()) if upstream_discharge and upstream.notna().any() else None
        if precipitation and precipitation_total and precipitation_total > 0:
            event_type = "rainfall_flood"
            confidence = "medium" if precipitation_missing_fraction else "high"
        elif upstream_discharge and upstream_peak is not None and upstream_peak > 0:
            event_type = "upstream_inflow_event"
            confidence = "medium"
        elif discharge:
            event_type = "operation_or_unknown_event"
            confidence = "low"
        else:
            event_type = "unclassified"
            confidence = "none"

        rows.append(
            {
                "event_id": event_id,
                "start": group.timestamp.min().isoformat(),
                "end": group.timestamp.max().isoformat(),
                "samples": int(len(group)),
                "duration_seconds": float(
                    (group.timestamp.max() - group.timestamp.min()).total_seconds()
                ),
                "precipitation_total": precipitation_total,
                "local_precipitation_total": precipitation_total,
                "local_precipitation_missing_fraction": precipitation_missing_fraction,
                "discharge_peak": (
                    float(flow.max()) if discharge and flow.notna().any() else None
                ),
                "peak_time": (
                    group.loc[peak_index, "timestamp"].isoformat()
                    if peak_index is not None
                    else None
                ),
                "upstream_discharge_peak": upstream_peak,
                "event_type": event_type,
                "classification_confidence": confidence,
                "flow_volume_m3": volume,
                "runoff_coefficient": runoff_coefficient,
            }
        )

    if not rows:
        return _empty_event_features()
    return pd.DataFrame(rows)


def _event_statistics(features: pd.DataFrame) -> dict[str, Any]:
    """把逐事件特征压缩成给报告使用的统计摘要。"""
    if features.empty:
        return {
            "count": 0,
            "peak_max": None,
            "duration_seconds_min": None,
            "duration_seconds_max": None,
            "precipitation_total_min": None,
            "precipitation_total_max": None,
            "discharge_peak_min": None,
            "discharge_peak_max": None,
            "peak_time_available": False,
            "event_type_counts": {},
            "events_without_local_precipitation": 0,
        }

    event_type_counts = features["event_type"].fillna("unclassified").value_counts().to_dict() if "event_type" in features else {}
    without_local_precipitation = 0
    if "local_precipitation_total" in features:
        without_local_precipitation = int(features["local_precipitation_total"].fillna(0).le(0).sum())
    return {
        "count": int(len(features)),
        "peak_max": (
            float(features.discharge_peak.max())
            if features.discharge_peak.notna().any()
            else None
        ),
        "duration_seconds_min": (
            float(features.duration_seconds.min())
            if features.duration_seconds.notna().any()
            else None
        ),
        "duration_seconds_max": (
            float(features.duration_seconds.max())
            if features.duration_seconds.notna().any()
            else None
        ),
        "precipitation_total_min": (
            float(features.precipitation_total.min())
            if features.precipitation_total.notna().any()
            else None
        ),
        "precipitation_total_max": (
            float(features.precipitation_total.max())
            if features.precipitation_total.notna().any()
            else None
        ),
        "discharge_peak_min": (
            float(features.discharge_peak.min())
            if features.discharge_peak.notna().any()
            else None
        ),
        "discharge_peak_max": (
            float(features.discharge_peak.max())
            if features.discharge_peak.notna().any()
            else None
        ),
        "peak_time_available": bool(features.peak_time.notna().any()),
        "event_type_counts": {str(key): int(value) for key, value in event_type_counts.items()},
        "events_without_local_precipitation": without_local_precipitation,
    }


def _water_balance(
    features: pd.DataFrame,
    meta: dict[str, Any],
    roles: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """汇总径流体积和径流系数；条件不足时只报告 unavailable。"""
    unavailable: list[str] = []
    if "precipitation" not in roles:
        unavailable.append("water balance unavailable: precipitation variable missing")
    if "discharge" not in roles:
        unavailable.append("water balance unavailable: discharge variable missing")
    elif roles["discharge"].get("unit", "").lower().replace("³", "3") not in DISCHARGE_VOLUME_UNITS:
        unavailable.append("flow volume unavailable: discharge unit is not m3/s")
    if not meta.get("basin", {}).get("area_km2"):
        unavailable.append("runoff coefficient unavailable: basin area missing")
    if not _expected_timestep_seconds(meta):
        unavailable.append("flow volume unavailable: timestep unresolved")

    return {
        "flow_volume_m3_total": (
            float(features.flow_volume_m3.sum())
            if "flow_volume_m3" in features and features.flow_volume_m3.notna().any()
            else None
        ),
        "runoff_coefficient_min": (
            float(features.runoff_coefficient.min())
            if "runoff_coefficient" in features and features.runoff_coefficient.notna().any()
            else None
        ),
        "runoff_coefficient_max": (
            float(features.runoff_coefficient.max())
            if "runoff_coefficient" in features and features.runoff_coefficient.notna().any()
            else None
        ),
        "runoff_coefficient_mean": (
            float(features.runoff_coefficient.mean())
            if "runoff_coefficient" in features and features.runoff_coefficient.notna().any()
            else None
        ),
        "unavailable": unavailable,
    }


def _unavailable_items(
    meta: dict[str, Any],
    roles: dict[str, dict[str, Any]],
    water_balance: dict[str, Any],
) -> list[str]:
    """汇总不能完成的预分析项目，明确说明原因。"""
    unavailable: list[str] = []
    if "precipitation" not in roles:
        unavailable.append("event precipitation totals unavailable: precipitation variable missing")
    if "discharge" not in roles:
        unavailable.append("flow features unavailable: discharge variable missing")
    if not meta.get("basin", {}).get("area_km2"):
        unavailable.append("runoff coefficient unavailable: basin area missing")
    if not meta.get("timestep"):
        unavailable.append("flow volume unavailable: timestep unresolved")
    if "pet" not in roles:
        unavailable.append("PET unavailable: geodata enrichment required before PET-dependent models")
    unavailable.extend(water_balance["unavailable"])
    return list(dict.fromkeys(unavailable))


def _variable_readiness(quality: dict[str, Any]) -> list[dict[str, Any]]:
    """为每个变量生成建模前可读的 readiness 状态。"""
    rows = []
    for role, item in quality["variables"].items():
        blocking = item["missing_fraction"] >= 1.0
        warning = item["missing_fraction"] > 0 or item["outlier_count"] > 0
        rows.append(
            {
                "role": role,
                "column": item["column"],
                "unit": item.get("unit"),
                "status": "not_ready" if blocking else "warning" if warning else "ready",
                "missing_fraction": item["missing_fraction"],
                "outlier_count": item["outlier_count"],
            }
        )
    return rows


def _modeling_readiness(
    meta: dict[str, Any],
    quality: dict[str, Any],
    unavailable: list[str],
    geographic_readiness: dict[str, Any] | None,
) -> dict[str, Any]:
    """生成建模前总体就绪性摘要，不替代后续 modeling validation。"""
    roles = set(quality["variables"])
    blocking: list[str] = []
    warnings: list[str] = []

    if "precipitation" not in roles:
        blocking.append("missing precipitation variable")
    if "discharge" not in roles:
        blocking.append("missing observed discharge variable")
    dataset_readiness = meta.get("modeling_readiness") or {}
    blocking.extend(dataset_readiness.get("blocking", []))
    warnings.extend(dataset_readiness.get("warnings", []))
    enrichment_required = list(dataset_readiness.get("enrichment_required", []))
    if quality["duplicate_timestamps"]:
        blocking.append("duplicate timestamps present")
    if meta.get("series_mode") == "event_collection" and meta.get("splits", {}).get("warmup_steps") is None:
        warnings.append("event_collection warmup_steps still requires confirmation")
    if quality["irregular_or_gap_intervals"]:
        warnings.append("temporal gaps or irregular intervals present")
    for role, item in quality["variables"].items():
        if item["missing_fraction"] > 0:
            warnings.append(f"{role} has missing values")
        if item["outlier_count"] > 0:
            warnings.append(f"{role} has robust-MAD outliers")
    if unavailable:
        warnings.extend(unavailable)
    if geographic_readiness and geographic_readiness.get("status") != "ready":
        warnings.append("geographic artifacts are not fully ready")
    if geographic_readiness:
        geo_model = geographic_readiness.get("modeling_readiness") or {}
        blocking.extend(geo_model.get("blocking", []))
        warnings.extend(geo_model.get("warnings", []))
        enrichment_required.extend(geo_model.get("enrichment_required", []))

    status = "not_ready" if blocking else "ready_with_warnings" if warnings else "ready"
    return {
        "status": status,
        "modeling_status": status,
        "blocking": list(dict.fromkeys(blocking)),
        "warnings": list(dict.fromkeys(warnings)),
        "enrichment_required": list(dict.fromkeys(enrichment_required)),
        "variables": _variable_readiness(quality),
        "temporal": {
            "duplicate_timestamps": quality["duplicate_timestamps"],
            "irregular_or_gap_intervals": quality["irregular_or_gap_intervals"],
        },
        "event_collection": {
            "requires_warmup_confirmation": (
                meta.get("series_mode") == "event_collection"
                and meta.get("splits", {}).get("warmup_steps") is None
            )
        },
    }


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _geo_artifact_path(geo: Path, value: str | None, default: str) -> Path:
    path = Path(value or default)
    return path if path.is_absolute() else geo / path


def _count_geojson_features(path: Path) -> int | None:
    if not path.exists():
        return None
    payload = _read_json(path)
    return int(len(payload.get("features", [])))


def _station_role_counts(path: Path) -> dict[str, int] | None:
    if not path.exists():
        return None
    payload = _read_json(path)
    counts: dict[str, int] = {}
    for feature in payload.get("features", []):
        role = str(feature.get("properties", {}).get("role") or "unconfirmed")
        counts[role] = counts.get(role, 0) + 1
    return counts


def _csv_row_count(path: Path) -> int | None:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8", newline="") as handle:
        return sum(1 for _ in csv.DictReader(handle))


def _csv_columns(path: Path) -> list[str] | None:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or [])


def _topology_summary(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    payload = _read_json(path)
    subbasins = payload.get("subbasins", [])
    return {
        "schema_version": payload.get("schema_version"),
        "method": payload.get("method"),
        "subbasin_count": int(len(subbasins)),
        "has_downstream_links": any(item.get("downstream_subbasin_id") for item in subbasins),
        "status": payload.get("status") or payload.get("topology_status"),
        "stream_connectivity": payload.get("stream_connectivity"),
    }


def _hru_readiness(geo: Path, files: dict[str, Any]) -> dict[str, Any] | None:
    manifest_path = _geo_artifact_path(geo, files.get("hru_manifest"), "hru.json")
    if not manifest_path.exists():
        return None
    manifest = _read_json(manifest_path)
    hru_files = manifest.get("files", {})
    hru_path = _geo_artifact_path(manifest_path.parent, hru_files.get("hru"), "hru.geojson")
    parameter_path = _geo_artifact_path(manifest_path.parent, hru_files.get("hru_parameters"), "hru_parameters.csv")
    summary_path = _geo_artifact_path(manifest_path.parent, hru_files.get("hru_summary"), "hru_summary.csv")
    required = {
        "hru": hru_path,
        "hru_parameters": parameter_path,
        "hru_summary": summary_path,
    }
    return {
        "status": "ready" if all(path.exists() for path in required.values()) else "incomplete",
        "source": str(manifest_path),
        "artifact_status": {key: "present" if path.exists() else "missing" for key, path in required.items()},
        "hru_count": manifest.get("hru", {}).get("count"),
        "subbasin_count": manifest.get("hru", {}).get("subbasin_count"),
        "landuse_class_count": manifest.get("hru", {}).get("landuse_class_count"),
        "soil_class_count": manifest.get("hru", {}).get("soil_class_count"),
        "slope_class_count": manifest.get("hru", {}).get("slope_class_count"),
        "area_filter": manifest.get("area_filter"),
        "parameter_rows": _csv_row_count(parameter_path),
        "summary_rows": _csv_row_count(summary_path),
        "warnings": manifest.get("warnings", []),
    }


def _geographic_readiness(geo: Path | None) -> tuple[dict[str, Any] | None, list[str], list[str]]:
    """读取显式传入的 Geo artifacts，并判断空间输入就绪性。"""
    if geo is None:
        return None, [], []
    if not geo.exists():
        return None, [f"geo directory not found: {geo}"], []

    manifest_path = geo / GEO_MANIFEST_FILE
    if not manifest_path.exists():
        return None, [f"geo manifest not found: {manifest_path}"], []

    manifest = _read_json(manifest_path)
    if manifest.get("status") == "error":
        return None, ["geo.json has error status"], []

    warnings: list[str] = []
    files = manifest.get("files", {})
    artifact_status: dict[str, str] = {}
    reverse_files = {value: value for value in files.values()}
    logical_to_default = {
        "basin": "basin.geojson",
        "subbasins": "subbasins.geojson",
        "stations": "stations.geojson",
        "parameters": "parameters.csv",
        "streams": "streams.geojson",
        "flowpaths": "flowpaths.geojson",
        "snapped_outlet": "snapped_outlet.geojson",
        "precipitation_zones": "precipitation_zones.geojson",
        "topology": "topology.json",
        "processed_dem": "processed_dem.tif",
        "slope": "slope.tif",
        "aspect": "aspect.tif",
        "flow_direction": "flow_direction.tif",
        "flow_accumulation": "flow_accumulation.tif",
        "streams_raster": "streams.tif",
    }
    for filename in (*GEO_REQUIRED_ARTIFACTS, *GEO_OPTIONAL_ARTIFACTS):
        logical = next((key for key, default in logical_to_default.items() if default == filename), None)
        declared = files.get(logical) if logical else None
        declared = declared or reverse_files.get(filename, filename)
        path = _geo_artifact_path(geo, declared, filename)
        artifact_status[filename] = "present" if path.exists() else "missing"
        if filename in GEO_REQUIRED_ARTIFACTS and not path.exists():
            warnings.append(f"geographic artifact missing: {filename}")

    subbasin_file = _geo_artifact_path(geo, files.get("subbasins"), "subbasins.geojson")
    station_file = _geo_artifact_path(geo, files.get("stations"), "stations.geojson")
    parameter_file = _geo_artifact_path(geo, files.get("parameters"), "parameters.csv")
    topology_file = _geo_artifact_path(geo, files.get("topology"), "topology.json")
    raster_files = {
        key: _geo_artifact_path(geo, files.get(key), default)
        for key, default in {
            "processed_dem": "processed_dem.tif",
            "slope": "slope.tif",
            "aspect": "aspect.tif",
            "flow_direction": "flow_direction.tif",
            "flow_accumulation": "flow_accumulation.tif",
            "streams_raster": "streams.tif",
        }.items()
    }
    readiness = {
        "status": "ready" if not warnings and (manifest.get("modeling_readiness", {}).get("modeling_status") in (None, "ready", "ready_with_warnings")) else "incomplete",
        "source": str(manifest_path),
        "crs": manifest.get("crs"),
        "artifact_status": artifact_status,
        "subbasin_count": manifest.get("subbasins", {}).get("count")
        or _count_geojson_features(subbasin_file),
        "station_roles": _station_role_counts(station_file),
        "parameter_rows": _csv_row_count(parameter_file),
        "parameter_columns": _csv_columns(parameter_file),
        "topology": _topology_summary(topology_file),
        "hru_readiness": _hru_readiness(geo, files),
        "raster_status": {
            key: "present" if path.exists() else "missing"
            for key, path in raster_files.items()
        },
        "provenance": manifest.get("provenance"),
        "topology_status": manifest.get("topology_status"),
        "outlet_snap_status": manifest.get("outlet_snap_status"),
        "stream_connectivity": manifest.get("stream_connectivity"),
        "artifact_cleanup": manifest.get("artifact_cleanup"),
        "modeling_readiness": manifest.get("modeling_readiness"),
    }
    return readiness, [], warnings


def _analysis_warnings(quality: dict[str, Any], geo_warnings: list[str]) -> list[str]:
    warnings = [
        f"{role}: missing fraction {item['missing_fraction']:.1%}"
        for role, item in quality["variables"].items()
        if item["missing_fraction"] > 0
    ]
    warnings.extend(geo_warnings)
    return warnings


def _write_analysis_artifacts(
    output: Path,
    features: pd.DataFrame,
    preanalysis: dict[str, Any],
    analysis: dict[str, Any],
) -> list[str]:
    features.to_parquet(output / EVENT_FEATURES_FILE, index=False)
    write_json(output / PREANALYSIS_FILE, preanalysis)
    write_json(output / ANALYSIS_FILE, analysis)
    return [ANALYSIS_FILE, PREANALYSIS_FILE, EVENT_FEATURES_FILE]


# ---------------------------------------------------------------------------
# 公开 Runtime API
# ---------------------------------------------------------------------------


def analyze_dataset(dataset: Path, output: Path, *, geo: Path | None = None) -> int:
    """分析 HydroTune dataset，并可选检查 Geo artifacts 的建模就绪性。"""
    output.mkdir(parents=True, exist_ok=True)
    try:
        frame, meta = load_dataset(dataset)
        roles = _role_variables(meta)
        geographic_readiness, geo_errors, geo_warnings = _geographic_readiness(geo)
        if geo_errors:
            return finish(output, result("analysis", errors=geo_errors))

        quality = _quality(frame, meta)
        temporal = _temporal_coverage(frame, meta)
        features = _event_features(frame, meta, roles)
        event_statistics = _event_statistics(features)
        water_balance = _water_balance(features, meta, roles)
        unavailable = _unavailable_items(meta, roles, water_balance)
        modeling_readiness = _modeling_readiness(
            meta,
            quality,
            unavailable,
            geographic_readiness,
        )

        sources = {
            "dataset": str(dataset / "dataset.json"),
        }
        if geo is not None:
            sources["geo"] = str(geo / GEO_MANIFEST_FILE)

        preanalysis = {
            "schema_version": PREANALYSIS_VERSION,
            "series_mode": meta.get("series_mode"),
            "data_scope": {
                "start": temporal["start"],
                "end": temporal["end"],
                "samples": int(len(frame)),
                "variables": list(quality["variables"]),
            },
            "temporal_coverage": temporal,
            "quality": quality,
            "event_summary": {
                "count": event_statistics["count"],
                "peak_max": event_statistics["peak_max"],
                "event_type_counts": event_statistics["event_type_counts"],
                "events_without_local_precipitation": event_statistics["events_without_local_precipitation"],
            },
            "event_statistics": event_statistics,
            "water_balance": water_balance,
            "geographic_readiness": geographic_readiness,
            "unavailable": unavailable,
            "artifact_sources": sources,
        }
        analysis = {
            "schema_version": ANALYSIS_VERSION,
            "variables": quality["variables"],
            "physical_diagnostics": {
                "runoff_coefficient": (
                    "available"
                    if features.runoff_coefficient.notna().any()
                    else "unavailable"
                )
            },
            "modeling_readiness": modeling_readiness,
            "geographic_readiness": geographic_readiness,
            "preanalysis": PREANALYSIS_FILE,
        }

        outputs = _write_analysis_artifacts(output, features, preanalysis, analysis)
        warnings = _analysis_warnings(quality, geo_warnings)
        return finish(
            output,
            result("analysis", warnings=warnings, outputs=outputs, summary=analysis),
        )
    except Exception as exc:
        return finish(output, result("analysis", errors=[str(exc)]))


def load_analysis(directory: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """读取已生成的 analysis.json 和 preanalysis.json。"""
    analysis = _read_json(directory / ANALYSIS_FILE)
    preanalysis = _read_json(directory / PREANALYSIS_FILE)
    return analysis, preanalysis


# ---------------------------------------------------------------------------
# CLI adapters
# ---------------------------------------------------------------------------


def cmd_analyze(args) -> int:
    """CLI 适配器：解析 argparse 参数并调用 analyze_dataset。"""
    return analyze_dataset(
        dataset=Path(args.dataset),
        output=Path(args.output),
        geo=Path(args.geo) if getattr(args, "geo", None) else None,
    )
