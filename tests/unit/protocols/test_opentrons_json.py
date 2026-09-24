"""Backend selection and offline JSON compilation without the robot SDK."""

import json
import subprocess
import sys
from dataclasses import replace

import pytest

from buildcompiler.api.protocols import (
    compile_assembly,
    compile_plating,
    compile_transformation,
)
from buildcompiler.domain import BuildStage, StageResult, StageStatus
from buildcompiler.protocols import (
    AssemblyConfig,
    OpentronsAssemblyProfile,
    ProtocolCompiler,
    TransformationConfig,
    assembly_request_from_json,
    transformation_request_from_json,
)
from buildcompiler.protocols.backends.opentrons_ot2_json import (
    OpentronsProtocolBuilder,
    render_json,
)
from buildcompiler.protocols.models import PickUpTip, Transfer


@pytest.fixture(autouse=True)
def shared_data():
    """Only the optional data package is needed; core imports remain independent."""
    pytest.importorskip("opentrons_shared_data")


def assembly_request():
    """A small batch for testing compiler contracts."""
    return assembly_request_from_json(
        [
            {
                "Product": "product",
                "Backbone": "backbone",
                "PartsList": ["part"],
                "Restriction Enzyme": "enzyme",
            }
        ],
        request_id="assembly",
    )


def transformation_request():
    """A transformation consuming the assembly's identified product."""
    return transformation_request_from_json(
        [{"Strain": "strain", "Chassis": "cell", "Plasmids": ["product"]}],
        request_id="transformation",
    )


def test_json_is_deterministic_offline_and_writes_the_correct_artifact(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    compiler = ProtocolCompiler()
    first = compiler.compile(assembly_request(), backend="opentrons_ot2_json")
    assert first == compiler.compile(assembly_request(), backend="opentrons_ot2_json")
    assert not list(tmp_path.iterdir())
    assert "opentrons" not in sys.modules
    document = json.loads(first.source)
    assert document["robot"]["model"] == "OT-2 Standard"
    assert document["schemaVersion"] == 8
    assert document["commandSchemaId"] == "opentronsCommandSchemaV10"
    for command in document["commands"]:
        if command["commandType"] == "loadLabware":
            p = command["params"]
            assert (
                f"{p['namespace']}/{p['loadName']}/{p['version']}"
                in document["labwareDefinitions"]
            )
    assert first.protocol_filename == "protocol.json"
    paths = first.write(tmp_path)
    assert (tmp_path / "protocol.json").read_text() == first.source
    assert not (tmp_path / "protocol.py").exists()
    assert first.protocol_filename in {path.name for path in paths}
    with pytest.raises(FileExistsError):
        first.write(tmp_path)
    assert (
        json.loads(first.files["compilation.json"])["backend"] == "opentrons_ot2_json"
    )


@pytest.mark.parametrize("backend", ["opentrons_ot2_python", "opentrons_ot2_json"])
def test_stage_helpers_accept_either_backend_through_a_complete_workflow(backend):
    assembled = compile_assembly(
        StageResult(
            id="assembly",
            stage=BuildStage.ASSEMBLY_LVL1,
            status=StageStatus.SUCCESS,
            protocol_requests=(assembly_request(),),
        ),
        backend=backend,
    )
    transformed = compile_transformation(
        StageResult(
            id="transformation",
            stage=BuildStage.TRANSFORMATION,
            status=StageStatus.SUCCESS,
            protocol_requests=(transformation_request(),),
        ),
        inputs=assembled.manifest,
        backend=backend,
    )
    plated = compile_plating(transformed.manifest, backend=backend)
    for compiled in (assembled, transformed, plated):
        assert compiled.backend == backend
        assert compiled.source == compiled.files[compiled.protocol_filename]
        assert compiled.manifest.samples


def test_unknown_backend_fails_explicitly():
    with pytest.raises(ValueError, match="Unsupported protocol backend"):
        ProtocolCompiler().compile(assembly_request(), backend="unknown")


def test_json_retains_execution_temperatures_and_respects_water_testing():
    for water_testing in (False, True):
        compiled = ProtocolCompiler(
            transformation=TransformationConfig(water_testing=water_testing)
        ).compile(transformation_request(), backend="opentrons_ot2_json")
        programs = [
            c
            for c in json.loads(compiled.source)["commands"]
            if c["commandType"] == "thermocycler/runExtendedProfile"
        ]
        assert len(programs) == (0 if water_testing else 2)


def test_json_rejects_capacity_and_invalid_tip_ownership():
    compiler = ProtocolCompiler()
    profile = OpentronsAssemblyProfile()
    plan = compiler.compile(assembly_request()).plan
    transfer = next(step for step in plan.steps if isinstance(step, Transfer))
    with pytest.raises(ValueError, match="attached tip"):
        render_json(
            replace(plan, steps=(replace(transfer, new_tip=False),)), profile=profile
        )
    with pytest.raises(ValueError, match="already attached"):
        render_json(
            replace(plan, steps=(PickUpTip(id="first"), transfer)), profile=profile
        )
    with pytest.raises(ValueError, match="pipette capacity"):
        ProtocolCompiler(assembly=AssemblyConfig(volume_total_reaction=50)).compile(
            assembly_request(), backend="opentrons_ot2_json"
        )


def test_authoring_boundary_rejects_unknown_optional_command_parameters():
    from jsonschema import ValidationError

    builder = OpentronsProtocolBuilder(
        ProtocolCompiler().compile(assembly_request()).plan, OpentronsAssemblyProfile()
    )
    with pytest.raises(ValidationError):
        builder._emit(
            "pickUpTip",
            pipetteId="pipette",
            labwareId="tips",
            wellName="A1",
            wellLocaton={},
        )


def test_missing_json_dependency_does_not_break_python_compilation():
    code = """
import importlib.abc
import sys
class NoSharedData(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        if fullname.split('.')[0] == 'opentrons_shared_data':
            raise ImportError('intentionally unavailable')
sys.meta_path.insert(0, NoSharedData())
from buildcompiler.protocols import ProtocolCompiler, assembly_request_from_json
request = assembly_request_from_json(
    [{'Product': 'product', 'Backbone': 'backbone', 'PartsList': ['part'], 'Restriction Enzyme': 'enzyme'}],
    request_id='boundary')
assert ProtocolCompiler().compile(request).protocol_filename == 'protocol.py'
try:
    ProtocolCompiler().compile(request, backend='opentrons_ot2_json')
except ImportError as error:
    assert 'automation' in str(error)
else:
    raise AssertionError('JSON compilation silently ignored a missing dependency')
assert 'opentrons' not in sys.modules
"""
    process = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True
    )
    assert process.returncode == 0, process.stderr
