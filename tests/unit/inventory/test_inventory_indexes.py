from buildcompiler.domain import (
    BuildStage,
    IndexedBackbone,
    IndexedPlasmid,
    IndexedReagent,
    MaterialState,
)
from buildcompiler.inventory import Inventory


def _plasmid(
    identity: str,
    inserts: list[str],
    fusion_sites=("A", "B"),
    antibiotic="Ampicillin",
    state=MaterialState.PLANNED,
):
    return IndexedPlasmid(
        identity=identity,
        display_id=identity.rsplit("/", 1)[-1],
        state=state,
        metadata={
            "insert_identities": inserts,
            "fusion_sites": fusion_sites,
            "antibiotic": antibiotic,
        },
    )


def test_inventory_indexes_and_queries_are_deterministic():
    p2 = _plasmid(
        "https://example.org/p2",
        ["https://example.org/partA"],
        state=MaterialState.GENERATED,
    )
    p1 = _plasmid(
        "https://example.org/p1",
        ["https://example.org/partA", "https://example.org/region1"],
    )

    b1 = IndexedBackbone(
        identity="https://example.org/b1",
        metadata={
            "fusion_sites": ("A", "B"),
            "antibiotic": "Ampicillin",
            "stage": BuildStage.ASSEMBLY_LVL1.value,
        },
    )
    b2 = IndexedBackbone(
        identity="https://example.org/b2",
        metadata={
            "fusion_sites": ("A", "B"),
            "antibiotic": "Ampicillin",
            "stage": BuildStage.ASSEMBLY_LVL2.value,
        },
    )

    e1 = IndexedReagent(
        identity="https://example.org/r1",
        name="BsaI",
        reagent_type="restriction_enzyme",
    )
    l1 = IndexedReagent(
        identity="https://example.org/r2", name="T4_DNA_ligase", reagent_type="ligase"
    )

    inv = Inventory(plasmids=[p2, p1], backbones=[b2, b1], reagents=[e1, l1])

    assert inv.plasmids_by_identity[p1.identity] == p1
    assert [
        p.identity for p in inv.plasmids_by_insert_identity["https://example.org/partA"]
    ] == [p1.identity, p2.identity]
    assert [p.identity for p in inv.plasmids_by_fusion_sites[("A", "B")]] == [
        p1.identity,
        p2.identity,
    ]
    assert [p.identity for p in inv.plasmids_by_antibiotic["Ampicillin"]] == [
        p1.identity,
        p2.identity,
    ]

    key = (("A", "B"), "Ampicillin")
    assert [b.identity for b in inv.backbones_by_fusion_sites_and_antibiotic[key]] == [
        b1.identity,
        b2.identity,
    ]
    assert (
        inv.find_backbone(
            fusion_sites=("A", "B"),
            antibiotic="Ampicillin",
            stage=BuildStage.ASSEMBLY_LVL1,
        )
        == b1
    )

    assert inv.find_restriction_enzyme("BsaI") == e1
    assert inv.find_ligase("T4_DNA_ligase") == l1
    assert inv.find_ligase().identity == l1.identity

    assert [
        p.identity for p in inv.find_single_part_plasmids("https://example.org/partA")
    ] == [p1.identity, p2.identity]
    assert [
        p.identity for p in inv.find_lvl1_region_plasmids("https://example.org/region1")
    ] == [p1.identity]
    assert inv.find_lvl1_region_plasmids(
        "https://example.org/partA", min_material_state=MaterialState.GENERATED
    ) == [p2]


def test_add_generated_product_updates_indexes_immediately():
    inv = Inventory()
    product = _plasmid(
        "https://example.org/generated1",
        ["https://example.org/partG"],
        fusion_sites=("C", "D"),
        antibiotic="Kanamycin",
        state=MaterialState.GENERATED,
    )

    inv.add_generated_product(product)

    assert inv.generated_products_by_identity[product.identity] == product
    assert inv.plasmids_by_identity[product.identity] == product
    assert inv.find_single_part_plasmids("https://example.org/partG") == [product]
    assert inv.plasmids_by_fusion_sites[("C", "D")] == [product]
    assert inv.plasmids_by_antibiotic["Kanamycin"] == [product]


def test_add_generated_product_replaces_existing_secondary_indexes():
    inv = Inventory()
    original = _plasmid(
        "https://example.org/generated2",
        ["https://example.org/partOld"],
        fusion_sites=("A", "B"),
        antibiotic="Ampicillin",
        state=MaterialState.GENERATED,
    )
    updated = _plasmid(
        "https://example.org/generated2",
        ["https://example.org/partNew"],
        fusion_sites=("C", "D"),
        antibiotic="Kanamycin",
        state=MaterialState.ASSEMBLED,
    )

    inv.add_generated_product(original)
    inv.add_generated_product(updated)

    assert inv.plasmids_by_identity[updated.identity] == updated
    assert inv.generated_products_by_identity[updated.identity] == updated
    assert inv.find_single_part_plasmids("https://example.org/partOld") == []
    assert inv.find_single_part_plasmids("https://example.org/partNew") == [updated]
    assert inv.plasmids_by_fusion_sites.get(("A", "B"), []) == []
    assert inv.plasmids_by_fusion_sites[("C", "D")] == [updated]
    assert inv.plasmids_by_antibiotic.get("Ampicillin", []) == []
    assert inv.plasmids_by_antibiotic["Kanamycin"] == [updated]
