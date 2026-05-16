# ltspice_runner

LTspice simulation runner. Prepares netlists, runs simulations, and plots results.

## Workflow

1. Load a netlist exported from LTspice.
2. Replace absolute library paths with local equivalents (longest-suffix match).
3. Strip the original simulation command.
4. Optionally replace voltage or current sources with a defined signal (pulse, sine, etc.). Only changed if explicitly set in the script.
5. Inject a simulation command from a class object and rename the netlist to match.
6. Run LTspice. Output `.raw` files have predictable names derived from the simulation.
7. Plot results using the ltspice library.

## Installation

```
uv pip install -e .
```

The local `ltspice` library at `ltspice_pytool/` is resolved automatically via `[tool.uv.sources]`.

## CLI

### Run simulations

```
ltspice-runner run circuit.net --tran 10u --ac 1:100meg --lib-dir ./lib --build-dir build
```

| Flag | Description |
|------|-------------|
| `--tran STOP` | Transient sim, e.g. `10u` |
| `--ac START:STOP[:POINTS]` | AC sweep, e.g. `1:100meg` or `1:100meg:200` |
| `--noise OUTPUT:SOURCE` | Noise sim, e.g. `out:V1` |
| `--op` | DC operating point |
| `--dc SRC:START:STOP:STEP` | DC sweep, e.g. `V1:0:5:0.1` |
| `--lib-dir DIR` | Directory to search for library files |
| `--build-dir DIR` | Output directory (default: `build`) |
| `--ltspice CMD` | LTspice command (default: wine path) |

### Prepare a netlist

Replaces library paths and strips simulation commands; writes the result to stdout or a file.

```
ltspice-runner prepare circuit.net --lib-dir ./lib
ltspice-runner prepare circuit.net --lib-dir ./lib --output circuit_prepared.net
```

### List nodes

```
ltspice-runner nodes circuit.net
```

Prints all node names found in the netlist, one per line, with `0` (ground) first.

### Plot a raw file

```
ltspice-runner plot build/tran_10u.raw
ltspice-runner plot build/ac_1_100meg.raw --db --output ac.png
ltspice-runner plot build/tran_10u.raw --variable V(out) --variable V(in)
```

## Library API

### Netlist

```python
from ltspice_runner import Netlist

net = Netlist.from_file("circuit.net")
net = net.replace_libraries(Path("./lib"))   # fix .lib paths
net = net.remove_simulation_lines()          # strip .tran / .ac / etc.
net = net.add_simulation(sim)                # inject simulation command
net = net.set_source(source)                 # replace or add a source component
nodes = net.nodes()                          # sorted list of node names
net.write(Path("build/circuit.net"))
```

### Simulations

```python
from ltspice_runner import Transient, AC, Noise, OperatingPoint, DC

Transient("10u")                             # .tran 10u
Transient("10u", step_ceiling="1n")          # .tran 1n 10u
AC()                                         # .ac dec 200 1 100meg
AC(sweep="lin", points=100, start_freq="10", stop_freq="1G")
Noise(output="out", source="I1")             # .noise v(out) I1 dec 500 10m 100meg
OperatingPoint()                             # .op
DC(source="V1", start="0", stop="5", step="0.1")  # .dc V1 0 5 0.1
```

Each simulation has a `name` property used as the output filename stem, e.g. `tran_10u`, `ac_1_100meg`.

### Source signals

Used with `Netlist.set_source()` to replace or add voltage/current source components. Only sources that are explicitly set are changed.

```python
from ltspice_runner import VoltageSource, CurrentSource, Pulse, Sin, Exp, PWL, Constant

# Waveforms
Pulse("0", "1", delay="0", rise="1n", fall="1n", width="5u", period="10u")
Sin("1m", "1k")                              # amplitude, frequency
Sin("1m", "1k", offset="0.5")
Exp("0", "1", rise_tau="10n", fall_tau="10n")
PWL([("0", "0"), ("1u", "1"), ("2u", "0")])
Constant("15")                               # DC value, e.g. for supply rails

# Source components
VoltageSource("V1", "in", "0", Pulse("0", "1"))
CurrentSource("I1", "sj", "N011", Sin("1u", "1k"))

# Change a supply rail
net = net.set_source(VoltageSource("V2", "VCC", "0", Constant("12")))

# Change a stimulus source
net = net.set_source(CurrentSource("I1", "sj", "N011", Pulse("0", "1u", width="5u", period="10u")))
```

### Running programmatically

```python
from pathlib import Path
from ltspice_runner import Netlist, Transient, AC, CurrentSource, Pulse, run_simulations

net = Netlist.from_file("example/circuit.net")
net = net.set_source(CurrentSource("I1", "sj", "N011", Pulse("0", "1u", width="5u", period="10u")))

simulations = [Transient("10u"), AC()]
raw_files = run_simulations(net, simulations, build_dir=Path("build"), lib_dir=Path("lib"))
```

### Plotting

```python
from ltspice_runner import plot_raw

plot_raw("build/ac_1_100meg.raw", db=True, title="Frequency Response")
plot_raw("build/tran_10u.raw", variables=["V(out)", "V(in)"], output_path=Path("tran.png"))
```

## Standard test patterns

### Step response

```python
net = net.set_source(VoltageSource("V1", "in", "0", Pulse("0", "1", rise="1n", width="50u", period="100u")))
simulations = [Transient("100u")]
```

### Noise

```python
net = net.set_source(CurrentSource("I1", "sj", "N011", Pulse("0", "1u", width="5u", period="10u")))
simulations = [Noise(output="out", source="I1")]
```

### AC sweep with sine stimulus

```python
net = net.set_source(VoltageSource("V1", "in", "0", Sin("1m", "1k")))
simulations = [AC()]
```

### DC operating point

```python
net = net.set_source(VoltageSource("V2", "VCC", "0", Constant("15")))
simulations = [OperatingPoint()]
```
