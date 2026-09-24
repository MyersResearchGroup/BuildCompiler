import ast
import dataclasses
import json

import pytest

from buildcompiler.protocols import (
    OpentronsPlatingProfile,
    OpentronsTransformationProfile,
    PlatingConfig,
    PlatingRequest,
    ProtocolCompiler,
    TransformationConfig,
    bacterium_manifest_from_json,
    plasmid_manifest_from_json,
    transformation_request_from_json,
)
from buildcompiler.protocols.models import Distribute, RunTemperatureProgram


def request():
    return transformation_request_from_json(
        [
            {
                "Strain": "https://example.org/strain/1",
                "Chassis": "https://example.org/chassis/1",
                "Plasmids": [
                    "https://example.org/first/1",
                    "https://example.org/second/1",
                ],
            },
        ],
        request_id="transform",
    )


def sources():
    return plasmid_manifest_from_json(
        {
            "https://example.org/first/1": ["D2", "A4"],
            "https://example.org/second/1": ["F3", "G8"],
        }
    )


def test_source_replicates_lineage_and_explicit_locations():
    upstream = sources()
    compiled = ProtocolCompiler(
        transformation=TransformationConfig(replicates=3)
    ).compile(
        request(),
        inputs=upstream,
        profile=OpentronsTransformationProfile(thermocycler_starting_well=8),
    )
    assert len(compiled.manifest.samples) == 6
    assert [p.location.well_name for p in compiled.manifest.samples] == [
        "A2",
        "B2",
        "C2",
        "D2",
        "E2",
        "F2",
    ]
    samples = {s.id: s for s in compiled.plan.samples}
    first_sources = compiled.manifest.samples[0].parent_ids[1:-1]
    second_sources = compiled.manifest.samples[3].parent_ids[1:-1]
    assert [samples[s].source_sample_id for s in first_sources] == [
        upstream.samples[0].id,
        upstream.samples[2].id,
    ]
    assert [samples[s].source_sample_id for s in second_sources] == [
        upstream.samples[1].id,
        upstream.samples[3].id,
    ]
    dna_locations = {p.id: p.location.well_name for p in compiled.plan.samples}
    assert [dna_locations[s] for s in first_sources] == ["D2", "F3"]
    assert [dna_locations[s] for s in second_sources] == ["A4", "G8"]


@pytest.mark.parametrize(
    "locations",
    [
        {"https://example.org/first/1": ["A1"]},
        {
            "https://example.org/first/1": ["A1", "B1"],
            "https://example.org/second/1": ["C1"],
        },
    ],
)
def test_missing_and_unequal_plasmid_source_replicates_fail(locations):
    with pytest.raises(ValueError, match="source|Source"):
        ProtocolCompiler().compile(
            request(), inputs=plasmid_manifest_from_json(locations)
        )


def test_duplicate_physical_sources_are_rejected():
    with pytest.raises(ValueError, match="locations must be unique"):
        plasmid_manifest_from_json({"first": ["A1"], "second": ["A1"]})


def test_transformation_requires_one_plate_for_the_complete_handoff():
    upstream = plasmid_manifest_from_json(
        {
            "https://example.org/first/1": ["A1"],
            "https://example.org/second/1": ["B1"],
            "unused": ["C1"],
        }
    )
    unused = upstream.samples[-1]
    upstream = dataclasses.replace(
        upstream,
        samples=(
            *upstream.samples[:-1],
            dataclasses.replace(
                unused,
                location=dataclasses.replace(unused.location, container_id="other"),
            ),
        ),
    )
    with pytest.raises(ValueError, match="one source DNA plate"):
        ProtocolCompiler().compile(request(), inputs=upstream)


def test_plating_binds_selected_aliquots_by_id_and_preserves_their_wells():
    upstream = sources()
    # Keep two aliquots of the same material on one plate; the unselected
    # material occupies another plate and must not affect the selected batch.
    upstream = dataclasses.replace(
        upstream,
        samples=(
            *upstream.samples[:2],
            *(
                dataclasses.replace(
                    sample,
                    location=dataclasses.replace(sample.location, container_id="other"),
                )
                for sample in upstream.samples[2:]
            ),
        ),
    )
    selected = tuple(s.id for s in reversed(upstream.samples[:2]))
    compiled = ProtocolCompiler().compile(
        PlatingRequest(id="selected", sample_ids=selected), inputs=upstream
    )
    cultures = [s for s in compiled.plan.samples if s.role == "bacteria"]
    assert tuple(s.source_sample_id for s in cultures) == selected
    assert [s.location.well_name for s in cultures] == ["A4", "D2"]
    assert {s.location.container_id for s in cultures} == {"reactions"}
    with pytest.raises(ValueError, match="one source plate"):
        ProtocolCompiler().compile(
            PlatingRequest(
                id="mixed-plates",
                sample_ids=(upstream.samples[0].id, upstream.samples[-1].id),
            ),
            inputs=upstream,
        )


def test_transformation_thermal_steps_are_reviewable_but_simulation_guarded():
    compiler = ProtocolCompiler()
    compiled = compiler.compile(request())
    programs = [s for s in compiled.plan.steps if isinstance(s, RunTemperatureProgram)]
    assert len(programs) == 2 and all(p.skip_during_simulation for p in programs)
    assert "Omitted during Opentrons simulation" in compiled.markdown
    assert "if not protocol.is_simulating():" in compiled.script
    wet = compiler.transformation.with_overrides({"water_testing": True})
    assert not any(
        isinstance(s, RunTemperatureProgram)
        for s in ProtocolCompiler(transformation=wet).plan(request()).steps
    )


def test_transformation_tube_and_tip_capacity_checked_before_rendering():
    with pytest.raises(ValueError, match="outside this grid"):
        ProtocolCompiler(
            transformation=TransformationConfig(
                replicates=60, tube_volume_competent_cell=20
            )
        ).compile(request())
    with pytest.raises(ValueError, match="tips"):
        ProtocolCompiler().compile(
            request(), profile=OpentronsTransformationProfile(initial_tip_p20="H12")
        )


@pytest.mark.parametrize(
    "config_type,values",
    [
        (TransformationConfig, {"replicates": True}),
        (TransformationConfig, {"transfer_volume_dna": float("nan")}),
        (TransformationConfig, {"tube_volume_competent_cell": 1}),
        (TransformationConfig, {"tube_volume_recovery_media": 1}),
        (TransformationConfig, {"water_testing": "false"}),
        (PlatingConfig, {"number_dilutions": 3}),
        (PlatingConfig, {"replicates": 9}),
        (PlatingConfig, {"dilution_factor": 1}),
        (PlatingConfig, {"volume_colony": 20}),
        (PlatingConfig, {"volume_lb": float("inf")}),
    ],
)
def test_invalid_method_configuration(config_type, values):
    with pytest.raises((ValueError, TypeError)):
        config_type(**values)


def test_plating_has_lineage_for_dilutions_and_each_replicate():
    transformed = ProtocolCompiler().compile(request())
    compiled = ProtocolCompiler(plating=PlatingConfig(replicates=2)).compile(
        PlatingRequest(
            id="plate", sample_ids=tuple(s.id for s in transformed.manifest.samples)
        ),
        inputs=transformed.manifest,
    )
    assert len(compiled.manifest.samples) == 8
    samples = {s.id: s for s in compiled.plan.samples}
    for output in compiled.manifest.samples:
        parent = samples[output.parent_ids[0]]
        assert parent.role == "dilution" and parent.dilution == output.dilution
        while parent.role == "dilution":
            parent = samples[parent.parent_ids[0]]
        assert parent.source_sample_id in {s.id for s in transformed.manifest.samples}
    broth = [s for s in compiled.plan.steps if isinstance(s, Distribute)]
    assert all(s.new_tip == "never" and s.source.track_conical_height for s in broth)


def test_plating_import_does_not_fabricate_sbol_identity():
    manifest = bacterium_manifest_from_json(
        {"bacterium_locations": {"B4": ["strain", "plasmid"]}}
    )
    assert manifest.samples[0].material.identity.startswith(
        "urn:buildcompiler:imported:"
    )
    assert manifest.samples[0].contents == ("strain", "plasmid")


def test_compilation_is_deterministic_and_has_no_file_or_sdk_effects(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    compiler = ProtocolCompiler()
    transformed = compiler.compile(request())
    plated = compiler.compile(
        PlatingRequest(
            id="plating", sample_ids=tuple(s.id for s in transformed.manifest.samples)
        ),
        inputs=transformed.manifest,
    )
    assert compiler.compile(request()) == transformed
    assert list(tmp_path.iterdir()) == []
    for compiled in (transformed, plated):
        with pytest.raises(dataclasses.FrozenInstanceError):
            compiled.manifest.protocol_id = "changed"
        imports = [
            n.module
            for n in ast.walk(ast.parse(compiled.script))
            if isinstance(n, ast.ImportFrom)
        ]
        assert imports == ["opentrons"]
        metadata = json.loads(compiled.files["compilation.json"])
        assert all("kind" in operation for operation in metadata["plan"]["steps"])


def test_plating_requires_matching_profile_and_manifest():
    req = PlatingRequest(id="plate", sample_ids=("unknown",))
    with pytest.raises(ValueError, match="source manifest"):
        ProtocolCompiler().compile(req)
    with pytest.raises(ValueError, match="missing"):
        ProtocolCompiler().compile(req, inputs=sources())
    with pytest.raises(ValueError, match="Deck slots"):
        OpentronsPlatingProfile(large_tiprack_position="9")
