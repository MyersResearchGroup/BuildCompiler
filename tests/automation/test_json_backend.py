"""Negative controls for Protocol Engine equivalence and failure reporting."""

import copy
import json

import pytest

from buildcompiler.adapters.opentrons import OpentronsSimulationAdapter
from buildcompiler.api import ProtocolOptions
from buildcompiler.protocols import (
    ProtocolCompiler,
    TransformationConfig,
    assembly_request_from_json,
    transformation_request_from_json,
)
from buildcompiler.protocols.backends.simulation import SimulationError, analyze_source

from conftest import engine_actions

pytestmark = pytest.mark.automation


@pytest.fixture(scope="module")
def json_reference(pudu_repository):
    """Analyze one valid document once for the mutation tests."""
    request = assembly_request_from_json(
        [
            {
                "Product": "product",
                "Backbone": "backbone",
                "PartsList": ["part"],
                "Restriction Enzyme": "enzyme",
            }
        ],
        request_id="negative-controls",
    )
    compiled = ProtocolCompiler().compile(request, backend="opentrons_ot2_json")
    return json.loads(compiled.source), engine_actions(
        analyze_source(compiled.source, format="json")
    )


@pytest.mark.parametrize(
    "mutation", ["rate", "position", "tip", "temperature", "hardware"]
)
def test_engine_comparator_detects_behavior_changes(json_reference, mutation):
    document, original = json_reference
    changed = copy.deepcopy(document)
    kind = {
        "rate": "aspirate",
        "position": "aspirate",
        "tip": "pickUpTip",
        "temperature": "temperatureModule/setTargetTemperature",
        "hardware": "loadModule",
    }[mutation]
    params = next(c["params"] for c in changed["commands"] if c["commandType"] == kind)
    if mutation == "rate":
        params["flowRate"] *= 0.5
    elif mutation == "position":
        params["wellLocation"]["offset"]["z"] += 1
    elif mutation == "tip":
        params["wellName"] = "H12"
    elif mutation == "temperature":
        params["celsius"] += 1
    else:
        params["model"] = "temperatureModuleV2"
    analysis = analyze_source(json.dumps(changed), format="json")
    assert engine_actions(analysis) != original


def test_engine_rejects_invalid_json_execution(json_reference):
    document, _ = json_reference
    changed = copy.deepcopy(document)
    next(c["params"] for c in changed["commands"] if c["commandType"] == "aspirate")[
        "volume"
    ] = 1000
    with pytest.raises(SimulationError, match="analysis failed"):
        analyze_source(json.dumps(changed), format="json")


def test_simulation_adapter_accepts_json_protocol_files(json_reference, tmp_path):
    document, _ = json_reference
    path = tmp_path / "protocol.json"
    path.write_text(json.dumps(document))
    result = OpentronsSimulationAdapter().simulate(
        path, options=ProtocolOptions(simulate=True)
    )
    assert result.ran
    assert result.metadata["simulator_version"] == "8.8.2"
    assert result.metadata["command_count"] >= len(document["commands"])


def test_fractional_refills_match_the_python_sdk(pudu_repository):
    """Check the native backends where the reference's integer tube counter fails."""
    request = transformation_request_from_json(
        [{"Strain": "strain", "Chassis": "cell", "Plasmids": ["product"]}],
        request_id="fractional-refills",
    )
    compiler = ProtocolCompiler(
        transformation=TransformationConfig(
            replicates=31,
            tube_volume_competent_cell=500,
            transfer_volume_competent_cell=20 / 3,
            water_testing=True,
        )
    )
    python_protocol = compiler.compile(request)
    json_protocol = compiler.compile(request, backend="opentrons_ot2_json")
    expected = analyze_source(python_protocol.source)
    actual = analyze_source(json_protocol.source, format="json")
    assert engine_actions(actual) == engine_actions(expected)
