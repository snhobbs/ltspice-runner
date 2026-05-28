import logging
import os
import shlex
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

from .netlist import Netlist
from .simulation import OperatingPoint, ParameterStep, ParameterValue, Simulation, SimulationCase
from .sources import CurrentSource


def _collect_sim_params(sim) -> list[str]:
    """Return parameter names for every ParameterStep/ParameterValue in the chain."""
    names: list[str] = []
    while isinstance(sim, (ParameterStep, ParameterValue)):
        names.append(sim.param)
        sim = sim.inner
    return names

DEFAULT_LTSPICE = (
    r"wine /home/simon/.wine/drive_c/Program\ Files/LTC/LTspiceXVII/XVIIx64.exe"
)


def run_simulations(
    netlist: Netlist,
    simulations: list[Simulation | SimulationCase],
    build_dir: Path,
    lib_dir: Optional[Path] = None,
    ltspice_cmd: str = DEFAULT_LTSPICE,
    saves: Optional[dict[str, list[str]]] = None,
) -> list[Path]:
    """Prepare netlist, run each simulation, return paths to output .raw files.

    saves: optional mapping of simulation label -> list of SPICE vars to save.
           When provided, only those variables are written to the .raw file.
           Falls back to V(*) for any label not in the dict.
    """
    build_dir = Path(build_dir)
    build_dir.mkdir(parents=True, exist_ok=True)

    prepared = netlist.remove_simulation_lines()
    if lib_dir:
        prepared = prepared.replace_libraries(Path(lib_dir))

    bias_path = build_dir / "op.op"
    bias_rel = "op.op"  # relative to netlist dir; LTspice resolves savebias/loadbias from there

    # Record the DC value of the OP source so we only load the bias for cases
    # that share the same DC operating point.
    op_items = [
        s
        for s in simulations
        if isinstance(s, SimulationCase) and isinstance(s.simulation, OperatingPoint)
    ]
    other_items = [s for s in simulations if s not in op_items]
    op_dc = op_items[0].source.waveform.dc_value() if op_items else None

    def _bias_matches(item: SimulationCase) -> bool:
        return (
            bias_path.exists()
            and op_dc is not None
            and item.source.waveform.dc_value() == op_dc
        )

    def _write_net(item) -> Path:
        if isinstance(item, SimulationCase):
            sim_params = _collect_sim_params(item.simulation)
            base = prepared.remove_params(*sim_params) if sim_params else prepared
            net = base.set_source(item.source).add_simulation(item.simulation)
            save_vars: list[str] = (saves or {}).get(item.label, ["V(*)"])
            if isinstance(item.source, CurrentSource):
                current_var = f"I({item.source.name})"
                if current_var not in save_vars:
                    save_vars = list(save_vars) + [current_var]
            net = net.add_save(*save_vars)
            if isinstance(item.simulation, OperatingPoint):
                net = net.add_savebias(bias_rel)
            elif _bias_matches(item):
                net = net.add_loadbias(bias_rel)
            net_path = build_dir / f"{item.label}.net"
        else:
            net = prepared.add_simulation(item)
            net_path = build_dir / f"{item.name}.net"
        net.write(net_path)
        return net_path

    raw_files: list[Path] = []
    for item in op_items:
        try:
            raw_files.append(run_ltspice(_write_net(item), ltspice_cmd))
        except RuntimeError as e:
            logger.error("  %s", e)

    def _run_one(item) -> Path:
        return run_ltspice(_write_net(item), ltspice_cmd)

    with ThreadPoolExecutor() as pool:
        futures = {pool.submit(_run_one, item): item for item in other_items}
        for future in as_completed(futures):
            try:
                raw_files.append(future.result())
            except RuntimeError as e:
                logger.error("  %s", e)

    return raw_files


def export_netlist(
    asc_path: Path,
    ltspice_cmd: str = DEFAULT_LTSPICE,
    build_dir: Optional[Path] = None,
) -> Path:
    """Export a .net netlist from a .asc schematic, return the .net path."""
    asc_path = Path(asc_path).resolve()
    if build_dir:
        Path(build_dir).mkdir(parents=True, exist_ok=True)

    cmd = shlex.split(ltspice_cmd) + ["-netlist", str(asc_path)]
    logger.info("%s", " ".join(cmd))
    subprocess.run(cmd, capture_output=True, text=True)

    # LTspice writes the .net alongside the .asc.
    net_path = asc_path.with_suffix(".net")
    if not net_path.exists():
        raise RuntimeError(
            f"Netlist export failed for {asc_path.name}: no .net produced"
        )
    return net_path


def run_ltspice(netlist_path: Path, ltspice_cmd: str = DEFAULT_LTSPICE) -> Path:
    """Run LTspice on an already-written netlist file, return the .raw path."""
    netlist_path = Path(netlist_path).resolve()
    cmd = shlex.split(ltspice_cmd) + ["-b", os.path.relpath(netlist_path)]
    logger.info("%s", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True)
    raw_path = netlist_path.with_suffix(".raw")
    # LTspice under Wine often returns non-zero even on success; treat a
    # missing .raw file as the definitive failure signal.
    if not raw_path.exists():
        detail = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(
            f"LTspice produced no .raw for {netlist_path.name}"
            + (f":\n{detail}" if detail else "")
        )
    return raw_path
