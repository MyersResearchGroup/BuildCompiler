import sbol2

from buildcompiler.api import (
    BuildOptions,
    assembly_lvl1,
    assembly_lvl2,
    domestication,
    transformation,
)
from buildcompiler.domain import (
    BuildStage,
    IndexedBackbone,
    IndexedPlasmid,
    IndexedReagent,
    MaterialState,
    StageStatus,
)
from buildcompiler.inventory import Inventory
from buildcompiler.sbol import AssemblySbolResult


class FakeAssemblyService:
    def run(self, job):
        component = sbol2.ComponentDefinition(f"{job.product_display_id}_product")
        job.target_document.addComponentDefinition(component)
        return AssemblySbolResult(
            products=[
                IndexedPlasmid(
                    identity=component.identity,
                    display_id=component.displayId,
                    state=MaterialState.GENERATED,
                    sbol_component=component,
                )
            ],
            stage_document=job.target_document,
            activity_identity="fake_activity",
            logs=["fake assembly ran"],
        )


def _reagents():
    return [
        IndexedReagent("bsai", name="BsaI", reagent_type="restriction_enzyme"),
        IndexedReagent("ligase", name="T4_DNA_ligase", reagent_type="ligase"),
    ]


def test_domestication_public_function_example():
    doc = sbol2.Document()
    part = sbol2.ComponentDefinition("promoter_a")
    part.roles = "http://identifiers.org/so/SO:0000167"
    seq = sbol2.Sequence("promoter_a_seq")
    seq.elements = "ATGCAA"
    seq.encoding = sbol2.SBOL_ENCODING_IUPAC
    doc.addSequence(seq)
    part.sequences = seq.identity
    doc.addComponentDefinition(part)
    inventory = Inventory(
        backbones=[
            IndexedBackbone(
                "dom_bb",
                metadata={
                    "fusion_sites": ("A", "B"),
                    "antibiotic": "Ampicillin",
                    "insertion_index": 0,
                },
            )
        ],
        reagents=_reagents(),
    )

    result = domestication(part, inventory=inventory, source_document=doc)

    assert result.status == StageStatus.SUCCESS
    assert result.products
    assert doc.find(result.products[0].identity) is not None


def test_assembly_lvl1_public_function_example(monkeypatch):
    monkeypatch.setattr(
        "buildcompiler.stages.assembly_lvl1.AssemblyService", FakeAssemblyService
    )
    doc = sbol2.Document()
    design = sbol2.ComponentDefinition("tu_a")
    part_ids = ["promoter", "rbs", "cds", "terminator"]
    for part_id in part_ids:
        part = sbol2.ComponentDefinition(part_id)
        doc.addComponentDefinition(part)
        component = design.components.create(f"{part_id}_component")
        component.definition = part.identity
    doc.addComponentDefinition(design)
    inventory = Inventory(
        plasmids=[
            IndexedPlasmid(
                f"{part_id}_plasmid",
                metadata={
                    "insert_identities": [part_id],
                    "fusion_sites": ("A", "B"),
                    "antibiotic": "Ampicillin",
                },
            )
            for part_id in part_ids
        ],
        backbones=[
            IndexedBackbone(
                "lvl1_bb",
                metadata={
                    "stage": BuildStage.ASSEMBLY_LVL1.value,
                    "fusion_sites": ("A", "B"),
                    "antibiotic": "Ampicillin",
                },
            )
        ],
        reagents=_reagents(),
    )

    result = assembly_lvl1(
        design,
        inventory=inventory,
        source_document=doc,
        constraints={
            "ordered_part_identities": part_ids,
            "fusion_sites": ("A", "B"),
            "antibiotic": "Ampicillin",
        },
    )

    assert result.status == StageStatus.SUCCESS
    assert result.json_intermediate["Product"] == design.identity
    assert doc.find(result.products[0].identity) is not None


def test_assembly_lvl2_public_function_example(monkeypatch):
    monkeypatch.setattr(
        "buildcompiler.stages.assembly_lvl2.AssemblyService", FakeAssemblyService
    )
    doc = sbol2.Document()
    module = sbol2.ModuleDefinition("module_a")
    regions = []
    for name in ("region_a", "region_b"):
        region = sbol2.ComponentDefinition(name)
        doc.addComponentDefinition(region)
        fc = module.functionalComponents.create(f"{name}_fc")
        fc.definition = region.identity
        regions.append(region.identity)
    doc.addModuleDefinition(module)
    inventory = Inventory(
        plasmids=[
            IndexedPlasmid(
                f"{region}_plasmid", metadata={"insert_identities": [region]}
            )
            for region in regions
        ],
        backbones=[
            IndexedBackbone(
                "lvl2_bb", metadata={"stage": BuildStage.ASSEMBLY_LVL2.value}
            )
        ],
        reagents=_reagents(),
    )

    result = assembly_lvl2(
        module,
        inventory=inventory,
        source_document=doc,
        constraints={"region_order": regions},
    )

    assert result.status == StageStatus.SUCCESS
    assert result.protocol_artifacts["selected_route"]["region_order"] == regions
    assert doc.find(result.products[0].identity) is not None


def test_transformation_public_function_example():
    doc = sbol2.Document()
    plasmid = sbol2.ComponentDefinition("plasmid_a")
    doc.addComponentDefinition(plasmid)
    options = BuildOptions()

    result = transformation(
        IndexedPlasmid(
            identity=plasmid.identity,
            display_id=plasmid.displayId,
            sbol_component=plasmid,
        ),
        source_document=doc,
        options=options,
        chassis_identity="dh5alpha",
        chassis_display_id="dh5alpha",
    )

    assert result.status == StageStatus.SUCCESS
    assert result.products
    assert doc.find(result.products[0].identity) is not None
