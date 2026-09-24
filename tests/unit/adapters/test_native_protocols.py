import json

import pytest

from buildcompiler.adapters.native_protocols import compile_plating_payload


def test_legacy_plating_overrides_are_explicit_and_use_native_compilation():
    compiled = compile_plating_payload(
        {"bacterium_locations": {"A2": "strain"}, "replicates": 2},
        advanced_params={"replicates": 1, "number_dilutions": 1},
    )
    assert len(compiled.manifest.samples) == 1
    assert "from pudu" not in compiled.script
    assert ".distribute(" in compiled.script
    resolved = json.loads(
        next(
            a.content
            for a in compiled.artifacts.artifacts
            if a.name == "compilation.json"
        )
    )
    assert resolved["configuration"]["replicates"] == 1


def test_unsupported_legacy_parameters_fail_instead_of_being_ignored():
    with pytest.raises(ValueError, match="Unsupported native plating parameters"):
        compile_plating_payload(
            {"bacterium_locations": {"A1": "strain"}}, advanced_params={"unknown": 1}
        )
