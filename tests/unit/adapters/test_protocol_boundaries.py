import sys
import types

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


def test_automated_bundle_generates_pudu_script_lazily(monkeypatch, tmp_path):
    calls = []

    def generate_protocol(**kwargs):
        calls.append(kwargs)
        return "from opentrons import protocol_api\n"

    pudu_module = types.ModuleType("pudu")
    generate_module = types.ModuleType("pudu.generate_protocol")
    generate_module.generate_protocol = generate_protocol
    monkeypatch.setitem(sys.modules, "pudu", pudu_module)
    monkeypatch.setitem(sys.modules, "pudu.generate_protocol", generate_module)
    stage_result = StageResult(
        id="assembly-result",
        stage=BuildStage.ASSEMBLY_LVL1,
        status=StageStatus.SUCCESS,
        json_intermediate={"Product": "product", "PartsList": ["part"]},
    )

    bundle = build_protocol_bundle(
        stage_results=[stage_result],
        options=ProtocolOptions(mode=ProtocolMode.AUTOMATED, results_dir=tmp_path),
    )

    assert (tmp_path / "assembly_lvl1_001.py").exists()
    assert bundle.artifacts["assembly_lvl1_001_automated"].metadata["written"] is True
    assert calls[0]["protocol_type"] == "assembly"
    assert calls[0]["assembly_subtype"] == "SBOL"


def test_automated_bundle_missing_pudu_fails_explicitly(monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, "pudu", None)
    monkeypatch.setitem(sys.modules, "pudu.generate_protocol", None)
    stage_result = StageResult(
        id="transformation-result",
        stage=BuildStage.TRANSFORMATION,
        status=StageStatus.SUCCESS,
        json_intermediate={"Strain": "strain", "Plasmids": ["plasmid"]},
    )

    with pytest.raises(ImportError, match="automation"):
        build_protocol_bundle(
            stage_results=[stage_result],
            options=ProtocolOptions(
                mode=ProtocolMode.AUTOMATED,
                results_dir=tmp_path,
            ),
        )
