"""An independent pinned PUDU checkout is mandatory for acceptance runs."""

import hashlib
import importlib.util
import json
import os
from pathlib import Path

import pytest


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
        pytest.skip("Install the simulation extra and supply PUDU_REPOSITORY.")
    reference = json.loads(Path(__file__).with_name("pudu_reference.json").read_text())
    for name, expected in reference["sha256"].items():
        path = repository / name
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected, (
            f"PUDU reference changed: {path}"
        )
    return repository
