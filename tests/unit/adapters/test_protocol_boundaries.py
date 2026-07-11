from buildcompiler.adapters import maybe_write_protocol_artifacts
from buildcompiler.api import ProtocolMode, ProtocolOptions


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


def test_protocol_mode_automated_with_no_results_dir_writes_nothing():
    artifacts = maybe_write_protocol_artifacts(
        payloads={"plating": {"k": "v"}},
        options=ProtocolOptions(mode=ProtocolMode.AUTOMATED, results_dir=None),
    )

    assert artifacts["plating"].path is None
    assert artifacts["plating"].metadata["written"] is False
