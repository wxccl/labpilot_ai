from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


ONE_D_FITS = ["none", "linear", "gaussian", "logarithmic", "exponential", "lorentzian"]
HISTOGRAM_FITS = ["none", "gaussian", "lorentzian"]
TWO_D_FITS = ["none", "gaussian2d", "double_gaussian2d"]


@dataclass(frozen=True)
class PlotSpec:
    key: str
    label: str
    required_columns: tuple[str, ...]
    fit_models: tuple[str, ...]
    description: str


PLOT_SPECS = {
    "scatter_line": PlotSpec(
        "scatter_line",
        "1D scatter + line",
        ("x", "y"),
        tuple(ONE_D_FITS),
        "Single-parameter scan against one result column.",
    ),
    "mean_errorbar": PlotSpec(
        "mean_errorbar",
        "1D mean +/- std",
        ("x", "y"),
        tuple(ONE_D_FITS),
        "Grouped one-parameter scan; repeated x values are shown as mean with standard deviation.",
    ),
    "histogram": PlotSpec(
        "histogram",
        "Histogram",
        ("value",),
        tuple(HISTOGRAM_FITS),
        "Distribution of one result column.",
    ),
    "scatter2d": PlotSpec(
        "scatter2d",
        "2D color scatter",
        ("x", "y", "z"),
        tuple(TWO_D_FITS),
        "Two scan variables and one result variable shown as colored scatter points.",
    ),
    "heatmap2d": PlotSpec(
        "heatmap2d",
        "2D grid heatmap",
        ("x", "y", "z"),
        tuple(TWO_D_FITS),
        "Two scan variables and one result variable binned onto a grid with a color bar.",
    ),
    "surface3d": PlotSpec(
        "surface3d",
        "3D scatter/surface",
        ("x", "y", "z"),
        tuple(TWO_D_FITS),
        "Two scan variables and one result variable shown in 3D.",
    ),
}


def numeric_varying_columns(dataframe: pd.DataFrame | None, *, min_unique: int = 2) -> list[str]:
    """Return numeric-like columns that have enough variation to be useful in plots."""
    if dataframe is None or dataframe.empty:
        return []
    out: list[str] = []
    for column in dataframe.columns:
        name = str(column)
        if name.lower() in {"filepath", "path", "filename", "shot_label"}:
            continue
        values = pd.to_numeric(dataframe[column], errors="coerce")
        if int(values.dropna().nunique()) >= min_unique:
            out.append(name)
    return out


def valid_fit_models(plot_type: str) -> list[str]:
    spec = PLOT_SPECS.get(plot_type, PLOT_SPECS["scatter_line"])
    return list(spec.fit_models)


def required_columns(plot_type: str) -> tuple[str, ...]:
    spec = PLOT_SPECS.get(plot_type, PLOT_SPECS["scatter_line"])
    return spec.required_columns


def default_plot_columns(plot_type: str, columns: list[str]) -> dict[str, str]:
    if not columns:
        return {"x": "", "y": "", "z": ""}
    if plot_type == "histogram":
        return {"x": "", "y": columns[0], "z": ""}
    if plot_type in {"scatter_line", "mean_errorbar"}:
        return {
            "x": columns[0],
            "y": columns[1] if len(columns) > 1 else columns[0],
            "z": "",
        }
    return {
        "x": columns[0],
        "y": columns[1] if len(columns) > 1 else columns[0],
        "z": columns[2] if len(columns) > 2 else columns[-1],
    }
