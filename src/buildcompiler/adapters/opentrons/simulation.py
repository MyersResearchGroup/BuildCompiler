"""Optional Opentrons simulation boundary adapter."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from buildcompiler.api import ProtocolOptions


class OptionalAutomationDependencyError(ImportError):
    """Raised when optional automation dependency is unavailable."""


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

        try:
            __import__("opentrons")
        except ImportError as exc:
            raise OptionalAutomationDependencyError(
                "Install synbio-buildcompiler[automation] to use Opentrons simulation."
            ) from exc

        return SimulationResult(
            ran=True,
            logs=["Simulation dependency check passed."],
            metadata={"protocol_source": str(protocol_source)},
        )
