import pytest

pytestmark = pytest.mark.automation


def test_opentrons_simulation_manual_only():
    pytest.skip("Manual/optional automation validation only. TODO(#67): wire real simulation checks in automation environment.")
