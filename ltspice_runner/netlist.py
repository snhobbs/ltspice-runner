import os
import re
from pathlib import Path
from typing import Optional

# Number of nodes for each single-letter SPICE component prefix.
# X (subcircuit) is handled separately.
_NODE_COUNTS: dict[str, int] = {
    "c": 2,
    "d": 2,
    "e": 4,
    "f": 2,
    "g": 4,
    "h": 2,
    "i": 2,
    "j": 3,
    "k": 0,
    "l": 2,
    "m": 4,
    "q": 4,
    "r": 2,
    "s": 2,
    "t": 4,
    "v": 2,
    "w": 2,
    "z": 3,
}

SIMULATION_DIRECTIVES = frozenset(
    {
        ".tran",
        ".ac",
        ".dc",
        ".noise",
        ".op",
        ".step",
        ".tf",
        ".sens",
        ".four",
        ".fft",
        ".meas",
        ".measure",
        ".savebias",
        ".loadbias",
    }
)


class Netlist:
    def __init__(self, lines: list[str]):
        self.lines = lines

    @classmethod
    def from_file(cls, path: Path) -> "Netlist":
        # LTspice netlists use Latin-1 (µ, Ω, etc. are encoded as single bytes)
        with open(path, encoding="latin-1") as f:
            lines = f.read().splitlines()
        return cls(lines)

    def replace_libraries(self, lib_dir: Path) -> "Netlist":
        new_lines = []
        for line in self.lines:
            stripped = line.strip()
            if stripped.lower().startswith(".lib"):
                parts = stripped.split(None, 1)
                if len(parts) == 2:
                    resolved = _resolve_lib(parts[1].strip(), Path(lib_dir))
                    new_lines.append(f".lib {resolved}" if resolved else line)
                else:
                    new_lines.append(line)
            else:
                new_lines.append(line)
        return Netlist(new_lines)

    def remove_simulation_lines(self) -> "Netlist":
        new_lines = []
        for line in self.lines:
            tokens = line.strip().lower().split()
            if tokens and tokens[0] in SIMULATION_DIRECTIVES:
                continue
            new_lines.append(line)
        return Netlist(new_lines)

    def add_simulation(self, sim: "Simulation") -> "Netlist":
        new_lines = []
        inserted = False
        for line in self.lines:
            stripped = line.strip().lower()
            if not inserted and stripped in (".backanno", ".end"):
                new_lines.append(sim.to_net())
                inserted = True
            new_lines.append(line)
        if not inserted:
            new_lines.append(sim.to_net())
        return Netlist(new_lines)

    def _insert_before_end(self, directive: str) -> "Netlist":
        new_lines = []
        inserted = False
        for line in self.lines:
            stripped = line.strip().lower()
            if not inserted and stripped in (".backanno", ".end"):
                new_lines.append(directive)
                inserted = True
            new_lines.append(line)
        if not inserted:
            new_lines.append(directive)
        return Netlist(new_lines)

    def add_savebias(self, path: str) -> "Netlist":
        """Insert .savebias directive (saves OP including internal device states).

        path must be relative to this netlist's own directory (LTspice resolves
        .savebias/.loadbias paths relative to the netlist file, not the CWD).
        """
        return self._insert_before_end(f'.savebias "{path}" internal time=0')

    def add_loadbias(self, path: str) -> "Netlist":
        """Insert .loadbias directive to pre-load a saved operating point.

        path must be relative to this netlist's own directory.
        """
        return self._insert_before_end(f'.loadbias "{path}"')

    def add_save(self, *specs: str) -> "Netlist":
        """Insert a .save directive before .backanno/.end.

        Multiple specs are joined on one line: add_save("V(*)", "I(I1)")
        produces '.save V(*) I(I1)'.
        """
        return self._insert_before_end(".save " + " ".join(specs))

    def remove_params(self, *names: str) -> "Netlist":
        """Remove all .param lines for the given parameter names (case-insensitive)."""
        patterns = [
            re.compile(rf"(?i)^[ \t]*\.param[ \t]+{re.escape(n)}[ \t]*=")
            for n in names
        ]
        return Netlist([l for l in self.lines if not any(p.match(l) for p in patterns)])

    def set_source(self, source) -> "Netlist":
        """Replace a source component by name, or insert it after the title line.

        For Parameter sources: replaces the matching `.param name=...` line in-place,
        or inserts after the title if none exists.  Pre-existing .step lines are
        already stripped by remove_simulation_lines() before this is called.

        For VoltageSource / CurrentSource: replaces the component line by name.
        """
        name_lower = source.name.lower()
        new_lines = []
        replaced = False

        if not hasattr(source, "waveform"):
            # Parameter source — find the existing .param line and replace it.
            param_pat = re.compile(
                rf"(?i)^[ \t]*\.param[ \t]+{re.escape(name_lower)}[ \t]*="
            )
            for line in self.lines:
                if param_pat.match(line):
                    if not replaced:
                        new_lines.append(source.to_net())
                        replaced = True
                    # drop additional duplicate .param lines for this name
                else:
                    new_lines.append(line)
        else:
            for line in self.lines:
                tokens = line.split()
                if tokens and tokens[0].lower() == name_lower:
                    new_lines.append(source.to_net())
                    replaced = True
                else:
                    new_lines.append(line)

        if not replaced:
            new_lines = [self.lines[0], source.to_net()] + self.lines[1:]
        return Netlist(new_lines)

    def set_param(self, name: str, value: float) -> "Netlist":
        """Replace a .param value by name. Raises ValueError if not found."""
        pattern = re.compile(
            rf'(?i)^([ \t]*\.param[ \t]+{re.escape(name)}[ \t]*=[ \t]*)\S+'
        )
        new_lines = []
        found = False
        for line in self.lines:
            if pattern.match(line):
                new_lines.append(f".param {name}={value:.6g}")
                found = True
            else:
                new_lines.append(line)
        if not found:
            raise ValueError(f"Parameter '{name}' not found in netlist")
        return Netlist(new_lines)

    def nodes(self) -> list[str]:
        """Return a sorted list of unique node names found in the netlist."""
        seen: set[str] = set()
        for line in self.lines:
            stripped = line.strip()
            if not stripped or stripped[0] in ("*", ";", ".", "+"):
                continue
            for node in _component_nodes(stripped):
                seen.add(node)
        return sorted(seen, key=lambda n: (n != "0", n.lower()))

    def to_string(self) -> str:
        return "\n".join(self.lines)

    def write(self, path: Path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_string(), encoding="latin-1")


def _component_nodes(line: str) -> list[str]:
    """Return node names from a single component line."""
    tokens = line.split()
    if not tokens:
        return []
    prefix = tokens[0][0].lower()
    if prefix == "x":
        # Xname node1...nodeN subckt_model [key=val ...]
        # Strip key=value params; remaining tokens are [nodes..., model_name]
        non_params = [t for t in tokens[1:] if "=" not in t]
        return non_params[:-1]
    count = _NODE_COUNTS.get(prefix, 0)
    return tokens[1 : 1 + count]


def _normalize_parts(path_str: str) -> list[str]:
    normalized = path_str.replace("\\", "/")
    # Strip Windows drive letter
    if len(normalized) >= 2 and normalized[1] == ":":
        normalized = normalized[2:]
    return [p for p in normalized.split("/") if p]


def _resolve_lib(lib_path: str, lib_dir: Path) -> Optional[Path]:
    """Find lib_path under lib_dir by matching the longest suffix of lib_path."""
    parts = _normalize_parts(lib_path)
    # Try from most-specific (full path) to least-specific (filename only)
    for i in range(len(parts)):
        candidate = lib_dir.joinpath(*parts[i:])
        if candidate.exists():
            return candidate
    return None
