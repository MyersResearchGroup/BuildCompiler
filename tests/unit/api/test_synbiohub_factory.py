import subprocess
import sys

import pytest
import sbol2

from buildcompiler.api import (
    BuildCompiler,
    SynBioHubAuthenticationError,
    SynBioHubConfigurationError,
    SynBioHubNetworkError,
)
from buildcompiler.constants import ENGINEERED_PLASMID
from buildcompiler.domain import BuildStatus
from buildcompiler.planning import BuildPlan


class FakePartShop:
    resources = {}
    calls = []
    instances = []
    failure = None

    def __init__(self, registry):
        self.registry = registry
        self.key = ""
        type(self).instances.append(self)

    def pull(self, identity, document):
        type(self).calls.append((identity, self.key))
        if type(self).failure is not None:
            raise type(self).failure
        document.add(type(self).resources[identity])


@pytest.fixture(autouse=True)
def reset_fake_partshop(monkeypatch):
    FakePartShop.resources = {}
    FakePartShop.calls = []
    FakePartShop.instances = []
    FakePartShop.failure = None
    monkeypatch.setattr(sbol2, "PartShop", FakePartShop)


def _collection_graph(name):
    collection = sbol2.Collection(f"collection_{name}")
    implementation = sbol2.Implementation(f"implementation_{name}")
    plasmid = sbol2.ComponentDefinition(f"plasmid_{name}", sbol2.BIOPAX_DNA)
    plasmid.roles = [ENGINEERED_PLASMID]
    implementation.built = plasmid.identity
    collection.members = [implementation.identity]
    return collection, implementation, plasmid


def _install_resources(*graphs):
    FakePartShop.resources = {item.identity: item for graph in graphs for item in graph}


def test_token_only_factory_indexes_collection_and_clears_token():
    graph = _collection_graph("one")
    _install_resources(graph)
    token = "secret-token-value"

    compiler = BuildCompiler.from_synbiohub(
        collections=[graph[0].identity],
        sbh_registry="https://registry.example",
        auth_token=token,
    )

    assert graph[2].identity in compiler.inventory.plasmids_by_identity
    assert compiler.sbol_document.find(graph[2].identity) is graph[2]
    assert compiler.resolver.get_component(graph[2].identity) is graph[2]
    assert compiler.planner.resolver is compiler.resolver
    assert compiler.execute(BuildPlan()).status == BuildStatus.SUCCESS
    assert FakePartShop.instances[0].key == ""
    assert token not in repr(compiler)
    assert "pudupy" not in sys.modules
    assert "opentrons" not in sys.modules


def test_clean_api_import_does_not_load_legacy_or_optional_dependencies():
    script = """
import sys
import buildcompiler.api
forbidden = {'buildcompiler.buildcompiler', 'pudupy', 'opentrons', 'SBOLInventory'}
loaded = forbidden.intersection(sys.modules)
if loaded:
    raise SystemExit(','.join(sorted(loaded)))
"""
    completed = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, check=False
    )

    assert completed.returncode == 0, completed.stderr or completed.stdout


def test_multiple_collections_are_indexed_deterministically():
    graph_b = _collection_graph("b")
    graph_a = _collection_graph("a")
    _install_resources(graph_a, graph_b)

    compiler = BuildCompiler.from_synbiohub(
        collections=[graph_b[0].identity, graph_a[0].identity],
        sbh_registry="https://registry.example",
        auth_token="token",
    )

    assert list(compiler.inventory.plasmids_by_identity) == sorted(
        [graph_a[2].identity, graph_b[2].identity]
    )
    assert [identity for identity, _ in FakePartShop.calls[:2]] == sorted(
        [graph_a[0].identity, graph_b[0].identity]
    )


def test_missing_member_and_built_identity_are_resolved_before_indexing():
    graph = _collection_graph("remote")
    _install_resources(graph)

    compiler = BuildCompiler.from_synbiohub(
        collections=[graph[0].identity],
        sbh_registry="https://registry.example",
        auth_token="token",
    )

    assert [identity for identity, _ in FakePartShop.calls] == [
        graph[0].identity,
        graph[1].identity,
        graph[2].identity,
    ]
    assert compiler.resolver.get_component(graph[2].identity) is graph[2]


@pytest.mark.parametrize(
    ("failure", "expected"),
    [
        (
            RuntimeError("401 unauthorized: secret-token-value"),
            SynBioHubAuthenticationError,
        ),
        (OSError("network down: secret-token-value"), SynBioHubNetworkError),
    ],
)
def test_failures_are_typed_and_never_expose_token(failure, expected):
    graph = _collection_graph("failure")
    _install_resources(graph)
    FakePartShop.failure = failure
    token = "secret-token-value"

    with pytest.raises(expected) as caught:
        BuildCompiler.from_synbiohub(
            collections=[graph[0].identity],
            sbh_registry="https://registry.example",
            auth_token=token,
        )

    assert token not in str(caught.value)
    assert FakePartShop.instances[0].key == ""


def test_collection_loading_requires_registry_and_token():
    with pytest.raises(SynBioHubConfigurationError, match="sbh_registry"):
        BuildCompiler.from_synbiohub(collections=["collection"])
    with pytest.raises(SynBioHubConfigurationError, match="auth_token"):
        BuildCompiler.from_synbiohub(
            collections=["collection"], sbh_registry="https://registry.example"
        )
    with pytest.raises(SynBioHubConfigurationError, match="list"):
        BuildCompiler.from_synbiohub(collections=("collection",))


def test_factory_does_not_accept_username_or_password():
    with pytest.raises(TypeError):
        BuildCompiler.from_synbiohub(username="user")
    with pytest.raises(TypeError):
        BuildCompiler.from_synbiohub(password="password")
