from pathlib import Path

import sbol2

from buildcompiler.api import domestication
from buildcompiler.buildcompiler import BuildCompiler
from buildcompiler.domain import IndexedBackbone, IndexedReagent, StageStatus
from buildcompiler.inventory import Inventory


COLLECTION_PATHS = [
    "tests/test_files/CIDARMoCloParts_collection.xml",
    "tests/test_files/CIDARMoCloPlasmidsKit_collection.xml",
    "tests/test_files/Enzyme_Implementations_collection.xml",
    "tests/test_files/impl_test_collection.xml",
]


def _read_docs(paths):
    missing = [path for path in paths if not Path(path).exists()]
    if missing:
        raise AssertionError(f"Missing downloaded SBOL fixture(s): {missing}")

    docs = []
    for path in paths:
        doc = sbol2.Document()
        doc.read(path)
        docs.append(doc)
    return docs


def test_from_local_documents_merges_downloaded_collections_offline():
    compiler = BuildCompiler.from_local_documents(_read_docs(COLLECTION_PATHS))

    assert compiler.sbh is None
    assert len(compiler.sbol_doc.componentDefinitions) >= 90
    assert len(compiler.indexed_plasmids) >= 20
    assert len(compiler.indexed_backbones) >= 4
    assert len(compiler.restriction_enzyme_implementations) >= 2
    assert len(compiler.ligase_implementations) >= 1


def test_local_collections_support_two_offline_lvl1_designs():
    design_paths = [
        "tests/test_files/moclo_parts_circuit.xml",
        "tests/test_files/mocloparts116.xml",
    ]
    collection_docs = _read_docs(COLLECTION_PATHS)
    design_docs = _read_docs(design_paths)
    designs = [
        next(cd for cd in doc.componentDefinitions if len(cd.components) > 1)
        for doc in design_docs
    ]

    compiler = BuildCompiler.from_local_documents(
        collection_docs, design_doc=design_docs[0]
    )
    compiler.index_document(design_docs[1])

    product_names = []
    for index, design in enumerate(designs, start=1):
        product_doc = sbol2.Document()
        assembly_dict, product_doc = compiler.assembly_lvl1(
            [design], final_doc=product_doc, product_name=f"offline_multi_{index}"
        )
        products = assembly_dict[design.identity]
        assert len(products) == 1
        assert len(product_doc.componentDefinitions) >= 1
        product_names.append(products[0].plasmid_definition.displayId)

    assert product_names == ["qlSBuNBL_offline_multi_1", "i0mwvNcgH_offline_multi_2"]


def test_local_collections_support_four_part_domestication_from_index():
    compiler = BuildCompiler.from_local_documents(_read_docs(COLLECTION_PATHS))
    backbones = []
    seen = set()
    for indexed in [*compiler.indexed_backbones, *compiler.indexed_plasmids]:
        definition = getattr(indexed, "plasmid_definition", None)
        fusion_sites = tuple(getattr(indexed, "fusion_sites", ()) or ())
        antibiotic = getattr(indexed, "antibiotic_resistance", None)
        if (
            definition is None
            or not fusion_sites
            or antibiotic != "Ampicillin"
            or definition.identity in seen
        ):
            continue
        seen.add(definition.identity)
        backbones.append(
            IndexedBackbone(
                identity=definition.identity,
                display_id=definition.displayId,
                metadata={
                    "fusion_sites": fusion_sites,
                    "antibiotic": antibiotic,
                    "insertion_index": 0,
                },
                sbol_component=definition,
            )
        )

    reagents = []
    for impl in compiler.restriction_enzyme_implementations:
        definition = compiler.sbol_doc.find(impl.built)
        reagents.append(
            IndexedReagent(
                definition.identity,
                display_id=definition.displayId,
                name=definition.displayId,
                reagent_type="restriction_enzyme",
            )
        )
    for impl in compiler.ligase_implementations:
        definition = compiler.sbol_doc.find(impl.built)
        reagents.append(
            IndexedReagent(
                definition.identity,
                display_id=definition.displayId,
                name=definition.displayId,
                reagent_type="ligase",
            )
        )

    inventory = Inventory(backbones=backbones, reagents=reagents)
    part_ids = ["J23100", "B0034", "E0030_yfp", "B0015"]
    parts = [
        next(
            cd
            for cd in compiler.sbol_doc.componentDefinitions
            if cd.displayId == display_id
        )
        for display_id in part_ids
    ]

    results = domestication(
        parts,
        inventory=inventory,
        source_document=compiler.sbol_doc,
        target_document=sbol2.Document(),
    )

    assert [result.status for result in results] == [StageStatus.SUCCESS] * len(
        part_ids
    )
    for result in results:
        artifact = result.protocol_artifacts["domestication"]
        assert "GGTCTC" not in artifact["domesticated_part_sequence"]
        assert "GAGACC" not in artifact["domesticated_part_sequence"]
        assert artifact["backbone_sequence"] in artifact["final_plasmid_sequence"]
