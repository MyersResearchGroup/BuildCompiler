import ast
import dataclasses
import json
import subprocess
import sys

import pytest

from buildcompiler.api.protocols import compile_assembly
from buildcompiler.api.serialization import serialize_stage_result
from buildcompiler.domain import BuildStage, StageResult, StageStatus
from buildcompiler.protocols import (
    AssemblyConfig,
    OpentronsAssemblyProfile,
    ProtocolCompiler,
    assembly_request_from_json,
    transformation_request_from_json,
)
from buildcompiler.protocols.backends.markdown import render_markdown
from buildcompiler.protocols.methods import sequential_wells
from buildcompiler.protocols.models import BLOCK_24, PLATE_96, Transfer


def payload():
    return [
        {
            "Product": "https://example.org/product/1",
            "Backbone": "https://example.org/backbone/1",
            "PartsList": [
                "https://example.org/part_b/1",
                "https://example.org/part_a/1",
            ],
            "Restriction Enzyme": "https://example.org/enzyme/1",
        }
    ]


def request():
    return assembly_request_from_json(payload(), request_id="example")


@pytest.mark.parametrize(
    "decode", [assembly_request_from_json, transformation_request_from_json]
)
@pytest.mark.parametrize(
    "data,error,message",
    [
        ({}, TypeError, "sequence of reaction objects"),
        ("[]", TypeError, "sequence of reaction objects"),
        ([None], TypeError, "entry must be an object"),
        ([{}], ValueError, "0 is missing"),
    ],
)
def test_reaction_decoders_reject_invalid_envelopes(decode, data, error, message):
    with pytest.raises(error, match=message):
        decode(data, request_id="invalid")


@pytest.mark.parametrize("grid,last_well", [(PLATE_96, "H12"), (BLOCK_24, "D6")])
def test_sequential_wells_respect_remaining_capacity(grid, last_well):
    locations = sequential_wells(
        ("last",), container_id="plate", grid=grid, start=grid.capacity - 1
    )
    assert locations["last"].well_name == last_well
    assert locations["last"].container_id == "plate"
    with pytest.raises(ValueError, match="outside this grid"):
        sequential_wells(
            ("last", "overflow"),
            container_id="plate",
            grid=grid,
            start=grid.capacity - 1,
        )


def test_compile_is_deterministic_and_never_writes(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    compiler = ProtocolCompiler()
    first = compiler.compile(request())
    second = compiler.compile(request())
    assert first == second
    assert list(tmp_path.iterdir()) == []
    assert ast.parse(first.script)
    imports = [
        node.module
        for node in ast.walk(ast.parse(first.script))
        if isinstance(node, ast.ImportFrom)
    ]
    assert imports == ["opentrons"]
    with pytest.raises(dataclasses.FrozenInstanceError):
        first.plan.id = "changed"


def test_config_overrides_preserve_explicit_default_and_false():
    config = AssemblyConfig(replicates=3, water_testing=True)
    resolved = config.with_overrides({"replicates": 1, "water_testing": False})
    assert resolved.replicates == 1
    assert not resolved.water_testing
    assert config.replicates == 3 and config.water_testing
    with pytest.raises(ValueError, match="Unknown"):
        config.with_overrides({"typo": 2})


@pytest.mark.parametrize(
    "values",
    [
        {"replicates": 0},
        {"replicates": True},
        {"replicates": 1.5},
        {"volume_part": float("nan")},
        {"volume_part": float("inf")},
        {"volume_part": -1},
        {"water_testing": "false"},
    ],
)
def test_invalid_configuration_is_rejected(values):
    with pytest.raises((TypeError, ValueError)):
        AssemblyConfig(**values)


def test_order_identity_replicates_and_locations_survive_compilation():
    compiled = ProtocolCompiler(assembly=AssemblyConfig(replicates=2)).compile(
        request(),
        profile=OpentronsAssemblyProfile(thermocycler_starting_well=9),
    )
    plan = compiled.plan
    samples = {sample.id: sample for sample in plan.samples}
    outputs = [samples[identity] for identity in plan.output_sample_ids]
    assert [output.replicate for output in outputs] == [1, 2]
    assert outputs[0].id != outputs[1].id
    assert [samples[parent].material.identity for parent in outputs[0].parent_ids] == [
        payload()[0]["Backbone"],
        *payload()[0]["PartsList"],
    ]
    assert compiled.manifest.plasmid_locations() == {
        payload()[0]["Product"]: ["B2", "C2"]
    }
    assert compiled.manifest.to_dict()["state"] == "planned"


def test_same_labels_do_not_collapse_different_material_identities():
    data = payload()
    data[0]["PartsList"] = ["https://a.example/part/1", "https://b.example/part/1"]
    plan = ProtocolCompiler().plan(
        assembly_request_from_json(data, request_id="collision")
    )
    parts = [sample for sample in plan.samples if sample.material.label == "part"]
    assert len(parts) == 2
    assert parts[0].id != parts[1].id


@pytest.mark.parametrize(
    "profile",
    [
        {"thermocycler_starting_well": -1},
        {"thermocycler_starting_well": 96},
        {"initial_tip": "I1"},
        {"tiprack_positions": ()},
        {"tiprack_positions": ("1",)},
        {"tiprack_positions": ("7",)},
        {"tiprack_positions": ("2", "2")},
        {"api_level": "2.1"},
    ],
)
def test_bad_hardware_profiles_fail_before_rendering(profile):
    with pytest.raises(ValueError):
        OpentronsAssemblyProfile(**profile)


def test_capacity_and_invalid_reaction_are_rejected():
    with pytest.raises(ValueError, match="plate capacity"):
        ProtocolCompiler(assembly=AssemblyConfig(replicates=97)).compile(request())
    with pytest.raises(ValueError, match="remaining volume"):
        ProtocolCompiler(assembly=AssemblyConfig(volume_total_reaction=10)).compile(
            request()
        )
    with pytest.raises(ValueError, match="pipette capacity"):
        ProtocolCompiler(assembly=AssemblyConfig(volume_total_reaction=50)).compile(
            request()
        )


def test_manual_render_and_script_use_the_same_configuration():
    compiled = ProtocolCompiler(assembly=AssemblyConfig(replicates=2)).compile(
        request()
    )
    transfers = [step for step in compiled.plan.steps if isinstance(step, Transfer)]
    assert len(transfers) == compiled.markdown.count("Transfer ")
    assert "replicate 1" in compiled.markdown and "replicate 2" in compiled.markdown
    assert "reactions/A1" in compiled.markdown and "reactions/B1" in compiled.markdown
    assert "75" in compiled.markdown
    assert "not an execution record" in compiled.markdown
    assert render_markdown(compiled.plan)


def test_compiled_artifacts_require_explicit_write_and_refuse_overwrite(tmp_path):
    compiled = ProtocolCompiler().compile(request())
    paths = compiled.write(tmp_path)
    assert {path.name for path in paths} == {
        "protocol.py",
        "compilation.json",
        "protocol.md",
        "manifest.json",
        "transformation_input.json",
    }
    assert (
        json.loads((tmp_path / "manifest.json").read_text())
        == compiled.manifest.to_dict()
    )
    with pytest.raises(FileExistsError):
        compiled.write(tmp_path)


def test_stage_to_compiled_protocol_preserves_serializable_requests():
    result = StageResult(
        id="assembly-stage",
        stage=BuildStage.ASSEMBLY_LVL1,
        status=StageStatus.SUCCESS,
        protocol_requests=(request(),),
    )
    compiled = compile_assembly(result)
    assert compiled.manifest.protocol_id == result.id
    dto = serialize_stage_result(result)
    assert (
        dto["protocol_requests"][0]["reactions"][0]["parts"][0]["identity"]
        == payload()[0]["PartsList"][0]
    )
    result.status = StageStatus.BLOCKED
    with pytest.raises(ValueError, match="successful"):
        compile_assembly(result)


def test_well_order_is_explicit_for_both_geometries():
    assert [PLATE_96.name(i) for i in (0, 7, 8, 95)] == ["A1", "H1", "A2", "H12"]
    assert [BLOCK_24.name(i) for i in (0, 3, 4, 23)] == ["A1", "D1", "A2", "D6"]


def test_core_import_does_not_load_automation_or_reporting_dependencies():
    process = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; import buildcompiler.protocols; "
                "assert not any(name.split('.')[0] in {'opentrons', 'pudu', 'xlsxwriter'} for name in sys.modules)"
            ),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert process.returncode == 0, process.stderr
