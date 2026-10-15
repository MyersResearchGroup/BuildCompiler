"""Real simulator comparisons for plating and its allocation manifest."""

import json
from dataclasses import asdict

import pytest

from buildcompiler.protocols import (
    OpentronsPlatingProfile,
    PlatingConfig,
    PlatingRequest,
    ProtocolCompiler,
    bacterium_manifest_from_json,
)
from buildcompiler.protocols.backends.simulation import simulate_source
from buildcompiler.protocols.models import PLATE_96

pytestmark = pytest.mark.automation


def plating_data(count):
    return {
        "bacterium_locations": {
            PLATE_96.name(i + 3): [f"strain_{i}", "cell", f"plasmid_{i}"]
            for i in range(count)
        }
    }


def reference_script(payload, config, profile):
    parameters = asdict(config) | {
        key: value for key, value in asdict(profile).items() if key != "api_level"
    }
    return (
        "from pudu.plating import Plating\nmetadata={'apiLevel': '2.21'}\ndef run(protocol):\n"
        f"    Plating(plating_data={payload!r}, json_params={parameters!r}).run(protocol)\n"
    )


@pytest.mark.parametrize(
    "count,config,profile",
    [
        (1, PlatingConfig(), OpentronsPlatingProfile()),
        (
            5,
            PlatingConfig(replicates=2),
            OpentronsPlatingProfile(
                initial_small_tip="C4", initial_large_tip="B2", lb_tube_position=4
            ),
        ),
        (25, PlatingConfig(replicates=2), OpentronsPlatingProfile()),
        (
            3,
            PlatingConfig(number_dilutions=1, aspiration_rate=0.25, dispense_rate=0.75),
            OpentronsPlatingProfile(),
        ),
        (9, PlatingConfig(volume_lb=3100), OpentronsPlatingProfile()),
    ],
    ids=[
        "default",
        "replicates-and-offsets",
        "two-agar-plates",
        "one-dilution",
        "conical-height-threshold",
    ],
)
def test_plating_equivalence(
    pudu_repository, tmp_path, count, config, profile, compare_json_backend
):
    payload = plating_data(count)
    inputs = bacterium_manifest_from_json(payload)
    compiled = ProtocolCompiler(plating=config).compile(
        PlatingRequest(id="plating", sample_ids=tuple(s.id for s in inputs.samples)),
        inputs=inputs,
        profile=profile,
    )
    json_protocol = ProtocolCompiler(plating=config).compile(
        PlatingRequest(id="plating", sample_ids=tuple(s.id for s in inputs.samples)),
        inputs=inputs,
        profile=profile,
        backend="opentrons_ot2_json",
    )
    compare_json_backend(
        reference_script(payload, config, profile), compiled, json_protocol
    )
    expected = simulate_source(
        reference_script(payload, config, profile),
        python_paths=(pudu_repository / "src",),
    )
    actual = simulate_source(compiled.script)
    for name, result in (("reference", expected), ("migrated", actual)):
        (tmp_path / f"{name}.json").write_text(
            json.dumps(asdict(result), indent=2, sort_keys=True)
        )
    assert actual.actions and actual.actions == expected.actions
    assert actual.sdk_calls == expected.sdk_calls
    handoff = compiled.files["plating_layout.json"]
    assert expected.generated_json["plating_layout.json"] == json.loads(handoff)
    assert actual.generated_json == {}
    print(
        f"{len(actual.actions)} actions; {len(actual.sdk_calls)} SDK calls; handoff equal"
    )
