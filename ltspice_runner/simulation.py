from dataclasses import dataclass
from typing import Optional


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
