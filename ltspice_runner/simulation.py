from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .sources import VoltageSource, CurrentSource, Parameter


class Simulation:
    def to_net(self) -> str:
        raise NotImplementedError

    @property
    def name(self) -> str:
        return type(self).__name__.lower()


@dataclass
class Transient(Simulation):
    stop_time: str
    step_ceiling: Optional[str] = None
    start_time: str = "0"
    startup: bool = False

    @property
    def name(self) -> str:
        return f"tran_{self.stop_time}"

    def to_net(self) -> str:
        parts = [".tran"]
        if self.step_ceiling:
            parts.extend([self.step_ceiling, self.stop_time])
        else:
            parts.append(self.stop_time)
        if self.start_time != "0":
            parts.append(self.start_time)
        if self.startup:
            parts.append("startup")
        return " ".join(parts)


@dataclass
class AC(Simulation):
    sweep: str = "dec"
    points: int = 200
    start_freq: str = "1"
    stop_freq: str = "100meg"

    @property
    def name(self) -> str:
        return f"ac_{self.start_freq}_{self.stop_freq}"

    def to_net(self) -> str:
        return f".ac {self.sweep} {self.points} {self.start_freq} {self.stop_freq}"


@dataclass
class Noise(Simulation):
    output: str
    source: str
    sweep: str = "dec"
    points: int = 500
    start_freq: str = "10m"
    stop_freq: str = "100meg"

    @property
    def name(self) -> str:
        return f"noise_{self.start_freq}_{self.stop_freq}"

    def to_net(self) -> str:
        return (
            f".noise v({self.output}) {self.source} "
            f"{self.sweep} {self.points} {self.start_freq} {self.stop_freq}"
        )


@dataclass
class OperatingPoint(Simulation):
    @property
    def name(self) -> str:
        return "op"

    def to_net(self) -> str:
        return ".op"


@dataclass
class DC(Simulation):
    source: str
    start: str
    stop: str
    step: str

    @property
    def name(self) -> str:
        return f"dc_{self.source}"

    def to_net(self) -> str:
        return f".dc {self.source} {self.start} {self.stop} {self.step}"


@dataclass
class ParameterValue(Simulation):
    """Wrap any simulation with a single fixed .param override."""

    param: str
    value: str
    inner: "Simulation"

    @property
    def name(self) -> str:
        return f"{self.param}_{self.value}_{self.inner.name}"

    def to_net(self) -> str:
        return f".param {self.param}={self.value}\n{self.inner.to_net()}"


@dataclass
class ParameterStep(Simulation):
    """Wrap any simulation with a .step param sweep.

    Three sweep forms:
      Linear:  start, stop, increment (default when values and sweep are empty)
      List:    values=["1k", "4.7k", "10k"]
      Log:     sweep="oct" or "dec", points=<n>, start, stop
    """

    param: str
    inner: "Simulation"
    start: str = ""
    stop: str = ""
    increment: str = ""
    values: list = field(default_factory=list)
    sweep: str = ""
    points: int = 0

    @property
    def name(self) -> str:
        return f"step_{self.param}_{self.inner.name}"

    def to_net(self) -> str:
        if self.values:
            step_line = f".step param {self.param} list {' '.join(self.values)}"
        elif self.sweep:
            step_line = f".step param {self.param} {self.sweep} {self.points} {self.start} {self.stop}"
        else:
            step_line = f".step param {self.param} {self.start} {self.stop} {self.increment}"
        return f"{step_line}\n{self.inner.to_net()}"


@dataclass
class SimulationCase:
    """A stimulus source paired with the analysis to run against it."""

    source: VoltageSource | CurrentSource | Parameter
    simulation: Simulation
    label: str = field(default="")

    def __post_init__(self):
        if not self.label:
            self.label = self.simulation.name
