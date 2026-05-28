"""
Optimize feedback resistor and compensation cap of a noninverting op-amp.

The netlist must define (as LTspice .param directives):
    .param Rf=10k    ; feedback resistor
    .param Cf=100p   ; compensation cap in parallel with Rf

Minimises 20-80% rise time subject to an overshoot penalty.
"""
from pathlib import Path

import numpy as np
import pulse_transitions as pt
from ltspice import Ltspice

from ltspice_runner import Netlist, Pulse, SimulationCase, Transient, VoltageSource
from ltspice_runner.optimizer import Param, optimize
from ltspice_runner.runner import DEFAULT_LTSPICE, export_netlist

# ── Paths ─────────────────────────────────────────────────────────────────────

ASC = Path("noninverting-opamp.asc")
BUILD_DIR = Path("build/opt")
LIB_DIR = None


# ── Waveform metrics ──────────────────────────────────────────────────────────


def _load(raw_path: Path, node: str) -> tuple[np.ndarray, np.ndarray]:
    sim = Ltspice(str(raw_path)).parse()
    return sim.get_time(), sim.get_data(node).real


def rise_time_ns(t_s: np.ndarray, v: np.ndarray,
                 thresholds: tuple[float, float] = (0.2, 0.8)) -> float:
    """20-80% (or custom) rise time in nanoseconds. Returns inf on failure."""
    result = pt.calculate_risetime(t_s * 1e9, v, fractional_thresholds=thresholds)
    return float(result[0]) if result is not None else float("inf")


def overshoot_pct(v: np.ndarray, n_settle: int = 100) -> float:
    """Overshoot as % of total swing, measured after settling."""
    v_lo = float(np.median(v[:20]))
    v_hi = float(np.median(v[-n_settle:]))
    swing = v_hi - v_lo
    if abs(swing) < 1e-9:
        return 0.0
    return max(0.0, (v.max() - v_hi) / swing * 100.0)


def pulse_tilt_pct(v: np.ndarray, settled_slice: slice) -> float:
    """Droop across the top of the pulse as % of swing.

    A positive value means the output droops during the flat portion.
    """
    top = v[settled_slice]
    v_lo = float(np.median(v[:20]))
    v_hi = float(np.median(top))
    swing = v_hi - v_lo
    if abs(swing) < 1e-9:
        return 0.0
    return (float(top[0]) - float(top[-1])) / swing * 100.0


def flatness_pct(v: np.ndarray, settled_slice: slice) -> float:
    """Peak-to-peak ripple in the settled region as % of swing."""
    top = v[settled_slice]
    v_lo = float(np.median(v[:20]))
    v_hi = float(np.median(top))
    swing = v_hi - v_lo
    if abs(swing) < 1e-9:
        return 0.0
    return float(top.ptp()) / swing * 100.0


# ── Cost function ─────────────────────────────────────────────────────────────

OVERSHOOT_LIMIT_PCT = 5.0   # penalise above this
OVERSHOOT_WEIGHT    = 10.0  # ns-equivalent cost per % overshoot above limit


def cost_fn(raw_path: Path) -> float:
    t, v = _load(raw_path, "V(OUT)")

    rt = rise_time_ns(t, v)
    if not np.isfinite(rt):
        return 1e6

    over = overshoot_pct(v)
    penalty = max(0.0, over - OVERSHOOT_LIMIT_PCT) * OVERSHOOT_WEIGHT

    return rt + penalty


# ── Parameters to optimise ────────────────────────────────────────────────────

PARAMS = [
    Param("Rf", bounds=(1e3, 100e3), initial=10e3),
    Param("Cf", bounds=(1e-12, 10e-9), initial=100e-12),
]

# ── Simulation case ───────────────────────────────────────────────────────────

SIM_CASE = SimulationCase(
    VoltageSource(
        "VIN", "IN", "0",
        Pulse("0", "1", rise="1n", fall="1n", width="500u", period="1m"),
    ),
    Transient("1m", step_ceiling="1n"),
    label="step_opt",
)

# ── Run ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    net_path = export_netlist(ASC, build_dir=BUILD_DIR)
    netlist = Netlist.from_file(net_path)

    result = optimize(
        netlist=netlist,
        params=PARAMS,
        sim_case=SIM_CASE,
        cost_fn=cost_fn,
        build_dir=BUILD_DIR,
        method="differential_evolution",
        maxiter=40,
        popsize=8,
        seed=42,
        tol=0.01,
        workers=1,          # set to -1 to use all cores (requires cost_fn to be picklable)
    )

    print("\n── Result ──────────────────────────────────────────")
    print(f"  Converged : {result.success}")
    print(f"  Iterations: {result.nit}  /  Evaluations: {result.nfev}")
    print(f"  Final cost: {result.fun:.4g} ns-equivalent")
    print()
    for p, val in zip(PARAMS, result.x):
        print(f"  {p.name:10s} = {val:.4g}")

    # Final evaluation with diagnostics
    print("\n── Final waveform metrics ──────────────────────────")
    net_path = BUILD_DIR / "opt_final.net"
    from ltspice_runner.netlist import Netlist as _N
    patched = netlist.remove_simulation_lines()
    for p, val in zip(PARAMS, result.x):
        patched = patched.set_param(p.name, val)
    net = patched.set_source(SIM_CASE.source).add_simulation(SIM_CASE.simulation)
    net.write(net_path)
    from ltspice_runner.runner import run_ltspice
    raw = run_ltspice(net_path)
    t, v = _load(raw, "V(OUT)")
    settled = slice(len(v) // 2, 3 * len(v) // 4)
    print(f"  Rise time  (20-80%): {rise_time_ns(t, v):.2f} ns")
    print(f"  Overshoot          : {overshoot_pct(v):.2f} %")
    print(f"  Pulse tilt         : {pulse_tilt_pct(v, settled):.2f} %")
    print(f"  Flatness (pk-pk)   : {flatness_pct(v, settled):.2f} %")
