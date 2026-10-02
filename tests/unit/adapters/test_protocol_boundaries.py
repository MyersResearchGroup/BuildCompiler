import hashlib
import json
import sys

import pytest

from buildcompiler.adapters import build_protocol_bundle, maybe_write_protocol_artifacts
from buildcompiler.api import ProtocolMode, ProtocolOptions
from buildcompiler.domain import BuildStage, StageResult, StageStatus


def test_protocol_mode_none_returns_in_memory_only(tmp_path):
    artifacts = maybe_write_protocol_artifacts(
        payloads={"assembly": {"k": "v"}},
        options=ProtocolOptions(mode=ProtocolMode.NONE, results_dir=tmp_path),
        basename="artifact",
    )

    assert artifacts["assembly"].path is None
    assert artifacts["assembly"].content == {"k": "v"}
    assert artifacts["assembly"].metadata["written"] is False
    assert not any(tmp_path.iterdir())


def test_protocol_mode_manual_writes_when_results_dir_set(tmp_path):
    artifacts = maybe_write_protocol_artifacts(
        payloads={"assembly": {"k": "v"}},
        options=ProtocolOptions(mode=ProtocolMode.MANUAL, results_dir=tmp_path),
        basename="artifact",
    )

    path = artifacts["assembly"].path
    assert path is not None
    assert path.name == "artifact_assembly.json"
    assert path.exists()


def test_file_protocol_mode_requires_explicit_results_dir():
    with pytest.raises(ValueError, match="results_dir"):
        maybe_write_protocol_artifacts(
            payloads={"plating": {"k": "v"}},
            options=ProtocolOptions(mode=ProtocolMode.AUTOMATED, results_dir=None),
        )


def test_protocol_bundle_writes_json_manual_and_deterministic_manifest(tmp_path):
    stage_results = [
        StageResult(
            id="assembly-result",
            stage=BuildStage.ASSEMBLY_LVL1,
            status=StageStatus.SUCCESS,
            request_ids=["request-1"],
            json_intermediate={
                "Product": "product",
                "Backbone": "backbone",
                "PartsList": ["part-a", "part-b"],
                "Restriction Enzyme": "BsaI",
                "Ligase": "T4_DNA_ligase",
            },
        )
    ]

    bundle = build_protocol_bundle(
        stage_results=stage_results,
        options=ProtocolOptions(mode=ProtocolMode.MANUAL, results_dir=tmp_path),
    )

    assert bundle.status == "success"
    assert (tmp_path / "assembly_lvl1_001.json").exists()
    assert (tmp_path / "assembly_lvl1_001.md").exists()
    assert (tmp_path / "protocol_manifest.json").exists()
    assert bundle.manifest["artifacts"]
    assert all("sha256" in item for item in bundle.manifest["artifacts"])


@pytest.mark.parametrize(
    ("stage", "payload", "handoff"),
    [
        (
            BuildStage.ASSEMBLY_LVL1,
            {
                "Product": "product",
                "Backbone": "backbone",
                "PartsList": ["part"],
                "Restriction Enzyme": "BsaI",
            },
            "transformation_input.json",
        ),
        (
            BuildStage.ASSEMBLY_LVL2,
            [
                {
                    "Product": "product",
                    "Backbone": "backbone",
                    "PartsList": ["part"],
                    "Restriction Enzyme": "BsaI",
                }
            ],
            "transformation_input.json",
        ),
        (
            BuildStage.DOMESTICATION,
            {
                "Product": "product",
                "Backbone": "backbone",
                "PartsList": ["insert"],
                "Restriction Enzyme": "BsaI",
                "Generated Insert Sequence": "ACGT",
            },
            "transformation_input.json",
        ),
        (
            BuildStage.TRANSFORMATION,
            {"Strain": "strain", "Chassis": "chassis", "Plasmids": ["plasmid"]},
            "plating_input.json",
        ),
        (
            BuildStage.PLATING,
            {"bacterium_locations": {"A1": ["strain"]}},
            "plating_layout.json",
        ),
    ],
)
def test_automated_bundle_uses_native_compiler_without_pudu_or_sdk(
    monkeypatch, tmp_path, stage, payload, handoff
):
    monkeypatch.setitem(sys.modules, "pudu", None)
    monkeypatch.setitem(sys.modules, "pudu.generate_protocol", None)
    monkeypatch.setitem(sys.modules, "opentrons", None)
    result = StageResult(
        id="stage-result",
        stage=stage,
        status=StageStatus.SUCCESS,
        json_intermediate=payload,
    )
    options = ProtocolOptions(mode=ProtocolMode.AUTOMATED, results_dir=tmp_path)

    bundle = build_protocol_bundle(stage_results=[result], options=options)

    basename = f"{stage.value}_001"
    script = (tmp_path / f"{basename}.py").read_text()
    compile(script, f"{basename}.py", "exec")
    assert "def run(" in script
    assert "pudu" not in script
    assert bundle.artifacts[f"{basename}_automated"].metadata["written"] is True
    assert json.loads((tmp_path / f"{basename}_{handoff}").read_text())
    compilation = json.loads((tmp_path / f"{basename}_compilation.json").read_text())
    assert compilation["backend"] == "opentrons_ot2_python"
    for artifact in bundle.manifest["artifacts"]:
        assert (
            artifact["sha256"]
            == hashlib.sha256((tmp_path / artifact["path"]).read_bytes()).hexdigest()
        )

    before = {path.name: path.read_bytes() for path in tmp_path.iterdir()}
    with pytest.raises(FileExistsError):
        build_protocol_bundle(stage_results=[result], options=options)
    options.overwrite = True
    repeated = build_protocol_bundle(stage_results=[result], options=options)
    assert repeated.manifest == bundle.manifest
    assert before == {path.name: path.read_bytes() for path in tmp_path.iterdir()}


def test_automated_bundle_rejects_incomplete_input_before_writing(tmp_path):
    result = StageResult(
        id="transformation-result",
        stage=BuildStage.TRANSFORMATION,
        status=StageStatus.SUCCESS,
        json_intermediate={"Strain": "strain", "Plasmids": ["plasmid"]},
    )

    with pytest.raises(ValueError, match="Chassis"):
        build_protocol_bundle(
            stage_results=[result],
            options=ProtocolOptions(mode=ProtocolMode.AUTOMATED, results_dir=tmp_path),
        )
    assert not any(tmp_path.iterdir())
