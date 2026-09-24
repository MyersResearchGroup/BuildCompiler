"""Acceptance: execute both independent implementations in the real simulator."""

import json
from dataclasses import asdict

import pytest

from buildcompiler.protocols import (
    AssemblyConfig,
    OpentronsAssemblyProfile,
    ProtocolCompiler,
    assembly_request_from_json,
)
from buildcompiler.protocols.backends.opentrons.simulation import (
    SimulationError,
    simulate_source,
)

pytestmark = pytest.mark.automation


def assemblies(count=1):
    return [
        {
            "Product": f"https://example.org/product_{index}/1",
            "Backbone": "https://example.org/backbone/1",
            "PartsList": [
                "https://example.org/part_b/1",
                f"https://example.org/part_{index}/1",
            ],
            "Restriction Enzyme": "https://example.org/enzyme/1",
        }
        for index in range(count)
    ]


def reference_script(payload, config, profile):
    fields = (
        "volume_total_reaction",
        "volume_part",
        "volume_restriction_enzyme",
        "volume_t4_dna_ligase",
        "volume_t4_dna_ligase_buffer",
        "replicates",
        "aspiration_rate",
        "dispense_rate",
        "water_testing",
    )
    parameters = {name: getattr(config, name) for name in fields}
    parameters.update(
        {key: value for key, value in asdict(profile).items() if key != "api_level"}
    )
    parameters["tiprack_positions"] = list(parameters["tiprack_positions"])
    parameters["output_xlsx"] = False
    return (
        "from pudu.assembly import SBOLLoopAssembly\n"
        "metadata = {'apiLevel': '2.21', 'protocolName': 'PUDU reference'}\n"
        "def run(protocol):\n"
        f"    SBOLLoopAssembly(assemblies={payload!r}, json_params={parameters!r}).run(protocol)\n"
    )


@pytest.mark.parametrize(
    "count,config,profile",
    [
        (1, AssemblyConfig(), OpentronsAssemblyProfile()),
        (3, AssemblyConfig(replicates=2), OpentronsAssemblyProfile()),
        (
            1,
            AssemblyConfig(replicates=2),
            OpentronsAssemblyProfile(initial_tip="G10", thermocycler_starting_well=9),
        ),
        (
            1,
            AssemblyConfig(replicates=15),
            OpentronsAssemblyProfile(tiprack_positions=("2",)),
        ),
        (1, AssemblyConfig(water_testing=True), OpentronsAssemblyProfile()),
        (
            2,
            AssemblyConfig(
                volume_total_reaction=25, aspiration_rate=0.25, dispense_rate=0.75
            ),
            OpentronsAssemblyProfile(),
        ),
    ],
    ids=[
        "default",
        "multiple-products-and-replicates",
        "offsets",
        "rack-swap",
        "water-testing",
        "configuration",
    ],
)
def test_assembly_simulator_equivalence(
    pudu_repository, tmp_path, count, config, profile
):
    payload = assemblies(count)
    compiled = ProtocolCompiler(assembly=config).compile(
        assembly_request_from_json(payload, request_id="acceptance"),
        profile=profile,
    )
    expected = simulate_source(
        reference_script(payload, config, profile),
        python_paths=(pudu_repository / "src",),
    )
    actual = simulate_source(compiled.script)
    for label, trace in (("reference", expected), ("migrated", actual)):
        (tmp_path / f"{label}.json").write_text(
            json.dumps(asdict(trace), indent=2, sort_keys=True)
        )
    assert actual.simulator_version == expected.simulator_version == "8.8.2"
    assert actual.actions, "An empty simulation is not equivalence evidence."
    assert actual.actions == expected.actions
    assert actual.sdk_calls == expected.sdk_calls
    assert (
        expected.generated_json["transformation_input.json"]
        == compiled.manifest.plasmid_locations()
    )
    assert actual.generated_json == {}, (
        "Generated scripts must not write handoff files at runtime."
    )
    print(
        f"{len(actual.actions)} actions; {len(actual.sdk_calls)} SDK calls; handoff equal"
    )


def test_trace_detects_a_changed_flow_rate(pudu_repository):
    request = assembly_request_from_json(assemblies(), request_id="negative-control")
    original = simulate_source(ProtocolCompiler().compile(request).script)
    changed = simulate_source(
        ProtocolCompiler(assembly=AssemblyConfig(aspiration_rate=0.25))
        .compile(request)
        .script
    )
    assert original.actions != changed.actions


def test_simulator_failure_is_reported(pudu_repository):
    with pytest.raises(SimulationError, match="deliberate failure"):
        simulate_source(
            "metadata={'apiLevel':'2.21'}\ndef run(protocol):\n    raise ValueError('deliberate failure')\n"
        )
