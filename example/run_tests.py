"""
Standard test suite runner.

Discovers all .net files in the example directory (or accepts explicit paths)
and runs five analyses on each: operating point, step response, noise,
DC sweep, and AC sweep.

Usage:
    uv run python example/run_tests.py [NETLIST ...] [options]

    uv run python example/run_tests.py --plot
    uv run python example/run_tests.py --skip-run
    uv run python example/run_tests.py MyCircuit.net --lib-dir ../lib
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from ltspice_runner import (
    AC,
    ACSource,
    Constant,
    DC,
    Netlist,
    Noise,
    OperatingPoint,
    Pulse,
    SimulationCase,
    Transient,
    VoltageSource,
    export_netlist,
    plot_raw,
    run_simulations,
)
from ltspice_runner.runner import DEFAULT_LTSPICE

import click

EXAMPLE_DIR = Path(__file__).parent


def opamp_suite(input_node="IN", output_node="OUT") -> list[SimulationCase]:
    """Five standard analyses for a voltage-input / voltage-output circuit."""
    return [
        SimulationCase(
            VoltageSource(
                f"V({input_node})",
                node_plus=input_node,
                node_minus="0",
                waveform=Constant("0"),
            ),
            OperatingPoint(),
        ),
        SimulationCase(
            VoltageSource(
                f"V({input_node})",
                node_plus=input_node,
                node_minus="0",
                waveform=Pulse(
                    initial="0",
                    pulsed="1",
                    rise="1n",
                    fall="1n",
                    width="500u",
                    period="1m",
                ),
            ),
            Transient("2m", step_ceiling="10n"),
            plot_vars=[f"V({input_node})", f"V({output_node})"],
        ),
        SimulationCase(
            VoltageSource(
                f"V({input_node})",
                node_plus=input_node,
                node_minus="0",
                waveform=Constant("0"),
            ),
            Noise(
                output=output_node,
                source=f"V({input_node})",
                points=100,
                start_freq="1",
                stop_freq="10meg",
            ),
            label="noise",
            plot_vars=[f"V({input_node})", f"V({output_node})", "gain"],
        ),
        SimulationCase(
            VoltageSource(
                f"V({input_node})",
                node_plus=input_node,
                node_minus="0",
                waveform=Constant("0"),
            ),
            DC(source=f"V({input_node})", start="-10", stop="10", step="10m"),
            plot_vars=[f"V({input_node})", f"V({output_node})"],
        ),
        SimulationCase(
            VoltageSource(
                f"V({input_node})",
                node_plus=input_node,
                node_minus="0",
                waveform=ACSource("1"),
            ),
            AC(points=200, start_freq="1", stop_freq="10meg"),
            plot_vars=[f"V({input_node})", f"V({output_node})", "gain"],
        ),
    ]


def resolve_sources(netlists, ltspice, skip_run) -> list[Path]:
    """Resolve and deduplicate netlist paths, exporting .asc files as needed."""
    seen = set()
    resolved = []
    for path in netlists:
        if path.suffix == ".asc":
            net = path.with_suffix(".net")
            if net.exists():
                path = net
            elif skip_run:
                click.echo(f"Skipping {path.name} (no .net file)")
                continue
            else:
                click.echo(f"Exporting netlist from {path.name}...")
                try:
                    path = export_netlist(path, ltspice)
                except RuntimeError as e:
                    click.echo(f"  ERROR: {e}", err=True)
                    continue
        if path.stem not in seen:
            seen.add(path.stem)
            resolved.append(path)
    return resolved


def run_all(
    paths, build_dir, lib_dir, ltspice, skip_run
) -> list[tuple[Path, list[SimulationCase], list[Path]]]:
    """Run the opamp suite on each netlist. Returns (netlist_path, suite, raw_files) tuples."""
    results = []
    for path in paths:
        click.echo(f"=== {path.stem} ===")
        base_net = Netlist.from_file(path)
        suite = opamp_suite()
        click.echo(f"  nodes: {', '.join(base_net.nodes())}")

        if skip_run:
            raw_files = [build_dir / path.stem / f"{case.label}.raw" for case in suite]
        else:
            try:
                raw_files = run_simulations(
                    base_net, suite, build_dir / path.stem, lib_dir, ltspice
                )
            except RuntimeError as e:
                click.echo(f"  ERROR: {e}", err=True)
                continue

        results.append((path, suite, raw_files))
    return results


def plot_all(results):
    """Plot results for all simulations across all netlists."""
    for path, suite, raw_files in results:
        for case, raw_path in zip(suite, raw_files):
            if raw_path.exists():
                plot_raw(
                    raw_path,
                    variables=case.plot_vars,
                    title=f"{path.stem} — {case.label.replace('_', ' ')}",
                    db=(case.label == "ac_sweep"),
                )


@click.command()
@click.argument("netlists", nargs=-1, type=click.Path(path_type=Path))
@click.option("--lib-dir", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--build-dir",
    type=click.Path(path_type=Path),
    default=EXAMPLE_DIR / "build",
    show_default=True,
)
@click.option(
    "--ltspice", default=os.environ.get("LTSPICE", DEFAULT_LTSPICE), show_default=True
)
@click.option("--plot", is_flag=True)
@click.option(
    "--plot-only", is_flag=True, help="Skip simulation and plot existing outputs."
)
@click.option("--skip-run", is_flag=True)
def main(netlists, lib_dir, build_dir, ltspice, plot, plot_only, skip_run):
    sources = list(netlists) or sorted(EXAMPLE_DIR.glob("*.net")) + sorted(
        EXAMPLE_DIR.glob("*.asc")
    )
    if not sources:
        raise click.ClickException("No .net or .asc files found.")

    if plot_only:
        skip_run = True
        plot = True

    paths = resolve_sources(sources, ltspice, skip_run)
    results = run_all(paths, build_dir, lib_dir, ltspice, skip_run)

    if plot:
        plot_all(results)


if __name__ == "__main__":
    main()
