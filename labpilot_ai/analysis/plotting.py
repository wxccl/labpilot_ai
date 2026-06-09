from pathlib import Path
import matplotlib.pyplot as plt


def scatter_line(df, x, y, out_path=None):
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.scatter(df[x], df[y], label="raw")
    ax.plot(df[x], df[y], alpha=0.5)
    ax.set_xlabel(x)
    ax.set_ylabel(y)
    ax.grid(True, alpha=0.3)
    ax.legend()
    if out_path:
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out_path, dpi=200, bbox_inches="tight")
    return fig
