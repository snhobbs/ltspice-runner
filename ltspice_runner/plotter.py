from pathlib import Path
from typing import Optional

import matplotlib.pyplot as plt
import numpy as np
from ltspice import Ltspice

_FREQ_MODES = {"AC", "FFT", "Noise"}
_TIME_MODES = {"Transient", "DC"}


def plot_raw(
    raw_path: Path,
    variables: Optional[list[str]] = None,
    output_path: Optional[Path] = None,
    title: Optional[str] = None,
    db: bool = False,
) -> plt.Figure:
    """Plot signals from an LTspice .raw file."""
    sim = Ltspice(str(raw_path)).parse()

    to_plot = variables if variables else sim.variables[1:]

    if sim._mode == "Operating Point":
        return _plot_operating_point(sim, to_plot, output_path, title)

    if sim._mode in _FREQ_MODES:
        return _plot_freq(sim, to_plot, output_path, title, db)

    if sim._mode in _TIME_MODES:
        return _plot_time(sim, to_plot, output_path, title)

    raise ValueError(f"Unsupported simulation mode: {sim._mode!r}")


def _plot_time(sim, variables, output_path, title):
    x = sim.get_time()
    fig, ax = plt.subplots(figsize=(10, 6))
    for var in variables:
        data = sim.get_data(var)
        if data is not None:
            ax.plot(x, data.real, label=var)
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Value")
    ax.legend()
    ax.grid(True, which="both", alpha=0.3)
    if title:
        ax.set_title(title)
    return _save_or_show(fig, output_path)


def _plot_freq(sim, variables, output_path, title, db):
    x = sim.get_frequency()
    fig, ax = plt.subplots(figsize=(10, 6))
    for var in variables:
        data = sim.get_data(var)
        if data is None:
            continue
        y = 20 * np.log10(np.abs(data)) if db else np.abs(data)
        ax.plot(x, y, label=var)
    ax.set_xscale("log")
    ax.set_xlabel("Frequency (Hz)")
    ax.set_ylabel("Magnitude (dB)" if db else "Magnitude")
    ax.legend()
    ax.grid(True, which="both", alpha=0.3)
    if title:
        ax.set_title(title)
    return _save_or_show(fig, output_path)


def _plot_operating_point(sim, variables, output_path, title):
    values = {}
    for var in variables:
        data = sim.get_data(var)
        if data is not None and len(data) > 0:
            values[var] = float(data[0].real)

    fig, ax = plt.subplots(figsize=(max(6, len(values) * 0.5), 5))
    labels = list(values.keys())
    vals = list(values.values())
    colors = ["tab:red" if v < 0 else "tab:blue" for v in vals]
    ax.bar(range(len(labels)), vals, color=colors)
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, rotation=45, ha="right")
    ax.set_ylabel("Voltage (V) / Current (A)")
    ax.axhline(0, color="black", linewidth=0.8)
    ax.grid(True, axis="y", alpha=0.3)
    if title:
        ax.set_title(title)
    fig.tight_layout()
    return _save_or_show(fig, output_path)


def _save_or_show(fig, output_path):
    if output_path:
        fig.savefig(output_path, dpi=150, bbox_inches="tight")
    else:
        plt.show()
    plt.close(fig)
    return fig
