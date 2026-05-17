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

## CI/CD
