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

import argparse
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
    Transient,
    VoltageSource,
    export_netlist,
    plot_raw,
    run_ltspice,
)
from ltspice_runner.runner import DEFAULT_LTSPICE

EXAMPLE_DIR = Path(__file__).parent


def opamp_suite():
    """Five standard analyses for a voltage-input / voltage-output circuit."""
    return [
        (
            "operating_point",
            VoltageSource("VIN", "IN", "0", Constant("0")),
            OperatingPoint(),
        ),
        (
            "step_response",
            VoltageSource(
                "VIN",
                "IN",
                "0",
                Pulse(
                    initial="0",
                    pulsed="1",
                    rise="1n",
                    fall="1n",
                    width="500u",
                    period="1m",
                ),
            ),
            Transient("2m", step_ceiling="10n"),
        ),
        (
            "noise",
            VoltageSource("VIN", "IN", "0", Constant("0")),
            Noise(
                output="OUT",
                source="VIN",
                points=100,
                start_freq="1",
                stop_freq="10meg",
            ),
        ),
        (
            "dc_sweep",
            VoltageSource("VIN", "IN", "0", Constant("0")),
            DC(source="VIN", start="-10", stop="10", step="10m"),
        ),
        (
            "ac_sweep",
            VoltageSource("VIN", "IN", "0", ACSource("1")),
            AC(points=200, start_freq="1", stop_freq="10meg"),
        ),
    ]


def run_circuit(netlist_path, suite, args):
    print(f"=== {netlist_path.stem} ===")

    base_net = Netlist.from_file(netlist_path)
    base_net = base_net.remove_simulation_lines()
    if args.lib_dir:
        base_net = base_net.replace_libraries(args.lib_dir)

    print(f"  nodes: {', '.join(base_net.nodes())}")

    build_dir = args.build_dir / netlist_path.stem
    build_dir.mkdir(parents=True, exist_ok=True)

    for label, source, sim in suite:
        net = base_net.set_source(source).add_simulation(sim)
        net_path = build_dir / f"{label}.net"
        net.write(net_path)

        print(f"  [{label}]  {sim.to_net()}")

        raw_path = net_path.with_suffix(".raw")

        if not args.skip_run:
            try:
                run_ltspice(net_path, args.ltspice)
                print(f"    output: {raw_path}")
            except RuntimeError as e:
                print(f"    ERROR:  {e}")

        if args.plot and raw_path.exists():
            plot_raw(
                raw_path,
                variables=[f"V({source.node_plus})"] if sim.name != "op" else None,
                title=f"{netlist_path.stem} — {label.replace('_', ' ')}",
                db=(label == "ac_sweep"),
            )


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("netlists", nargs="*", type=Path)
    parser.add_argument("--lib-dir", type=Path, default=None)
    parser.add_argument("--build-dir", type=Path, default=EXAMPLE_DIR / "build")
    parser.add_argument("--ltspice", default=os.environ.get("LTSPICE", DEFAULT_LTSPICE))
    parser.add_argument("--plot", action="store_true")
    parser.add_argument("--skip-run", action="store_true")
    args = parser.parse_args()

    sources = args.netlists or (
        sorted(EXAMPLE_DIR.glob("*.net")) + sorted(EXAMPLE_DIR.glob("*.asc"))
    )
    if not sources:
        print("No .net or .asc files found.")
        sys.exit(1)

    seen = set()
    for path in sources:
        if path.suffix == ".asc":
            net = path.with_suffix(".net")
            if net.exists():
                path = net
            elif args.skip_run:
                print(
                    f"Skipping {path.name} (no .net file, use --skip-run only after exporting)"
                )
                continue
            else:
                print(f"Exporting netlist from {path.name}...")
                try:
                    path = export_netlist(path, args.ltspice)
                except RuntimeError as e:
                    print(f"  ERROR: {e}")
                    continue

        if path.stem in seen:
            continue
        seen.add(path.stem)

        suite = opamp_suite()
        run_circuit(path, suite, args)


if __name__ == "__main__":
    main()
