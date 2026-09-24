"""Connected acceptance: each implementation consumes its own previous handoff."""

import json
from dataclasses import asdict

import pytest

from buildcompiler.protocols import (
    AssemblyConfig,
    OpentronsPlatingProfile,
    PlatingConfig,
    PlatingRequest,
    ProtocolCompiler,
    TransformationConfig,
    assembly_request_from_json,
    transformation_request_from_json,
)
from buildcompiler.protocols.backends.simulation import simulate_source

pytestmark = pytest.mark.automation


def test_connected_workflow_equivalence(
    pudu_repository, tmp_path, compare_json_backend
):
    assemblies = [
        {
            "Product": f"https://example.org/plasmid_{i}/1",
            "Backbone": "https://example.org/backbone/1",
            "PartsList": [f"https://example.org/part_{i}/1"],
            "Restriction Enzyme": "https://example.org/enzyme/1",
        }
        for i in range(2)
    ]
    transformations = [
        {
            "Strain": f"https://example.org/strain_{i}/1",
            "Chassis": "https://example.org/chassis/1",
            "Plasmids": [a["Product"]],
        }
        for i, a in enumerate(assemblies)
    ]
    compiler = ProtocolCompiler(
        assembly=AssemblyConfig(replicates=2),
        transformation=TransformationConfig(replicates=2),
        plating=PlatingConfig(replicates=2),
    )
    reference_preamble = "metadata={'apiLevel':'2.21'}\ndef run(protocol):\n"

    def compare(name, reference_source, compiled, json_compiled):
        compare_json_backend(reference_source, compiled, json_compiled)
        expected = simulate_source(
            reference_source, python_paths=(pudu_repository / "src",)
        )
        actual = simulate_source(compiled.script)
        for label, result in (("reference", expected), ("migrated", actual)):
            (tmp_path / f"{name}-{label}.json").write_text(
                json.dumps(asdict(result), indent=2, sort_keys=True)
            )
        assert actual.actions and actual.actions == expected.actions
        assert actual.sdk_calls == expected.sdk_calls
        assert actual.generated_json == {}
        return expected.generated_json

    assembly = compiler.compile(
        assembly_request_from_json(assemblies, request_id="assembly")
    )
    json_assembly = compiler.compile(
        assembly_request_from_json(assemblies, request_id="assembly"),
        backend="opentrons_ot2_json",
    )
    expected_assembly = compare(
        "assembly",
        "from pudu.assembly import SBOLLoopAssembly\n"
        + reference_preamble
        + f"    SBOLLoopAssembly(assemblies={assemblies!r}, replicates=2, output_xlsx=False).run(protocol)\n",
        assembly,
        json_assembly,
    )
    assert (
        expected_assembly["transformation_input.json"]
        == assembly.manifest.plasmid_locations()
    )
    transformation = compiler.compile(
        transformation_request_from_json(transformations, request_id="transformation"),
        inputs=assembly.manifest,
    )
    json_transformation = compiler.compile(
        transformation_request_from_json(transformations, request_id="transformation"),
        inputs=json_assembly.manifest,
        backend="opentrons_ot2_json",
    )
    expected_transformation = compare(
        "transformation",
        "from pudu.transformation import HeatShockTransformation\n"
        + reference_preamble
        + f"    HeatShockTransformation(transformation_data={transformations!r}, plasmid_locations={expected_assembly['transformation_input.json']!r}, replicates=2).run(protocol)\n",
        transformation,
        json_transformation,
    )
    assert expected_transformation["plating_input.json"] == {
        "bacterium_locations": transformation.manifest.bacterium_locations()
    }
    # Explicitly retain the physical plate definition from transformation.
    plating_profile = OpentronsPlatingProfile(
        thermocycler_labware="nest_96_wellplate_100ul_pcr_full_skirt"
    )
    plating = compiler.compile(
        PlatingRequest(
            id="plating",
            sample_ids=tuple(s.id for s in transformation.manifest.samples),
        ),
        inputs=transformation.manifest,
        profile=plating_profile,
    )
    json_plating = compiler.compile(
        PlatingRequest(
            id="plating",
            sample_ids=tuple(s.id for s in json_transformation.manifest.samples),
        ),
        inputs=json_transformation.manifest,
        profile=plating_profile,
        backend="opentrons_ot2_json",
    )
    expected_plating = compare(
        "plating",
        "from pudu.plating import Plating\n"
        + reference_preamble
        + f"    Plating(plating_data={expected_transformation['plating_input.json']!r}, replicates=2, thermocycler_labware={plating_profile.thermocycler_labware!r}).run(protocol)\n",
        plating,
        json_plating,
    )
    assert expected_plating["plating_layout.json"] == json.loads(
        plating.files["plating_layout.json"]
    )
    assert [len(p.manifest.samples) for p in (assembly, transformation, plating)] == [
        4,
        8,
        32,
    ]
    assert {
        s.source_sample_id for s in transformation.plan.samples if s.role == "dna"
    } == {s.id for s in assembly.manifest.samples}
    assert {
        s.source_sample_id for s in plating.plan.samples if s.role == "bacteria"
    } == {s.id for s in transformation.manifest.samples}
