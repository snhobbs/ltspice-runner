import logging
import os
from pathlib import Path

import click

from .netlist import Netlist
from .plotter import plot_raw
from .runner import DEFAULT_LTSPICE, export_netlist, run_ltspice, run_simulations
from .simulation import AC, DC, Noise, OperatingPoint, Transient


@click.group()
@click.option("--debug", is_flag=True, default=False, help="Enable debug logging.")
@click.pass_context
def cli(ctx, debug):
    """LTspice simulation runner."""
    logging.basicConfig(
        level=logging.DEBUG if debug else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("matplotlib").setLevel(logging.ERROR)


@cli.command()
@click.argument("netlist", type=click.Path(exists=True, path_type=Path))
@click.option("--build-dir", "-b", default="build", type=click.Path(path_type=Path), show_default=True)
@click.option("--lib-dir", "-l", type=click.Path(exists=True, path_type=Path), help="Directory containing libraries")
@click.option("--ltspice", default=DEFAULT_LTSPICE, show_default=True, help="LTspice executable command")
@click.option("--tran", "tran_stop", metavar="STOP", help="Run transient sim with given stop time (e.g. 10u)")
@click.option("--ac", "ac_spec", metavar="START:STOP[:POINTS]", help="Run AC sim, e.g. 1:100meg or 1:100meg:200")
@click.option("--noise", "noise_spec", metavar="OUTPUT:SOURCE", help="Run noise sim, e.g. out:V1")
@click.option("--op", "run_op", is_flag=True, help="Run operating point")
@click.option("--dc", "dc_spec", metavar="SRC:START:STOP:STEP", help="Run DC sweep, e.g. V1:0:5:0.1")
def run(netlist, build_dir, lib_dir, ltspice, tran_stop, ac_spec, noise_spec, run_op, dc_spec):
    """Run simulations on a netlist and write outputs to BUILD_DIR."""
    simulations = []

    if tran_stop:
        simulations.append(Transient(stop_time=tran_stop))

    if ac_spec:
        parts = ac_spec.split(":")
        if len(parts) < 2:
            raise click.BadParameter("Expected START:STOP[:POINTS]", param_hint="--ac")
        kwargs = dict(start_freq=parts[0], stop_freq=parts[1])
        if len(parts) >= 3:
            kwargs["points"] = int(parts[2])
        simulations.append(AC(**kwargs))

    if noise_spec:
        parts = noise_spec.split(":", 1)
        if len(parts) != 2:
            raise click.BadParameter("Expected OUTPUT:SOURCE", param_hint="--noise")
        simulations.append(Noise(output=parts[0], source=parts[1]))

    if run_op:
        simulations.append(OperatingPoint())

    if dc_spec:
        parts = dc_spec.split(":")
        if len(parts) != 4:
            raise click.BadParameter("Expected SRC:START:STOP:STEP", param_hint="--dc")
        simulations.append(DC(source=parts[0], start=parts[1], stop=parts[2], step=parts[3]))

    if not simulations:
        raise click.UsageError("Specify at least one simulation: --tran, --ac, --noise, --op, or --dc")

    netlist = Path(netlist)
    if netlist.suffix.lower() == ".asc":
        netlist = export_netlist(netlist, ltspice_cmd=ltspice, build_dir=build_dir)

    net = Netlist.from_file(netlist)
    raw_files = run_simulations(net, simulations, build_dir, lib_dir, ltspice)
    for raw in raw_files:
        click.echo(str(raw))


@cli.command()
@click.argument("netlist", type=click.Path(exists=True, path_type=Path))
@click.option("--lib-dir", "-l", type=click.Path(exists=True, path_type=Path), help="Directory containing libraries")
@click.option("--output", "-o", type=click.Path(path_type=Path), help="Output file (default: stdout)")
def prepare(netlist, lib_dir, output):
    """Prepare a netlist: replace libraries and strip simulation commands."""
    net = Netlist.from_file(netlist)
    if lib_dir:
        net = net.replace_libraries(Path(lib_dir))
    net = net.remove_simulation_lines()
    result = net.to_string()
    if output:
        Path(output).write_text(result)
    else:
        click.echo(result)


@cli.command()
@click.argument("netlist", type=click.Path(exists=True, path_type=Path))
@click.option("--ltspice", default=DEFAULT_LTSPICE, show_default=True, help="LTspice executable command")
def batch(netlist, ltspice):
    """Run LTspice on a .net file as-is, using its own simulation directives."""
    raw_path = run_ltspice(Path(netlist), ltspice)
    click.echo(str(raw_path))


@cli.command("export")
@click.argument("schematic", type=click.Path(exists=True, path_type=Path))
@click.option("--build-dir", "-b", default="build", type=click.Path(path_type=Path), show_default=True)
@click.option("--ltspice", default=DEFAULT_LTSPICE, show_default=True, help="LTspice executable command")
def export_cmd(schematic, build_dir, ltspice):
    """Export a .asc schematic to a .net netlist in BUILD_DIR."""
    net_path = export_netlist(Path(schematic), ltspice_cmd=ltspice, build_dir=build_dir)
    click.echo(str(net_path))


@cli.command()
@click.argument("netlist", type=click.Path(exists=True, path_type=Path))
def nodes(netlist):
    """Print all node names found in a netlist, one per line."""
    net = Netlist.from_file(netlist)
    for node in net.nodes():
        click.echo(node)


@cli.command()
@click.argument("raw_file", type=click.Path(exists=True, path_type=Path))
@click.option("--variable", "-v", multiple=True, help="Variables to plot (default: all)")
@click.option("--output", "-o", type=click.Path(path_type=Path), help="Output image path")
@click.option("--db", is_flag=True, help="Plot AC magnitude in dB")
@click.option("--title", help="Plot title")
def plot(raw_file, variable, output, db, title):
    """Plot signals from an LTspice .raw file."""
    plot_raw(raw_file, list(variable) or None, output, title, db)


@cli.command()
@click.argument("schematic", type=click.Path(exists=True, path_type=Path))
@click.option("--output", "-o", type=click.Path(path_type=Path), help="Output SVG path (default: next to .asc)")
@click.option("--ltspice-lib", type=click.Path(path_type=Path), help="LTspice symbol library path")
@click.option("--stroke-width", default=2.0, show_default=True)
@click.option("--font-size", default=16.0, show_default=True)
@click.option("--margin", default=10.0, show_default=True)
@click.option("--font-family", default="Arial", show_default=True)
@click.option("--no-text", is_flag=True, help="Suppress all text rendering")
@click.option("--no-comments", is_flag=True, help="Suppress schematic comments")
@click.option("--no-directives", is_flag=True, help="Suppress SPICE directives")
@click.option("--no-values", is_flag=True, help="Suppress component values")
@click.option("--no-names", is_flag=True, help="Suppress component names")
def svg(schematic, output, ltspice_lib, stroke_width, font_size, margin, font_family,
        no_text, no_comments, no_directives, no_values, no_names):
    """Convert a .asc schematic to SVG."""
    from ltspice_to_svg.ltspice_to_svg import get_ltspice_lib_path
    from ltspice_to_svg.parsers.schematic_parser import SchematicParser
    from ltspice_to_svg.renderers.rendering_config import RenderingConfig
    from ltspice_to_svg.renderers.svg_renderer import SVGRenderer

    if ltspice_lib:
        os.environ["LTSPICE_LIB_PATH"] = str(ltspice_lib)
    elif "LTSPICE_LIB_PATH" not in os.environ:
        os.environ["LTSPICE_LIB_PATH"] = get_ltspice_lib_path()

    schematic = Path(schematic)
    svg_path = Path(output) if output else schematic.with_suffix(".svg")

    data = SchematicParser(str(schematic)).parse()

    config = RenderingConfig(
        stroke_width=stroke_width,
        base_font_size=font_size,
        viewbox_margin=margin,
        font_family=font_family,
        no_schematic_comment=no_text or no_comments,
        no_spice_directive=no_text or no_directives,
        no_component_value=no_text or no_values,
        no_component_name=no_text or no_names,
    )
    renderer = SVGRenderer(config)
    renderer.load_schematic(data["schematic"], data["symbols"])
    renderer.create_drawing(str(svg_path))
    renderer.render_wires()
    renderer.render_symbols()
    if not no_text:
        renderer.render_texts()
    renderer.render_shapes()
    renderer.render_flags()
    renderer.save()
    click.echo(str(svg_path))
