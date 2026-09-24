import sys
from subprocess import CompletedProcess

import pytest

from buildcompiler.adapters.opentrons import (
    OpentronsSimulationAdapter,
    OptionalAutomationDependencyError,
    ProtocolSimulationError,
)
from buildcompiler.api import ProtocolOptions


def test_opentrons_import_is_lazy():
    assert "opentrons" not in sys.modules


def test_simulate_false_does_not_import_opentrons():
    adapter = OpentronsSimulationAdapter()

    result = adapter.simulate("protocol.py", options=ProtocolOptions(simulate=False))

    assert result.ran is False
    assert "opentrons" not in sys.modules


def test_simulate_true_missing_dependency_raises(monkeypatch):
    adapter = OpentronsSimulationAdapter()
    monkeypatch.setattr("shutil.which", lambda _: None)
    with pytest.raises(OptionalAutomationDependencyError):
        adapter.simulate("protocol.py", options=ProtocolOptions(simulate=True))


def test_simulate_runs_cli_and_captures_evidence(monkeypatch, tmp_path):
    protocol = tmp_path / "protocol.py"
    protocol.write_text("from opentrons import protocol_api\n", encoding="utf-8")
    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/opentrons_simulate")
    monkeypatch.setattr(
        "subprocess.run",
        lambda *args, **kwargs: CompletedProcess(args[0], 0, "ok\n", ""),
    )

    result = OpentronsSimulationAdapter().simulate(
        protocol, options=ProtocolOptions(simulate=True)
    )

    assert result.ran is True
    assert result.metadata["returncode"] == 0
    assert result.metadata["command"][-1] == "protocol.py"
    assert result.logs == ["ok\n"]


def test_simulation_failure_is_not_reported_as_success(monkeypatch, tmp_path):
    protocol = tmp_path / "protocol.py"
    protocol.write_text("broken", encoding="utf-8")
    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/opentrons_simulate")
    monkeypatch.setattr(
        "subprocess.run",
        lambda *args, **kwargs: CompletedProcess(args[0], 2, "", "invalid\n"),
    )

    with pytest.raises(ProtocolSimulationError, match="exit code 2"):
        OpentronsSimulationAdapter().simulate(
            protocol, options=ProtocolOptions(simulate=True)
        )
