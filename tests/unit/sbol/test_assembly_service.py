import sbol2
import pytest

from buildcompiler.domain import (
    BuildStage,
    IndexedBackbone,
    IndexedPlasmid,
    IndexedReagent,
    MaterialState,
)
from buildcompiler.sbol import AssemblyJob, AssemblySbolResult, AssemblyService


def test_assembly_service_runs_and_returns_normalized_products(monkeypatch):
    source = sbol2.Document()
    product_component = sbol2.ComponentDefinition("assembled_product")
    source.add(product_component)
    product_impl = sbol2.Implementation("assembled_product_impl")
    product_impl.built = product_component.identity
    source.add(product_impl)
    product_impl.wasGeneratedBy = "https://example.org/activity/assembly"

    class FakeLegacyAssembly:
        def __init__(self, **kwargs):
            self.assembly_activity = sbol2.Activity("fake_assembly")

        def run(self, include_extracted_parts=False):
            return [type("LegacyProduct", (), {"plasmid_definition": product_component, "plasmid_implementations": [product_impl]})()], source

    monkeypatch.setattr("buildcompiler.sbol.assembly.Assembly", FakeLegacyAssembly)

    service = AssemblyService()
    result = service.run(
        AssemblyJob(
            stage=BuildStage.ASSEMBLY_LVL1,
            product_identity="https://example.org/products/p001",
            product_display_id="p001",
            part_plasmids=[
                IndexedPlasmid(
                    identity=product_component.identity,
                    sbol_component=product_component,
                    metadata={"implementation_identity": product_impl.identity},
                )
            ],
            backbone=IndexedBackbone(
                identity=product_component.identity,
                sbol_component=product_component,
                metadata={"implementation_identity": product_impl.identity},
            ),
            restriction_enzyme=IndexedReagent(identity=product_impl.identity),
            ligase=IndexedReagent(identity=product_impl.identity),
            source_document=source,
            target_document=sbol2.Document(),
        )
    )

    assert isinstance(result, AssemblySbolResult)
    assert result.products
    assert isinstance(result.products[0], IndexedPlasmid)
    assert result.products[0].state == MaterialState.GENERATED
    assert result.activity_identity


def test_assembly_service_raises_clear_error_for_missing_component():
    doc = sbol2.Document()
    service = AssemblyService()

    with pytest.raises(ValueError, match="Missing SBOL ComponentDefinition"):
        service.run(
            AssemblyJob(
                stage=BuildStage.ASSEMBLY_LVL1,
                product_identity="https://example.org/products/p001",
                product_display_id="p001",
                part_plasmids=[IndexedPlasmid(identity="https://example.org/missing")],
                backbone=IndexedBackbone(identity="https://example.org/backbone"),
                restriction_enzyme=IndexedReagent(identity="https://example.org/reagent/re"),
                ligase=IndexedReagent(identity="https://example.org/reagent/ligase"),
                source_document=doc,
                target_document=sbol2.Document(),
            )
        )


def test_assembly_service_requires_single_ligation_product(monkeypatch):
    source = sbol2.Document()
    component = sbol2.ComponentDefinition("assembled_product")
    source.add(component)
    impl = sbol2.Implementation("assembled_product_impl")
    impl.built = component.identity
    source.add(impl)

    class FakeLegacyAssembly:
        def __init__(self, **kwargs):
            self.assembly_activity = sbol2.Activity("fake_assembly")

        def run(self, include_extracted_parts=False):
            product = type(
                "LegacyProduct",
                (),
                {"plasmid_definition": component, "plasmid_implementations": [impl]},
            )()
            return [product, product], source

    monkeypatch.setattr("buildcompiler.sbol.assembly.Assembly", FakeLegacyAssembly)

    service = AssemblyService()
    with pytest.raises(ValueError, match="exactly one assembled product"):
        service.run(
            AssemblyJob(
                stage=BuildStage.ASSEMBLY_LVL1,
                product_identity="https://example.org/products/p001",
                product_display_id="p001",
                part_plasmids=[
                    IndexedPlasmid(
                        identity=component.identity,
                        sbol_component=component,
                        metadata={"implementation_identity": impl.identity},
                    )
                ],
                backbone=IndexedBackbone(
                    identity=component.identity,
                    sbol_component=component,
                    metadata={"implementation_identity": impl.identity},
                ),
                restriction_enzyme=IndexedReagent(identity=impl.identity),
                ligase=IndexedReagent(identity=impl.identity),
                source_document=source,
                target_document=sbol2.Document(),
            )
        )
