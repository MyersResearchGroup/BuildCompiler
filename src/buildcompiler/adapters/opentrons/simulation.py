"""Optional Opentrons simulation boundary adapter."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import shutil
import subprocess

from buildcompiler.api import ProtocolOptions


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

        executable = shutil.which("opentrons_simulate")
        if executable is None:
            raise OptionalAutomationDependencyError(
                "Install synbio-buildcompiler[automation] and ensure "
                "opentrons_simulate is on PATH."
            )

        source = Path(protocol_source)
        if not source.is_file():
            raise FileNotFoundError(f"Protocol source does not exist: {source}")
        completed = subprocess.run(
            [executable, source.name],
            check=False,
            capture_output=True,
            cwd=source.parent,
            text=True,
        )
        logs = [line for line in (completed.stdout, completed.stderr) if line]
        if completed.returncode:
            raise ProtocolSimulationError(
                f"Opentrons simulation failed with exit code {completed.returncode}: "
                + "\n".join(logs)
            )

        return SimulationResult(
            ran=True,
            logs=logs,
            metadata={
                "protocol_source": str(source),
                "command": [executable, source.name],
                "returncode": completed.returncode,
            },
        )
