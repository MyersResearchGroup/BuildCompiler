import sys


def test_core_imports_do_not_load_optional_automation_dependencies():
    import buildcompiler
    from buildcompiler.adapters.pudu import (
        assembly_route_to_pudu_json,
        plating_to_pudu_json,
        transformation_to_pudu_json,
    )
    from buildcompiler.api import BuildCompiler, BuildOptions
    from buildcompiler import (
        BuildCompiler as RootBuildCompiler,
        assembly_lvl1,
        assembly_lvl2,
        domestication,
        full_build,
        transformation,
    )
    from buildcompiler.execution import FullBuildExecutor
    from buildcompiler.reporting import BuildGraph, BuildReport, BuildSummary

    assert buildcompiler
    assert BuildCompiler
    assert RootBuildCompiler is BuildCompiler
    assert BuildOptions
    assert full_build
    assert domestication
    assert assembly_lvl1
    assert assembly_lvl2
    assert transformation
    assert FullBuildExecutor
    assert BuildSummary
    assert BuildReport
    assert BuildGraph
    assert assembly_route_to_pudu_json
    assert transformation_to_pudu_json
    assert plating_to_pudu_json

    assert "pudupy" not in sys.modules
    assert "opentrons" not in sys.modules
    assert "SBOLInventory" not in sys.modules
