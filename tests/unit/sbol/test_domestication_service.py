import sbol2

from buildcompiler.domain import IndexedBackbone, IndexedReagent, MaterialState
from buildcompiler.planning import SequenceEditProposal
from buildcompiler.sbol import DomesticationJob, DomesticationService


def test_domestication_service_returns_generated_plasmid_with_provenance() -> None:
    source = sbol2.Document()
    target = sbol2.Document()
    part = sbol2.ComponentDefinition("https://example.org/part")
    part.roles = ["https://example.org/role1", "https://example.org/role2"]
    source.addComponentDefinition(part)

    service = DomesticationService()
    result = service.run(
        DomesticationJob(
            part_identity=part.identity,
            part_display_id="part",
            part_component=part,
            backbone=IndexedBackbone("https://example.org/bb", metadata={"stage": "domestication"}),
            restriction_enzyme=IndexedReagent("https://example.org/bsai", name="BsaI", reagent_type="restriction_enzyme"),
            ligase=IndexedReagent("https://example.org/lig", name="T4_DNA_ligase", reagent_type="ligase"),
            source_document=source,
            target_document=target,
            sequence_edit_proposals=[
                SequenceEditProposal(part.identity, "BsaI", "GGTCTC", 5, "GGTCTC", "GGTCTA", "reason")
            ],
        )
    )

    assert result.product.state == MaterialState.GENERATED
    assert result.product.metadata["source_part_identity"] == part.identity
    assert result.product.metadata["insert_identities"] == [part.identity]
    assert result.product.roles == list(part.roles)
    implementation_identity = result.product.metadata["implementation_identity"]
    implementation = target.find(implementation_identity)
    assert isinstance(implementation, sbol2.Implementation)
    assert implementation.built == result.product.identity
    assert result.logs
