from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt
import pandas as pd


def _numeric_frame(df, columns):
    missing = [name for name in columns if name not in df.columns]
    if missing:
        raise KeyError(f"plot column(s) not found: {', '.join(missing)}")
    out = pd.DataFrame({name: pd.to_numeric(df[name], errors="coerce") for name in columns})
    out = out.replace([np.inf, -np.inf], np.nan).dropna()
    if out.empty:
        raise ValueError(f"no finite numeric rows for columns: {', '.join(columns)}")
    return out


def scatter_line(df, x, y, out_path=None):
    data = _numeric_frame(df, [x, y]).sort_values(x)
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.scatter(data[x], data[y], label="raw")
    ax.plot(data[x], data[y], alpha=0.5)
    ax.set_xlabel(x)
    ax.set_ylabel(y)
    ax.grid(True, alpha=0.3)
    ax.legend()
    if out_path:
        save_figure(fig, out_path)
    return fig


def mean_errorbar(df, x, y, out_path=None):
    data = _numeric_frame(df, [x, y])
    grouped = data.groupby(x)[y].agg(["mean", "std", "count"]).reset_index().sort_values(x)
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.scatter(data[x], data[y], alpha=0.35, label="raw")
    ax.errorbar(grouped[x], grouped["mean"], yerr=grouped["std"].fillna(0), fmt="o-", capsize=3, label="mean +/- std")
    ax.set_xlabel(x)
    ax.set_ylabel(y)
    ax.grid(True, alpha=0.3)
    ax.legend()
    if out_path:
        save_figure(fig, out_path)
    return fig


def histogram(df, value, bins=30, out_path=None):
    data = _numeric_frame(df, [value])
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.hist(data[value], bins=bins, alpha=0.8)
    ax.set_xlabel(value)
    ax.set_ylabel("count")
    ax.grid(True, alpha=0.3)
    if out_path:
        save_figure(fig, out_path)
    return fig


def scatter2d(df, x, y, value, out_path=None):
    data = _numeric_frame(df, [x, y, value])
    fig, ax = plt.subplots(figsize=(6, 5))
    sc = ax.scatter(data[x], data[y], c=data[value], cmap="viridis")
    ax.set_xlabel(x)
    ax.set_ylabel(y)
    fig.colorbar(sc, ax=ax, label=value)
    ax.grid(True, alpha=0.25)
    if out_path:
        save_figure(fig, out_path)
    return fig


def heatmap2d(df, x, y, value, out_path=None):
    data = _numeric_frame(df, [x, y, value])
    table = data.groupby([y, x])[value].mean().unstack(x)
    fig, ax = plt.subplots(figsize=(7, 5))
    image = ax.imshow(table.values, aspect="auto", origin="lower", cmap="viridis")
    ax.set_xticks(np.arange(len(table.columns)))
    ax.set_xticklabels([str(v) for v in table.columns], rotation=45, ha="right")
    ax.set_yticks(np.arange(len(table.index)))
    ax.set_yticklabels([str(v) for v in table.index])
    ax.set_xlabel(x)
    ax.set_ylabel(y)
    fig.colorbar(image, ax=ax, label=value)
    if out_path:
        save_figure(fig, out_path)
    return fig


def surface3d(df, x, y, value, out_path=None):
    data = _numeric_frame(df, [x, y, value])
    fig = plt.figure(figsize=(7, 5))
    ax = fig.add_subplot(111, projection="3d")
    grouped = data.groupby([x, y])[value].mean().reset_index()
    ax.scatter(grouped[x], grouped[y], grouped[value], c=grouped[value], cmap="viridis")
    if len(grouped) >= 4:
        try:
            ax.plot_trisurf(grouped[x], grouped[y], grouped[value], cmap="viridis", alpha=0.35, linewidth=0.2)
        except Exception:
            pass
    ax.set_xlabel(x)
    ax.set_ylabel(y)
    ax.set_zlabel(value)
    if out_path:
        save_figure(fig, out_path)
    return fig


def save_figure(fig, out_path):
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=200, bbox_inches="tight")
    return out_path
