import importlib.util
import sys
from types import SimpleNamespace

import pytest

from buildcompiler.adapters.opentrons import (
    OpentronsSimulationAdapter,
    OptionalAutomationDependencyError,
    ProtocolSimulationError,
)
from buildcompiler.api import ProtocolOptions
from buildcompiler.adapters.opentrons import simulation


def test_opentrons_import_is_lazy():
    assert "opentrons" not in sys.modules


def test_simulate_false_does_not_import_opentrons():
    adapter = OpentronsSimulationAdapter()

    result = adapter.simulate("protocol.py", options=ProtocolOptions(simulate=False))

    assert result.ran is False
    assert "opentrons" not in sys.modules


def test_simulate_true_missing_dependency_raises(monkeypatch):
    adapter = OpentronsSimulationAdapter()
    real_find_spec = importlib.util.find_spec

    def fake_find_spec(name, *args, **kwargs):
        if name == "opentrons":
            return None
        return real_find_spec(name, *args, **kwargs)

    monkeypatch.setattr(importlib.util, "find_spec", fake_find_spec)
    with pytest.raises(OptionalAutomationDependencyError):
        adapter.simulate("protocol.py", options=ProtocolOptions(simulate=True))


def test_simulate_captures_evidence(monkeypatch, tmp_path):
    protocol = tmp_path / "protocol.py"
    protocol.write_text("from opentrons import protocol_api\n", encoding="utf-8")
    monkeypatch.setattr(importlib.util, "find_spec", lambda _: object())
    monkeypatch.setattr(
        simulation,
        "simulate_source",
        lambda source: SimpleNamespace(
            actions=[{"command": "test"}],
            simulator_version="8.8.2",
            stdout="ok\n",
            stderr="",
        ),
    )

    result = OpentronsSimulationAdapter().simulate(
        protocol, options=ProtocolOptions(simulate=True)
    )

    assert result.ran is True
    assert result.metadata["returncode"] == 0
    assert result.metadata["command_count"] == 1
    assert result.metadata["simulator_version"] == "8.8.2"
    assert "ok" in result.logs


def test_simulation_failure_is_not_reported_as_success(monkeypatch, tmp_path):
    protocol = tmp_path / "protocol.py"
    protocol.write_text("broken", encoding="utf-8")
    monkeypatch.setattr(importlib.util, "find_spec", lambda _: object())

    def fail(source):
        raise RuntimeError("Opentrons simulation failed with exit code 2: invalid")

    monkeypatch.setattr(simulation, "simulate_source", fail)

    with pytest.raises(ProtocolSimulationError, match="exit code 2"):
        OpentronsSimulationAdapter().simulate(
            protocol, options=ProtocolOptions(simulate=True)
        )
