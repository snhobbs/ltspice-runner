from pathlib import Path
from typing import Optional

import matplotlib.pyplot as plt
import numpy as np
from ltspice import Ltspice

_FREQ_MODES = {"AC", "FFT", "Noise"}
_TIME_MODES = {"Transient", "DC"}

# Single-trace colours: left axis uses the first group, right axis the second.
_COLORS_LEFT  = ["#1f77b4", "#2ca02c", "#9467bd", "#8c564b", "#17becf"]
_COLORS_RIGHT = ["#ff7f0e", "#d62728", "#e377c2", "#bcbd22", "#7f7f7f"]

# Beyond this many cases the legend is omitted to keep the plot readable.
_LEGEND_CASE_LIMIT = 20

_LINESTYLES = ["-", "--", ":", "-."]


def plot_raw(
    raw_path: Path,
    variables: Optional[list[str]] = None,
    right_vars: Optional[list[str]] = None,
    output_path: Optional[Path] = None,
    title: Optional[str] = None,
    db: bool = False,
) -> plt.Figure:
    """Plot signals from an LTspice .raw file.

    Stepped raw files (case_count > 1) are plotted with one trace per step,
    coloured by a viridis gradient.  If right_vars is given those variables are
    drawn on a twin y-axis.
    """
    sim = Ltspice(str(raw_path)).parse()

    left = variables if variables else sim.variables[1:]
    right = right_vars or []

    if sim._mode == "Operating Point":
        return _plot_operating_point(sim, left, output_path, title)

    if sim._mode in _FREQ_MODES:
        return _plot_freq(sim, left, right, output_path, title, db)

    if sim._mode in _TIME_MODES:
        return _plot_time(sim, left, right, output_path, title)

    raise ValueError(f"Unsupported simulation mode: {sim._mode!r}")


# ── internal helpers ──────────────────────────────────────────────────────────

def _get_y(data, db: bool):
    return 20 * np.log10(np.abs(data) + 1e-300) if db else data.real


def _case_colors(n: int):
    """Return a list of n colours from viridis, or the fixed palette for n==1."""
    if n == 1:
        return None  # caller falls back to _COLORS_LEFT / _COLORS_RIGHT
    return plt.cm.viridis(np.linspace(0, 1, n))


def _draw(ax, sim, variables, db, colors, get_x):
    """Plot variables on ax for every simulation case.

    colors:  fixed palette (list) for single-trace; viridis array for multi-trace.
    get_x:   sim.get_time or sim.get_frequency (callable accepting a case index).
    """
    n = sim.case_count
    multi = n > 1
    for case in range(n):
        x = get_x(case)
        c = colors[case] if multi else None
        for j, var in enumerate(variables):
            data = sim.get_data(var, case)
            if data is None:
                continue
            color = c if multi else colors[j % len(colors)]
            ls = _LINESTYLES[j % len(_LINESTYLES)] if multi else "-"
            if multi:
                lbl = f"step {case}" if len(variables) == 1 else f"{var} (step {case})"
            else:
                lbl = var
            ax.plot(x, _get_y(data, db), label=lbl, color=color, linestyle=ls)


def _add_legend(ax, case_count):
    if case_count <= _LEGEND_CASE_LIMIT:
        ax.legend()


def _merged_legend(ax_left, ax_right, case_count, **kwargs):
    if case_count > _LEGEND_CASE_LIMIT:
        return
    h1, l1 = ax_left.get_legend_handles_labels()
    h2, l2 = ax_right.get_legend_handles_labels()
    ax_left.legend(h1 + h2, l1 + l2, **kwargs)


def _apply_grid(ax):
    ax.grid(True, which="both", alpha=0.3)


# ── time-domain ───────────────────────────────────────────────────────────────

def _ylabel(variables: list[str], db: bool) -> str:
    if db:
        return "Magnitude (dB)"
    if variables and all(v.strip().upper().startswith("I(") for v in variables):
        return "Current (A)"
    return "Voltage (V)"


def _plot_time(sim, left, right, output_path, title):
    n = sim.case_count
    colors_l = _case_colors(n) if n > 1 else _COLORS_LEFT
    colors_r = _case_colors(n) if n > 1 else _COLORS_RIGHT
    fig, ax = plt.subplots(figsize=(10, 6))

    if right:
        ax2 = ax.twinx()
        _draw(ax,  sim, left,  db=False, colors=colors_l, get_x=sim.get_time)
        _draw(ax2, sim, right, db=False, colors=colors_r, get_x=sim.get_time)
        ax.set_ylabel(_ylabel(left, False), color=_COLORS_LEFT[0])
        ax2.set_ylabel(_ylabel(right, False), color=_COLORS_RIGHT[0])
        _merged_legend(ax, ax2, n)
    else:
        _draw(ax, sim, left, db=False, colors=colors_l, get_x=sim.get_time)
        ax.set_ylabel(_ylabel(left, False))
        _add_legend(ax, n)

    ax.set_xlabel("Time (s)")
    _apply_grid(ax)
    if title:
        ax.set_title(title)
    return _save_or_show(fig, output_path)


# ── frequency-domain ──────────────────────────────────────────────────────────

def _plot_freq(sim, left, right, output_path, title, db):
    n = sim.case_count
    colors_l = _case_colors(n) if n > 1 else _COLORS_LEFT
    colors_r = _case_colors(n) if n > 1 else _COLORS_RIGHT
    fig, ax = plt.subplots(figsize=(10, 6))

    if right:
        ax2 = ax.twinx()
        _draw(ax,  sim, left,  db=db, colors=colors_l, get_x=sim.get_frequency)
        _draw(ax2, sim, right, db=db, colors=colors_r, get_x=sim.get_frequency)
        ax.set_ylabel(_ylabel(left, db), color=_COLORS_LEFT[0])
        ax2.set_ylabel(_ylabel(right, db), color=_COLORS_RIGHT[0])
        _merged_legend(ax, ax2, n)
    else:
        _draw(ax, sim, left, db=db, colors=colors_l, get_x=sim.get_frequency)
        ax.set_ylabel(_ylabel(left, db))
        _add_legend(ax, n)

    ax.set_xscale("log")
    ax.set_xlabel("Frequency (Hz)")
    _apply_grid(ax)
    if title:
        ax.set_title(title)
    return _save_or_show(fig, output_path)


# ── operating point ───────────────────────────────────────────────────────────

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


# ── transient by parameter ────────────────────────────────────────────────────

def plot_transient_by_param(
    raw_path: Path,
    variable: str,
    outer_values,
    inner_values,
    outer_label: str = "",
    inner_label: str = "",
    outer_unit: str = "",
    inner_unit: str = "",
    ncols: int = 4,
    title: str = "",
    output_path: Optional[Path] = None,
) -> plt.Figure:
    """One subplot per outer value; each subplot overlays one trace per inner value.

    Outer values each get their own panel, arranged in a grid of ncols columns.
    Inner values become coloured traces within each panel.  All panels share x
    and y axes for direct comparison.

    Case ordering follows LTspice convention: the LAST .step directive in the
    netlist is the outer (slower) loop.  Pass outer/inner to match that ordering,
    i.e. outer_values should correspond to the parameter whose .step appears last.
    case = inner_idx * n_outer + outer_idx.
    """
    sim = Ltspice(str(raw_path)).parse()

    n_outer = len(outer_values)
    n_inner = len(inner_values)
    nrows = (n_outer + ncols - 1) // ncols

    trace_colors = plt.cm.viridis(np.linspace(0, 1, n_inner))

    fig, axes = plt.subplots(
        nrows, ncols,
        figsize=(ncols * 3.0, nrows * 2.5),
        sharex=True,
        sharey=True,
        squeeze=False,
    )

    for idx, ov in enumerate(outer_values):
        row, col = divmod(idx, ncols)
        ax = axes[row, col]
        ax.set_title(f"{outer_label}{ov}{outer_unit}", fontsize=8)
        ax.tick_params(labelsize=7)

        for j, iv in enumerate(inner_values):
            case = j * n_outer + idx
            if case >= sim.case_count:
                continue
            t = sim.get_time(case)
            v = sim.get_data(variable, case)
            if v is None:
                continue
            ax.plot(t, np.asarray(v).real,
                    color=trace_colors[j],
                    linewidth=0.9,
                    label=f"{inner_label}{iv}{inner_unit}")

    # Hide unused subplots in the last row
    for idx in range(n_outer, nrows * ncols):
        row, col = divmod(idx, ncols)
        axes[row, col].set_visible(False)

    # x-axis label on bottom-row visible panels only
    for col in range(ncols):
        last_visible_row = max(
            (r for r in range(nrows) if r * ncols + col < n_outer), default=None
        )
        if last_visible_row is not None:
            axes[last_visible_row, col].set_xlabel("Time (s)", fontsize=7)

    # Shared legend from the first subplot
    handles, labels = axes[0, 0].get_legend_handles_labels()
    if handles:
        fig.legend(handles, labels, loc="lower center",
                   ncol=min(n_inner, 8), fontsize=7,
                   bbox_to_anchor=(0.5, -0.02))

    if title:
        fig.suptitle(title, fontsize=10)

    fig.tight_layout()
    return _save_or_show(fig, output_path)


# ── endpoint-vs-parameter ─────────────────────────────────────────────────────

def plot_endpoint_vs_param(
    raw_path: Path,
    variable: str,
    outer_values,
    inner_values,
    x_axis: str = "inner",
    x_label: str = "",
    trace_label: str = "",
    trace_unit: str = "",
    tail_frac: float = 0.2,
    title: str = "",
    output_path: Optional[Path] = None,
) -> plt.Figure:
    """Plot the settled endpoint of `variable` against one sweep parameter.

    Expects a stepped raw file from two nested .step directives.  LTspice runs
    the LAST .step as the outer (slower) loop: case = inner_idx * n_outer + outer_idx.

    x_axis="inner"  → x-axis is the inner (faster) parameter, one trace per
                       outer (slower) value.
    x_axis="outer"  → x-axis is the outer parameter, one trace per inner value.

    The endpoint is the mean of the final `tail_frac` of each transient.
    """
    sim = Ltspice(str(raw_path)).parse()

    n_outer = len(outer_values)
    n_inner = len(inner_values)

    # Build a 2-D array of endpoint values [n_outer, n_inner]
    endpoints = np.full((n_outer, n_inner), float("nan"))
    for oi in range(n_outer):
        for ii in range(n_inner):
            case = ii * n_outer + oi
            if case >= sim.case_count:
                continue
            t = sim.get_time(case)
            v = sim.get_data(variable, case)
            if v is None:
                continue
            v = np.asarray(v).real
            mask = t >= t[-1] * (1.0 - tail_frac)
            if mask.any():
                endpoints[oi, ii] = np.mean(v[mask])

    if x_axis == "inner":
        x_vals    = list(inner_values)
        trace_vals = list(outer_values)
        rows = endpoints          # shape [n_traces, n_x]
    else:
        x_vals    = list(outer_values)
        trace_vals = list(inner_values)
        rows = endpoints.T        # transpose so rows index over trace_vals

    n_traces = len(trace_vals)
    colors = plt.cm.viridis(np.linspace(0, 1, n_traces))

    fig, ax = plt.subplots(figsize=(10, 6))
    for i, (tv, row) in enumerate(zip(trace_vals, rows)):
        ax.plot(x_vals, row, label=f"{trace_label}{tv}{trace_unit}", color=colors[i])

    ax.set_xlabel(x_label)
    ax.set_ylabel(_ylabel([variable], False))
    if title:
        ax.set_title(title)
    _apply_grid(ax)
    if n_traces <= _LEGEND_CASE_LIMIT:
        ax.legend(ncol=max(1, n_traces // 10), fontsize=8, loc="best")
    fig.tight_layout()
    return _save_or_show(fig, output_path)


# ── output ────────────────────────────────────────────────────────────────────

def _save_or_show(fig, output_path):
    if output_path:
        fig.savefig(output_path, dpi=150, bbox_inches="tight")
    else:
        plt.show()
    plt.close(fig)
    return fig
