"""An independent pinned PUDU checkout is mandatory for acceptance runs."""

import hashlib
import importlib.util
import json
import os
from pathlib import Path

import pytest

from buildcompiler.protocols.backends.simulation import analyze_source


def engine_actions(analysis):
    """Compare physical semantics while removing generated IDs and float noise.

    Keep command order, every execution parameter, loaded geometry and resolved
    positions. Only informational comments, IDs and nonphysical result bookkeeping
    are omitted. A bottom-relative and top-relative offset may denote one point.
    """
    data = analysis.data
    identifiers = {}
    definitions = {}
    liquids = {liquid["id"]: liquid for liquid in data["liquids"]}
    counts = {kind: 0 for kind in ("moduleId", "labwareId", "pipetteId")}
    for command in data["commands"]:
        for kind, load in (
            ("moduleId", "loadModule"),
            ("labwareId", "loadLabware"),
            ("pipetteId", "loadPipette"),
        ):
            if command["commandType"] == load:
                result = command["result"]
                identifiers[result[kind]] = f"{kind}/{counts[kind]}"
                counts[kind] += 1
                if kind == "labwareId":
                    definitions[result[kind]] = result["definition"]

    def normalize(value):
        """Replace resource IDs recursively and retain sub-nanometre precision."""
        if isinstance(value, str):
            return identifiers.get(value, value)
        if isinstance(value, float):
            return round(value, 9)
        if isinstance(value, list):
            return [normalize(item) for item in value]
        if isinstance(value, dict):
            return {key: normalize(item) for key, item in value.items()}
        return value

    actions = []
    for command in data["commands"]:
        assert command["status"] == "succeeded", command
        kind = command["commandType"]
        if kind == "comment":
            continue
        params = dict(command["params"])
        if kind in ("loadModule", "loadLabware", "loadPipette"):
            params.pop(
                {
                    "loadModule": "moduleId",
                    "loadLabware": "labwareId",
                    "loadPipette": "pipetteId",
                }[kind],
                None,
            )
        if "liquidId" in params:
            params["liquidId"] = {
                key: value
                for key, value in liquids[params["liquidId"]].items()
                if key != "id"
            }
        if "wellLocation" in params:
            location = dict(params["wellLocation"])
            offset = dict(location["offset"])
            if location["origin"] == "bottom":
                offset["z"] -= definitions[params["labwareId"]]["wells"][
                    params["wellName"]
                ]["depth"]
                location["origin"] = "top"
            params["wellLocation"] = {**location, "offset": offset}
        # Physical results catch differences in geometry and trash positioning
        # that equal-looking command parameters alone would miss.
        result = {
            key: value
            for key, value in command["result"].items()
            if key
            in (
                "position",
                "volume",
                "tipVolume",
                "tipLength",
                "tipDiameter",
                "definition",
                "model",
            )
        }
        actions.append(
            normalize({"commandType": kind, "params": params, "result": result})
        )
    assert actions
    return actions


@pytest.fixture
def compare_json_backend(pudu_repository, tmp_path):
    """Run PUDU, native Python and native JSON through the same real engine."""

    def compare(reference, python_protocol, json_protocol):
        """Require the same plan, handoffs and physical trace in all three runs."""
        assert python_protocol.plan == json_protocol.plan
        assert python_protocol.manifest == json_protocol.manifest
        for name in python_protocol.files.keys() - {"protocol.py", "compilation.json"}:
            assert python_protocol.files[name] == json_protocol.files[name]

        def thermal_source(source):
            """Exercise execution's thermal path even while the engine simulates."""
            return (
                source.replace("def run(", "def _original_run(", 1)
                + "\ndef run(protocol):\n    protocol.is_simulating = lambda: False\n    _original_run(protocol)\n"
            )

        traces = {}
        for label, source, format, paths in (
            ("pudu", thermal_source(reference), "python", (pudu_repository / "src",)),
            ("python", thermal_source(python_protocol.source), "python", ()),
            ("json", json_protocol.source, "json", ()),
        ):
            analysis = analyze_source(source, format=format, python_paths=paths)
            assert analysis.simulator_version == "8.8.2"
            traces[label] = engine_actions(analysis)
            (
                tmp_path
                / f"{python_protocol.plan.id.replace('/', '_')}-{label}-engine.json"
            ).write_text(json.dumps(traces[label], indent=2, sort_keys=True))
            if label != "pudu":
                assert not analysis.generated_json
        assert traces["python"] == traces["pudu"]
        assert traces["json"] == traces["pudu"]
        print(
            f"{len(traces['json'])} Protocol Engine commands equal across all three backends"
        )

    return compare


@pytest.fixture(scope="session")
def pudu_repository():
    required = os.environ.get("BUILDCOMPILER_REQUIRE_EQUIVALENCE") == "1"
    repository = Path(
        os.environ.get("PUDU_REPOSITORY", Path(__file__).resolve().parents[3] / "PUDU")
    )
    if (
        importlib.util.find_spec("opentrons") is None
        or not (repository / "src/pudu/assembly.py").is_file()
    ):
        if required:
            pytest.fail("Acceptance requires Opentrons and a PUDU reference checkout.")
        pytest.skip("Install the automation extra and supply PUDU_REPOSITORY.")
    reference = json.loads(Path(__file__).with_name("pudu_reference.json").read_text())
    for name, expected in reference["sha256"].items():
        path = repository / name
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected, (
            f"PUDU reference changed: {path}"
        )
    return repository
