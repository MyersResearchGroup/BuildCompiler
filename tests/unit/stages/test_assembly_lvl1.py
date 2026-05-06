import sbol2

from buildcompiler.domain import (
    BuildRequest,
    BuildStage,
    BuildWarning,
    DesignKind,
    IndexedBackbone,
    IndexedPlasmid,
    IndexedReagent,
    MaterialState,
    StageStatus,
)
from buildcompiler.inventory import Inventory
from buildcompiler.sbol import AssemblySbolResult
from buildcompiler.stages import AssemblyLvl1Stage


class _FakeAssemblyService:
    def __init__(self, products):
        self.products = products

    def run(self, job):
        return AssemblySbolResult(
            products=self.products,
            stage_document=job.target_document,
            activity_identity="https://example.org/activity/a1",
            logs=["fake-assembly-service-ran"],
        )


def _inventory(*, include_parts=True, include_backbone=True, include_reagents=True):
    plasmids = []
    if include_parts:
        plasmids = [
            IndexedPlasmid(
                identity="https://example.org/plasmids/p-prom",
                metadata={
                    "insert_identities": ["https://example.org/parts/promoter"],
                    "antibiotic": "Ampicillin",
                },
            ),
            IndexedPlasmid(
                identity="https://example.org/plasmids/p-rbs",
                metadata={
                    "insert_identities": ["https://example.org/parts/rbs"],
                    "antibiotic": "Ampicillin",
                },
            ),
            IndexedPlasmid(
                identity="https://example.org/plasmids/p-cds",
                metadata={
                    "insert_identities": ["https://example.org/parts/cds"],
                    "antibiotic": "Ampicillin",
                },
            ),
            IndexedPlasmid(
                identity="https://example.org/plasmids/p-term",
                metadata={
                    "insert_identities": ["https://example.org/parts/terminator"],
                    "antibiotic": "Ampicillin",
                },
            ),
        ]
    backbones = []
    if include_backbone:
        backbones = [
            IndexedBackbone(
                identity="https://example.org/backbones/lvl1",
                metadata={
                    "fusion_sites": ("A", "B"),
                    "antibiotic": "Ampicillin",
                    "stage": BuildStage.ASSEMBLY_LVL1.value,
                },
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


def _request():
    return BuildRequest(
        id="req-1",
        stage=BuildStage.ASSEMBLY_LVL1,
        source_identity="https://example.org/designs/d1",
        source_display_id="d1",
        source_kind=DesignKind.COMPONENT_DEFINITION,
        constraints={
            "ordered_part_identities": [
                "https://example.org/parts/promoter",
                "https://example.org/parts/rbs",
                "https://example.org/parts/cds",
                "https://example.org/parts/terminator",
            ],
            "fusion_sites": ["A", "B"],
            "antibiotic": "Ampicillin",
            "ordering_warnings": [
                {
                    "code": "planner.ordering",
                    "message": "planner warning",
                    "metadata": {"source": "planner"},
                }
            ],
        },
    )


def test_assembly_lvl1_success_returns_products_json_and_indexes_generated():
    inv = _inventory()
    generated = IndexedPlasmid(
        identity="https://example.org/plasmids/generated-1",
        state=MaterialState.GENERATED,
        metadata={"insert_identities": ["https://example.org/parts/promoter"]},
    )
    stage = AssemblyLvl1Stage(
        inventory=inv, assembly_service=_FakeAssemblyService([generated])
    )

    result = stage.run(
        _request(), source_document=sbol2.Document(), target_document=sbol2.Document()
    )

    assert result.status == StageStatus.SUCCESS
    assert result.products
    assert result.products[0].identity == generated.identity
    assert (
        result.json_intermediate
        and result.json_intermediate["Product"] == "https://example.org/designs/d1"
    )
    assert result.sbol_document is not None
    assert inv.find_lvl1_region_plasmids("https://example.org/designs/d1")
    assert result.logs
    assert result.warnings and isinstance(result.warnings[0], BuildWarning)


def test_assembly_lvl1_missing_inputs_return_blocked_with_structured_kinds():
    inv = _inventory(
        include_parts=False, include_backbone=False, include_reagents=False
    )
    stage = AssemblyLvl1Stage(inventory=inv, assembly_service=_FakeAssemblyService([]))

    result = stage.run(
        _request(), source_document=sbol2.Document(), target_document=sbol2.Document()
    )

    assert result.status == StageStatus.BLOCKED
    kinds = {missing.missing_kind for missing in result.missing_inputs}
    assert {
        "promoter",
        "rbs",
        "cds",
        "terminator",
        "backbone",
        "restriction_enzyme",
        "ligase",
    }.issubset(kinds)
