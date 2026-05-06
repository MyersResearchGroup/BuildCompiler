import sbol2

from buildcompiler.domain import BuildStage
from buildcompiler.planning.classifier import classify_non_combinatorial, request_id_for
from buildcompiler.planning.models import UnsupportedPlanningRecord


def test_classifier_maps_module_and_components():
    sbol2.setHomespace("https://example.org")
    md = sbol2.ModuleDefinition("https://example.org/mod")
    out = classify_non_combinatorial(md)
    assert out.stage == BuildStage.ASSEMBLY_LVL2

    er = sbol2.ComponentDefinition("https://example.org/er")
    p = sbol2.ComponentDefinition("https://example.org/p")
    p.roles = ["http://identifiers.org/so/SO:0000167"]
    er.components.create("c1").definition = p.identity
    er.components.create("c2").definition = p.identity
    out2 = classify_non_combinatorial(er)
    assert out2.stage == BuildStage.ASSEMBLY_LVL1


def test_classifier_domestication_and_unsupported_and_deterministic_id():
    part = sbol2.ComponentDefinition("https://example.org/part")
    part.roles = ["http://identifiers.org/so/SO:0000139"]
    out = classify_non_combinatorial(part)
    assert out.stage == BuildStage.DOMESTICATION

    unknown = sbol2.ComponentDefinition("https://example.org/u")
    bad = classify_non_combinatorial(unknown)
    assert isinstance(bad, UnsupportedPlanningRecord)

    rid1 = request_id_for(BuildStage.ASSEMBLY_LVL1, "https://example.org/A", "A")
    rid2 = request_id_for(BuildStage.ASSEMBLY_LVL1, "https://example.org/A", "A")
    assert rid1 == rid2
