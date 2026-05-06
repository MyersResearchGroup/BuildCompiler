import sys


def test_core_imports_do_not_load_optional_automation_dependencies():
    import buildcompiler
    from buildcompiler.adapters.opentrons import OpentronsSimulationAdapter
    from buildcompiler.adapters.pudu import (
        plating_to_pudu_json,
        transformation_to_pudu_json,
    )
    from buildcompiler.api import BuildOptions

    assert buildcompiler
    assert BuildOptions
    assert OpentronsSimulationAdapter
    assert transformation_to_pudu_json
    assert plating_to_pudu_json

    assert "pudupy" not in sys.modules
    assert "opentrons" not in sys.modules
    assert "SBOLInventory" not in sys.modules
