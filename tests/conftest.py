from __future__ import annotations

import sbol2
import pytest

from buildcompiler.api import BuildOptions
from buildcompiler.domain import BuildRequest, BuildStage, DesignKind


@pytest.fixture
def default_build_options() -> BuildOptions:
    options = BuildOptions()
    options.execution.max_iterations = 5
    return options


@pytest.fixture
def minimal_sbol_document() -> sbol2.Document:
    return sbol2.Document()


@pytest.fixture
def minimal_lvl2_request() -> BuildRequest:
    return BuildRequest(
        id="req-lvl2-1",
        stage=BuildStage.ASSEMBLY_LVL2,
        source_identity="https://example.org/module/main",
        source_display_id="main",
        source_kind=DesignKind.MODULE_DEFINITION,
    )
