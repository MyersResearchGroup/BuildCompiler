import builtins
import sys

import pytest

from buildcompiler.adapters.opentrons import (
    OpentronsSimulationAdapter,
    OptionalAutomationDependencyError,
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

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "opentrons":
            raise ImportError("forced missing dependency")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    with pytest.raises(OptionalAutomationDependencyError):
        adapter.simulate("protocol.py", options=ProtocolOptions(simulate=True))
