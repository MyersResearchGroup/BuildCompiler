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
    r = sbol2.ComponentDefinition("https://example.org/r")
    r.roles = ["http://identifiers.org/so/SO:0000139"]
    c = sbol2.ComponentDefinition("https://example.org/c")
    c.roles = ["http://identifiers.org/so/SO:0000316"]
    t = sbol2.ComponentDefinition("https://example.org/t")
    t.roles = ["http://identifiers.org/so/SO:0000141"]
    er.components.create("c1").definition = p.identity
    er.components.create("c2").definition = r.identity
    er.components.create("c3").definition = c.identity
    er.components.create("c4").definition = t.identity
    out2 = classify_non_combinatorial(er)
    assert out2.stage == BuildStage.ASSEMBLY_LVL1


def test_classifier_warns_for_invalid_lvl1_part_mix():
    design = sbol2.ComponentDefinition("https://example.org/invalid")
    p = sbol2.ComponentDefinition("https://example.org/p2")
    p.roles = ["http://identifiers.org/so/SO:0000167"]
    design.components.create("c1").definition = p.identity
    design.components.create("c2").definition = p.identity

    out = classify_non_combinatorial(design)
    assert isinstance(out, UnsupportedPlanningRecord)
    assert "promoter" in out.reason.lower()


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


def test_classifier_carries_lvl2_region_order_constraints():
    doc = sbol2.Document()
    promoter = sbol2.ComponentDefinition("https://example.org/p_region")
    promoter.roles = ["http://identifiers.org/so/SO:0000167"]
    rbs = sbol2.ComponentDefinition("https://example.org/r_region")
    rbs.roles = ["http://identifiers.org/so/SO:0000139"]
    cds = sbol2.ComponentDefinition("https://example.org/c_region")
    cds.roles = ["http://identifiers.org/so/SO:0000316"]
    terminator = sbol2.ComponentDefinition("https://example.org/t_region")
    terminator.roles = ["http://identifiers.org/so/SO:0000141"]
    region = sbol2.ComponentDefinition("https://example.org/region")
    module = sbol2.ModuleDefinition("https://example.org/mod_with_region")

    for obj in (promoter, rbs, cds, terminator, region):
        doc.addComponentDefinition(obj)
    for idx, part in enumerate((promoter, rbs, cds, terminator), start=1):
        region.components.create(f"part{idx}").definition = part.identity
    fc = module.functionalComponents.create("region_fc")
    fc.definition = region.identity
    doc.addModuleDefinition(module)

    out = classify_non_combinatorial(module)

    assert out.stage == BuildStage.ASSEMBLY_LVL2
    assert out.constraints["engineered_region_identities"] == [region.identity]
    assert out.constraints["lvl1_region_part_identities"] == {
        region.identity: [
            promoter.identity,
            rbs.identity,
            cds.identity,
            terminator.identity,
        ]
    }
