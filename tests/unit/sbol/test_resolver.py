import sbol2
import pytest

from buildcompiler.sbol import PullPolicy, SbolResolver


class FakePullClient:
    def __init__(self, document: sbol2.Document) -> None:
        self.document = document
        self.calls: list[str] = []

    def __call__(self, identity: str):
        self.calls.append(identity)
        return self.document.find(identity)


class ReturnOnlyPullClient:
    def __init__(self, pulled_objects: dict[str, object]) -> None:
        self.pulled_objects = pulled_objects
        self.calls: list[str] = []

    def __call__(self, identity: str):
        self.calls.append(identity)
        return self.pulled_objects.get(identity)


def _make_doc() -> tuple[sbol2.Document, dict[str, str]]:
    doc = sbol2.Document()
    ns = "https://example.org"
    sbol2.setHomespace(ns)

    comp = sbol2.ComponentDefinition(f"{ns}/component")
    mod = sbol2.ModuleDefinition(f"{ns}/module")
    impl = sbol2.Implementation(f"{ns}/impl")
    comb = sbol2.CombinatorialDerivation(f"{ns}/comb", comp.identity)

    doc.add(comp)
    doc.add(mod)
    doc.add(impl)
    doc.add(comb)
    return doc, {
        "component": comp.identity,
        "module": mod.identity,
        "implementation": impl.identity,
        "combinatorial": comb.identity,
    }


def test_resolver_gets_expected_types_from_local_document():
    doc, ids = _make_doc()
    resolver = SbolResolver(doc, pull_policy=PullPolicy.NEVER)

    assert resolver.get_component(ids["component"]).identity == ids["component"]
    assert resolver.get_module(ids["module"]).identity == ids["module"]
    assert resolver.get_implementation(ids["implementation"]).identity == ids["implementation"]
    assert (
        resolver.get_combinatorial_derivation(ids["combinatorial"]).identity
        == ids["combinatorial"]
    )


def test_never_policy_does_not_pull_on_miss():
    doc, _ = _make_doc()
    fake = FakePullClient(doc)
    resolver = SbolResolver(doc, pull_policy=PullPolicy.NEVER, pull_client=fake)

    with pytest.raises(LookupError):
        resolver.get_component("https://example.org/missing")

    assert fake.calls == []


def test_missing_only_pulls_only_when_local_lookup_misses():
    doc, ids = _make_doc()
    fake = FakePullClient(doc)
    resolver = SbolResolver(doc, pull_policy=PullPolicy.MISSING_ONLY, pull_client=fake)

    resolver.get_component(ids["component"])
    assert fake.calls == []

    with pytest.raises(LookupError):
        resolver.get_component("https://example.org/missing")
    assert fake.calls == ["https://example.org/missing"]


def test_always_refresh_pulls_even_on_hit():
    doc, ids = _make_doc()
    fake = FakePullClient(doc)
    resolver = SbolResolver(doc, pull_policy=PullPolicy.ALWAYS_REFRESH, pull_client=fake)

    resolver.get_component(ids["component"])

    assert fake.calls == [ids["component"]]


def test_missing_only_returns_object_from_pull_client_without_document_mutation():
    local_doc = sbol2.Document()
    ns = "https://example.org"
    sbol2.setHomespace(ns)
    remote_component = sbol2.ComponentDefinition(f"{ns}/remote-component")
    pull_client = ReturnOnlyPullClient({remote_component.identity: remote_component})
    resolver = SbolResolver(
        local_doc, pull_policy=PullPolicy.MISSING_ONLY, pull_client=pull_client
    )

    resolved = resolver.get_component(remote_component.identity)

    assert resolved is remote_component
    assert pull_client.calls == [remote_component.identity]
