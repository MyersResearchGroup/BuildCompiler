"""Transformation acceptance covers mappings, grouping and both thermal paths."""

import json
from dataclasses import asdict

import pytest

from buildcompiler.protocols import (
    OpentronsTransformationProfile,
    ProtocolCompiler,
    TransformationConfig,
    plasmid_manifest_from_json,
    transformation_request_from_json,
)
from buildcompiler.protocols.backends.opentrons.simulation import simulate_source

pytestmark = pytest.mark.automation


def transformations(chassis=("chassis_a",), *, multiple_plasmids=False):
    return [
        {
            "Strain": f"https://example.org/strain_{i}/1",
            "Chassis": f"https://example.org/{cell}/1",
            "Plasmids": [f"https://example.org/plasmid_{i}/1"]
            + (["https://example.org/shared/1"] if multiple_plasmids else []),
        }
        for i, cell in enumerate(chassis)
    ]


def reference_script(payload, config, profile, locations=None):
    parameters = asdict(config)
    for name in (
        "cold_incubation1",
        "heat_shock",
        "cold_incubation2",
        "recovery_incubation",
    ):
        step = getattr(config, name)
        parameters[name] = {
            "temperature": step.celsius,
            "hold_time_minutes": step.minutes,
        }
    parameters.update(
        {name: value for name, value in asdict(profile).items() if name != "api_level"}
    )
    return (
        "from pudu.transformation import HeatShockTransformation\n"
        "metadata = {'apiLevel': '2.21', 'protocolName': 'PUDU reference'}\n"
        "def run(protocol):\n"
        f"    HeatShockTransformation(transformation_data={payload!r}, plasmid_locations={locations!r}, json_params={parameters!r}).run(protocol)\n"
    )


def force_thermal_path(source):
    # Still runs through opentrons.simulate.simulate; only the conditional changes.
    return (
        source.replace("def run(", "def _original_run(", 1)
        + "\ndef run(protocol):\n    protocol.is_simulating = lambda: False\n    _original_run(protocol)\n"
    )


@pytest.mark.parametrize(
    "payload,config,profile,locations,thermal",
    [
        (
            transformations(),
            TransformationConfig(),
            OpentronsTransformationProfile(),
            None,
            False,
        ),
        (
            transformations(
                ("chassis_b", "chassis_a", "chassis_b"), multiple_plasmids=True
            ),
            TransformationConfig(replicates=3, tube_volume_recovery_media=180),
            OpentronsTransformationProfile(),
            None,
            False,
        ),
        (
            transformations(),
            TransformationConfig(replicates=3),
            OpentronsTransformationProfile(
                thermocycler_starting_well=9,
                initial_tip_p20="E3",
                initial_tip_p300="B2",
            ),
            {"https://example.org/plasmid_0/1": ["G3", "A5"]},
            False,
        ),
        (
            transformations(),
            TransformationConfig(
                transfer_volume_dna=25,
                volume_dna=100,
                aspiration_rate=0.25,
                dispense_rate=0.75,
            ),
            OpentronsTransformationProfile(initial_dna_well=5),
            None,
            False,
        ),
        (
            transformations(),
            TransformationConfig(),
            OpentronsTransformationProfile(),
            None,
            True,
        ),
        (
            transformations(),
            TransformationConfig(water_testing=True),
            OpentronsTransformationProfile(),
            None,
            True,
        ),
    ],
    ids=[
        "default",
        "mixed-chassis-and-tube-boundaries",
        "source-replicates-and-offsets",
        "large-dna-pipette",
        "thermal-path",
        "explicit-water-testing",
    ],
)
def test_transformation_equivalence(
    pudu_repository, tmp_path, payload, config, profile, locations, thermal
):
    compiled = ProtocolCompiler(transformation=config).compile(
        transformation_request_from_json(payload, request_id="transformation"),
        profile=profile,
        inputs=plasmid_manifest_from_json(locations) if locations is not None else None,
    )
    expected_source = reference_script(payload, config, profile, locations)
    actual_source = compiled.script
    if thermal:
        expected_source, actual_source = (
            force_thermal_path(expected_source),
            force_thermal_path(actual_source),
        )
    expected = simulate_source(expected_source, python_paths=(pudu_repository / "src",))
    actual = simulate_source(actual_source)
    for name, result in (("reference", expected), ("migrated", actual)):
        (tmp_path / f"{name}.json").write_text(
            json.dumps(asdict(result), indent=2, sort_keys=True)
        )
    assert actual.actions and actual.actions == expected.actions
    assert actual.sdk_calls == expected.sdk_calls
    if not thermal:
        assert expected.generated_json["plating_input.json"] == {
            "bacterium_locations": compiled.manifest.bacterium_locations()
        }
    if thermal and not config.water_testing:
        assert (
            sum(
                call["method"].endswith(".execute_profile") for call in actual.sdk_calls
            )
            == 2
        )
    assert actual.generated_json == {}
    print(
        f"{len(actual.actions)} actions; {len(actual.sdk_calls)} SDK calls; thermal={thermal}"
    )
