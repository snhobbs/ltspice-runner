import shlex
import subprocess
from pathlib import Path
from typing import Optional

from .netlist import Netlist
from .simulation import Simulation

DEFAULT_LTSPICE = (
    r"wine /home/simon/.wine/drive_c/Program\ Files/LTC/LTspiceXVII/XVIIx64.exe"
)


def run_simulations(
    netlist: Netlist,
    simulations: list[Simulation],
    build_dir: Path,
    lib_dir: Optional[Path] = None,
    ltspice_cmd: str = DEFAULT_LTSPICE,
) -> list[Path]:
    """Prepare netlist, run each simulation, return paths to output .raw files."""
    build_dir = Path(build_dir)
    build_dir.mkdir(parents=True, exist_ok=True)

    prepared = netlist.remove_simulation_lines()
    if lib_dir:
        prepared = prepared.replace_libraries(Path(lib_dir))

    raw_files = []
    for sim in simulations:
        net_path = build_dir / f"{sim.name}.net"
        prepared.add_simulation(sim).write(net_path)
        raw_files.append(run_ltspice(net_path, ltspice_cmd))

    return raw_files


def export_netlist(asc_path: Path, ltspice_cmd: str = DEFAULT_LTSPICE) -> Path:
    """Export a .net netlist from a .asc schematic, return the .net path."""
    asc_path = Path(asc_path)
    cmd = shlex.split(ltspice_cmd) + ["-netlist", asc_path.name]
    result = subprocess.run(cmd, cwd=asc_path.parent, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Netlist export failed for {asc_path.name}:\n{result.stderr}")
    return asc_path.with_suffix(".net")


def run_ltspice(netlist_path: Path, ltspice_cmd: str = DEFAULT_LTSPICE) -> Path:
    """Run LTspice on an already-written netlist file, return the .raw path."""
    cmd = shlex.split(ltspice_cmd) + ["-b", netlist_path.name]
    result = subprocess.run(cmd, cwd=netlist_path.parent, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"LTspice failed for {netlist_path.name}:\n{result.stderr}")
    return netlist_path.with_suffix(".raw")
