import sbol2

from buildcompiler.api import BuildOptions
from buildcompiler.domain import (
    BuildRequest,
    BuildStage,
    DesignKind,
    IndexedBackbone,
    IndexedPlasmid,
    IndexedReagent,
    MaterialState,
    StageStatus,
)
from buildcompiler.inventory import Inventory
from buildcompiler.sbol import AssemblySbolResult
from buildcompiler.stages import AssemblyLvl2Stage


class _FakeAssemblyService:
    def __init__(self, products):
        self.products = products

    def run(self, job):
        return AssemblySbolResult(
            products=self.products,
            stage_document=job.target_document,
            activity_identity="https://example.org/activity/lvl2",
            logs=["fake-lvl2-assembly-service-ran"],
        )


def _module_doc():
    doc = sbol2.Document()
    module = sbol2.ModuleDefinition("design_mod")
    region1 = sbol2.ComponentDefinition("region1", sbol2.BIOPAX_DNA)
    region2 = sbol2.ComponentDefinition("region2", sbol2.BIOPAX_DNA)
    doc.addComponentDefinition(region1)
    doc.addComponentDefinition(region2)
    fc1 = module.functionalComponents.create("fc1")
    fc1.definition = region1.identity
    fc2 = module.functionalComponents.create("fc2")
    fc2.definition = region2.identity
    doc.addModuleDefinition(module)
    return doc, module, [region1.identity, region2.identity]


def _request(source_identity, constraints=None):
    return BuildRequest(
        id="req-lvl2",
        stage=BuildStage.ASSEMBLY_LVL2,
        source_identity=source_identity,
        source_display_id="design_mod",
        source_kind=DesignKind.MODULE_DEFINITION,
        constraints=constraints or {},
    )


def _inventory(
    region_identities=None,
    *,
    include_regions=True,
    include_backbone=True,
    include_reagents=True,
):
    plasmids = []
    if include_regions and region_identities:
        plasmids = [
            IndexedPlasmid(
                identity="https://example.org/plasmids/lvl1-r1",
                metadata={"insert_identities": [region_identities[0]]},
                state=MaterialState.ASSEMBLED,
            ),
            IndexedPlasmid(
                identity="https://example.org/plasmids/lvl1-r2",
                metadata={"insert_identities": [region_identities[1]]},
                state=MaterialState.ASSEMBLED,
            ),
        ]
    backbones = []
    if include_backbone:
        backbones = [
            IndexedBackbone(
                identity="https://example.org/backbones/lvl2",
                metadata={"stage": BuildStage.ASSEMBLY_LVL2.value},
            )
        ]
    reagents = []
    if include_reagents:
        reagents = [
            IndexedReagent(
                identity="https://example.org/reagents/bsaI",
                name="BsaI",
                reagent_type="restriction_enzyme",
            ),
            IndexedReagent(
                identity="https://example.org/reagents/ligase",
                name="T4_DNA_ligase",
                reagent_type="ligase",
            ),
        ]
    return Inventory(plasmids=plasmids, backbones=backbones, reagents=reagents)


def test_assembly_lvl2_success_routes_and_indexes_generated_product():
    doc, module, regions = _module_doc()
    inv = _inventory(regions)
    generated = IndexedPlasmid(
        identity="https://example.org/plasmids/lvl2-product",
        state=MaterialState.GENERATED,
    )
    stage = AssemblyLvl2Stage(
        inventory=inv, assembly_service=_FakeAssemblyService([generated])
    )

    result = stage.run(
        _request(module.identity), source_document=doc, target_document=sbol2.Document()
    )

    assert result.status == StageStatus.SUCCESS
    assert result.products and result.products[0].identity == generated.identity
    assert (
        result.json_intermediate
        and result.json_intermediate["Product"] == module.identity
    )
    assert result.protocol_artifacts["selected_route"] is not None
    assert inv.find_lvl1_region_plasmids(module.identity)


def test_assembly_lvl2_no_regions_failed():
    doc = sbol2.Document()
    module = sbol2.ModuleDefinition("empty_mod")
    doc.addModuleDefinition(module)
    stage = AssemblyLvl2Stage(inventory=_inventory([], include_regions=False))

    result = stage.run(
        _request(module.identity), source_document=doc, target_document=sbol2.Document()
    )

    assert result.status == StageStatus.FAILED


def test_assembly_lvl2_missing_engineered_regions_promote_to_lvl1_blockers():
    doc, module, regions = _module_doc()
    stage = AssemblyLvl2Stage(inventory=_inventory(regions, include_regions=False))

    result = stage.run(
        _request(module.identity), source_document=doc, target_document=sbol2.Document()
    )

    assert result.status == StageStatus.BLOCKED
    engineered = [
        m for m in result.missing_inputs if m.missing_kind == "engineered_region"
    ]
    assert engineered
    assert all(m.required_stage == BuildStage.ASSEMBLY_LVL1 for m in engineered)


def test_assembly_lvl2_large_order_requires_opt_in_without_explicit_order():
    options = BuildOptions()
    options.planning.lvl2_search.max_exhaustive_region_count = 4
    options.planning.lvl2_search.allow_large_order_search = False
    stage = AssemblyLvl2Stage(
        inventory=_inventory([], include_regions=False), options=options
    )
    constraints = {"region_identities": [f"https://example.org/r{i}" for i in range(5)]}

    doc, module, _ = _module_doc()
    result = stage.run(
        _request(module.identity, constraints=constraints),
        source_document=doc,
        target_document=sbol2.Document(),
    )

    assert result.status == StageStatus.BLOCKED
    assert result.protocol_artifacts["selected_route"] is None


def test_assembly_lvl2_region_order_constraint_is_hard():
    doc, module, regions = _module_doc()
    inv = _inventory(regions)
    stage = AssemblyLvl2Stage(inventory=inv, assembly_service=_FakeAssemblyService([]))

    order = [regions[1], regions[0]]
    result = stage.run(
        _request(module.identity, constraints={"region_order": order}),
        source_document=doc,
        target_document=sbol2.Document(),
    )

    assert result.status == StageStatus.SUCCESS
    assert result.protocol_artifacts["selected_route"]["region_order"] == order


def test_assembly_lvl2_incomplete_region_order_falls_back_with_warning():
    doc, module, regions = _module_doc()
    inv = _inventory(regions)
    stage = AssemblyLvl2Stage(inventory=inv, assembly_service=_FakeAssemblyService([]))

    incomplete_order = [regions[0]]
    result = stage.run(
        _request(module.identity, constraints={"region_order": incomplete_order}),
        source_document=doc,
        target_document=sbol2.Document(),
    )

    assert result.status == StageStatus.SUCCESS
    assert result.protocol_artifacts["selected_route"] is not None
    assert any("Unable to satisfy region_order constraint" in log for log in result.logs)
