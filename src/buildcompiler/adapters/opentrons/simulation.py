"""Optional Opentrons simulation boundary adapter."""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass, field
from pathlib import Path

from buildcompiler.api.options import ProtocolOptions
from buildcompiler.protocols.backends.opentrons.simulation import simulate_source


class OptionalAutomationDependencyError(ImportError):
    """Raised when optional automation dependency is unavailable."""


class ProtocolSimulationError(RuntimeError):
    """Raised when Opentrons rejects a generated protocol."""


@dataclass
class SimulationResult:
    ran: bool
    logs: list[str] = field(default_factory=list)
    metadata: dict[str, object] = field(default_factory=dict)


class OpentronsSimulationAdapter:
    def simulate(
        self, protocol_source: str | Path, *, options: ProtocolOptions
    ) -> SimulationResult:
        if not options.simulate:
            return SimulationResult(
                ran=False,
                logs=["Simulation skipped: ProtocolOptions.simulate is False."],
                metadata={"protocol_source": str(protocol_source)},
            )

        if importlib.util.find_spec("opentrons") is None:
            raise OptionalAutomationDependencyError(
                "Install synbio-buildcompiler[simulation] in a Python 3.10 environment to use Opentrons simulation."
            )

        source = Path(protocol_source)
        if not source.is_file():
            raise FileNotFoundError(f"Protocol source does not exist: {source}")
        try:
            trace = simulate_source(source.read_text(encoding="utf-8"))
        except RuntimeError as exc:
            raise ProtocolSimulationError(str(exc)) from exc

        return SimulationResult(
            ran=True,
            logs=["Opentrons simulation completed.", *trace.stdout.splitlines()],
            metadata={
                "protocol_source": str(protocol_source),
                "simulator_version": trace.simulator_version,
                "returncode": 0,
                "command_count": len(trace.actions),
                "stderr": trace.stderr,
            },
        )
