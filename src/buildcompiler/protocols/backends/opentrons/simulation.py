"""Run the real simulator in an isolated process and temporary working directory."""

import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path


class SimulationError(RuntimeError):
    """The actual simulator failed or did not produce a trace."""


@dataclass(frozen=True, slots=True, kw_only=True)
class SimulationResult:
    simulator_version: str
    actions: tuple[dict, ...]
    sdk_calls: tuple[dict, ...]
    generated_json: dict[str, object]
    stdout: str
    stderr: str


def simulate_source(
    source: str,
    *,
    python: str | Path = sys.executable,
    python_paths: tuple[str | Path, ...] = (),
    timeout: float = 120,
) -> SimulationResult:
    """Simulate explicitly supplied source; never called during compilation.

    Source must be trusted just like any Python protocol. Process isolation
    prevents SDK state and PUDU's simulation file writes leaking between runs;
    it is not a security sandbox for arbitrary Python.
    """
    worker = Path(__file__).with_name("_simulation_worker.py")
    with tempfile.TemporaryDirectory(prefix="buildcompiler-simulation-") as temporary:
        directory = Path(temporary)
        (directory / "protocol.py").write_text(source, encoding="utf-8")
        environment = os.environ.copy()
        environment["OT_API_CONFIG_DIR"] = str(directory / "config")
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        if python_paths:
            environment["PYTHONPATH"] = os.pathsep.join(
                str(Path(p).resolve()) for p in python_paths
            )
        try:
            process = subprocess.run(
                [str(python), str(worker)],
                cwd=directory,
                env=environment,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise SimulationError(f"Could not run Opentrons simulator: {exc}") from exc
        result_path = directory / "trace.json"
        if process.returncode or not result_path.exists():
            raise SimulationError(
                f"Opentrons simulation failed ({process.returncode}):\n{process.stderr}\n{process.stdout}"
            )
        data = json.loads(result_path.read_text(encoding="utf-8"))
        generated = {
            path.name: json.loads(path.read_text(encoding="utf-8"))
            for path in directory.glob("*.json")
            if path.name != "trace.json"
        }
        return SimulationResult(
            simulator_version=data["simulator_version"],
            actions=tuple(data["actions"]),
            sdk_calls=tuple(data["sdk_calls"]),
            generated_json=generated,
            stdout=process.stdout,
            stderr=process.stderr,
        )
