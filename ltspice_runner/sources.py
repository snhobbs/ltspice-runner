from dataclasses import dataclass, field


class Waveform:
    def to_net(self) -> str:
        raise NotImplementedError

    def dc_value(self) -> str:
        """DC operating-point value of this waveform (used for bias matching)."""
        raise NotImplementedError


@dataclass
class Pulse(Waveform):
    initial: str
    pulsed: str
    delay: str = "0"
    rise: str = "1n"
    fall: str = "1n"
    width: str = "5u"
    period: str = "10u"

    def to_net(self) -> str:
        return (
            f"PULSE({self.initial} {self.pulsed} {self.delay}"
            f" {self.rise} {self.fall} {self.width} {self.period})"
        )

    def dc_value(self) -> str:
        return self.initial


@dataclass
class Sin(Waveform):
    amplitude: str
    freq: str
    offset: str = "0"
    delay: str = "0"
    damping: str = "0"
    phase: str = "0"

    def to_net(self) -> str:
        return f"SIN({self.offset} {self.amplitude} {self.freq} {self.delay} {self.damping} {self.phase})"

    def dc_value(self) -> str:
        return self.offset


@dataclass
class Exp(Waveform):
    initial: str
    pulsed: str
    rise_delay: str = "0"
    rise_tau: str = "1n"
    fall_delay: str = "0"
    fall_tau: str = "1n"

    def to_net(self) -> str:
        return (
            f"EXP({self.initial} {self.pulsed}"
            f" {self.rise_delay} {self.rise_tau} {self.fall_delay} {self.fall_tau})"
        )

    def dc_value(self) -> str:
        return self.initial


@dataclass
class PWL(Waveform):
    points: list[tuple[str, str]]

    def to_net(self) -> str:
        pairs = " ".join(f"{t} {v}" for t, v in self.points)
        return f"PWL({pairs})"

    def dc_value(self) -> str:
        return self.points[0][1] if self.points else "0"


@dataclass
class ACSource(Waveform):
    """AC specification for frequency-domain analysis. Produces: AC magnitude [phase]"""

    magnitude: str = "1"
    phase: str = "0"

    def to_net(self) -> str:
        return f"AC {self.magnitude} {self.phase}"

    def dc_value(self) -> str:
        return "0"


@dataclass
class Constant(Waveform):
    value: str

    def to_net(self) -> str:
        return self.value

    def dc_value(self) -> str:
        return self.value


@dataclass
class Parameter:
    name: str
    value: str

    def to_net(self) -> str:
        return f".param {self.name} = {self.value}"


@dataclass
class VoltageSource:
    name: str
    node_plus: str
    node_minus: str
    waveform: Waveform

    def to_net(self) -> str:
        return (
            f"{self.name} {self.node_plus} {self.node_minus} {self.waveform.to_net()}"
        )


@dataclass
class CurrentSource:
    name: str
    node_plus: str
    node_minus: str
    waveform: Waveform

    def to_net(self) -> str:
        return (
            f"{self.name} {self.node_plus} {self.node_minus} {self.waveform.to_net()}"
        )
