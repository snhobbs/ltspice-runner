from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np
from scipy.optimize import OptimizeResult, differential_evolution, minimize

from .netlist import Netlist
from .runner import DEFAULT_LTSPICE, run_ltspice
from .simulation import SimulationCase

logger = logging.getLogger(__name__)


@dataclass
class Param:
    name: str
    bounds: tuple[float, float]
    initial: float | None = None

    @property
    def x0(self) -> float:
        lo, hi = self.bounds
        return self.initial if self.initial is not None else (lo + hi) / 2


def optimize(
    netlist: Netlist,
    params: list[Param],
    sim_case: SimulationCase,
    cost_fn: Callable[[Path], float],
    build_dir: Path,
    method: str = "differential_evolution",
    ltspice_cmd: str = DEFAULT_LTSPICE,
    lib_dir: Path | None = None,
    **scipy_kwargs,
) -> OptimizeResult:
    """Run scipy optimization over LTspice .param values.

    cost_fn receives the path to the .raw file and returns a scalar cost.
    method is passed to scipy — "differential_evolution" for global search,
    or any scipy.optimize.minimize method (e.g. "Nelder-Mead") for local.
    Extra kwargs are forwarded to the scipy function.
    """
    build_dir = Path(build_dir)
    build_dir.mkdir(parents=True, exist_ok=True)

    base = netlist.remove_simulation_lines()
    if lib_dir:
        base = base.replace_libraries(lib_dir)

    names = [p.name for p in params]
    iteration = [0]

    def _objective(x: np.ndarray) -> float:
        iteration[0] += 1
        patched = base
        for name, value in zip(names, x):
            patched = patched.set_param(name, value)
        net = patched.set_source(sim_case.source).add_simulation(sim_case.simulation)
        net_path = build_dir / f"opt_{iteration[0]:04d}_{sim_case.label}.net"
        net.write(net_path)
        try:
            raw_path = run_ltspice(net_path, ltspice_cmd)
            cost = cost_fn(raw_path)
        except Exception as e:
            logger.warning("iter %d failed: %s", iteration[0], e)
            cost = 1e9
        logger.info(
            "iter %d  %s  cost=%.4g",
            iteration[0],
            "  ".join(f"{n}={v:.4g}" for n, v in zip(names, x)),
            cost,
        )
        return cost

    bounds = [p.bounds for p in params]

    if method == "differential_evolution":
        return differential_evolution(_objective, bounds, **scipy_kwargs)

    x0 = np.array([p.x0 for p in params])
    return minimize(_objective, x0, method=method, bounds=bounds, **scipy_kwargs)
