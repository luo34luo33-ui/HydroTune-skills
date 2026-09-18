"""HydroTune 固定可视化运行时。

本模块负责从 HydroTune canonical artifacts 生成确定性的建模前图表：

- dataset timeseries：Intake 后的时序数据概览。
- event overview：Analysis 后的事件特征概览。
- geographic overview：现成 Geo artifacts 中的流域、子流域、站点和河网概览。

本模块只选择固定模板和输入 artifacts，不执行 Intake、Analysis、Geo preprocessing、
模型模拟、参数率定或模型误差诊断。
"""

from __future__ import annotations

import csv
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from .common import finish, result, write_json
from .intake import load_dataset


# 图表输出 contract，和 skill-level legacy scripts 保持同一 schema family。
PLOT_SCHEMA_VERSION = "hydrotune.plots.v1"
DEFAULT_DPI = 160

DATASET_TIMESERIES_FILE = "dataset-timeseries.png"
EVENT_OVERVIEW_FILE = "event-overview.png"
GEOGRAPHIC_OVERVIEW_FILE = "geographic-overview.png"
FIGURE_FILE = "figure.json"

SUPPORTED_TEMPLATES = (
    "dataset_timeseries",
    "event_overview",
    "geographic_overview",
)

GEO_MANIFEST_FILE = "geo.json"
GEO_REQUIRED_VECTOR_FILES = ("basin.geojson", "subbasins.geojson", "stations.geojson")
GEO_OPTIONAL_VECTOR_FILES = ("streams.geojson", "flowpaths.geojson", "snapped_outlet.geojson", "hru.geojson")

__all__ = [
    "cmd_visualize_dataset",
    "cmd_visualize_events",
    "cmd_visualize_geo",
    "plot_dataset_timeseries",
    "plot_event_overview",
    "plot_geographic_overview",
]


# ---------------------------------------------------------------------------
# 内部确定性操作
# ---------------------------------------------------------------------------


def _load_matplotlib():
    import matplotlib.pyplot as plt

    return plt


def _load_geo_plot_dependencies() -> dict[str, Any]:
    missing = [
        package
        for package in ("geopandas", "shapely", "pyproj", "fiona")
        if importlib.util.find_spec(package) is None
    ]
    if missing:
        raise ValueError(
            "geographic visualization requires optional packages: "
            + ", ".join(missing)
        )

    import geopandas as gpd

    return {"gpd": gpd}


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _geo_artifact_path(geo: Path, value: str | None, default: str) -> Path:
    path = Path(value or default)
    return path if path.is_absolute() else geo / path


def _plot_result(output: Path, template: str, figure: dict[str, Any], warnings: list[str] | None = None) -> int:
    """写出 figure.json 和标准 result.json。"""
    warnings = warnings or []
    write_json(output / FIGURE_FILE, figure)
    return finish(
        output,
        result(
            "visualization",
            warnings=warnings,
            outputs=[str(output / figure["output_png"]), str(output / FIGURE_FILE)],
            template=template,
        ),
    )


def _figure_payload(
    output_png: str,
    template: str,
    meta: dict[str, Any] | None,
    extra: dict[str, Any],
) -> dict[str, Any]:
    """构造固定图表 metadata。"""
    return {
        "schema_version": PLOT_SCHEMA_VERSION,
        "template": template,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "series_mode": meta.get("series_mode") if meta else None,
        "splits": meta.get("splits") if meta else None,
        "output_png": output_png,
        "input_provenance": meta.get("provenance") if meta else None,
        **extra,
    }


def _role_lookup(meta: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {variable["role"]: variable for variable in meta.get("variables", [])}


def _resolve_variable_columns(
    meta: dict[str, Any],
    variables: list[str] | None,
) -> list[str]:
    """把 role 或 column 参数解析为 dataset.parquet 中的列名。"""
    declared = meta.get("variables", [])
    by_role = {variable["role"]: variable["column"] for variable in declared}
    columns = {variable["column"] for variable in declared}
    if not variables:
        ordered = []
        for role in ("precipitation", "discharge", "temperature", "pet", "upstream_discharge"):
            if role in by_role:
                ordered.append(by_role[role])
        for column in columns:
            if column not in ordered:
                ordered.append(column)
        return ordered

    resolved = []
    missing = []
    for item in variables:
        if item in by_role:
            resolved.append(by_role[item])
        elif item in columns:
            resolved.append(item)
        else:
            missing.append(item)
    if missing:
        raise ValueError(f"visualization variable not found: {', '.join(missing)}")
    return list(dict.fromkeys(resolved))


def _unit_label(meta: dict[str, Any], column: str) -> str:
    variable = next(
        (item for item in meta.get("variables", []) if item["column"] == column),
        None,
    )
    if not variable:
        return column
    unit = variable.get("unit")
    return f"{variable['role']} ({column}, {unit})" if unit else f"{variable['role']} ({column})"


def _split_spans(meta: dict[str, Any]) -> list[tuple[str, pd.Timestamp, pd.Timestamp]]:
    """读取 continuous split，用于时序图背景标注。"""
    if meta.get("series_mode") != "continuous":
        return []
    spans = []
    for name in ("warmup", "calibration", "validation"):
        split = meta.get("splits", {}).get(name)
        if split and split.get("start") and split.get("end"):
            spans.append((name, pd.Timestamp(split["start"]), pd.Timestamp(split["end"])))
    return spans


def _shade_splits(axis, meta: dict[str, Any]) -> None:
    colors = {
        "warmup": "#D8DEE9",
        "calibration": "#B7E4C7",
        "validation": "#FFD6A5",
    }
    for name, start, end in _split_spans(meta):
        axis.axvspan(start, end, color=colors[name], alpha=0.25, label=name)


def _plot_continuous_dataset(frame: pd.DataFrame, meta: dict[str, Any], columns: list[str], path: Path) -> dict[str, Any]:
    """绘制 continuous dataset 的建模前时序图。"""
    plt = _load_matplotlib()
    roles = _role_lookup(meta)
    precipitation_column = roles.get("precipitation", {}).get("column")
    line_columns = [column for column in columns if column != precipitation_column]
    panel_count = 2 if precipitation_column in columns and line_columns else 1
    fig, axes = plt.subplots(
        panel_count,
        1,
        figsize=(12, 4 + 2 * (panel_count - 1)),
        dpi=DEFAULT_DPI,
        sharex=True,
    )
    if panel_count == 1:
        axes = [axes]

    axis_index = 0
    if precipitation_column in columns:
        rain_ax = axes[axis_index]
        rain_ax.bar(
            frame.timestamp,
            pd.to_numeric(frame[precipitation_column], errors="coerce").fillna(0),
            width=0.02,
            color="#4C78A8",
            alpha=0.75,
            label=_unit_label(meta, precipitation_column),
        )
        _shade_splits(rain_ax, meta)
        rain_ax.set_ylabel("Precipitation")
        rain_ax.legend(fontsize=8, loc="upper right")
        rain_ax.grid(alpha=0.25)
        axis_index += 1

    data_ax = axes[axis_index]
    for column in line_columns or [column for column in columns if column != precipitation_column]:
        data_ax.plot(
            frame.timestamp,
            pd.to_numeric(frame[column], errors="coerce"),
            lw=1.4,
            label=_unit_label(meta, column),
        )
    _shade_splits(data_ax, meta)
    data_ax.set_xlabel("Time")
    data_ax.set_ylabel("Value")
    data_ax.legend(fontsize=8, loc="upper right")
    data_ax.grid(alpha=0.25)
    fig.suptitle("HydroTune dataset timeseries")
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)

    return {
        "template": "dataset_timeseries",
        "variables": columns,
        "range": [str(frame.timestamp.min()), str(frame.timestamp.max())],
        "split_bands": [name for name, _, _ in _split_spans(meta)],
    }


def _plot_event_collection_dataset(frame: pd.DataFrame, meta: dict[str, Any], columns: list[str], path: Path) -> dict[str, Any]:
    """绘制 event_collection 的建模前事件概览，不拼接事件连续性。"""
    plt = _load_matplotlib()
    fig, axis = plt.subplots(figsize=(12, 5), dpi=DEFAULT_DPI)
    event_ids = list(frame.event_id.dropna().astype(str).unique())
    for event_index, event_id in enumerate(event_ids, start=1):
        event = frame[frame.event_id == event_id].sort_values("timestamp")
        x = range(len(event))
        for column in columns:
            values = pd.to_numeric(event[column], errors="coerce")
            axis.plot(
                [sample + event_index * (len(event) + 1) for sample in x],
                values,
                lw=1.2,
                alpha=0.75,
                label=_unit_label(meta, column) if event_index == 1 else None,
            )
        axis.text(
            event_index * (len(event) + 1),
            axis.get_ylim()[0],
            event_id,
            rotation=45,
            fontsize=7,
            va="top",
        )

    axis.set_title("HydroTune event collection overview")
    axis.set_xlabel("Samples grouped by event")
    axis.set_ylabel("Value")
    axis.grid(alpha=0.25)
    axis.legend(fontsize=8, loc="upper right")
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)

    return {
        "template": "dataset_timeseries",
        "variables": columns,
        "event_count": len(event_ids),
        "warmup_status": meta.get("splits", {}).get("warmup_status"),
        "warmup_steps": meta.get("splits", {}).get("warmup_steps"),
    }


def _numeric_feature_columns(features: pd.DataFrame) -> list[str]:
    candidates = [
        "duration_seconds",
        "precipitation_total",
        "discharge_peak",
        "runoff_coefficient",
    ]
    return [
        column
        for column in candidates
        if column in features and features[column].notna().any()
    ]


def _plot_event_feature_overview(features: pd.DataFrame, path: Path) -> dict[str, Any]:
    """绘制 Analysis 事件特征概览。"""
    numeric_columns = _numeric_feature_columns(features)
    if features.empty or not numeric_columns:
        raise ValueError("no plottable event features available")

    plt = _load_matplotlib()
    fig, axes = plt.subplots(
        len(numeric_columns),
        1,
        figsize=(10, max(3, 2.4 * len(numeric_columns))),
        dpi=DEFAULT_DPI,
        sharex=True,
    )
    if len(numeric_columns) == 1:
        axes = [axes]

    labels = features["event_id"].astype(str).tolist()
    x = range(len(features))
    for axis, column in zip(axes, numeric_columns):
        axis.bar(x, pd.to_numeric(features[column], errors="coerce"), color="#4C78A8", alpha=0.8)
        axis.set_ylabel(column)
        axis.grid(axis="y", alpha=0.25)

    axes[-1].set_xticks(list(x))
    axes[-1].set_xticklabels(labels, rotation=45, ha="right", fontsize=8)
    axes[-1].set_xlabel("Event")
    fig.suptitle("HydroTune event feature overview")
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)

    skipped = [
        column
        for column in ("duration_seconds", "precipitation_total", "discharge_peak", "runoff_coefficient")
        if column not in numeric_columns
    ]
    return {
        "template": "event_overview",
        "event_count": int(len(features)),
        "plotted_metrics": numeric_columns,
        "skipped_metrics": skipped,
    }


def _geo_file_paths(geo: Path, manifest: dict[str, Any]) -> dict[str, Path]:
    files = manifest.get("files", {})
    hru_path = _geo_artifact_path(geo, files.get("hru"), "hru.geojson")
    hru_manifest = _geo_artifact_path(geo, files.get("hru_manifest"), "hru.json")
    if not hru_path.exists() and hru_manifest.exists():
        try:
            hru_files = _read_json(hru_manifest).get("files", {})
            hru_path = _geo_artifact_path(hru_manifest.parent, hru_files.get("hru"), "hru.geojson")
        except Exception:
            pass
    return {
        "basin": _geo_artifact_path(geo, files.get("basin"), "basin.geojson"),
        "subbasins": _geo_artifact_path(geo, files.get("subbasins"), "subbasins.geojson"),
        "stations": _geo_artifact_path(geo, files.get("stations"), "stations.geojson"),
        "streams": _geo_artifact_path(geo, files.get("streams"), "streams.geojson"),
        "flowpaths": _geo_artifact_path(geo, files.get("flowpaths"), "flowpaths.geojson"),
        "snapped_outlet": _geo_artifact_path(geo, files.get("snapped_outlet"), "snapped_outlet.geojson"),
        "hru": hru_path,
    }


def _read_geo_layer(path: Path, deps: dict[str, Any]):
    return deps["gpd"].read_file(path)


def _plot_geographic_layers(geo: Path, manifest: dict[str, Any], output_png: Path) -> tuple[dict[str, Any], list[str]]:
    """绘制现成 Geo vector artifacts。"""
    deps = _load_geo_plot_dependencies()
    plt = _load_matplotlib()
    paths = _geo_file_paths(geo, manifest)
    missing = [
        str(paths[name])
        for name in ("basin", "subbasins", "stations")
        if not paths[name].exists()
    ]
    if missing:
        raise ValueError("required geographic artifact missing: " + ", ".join(missing))

    warnings = []
    if not paths["streams"].exists():
        warnings.append("optional streams.geojson missing; plotted basin/subbasins/stations only")
    if not paths["flowpaths"].exists():
        warnings.append("optional flowpaths.geojson missing; flowpaths not plotted")
    if not paths["snapped_outlet"].exists():
        warnings.append("optional snapped_outlet.geojson missing; snapped outlet not plotted")
    if not paths["hru"].exists():
        warnings.append("optional hru.geojson missing; HRU layer not plotted")

    basin = _read_geo_layer(paths["basin"], deps)
    subbasins = _read_geo_layer(paths["subbasins"], deps)
    stations = _read_geo_layer(paths["stations"], deps)
    streams = _read_geo_layer(paths["streams"], deps) if paths["streams"].exists() else None
    flowpaths = _read_geo_layer(paths["flowpaths"], deps) if paths["flowpaths"].exists() else None
    snapped_outlet = _read_geo_layer(paths["snapped_outlet"], deps) if paths["snapped_outlet"].exists() else None
    hru = _read_geo_layer(paths["hru"], deps) if paths["hru"].exists() else None

    fig, axis = plt.subplots(figsize=(8, 8), dpi=DEFAULT_DPI)
    if hru is not None and not hru.empty:
        hru.plot(ax=axis, column="landuse_class" if "landuse_class" in hru else None, alpha=0.28, edgecolor="#FFFFFF", linewidth=0.25)
    if not subbasins.empty:
        subbasins.plot(ax=axis, column="subbasin_id" if "subbasin_id" in subbasins else None, alpha=0.35, edgecolor="#4C78A8")
        if "subbasin_id" in subbasins:
            for _, row in subbasins.iterrows():
                if row.geometry is not None and not row.geometry.is_empty:
                    point = row.geometry.representative_point()
                    axis.text(point.x, point.y, str(row["subbasin_id"]), fontsize=7, ha="center", va="center")
    if not basin.empty:
        basin.boundary.plot(ax=axis, color="#222222", linewidth=1.5)
    if flowpaths is not None and not flowpaths.empty:
        flowpaths.plot(ax=axis, color="#E76F51", linewidth=1.0, linestyle="--")
    if streams is not None and not streams.empty:
        streams.plot(ax=axis, color="#2A9D8F", linewidth=1.4)
    if not stations.empty:
        for role, group in stations.groupby("role" if "role" in stations else lambda _: "station"):
            group.plot(ax=axis, markersize=28, label=str(role), alpha=0.9)
    if snapped_outlet is not None and not snapped_outlet.empty:
        snapped_outlet.plot(ax=axis, markersize=46, marker="x", color="#D00000", label="snapped_outlet")

    axis.set_title("HydroTune geographic overview")
    axis.set_xlabel("X")
    axis.set_ylabel("Y")
    axis.grid(alpha=0.25)
    axis.legend(fontsize=8, loc="best")
    axis.set_aspect("equal", adjustable="box")
    fig.tight_layout()
    fig.savefig(output_png)
    plt.close(fig)

    station_roles = {}
    if "role" in stations:
        station_roles = {
            str(role): int(count)
            for role, count in stations["role"].fillna("unconfirmed").value_counts().items()
        }

    return {
        "template": "geographic_overview",
        "subbasin_count": int(len(subbasins)),
        "station_count": int(len(stations)),
        "station_roles": station_roles,
        "streams_plotted": streams is not None and not streams.empty,
        "flowpaths_plotted": flowpaths is not None and not flowpaths.empty,
        "snapped_outlet_plotted": snapped_outlet is not None and not snapped_outlet.empty,
        "hru_plotted": hru is not None and not hru.empty,
        "geo_manifest": str(geo / GEO_MANIFEST_FILE),
    }, warnings


# ---------------------------------------------------------------------------
# 公开 Runtime API
# ---------------------------------------------------------------------------


def plot_dataset_timeseries(
    dataset: Path,
    output: Path,
    *,
    variables: list[str] | None = None,
) -> int:
    """绘制 Intake 后的建模前时序数据图。"""
    output.mkdir(parents=True, exist_ok=True)
    try:
        frame, meta = load_dataset(dataset)
        frame = frame.copy()
        frame["timestamp"] = pd.to_datetime(frame["timestamp"])
        columns = _resolve_variable_columns(meta, variables)
        if not columns:
            raise ValueError("no plottable dataset variables found")

        output_png = output / DATASET_TIMESERIES_FILE
        if meta.get("series_mode") == "event_collection":
            details = _plot_event_collection_dataset(frame, meta, columns, output_png)
        else:
            details = _plot_continuous_dataset(frame.sort_values("timestamp"), meta, columns, output_png)

        figure = _figure_payload(
            DATASET_TIMESERIES_FILE,
            "dataset_timeseries",
            meta,
            {
                "input_dataset": str(dataset),
                **details,
            },
        )
        return _plot_result(output, "dataset_timeseries", figure)
    except Exception as exc:
        return finish(output, result("visualization", errors=[str(exc)]))


def plot_event_overview(dataset: Path, analysis: Path, output: Path) -> int:
    """绘制 Analysis 生成的事件特征概览图。"""
    output.mkdir(parents=True, exist_ok=True)
    try:
        _, meta = load_dataset(dataset)
        features_path = analysis / "event_features.parquet"
        preanalysis_path = analysis / "preanalysis.json"
        if not features_path.exists():
            raise ValueError(f"event features artifact not found: {features_path}")
        if not preanalysis_path.exists():
            raise ValueError(f"preanalysis artifact not found: {preanalysis_path}")

        features = pd.read_parquet(features_path)
        preanalysis = _read_json(preanalysis_path)
        output_png = output / EVENT_OVERVIEW_FILE
        details = _plot_event_feature_overview(features, output_png)
        figure = _figure_payload(
            EVENT_OVERVIEW_FILE,
            "event_overview",
            meta,
            {
                "input_dataset": str(dataset),
                "input_analysis": str(analysis),
                "preanalysis_event_summary": preanalysis.get("event_summary"),
                **details,
            },
        )
        return _plot_result(output, "event_overview", figure)
    except Exception as exc:
        return finish(output, result("visualization", errors=[str(exc)]))


def plot_geographic_overview(geo: Path, output: Path) -> int:
    """绘制现成 Geo artifacts 的空间概览图。"""
    output.mkdir(parents=True, exist_ok=True)
    try:
        manifest_path = geo / GEO_MANIFEST_FILE
        if not manifest_path.exists():
            raise ValueError(f"geo manifest not found: {manifest_path}")
        manifest = _read_json(manifest_path)
        if manifest.get("status") == "error":
            raise ValueError("geo.json has error status")

        output_png = output / GEOGRAPHIC_OVERVIEW_FILE
        details, warnings = _plot_geographic_layers(geo, manifest, output_png)
        figure = _figure_payload(
            GEOGRAPHIC_OVERVIEW_FILE,
            "geographic_overview",
            None,
            {
                "input_geo": str(geo),
                "geo_schema_version": manifest.get("schema_version"),
                "geo_provenance": manifest.get("provenance"),
                **details,
            },
        )
        return _plot_result(output, "geographic_overview", figure, warnings)
    except Exception as exc:
        return finish(output, result("visualization", errors=[str(exc)]))


# ---------------------------------------------------------------------------
# CLI adapters
# ---------------------------------------------------------------------------


def cmd_visualize_dataset(args) -> int:
    """CLI 适配器：绘制建模前 dataset 时序图。"""
    return plot_dataset_timeseries(
        dataset=Path(args.dataset),
        output=Path(args.output),
        variables=args.variables,
    )


def cmd_visualize_events(args) -> int:
    """CLI 适配器：绘制建模前事件特征图。"""
    return plot_event_overview(
        dataset=Path(args.dataset),
        analysis=Path(args.analysis),
        output=Path(args.output),
    )


def cmd_visualize_geo(args) -> int:
    """CLI 适配器：绘制 Geo artifacts 空间概览图。"""
    return plot_geographic_overview(
        geo=Path(args.geo),
        output=Path(args.output),
    )
