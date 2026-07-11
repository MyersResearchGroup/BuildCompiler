import sbol2

from buildcompiler.domain import IndexedBackbone, IndexedReagent, MaterialState
from buildcompiler.planning import SequenceEditProposal
from buildcompiler.sbol import DomesticationJob, DomesticationService


def test_domestication_service_returns_generated_plasmid_with_provenance() -> None:
    source = sbol2.Document()
    target = sbol2.Document()
    part = sbol2.ComponentDefinition("https://example.org/part")
    part.roles = ["https://example.org/role1", "https://example.org/role2"]
    part_sequence = sbol2.Sequence("part_sequence")
    part_sequence.elements = "AAAAGGTCTCTTTT"
    part_sequence.encoding = sbol2.SBOL_ENCODING_IUPAC
    source.addSequence(part_sequence)
    part.sequences = [part_sequence.identity]
    source.addComponentDefinition(part)
    backbone = sbol2.ComponentDefinition("bb")
    backbone_sequence = sbol2.Sequence("bb_sequence")
    backbone_sequence.elements = "CCCCGGGG"
    backbone_sequence.encoding = sbol2.SBOL_ENCODING_IUPAC
    source.addSequence(backbone_sequence)
    backbone.sequences = [backbone_sequence.identity]
    source.addComponentDefinition(backbone)

    service = DomesticationService()
    result = service.run(
        DomesticationJob(
            part_identity=part.identity,
            part_display_id="part",
            part_component=part,
            backbone=IndexedBackbone(
                backbone.identity,
                metadata={
                    "stage": "domestication",
                    "sequence": "TTTT",
                    "insertion_index": 4,
                },
            ),
            restriction_enzyme=IndexedReagent(
                "https://example.org/bsai",
                name="BsaI",
                reagent_type="restriction_enzyme",
            ),
            ligase=IndexedReagent(
                "https://example.org/lig", name="T4_DNA_ligase", reagent_type="ligase"
            ),
            source_document=source,
            target_document=target,
            part_role="promoter",
            fusion_site_sequences=("GGAG", "TACT"),
            fusion_site_names=("A", "B"),
            sequence_edit_proposals=[
                SequenceEditProposal(
                    part.identity, "BsaI", "GGTCTC", 4, "GGTCTC", "GGTCTA", "reason"
                )
            ],
        )
    )

    assert result.product.state == MaterialState.GENERATED
    assert result.product.metadata["source_part_identity"] == part.identity
    assert result.product.metadata["insert_identities"] == [part.identity]
    assert result.product.roles == list(part.roles)
    assert result.product.metadata["source_sequence"] == "AAAAGGTCTCTTTT"
    assert result.product.metadata["domesticated_part_sequence"] == "AAAAGGTCTATTTT"
    generated_insert = result.product.metadata["generated_insert_sequence"]
    assert len(generated_insert) == 35 + 6 + 4 + 14 + 4 + 6 + 35
    assert generated_insert[35:45] == "GGTCTCGGAG"
    assert generated_insert[45:59] == "AAAAGGTCTATTTT"
    assert generated_insert[59:69] == "TACTGAGACC"
    assert result.product.metadata["backbone_sequence"] == "CCCCGGGG"
    assert result.product.metadata["fusion_site_sequences"] == ["GGAG", "TACT"]
    assert result.product.metadata["fusion_site_names"] == ["A", "B"]
    assert (
        result.product.metadata["final_plasmid_sequence"]
        == "CCCCGGAGAAAAGGTCTATTTTTACTGGGG"
    )
    insert_component = target.find(result.product.metadata["generated_insert_identity"])
    assert isinstance(insert_component, sbol2.ComponentDefinition)
    assert insert_component.sequences == [
        result.product.metadata["generated_insert_sequence_identity"]
    ]
    insert_sequence = target.find(
        result.product.metadata["generated_insert_sequence_identity"]
    )
    assert isinstance(insert_sequence, sbol2.Sequence)
    assert insert_sequence.elements == generated_insert
    implementation_identity = result.product.metadata["implementation_identity"]
    implementation = target.find(implementation_identity)
    assert isinstance(implementation, sbol2.Implementation)
    assert implementation.built == result.product.identity
    final_sequence = target.find(
        result.product.metadata["final_plasmid_sequence_identity"]
    )
    assert isinstance(final_sequence, sbol2.Sequence)
    assert final_sequence.elements == "CCCCGGAGAAAAGGTCTATTTTTACTGGGG"
    assert result.logs
